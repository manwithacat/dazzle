"""
Event Envelope Schema for Dazzle Event-First Architecture.

This module defines the canonical event envelope used throughout the Dazzle
event system. The schema is Kafka-shaped, meaning it follows Kafka's
conceptual model (topics, partitions, keys) even when running on SQLite.

Rule 0: The event log is the system journal; state is derived from accepted events.
Acceptance criteria:
1. Trust boundary - event originates from authorized producer
2. Schema validation - event conforms to declared schema
3. Producer commit - producer has durably committed the event (outbox published)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4


def _utc_now() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(UTC)


@dataclass
class EventEnvelope:
    """
    Canonical event envelope for Dazzle events.

    This is the wire format for all events in the system. It follows
    Kafka-shaped semantics while being transport-agnostic.

    Naming convention for event_type: <domain>.<entity>.<action>
    Examples:
        - app.Order.created
        - app.Order.status_changed
        - app.User.deleted

    Attributes:
        event_id: Unique identifier for this event (UUID)
        event_type: Fully qualified event type (e.g., "app.Order.created")
        event_version: Schema version for evolution (default "1.0")
        correlation_id: Links related events in a workflow/saga
        causation_id: Event ID that caused this event (for tracing)
        key: Partition key for ordering guarantees (usually entity_id)
        payload: Event data as JSON-serializable dict
        headers: Metadata dict (tenant_id, user_id, etc.)
        timestamp: When the event occurred (UTC)
        producer: Name of the service/module that produced this event
    """

    event_id: UUID = field(default_factory=uuid4)
    event_type: str = ""
    event_version: str = "1.0"
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    key: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utc_now)
    producer: str = "dazzle"
    deliver_at: datetime | None = None  # Delayed delivery: hold until this time

    @property
    def topic(self) -> str:
        """
        Extract topic from event_type.

        The topic is the event_type without the action suffix.
        Example: "app.Order.created" -> "app.Order"
        """
        parts = self.event_type.rsplit(".", 1)
        return parts[0] if len(parts) > 1 else self.event_type

    @property
    def action(self) -> str:
        """
        Extract action from event_type.

        The action is the last component of the event_type.
        Example: "app.Order.created" -> "created"
        """
        parts = self.event_type.rsplit(".", 1)
        return parts[1] if len(parts) > 1 else ""

    @property
    def entity_name(self) -> str:
        """
        Extract entity name from event_type.

        The entity name is the second component of the event_type.
        Example: "app.Order.created" -> "Order"
        """
        parts = self.event_type.split(".")
        return parts[1] if len(parts) >= 2 else ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize envelope to a JSON-serializable dictionary."""
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "event_version": self.event_version,
            "correlation_id": str(self.correlation_id) if self.correlation_id else None,
            "causation_id": str(self.causation_id) if self.causation_id else None,
            "key": self.key,
            "payload": self.payload,
            "headers": self.headers,
            "timestamp": self.timestamp.isoformat(),
            "producer": self.producer,
            "deliver_at": self.deliver_at.isoformat() if self.deliver_at else None,
        }

    def to_json(self) -> str:
        """Serialize envelope to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EventEnvelope:
        """Deserialize envelope from a dictionary."""
        return cls(
            event_id=UUID(data["event_id"]),
            event_type=data["event_type"],
            event_version=data.get("event_version", "1.0"),
            correlation_id=UUID(data["correlation_id"]) if data.get("correlation_id") else None,
            causation_id=UUID(data["causation_id"]) if data.get("causation_id") else None,
            key=data["key"],
            payload=data.get("payload", {}),
            headers=data.get("headers", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            producer=data.get("producer", "dazzle"),
            deliver_at=(
                datetime.fromisoformat(data["deliver_at"]) if data.get("deliver_at") else None
            ),
        )

    @classmethod
    def from_json(cls, json_str: str) -> EventEnvelope:
        """Deserialize envelope from JSON string."""
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def create(
        cls,
        event_type: str,
        key: str,
        payload: dict[str, Any],
        *,
        correlation_id: UUID | None = None,
        causation_id: UUID | None = None,
        headers: dict[str, str] | None = None,
        producer: str = "dazzle",
    ) -> EventEnvelope:
        """
        Factory method to create a new event envelope.

        Args:
            event_type: Fully qualified event type (e.g., "app.Order.created")
            key: Partition key for ordering (usually entity_id)
            payload: Event data
            correlation_id: Optional correlation ID for workflow tracking
            causation_id: Optional ID of the event that caused this one
            headers: Optional metadata headers
            producer: Name of the producing service

        Returns:
            A new EventEnvelope instance
        """
        return cls(
            event_id=uuid4(),
            event_type=event_type,
            key=key,
            payload=payload,
            correlation_id=correlation_id,
            causation_id=causation_id,
            headers=headers or {},
            producer=producer,
            timestamp=_utc_now(),
        )

    @classmethod
    def create_delayed(
        cls,
        event_type: str,
        key: str,
        payload: dict[str, Any],
        deliver_at: datetime,
        *,
        correlation_id: UUID | None = None,
        headers: dict[str, str] | None = None,
        producer: str = "dazzle",
    ) -> EventEnvelope:
        """Create a delayed event that won't be delivered until deliver_at."""
        return cls(
            event_id=uuid4(),
            event_type=event_type,
            key=key,
            payload=payload,
            correlation_id=correlation_id,
            headers=headers or {},
            producer=producer,
            timestamp=_utc_now(),
            deliver_at=deliver_at,
        )

    def with_correlation(self, correlation_id: UUID) -> EventEnvelope:
        """Create a copy of this envelope with a correlation ID."""
        return EventEnvelope(
            event_id=self.event_id,
            event_type=self.event_type,
            event_version=self.event_version,
            correlation_id=correlation_id,
            causation_id=self.causation_id,
            key=self.key,
            payload=self.payload,
            headers=self.headers,
            timestamp=self.timestamp,
            producer=self.producer,
        )

    def caused_by(self, cause: EventEnvelope) -> EventEnvelope:
        """
        Create a copy of this envelope that is caused by another event.

        Sets both causation_id (to the cause's event_id) and correlation_id
        (inherited from the cause if present, otherwise uses cause's event_id).
        """
        return EventEnvelope(
            event_id=self.event_id,
            event_type=self.event_type,
            event_version=self.event_version,
            correlation_id=cause.correlation_id or cause.event_id,
            causation_id=cause.event_id,
            key=self.key,
            payload=self.payload,
            headers=self.headers,
            timestamp=self.timestamp,
            producer=self.producer,
        )

    def __repr__(self) -> str:
        return (
            f"EventEnvelope(event_id={self.event_id!r}, "
            f"event_type={self.event_type!r}, key={self.key!r})"
        )
