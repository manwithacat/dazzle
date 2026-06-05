"""Real-PostgreSQL proof of two-phase activation + org-switch (auth Plan 1b).

Marked e2e + postgres: skipped without TEST_DATABASE_URL/DATABASE_URL.
Mirrors tests/integration/test_auth_membership_pg.py's scratch-DB harness.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def scratch_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin_url = _admin_url()
    base, _, _old = admin_url.rpartition("/")
    scratch = f"dazzle_auth_1b_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep — uuid-derived
    try:
        yield url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (scratch,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep


# ── Task 3: set_session_active_membership ────────────────────────────────────


def test_set_session_active_membership_happy_path(scratch_url: str) -> None:
    from dazzle.back.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="a@b.test", password="pw123456")
    uid = str(user.id)
    m = store.create_membership(tenant_id="t-1", identity_id=uid, roles=["admin"])
    session = store.create_session(user)  # no active membership yet

    ok = store.set_session_active_membership(session.id, m.id, identity_id=uid)
    assert ok is True
    ctx = store.validate_session(session.id)
    assert ctx.active_membership is not None
    assert ctx.active_membership.id == m.id


def test_set_session_active_membership_rejects_foreign_membership(scratch_url: str) -> None:
    from dazzle.back.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user_a = store.create_user(email="a@b.test", password="pw123456")
    user_b = store.create_user(email="b@b.test", password="pw123456")
    m_b = store.create_membership(tenant_id="t-b", identity_id=str(user_b.id), roles=["admin"])
    session_a = store.create_session(user_a)

    # A must not be able to activate B's membership.
    ok = store.set_session_active_membership(session_a.id, m_b.id, identity_id=str(user_a.id))
    assert ok is False
    ctx = store.validate_session(session_a.id)
    assert ctx.active_membership is None


def test_set_session_active_membership_rejects_suspended(scratch_url: str) -> None:
    from dazzle.back.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="a@b.test", password="pw123456")
    uid = str(user.id)
    m = store.create_membership(
        tenant_id="t-1", identity_id=uid, roles=["admin"], status="suspended"
    )
    session = store.create_session(user)

    ok = store.set_session_active_membership(session.id, m.id, identity_id=uid)
    assert ok is False


# ── Task 4: activation at password login / signup ────────────────────────────


def _app_with_store(store):
    """Minimal FastAPI app wiring the password-login router to `store`."""
    from fastapi import FastAPI

    from dazzle.back.runtime.auth.password_login_routes import (
        create_password_login_routes,
    )

    app = FastAPI()
    app.state.auth_store = store
    app.state.auth_password_mode_enabled = True
    app.include_router(create_password_login_routes())
    return app


def _client(app):
    from fastapi.testclient import TestClient

    return TestClient(app, follow_redirects=False)


def test_password_login_single_membership_auto_activates(scratch_url: str) -> None:
    from dazzle.back.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="solo@b.test", password="pw123456")
    store.create_membership(tenant_id="t-1", identity_id=str(user.id), roles=["admin"])

    resp = _client(_app_with_store(store)).post(
        "/auth/login/password", data={"email": "solo@b.test", "password": "pw123456"}
    )
    assert resp.status_code == 303
    sid = resp.cookies.get("dazzle_session")
    assert sid is not None
    ctx = store.validate_session(sid)
    assert ctx.active_membership is not None
    assert ctx.active_membership.tenant_id == "t-1"
    assert resp.headers["location"] == "/app"


def test_password_login_multi_membership_redirects_to_picker(scratch_url: str) -> None:
    from dazzle.back.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="multi@b.test", password="pw123456")
    store.create_membership(tenant_id="t-1", identity_id=str(user.id), roles=["admin"])
    store.create_membership(tenant_id="t-2", identity_id=str(user.id), roles=["member"])

    resp = _client(_app_with_store(store)).post(
        "/auth/login/password", data={"email": "multi@b.test", "password": "pw123456"}
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/select-org"
    sid = resp.cookies.get("dazzle_session")
    ctx = store.validate_session(sid)
    assert ctx.active_membership is None  # not yet chosen


def test_password_login_no_membership_redirects_to_no_orgs(scratch_url: str) -> None:
    from dazzle.back.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    store.create_user(email="orphan@b.test", password="pw123456")

    resp = _client(_app_with_store(store)).post(
        "/auth/login/password", data={"email": "orphan@b.test", "password": "pw123456"}
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/no-orgs"
