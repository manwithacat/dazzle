"""
Tests for entity event bus.

Tests event emission, handler registration, and WebSocket broadcasting.
"""

from unittest.mock import AsyncMock

import pytest

from dazzle_dnr_back.runtime.event_bus import (
    EntityEvent,
    EntityEventBus,
    EntityEventType,
    RealtimeRepositoryMixin,
    create_event_bus,
    get_event_bus,
    reset_event_bus,
    set_event_bus,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_global_bus():
    """Reset global event bus before each test."""
    reset_event_bus()
    yield
    reset_event_bus()


@pytest.fixture
def event_bus():
    """Create an event bus for testing."""
    return create_event_bus()


@pytest.fixture
def mock_ws_manager():
    """Create a mock WebSocket manager."""
    manager = AsyncMock()
    manager.broadcast = AsyncMock(return_value=2)
    return manager


# =============================================================================
# EntityEvent Tests
# =============================================================================


class TestEntityEvent:
    """Tests for EntityEvent class."""

    def test_create_event(self):
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
        assert event.data["title"] == "Test"
        assert event.user_id == "user_456"
        assert event.timestamp > 0

    def test_channel_property(self):
        """Test channel name generation."""
        event = EntityEvent(
            event_type=EntityEventType.UPDATED,
            entity_name="Task",
            entity_id="123",
        )

        assert event.channel == "entity:Task"

    def test_record_channel_property(self):
        """Test record channel name generation."""
        event = EntityEvent(
            event_type=EntityEventType.UPDATED,
            entity_name="Task",
            entity_id="123",
        )

        assert event.record_channel == "entity:Task:123"


# =============================================================================
# EntityEventBus Tests
# =============================================================================


class TestEntityEventBus:
    """Tests for EntityEventBus class."""

    @pytest.mark.asyncio
    async def test_emit_created(self, event_bus):
        """Test emitting created event."""
        events = []

        async def handler(event):
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
    async def test_emit_updated(self, event_bus):
        """Test emitting updated event."""
        events = []

        async def handler(event):
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
    async def test_emit_deleted(self, event_bus):
        """Test emitting deleted event."""
        events = []

        async def handler(event):
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
    async def test_multiple_handlers(self, event_bus):
        """Test multiple handlers are called."""
        handler1_calls = []
        handler2_calls = []

        async def handler1(event):
            handler1_calls.append(event)

        async def handler2(event):
            handler2_calls.append(event)

        event_bus.add_handler(handler1)
        event_bus.add_handler(handler2)

        await event_bus.emit_created("Task", "123", {"title": "Test"})

        assert len(handler1_calls) == 1
        assert len(handler2_calls) == 1

    @pytest.mark.asyncio
    async def test_remove_handler(self, event_bus):
        """Test removing a handler."""
        events = []

        async def handler(event):
            events.append(event)

        event_bus.add_handler(handler)
        await event_bus.emit_created("Task", "123", {})
        assert len(events) == 1

        event_bus.remove_handler(handler)
        await event_bus.emit_created("Task", "456", {})
        assert len(events) == 1  # No new event

    def test_sync_handler(self, event_bus):
        """Test synchronous handler."""
        events = []

        def sync_handler(event):
            events.append(event)

        event_bus.add_sync_handler(sync_handler)

        event_bus.emit_created_sync("Task", "123", {"title": "Test"})

        assert len(events) == 1

    def test_enable_disable(self, event_bus):
        """Test enabling/disabling event emission."""
        events = []

        def handler(event):
            events.append(event)

        event_bus.add_sync_handler(handler)

        event_bus.emit_created_sync("Task", "1", {})
        assert len(events) == 1

        event_bus.disable()
        event_bus.emit_created_sync("Task", "2", {})
        assert len(events) == 1  # No new event

        event_bus.enable()
        event_bus.emit_created_sync("Task", "3", {})
        assert len(events) == 2


# =============================================================================
# WebSocket Broadcasting Tests
# =============================================================================


class TestWebSocketBroadcasting:
    """Tests for WebSocket broadcasting integration."""

    @pytest.mark.asyncio
    async def test_broadcast_on_emit(self, event_bus, mock_ws_manager):
        """Test that emit broadcasts to WebSocket."""
        event_bus.set_websocket_manager(mock_ws_manager)

        await event_bus.emit_created("Task", "123", {"title": "Test"})

        # Should broadcast to entity channel
        mock_ws_manager.broadcast.assert_called()
        call_args = mock_ws_manager.broadcast.call_args[0]
        assert call_args[0] == "entity:Task"

    @pytest.mark.asyncio
    async def test_broadcast_to_record_channel_on_update(self, event_bus, mock_ws_manager):
        """Test that update broadcasts to record channel too."""
        event_bus.set_websocket_manager(mock_ws_manager)

        await event_bus.emit_updated("Task", "123", {"title": "Updated"})

        # Should broadcast twice - entity channel and record channel
        assert mock_ws_manager.broadcast.call_count == 2

    @pytest.mark.asyncio
    async def test_no_broadcast_without_manager(self, event_bus):
        """Test that emit works without WebSocket manager."""
        events = []

        async def handler(event):
            events.append(event)

        event_bus.add_handler(handler)

        # Should not raise
        await event_bus.emit_created("Task", "123", {"title": "Test"})

        assert len(events) == 1


# =============================================================================
# Global Event Bus Tests
# =============================================================================


class TestGlobalEventBus:
    """Tests for global event bus functions."""

    def test_get_event_bus_creates_default(self):
        """Test that get_event_bus creates a default bus."""
        bus = get_event_bus()

        assert bus is not None
        assert isinstance(bus, EntityEventBus)

    def test_get_event_bus_returns_same(self):
        """Test that get_event_bus returns the same instance."""
        bus1 = get_event_bus()
        bus2 = get_event_bus()

        assert bus1 is bus2

    def test_set_event_bus(self):
        """Test setting a custom event bus."""
        custom_bus = create_event_bus()
        set_event_bus(custom_bus)

        assert get_event_bus() is custom_bus

    def test_reset_event_bus(self):
        """Test resetting the global event bus."""
        bus1 = get_event_bus()
        reset_event_bus()
        bus2 = get_event_bus()

        assert bus1 is not bus2


# =============================================================================
# RealtimeRepositoryMixin Tests
# =============================================================================


class TestRealtimeRepositoryMixin:
    """Tests for RealtimeRepositoryMixin."""

    @pytest.mark.asyncio
    async def test_emit_created_method(self):
        """Test the _emit_created method."""
        events = []

        async def handler(event):
            events.append(event)

        bus = create_event_bus()
        bus.add_handler(handler)
        set_event_bus(bus)

        class TestRepo(RealtimeRepositoryMixin):
            entity_name = "Task"

        repo = TestRepo()
        await repo._emit_created("123", {"title": "Test"}, "user_456")

        assert len(events) == 1
        assert events[0].entity_name == "Task"
        assert events[0].entity_id == "123"
        assert events[0].user_id == "user_456"

    @pytest.mark.asyncio
    async def test_custom_event_bus(self):
        """Test using a custom event bus on the mixin."""
        events = []

        async def handler(event):
            events.append(event)

        custom_bus = create_event_bus()
        custom_bus.add_handler(handler)

        class TestRepo(RealtimeRepositoryMixin):
            entity_name = "Task"

        repo = TestRepo()
        repo.set_event_bus(custom_bus)

        await repo._emit_updated("123", {"title": "Updated"})

        assert len(events) == 1
        assert events[0].event_type == EntityEventType.UPDATED


# =============================================================================
# Handler Error Handling Tests
# =============================================================================


class TestHandlerErrors:
    """Tests for handler error handling."""

    @pytest.mark.asyncio
    async def test_handler_error_does_not_stop_others(self, event_bus):
        """Test that a handler error doesn't stop other handlers."""
        events = []

        async def failing_handler(event):
            raise ValueError("Handler failed")

        async def working_handler(event):
            events.append(event)

        event_bus.add_handler(failing_handler)
        event_bus.add_handler(working_handler)

        # Should not raise
        await event_bus.emit_created("Task", "123", {})

        # Working handler should still be called
        assert len(events) == 1

    def test_sync_handler_error_does_not_stop_others(self, event_bus):
        """Test that a sync handler error doesn't stop others."""
        events = []

        def failing_handler(event):
            raise ValueError("Handler failed")

        def working_handler(event):
            events.append(event)

        event_bus.add_sync_handler(failing_handler)
        event_bus.add_sync_handler(working_handler)

        # Should not raise
        event_bus.emit_created_sync("Task", "123", {})

        # Working handler should still be called
        assert len(events) == 1
