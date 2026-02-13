"""
Webhook types for DAZZLE IR.

Outbound HTTP notifications triggered by entity events.

DSL Syntax (v0.25.0):

    webhook OrderNotification "Order Status Webhook":
      entity: Order
      events: [created, updated, deleted]
      url: config("ORDER_WEBHOOK_URL")
      auth:
        method: hmac_sha256
        secret: config("WEBHOOK_SECRET")
      payload:
        include: [id, status, total, customer.name]
        format: json
      retry:
        max_attempts: 3
        backoff: exponential
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class WebhookEvent(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


class WebhookAuthMethod(StrEnum):
    HMAC_SHA256 = "hmac_sha256"
    BEARER = "bearer"
    BASIC = "basic"


class WebhookAuthSpec(BaseModel):
    """Authentication configuration for a webhook."""

    method: WebhookAuthMethod = WebhookAuthMethod.HMAC_SHA256
    secret_ref: str | None = None

    model_config = ConfigDict(frozen=True)


class WebhookPayloadSpec(BaseModel):
    """Payload configuration for a webhook."""

    include_fields: list[str] = Field(default_factory=list)
    format: str = "json"

    model_config = ConfigDict(frozen=True)


class WebhookRetrySpec(BaseModel):
    """Retry configuration for a webhook."""

    max_attempts: int = 3
    backoff: str = "exponential"

    model_config = ConfigDict(frozen=True)


class WebhookSpec(BaseModel):
    """
    A webhook definition for outbound HTTP notifications.

    Attributes:
        name: Webhook identifier
        title: Human-readable title
        entity: Entity that triggers the webhook
        events: List of entity events that fire the webhook
        url: Target URL (may be a config() reference)
        auth: Authentication configuration
        payload: Payload field selection and format
        retry: Retry policy
    """

    name: str
    title: str | None = None
    entity: str = ""
    events: list[WebhookEvent] = Field(default_factory=list)
    url: str = ""
    auth: WebhookAuthSpec | None = None
    payload: WebhookPayloadSpec | None = None
    retry: WebhookRetrySpec | None = None

    model_config = ConfigDict(frozen=True)
