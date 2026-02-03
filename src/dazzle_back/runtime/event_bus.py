"""
Event bus for DNR entity change events.

Provides decoupled event publishing from repositories to WebSocket broadcasts.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from dazzle_back.runtime.websocket_manager import WebSocketManager


# =============================================================================
# Event Types
# =============================================================================


class EntityEventType(StrEnum):
    """Entity event types."""

    CREATED = "entity:created"
    UPDATED = "entity:updated"
    DELETED = "entity:deleted"


@dataclass
class EntityEvent:
    """An entity change event."""

    event_type: EntityEventType
    entity_name: str
    entity_id: str
    data: dict[str, Any] | None = None
    user_id: str | None = None  # Who made the change
    timestamp: float = field(default_factory=lambda: __import__("time").time() * 1000)

    @property
    def channel(self) -> str:
        """Get the entity channel name."""
        return f"entity:{self.entity_name}"

    @property
    def record_channel(self) -> str:
        """Get the specific record channel name."""
        return f"entity:{self.entity_name}:{self.entity_id}"


# =============================================================================
# Event Handlers
# =============================================================================


EventHandler = Callable[[EntityEvent], Awaitable[None]]
SyncEventHandler = Callable[[EntityEvent], None]


# =============================================================================
# Entity Event Bus
# =============================================================================


@dataclass
class EntityEventBus:
    """
    Publishes entity change events to WebSocket subscribers.

    Provides:
    - Event emission for CRUD operations
    - WebSocket broadcast integration
    - Custom event handlers
    - Sync and async handler support
    """

    ws_manager: WebSocketManager | None = None
    _handlers: list[EventHandler] = field(default_factory=list)
    _sync_handlers: list[SyncEventHandler] = field(default_factory=list)
    _enabled: bool = True

    def set_websocket_manager(self, manager: WebSocketManager) -> None:
        """Set the WebSocket manager for broadcasting."""
        self.ws_manager = manager

    def add_handler(self, handler: EventHandler) -> None:
        """Add an async event handler."""
        self._handlers.append(handler)

    def add_sync_handler(self, handler: SyncEventHandler) -> None:
        """Add a sync event handler."""
        self._sync_handlers.append(handler)

    def remove_handler(self, handler: EventHandler) -> None:
        """Remove an async event handler."""
        if handler in self._handlers:
            self._handlers.remove(handler)

    def remove_sync_handler(self, handler: SyncEventHandler) -> None:
        """Remove a sync event handler."""
        if handler in self._sync_handlers:
            self._sync_handlers.remove(handler)

    def enable(self) -> None:
        """Enable event publishing."""
        self._enabled = True

    def disable(self) -> None:
        """Disable event publishing."""
        self._enabled = False

    @property
    def is_enabled(self) -> bool:
        """Check if events are enabled."""
        return self._enabled

    # =========================================================================
    # Event Emission
    # =========================================================================

    async def emit(self, event: EntityEvent) -> None:
        """
        Emit an entity event.

        Broadcasts to WebSocket subscribers and calls handlers.
        """
        if not self._enabled:
            return

        # Call sync handlers
        for handler in self._sync_handlers:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Sync event handler %s failed for event %s:%s",
                    getattr(handler, "__name__", handler),
                    event.entity_name,
                    event.event_type.value,
                )

        # Call async handlers
        for handler in self._handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Async event handler %s failed for event %s:%s",
                    getattr(handler, "__name__", handler),
                    event.entity_name,
                    event.event_type.value,
                )

        # Broadcast to WebSocket
        await self._broadcast(event)

    async def emit_created(
        self,
        entity_name: str,
        entity_id: str | UUID,
        data: dict[str, Any],
        user_id: str | None = None,
    ) -> None:
        """
        Emit an entity created event.

        Args:
            entity_name: Name of the entity type
            entity_id: ID of the created entity
            data: Entity data
            user_id: ID of user who created it
        """
        event = EntityEvent(
            event_type=EntityEventType.CREATED,
            entity_name=entity_name,
            entity_id=str(entity_id),
            data=data,
            user_id=user_id,
        )
        await self.emit(event)

    async def emit_updated(
        self,
        entity_name: str,
        entity_id: str | UUID,
        data: dict[str, Any],
        user_id: str | None = None,
    ) -> None:
        """
        Emit an entity updated event.

        Args:
            entity_name: Name of the entity type
            entity_id: ID of the updated entity
            data: Updated entity data
            user_id: ID of user who updated it
        """
        event = EntityEvent(
            event_type=EntityEventType.UPDATED,
            entity_name=entity_name,
            entity_id=str(entity_id),
            data=data,
            user_id=user_id,
        )
        await self.emit(event)

    async def emit_deleted(
        self,
        entity_name: str,
        entity_id: str | UUID,
        user_id: str | None = None,
    ) -> None:
        """
        Emit an entity deleted event.

        Args:
            entity_name: Name of the entity type
            entity_id: ID of the deleted entity
            user_id: ID of user who deleted it
        """
        event = EntityEvent(
            event_type=EntityEventType.DELETED,
            entity_name=entity_name,
            entity_id=str(entity_id),
            data=None,
            user_id=user_id,
        )
        await self.emit(event)

    # =========================================================================
    # Sync Emission (for non-async contexts)
    # =========================================================================

    def emit_sync(self, event: EntityEvent) -> None:
        """
        Emit an event synchronously.

        Only calls sync handlers, does not broadcast to WebSocket.
        Use this when in a non-async context.
        """
        if not self._enabled:
            return

        for handler in self._sync_handlers:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Sync event handler %s failed for event %s:%s",
                    getattr(handler, "__name__", handler),
                    event.entity_name,
                    event.event_type.value,
                )

    def emit_created_sync(
        self,
        entity_name: str,
        entity_id: str | UUID,
        data: dict[str, Any],
        user_id: str | None = None,
    ) -> None:
        """Emit created event synchronously."""
        event = EntityEvent(
            event_type=EntityEventType.CREATED,
            entity_name=entity_name,
            entity_id=str(entity_id),
            data=data,
            user_id=user_id,
        )
        self.emit_sync(event)

    def emit_updated_sync(
        self,
        entity_name: str,
        entity_id: str | UUID,
        data: dict[str, Any],
        user_id: str | None = None,
    ) -> None:
        """Emit updated event synchronously."""
        event = EntityEvent(
            event_type=EntityEventType.UPDATED,
            entity_name=entity_name,
            entity_id=str(entity_id),
            data=data,
            user_id=user_id,
        )
        self.emit_sync(event)

    def emit_deleted_sync(
        self,
        entity_name: str,
        entity_id: str | UUID,
        user_id: str | None = None,
    ) -> None:
        """Emit deleted event synchronously."""
        event = EntityEvent(
            event_type=EntityEventType.DELETED,
            entity_name=entity_name,
            entity_id=str(entity_id),
            data=None,
            user_id=user_id,
        )
        self.emit_sync(event)

    # =========================================================================
    # WebSocket Broadcasting
    # =========================================================================

    async def _broadcast(self, event: EntityEvent) -> None:
        """Broadcast an event to WebSocket subscribers."""
        if not self.ws_manager:
            return

        from dazzle_back.runtime.websocket_manager import RealtimeMessage

        message = RealtimeMessage(
            type=event.event_type.value,
            channel=event.channel,
            payload={
                "id": event.entity_id,
                "entityName": event.entity_name,
                "data": event.data,
                "userId": event.user_id,
            },
            timestamp=event.timestamp,
        )

        # Broadcast to entity channel (all subscribers of this entity type)
        await self.ws_manager.broadcast(event.channel, message)

        # Also broadcast to specific record channel (for detail views)
        if event.event_type != EntityEventType.CREATED:
            await self.ws_manager.broadcast(event.record_channel, message)


# =============================================================================
# Global Event Bus
# =============================================================================


_global_event_bus: EntityEventBus | None = None


def get_event_bus() -> EntityEventBus:
    """Get the global event bus instance."""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EntityEventBus()
    return _global_event_bus


def set_event_bus(bus: EntityEventBus) -> None:
    """Set the global event bus instance."""
    global _global_event_bus
    _global_event_bus = bus


def reset_event_bus() -> None:
    """Reset the global event bus (mainly for testing)."""
    global _global_event_bus
    _global_event_bus = None


# =============================================================================
# Repository Integration
# =============================================================================


class RealtimeRepositoryMixin:
    """
    Mixin that adds event emission to repository operations.

    Usage:
        class MyRepository(RealtimeRepositoryMixin, SQLiteRepository[T]):
            entity_name = "Task"  # Set as class attribute
    """

    entity_name: str  # Must be set by the repository (as class attribute)
    _event_bus: EntityEventBus | None = None

    def set_event_bus(self, bus: EntityEventBus) -> None:
        """Set the event bus for this repository."""
        self._event_bus = bus

    def get_event_bus(self) -> EntityEventBus:
        """Get the event bus, using global if not set."""
        return self._event_bus or get_event_bus()

    async def _emit_created(
        self, entity_id: str, data: dict[str, Any], user_id: str | None = None
    ) -> None:
        """Emit a created event."""
        bus = self.get_event_bus()
        await bus.emit_created(self.entity_name, entity_id, data, user_id)

    async def _emit_updated(
        self, entity_id: str, data: dict[str, Any], user_id: str | None = None
    ) -> None:
        """Emit an updated event."""
        bus = self.get_event_bus()
        await bus.emit_updated(self.entity_name, entity_id, data, user_id)

    async def _emit_deleted(self, entity_id: str, user_id: str | None = None) -> None:
        """Emit a deleted event."""
        bus = self.get_event_bus()
        await bus.emit_deleted(self.entity_name, entity_id, user_id)


# =============================================================================
# Convenience Functions
# =============================================================================


def create_event_bus(
    ws_manager: WebSocketManager | None = None,
) -> EntityEventBus:
    """
    Create a new event bus.

    Args:
        ws_manager: Optional WebSocket manager for broadcasting

    Returns:
        Configured EntityEventBus
    """
    return EntityEventBus(ws_manager=ws_manager)
