"""Tests for OpsDatabase PostgreSQL dual-backend support."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from dazzle_back.runtime.ops_database import (
    AnalyticsEvent,
    ApiCallRecord,
    ComponentType,
    HealthCheckRecord,
    HealthStatus,
    OpsDatabase,
    RetentionConfig,
)

# ---------------------------------------------------------------------------
# Constructor / backend selection
# ---------------------------------------------------------------------------


class TestOpsDatabaseConstructor:
    """Tests for OpsDatabase constructor and backend selection."""

    def test_sqlite_default_path(self, tmp_path: Path) -> None:
        db = OpsDatabase(db_path=tmp_path / "ops.db")
        assert db.backend_type == "sqlite"
        assert db._db_path == tmp_path / "ops.db"
        assert db._use_postgres is False

    def test_database_url_selects_postgres(self, tmp_path: Path) -> None:
        """Constructor with database_url should set postgres mode (without connecting)."""
        # We can't actually connect to PG in unit tests, so just verify
        # the backend selection logic by patching _init_schema
        with patch.object(OpsDatabase, "_init_schema"):
            db = OpsDatabase(
                db_path=tmp_path / "ops.db",
                database_url="postgresql://localhost/test",
            )
            assert db.backend_type == "postgres"
            assert db._use_postgres is True
            assert db._pg_url == "postgresql://localhost/test"

    def test_database_url_normalizes_heroku_prefix(self, tmp_path: Path) -> None:
        with patch.object(OpsDatabase, "_init_schema"):
            db = OpsDatabase(
                database_url="postgres://localhost/test",
            )
            assert db._pg_url == "postgresql://localhost/test"

    def test_database_url_takes_precedence(self, tmp_path: Path) -> None:
        with patch.object(OpsDatabase, "_init_schema"):
            db = OpsDatabase(
                db_path=tmp_path / "ops.db",
                database_url="postgresql://localhost/test",
            )
            assert db._use_postgres is True
            assert db._db_path is None

    def test_retention_config_stored(self, tmp_path: Path) -> None:
        config = RetentionConfig(health_checks_days=7)
        db = OpsDatabase(db_path=tmp_path / "ops.db", retention=config)
        assert db.retention.health_checks_days == 7


# ---------------------------------------------------------------------------
# SQLite full CRUD (integration test with real SQLite)
# ---------------------------------------------------------------------------


class TestOpsDatabaseSQLiteCRUD:
    """Full CRUD test using real SQLite backend."""

    @pytest.fixture()
    def db(self, tmp_path: Path) -> OpsDatabase:
        return OpsDatabase(db_path=tmp_path / "ops.db")

    def test_credentials_crud(self, db: OpsDatabase) -> None:
        assert db.has_credentials() is False
        creds = db.create_credentials("admin", "secret123")
        assert creds.username == "admin"
        assert db.has_credentials() is True
        assert db.verify_credentials("admin", "secret123") is True
        assert db.verify_credentials("admin", "wrong") is False
        assert db.verify_credentials("nobody", "secret123") is False

    def test_credentials_upsert(self, db: OpsDatabase) -> None:
        db.create_credentials("admin", "pass1")
        db.create_credentials("admin", "pass2")
        assert db.verify_credentials("admin", "pass2") is True
        assert db.verify_credentials("admin", "pass1") is False

    def test_health_check_crud(self, db: OpsDatabase) -> None:
        record = HealthCheckRecord(
            id=str(uuid4()),
            component="db",
            component_type=ComponentType.DATABASE,
            status=HealthStatus.HEALTHY,
            latency_ms=1.5,
            message="OK",
            metadata={"version": "1.0"},
            checked_at=datetime.now(UTC),
        )
        db.record_health_check(record)

        latest = db.get_latest_health("db")
        assert len(latest) == 1
        assert latest[0].component == "db"
        assert latest[0].status == HealthStatus.HEALTHY
        assert latest[0].metadata == {"version": "1.0"}

    def test_health_history(self, db: OpsDatabase) -> None:
        for i in range(3):
            record = HealthCheckRecord(
                id=str(uuid4()),
                component="api",
                component_type=ComponentType.EXTERNAL_API,
                status=HealthStatus.HEALTHY,
                latency_ms=float(i),
                message=None,
                metadata={},
                checked_at=datetime.now(UTC),
            )
            db.record_health_check(record)
        history = db.get_health_history("api", hours=1)
        assert len(history) == 3

    def test_api_call_crud(self, db: OpsDatabase) -> None:
        record = ApiCallRecord(
            id=str(uuid4()),
            service_name="stripe",
            endpoint="/v1/charges",
            method="POST",
            status_code=200,
            latency_ms=150.0,
            request_size_bytes=512,
            response_size_bytes=1024,
            error_message=None,
            cost_cents=0.5,
            metadata={"idempotency_key": "abc"},
            called_at=datetime.now(UTC),
            tenant_id="t1",
        )
        db.record_api_call(record)

        stats = db.get_api_call_stats(service_name="stripe", hours=1)
        assert "stripe" in stats
        assert stats["stripe"]["total_calls"] == 1

    def test_analytics_crud(self, db: OpsDatabase) -> None:
        event = AnalyticsEvent(
            id=str(uuid4()),
            tenant_id="t1",
            event_type="page_view",
            event_name="dashboard",
            user_id="u1",
            session_id="s1",
            properties={"page": "/dashboard"},
            recorded_at=datetime.now(UTC),
        )
        db.record_analytics_event(event)

        summary = db.get_analytics_summary("t1", days=1)
        assert summary["tenant_id"] == "t1"
        assert "page_view" in summary["events_by_type"]

    def test_event_log_crud(self, db: OpsDatabase) -> None:
        event_id = db.record_event(
            event_type="task.created",
            entity_name="Task",
            entity_id="123",
            payload={"title": "Test"},
            correlation_id="corr-1",
            tenant_id="t1",
        )
        assert event_id

        events = db.get_events(entity_name="Task")
        assert len(events) == 1
        assert events[0]["event_type"] == "task.created"
        assert events[0]["payload"] == {"title": "Test"}

    def test_retention_config_crud(self, db: OpsDatabase) -> None:
        config = RetentionConfig(health_checks_days=7, api_calls_days=14)
        db.set_retention_config(config)
        assert db.get_retention_config().health_checks_days == 7

        # Upsert with new values
        config2 = RetentionConfig(health_checks_days=3)
        db.set_retention_config(config2)
        assert db.get_retention_config().health_checks_days == 3

    def test_enforce_retention(self, db: OpsDatabase) -> None:
        result = db.enforce_retention()
        assert "health_checks" in result
        assert "api_calls" in result
        assert "analytics_events" in result
        assert "event_log" in result


# ---------------------------------------------------------------------------
# INSERT OR REPLACE → ON CONFLICT branching
# ---------------------------------------------------------------------------


class TestInsertOrReplaceBranching:
    """Verify that Postgres paths use ON CONFLICT instead of INSERT OR REPLACE."""

    def test_create_credentials_uses_on_conflict_for_postgres(self) -> None:
        """Verify the Postgres branch generates ON CONFLICT SQL."""
        with patch.object(OpsDatabase, "_init_schema"):
            db = OpsDatabase(database_url="postgresql://localhost/test")

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.commit = MagicMock()
        mock_conn.rollback = MagicMock()
        mock_conn.close = MagicMock()

        with patch.object(db, "_get_sync_connection", return_value=mock_conn):
            db.create_credentials("admin", "secret")

        # Check that the SQL contains ON CONFLICT
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        assert "ON CONFLICT" in sql
        assert "INSERT OR REPLACE" not in sql

    def test_set_retention_uses_on_conflict_for_postgres(self) -> None:
        with patch.object(OpsDatabase, "_init_schema"):
            db = OpsDatabase(database_url="postgresql://localhost/test")

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.commit = MagicMock()
        mock_conn.rollback = MagicMock()
        mock_conn.close = MagicMock()

        with patch.object(db, "_get_sync_connection", return_value=mock_conn):
            db.set_retention_config(RetentionConfig())

        # All 4 retention keys should use ON CONFLICT
        for call in mock_cursor.execute.call_args_list:
            sql = call[0][0]
            if "INSERT" in sql:
                assert "ON CONFLICT" in sql
                assert "INSERT OR REPLACE" not in sql

    def test_create_credentials_uses_insert_or_replace_for_sqlite(self, tmp_path: Path) -> None:
        db = OpsDatabase(db_path=tmp_path / "ops.db")
        # SQLite uses INSERT OR REPLACE — just verify it works
        db.create_credentials("admin", "pass1")
        db.create_credentials("admin", "pass2")
        assert db.verify_credentials("admin", "pass2")


# ---------------------------------------------------------------------------
# Placeholder format
# ---------------------------------------------------------------------------


class TestPlaceholderFormat:
    """Verify placeholder selection based on backend."""

    def test_sqlite_placeholder(self, tmp_path: Path) -> None:
        db = OpsDatabase(db_path=tmp_path / "ops.db")
        assert db._ph == "?"

    def test_postgres_placeholder(self) -> None:
        with patch.object(OpsDatabase, "_init_schema"):
            db = OpsDatabase(database_url="postgresql://localhost/test")
        assert db._ph == "%s"
