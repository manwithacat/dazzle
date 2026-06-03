"""Phase 1 of the declarative-CSRF spec: the token is session-bound."""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

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
