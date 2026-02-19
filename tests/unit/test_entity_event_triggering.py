"""
Unit tests for entity lifecycle event triggering.

Tests that CRUDService correctly notifies callbacks when entities are
created, updated, or deleted, and that ProcessManager correctly registers
triggers and dispatches entity events.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from dazzle_back.runtime.service_generator import CRUDService


class SampleEntity(BaseModel):
    """Sample entity model for testing."""

    id: UUID
    name: str
    status: str = "active"


class SampleCreateSchema(BaseModel):
    """Sample create schema for testing."""

    name: str
    status: str = "active"


class SampleUpdateSchema(BaseModel):
    """Sample update schema for testing."""

    name: str | None = None
    status: str | None = None


@pytest.fixture
def crud_service() -> CRUDService[SampleEntity, SampleCreateSchema, SampleUpdateSchema]:
    """Create a basic CRUD service for testing."""
    return CRUDService(
        entity_name="SampleEntity",
        model_class=SampleEntity,
        create_schema=SampleCreateSchema,
        update_schema=SampleUpdateSchema,
    )


class TestEntityCreatedCallback:
    """Tests for on_created callbacks."""

    @pytest.mark.asyncio
    async def test_callback_called_on_create(
        self, crud_service: CRUDService[SampleEntity, SampleCreateSchema, SampleUpdateSchema]
    ) -> None:
        """Test that on_created callback is called when entity is created."""
        callback = AsyncMock(return_value=["run-123"])
        crud_service.on_created(callback)

        create_data = SampleCreateSchema(name="Test Item")
        await crud_service.create(create_data)

        callback.assert_called_once()
        call_args = callback.call_args[0]
        assert call_args[0] == "SampleEntity"  # entity_name
        assert call_args[2]["name"] == "Test Item"  # entity_data
        assert call_args[3] is None  # old_data (None for create)

    @pytest.mark.asyncio
    async def test_multiple_callbacks_called(
        self, crud_service: CRUDService[SampleEntity, SampleCreateSchema, SampleUpdateSchema]
    ) -> None:
        """Test that multiple callbacks are all called."""
        callback1 = AsyncMock(return_value=["run-1"])
        callback2 = AsyncMock(return_value=["run-2"])

        crud_service.on_created(callback1)
        crud_service.on_created(callback2)

        create_data = SampleCreateSchema(name="Test Item")
        await crud_service.create(create_data)

        callback1.assert_called_once()
        callback2.assert_called_once()

    @pytest.mark.asyncio
    async def test_callback_receives_entity_id(
        self, crud_service: CRUDService[SampleEntity, SampleCreateSchema, SampleUpdateSchema]
    ) -> None:
        """Test that callback receives the entity ID as a string."""
        callback = AsyncMock(return_value=[])
        crud_service.on_created(callback)

        create_data = SampleCreateSchema(name="Test Item")
        entity = await crud_service.create(create_data)

        call_args = callback.call_args[0]
        entity_id = call_args[1]  # entity_id

        # Verify it's a string representation of the UUID
        assert entity_id == str(entity.id)

    @pytest.mark.asyncio
    async def test_callback_error_does_not_fail_create(
        self, crud_service: CRUDService[SampleEntity, SampleCreateSchema, SampleUpdateSchema]
    ) -> None:
        """Test that callback errors don't fail the create operation."""
        callback = AsyncMock(side_effect=Exception("Callback failed"))
        crud_service.on_created(callback)

        create_data = SampleCreateSchema(name="Test Item")
        entity = await crud_service.create(create_data)

        # Entity should still be created successfully
        assert entity.name == "Test Item"
        callback.assert_called_once()


