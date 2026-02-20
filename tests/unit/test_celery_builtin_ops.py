"""Tests for built-in entity CRUD operations in celery_tasks.py (#345)."""

from __future__ import annotations

import sys
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Pre-mock celery before importing celery_tasks (celery not in test deps)
_celery_mock = MagicMock()
sys.modules.setdefault("celery", _celery_mock)
sys.modules.setdefault("celery.exceptions", MagicMock())
sys.modules.setdefault("celery.schedules", MagicMock())

from dazzle.core.process.adapter import ProcessRun, ProcessStatus  # noqa: E402
from dazzle.core.process.celery_tasks import (  # noqa: E402
    _BUILTIN_OPS,
    _builtin_create,
    _builtin_delete,
    _builtin_read,
    _builtin_transition,
    _builtin_update,
    _execute_builtin_entity_op,
    _execute_service_step,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(
    inputs: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> ProcessRun:
    return ProcessRun(
        run_id="run-001",
        process_name="test_proc",
        status=ProcessStatus.RUNNING,
        inputs=inputs or {},
        context=context or {},
    )


def _mock_cursor(
    rows: list[tuple[Any, ...]] | None = None,
    description: list[Any] | None = None,
    rowcount: int = 1,
) -> MagicMock:
    """Create a mock cursor with fetchone/fetchall/description support."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    if rows is not None:
        cur.fetchone.return_value = rows[0] if rows else None
        cur.fetchall.return_value = rows
    else:
        cur.fetchone.return_value = None
        cur.fetchall.return_value = []
    if description:
        cur.description = description
    cur.rowcount = rowcount
    return cur


def _mock_conn(cursor: Any | None = None) -> MagicMock:
    conn = MagicMock()
    conn.cursor.return_value = cursor or _mock_cursor()
    return conn


class _Desc:
    """Minimal cursor description item."""

    def __init__(self, name: str):
        self.name = name


# ---------------------------------------------------------------------------
# _BUILTIN_OPS detection
# ---------------------------------------------------------------------------


class TestBuiltinOpsDetection:
    def test_builtin_ops_contains_crud(self):
        assert _BUILTIN_OPS == {"create", "read", "update", "delete", "transition"}

    @patch("dazzle.core.process.celery_tasks._execute_builtin_entity_op")
    def test_service_step_routes_to_builtin(self, mock_builtin: MagicMock):
        mock_builtin.return_value = {"output": {"id": "123"}}
        run = _make_run()
        result = _execute_service_step(run, {"service": "Task.create"})
        mock_builtin.assert_called_once_with("Task", "create", run)
        assert result == {"output": {"id": "123"}}

    @patch("dazzle.core.process.celery_tasks._execute_builtin_entity_op")
    def test_service_step_routes_transition(self, mock_builtin: MagicMock):
        mock_builtin.return_value = {"output": {"transitioned": True}}
        run = _make_run()
        _execute_service_step(run, {"service": "Order.transition"})
        mock_builtin.assert_called_once_with("Order", "transition", run)

    def test_service_step_nonbuiltin_falls_through(self):
        """Non-builtin methods fall through to importlib (which returns {} on ImportError)."""
        run = _make_run()
        result = _execute_service_step(run, {"service": "Task.check_duplicate"})
        assert result == {}


# ---------------------------------------------------------------------------
# _builtin_create
# ---------------------------------------------------------------------------


class TestBuiltinCreate:
    def test_creates_row_with_generated_id(self):
        cur = _mock_cursor(rows=[(uuid.UUID("aaaaaaaa-1111-2222-3333-444444444444"),)])
        conn = _mock_conn(cur)

        result = _builtin_create(
            conn,
            table_name="Task",
            valid_fields={"id", "title", "status", "priority"},
            merged={"title": "Review Q1", "status": "open", "ignored_key": "skip"},
            internal_keys={"entity_id", "entity_name", "event_type"},
            uuid_mod=uuid,
        )

        assert result["output"]["title"] == "Review Q1"
        assert result["output"]["status"] == "open"
        assert "id" in result["output"]
        # Verify SQL was executed
        cur.execute.assert_called_once()
        sql = cur.execute.call_args[0][0]
        assert "INSERT INTO" in sql
        assert "Task" in sql

    def test_uses_provided_id(self):
        cur = _mock_cursor(rows=[("my-id",)])
        conn = _mock_conn(cur)

        result = _builtin_create(
            conn,
            table_name="Task",
            valid_fields={"id", "title"},
            merged={"id": "my-id", "title": "Foo"},
            internal_keys=set(),
            uuid_mod=uuid,
        )

        assert result["output"]["id"] == "my-id"

    def test_filters_internal_keys(self):
        cur = _mock_cursor(rows=[("new-id",)])
        conn = _mock_conn(cur)

        _builtin_create(
            conn,
            table_name="Task",
            valid_fields={"id", "title", "entity_name"},
            merged={"title": "Foo", "entity_name": "BookkeepingPeriod", "event_type": "created"},
            internal_keys={"entity_name", "event_type"},
            uuid_mod=uuid,
        )

        sql = cur.execute.call_args[0][0]
        assert "entity_name" not in sql
        assert "event_type" not in sql


# ---------------------------------------------------------------------------
# _builtin_read
# ---------------------------------------------------------------------------


class TestBuiltinRead:
    def test_reads_by_entity_id(self):
        desc = [_Desc("id"), _Desc("title"), _Desc("status")]
        row = (uuid.UUID("11111111-2222-3333-4444-555555555555"), "Task A", "open")
        cur = _mock_cursor(rows=[row], description=desc)
        conn = _mock_conn(cur)

        result = _builtin_read(conn, "Task", {"entity_id": "11111111-2222-3333-4444-555555555555"})

        assert result["output"]["title"] == "Task A"
        assert result["output"]["status"] == "open"

    def test_read_not_found(self):
        cur = _mock_cursor(rows=[])
        cur.fetchone.return_value = None
        conn = _mock_conn(cur)

        result = _builtin_read(conn, "Task", {"entity_id": "missing"})
        assert result["output"] is None

    def test_read_no_id_returns_empty(self):
        conn = _mock_conn()
        result = _builtin_read(conn, "Task", {"some_field": "val"})
        assert result == {}


# ---------------------------------------------------------------------------
# _builtin_update
# ---------------------------------------------------------------------------


class TestBuiltinUpdate:
    def test_updates_valid_fields(self):
        cur = _mock_cursor(rowcount=1)
        conn = _mock_conn(cur)

        result = _builtin_update(
            conn,
            table_name="Task",
            valid_fields={"id", "title", "priority"},
            merged={"entity_id": "abc-123", "title": "Updated", "priority": "high"},
            internal_keys={"entity_id", "entity_name", "event_type"},
        )

        assert result["output"]["updated"] is True
        assert result["output"]["title"] == "Updated"

    def test_update_no_valid_fields(self):
        conn = _mock_conn()

        result = _builtin_update(
            conn,
            table_name="Task",
            valid_fields={"id", "title"},
            merged={"entity_id": "abc-123", "entity_name": "Task"},
            internal_keys={"entity_id", "entity_name"},
        )

        assert result["output"]["updated"] is False

    def test_update_no_id_returns_empty(self):
        conn = _mock_conn()
        result = _builtin_update(conn, "Task", {"title"}, {"title": "Foo"}, set())
        assert result == {}


# ---------------------------------------------------------------------------
# _builtin_delete
# ---------------------------------------------------------------------------


class TestBuiltinDelete:
    def test_deletes_row(self):
        cur = _mock_cursor(rowcount=1)
        conn = _mock_conn(cur)

        result = _builtin_delete(conn, "Task", {"entity_id": "abc-123"})

        assert result["output"]["deleted"] is True
        sql = cur.execute.call_args[0][0]
        assert "DELETE" in sql

    def test_delete_not_found(self):
        cur = _mock_cursor(rowcount=0)
        conn = _mock_conn(cur)

        result = _builtin_delete(conn, "Task", {"entity_id": "missing"})
        assert result["output"]["deleted"] is False


# ---------------------------------------------------------------------------
# _builtin_transition
# ---------------------------------------------------------------------------


class TestBuiltinTransition:
    def test_transitions_status(self):
        cur = _mock_cursor(rowcount=1)
        conn = _mock_conn(cur)

        result = _builtin_transition(
            conn,
            table_name="Order",
            meta={"status_field": "status", "fields": ["id", "status"]},
            merged={"entity_id": "order-1", "new_status": "shipped"},
        )

        assert result["output"]["transitioned"] is True
        assert result["output"]["status"] == "shipped"
        sql = cur.execute.call_args[0][0]
        assert "status" in sql
        assert "UPDATE" in sql

    def test_transition_uses_status_field_value(self):
        """Falls back to reading the status field name from merged data."""
        cur = _mock_cursor(rowcount=1)
        conn = _mock_conn(cur)

        result = _builtin_transition(
            conn,
            table_name="Ticket",
            meta={"status_field": "state", "fields": ["id", "state"]},
            merged={"entity_id": "t-1", "state": "resolved"},
        )

        assert result["output"]["transitioned"] is True
        assert result["output"]["state"] == "resolved"

    def test_transition_no_status_field_returns_empty(self):
        conn = _mock_conn()
        result = _builtin_transition(
            conn, "Task", {"status_field": None, "fields": ["id"]}, {"entity_id": "t-1"}
        )
        assert result == {}


# ---------------------------------------------------------------------------
# _execute_builtin_entity_op (integration)
# ---------------------------------------------------------------------------


class TestExecuteBuiltinEntityOp:
    @patch("dazzle.core.process.celery_tasks._get_db_connection")
    @patch("dazzle.core.process.celery_tasks._get_store")
    def test_create_integration(self, mock_store_fn: MagicMock, mock_conn_fn: MagicMock):
        store = MagicMock()
        store.get_entity_meta.return_value = {
            "table_name": "Task",
            "fields": ["id", "title", "status"],
            "status_field": "status",
        }
        mock_store_fn.return_value = store

        cur = _mock_cursor(rows=[("new-uuid",)])
        conn = _mock_conn(cur)
        mock_conn_fn.return_value = conn

        run = _make_run(
            inputs={"entity_id": "bp-1", "entity_name": "BookkeepingPeriod", "title": "Q1 Review"},
            context={"status": "open"},
        )

        result = _execute_builtin_entity_op("Task", "create", run)

        assert result["output"]["title"] == "Q1 Review"
        assert result["output"]["status"] == "open"
        conn.close.assert_called_once()

    @patch("dazzle.core.process.celery_tasks._get_store")
    def test_missing_entity_meta_returns_empty(self, mock_store_fn: MagicMock):
        store = MagicMock()
        store.get_entity_meta.return_value = None
        mock_store_fn.return_value = store

        run = _make_run()
        result = _execute_builtin_entity_op("UnknownEntity", "create", run)
        assert result == {}


# ---------------------------------------------------------------------------
# ProcessManager entity metadata registration
# ---------------------------------------------------------------------------


class TestProcessManagerEntityMeta:
    @pytest.mark.asyncio
    async def test_initialize_stores_entity_meta(self):
        """ProcessManager.initialize() stores entity metadata via adapter."""
        from unittest.mock import AsyncMock

        from dazzle_back.runtime.process_manager import ProcessManager

        adapter = AsyncMock()
        adapter.register_entity_meta = AsyncMock()

        # Minimal AppSpec mock with one entity
        field = MagicMock()
        field.name = "id"
        entity = MagicMock()
        entity.name = "Task"
        entity.fields = [field]
        entity.state_machine = None

        domain = MagicMock()
        domain.entities = [entity]

        app_spec = MagicMock()
        app_spec.processes = []
        app_spec.schedules = []
        app_spec.domain = domain

        pm = ProcessManager(adapter=adapter, app_spec=app_spec)
        await pm.initialize()

        adapter.register_entity_meta.assert_called_once_with(
            "Task",
            {"table_name": "Task", "fields": ["id"], "status_field": None},
        )

    @pytest.mark.asyncio
    async def test_initialize_stores_status_field(self):
        """Entity with state machine stores status_field in metadata."""
        from unittest.mock import AsyncMock

        from dazzle_back.runtime.process_manager import ProcessManager

        adapter = AsyncMock()
        adapter.register_entity_meta = AsyncMock()

        field_id = MagicMock()
        field_id.name = "id"
        field_status = MagicMock()
        field_status.name = "status"

        sm = MagicMock()
        sm.status_field = "status"

        entity = MagicMock()
        entity.name = "Order"
        entity.fields = [field_id, field_status]
        entity.state_machine = sm

        domain = MagicMock()
        domain.entities = [entity]

        app_spec = MagicMock()
        app_spec.processes = []
        app_spec.schedules = []
        app_spec.domain = domain

        pm = ProcessManager(adapter=adapter, app_spec=app_spec)
        await pm.initialize()

        adapter.register_entity_meta.assert_called_once_with(
            "Order",
            {"table_name": "Order", "fields": ["id", "status"], "status_field": "status"},
        )
