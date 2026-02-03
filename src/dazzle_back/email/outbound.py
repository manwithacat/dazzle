"""
Outbound email sending with event emission.

Handles sending emails and emitting the appropriate events:
- email.send.requested (written to outbox)
- email.sent (on success)
- email.failed (on failure)
- email.bounced (async notification)

This module bridges the existing channel adapters with the
event-first email model.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from dazzle.core.ir.email import (
    EmailFailedEvent,
    EmailProvider,
    EmailSendRequestedEvent,
    EmailSentEvent,
)

if TYPE_CHECKING:
    from ..channels.adapters.base import EmailAdapter

logger = logging.getLogger("dazzle.email.outbound")


class EmailSendStatus(StrEnum):
    """Status of an email send operation."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    BOUNCED = "bounced"


@dataclass
class EmailSendResult:
    """Result of sending an email."""

    request_id: str
    status: EmailSendStatus
    message_id: str | None = None
    provider: EmailProvider = EmailProvider.MAILPIT
    latency_ms: float | None = None
    error_message: str | None = None
    is_retryable: bool = False

    # Events generated
    request_event: EmailSendRequestedEvent | None = None
    result_event: EmailSentEvent | EmailFailedEvent | None = None


class EmailSender:
    """Sends emails and emits events.

    Uses the underlying channel adapter for actual delivery,
    but wraps it with event emission for observability and replay.

    Usage:
        sender = EmailSender(adapter, event_bus)
        result = await sender.send(
            to="user@example.com",
            subject="Hello",
            body="World",
            triggered_by="User.created.123",
        )
    """

    def __init__(
        self,
        adapter: EmailAdapter,
        event_emitter: Any | None = None,
        default_from: str = "noreply@localhost",
    ):
        """Initialize email sender.

        Args:
            adapter: Email adapter for actual delivery
            event_emitter: Optional event emitter for publishing events
            default_from: Default from address
        """
        self._adapter = adapter
        self._event_emitter = event_emitter
        self._default_from = default_from

    @property
    def provider(self) -> EmailProvider:
        """Get provider enum from adapter name."""
        name = self._adapter.provider_name.lower()
        try:
            return EmailProvider(name)
        except ValueError:
            return EmailProvider.MAILPIT  # Default

    async def send(
        self,
        to: str,
        subject: str,
        body: str | None = None,
        html_body: str | None = None,
        from_address: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        template_id: str | None = None,
        triggered_by: str | None = None,
        correlation_id: str | None = None,
        tenant_id: str | None = None,
        channel_name: str = "email",
        operation_name: str = "send",
        idempotency_key: str | None = None,
    ) -> EmailSendResult:
        """Send an email with event emission.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Plain text body
            html_body: HTML body (optional)
            from_address: From address (uses default if not provided)
            cc: CC recipients
            bcc: BCC recipients
            template_id: Template ID if using templates
            triggered_by: What triggered this send (e.g., "Order.status_changed.123")
            correlation_id: Correlation ID for tracing
            tenant_id: Tenant ID for multi-tenancy
            channel_name: Channel name for events
            operation_name: Operation name for events
            idempotency_key: Key for deduplication

        Returns:
            EmailSendResult with status and events
        """
        request_id = str(uuid.uuid4())
        idem_key = idempotency_key or request_id

        # Create request event
        request_event = EmailSendRequestedEvent(
            request_id=request_id,
            idempotency_key=idem_key,
            channel_name=channel_name,
            operation_name=operation_name,
            to_address=to,
            cc_addresses=cc or [],
            bcc_addresses=bcc or [],
            template_id=template_id,
            body_pointer=None,  # Body is inline for now
            subject=subject,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            triggered_by=triggered_by,
            requested_at=datetime.now(UTC),
        )

        # Emit request event (if emitter configured)
        if self._event_emitter:
            await self._emit_event("office.mail.outbound", request_event)

        # Build outbox message for adapter
        from ..channels.outbox import OutboxMessage

        message = OutboxMessage(
            id=request_id,
            channel_name=channel_name,
            operation_name=operation_name,
            message_type="email",
            payload={
                "to": to,
                "from": from_address or self._default_from,
                "subject": subject,
                "body": body or "",
                "html_body": html_body,
                "cc": cc or [],
                "bcc": bcc or [],
            },
            recipient=to,
            correlation_id=correlation_id,
        )

        # Send via adapter
        try:
            result = await self._adapter.send(message)

            if result.is_success:
                # Create sent event
                sent_event = EmailSentEvent(
                    request_id=request_id,
                    message_id=result.message_id,
                    provider=self.provider,
                    to_address=to,
                    subject=subject,
                    sent_at=datetime.now(UTC),
                    latency_ms=result.latency_ms,
                )

                if self._event_emitter:
                    await self._emit_event("office.mail.sent", sent_event)

                return EmailSendResult(
                    request_id=request_id,
                    status=EmailSendStatus.SENT,
                    message_id=result.message_id,
                    provider=self.provider,
                    latency_ms=result.latency_ms,
                    request_event=request_event,
                    result_event=sent_event,
                )
            else:
                # Create failed event
                failed_event = EmailFailedEvent(
                    request_id=request_id,
                    provider=self.provider,
                    to_address=to,
                    subject=subject,
                    error_code=None,
                    error_message=result.error or "Unknown error",
                    is_retryable=result.is_retryable,
                    attempt_number=1,
                    failed_at=datetime.now(UTC),
                )

                if self._event_emitter:
                    await self._emit_event("office.mail.failed", failed_event)

                return EmailSendResult(
                    request_id=request_id,
                    status=EmailSendStatus.FAILED,
                    provider=self.provider,
                    error_message=result.error,
                    is_retryable=result.is_retryable,
                    request_event=request_event,
                    result_event=failed_event,
                )

        except Exception as e:
            logger.error(f"Error sending email: {e}")

            failed_event = EmailFailedEvent(
                request_id=request_id,
                provider=self.provider,
                to_address=to,
                subject=subject,
                error_code="EXCEPTION",
                error_message=str(e),
                is_retryable=True,
                attempt_number=1,
                failed_at=datetime.now(UTC),
            )

            if self._event_emitter:
                await self._emit_event("office.mail.failed", failed_event)

            return EmailSendResult(
                request_id=request_id,
                status=EmailSendStatus.FAILED,
                provider=self.provider,
                error_message=str(e),
                is_retryable=True,
                request_event=request_event,
                result_event=failed_event,
            )

    async def _emit_event(self, topic: str, event: Any) -> None:
        """Emit an event to the configured emitter."""
        if not self._event_emitter:
            return

        try:
            # The emitter should have a publish method
            if hasattr(self._event_emitter, "publish"):
                await self._event_emitter.publish(
                    topic=topic,
                    key=getattr(event, "request_id", str(uuid.uuid4())),
                    payload=event.model_dump(mode="json"),
                )
            else:
                logger.warning("Event emitter has no publish method")
        except Exception as e:
            logger.error(f"Failed to emit event to {topic}: {e}")


class EmailEventConsumer:
    """Consumer for email events.

    Handles:
    - Processing send requests from outbox
    - Handling bounce notifications
    """

    def __init__(self, sender: EmailSender):
        """Initialize consumer.

        Args:
            sender: Email sender for processing requests
        """
        self._sender = sender

    async def handle_send_requested(self, event: EmailSendRequestedEvent) -> EmailSendResult:
        """Handle a send request event.

        Called by the outbox processor when a send request is dequeued.

        Args:
            event: Send request event

        Returns:
            Send result
        """
        # The event contains the request, but we need to fetch
        # the actual content from somewhere (template or body pointer)

        # For now, this is a stub - actual implementation would:
        # 1. Fetch template if template_id is set
        # 2. Fetch body from pointer if body_pointer is set
        # 3. Call sender.send() with resolved content

        logger.info(f"Processing send request: {event.request_id} -> {event.to_address}")

        # This would be called from the outbox processor
        raise NotImplementedError("Outbox processing integration pending")
