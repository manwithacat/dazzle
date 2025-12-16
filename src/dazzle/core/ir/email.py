"""
Email event types for DAZZLE IR.

This module defines the event schema for the two-stream email model:
- Raw stream (`office.mail.raw`): Minimal metadata + pointer to blob storage
- Normalized stream (`office.mail.normalized`): Parsed fields, business refs, safe excerpts

Design Document: dev_docs/architecture/event_first/Dazzle-Email-Integration-Spec-v1.md
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# Email Provider Types
# ============================================================================


class EmailProvider(str, Enum):
    """Email provider types."""

    MAILPIT = "mailpit"  # Local dev
    SES = "ses"  # AWS SES
    SMTP_EDGE = "smtp_edge"  # Generic SMTP ingress
    WORKSPACE = "workspace"  # Google Workspace
    M365 = "m365"  # Microsoft 365


# ============================================================================
# Raw Email Event (Stream A: office.mail.raw)
# ============================================================================


class RawMailEvent(BaseModel):
    """
    Raw email event - minimal metadata with pointer to blob storage.

    This is the first event emitted when mail is received. Contains only
    metadata needed for routing and the pointer to the raw content.
    The raw content itself is stored in blob storage, never in the event.

    Stream: office.mail.raw
    Retention: Short (14-30 days typically)
    """

    # Identifiers
    mail_id: str = Field(..., description="UUID, stable internal ID")
    message_id: str | None = Field(None, description="RFC 5322 Message-ID header")

    # Provider info
    provider: EmailProvider = Field(..., description="Email provider that received this")
    received_at: datetime = Field(..., description="When the mail was received")

    # Minimal headers (for routing)
    from_address: str = Field(..., description="From address")
    to_addresses: list[str] = Field(default_factory=list, description="To addresses")
    cc_addresses: list[str] = Field(default_factory=list, description="Cc addresses")
    subject: str | None = Field(None, description="Subject (may be redacted by policy)")

    # Blob storage pointer
    raw_pointer: str = Field(..., description="S3 key / local path / blob ID")
    raw_sha256: str = Field(..., description="SHA256 hash of raw content")
    size_bytes: int = Field(..., description="Size of raw content")

    # Attachment summary
    attachments_present: bool = Field(default=False)
    attachment_count: int = Field(default=0)

    # Tenant (if known at ingestion)
    tenant_id: str | None = Field(None, description="Tenant ID if inferred from headers")

    model_config = ConfigDict(frozen=True)


# ============================================================================
# Normalized Email Event (Stream B: office.mail.normalized)
# ============================================================================


class EmailAttachmentRef(BaseModel):
    """Reference to an email attachment stored in blob storage."""

    name_redacted: str = Field(..., description="Filename (may be redacted)")
    mime_type: str = Field(..., description="MIME type")
    size_bytes: int = Field(..., description="Size in bytes")
    pointer: str = Field(..., description="Blob storage pointer")
    sha256: str = Field(..., description="SHA256 hash")

    model_config = ConfigDict(frozen=True)


class BusinessReference(BaseModel):
    """A business reference extracted from email content."""

    ref_type: str = Field(..., description="Type: ticket_id, invoice_ref, order_id, etc.")
    ref_value: str = Field(..., description="Extracted value")
    confidence: float = Field(default=1.0, description="Extraction confidence 0-1")

    model_config = ConfigDict(frozen=True)


class NormalizedMailEvent(BaseModel):
    """
    Normalized email event - parsed fields and business references.

    This event is emitted after normalizing a raw email. It contains
    structured, queryable fields extracted from the email content.
    No raw body content is included - only safe excerpts.

    Stream: office.mail.normalized
    Retention: Longer (aligned with business audit needs)
    """

    # Link to raw
    mail_id: str = Field(..., description="Same mail_id as RawMailEvent")
    raw_pointer: str = Field(..., description="Pointer to raw content")

    # Timestamps
    received_at: datetime = Field(..., description="Original receipt time")
    normalized_at: datetime = Field(..., description="When normalization occurred")

    # Parsed sender info
    from_address: str = Field(..., description="From address")
    from_domain: str = Field(..., description="Domain portion of from address")
    from_display_name: str | None = Field(None, description="Display name if present")

    # Recipient summary (not full addresses for privacy)
    to_count: int = Field(default=1, description="Number of To recipients")
    cc_count: int = Field(default=0, description="Number of Cc recipients")

    # Content summary
    subject_redacted: str = Field(default="", description="Subject (redacted if needed)")
    body_excerpt_redacted: str = Field(default="", description="First ~500 chars, redacted")
    body_length: int = Field(default=0, description="Original body length")
    has_html: bool = Field(default=False, description="Whether HTML body was present")

    # Language detection
    language: str | None = Field(None, description="Detected language code (ISO 639-1)")

    # Business references extracted
    business_refs: list[BusinessReference] = Field(
        default_factory=list, description="Extracted references"
    )

    # Attachments (pointers, not content)
    attachments: list[EmailAttachmentRef] = Field(
        default_factory=list, description="Attachment references"
    )

    # Classification (can be enhanced by LLM)
    classification: str | None = Field(
        None, description="Email type: invoice, support, sales, etc."
    )
    priority: str | None = Field(None, description="Inferred priority: high, normal, low")

    # Tenant/customer linkage
    tenant_id: str | None = Field(None, description="Matched tenant ID")
    customer_id: str | None = Field(None, description="Matched customer ID")

    model_config = ConfigDict(frozen=True)


# ============================================================================
# Outbound Email Events
# ============================================================================


class EmailSendRequestedEvent(BaseModel):
    """
    Event emitted when an email send is requested.

    Written via outbox pattern - guaranteed to be durable.

    Stream: office.mail.outbound
    """

    request_id: str = Field(..., description="UUID for this send request")
    idempotency_key: str = Field(..., description="For deduplication")
    channel_name: str = Field(..., description="Channel that initiated send")
    operation_name: str = Field(..., description="Send operation name")

    # Recipient info
    to_address: str = Field(..., description="Primary recipient")
    cc_addresses: list[str] = Field(default_factory=list)
    bcc_addresses: list[str] = Field(default_factory=list)

    # Content references (not inline content)
    template_id: str | None = Field(None, description="Template ID if using template")
    body_pointer: str | None = Field(None, description="Pointer to rendered body")
    subject: str = Field(default="", description="Subject line")

    # Context
    tenant_id: str | None = None
    correlation_id: str | None = None
    triggered_by: str | None = Field(None, description="Entity/event that triggered send")

    requested_at: datetime = Field(..., description="When send was requested")

    model_config = ConfigDict(frozen=True)


class EmailSentEvent(BaseModel):
    """Event emitted when an email was successfully sent."""

    request_id: str = Field(..., description="Links to EmailSendRequestedEvent")
    message_id: str | None = Field(None, description="Provider message ID")
    provider: EmailProvider = Field(..., description="Provider that sent it")

    to_address: str
    subject: str

    sent_at: datetime = Field(..., description="When send completed")
    latency_ms: float | None = Field(None, description="Send latency")

    model_config = ConfigDict(frozen=True)


class EmailFailedEvent(BaseModel):
    """Event emitted when an email send failed."""

    request_id: str = Field(..., description="Links to EmailSendRequestedEvent")
    provider: EmailProvider
    to_address: str
    subject: str

    error_code: str | None = Field(None, description="Error code if available")
    error_message: str = Field(..., description="Error description")
    is_retryable: bool = Field(default=False, description="Whether retry makes sense")
    attempt_number: int = Field(default=1)

    failed_at: datetime

    model_config = ConfigDict(frozen=True)


class EmailBouncedEvent(BaseModel):
    """Event emitted when an email bounced (async notification from provider)."""

    request_id: str | None = Field(None, description="Original request if traceable")
    message_id: str = Field(..., description="Provider message ID that bounced")
    provider: EmailProvider

    bounce_type: str = Field(..., description="hard, soft, complaint, etc.")
    bounce_subtype: str | None = None
    bounced_recipient: str = Field(..., description="Address that bounced")
    diagnostic_code: str | None = None

    bounced_at: datetime

    model_config = ConfigDict(frozen=True)


# ============================================================================
# Stream Definitions (HLESS-compliant)
# ============================================================================


def get_email_stream_definitions() -> dict[str, dict[str, str | int | list[str]]]:
    """
    Return HLESS stream definitions for email events.

    These are used to generate the email event infrastructure:
    - Topics
    - Schemas
    - Consumer groups
    """
    return {
        "office.mail.raw": {
            "record_kind": "OBSERVATION",  # External data, not verified
            "partition_key": "mail_id",
            "ordering_scope": "partition",
            "t_event_source": "received_at",
            "idempotency": "provider_dedup",  # Provider + message_id
            "retention_days": 30,
            "description": "Raw inbound email metadata with blob pointer",
        },
        "office.mail.normalized": {
            "record_kind": "DERIVATION",  # Derived from raw stream
            "partition_key": "mail_id",
            "ordering_scope": "partition",
            "t_event_source": "normalized_at",
            "idempotency": "source_dedup",  # mail_id from raw
            "source_streams": ["office.mail.raw"],
            "retention_days": 365,
            "description": "Normalized email with extracted fields and refs",
        },
        "office.mail.outbound": {
            "record_kind": "INTENT",  # Request to send
            "partition_key": "request_id",
            "ordering_scope": "partition",
            "t_event_source": "requested_at",
            "idempotency": "idempotency_key",
            "retention_days": 90,
            "description": "Outbound email send requests",
        },
        "office.mail.sent": {
            "record_kind": "FACT",  # Verified outcome
            "partition_key": "request_id",
            "ordering_scope": "partition",
            "t_event_source": "sent_at",
            "idempotency": "source_dedup",
            "source_streams": ["office.mail.outbound"],
            "retention_days": 365,
            "description": "Successfully sent emails",
        },
        "office.mail.failed": {
            "record_kind": "FACT",  # Verified outcome (failure)
            "partition_key": "request_id",
            "ordering_scope": "partition",
            "t_event_source": "failed_at",
            "idempotency": "attempt_dedup",  # request_id + attempt
            "source_streams": ["office.mail.outbound"],
            "retention_days": 365,
            "description": "Failed email sends",
        },
        "office.mail.bounced": {
            "record_kind": "OBSERVATION",  # External notification
            "partition_key": "message_id",
            "ordering_scope": "partition",
            "t_event_source": "bounced_at",
            "idempotency": "provider_dedup",
            "retention_days": 365,
            "description": "Email bounce notifications from provider",
        },
    }
