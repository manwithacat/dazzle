"""
Event-Emitting Service Mixin.

This module provides a mixin class that adds event emission capabilities
to CRUD services. Events are emitted through the outbox for transactional
safety.

Usage:
    class MyService(EventEmittingMixin, CRUDService):
        pass

    # Events will be automatically emitted on create/update/delete
"""

from __future__ import annotations

import logging
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel

from dazzle_back.events.envelope import EventEnvelope

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
CreateT = TypeVar("CreateT", bound=BaseModel)
UpdateT = TypeVar("UpdateT", bound=BaseModel)


class EventEmittingMixin(Generic[T]):
    """
    Mixin that adds event emission to CRUD services.

    When mixed into a service, this will emit events for:
    - create: Emits {Entity}.created event
    - update: Emits {Entity}.updated event (and {Entity}.{field}_changed for tracked fields)
    - delete: Emits {Entity}.deleted event

    Events are emitted through the outbox for transactional safety.
    The mixin expects the service to have:
    - entity_name: str
    - _repository: Repository with db connection access

    Example:
        class OrderService(EventEmittingMixin, CRUDService):
            pass

        # On create, emits: app.Order.created
        # On update, emits: app.Order.updated
        # On delete, emits: app.Order.deleted
    """

    # Entity name (set by service)
    entity_name: str

    # Event emission settings
    _emit_created: bool = True
    _emit_updated: bool = True
    _emit_deleted: bool = True
    _tracked_fields: list[str] | None = None  # Fields to emit change events for

    # Event framework (injected at runtime)
    _event_framework: Any = None

    def set_event_framework(self, framework: Any) -> None:
        """
        Set the event framework for event emission.

        Args:
            framework: EventFramework instance
        """
        self._event_framework = framework

    def configure_events(
        self,
        *,
        emit_created: bool = True,
        emit_updated: bool = True,
        emit_deleted: bool = True,
        tracked_fields: list[str] | None = None,
    ) -> None:
        """
        Configure which events to emit.

        Args:
            emit_created: Emit events on create
            emit_updated: Emit events on update
            emit_deleted: Emit events on delete
            tracked_fields: Fields to emit individual change events for
        """
        self._emit_created = emit_created
        self._emit_updated = emit_updated
        self._emit_deleted = emit_deleted
        self._tracked_fields = tracked_fields

    def _build_event_type(self, action: str) -> str:
        """Build the full event type string."""
        return f"app.{self.entity_name}.{action}"

    def _build_topic(self) -> str:
        """Build the topic name for this entity."""
        return f"app.{self.entity_name}"

    async def _emit_event(
        self,
        action: str,
        entity_id: UUID,
        payload: dict[str, Any],
        *,
        old_value: dict[str, Any] | None = None,
    ) -> None:
        """
        Emit an event for an entity action.

        Args:
            action: Action name (created, updated, deleted)
            entity_id: Entity ID
            payload: Event payload
            old_value: Previous entity state (for update events)
        """
        if self._event_framework is None:
            logger.debug(
                "Event framework not configured, skipping event emission",
                extra={"entity": self.entity_name, "action": action},
            )
            return

        event_type = self._build_event_type(action)
        topic = self._build_topic()

        # Include old_value in payload for updates
        if old_value is not None:
            payload = {**payload, "_old": old_value}

        envelope = EventEnvelope.create(
            event_type=event_type,
            key=str(entity_id),
            payload=payload,
            producer=f"dazzle.{self.entity_name}",
        )

        try:
            # Get connection from repository
            conn = await self._get_db_connection()
            if conn:
                await self._event_framework.emit_event(conn, envelope, topic)
                logger.debug(
                    "Emitted event",
                    extra={
                        "event_type": event_type,
                        "entity_id": str(entity_id),
                    },
                )
        except Exception as e:
            logger.warning(
                "Failed to emit event",
                extra={
                    "event_type": event_type,
                    "entity_id": str(entity_id),
                    "error": str(e),
                },
            )

    async def _get_db_connection(self) -> Any:
        """Get the database connection from the repository."""
        # This assumes the service has a _repository attribute
        repo = getattr(self, "_repository", None)
        if repo is None:
            return None

        # Get connection from repository
        conn_attr = getattr(repo, "_conn", None)
        if conn_attr is None:
            conn_attr = getattr(repo, "db", None)
        return conn_attr

    async def _emit_created_event(self, entity: T) -> None:
        """Emit a created event for the entity."""
        if not self._emit_created:
            return

        entity_dict = entity.model_dump() if hasattr(entity, "model_dump") else dict(entity)
        entity_id = entity_dict.get("id")
        if entity_id:
            await self._emit_event("created", entity_id, entity_dict)

    async def _emit_updated_event(
        self,
        entity: T,
        old_entity: T | None = None,
    ) -> None:
        """Emit an updated event for the entity."""
        if not self._emit_updated:
            return

        entity_dict = entity.model_dump() if hasattr(entity, "model_dump") else dict(entity)
        entity_id = entity_dict.get("id")

        old_dict = None
        if old_entity:
            old_dict = (
                old_entity.model_dump() if hasattr(old_entity, "model_dump") else dict(old_entity)
            )

        if entity_id:
            await self._emit_event("updated", entity_id, entity_dict, old_value=old_dict)

            # Emit field-specific change events for tracked fields
            if self._tracked_fields and old_dict:
                for field in self._tracked_fields:
                    if field in entity_dict and field in old_dict:
                        if entity_dict[field] != old_dict[field]:
                            await self._emit_event(
                                f"{field}_changed",
                                entity_id,
                                {
                                    "id": entity_id,
                                    "field": field,
                                    "old_value": old_dict[field],
                                    "new_value": entity_dict[field],
                                },
                            )

    async def _emit_deleted_event(self, entity_id: UUID) -> None:
        """Emit a deleted event for the entity."""
        if not self._emit_deleted:
            return

        await self._emit_event("deleted", entity_id, {"id": str(entity_id)})


class EventEmittingCRUDService(EventEmittingMixin[T], Generic[T, CreateT, UpdateT]):
    """
    CRUD service with automatic event emission.

    This is a convenience class that combines EventEmittingMixin with
    the standard CRUD operations. Subclass this instead of CRUDService
    to get automatic event emission.

    Note: This is a protocol/interface - actual implementation would
    need to inherit from both this and CRUDService.
    """

    pass
