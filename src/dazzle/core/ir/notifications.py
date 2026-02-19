"""
Notification types for DAZZLE IR (v0.34.0).

Defines notification rules that fire on entity events and route
messages to channels (in_app, email, sms, slack) with per-user
preference support.

DSL Syntax:

    notification invoice_overdue "Invoice Overdue":
      on: Invoice.status -> overdue
      channels: [in_app, email]
      message: "Invoice {{title}} is overdue"
      recipients: role(accountant)
      preferences: opt_out

    notification task_assigned "Task Assigned":
      on: Task.assigned_to changed
      channels: [in_app, email, slack]
      message: "You have been assigned {{title}}"
      recipients: field(assigned_to)
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class NotificationChannel(StrEnum):
    """Channels a notification can be sent through."""

    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    SLACK = "slack"


class NotificationPreference(StrEnum):
    """Per-user preference modes for notifications."""

    OPT_OUT = "opt_out"  # Enabled by default, user can disable
    OPT_IN = "opt_in"  # Disabled by default, user must enable
    MANDATORY = "mandatory"  # Cannot be disabled


class NotificationTrigger(BaseModel):
    """What triggers a notification.

    Attributes:
        entity: Entity name (e.g. "Invoice")
        event: Event type — "created", "deleted", or field/status change
        field: Field name for field_changed events (e.g. "status", "assigned_to")
        to_value: Optional target value for status transitions (e.g. "overdue")
    """

    entity: str
    event: str = "created"  # created | updated | deleted | field_changed | status_changed
    field: str | None = None
    to_value: str | None = None

    model_config = ConfigDict(frozen=True)


class NotificationRecipient(BaseModel):
    """Who receives a notification.

    Attributes:
        kind: How to resolve recipients — "role", "field", or "creator"
        value: Role name or field name (e.g. "accountant", "assigned_to")
    """

    kind: str = "role"  # role | field | creator
    value: str = ""

    model_config = ConfigDict(frozen=True)


class NotificationSpec(BaseModel):
    """
    A notification rule definition.

    Attributes:
        name: Notification identifier
        title: Human-readable title
        trigger: What entity event fires this notification
        channels: Channels to deliver through
        message: Template string with {{field}} interpolation
        recipients: Who receives the notification
        preference: Per-user preference mode
    """

    name: str
    title: str | None = None
    trigger: NotificationTrigger
    channels: list[NotificationChannel] = Field(
        default_factory=lambda: [NotificationChannel.IN_APP]
    )
    message: str = ""
    recipients: NotificationRecipient = Field(default_factory=NotificationRecipient)
    preference: NotificationPreference = NotificationPreference.OPT_OUT

    model_config = ConfigDict(frozen=True)
