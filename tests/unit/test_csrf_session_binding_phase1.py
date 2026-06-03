"""Phase 1 of the declarative-CSRF spec: the token is session-bound."""

import importlib.util
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy as sa

from dazzle.back.runtime.auth.models import SessionRecord


def _session() -> SessionRecord:
    return SessionRecord(
        user_id=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )


class TestSessionRecordCsrfSecret:
    def test_session_record_has_csrf_secret(self) -> None:
        s = _session()
        assert isinstance(s.csrf_secret, str) and len(s.csrf_secret) >= 32

    def test_csrf_secret_is_unique_per_session(self) -> None:
        assert _session().csrf_secret != _session().csrf_secret


def _load_migration():
    path = (
        Path(__file__).resolve().parents[2]
        / "src/dazzle/back/alembic/versions/0005_session_csrf_secret.py"
    )
    spec = importlib.util.spec_from_file_location("m0005", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMigration0005:
    def test_revision_chain(self) -> None:
        m = _load_migration()
        assert m.revision == "0005_session_csrf_secret"
        assert m.down_revision == "0004_widen_alembic_version_num"

    def test_upgrade_adds_column_idempotently(self) -> None:
        """upgrade() adds csrf_secret and is safe to run twice."""
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        engine = sa.create_engine("sqlite://")
        with engine.connect() as conn:
            conn.execute(
                sa.text(
                    "CREATE TABLE sessions (id TEXT PRIMARY KEY, user_id TEXT, "
                    "created_at TEXT, expires_at TEXT, ip_address TEXT, user_agent TEXT)"
                )
            )
            ctx = MigrationContext.configure(conn)
            m = _load_migration()
            with Operations.context(ctx):
                m.upgrade()
                m.upgrade()  # second run must not raise (idempotent)
            cols = {c["name"] for c in sa.inspect(conn).get_columns("sessions")}
            assert "csrf_secret" in cols


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
class TestLoginCsrfCookie:
    """The login handler binds the dazzle_csrf cookie to the session secret,
    and logout clears it (declarative-CSRF Phase 1, Task 4)."""

    @pytest.fixture
    def app(self) -> Any:
        """FastAPI app mounting the auth router — mirrors test_auth.py's harness."""
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("FastAPI not installed")

        from dazzle.back.runtime.auth import AuthStore, create_auth_routes

        auth_store = AuthStore(os.environ["DATABASE_URL"])
        fastapi_app = FastAPI()
        fastapi_app.include_router(create_auth_routes(auth_store))
        return fastapi_app, TestClient(fastapi_app), auth_store

    def _login(self, client: Any, auth_store: Any) -> Any:
        email = f"csrf_{uuid4().hex}@example.com"
        auth_store.create_user(email=email, password="password123")
        return client.post("/auth/login", json={"email": email, "password": "password123"})

    def test_login_sets_dazzle_csrf_cookie(self, app: Any) -> None:
        """(a) login sets a non-empty dazzle_csrf cookie (>=32 chars)."""
        _, client, auth_store = app
        response = self._login(client, auth_store)

        assert response.status_code == 200
        assert "dazzle_csrf" in response.cookies
        token = response.cookies["dazzle_csrf"]
        assert isinstance(token, str) and len(token) >= 32

    def test_dazzle_csrf_equals_session_secret(self, app: Any) -> None:
        """(b) the cookie value equals the session's stored csrf_secret."""
        _, client, auth_store = app
        response = self._login(client, auth_store)

        session_id = response.cookies["dazzle_session"]
        session = auth_store.get_session(session_id)
        assert session is not None
        assert response.cookies["dazzle_csrf"] == session.csrf_secret

    def test_logout_clears_dazzle_csrf_cookie(self, app: Any) -> None:
        """(c) logout clears the dazzle_csrf cookie."""
        _, client, auth_store = app
        login = self._login(client, auth_store)
        assert "dazzle_csrf" in login.cookies

        logout = client.post("/auth/logout", cookies=login.cookies)

        # A delete_cookie emits a Set-Cookie with an empty value + past expiry.
        set_cookie_headers = logout.headers.get_list("set-cookie")
        csrf_clears = [h for h in set_cookie_headers if h.startswith("dazzle_csrf=")]
        assert csrf_clears, f"no dazzle_csrf clear header in {set_cookie_headers!r}"
        cleared = csrf_clears[0]
        assert 'dazzle_csrf=""' in cleared or "dazzle_csrf=;" in cleared
        assert "expires=" in cleared.lower() or "max-age=0" in cleared.lower()