class TestEntityUpdatedCallback:
    """Tests for on_updated callbacks."""

    @pytest.mark.asyncio
    async def test_callback_called_on_update(
        self, crud_service: CRUDService[SampleEntity, SampleCreateSchema, SampleUpdateSchema]
    ) -> None:
        """Test that on_updated callback is called when entity is updated."""
        # Create entity first
        create_data = SampleCreateSchema(name="Original Name")
        entity = await crud_service.create(create_data)

        # Register callback
        callback = AsyncMock(return_value=["run-456"])
        crud_service.on_updated(callback)

        # Update entity
        update_data = SampleUpdateSchema(name="Updated Name")
        await crud_service.update(entity.id, update_data)

        callback.assert_called_once()
        call_args = callback.call_args[0]
        assert call_args[0] == "SampleEntity"  # entity_name
        assert call_args[2]["name"] == "Updated Name"  # entity_data (new)
        assert call_args[3]["name"] == "Original Name"  # old_data

    @pytest.mark.asyncio
    async def test_callback_receives_old_data(
        self, crud_service: CRUDService[SampleEntity, SampleCreateSchema, SampleUpdateSchema]
    ) -> None:
        """Test that callback receives old data for comparison."""
        # Create entity with initial status
        create_data = SampleCreateSchema(name="Test", status="pending")
        entity = await crud_service.create(create_data)

        # Register callback
        callback = AsyncMock(return_value=[])
        crud_service.on_updated(callback)

        # Update status
        update_data = SampleUpdateSchema(status="active")
        await crud_service.update(entity.id, update_data)

        call_args = callback.call_args[0]
        old_data = call_args[3]
        new_data = call_args[2]

        assert old_data["status"] == "pending"
        assert new_data["status"] == "active"

    @pytest.mark.asyncio
    async def test_callback_not_called_when_entity_not_found(
        self, crud_service: CRUDService[SampleEntity, SampleCreateSchema, SampleUpdateSchema]
    ) -> None:
        """Test that callback is not called when entity doesn't exist."""
        callback = AsyncMock(return_value=[])
        crud_service.on_updated(callback)

        # Try to update non-existent entity
        update_data = SampleUpdateSchema(name="Updated")
        result = await crud_service.update(uuid4(), update_data)

        assert result is None
        callback.assert_not_called()


class TestEntityDeletedCallback:
    """Tests for on_deleted callbacks."""

    @pytest.mark.asyncio
    async def test_callback_called_on_delete(
        self, crud_service: CRUDService[SampleEntity, SampleCreateSchema, SampleUpdateSchema]
    ) -> None:
        """Test that on_deleted callback is called when entity is deleted."""
        # Create entity first
        create_data = SampleCreateSchema(name="To Be Deleted")
        entity = await crud_service.create(create_data)

        # Register callback
        callback = AsyncMock(return_value=["run-789"])
        crud_service.on_deleted(callback)

        # Delete entity
        deleted = await crud_service.delete(entity.id)

        assert deleted is True
        callback.assert_called_once()
        call_args = callback.call_args[0]
        assert call_args[0] == "SampleEntity"  # entity_name
        assert call_args[1] == str(entity.id)  # entity_id
        assert call_args[2]["name"] == "To Be Deleted"  # entity_data

    @pytest.mark.asyncio
    async def test_callback_receives_entity_data(
        self, crud_service: CRUDService[SampleEntity, SampleCreateSchema, SampleUpdateSchema]
    ) -> None:
        """Test that callback receives entity data before deletion."""
        create_data = SampleCreateSchema(name="Test Entity", status="completed")
        entity = await crud_service.create(create_data)

        callback = AsyncMock(return_value=[])
        crud_service.on_deleted(callback)

        await crud_service.delete(entity.id)

        call_args = callback.call_args[0]
        entity_data = call_args[2]

        assert entity_data["name"] == "Test Entity"
        assert entity_data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_callback_not_called_when_entity_not_found(
        self, crud_service: CRUDService[SampleEntity, SampleCreateSchema, SampleUpdateSchema]
    ) -> None:
        """Test that callback is not called when entity doesn't exist."""
        callback = AsyncMock(return_value=[])
        crud_service.on_deleted(callback)

        # Try to delete non-existent entity
        result = await crud_service.delete(uuid4())

        assert result is False
        callback.assert_not_called()


