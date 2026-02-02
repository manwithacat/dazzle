"""
Unit tests for entity lifecycle event triggering.

Tests that CRUDService correctly notifies callbacks when entities are
created, updated, or deleted.
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
