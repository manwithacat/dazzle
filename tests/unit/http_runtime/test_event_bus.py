"""
Tests for entity event bus.

Tests event emission and handler registration.
"""

from typing import Any

import pytest

from dazzle.http.runtime.event_bus import (
    EntityEvent,
    EntityEventBus,
    EntityEventType,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def event_bus() -> Any:
    """Create a fresh event bus for testing."""
    return EntityEventBus()


# =============================================================================
# EntityEvent Tests
# =============================================================================


class TestEntityEvent:
    """Tests for EntityEvent class."""

    def test_create_event(self) -> None:
        """Test creating an event."""
        event = EntityEvent(
            event_type=EntityEventType.CREATED,
            entity_name="Task",
            entity_id="123",
            data={"title": "Test"},
            user_id="user_456",
        )

        assert event.event_type == EntityEventType.CREATED
        assert event.entity_name == "Task"
        assert event.entity_id == "123"
        assert event.data is not None and event.data["title"] == "Test"
        assert event.user_id == "user_456"
        assert event.timestamp > 0


# =============================================================================
# EntityEventBus Tests
# =============================================================================


class TestEntityEventBus:
    """Tests for EntityEventBus class."""

    @pytest.mark.asyncio
    async def test_emit_created(self, event_bus: Any) -> None:
        """Test emitting created event."""
        events = []

        async def handler(event: Any) -> None:
            events.append(event)

        event_bus.add_handler(handler)

        await event_bus.emit_created(
            entity_name="Task",
            entity_id="123",
            data={"title": "Test"},
            user_id="user_456",
        )

        assert len(events) == 1
        assert events[0].event_type == EntityEventType.CREATED
        assert events[0].entity_name == "Task"
        assert events[0].entity_id == "123"

    @pytest.mark.asyncio
    async def test_emit_updated(self, event_bus: Any) -> None:
        """Test emitting updated event."""
        events = []

        async def handler(event: Any) -> None:
            events.append(event)

        event_bus.add_handler(handler)

        await event_bus.emit_updated(
            entity_name="Task",
            entity_id="123",
            data={"title": "Updated"},
        )

        assert len(events) == 1
        assert events[0].event_type == EntityEventType.UPDATED

    @pytest.mark.asyncio
    async def test_emit_deleted(self, event_bus: Any) -> None:
        """Test emitting deleted event."""
        events = []

        async def handler(event: Any) -> None:
            events.append(event)

        event_bus.add_handler(handler)

        await event_bus.emit_deleted(
            entity_name="Task",
            entity_id="123",
        )

        assert len(events) == 1
        assert events[0].event_type == EntityEventType.DELETED
        assert events[0].data is None

    @pytest.mark.asyncio
    async def test_multiple_handlers(self, event_bus: Any) -> None:
        """Test multiple handlers are called."""
        handler1_calls = []
        handler2_calls = []

        async def handler1(event: Any) -> None:
            handler1_calls.append(event)

        async def handler2(event: Any) -> None:
            handler2_calls.append(event)

        event_bus.add_handler(handler1)
        event_bus.add_handler(handler2)

        await event_bus.emit_created("Task", "123", {"title": "Test"})

        assert len(handler1_calls) == 1
        assert len(handler2_calls) == 1

    @pytest.mark.asyncio
    async def test_sync_handler(self, event_bus: Any) -> None:
        """Test synchronous handler."""
        events = []

        def sync_handler(event: Any) -> None:
            events.append(event)

        event_bus.add_sync_handler(sync_handler)

        await event_bus.emit_created("Task", "123", {"title": "Test"})

        assert len(events) == 1


# =============================================================================
# Handler Error Handling Tests
# =============================================================================


class TestHandlerErrors:
    """Tests for handler error handling."""

    @pytest.mark.asyncio
    async def test_handler_error_does_not_stop_others(self, event_bus: Any) -> None:
        """Test that a handler error doesn't stop other handlers."""
        events = []

        async def failing_handler(event: Any) -> None:
            raise ValueError("Handler failed")

        async def working_handler(event: Any) -> None:
            events.append(event)

        event_bus.add_handler(failing_handler)
        event_bus.add_handler(working_handler)

        # Should not raise
        await event_bus.emit_created("Task", "123", {})

        # Working handler should still be called
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_sync_handler_error_does_not_stop_others(self, event_bus: Any) -> None:
        """Test that a sync handler error doesn't stop others."""
        events = []

        def failing_handler(event: Any) -> None:
            raise ValueError("Handler failed")

        def working_handler(event: Any) -> None:
            events.append(event)

        event_bus.add_sync_handler(failing_handler)
        event_bus.add_sync_handler(working_handler)

        # Should not raise
        await event_bus.emit_created("Task", "123", {})

        # Working handler should still be called
        assert len(events) == 1
