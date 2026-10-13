"""
Event bus for the Dazzle runtime entity change events.

In-process pub/sub: CRUD services emit lifecycle events and registered
handlers (integration mappings, LLM triggers, SLA timers and app handlers
registered with ``add_sync_handler``) react to them.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

# =============================================================================
# Event Types
# =============================================================================


class EntityEventType(StrEnum):
    """Entity event types."""

    CREATED = "entity:created"
    UPDATED = "entity:updated"
    DELETED = "entity:deleted"
    FILE_UPLOADED = "entity:file_uploaded"


class LLMEventType(StrEnum):
    """LLM intent execution event types."""

    INTENT_COMPLETED = "llm_intent:completed"
    INTENT_FAILED = "llm_intent:failed"


@dataclass
class EntityEvent:
    """An entity change event."""

    event_type: EntityEventType
    entity_name: str
    entity_id: str
    data: dict[str, Any] | None = None
    user_id: str | None = None  # Who made the change
    timestamp: float = field(default_factory=lambda: __import__("time").time() * 1000)


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
    """Publishes entity change events to registered sync and async handlers."""

    _handlers: list[EventHandler] = field(default_factory=list)
    _sync_handlers: list[SyncEventHandler] = field(default_factory=list)

    def add_handler(self, handler: EventHandler) -> None:
        """Add an async event handler."""
        self._handlers.append(handler)

    def add_sync_handler(self, handler: SyncEventHandler) -> None:
        """Add a sync event handler."""
        self._sync_handlers.append(handler)

    # =========================================================================
    # Event Emission
    # =========================================================================

    async def emit(self, event: EntityEvent) -> None:
        """
        Emit an entity event to the sync handlers, then the async handlers.
        """
        # Call sync handlers
        for sync_handler in self._sync_handlers:
            try:
                sync_handler(event)
            except Exception:
                logger.exception(
                    "Sync event handler %s failed for event %s:%s",
                    getattr(sync_handler, "__name__", sync_handler),
                    event.entity_name,
                    event.event_type.value,
                )

        # Call async handlers
        for async_handler in self._handlers:
            try:
                await async_handler(event)
            except Exception:
                logger.exception(
                    "Async event handler %s failed for event %s:%s",
                    getattr(async_handler, "__name__", async_handler),
                    event.entity_name,
                    event.event_type.value,
                )

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

    async def emit_file_uploaded(
        self,
        entity_name: str,
        entity_id: str | UUID,
        data: dict[str, Any],
        user_id: str | None = None,
    ) -> None:
        """Emit an entity file_uploaded event."""
        event = EntityEvent(
            event_type=EntityEventType.FILE_UPLOADED,
            entity_name=entity_name,
            entity_id=str(entity_id),
            data=data,
            user_id=user_id,
        )
        await self.emit(event)
