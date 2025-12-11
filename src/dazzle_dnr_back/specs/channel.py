"""
ChannelSpec - Messaging channel specifications for BackendSpec.

Defines channel configurations that can be used with ChannelManager.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MessageFieldSpec(BaseModel):
    """Field specification for a message schema."""

    name: str = Field(description="Field name")
    type: str = Field(description="Field type (str, int, bool, etc.)")
    required: bool = Field(default=False, description="Whether the field is required")
    default: Any | None = Field(default=None, description="Default value")
    description: str | None = Field(default=None, description="Field description")

    model_config = ConfigDict(frozen=True)


class MessageSpec(BaseModel):
    """Message schema specification."""

    name: str = Field(description="Message type name")
    description: str | None = Field(default=None, description="Message description")
    fields: list[MessageFieldSpec] = Field(default_factory=list, description="Message fields")
    channel: str | None = Field(default=None, description="Associated channel name")

    model_config = ConfigDict(frozen=True)


class SendOperationSpec(BaseModel):
    """Send operation specification."""

    name: str = Field(description="Operation name")
    message: str = Field(description="Message type to send")
    template: str | None = Field(default=None, description="Template for rendering")
    subject_template: str | None = Field(default=None, description="Subject template (for email)")

    model_config = ConfigDict(frozen=True)


class ReceiveOperationSpec(BaseModel):
    """Receive operation specification (for queues/streams)."""

    name: str = Field(description="Operation name")
    message: str = Field(description="Message type to receive")
    handler: str | None = Field(default=None, description="Handler service name")

    model_config = ConfigDict(frozen=True)


class ChannelSpec(BaseModel):
    """
    Channel specification for messaging.

    Channels are the connection points for messaging - email, queues, or streams.
    They use auto-detection to find available providers.

    Example:
        ChannelSpec(
            name="notifications",
            kind="email",
            provider="auto",  # Will detect Mailpit, SendGrid, or file fallback
            send_operations=[
                SendOperationSpec(name="welcome", message="WelcomeEmail")
            ]
        )
    """

    name: str = Field(description="Channel name")
    kind: Literal["email", "queue", "stream"] = Field(description="Channel kind")
    provider: str = Field(default="auto", description="Provider name or 'auto' for detection")
    connection_url: str | None = Field(
        default=None, description="Explicit connection URL (overrides detection)"
    )
    send_operations: list[SendOperationSpec] = Field(
        default_factory=list, description="Operations for sending messages"
    )
    receive_operations: list[ReceiveOperationSpec] = Field(
        default_factory=list, description="Operations for receiving messages"
    )
    config: dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific configuration"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(frozen=True)
