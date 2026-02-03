"""
Base channel adapter interface for DAZZLE messaging.

All channel adapters (Mailpit, SendGrid, RabbitMQ, etc.) implement this interface.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..detection import DetectionResult
    from ..outbox import OutboxMessage

logger = logging.getLogger("dazzle.channels.adapters")


def _utcnow() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


class SendStatus(StrEnum):
    """Status of a send operation."""

    SUCCESS = "success"
    FAILED = "failed"
    QUEUED = "queued"
    RATE_LIMITED = "rate_limited"


@dataclass
class SendResult:
    """Result of sending a message.

    Attributes:
        status: Send operation status
        message_id: Provider-assigned message ID (if available)
        provider_response: Raw response from provider
        error: Error message if failed
        latency_ms: Send latency in milliseconds
        timestamp: When the send completed
    """

    status: SendStatus
    message_id: str | None = None
    provider_response: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: float | None = None
    timestamp: datetime = field(default_factory=_utcnow)

    @property
    def is_success(self) -> bool:
        return self.status == SendStatus.SUCCESS

    @property
    def is_retryable(self) -> bool:
        """Check if the error is retryable."""
        return self.status in (SendStatus.RATE_LIMITED, SendStatus.QUEUED)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "message_id": self.message_id,
            "provider_response": self.provider_response,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp.isoformat(),
        }


class BaseChannelAdapter(ABC):
    """Base class for channel adapters.

    Adapters handle communication with specific messaging providers.
    Each adapter implements send/receive operations appropriate for its channel kind.

    Example:
        class MailpitAdapter(BaseChannelAdapter):
            async def send(self, message: OutboxMessage) -> SendResult:
                # Send via Mailpit SMTP
                ...
    """

    def __init__(self, detection_result: DetectionResult):
        """Initialize adapter with detection result.

        Args:
            detection_result: Provider detection result with connection info
        """
        self.detection_result = detection_result
        self._initialized = False

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider this adapter handles."""
        ...

    @property
    @abstractmethod
    def channel_kind(self) -> str:
        """Kind of channel: email, queue, or stream."""
        ...

    async def initialize(self) -> None:
        """Initialize the adapter.

        Called once before first use. Override to set up connections,
        validate credentials, etc.
        """
        self._initialized = True

    async def shutdown(self) -> None:
        """Shutdown the adapter.

        Called when the adapter is no longer needed. Override to close
        connections, flush buffers, etc.
        """
        self._initialized = False

    @abstractmethod
    async def send(self, message: OutboxMessage) -> SendResult:
        """Send a message through the provider.

        Args:
            message: Outbox message to send

        Returns:
            SendResult with status and details
        """
        ...

    async def health_check(self) -> bool:
        """Check if the adapter is healthy.

        Returns:
            True if healthy and ready to send
        """
        return self._initialized


class EmailAdapter(BaseChannelAdapter):
    """Base class for email adapters.

    Provides common email functionality like rendering templates.
    """

    @property
    def channel_kind(self) -> str:
        return "email"

    def build_email(self, message: OutboxMessage) -> dict[str, Any]:
        """Build email data from outbox message.

        Args:
            message: Outbox message with payload

        Returns:
            Dictionary with email fields (to, from, subject, body, etc.)
        """
        payload = message.payload
        return {
            "to": payload.get("to"),
            "from": payload.get("from", "noreply@localhost"),
            "subject": payload.get("subject", ""),
            "body": payload.get("body", ""),
            "html_body": payload.get("html_body"),
            "reply_to": payload.get("reply_to"),
            "cc": payload.get("cc", []),
            "bcc": payload.get("bcc", []),
            "attachments": payload.get("attachments", []),
        }


class QueueAdapter(BaseChannelAdapter):
    """Base class for queue adapters."""

    @property
    def channel_kind(self) -> str:
        return "queue"

    @abstractmethod
    async def receive(self, count: int = 1, timeout: float = 30.0) -> list[dict[str, Any]]:
        """Receive messages from the queue.

        Args:
            count: Maximum messages to receive
            timeout: Wait timeout in seconds

        Returns:
            List of received messages
        """
        ...

    @abstractmethod
    async def ack(self, message_id: str) -> None:
        """Acknowledge a message.

        Args:
            message_id: ID of message to acknowledge
        """
        ...

    @abstractmethod
    async def nack(self, message_id: str, requeue: bool = True) -> None:
        """Negative acknowledge a message.

        Args:
            message_id: ID of message to nack
            requeue: Whether to requeue the message
        """
        ...


class StreamAdapter(BaseChannelAdapter):
    """Base class for stream adapters."""

    @property
    def channel_kind(self) -> str:
        return "stream"

    @abstractmethod
    async def subscribe(
        self,
        group: str,
        consumer: str,
        callback: Any,
    ) -> None:
        """Subscribe to the stream.

        Args:
            group: Consumer group name
            consumer: Consumer name within group
            callback: Async callback for messages
        """
        ...

    @abstractmethod
    async def unsubscribe(self) -> None:
        """Unsubscribe from the stream."""
        ...
