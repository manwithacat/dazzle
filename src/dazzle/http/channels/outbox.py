"""
Outbound message shape for the DAZZLE email adapters.

``OutboxMessage`` is what ``BaseChannelAdapter.send`` takes. The delivery
outbox that persisted these messages (``OutboxRepository`` and the
``_dazzle_outbox`` table) was never constructed by the runtime; flense ship AR
removed it and Alembic revision ``0025_flense_park_event_transport`` drops the
table (DD-006 / DD-007).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class OutboxStatus(StrEnum):
    """Status of an outbox message."""

    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


@dataclass
class OutboxMessage:
    """A message in the outbox.

    Attributes:
        id: Unique message identifier
        channel_name: Name of the channel to send through
        operation_name: Name of the send operation
        message_type: Type of message (from DSL)
        payload: Serialized message payload
        recipient: Primary recipient (for deduplication)
        status: Current message status
        created_at: When the message was created
        updated_at: When the message was last updated
        scheduled_for: When to send the message (for delayed delivery)
        attempts: Number of send attempts
        max_attempts: Maximum retry attempts
        last_error: Last error message
        correlation_id: For tracking related messages
        build_id: Build identifier for observability
        metadata: Additional metadata
    """

    id: str
    channel_name: str
    operation_name: str
    message_type: str
    payload: dict[str, Any]
    recipient: str
    status: OutboxStatus = OutboxStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    scheduled_for: datetime | None = None
    attempts: int = 0
    max_attempts: int = 3
    last_error: str | None = None
    correlation_id: str | None = None
    build_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def create_outbox_message(
    channel_name: str,
    operation_name: str,
    message_type: str,
    payload: dict[str, Any],
    recipient: str,
    *,
    scheduled_for: datetime | None = None,
    correlation_id: str | None = None,
    build_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> OutboxMessage:
    """Create a new outbox message.

    This is the primary factory function for creating outbox messages.

    Args:
        channel_name: Name of the channel to send through
        operation_name: Name of the send operation
        message_type: Type of message (from DSL)
        payload: Message payload dictionary
        recipient: Primary recipient for deduplication
        scheduled_for: Optional delayed delivery time
        correlation_id: Optional correlation ID for tracking
        build_id: Optional build identifier
        metadata: Optional additional metadata

    Returns:
        New OutboxMessage ready to hand to an adapter
    """
    return OutboxMessage(
        id=str(uuid.uuid4()),
        channel_name=channel_name,
        operation_name=operation_name,
        message_type=message_type,
        payload=payload,
        recipient=recipient,
        scheduled_for=scheduled_for,
        correlation_id=correlation_id,
        build_id=build_id,
        metadata=metadata or {},
    )
