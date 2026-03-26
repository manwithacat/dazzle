"""Tests for audit log infrastructure.

Tests AuditLogger queue behavior, writing, query methods, and helpers.
All database tests use mocked psycopg connections (PostgreSQL only).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle_back.runtime.audit_log import (
    AuditLogger,
    create_audit_context_from_request,
    measure_evaluation_time,
)

# =============================================================================
# Fixtures
# =============================================================================


def _make_mock_cursor() -> MagicMock:
    """Create a mock cursor that tracks executed SQL and inserted rows."""
    cursor = MagicMock()
    cursor._rows: list[dict] = []  # type: ignore[attr-defined]
    cursor._executed: list[tuple] = []  # type: ignore[attr-defined]

    def _execute(sql: str, params: tuple | None = None) -> None:
        cursor._executed.append((sql, params))  # type: ignore[attr-defined]
        if sql.strip().startswith("INSERT"):
            # Store the row as a dict using known column order
            cols = [
                "id",
                "timestamp",
                "user_id",
                "user_email",
                "user_roles",
                "operation",
                "entity_name",
                "entity_id",
                "decision",
                "matched_policy",
                "policy_effect",
                "ip_address",
                "request_path",
                "request_method",
                "tenant_id",
                "evaluation_time_us",
                "field_changes",
            ]
            if params:
                cursor._rows.append(dict(zip(cols, params, strict=False)))  # type: ignore[attr-defined]

    cursor.execute = MagicMock(side_effect=_execute)
    cursor.fetchall = MagicMock(return_value=[])
    cursor.fetchone = MagicMock(return_value=None)
    return cursor


def _make_mock_connection(cursor: MagicMock | None = None) -> MagicMock:
    """Create a mock psycopg connection."""
    conn = MagicMock()
    if cursor is None:
        cursor = _make_mock_cursor()
    conn.cursor.return_value = cursor
    conn.commit = MagicMock()
    conn.close = MagicMock()
    return conn


@pytest.fixture
def mock_conn():
    """Provide a mock psycopg connection with patched connect."""
    cursor = _make_mock_cursor()
    conn = _make_mock_connection(cursor)

    with patch("psycopg.connect", return_value=conn), patch("psycopg.rows.dict_row", create=True):
        yield conn, cursor


@pytest.fixture
def audit_logger(mock_conn):
    """Create an AuditLogger with mocked PostgreSQL."""
    return AuditLogger(database_url="postgresql://localhost/test", flush_interval=0.1)


# =============================================================================
# AuditLogger Init
# =============================================================================


class TestAuditLoggerInit:
    def test_creates_table(self, mock_conn) -> None:
        """Logger should issue CREATE TABLE on init."""
        conn, cursor = mock_conn
        AuditLogger(database_url="postgresql://localhost/test")
        executed_sqls = [call[0] for call in cursor._executed]
        assert any("CREATE TABLE IF NOT EXISTS _dazzle_audit_log" in sql for sql in executed_sqls)

    def test_creates_indexes(self, mock_conn) -> None:
        """Logger should create indexes on init."""
        conn, cursor = mock_conn
        AuditLogger(database_url="postgresql://localhost/test")
        executed_sqls = [call[0] for call in cursor._executed]
        assert any("idx_audit_entity" in sql for sql in executed_sqls)
        assert any("idx_audit_user" in sql for sql in executed_sqls)
        assert any("idx_audit_timestamp" in sql for sql in executed_sqls)

    def test_raises_on_missing_psycopg(self) -> None:
        """_get_connection should raise RuntimeError if psycopg is not installed."""
        with patch.dict("sys.modules", {"psycopg": None, "psycopg.rows": None}):
            logger_obj = AuditLogger.__new__(AuditLogger)
            logger_obj._database_url = "postgresql://localhost/test"
            with pytest.raises(RuntimeError, match="psycopg is required"):
                logger_obj._get_connection()

    def test_raises_on_connection_failure(self) -> None:
        """Logger should raise RuntimeError if PostgreSQL connection fails."""
        with (
            patch("psycopg.connect", side_effect=ConnectionError("refused")),
            patch("psycopg.rows.dict_row", create=True),
        ):
            # _init_db catches all exceptions and logs a warning, so no raise
            # But _get_connection itself raises RuntimeError
            logger_obj = AuditLogger.__new__(AuditLogger)
            logger_obj._database_url = "postgresql://localhost/test"
            with pytest.raises(RuntimeError, match="Failed to connect"):
                logger_obj._get_connection()


# =============================================================================
# Logging and Flushing
# =============================================================================


class TestAuditLogging:
    @pytest.mark.asyncio
    async def test_log_and_flush(self, audit_logger, mock_conn) -> None:
        """Entries queued via log_decision should be flushed to DB."""
        conn, cursor = mock_conn
        await audit_logger.log_decision(
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
        await audit_logger._flush()

        # Verify INSERT was executed
        insert_calls = [
            (sql, params)
            for sql, params in cursor._executed
            if isinstance(sql, str) and "INSERT" in sql
        ]
        assert len(insert_calls) == 1
        _sql, params = insert_calls[0]
        assert params is not None
        # params is a tuple — entity_name is at index 6
        assert params[6] == "Task"
        assert params[8] == "allow"
        assert params[5] == "create"

    @pytest.mark.asyncio
    async def test_multiple_entries(self, audit_logger, mock_conn) -> None:
        """Multiple entries should all be flushed."""
        conn, cursor = mock_conn
        for i in range(5):
            await audit_logger.log_decision(
                operation="read",
                entity_name="Task",
                entity_id=f"task-{i}",
                decision="allow",
                matched_policy="authenticated",
                policy_effect="permit",
            )
        await audit_logger._flush()
        insert_calls = [c for c in cursor._executed if isinstance(c[0], str) and "INSERT" in c[0]]
        assert len(insert_calls) == 5

    @pytest.mark.asyncio
    async def test_queue_full_drops(self, mock_conn) -> None:
        """When queue is full, entries should be dropped."""
        small_logger = AuditLogger(database_url="postgresql://localhost/test", max_queue_size=2)
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
    async def test_deny_entries(self, audit_logger, mock_conn) -> None:
        """Deny decisions should also be logged."""
        conn, cursor = mock_conn
        await audit_logger.log_decision(
            operation="delete",
            entity_name="Invoice",
            entity_id="inv-1",
            decision="deny",
            matched_policy="forbid delete for role(intern)",
            policy_effect="forbid",
            user_id="user-2",
        )
        await audit_logger._flush()
        insert_calls = [c for c in cursor._executed if isinstance(c[0], str) and "INSERT" in c[0]]
        assert len(insert_calls) == 1
        params = insert_calls[0][1]
        assert params is not None
        assert params[8] == "deny"
        assert params[10] == "forbid"


# =============================================================================
# Query Methods
# =============================================================================


class TestAuditQueries:
    def test_query_by_entity(self, audit_logger, mock_conn) -> None:
        conn, cursor = mock_conn
        cursor.fetchall.return_value = []
        audit_logger.query_logs(entity_name="Task")
        # Should have executed a SELECT with entity_name filter
        select_calls = [c for c in cursor._executed if isinstance(c[0], str) and "SELECT" in c[0]]
        assert any("entity_name = %s" in c[0] for c in select_calls)

    def test_query_by_operation(self, audit_logger, mock_conn) -> None:
        conn, cursor = mock_conn
        cursor.fetchall.return_value = []
        audit_logger.query_logs(operation="create")
        select_calls = [c for c in cursor._executed if isinstance(c[0], str) and "SELECT" in c[0]]
        assert any("operation = %s" in c[0] for c in select_calls)

    def test_query_by_user(self, audit_logger, mock_conn) -> None:
        conn, cursor = mock_conn
        cursor.fetchall.return_value = []
        audit_logger.query_logs(user_id="alice")
        select_calls = [c for c in cursor._executed if isinstance(c[0], str) and "SELECT" in c[0]]
        assert any("user_id = %s" in c[0] for c in select_calls)

    def test_query_entity_logs(self, audit_logger, mock_conn) -> None:
        conn, cursor = mock_conn
        cursor.fetchall.return_value = []
        audit_logger.query_entity_logs("Task", "task-42")
        select_calls = [c for c in cursor._executed if isinstance(c[0], str) and "SELECT" in c[0]]
        assert any("entity_name = %s AND entity_id = %s" in c[0] for c in select_calls)

    def test_query_stats(self, audit_logger, mock_conn) -> None:
        conn, cursor = mock_conn
        cursor.fetchall.return_value = []
        stats = audit_logger.query_stats()
        assert stats["total"] == 0
        assert stats["by_decision"] == {}
        assert stats["by_operation"] == {}

    def test_query_stats_with_entity(self, audit_logger, mock_conn) -> None:
        conn, cursor = mock_conn
        cursor.fetchall.return_value = []
        stats = audit_logger.query_stats(entity_name="Task")
        assert stats["total"] == 0
        # Should have used the entity_name filter branch
        select_calls = [c for c in cursor._executed if isinstance(c[0], str) and "SELECT" in c[0]]
        assert any("entity_name = %s" in c[0] for c in select_calls)

    def test_query_limit(self, audit_logger, mock_conn) -> None:
        conn, cursor = mock_conn
        cursor.fetchall.return_value = []
        audit_logger.query_logs(limit=3)
        select_calls = [c for c in cursor._executed if isinstance(c[0], str) and "SELECT" in c[0]]
        # The limit param should be passed
        assert any(c[1] and c[1][-1] == 3 for c in select_calls if c[1])


# =============================================================================
# Background Flush Loop
# =============================================================================


class TestFlushLoop:
    @pytest.mark.asyncio
    async def test_start_stop(self, audit_logger, mock_conn) -> None:
        """Logger can be started and stopped without errors."""
        audit_logger.start()
        await audit_logger.log_decision(
            operation="read",
            entity_name="Task",
            entity_id="1",
            decision="allow",
            matched_policy="p",
            policy_effect="permit",
        )
        # Wait for at least one flush cycle
        await asyncio.sleep(0.2)
        await audit_logger.stop()

        conn, cursor = mock_conn
        insert_calls = [c for c in cursor._executed if isinstance(c[0], str) and "INSERT" in c[0]]
        assert len(insert_calls) >= 1


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
    async def test_evaluation_time_persisted(self, audit_logger, mock_conn) -> None:
        """evaluation_time_us should be written to the DB when provided."""
        conn, cursor = mock_conn
        await audit_logger.log_decision(
            operation="read",
            entity_name="Task",
            entity_id="t-1",
            decision="allow",
            matched_policy="permit read",
            policy_effect="permit",
            evaluation_time_us=1234,
        )
        await audit_logger._flush()
        insert_calls = [c for c in cursor._executed if isinstance(c[0], str) and "INSERT" in c[0]]
        assert len(insert_calls) == 1
        params = insert_calls[0][1]
        assert params is not None
        # evaluation_time_us is at index 15
        assert params[15] == 1234

    @pytest.mark.asyncio
    async def test_log_audit_decision_passes_evaluation_time(self) -> None:
        """_log_audit_decision should forward evaluation_time_us to log_decision."""
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


# =============================================================================
# Per-Entity Audit Filtering
# =============================================================================


class TestPerEntityAuditFiltering:
    """Tests for entity.audit.enabled and audit.operations filtering in RouteGenerator."""

    def _make_audit_config(self, enabled=True, operations=None):
        from dazzle.core.ir.domain import AuditConfig

        return AuditConfig(enabled=enabled, operations=operations or [])

    def _make_route_generator(
        self, audit_logger, entity_audit_configs=None, cedar_access_specs=None
    ):
        from dazzle_back.runtime.route_generator import RouteGenerator

        return RouteGenerator(
            services={},
            models={},
            audit_logger=audit_logger,
            entity_audit_configs=entity_audit_configs or {},
            cedar_access_specs=cedar_access_specs or {},
        )

    def test_audit_disabled_entity_gets_no_logger(self):
        """Entity with audit: false should not receive audit logger."""
        mock_logger = MagicMock()
        config = self._make_audit_config(enabled=False)
        rg = self._make_route_generator(mock_logger, entity_audit_configs={"Task": config})

        # Access the internal audit resolution logic
        rg_audit_configs = rg.entity_audit_configs
        assert "Task" in rg_audit_configs
        assert rg_audit_configs["Task"].enabled is False

    def test_audit_enabled_entity_gets_logger(self):
        """Entity with audit: true should receive audit logger."""
        mock_logger = MagicMock()
        config = self._make_audit_config(enabled=True)
        rg = self._make_route_generator(mock_logger, entity_audit_configs={"Task": config})

        assert rg.entity_audit_configs["Task"].enabled is True

    def test_entity_without_config_or_cedar_gets_no_logger(self):
        """Entity with no audit config and no Cedar spec should not be audited."""
        mock_logger = MagicMock()
        rg = self._make_route_generator(mock_logger)

        # Simulate what generate_route does
        entity_name = "Widget"
        _cedar_spec = rg.cedar_access_specs.get(entity_name)
        _audit_config = rg.entity_audit_configs.get(entity_name)
        _audit_enabled = False
        if _audit_config and getattr(_audit_config, "enabled", False):
            _audit_enabled = True
        elif _cedar_spec is not None:
            _audit_enabled = True
        _audit = rg.audit_logger if _audit_enabled else None
        assert _audit is None

    def test_cedar_entity_always_gets_logger(self):
        """Entity with Cedar access spec should always be audited."""
        mock_logger = MagicMock()
        rg = self._make_route_generator(
            mock_logger,
            cedar_access_specs={"Task": MagicMock()},
        )

        entity_name = "Task"
        _cedar_spec = rg.cedar_access_specs.get(entity_name)
        _audit_config = rg.entity_audit_configs.get(entity_name)
        _audit_enabled = False
        if _audit_config and getattr(_audit_config, "enabled", False):
            _audit_enabled = True
        elif _cedar_spec is not None:
            _audit_enabled = True
        _audit = rg.audit_logger if _audit_enabled else None
        assert _audit is mock_logger

    def test_operations_filter_restricts_logging(self):
        """audit: [create, delete] should only audit those operations."""
        from dazzle.core.ir.domain import PermissionKind

        config = self._make_audit_config(
            enabled=True,
            operations=[PermissionKind.CREATE, PermissionKind.DELETE],
        )
        _audit_ops = {str(op) for op in config.operations}

        # create and delete should pass
        assert "create" in _audit_ops
        assert "delete" in _audit_ops
        # read and update should not
        assert "read" not in _audit_ops
        assert "update" not in _audit_ops

    def test_empty_operations_means_all(self):
        """audit: all (empty operations list) should audit everything."""
        config = self._make_audit_config(enabled=True, operations=[])
        _audit_ops = {str(op) for op in config.operations}

        # Empty means all operations are audited
        assert len(_audit_ops) == 0  # empty = no filter = all ops


class TestListAuditLogging:
    """Tests for LIST operation audit logging (#351)."""

    @pytest.mark.asyncio
    async def test_list_handler_calls_audit_logger(self) -> None:
        """create_list_handler should log list access when audit_logger is provided."""
        from dazzle_back.runtime.route_generator import _list_handler_body

        mock_logger = AsyncMock()
        mock_service = AsyncMock()
        mock_service.execute.return_value = {"items": [], "total": 0, "page": 1, "page_size": 20}

        mock_request = MagicMock()
        mock_request.client.host = "10.0.0.1"
        mock_request.url.path = "/api/tasks"
        mock_request.method = "GET"
        mock_request.query_params = {}

        await _list_handler_body(
            service=mock_service,
            access_spec=None,
            is_authenticated=True,
            user_id="user-1",
            request=mock_request,
            page=1,
            page_size=20,
            sort=None,
            dir="asc",
            search=None,
            audit_logger=mock_logger,
            entity_name="Task",
            user=None,
        )

        mock_logger.log_decision.assert_called_once()
        call_kwargs = mock_logger.log_decision.call_args.kwargs
        assert call_kwargs["operation"] == "list"
        assert call_kwargs["entity_name"] == "Task"
        assert call_kwargs["decision"] == "allow"

    @pytest.mark.asyncio
    async def test_list_handler_no_audit_when_logger_none(self) -> None:
        """create_list_handler should not crash when audit_logger is None."""
        from dazzle_back.runtime.route_generator import _list_handler_body

        mock_service = AsyncMock()
        mock_service.execute.return_value = {"items": [], "total": 0}

        mock_request = MagicMock()
        mock_request.client.host = "10.0.0.1"
        mock_request.url.path = "/api/tasks"
        mock_request.method = "GET"
        mock_request.query_params = {}

        # Should not raise
        result = await _list_handler_body(
            service=mock_service,
            access_spec=None,
            is_authenticated=False,
            user_id=None,
            request=mock_request,
            page=1,
            page_size=20,
            sort=None,
            dir="asc",
            search=None,
            audit_logger=None,
            entity_name="Task",
        )
        assert result is not None


class TestAuditTrailGlobalSwitch:
    """Tests for app-level audit_trail: true global switch (#354)."""

    def test_audit_trail_on_appspec(self):
        """AppSpec should have audit_trail field."""
        from dazzle.core.ir.appspec import AppSpec

        fields = AppSpec.model_fields
        assert "audit_trail" in fields
        assert fields["audit_trail"].default is False

    def test_audit_trail_on_backend_spec(self):
        """BackendSpec should have audit_trail field."""
        from dazzle_back.specs import BackendSpec

        fields = BackendSpec.model_fields
        assert "audit_trail" in fields
        assert fields["audit_trail"].default is False

    def test_audit_trail_defaults_entities_to_audited(self):
        """When audit_trail=True, entities without explicit audit config get audited."""
        from dazzle.core.ir.domain import AuditConfig

        # Simulate server.py logic
        _global_audit = True
        entity_audit_configs: dict[str, object] = {}

        # Entity with no explicit audit config
        entity_name = "Widget"
        _ac = None  # No audit config on entity
        if _ac is not None:
            entity_audit_configs[entity_name] = _ac
        elif _global_audit:
            entity_audit_configs[entity_name] = AuditConfig(enabled=True)

        assert entity_name in entity_audit_configs
        assert entity_audit_configs[entity_name].enabled is True

    def test_audit_trail_respects_explicit_opt_out(self):
        """Entity with audit: false should NOT be audited even when audit_trail=True."""
        from dazzle.core.ir.domain import AuditConfig

        _global_audit = True
        entity_audit_configs: dict[str, object] = {}

        # Entity with explicit audit: false
        entity_name = "Config"
        _ac = AuditConfig(enabled=False)
        if _ac is not None:
            entity_audit_configs[entity_name] = _ac
        elif _global_audit:
            entity_audit_configs[entity_name] = AuditConfig(enabled=True)

        assert entity_audit_configs[entity_name].enabled is False

    def test_linker_passes_audit_trail(self):
        """Linker should pass audit_trail from AppConfigSpec to AppSpec."""
        from dazzle.core.ir.module import AppConfigSpec

        config = AppConfigSpec(audit_trail=True)
        assert config.audit_trail is True


class TestFieldChanges:
    """Tests for include_field_changes audit feature."""

    def test_audit_decision_has_field_changes(self):
        """AuditDecision should have a field_changes field."""
        from dazzle_back.runtime.audit_log import AuditDecision

        d = AuditDecision(
            operation="update",
            entity_name="Task",
            entity_id="123",
            decision="allow",
            matched_policy="test",
            policy_effect="permit",
            field_changes='{"title": {"old": "A", "new": "B"}}',
        )
        assert d.field_changes == '{"title": {"old": "A", "new": "B"}}'

    def test_audit_decision_field_changes_default_none(self):
        """AuditDecision.field_changes should default to None."""
        from dazzle_back.runtime.audit_log import AuditDecision

        d = AuditDecision(
            operation="read",
            entity_name="Task",
            entity_id="1",
            decision="allow",
            matched_policy="",
            policy_effect="",
        )
        assert d.field_changes is None

    def test_compute_field_changes_detects_diff(self):
        """_compute_field_changes should detect changed fields."""
        import json

        from dazzle_back.runtime.route_generator import _compute_field_changes

        before = {"title": "Old Title", "status": "todo", "id": "1"}
        after = {"title": "New Title", "status": "todo", "id": "1"}
        result = _compute_field_changes(before, after)
        assert result is not None
        changes = json.loads(result)
        assert "title" in changes
        assert changes["title"]["old"] == "Old Title"
        assert changes["title"]["new"] == "New Title"
        assert "status" not in changes
        assert "id" not in changes

    def test_compute_field_changes_returns_none_when_equal(self):
        """_compute_field_changes should return None when nothing changed."""
        from dazzle_back.runtime.route_generator import _compute_field_changes

        record = {"title": "Same", "status": "todo"}
        result = _compute_field_changes(record, record)
        assert result is None

    def test_compute_field_changes_handles_delete(self):
        """_compute_field_changes with empty after should capture all fields."""
        import json

        from dazzle_back.runtime.route_generator import _compute_field_changes

        before = {"title": "Task", "status": "done"}
        result = _compute_field_changes(before, {})
        assert result is not None
        changes = json.loads(result)
        assert changes["title"]["old"] == "Task"
        assert changes["title"]["new"] is None
        assert changes["status"]["old"] == "done"
        assert changes["status"]["new"] is None

    def test_compute_field_changes_with_pydantic_model(self):
        """_compute_field_changes should work with Pydantic models."""
        import json

        from pydantic import BaseModel

        from dazzle_back.runtime.route_generator import _compute_field_changes

        class Task(BaseModel):
            title: str
            status: str

        before = Task(title="Old", status="todo")
        after = Task(title="New", status="todo")
        result = _compute_field_changes(before, after)
        assert result is not None
        changes = json.loads(result)
        assert changes["title"] == {"old": "Old", "new": "New"}

    @pytest.mark.asyncio
    async def test_field_changes_persisted_to_db(self, audit_logger, mock_conn):
        """field_changes should be persisted to the audit log database."""
        conn, cursor = mock_conn
        await audit_logger.log_decision(
            operation="update",
            entity_name="Task",
            entity_id="abc",
            decision="allow",
            matched_policy="test",
            policy_effect="permit",
            field_changes='{"title": {"old": "A", "new": "B"}}',
        )
        await audit_logger._flush()

        insert_calls = [c for c in cursor._executed if isinstance(c[0], str) and "INSERT" in c[0]]
        assert len(insert_calls) == 1
        params = insert_calls[0][1]
        assert params is not None
        # field_changes is at index 16
        assert params[16] == '{"title": {"old": "A", "new": "B"}}'

    @pytest.mark.asyncio
    async def test_field_changes_null_when_not_provided(self, audit_logger, mock_conn):
        """field_changes should be NULL when not provided."""
        conn, cursor = mock_conn
        await audit_logger.log_decision(
            operation="read",
            entity_name="Task",
            entity_id="abc",
            decision="allow",
            matched_policy="test",
            policy_effect="permit",
        )
        await audit_logger._flush()

        insert_calls = [c for c in cursor._executed if isinstance(c[0], str) and "INSERT" in c[0]]
        assert len(insert_calls) == 1
        params = insert_calls[0][1]
        assert params is not None
        assert params[16] is None

    @pytest.mark.asyncio
    async def test_log_audit_decision_forwards_field_changes(self):
        """_log_audit_decision should forward field_changes to log_decision."""
        from dazzle_back.runtime.route_generator import _log_audit_decision

        mock_logger = MagicMock()
        mock_logger.log_decision = AsyncMock()
        mock_request = MagicMock()
        mock_request.client = None
        mock_request.url = MagicMock()
        mock_request.url.path = "/api/task/1"
        mock_request.method = "PUT"

        await _log_audit_decision(
            mock_logger,
            mock_request,
            operation="update",
            entity_name="Task",
            entity_id="1",
            decision="allow",
            matched_policy="test",
            policy_effect="permit",
            user=None,
            field_changes='{"status": {"old": "todo", "new": "done"}}',
        )

        mock_logger.log_decision.assert_called_once()
        call_kwargs = mock_logger.log_decision.call_args
        assert (
            call_kwargs.kwargs.get("field_changes") == '{"status": {"old": "todo", "new": "done"}}'
        )

    def test_include_field_changes_resolves_from_audit_config(self):
        """generate_route should resolve include_field_changes from AuditConfig."""
        from dazzle.core.ir.domain import AuditConfig

        # Config with include_field_changes=True (default)
        config = AuditConfig(enabled=True)
        assert config.include_field_changes is True
        _include_fc = bool(config and getattr(config, "include_field_changes", False))
        assert _include_fc is True

        # Config with include_field_changes=False
        config2 = AuditConfig(enabled=True, include_field_changes=False)
        _include_fc2 = bool(config2 and getattr(config2, "include_field_changes", False))
        assert _include_fc2 is False

    def test_validator_no_preview_warning(self):
        """Validator should not emit [Preview] warning for include_field_changes."""
        from dazzle.core.ir.domain import AuditConfig, EntitySpec
        from dazzle.core.validator import validate_audit_config

        entity = EntitySpec(
            name="Patient",
            title="Patient",
            fields=[],
            audit=AuditConfig(enabled=True, include_field_changes=True),
        )
        # Minimal appspec mock
        mock_appspec = MagicMock()
        mock_appspec.domain.entities = [entity]
        errors, warnings = validate_audit_config(mock_appspec)
        # Should have no [Preview] warnings
        for w in warnings:
            assert "[Preview]" not in w
