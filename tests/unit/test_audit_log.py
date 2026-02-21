"""Tests for audit log infrastructure.

Tests AuditLogger queue behavior, writing, query methods, and helpers.
"""

from __future__ import annotations

import asyncio
import sqlite3
from unittest.mock import MagicMock

import pytest

from dazzle_back.runtime.audit_log import (
    AuditLogger,
    create_audit_context_from_request,
    measure_evaluation_time,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary SQLite database path."""
    return f"sqlite:///{tmp_path / 'test_audit.db'}"


@pytest.fixture
def logger(db_path):
    """Create an AuditLogger with a temp database."""
    return AuditLogger(database_url=db_path, flush_interval=0.1)


# =============================================================================
# AuditLogger Init
# =============================================================================


class TestAuditLoggerInit:
    def test_creates_table(self, db_path, tmp_path) -> None:
        """Logger should create the audit log table on init."""
        AuditLogger(database_url=db_path)
        db_file = tmp_path / "test_audit.db"
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_dazzle_audit_log'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_creates_indexes(self, db_path, tmp_path) -> None:
        """Logger should create indexes on init."""
        AuditLogger(database_url=db_path)
        db_file = tmp_path / "test_audit.db"
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert "idx_audit_entity" in indexes
        assert "idx_audit_user" in indexes
        assert "idx_audit_timestamp" in indexes


# =============================================================================
# Logging and Flushing
# =============================================================================


class TestAuditLogging:
    @pytest.mark.asyncio
    async def test_log_and_flush(self, logger) -> None:
        """Entries queued via log_decision should be flushed to DB."""
        await logger.log_decision(
            operation="create",
            entity_name="Task",
            entity_id="task-1",
            decision="allow",
            matched_policy="permit create for role(admin)",
            policy_effect="permit",
            user_id="user-1",
            user_email="admin@example.com",
            user_roles=["admin"],
        )
        # Manually flush
        await logger._flush()

        logs = logger.query_logs(entity_name="Task")
        assert len(logs) == 1
        assert logs[0]["entity_name"] == "Task"
        assert logs[0]["decision"] == "allow"
        assert logs[0]["operation"] == "create"

    @pytest.mark.asyncio
    async def test_multiple_entries(self, logger) -> None:
        """Multiple entries should all be flushed."""
        for i in range(5):
            await logger.log_decision(
                operation="read",
                entity_name="Task",
                entity_id=f"task-{i}",
                decision="allow",
                matched_policy="authenticated",
                policy_effect="permit",
            )
        await logger._flush()
        logs = logger.query_logs(entity_name="Task")
        assert len(logs) == 5

    @pytest.mark.asyncio
    async def test_queue_full_drops(self) -> None:
        """When queue is full, entries should be dropped."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            db_url = f"sqlite:///{Path(td) / 'test.db'}"
            small_logger = AuditLogger(database_url=db_url, max_queue_size=2)
            # Fill queue
            await small_logger.log_decision(
                operation="read",
                entity_name="A",
                entity_id="1",
                decision="allow",
                matched_policy="p",
                policy_effect="permit",
            )
            await small_logger.log_decision(
                operation="read",
                entity_name="B",
                entity_id="2",
                decision="allow",
                matched_policy="p",
                policy_effect="permit",
            )
            # This should be dropped
            await small_logger.log_decision(
                operation="read",
                entity_name="C",
                entity_id="3",
                decision="allow",
                matched_policy="p",
                policy_effect="permit",
            )
            assert small_logger._dropped_count >= 1

    @pytest.mark.asyncio
    async def test_deny_entries(self, logger) -> None:
        """Deny decisions should also be logged."""
        await logger.log_decision(
            operation="delete",
            entity_name="Invoice",
            entity_id="inv-1",
            decision="deny",
            matched_policy="forbid delete for role(intern)",
            policy_effect="forbid",
            user_id="user-2",
        )
        await logger._flush()
        logs = logger.query_logs(entity_name="Invoice")
        assert len(logs) == 1
        assert logs[0]["decision"] == "deny"
        assert logs[0]["policy_effect"] == "forbid"


# =============================================================================
# Query Methods
# =============================================================================


class TestAuditQueries:
    @pytest.mark.asyncio
    async def test_query_by_operation(self, logger) -> None:
        await logger.log_decision(
            operation="create",
            entity_name="Task",
            entity_id="1",
            decision="allow",
            matched_policy="p",
            policy_effect="permit",
        )
        await logger.log_decision(
            operation="delete",
            entity_name="Task",
            entity_id="2",
            decision="deny",
            matched_policy="p",
            policy_effect="forbid",
        )
        await logger._flush()

        creates = logger.query_logs(operation="create")
        assert len(creates) == 1
        assert creates[0]["operation"] == "create"

    @pytest.mark.asyncio
    async def test_query_by_user(self, logger) -> None:
        await logger.log_decision(
            operation="read",
            entity_name="Task",
            entity_id="1",
            decision="allow",
            matched_policy="p",
            policy_effect="permit",
            user_id="alice",
        )
        await logger.log_decision(
            operation="read",
            entity_name="Task",
            entity_id="2",
            decision="allow",
            matched_policy="p",
            policy_effect="permit",
            user_id="bob",
        )
        await logger._flush()

        alice_logs = logger.query_logs(user_id="alice")
        assert len(alice_logs) == 1

    @pytest.mark.asyncio
    async def test_query_entity_logs(self, logger) -> None:
        await logger.log_decision(
            operation="read",
            entity_name="Task",
            entity_id="task-42",
            decision="allow",
            matched_policy="p",
            policy_effect="permit",
        )
        await logger.log_decision(
            operation="update",
            entity_name="Task",
            entity_id="task-42",
            decision="allow",
            matched_policy="p",
            policy_effect="permit",
        )
        await logger.log_decision(
            operation="read",
            entity_name="Task",
            entity_id="task-99",
            decision="allow",
            matched_policy="p",
            policy_effect="permit",
        )
        await logger._flush()

        logs = logger.query_entity_logs("Task", "task-42")
        assert len(logs) == 2

    @pytest.mark.asyncio
    async def test_query_stats(self, logger) -> None:
        for _ in range(3):
            await logger.log_decision(
                operation="read",
                entity_name="Task",
                entity_id="1",
                decision="allow",
                matched_policy="p",
                policy_effect="permit",
            )
        await logger.log_decision(
            operation="delete",
            entity_name="Task",
            entity_id="1",
            decision="deny",
            matched_policy="p",
            policy_effect="forbid",
        )
        await logger._flush()

        stats = logger.query_stats()
        assert stats["total"] == 4
        assert stats["by_decision"]["allow"] == 3
        assert stats["by_decision"]["deny"] == 1
        assert stats["by_operation"]["read"] == 3

    @pytest.mark.asyncio
    async def test_query_limit(self, logger) -> None:
        for i in range(10):
            await logger.log_decision(
                operation="read",
                entity_name="Task",
                entity_id=str(i),
                decision="allow",
                matched_policy="p",
                policy_effect="permit",
            )
        await logger._flush()
        logs = logger.query_logs(limit=3)
        assert len(logs) == 3


# =============================================================================
# Background Flush Loop
# =============================================================================


class TestFlushLoop:
    @pytest.mark.asyncio
    async def test_start_stop(self, logger) -> None:
        """Logger can be started and stopped without errors."""
        logger.start()
        await logger.log_decision(
            operation="read",
            entity_name="Task",
            entity_id="1",
            decision="allow",
            matched_policy="p",
            policy_effect="permit",
        )
        # Wait for at least one flush cycle
        await asyncio.sleep(0.2)
        await logger.stop()

        logs = logger.query_logs()
        assert len(logs) == 1


# =============================================================================
# Helper Functions
# =============================================================================


class TestHelpers:
    def test_create_audit_context_from_request(self) -> None:
        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.url.path = "/api/tasks"
        request.method = "GET"

        ctx = create_audit_context_from_request(request)
        assert ctx["ip_address"] == "127.0.0.1"
        assert ctx["request_path"] == "/api/tasks"
        assert ctx["request_method"] == "GET"

    def test_create_audit_context_missing_client(self) -> None:
        request = MagicMock(spec=[])
        ctx = create_audit_context_from_request(request)
        assert ctx["ip_address"] is None

    def test_measure_evaluation_time(self) -> None:
        result, elapsed_us = measure_evaluation_time(lambda: 42)
        assert result == 42
        assert isinstance(elapsed_us, int)
        assert elapsed_us >= 0

    @pytest.mark.asyncio
    async def test_evaluation_time_persisted(self, logger) -> None:
        """evaluation_time_us should be written to the DB when provided."""
        await logger.log_decision(
            operation="read",
            entity_name="Task",
            entity_id="t-1",
            decision="allow",
            matched_policy="permit read",
            policy_effect="permit",
            evaluation_time_us=1234,
        )
        await logger._flush()
        logs = logger.query_logs(entity_name="Task")
        assert len(logs) == 1
        assert logs[0]["evaluation_time_us"] == 1234

    @pytest.mark.asyncio
    async def test_log_audit_decision_passes_evaluation_time(self) -> None:
        """_log_audit_decision should forward evaluation_time_us to log_decision."""
        from unittest.mock import AsyncMock

        from dazzle_back.runtime.route_generator import _log_audit_decision

        mock_logger = AsyncMock()
        mock_request = MagicMock()
        mock_request.client.host = "10.0.0.1"
        mock_request.url.path = "/api/tasks/1"
        mock_request.method = "GET"

        await _log_audit_decision(
            mock_logger,
            mock_request,
            operation="read",
            entity_name="Task",
            entity_id="t-1",
            decision="allow",
            matched_policy="permit read",
            policy_effect="permit",
            user=None,
            evaluation_time_us=567,
        )

        mock_logger.log_decision.assert_called_once()
        call_kwargs = mock_logger.log_decision.call_args.kwargs
        assert call_kwargs["evaluation_time_us"] == 567