class TestCallbackRegistration:
    """Tests for callback registration."""

    def test_register_sync_callback(
        self, crud_service: CRUDService[SampleEntity, SampleCreateSchema, SampleUpdateSchema]
    ) -> None:
        """Test that sync callbacks can be registered."""

        def sync_callback(
            entity_name: str,
            entity_id: str,
            entity_data: dict[str, Any],
            old_data: dict[str, Any] | None,
        ) -> list[str]:
            return []

        # Should not raise
        crud_service.on_created(sync_callback)
        crud_service.on_updated(sync_callback)
        crud_service.on_deleted(sync_callback)

    @pytest.mark.asyncio
    async def test_sync_callback_executed(
        self, crud_service: CRUDService[SampleEntity, SampleCreateSchema, SampleUpdateSchema]
    ) -> None:
        """Test that sync callbacks are executed correctly."""
        call_count = {"value": 0}

        def sync_callback(
            entity_name: str,
            entity_id: str,
            entity_data: dict[str, Any],
            old_data: dict[str, Any] | None,
        ) -> list[str]:
            call_count["value"] += 1
            return []

        crud_service.on_created(sync_callback)

        create_data = SampleCreateSchema(name="Test")
        await crud_service.create(create_data)

        assert call_count["value"] == 1


class TestProcessManagerIntegration:
    """Tests for ProcessManager integration patterns."""

    @pytest.mark.asyncio
    async def test_callback_returns_process_run_ids(
        self, crud_service: CRUDService[SampleEntity, SampleCreateSchema, SampleUpdateSchema]
    ) -> None:
        """Test that callbacks can return process run IDs."""
        # Simulate ProcessManager.on_entity_created returning run IDs
        callback = AsyncMock(return_value=["run-001", "run-002"])
        crud_service.on_created(callback)

        create_data = SampleCreateSchema(name="Test")
        await crud_service.create(create_data)

        callback.assert_called_once()
        # The return value is captured but not used by CRUDService
        # ProcessManager's on_entity_created returns run IDs

    @pytest.mark.asyncio
    async def test_status_transition_detection(
        self, crud_service: CRUDService[SampleEntity, SampleCreateSchema, SampleUpdateSchema]
    ) -> None:
        """Test that status transitions can be detected from old_data."""
        # Create entity with initial status
        create_data = SampleCreateSchema(name="Task", status="pending")
        entity = await crud_service.create(create_data)

        # Callback that detects status transitions
        transitions_detected: list[tuple[str, str]] = []

        async def detect_transition(
            entity_name: str,
            entity_id: str,
            entity_data: dict[str, Any],
            old_data: dict[str, Any] | None,
        ) -> list[str]:
            if old_data and "status" in entity_data and "status" in old_data:
                old_status = old_data["status"]
                new_status = entity_data["status"]
                if old_status != new_status:
                    transitions_detected.append((old_status, new_status))
            return []

        crud_service.on_updated(detect_transition)

        # Update status from pending to in_progress
        update_data = SampleUpdateSchema(status="in_progress")
        await crud_service.update(entity.id, update_data)

        assert len(transitions_detected) == 1
        assert transitions_detected[0] == ("pending", "in_progress")


# ---------------------------------------------------------------------------
# ProcessManager trigger registration and dispatch tests
# ---------------------------------------------------------------------------


def _make_process_spec(
    name: str,
    trigger_kind: str = "entity_event",
    entity_name: str = "Order",
    event_type: str | None = "created",
    from_status: str | None = None,
    to_status: str | None = None,
) -> Any:
    """Create a minimal ProcessSpec-like object for testing."""
    from dazzle.core.ir.process import (
        ProcessSpec,
        ProcessTriggerKind,
        ProcessTriggerSpec,
    )

    trigger = ProcessTriggerSpec(
        kind=ProcessTriggerKind(trigger_kind),
        entity_name=entity_name,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
    )
    return ProcessSpec(name=name, trigger=trigger, steps=[])


def _make_app_spec_with_processes(
    processes: list[Any],
    entities: list[Any] | None = None,
) -> Any:
    """Create a minimal AppSpec-like object with processes and optional entities."""

    class FakeDomain:
        def __init__(self, ents: list[Any]) -> None:
            self.entities = ents

    class FakeAppSpec:
        def __init__(
            self,
            procs: list[Any],
            domain_obj: Any | None = None,
        ) -> None:
            self.processes = procs
            self.schedules: list[Any] = []
            self.domain = domain_obj

    domain = FakeDomain(entities or []) if entities is not None else None
    return FakeAppSpec(processes, domain)


