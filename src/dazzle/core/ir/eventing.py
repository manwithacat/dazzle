"""
IR Types for Event-First Architecture (v0.18.0).

This module defines the intermediate representation types for event-driven
features in the DAZZLE DSL:

- TopicSpec: Event topic definition with retention and partitioning
- EventSpec: Event schema definition
- EventModelSpec: Collection of topics and events
- PublishSpec: Declarative event publishing from entities
- SubscribeSpec: Event subscription with handlers
- ProjectionSpec: Event-driven state projection
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventTriggerKind(StrEnum):
    """Trigger conditions for automatic event publishing."""

    CREATED = "created"  # Entity created
    UPDATED = "updated"  # Entity updated (any field)
    DELETED = "deleted"  # Entity deleted
    FIELD_CHANGED = "field_changed"  # Specific field changed
    STATUS_CHANGED = "status_changed"  # Status field changed (state machine)


class ProjectionAction(StrEnum):
    """Actions for projection handlers."""

    UPSERT = "upsert"  # Insert or update
    UPDATE = "update"  # Update only
    DELETE = "delete"  # Delete record
    INCREMENT = "increment"  # Increment counter
    AGGREGATE = "aggregate"  # Recompute aggregate


class TopicSpec(BaseModel):
    """
    Specification for an event topic.

    Topics are logical groupings of related events. They provide:
    - Ordering guarantees within a partition key
    - Retention policy for event storage
    - Schema validation for events

    DSL Example:
        topic orders:
            retention: 7d
            partition_key: order_id
    """

    name: str = Field(..., description="Topic name (unique within app)")
    retention_days: int = Field(default=7, description="Days to retain events")
    partition_key: str = Field(
        default="entity_id",
        description="Field used for partitioning (ordering guarantee)",
    )
    description: str | None = Field(default=None, description="Human-readable description")


class EventFieldSpec(BaseModel):
    """
    Specification for a custom event field.

    Used when events have fields beyond the entity payload.

    DSL Example:
        event OrderStatusChanged:
            topic: orders
            fields:
                order_id: uuid required
                old_status: str required
                new_status: str required
    """

    name: str = Field(..., description="Field name")
    field_type: str = Field(..., description="Field type (uuid, str, int, etc.)")
    required: bool = Field(default=True, description="Whether field is required")
    description: str | None = Field(default=None, description="Field description")


class EventSpec(BaseModel):
    """
    Specification for an event type.

    Events are immutable records of things that happened in the system.
    Each event belongs to a topic and has either:
    - A reference to an entity (uses entity's schema as payload)
    - Custom fields defined inline

    DSL Example:
        event OrderCreated:
            topic: orders
            payload: Order

        event OrderStatusChanged:
            topic: orders
            fields:
                order_id: uuid required
                old_status: str required
                new_status: str required
    """

    name: str = Field(..., description="Event name (PascalCase)")
    topic: str = Field(..., description="Topic this event belongs to")
    payload_entity: str | None = Field(
        default=None,
        description="Entity name to use as payload schema",
    )
    custom_fields: list[EventFieldSpec] = Field(
        default_factory=list,
        description="Custom fields if not using entity payload",
    )
    version: str = Field(default="1.0", description="Event schema version")
    description: str | None = Field(default=None, description="Event description")

    @property
    def event_type(self) -> str:
        """Generate the fully qualified event type name."""
        return f"app.{self.topic}.{self.name}"


class EventModelSpec(BaseModel):
    """
    Complete event model specification for an application.

    Contains all topics and events defined in the app.

    DSL Example:
        event_model:
            topic orders:
                retention: 7d
                partition_key: order_id

            event OrderCreated:
                topic: orders
                payload: Order

            event OrderStatusChanged:
                topic: orders
                fields:
                    order_id: uuid required
                    old_status: str required
                    new_status: str required
    """

    topics: list[TopicSpec] = Field(default_factory=list, description="Defined topics")
    events: list[EventSpec] = Field(default_factory=list, description="Defined events")

    def get_topic(self, name: str) -> TopicSpec | None:
        """Get a topic by name."""
        for topic in self.topics:
            if topic.name == name:
                return topic
        return None

    def get_event(self, name: str) -> EventSpec | None:
        """Get an event by name."""
        for event in self.events:
            if event.name == name:
                return event
        return None

    def events_for_topic(self, topic_name: str) -> list[EventSpec]:
        """Get all events for a topic."""
        return [e for e in self.events if e.topic == topic_name]


class PublishSpec(BaseModel):
    """
    Specification for automatic event publishing from an entity.

    Declaratively specifies when events should be published based on
    entity lifecycle events or field changes.

    DSL Example (in entity):
        publish OrderCreated when created
        publish OrderStatusChanged when status changed
    """

    event_name: str = Field(..., description="Event to publish")
    trigger: EventTriggerKind = Field(..., description="When to trigger")
    entity_name: str = Field(..., description="Source entity")
    field_name: str | None = Field(
        default=None,
        description="Field to watch (for field_changed trigger)",
    )
    condition: str | None = Field(
        default=None,
        description="Optional condition expression",
    )


class EventHandlerSpec(BaseModel):
    """
    Specification for handling a specific event type in a subscription.

    DSL Example:
        on OrderCreated:
            call service send_confirmation_email
        on OrderStatusChanged:
            when new_status = "shipped":
                call service send_shipping_notification
    """

    event_name: str = Field(..., description="Event to handle")
    service_name: str | None = Field(default=None, description="Service to call")
    service_method: str | None = Field(default=None, description="Method to call")
    condition: str | None = Field(default=None, description="When condition")
    field_mappings: dict[str, str] = Field(
        default_factory=dict,
        description="Mappings from event fields to service inputs",
    )


class SubscribeSpec(BaseModel):
    """
    Specification for subscribing to events from a topic.

    Defines how events should be processed, including:
    - Which topic to subscribe to
    - Consumer group ID (for load balancing)
    - Handlers for each event type

    DSL Example:
        subscribe app.orders as notification_handler:
            on OrderCreated:
                call service send_confirmation_email
            on OrderStatusChanged:
                when new_status = "shipped":
                    call service send_shipping_notification
    """

    topic: str = Field(..., description="Topic to subscribe to")
    group_id: str = Field(..., description="Consumer group identifier")
    handlers: list[EventHandlerSpec] = Field(
        default_factory=list,
        description="Event handlers",
    )
    description: str | None = Field(default=None, description="Subscription purpose")


class ProjectionHandlerSpec(BaseModel):
    """
    Specification for handling an event in a projection.

    Projections build queryable state from events.

    DSL Example:
        on OrderCreated:
            upsert with order_id, status="pending"
        on OrderStatusChanged:
            update status=new_status
    """

    event_name: str = Field(..., description="Event to handle")
    action: ProjectionAction = Field(..., description="Projection action")
    key_field: str | None = Field(
        default=None,
        description="Field to use as key for upsert/update",
    )
    field_mappings: dict[str, Any] = Field(
        default_factory=dict,
        description="Field value mappings",
    )
    condition: str | None = Field(default=None, description="When condition")


class ProjectionSpec(BaseModel):
    """
    Specification for an event-driven projection.

    Projections build and maintain queryable state from event streams.
    They are automatically kept up-to-date as new events arrive.

    DSL Example:
        project OrderDashboard from app.orders:
            on OrderCreated:
                upsert with order_id, status="pending"
            on OrderStatusChanged:
                update status=new_status
    """

    name: str = Field(..., description="Projection name")
    source_topic: str = Field(..., description="Topic to project from")
    target_entity: str | None = Field(
        default=None,
        description="Entity to project into (optional, can be view)",
    )
    handlers: list[ProjectionHandlerSpec] = Field(
        default_factory=list,
        description="Event handlers",
    )
    description: str | None = Field(default=None, description="Projection purpose")