def _make_entity_with_state_machine(name: str, status_field: str = "status") -> Any:
    """Create a fake entity with a state machine."""

    class FakeStateMachine:
        def __init__(self, sf: str) -> None:
            self.status_field = sf

    class FakeEntity:
        def __init__(self, n: str, sm: Any) -> None:
            self.name = n
            self.state_machine = sm

    return FakeEntity(name, FakeStateMachine(status_field))


class TestProcessManagerTriggerRegistration:
    """Tests that ProcessManager correctly registers and dispatches triggers."""

    @pytest.mark.asyncio
    async def test_entity_event_trigger_registered(self) -> None:
        """Test that entity_event triggers are registered on initialize."""
        from dazzle_back.runtime.process_manager import ProcessManager

        proc = _make_process_spec("auto_task", "entity_event", "Order", "created")
        app_spec = _make_app_spec_with_processes([proc])

        adapter = AsyncMock()
        adapter.register_process = AsyncMock()
        adapter.register_schedule = AsyncMock()

        mgr = ProcessManager(adapter=adapter, app_spec=app_spec)
        await mgr.initialize()

        assert "Order:created" in mgr._entity_event_triggers
        assert mgr._entity_event_triggers["Order:created"] == [proc]

    @pytest.mark.asyncio
    async def test_status_transition_trigger_registered(self) -> None:
        """Test that status transition triggers are registered on initialize."""
        from dazzle_back.runtime.process_manager import ProcessManager

        proc = _make_process_spec(
            "escalation",
            "entity_status_transition",
            "Task",
            event_type=None,
            from_status="pending",
            to_status="overdue",
        )
        app_spec = _make_app_spec_with_processes([proc])

        adapter = AsyncMock()
        adapter.register_process = AsyncMock()
        adapter.register_schedule = AsyncMock()

        mgr = ProcessManager(adapter=adapter, app_spec=app_spec)
        await mgr.initialize()

        assert "Task:pending:overdue" in mgr._status_transition_triggers
        assert mgr._status_transition_triggers["Task:pending:overdue"] == [proc]

    @pytest.mark.asyncio
    async def test_on_entity_created_dispatches(self) -> None:
        """Test that on_entity_created starts matching processes."""
        from dazzle_back.runtime.process_manager import ProcessManager

        proc = _make_process_spec("on_order_created", "entity_event", "Order", "created")
        app_spec = _make_app_spec_with_processes([proc])

        adapter = AsyncMock()
        adapter.register_process = AsyncMock()
        adapter.register_schedule = AsyncMock()
        adapter.start_process = AsyncMock(return_value="run-001")

        mgr = ProcessManager(adapter=adapter, app_spec=app_spec)
        await mgr.initialize()

        run_ids = await mgr.on_entity_created("Order", "order-42", {"total": 100})

        assert run_ids == ["run-001"]
        adapter.start_process.assert_called_once_with(
            "on_order_created",
            {
                "entity_id": "order-42",
                "entity_name": "Order",
                "event_type": "created",
                "total": 100,
            },
        )

    @pytest.mark.asyncio
    async def test_on_entity_created_no_match(self) -> None:
        """Test that no processes start when no triggers match."""
        from dazzle_back.runtime.process_manager import ProcessManager

        proc = _make_process_spec("on_order_created", "entity_event", "Order", "created")
        app_spec = _make_app_spec_with_processes([proc])

        adapter = AsyncMock()
        adapter.register_process = AsyncMock()
        adapter.register_schedule = AsyncMock()

        mgr = ProcessManager(adapter=adapter, app_spec=app_spec)
        await mgr.initialize()

        # Different entity — no match
        run_ids = await mgr.on_entity_created("Customer", "cust-1", {"name": "Acme"})

        assert run_ids == []
        adapter.start_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_entity_updated_detects_status_transition(self) -> None:
        """Test that status transitions are detected and dispatched."""
        from dazzle_back.runtime.process_manager import ProcessManager

        proc = _make_process_spec(
            "on_task_overdue",
            "entity_status_transition",
            "Task",
            event_type=None,
            from_status="pending",
            to_status="overdue",
        )
        app_spec = _make_app_spec_with_processes([proc])

        adapter = AsyncMock()
        adapter.register_process = AsyncMock()
        adapter.register_schedule = AsyncMock()
        adapter.start_process = AsyncMock(return_value="run-transition-1")

        mgr = ProcessManager(adapter=adapter, app_spec=app_spec)
        await mgr.initialize()

        run_ids = await mgr.on_entity_updated(
            "Task",
            "task-99",
            {"status": "overdue", "title": "Review doc"},
            old_data={"status": "pending", "title": "Review doc"},
        )

        assert "run-transition-1" in run_ids
        adapter.start_process.assert_called_once()
        call_kwargs = adapter.start_process.call_args[0]
        assert call_kwargs[0] == "on_task_overdue"

    @pytest.mark.asyncio
    async def test_custom_status_field(self) -> None:
        """Test that custom status_field from state machine is used."""
        from dazzle_back.runtime.process_manager import ProcessManager

        proc = _make_process_spec(
            "on_approval_change",
            "entity_status_transition",
            "Invoice",
            event_type=None,
            from_status="draft",
            to_status="submitted",
        )

        # Entity with custom status field "approval_state"
        entity = _make_entity_with_state_machine("Invoice", "approval_state")
        app_spec = _make_app_spec_with_processes([proc], entities=[entity])

        adapter = AsyncMock()
        adapter.register_process = AsyncMock()
        adapter.register_schedule = AsyncMock()
        adapter.start_process = AsyncMock(return_value="run-custom-1")

        mgr = ProcessManager(adapter=adapter, app_spec=app_spec)
        await mgr.initialize()

        # Use the custom field name — should trigger
        run_ids = await mgr.on_entity_updated(
            "Invoice",
            "inv-1",
            {"approval_state": "submitted", "amount": 500},
            old_data={"approval_state": "draft", "amount": 500},
        )
        assert "run-custom-1" in run_ids

    @pytest.mark.asyncio
    async def test_custom_status_field_ignores_wrong_field(self) -> None:
        """Test that the default 'status' field is ignored when custom field is set."""
        from dazzle_back.runtime.process_manager import ProcessManager

        proc = _make_process_spec(
            "on_approval_change",
            "entity_status_transition",
            "Invoice",
            event_type=None,
            from_status="draft",
            to_status="submitted",
        )

        entity = _make_entity_with_state_machine("Invoice", "approval_state")
        app_spec = _make_app_spec_with_processes([proc], entities=[entity])

        adapter = AsyncMock()
        adapter.register_process = AsyncMock()
        adapter.register_schedule = AsyncMock()

        mgr = ProcessManager(adapter=adapter, app_spec=app_spec)
        await mgr.initialize()

        # Change the "status" field (not approval_state) — should NOT trigger
        run_ids = await mgr.on_entity_updated(
            "Invoice",
            "inv-2",
            {"status": "submitted", "approval_state": "draft"},
            old_data={"status": "draft", "approval_state": "draft"},
        )
        assert run_ids == []
        adapter.start_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_app_spec_no_triggers(self) -> None:
        """Test that ProcessManager without app_spec has no triggers."""
        from dazzle_back.runtime.process_manager import ProcessManager

        adapter = AsyncMock()
        mgr = ProcessManager(adapter=adapter)

        assert mgr._entity_event_triggers == {}
        assert mgr._status_transition_triggers == {}

    @pytest.mark.asyncio
    async def test_adapter_error_logged_not_raised(self) -> None:
        """Test that adapter errors are logged but don't propagate."""
        from dazzle_back.runtime.process_manager import ProcessManager

        proc = _make_process_spec("on_order_created", "entity_event", "Order", "created")
        app_spec = _make_app_spec_with_processes([proc])

        adapter = AsyncMock()
        adapter.register_process = AsyncMock()
        adapter.register_schedule = AsyncMock()
        adapter.start_process = AsyncMock(side_effect=RuntimeError("adapter broken"))

        mgr = ProcessManager(adapter=adapter, app_spec=app_spec)
        await mgr.initialize()

        # Should not raise
        run_ids = await mgr.on_entity_created("Order", "order-1", {"total": 50})
        assert run_ids == []
