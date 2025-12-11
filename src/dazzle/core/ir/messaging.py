"""
Messaging types for DAZZLE IR.

This module contains types for the v0.9.0 Messaging Channels feature:
- MessageSpec: Typed, reusable message schemas
- ChannelSpec: Communication pathways (email, queue, stream)
- SendOperationSpec: Outbound message operations with triggers
- ReceiveOperationSpec: Inbound message operations with actions

Design Documents:
- dev_docs/RFC-001-messaging-channels.md
- dev_docs/RFC-001-design-decisions.md
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Message Schemas
# ============================================================================


class MessageFieldSpec(BaseModel):
    """
    A field in a message schema.

    Attributes:
        name: Field name (snake_case)
        type_name: Type annotation (e.g., 'email', 'str', 'uuid', 'list[OrderItem]')
        required: Whether the field is required
        default: Optional default value
        description: Optional field description
    """

    name: str
    type_name: str
    required: bool = True
    default: str | None = None
    description: str | None = None

    model_config = ConfigDict(frozen=True)


class MessageSpec(BaseModel):
    """
    Specification for a message schema.

    Messages are typed, reusable structures that flow through channels.
    They support the same field types as entities, plus messaging-specific
    types like 'url', 'money', 'duration', and 'list[T]'.

    DSL syntax:
        message OrderConfirmation "Order Confirmation Email":
          '''Sent to customers when their order is confirmed'''
          to: email required
          order_number: str required
          items: list[OrderItem] required
          total: money required

    Attributes:
        name: Message identifier (PascalCase)
        title: Human-readable title
        description: Detailed description (from docstring)
        fields: List of message fields
    """

    name: str
    title: str | None = None
    description: str | None = None
    fields: list[MessageFieldSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


# ============================================================================
# Channel Kinds and Providers
# ============================================================================


class ChannelKind(str, Enum):
    """Types of messaging channels."""

    EMAIL = "email"  # Human-readable communication (SMTP, API)
    QUEUE = "queue"  # Reliable async processing (at-least-once)
    STREAM = "stream"  # Event sourcing, ordered log (replay support)


class DeliveryMode(str, Enum):
    """Message delivery modes."""

    OUTBOX = "outbox"  # Transactional: write to outbox in same transaction
    DIRECT = "direct"  # Fire-and-forget: no transactional guarantee


class ThrottleScope(str, Enum):
    """Scope for business throttling."""

    PER_RECIPIENT = "per_recipient"  # Limit per email/user
    PER_ENTITY = "per_entity"  # Limit per entity instance
    PER_CHANNEL = "per_channel"  # Limit across entire channel


class ThrottleExceedAction(str, Enum):
    """Action when throttle limit exceeded."""

    DROP = "drop"  # Silently drop the message
    ERROR = "error"  # Return business error to caller
    LOG = "log"  # Drop but log warning


# ============================================================================
# Throttle Configuration
# ============================================================================


class ThrottleSpec(BaseModel):
    """
    Business-level throttle configuration.

    DSL syntax:
        throttle:
          per_recipient:
            window: 1h
            max_messages: 5
            on_exceed: drop

    Attributes:
        scope: What to throttle by (per_recipient, per_entity, per_channel)
        window_seconds: Time window in seconds
        max_messages: Maximum messages in window
        on_exceed: Action when limit exceeded
    """

    scope: ThrottleScope
    window_seconds: int
    max_messages: int
    on_exceed: ThrottleExceedAction = ThrottleExceedAction.DROP

    model_config = ConfigDict(frozen=True)


# ============================================================================
# Send Operations (Outbound)
# ============================================================================


class EntityEvent(str, Enum):
    """Entity lifecycle events that can trigger sends."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


class SendTriggerKind(str, Enum):
    """Types of send triggers."""

    ENTITY_EVENT = "entity_event"  # When entity is created/updated/deleted
    ENTITY_FIELD_CHANGED = "entity_field_changed"  # When specific field changes
    ENTITY_STATUS_TRANSITION = "entity_status_transition"  # State machine transition
    SERVICE_CALLED = "service_called"  # When a service is invoked
    SERVICE_SUCCEEDED = "service_succeeded"  # When a service succeeds
    SERVICE_FAILED = "service_failed"  # When a service fails
    SCHEDULE = "schedule"  # Cron or interval trigger
    MANUAL = "manual"  # No automatic trigger


class SendTriggerSpec(BaseModel):
    """
    Specification for what triggers a send operation.

    DSL syntax:
        when: entity Order created
        when: entity Order status -> shipped
        when: service process_payment succeeded
        when: every 1h
        when: cron "0 9 * * *"

    Attributes:
        kind: Type of trigger
        entity_name: Entity name (for entity triggers)
        event: Entity event (created, updated, deleted)
        field_name: Field name (for field_changed triggers)
        field_value: Target value (for field_changed triggers)
        from_state: Source state (for status_transition triggers)
        to_state: Target state (for status_transition triggers)
        service_name: Service name (for service triggers)
        interval_seconds: Interval in seconds (for schedule triggers)
        cron_expression: Cron expression (for schedule triggers)
    """

    kind: SendTriggerKind
    entity_name: str | None = None
    event: EntityEvent | None = None
    field_name: str | None = None
    field_value: str | None = None
    from_state: str | None = None
    to_state: str | None = None
    service_name: str | None = None
    interval_seconds: int | None = None
    cron_expression: str | None = None

    model_config = ConfigDict(frozen=True)


class MappingSpec(BaseModel):
    """
    A field mapping from source to message field.

    DSL syntax:
        mapping:
          to -> Order.customer.email
          subject -> "Order #{{Order.number}} confirmed"
          order_number -> Order.number

    Attributes:
        target_field: Message field name
        source_path: Source field path or template string
        is_template: Whether source_path is a template string
    """

    target_field: str
    source_path: str
    is_template: bool = False

    model_config = ConfigDict(frozen=True)


class SendOperationSpec(BaseModel):
    """
    Specification for an outbound message operation.

    DSL syntax:
        send order_confirmation:
          message: OrderConfirmation
          when: entity Order status -> confirmed
          delivery_mode: outbox
          mapping:
            to -> Order.customer.email
            order_number -> Order.number
          throttle:
            per_recipient:
              window: 1h
              max_messages: 5

    Attributes:
        name: Operation identifier (snake_case)
        message_name: Reference to MessageSpec
        trigger: What triggers this send
        delivery_mode: Transactional (outbox) or fire-and-forget (direct)
        mappings: Field mappings from context to message
        throttle: Optional business-level throttling
        options: Provider-specific options (e.g., template, priority)
    """

    name: str
    message_name: str
    trigger: SendTriggerSpec | None = None
    delivery_mode: DeliveryMode = DeliveryMode.OUTBOX
    mappings: list[MappingSpec] = Field(default_factory=list)
    throttle: ThrottleSpec | None = None
    options: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


# ============================================================================
# Receive Operations (Inbound)
# ============================================================================


class MatchPatternKind(str, Enum):
    """Types of match patterns for filtering inbound messages."""

    EXACT = "exact"  # Exact string match
    PREFIX = "prefix"  # Starts with
    SUFFIX = "suffix"  # Ends with
    CONTAINS = "contains"  # Contains substring
    REGEX = "regex"  # Regular expression
    IN = "in"  # One of a list


class MatchPatternSpec(BaseModel):
    """
    A pattern for filtering inbound messages.

    DSL syntax:
        match:
          to: "support@{{app.domain}}"
          subject: "Help:*"

    Attributes:
        field_name: Message field to match against
        kind: Type of pattern matching
        value: Pattern value(s)
    """

    field_name: str
    kind: MatchPatternKind = MatchPatternKind.EXACT
    value: str | list[str] = ""

    model_config = ConfigDict(frozen=True)


class ReceiveActionKind(str, Enum):
    """Actions to perform when a message is received."""

    CREATE = "create"  # Create a new entity
    UPDATE = "update"  # Update an existing entity
    UPSERT = "upsert"  # Create or update based on match
    CALL_SERVICE = "call_service"  # Invoke a domain service


class ReceiveActionSpec(BaseModel):
    """
    Action to perform when a message is received.

    DSL syntax:
        action: create SupportTicket
        action: upsert Customer on email
        action: call service process_inbound_email

    Attributes:
        kind: Type of action
        entity_name: Target entity (for create/update/upsert)
        upsert_field: Field to match for upsert
        service_name: Service to call (for call_service)
    """

    kind: ReceiveActionKind
    entity_name: str | None = None
    upsert_field: str | None = None
    service_name: str | None = None

    model_config = ConfigDict(frozen=True)


class ReceiveMappingSpec(BaseModel):
    """
    A field mapping from message to entity/service input.

    DSL syntax:
        mapping:
          from -> requester_email
          subject -> title
          body -> description

    Attributes:
        source_field: Message field name
        target_field: Entity field or service input name
    """

    source_field: str
    target_field: str

    model_config = ConfigDict(frozen=True)


class ReceiveOperationSpec(BaseModel):
    """
    Specification for an inbound message operation.

    DSL syntax:
        receive support_ticket:
          message: InboundEmail
          match:
            to: "support@{{app.domain}}"
          action: create SupportTicket
          mapping:
            from -> requester_email
            subject -> title
            body -> description

    Attributes:
        name: Operation identifier (snake_case)
        message_name: Reference to MessageSpec (or built-in like InboundEmail)
        match_patterns: Filters for which messages to process
        action: What to do when message matches
        mappings: Field mappings from message to action target
        options: Provider-specific options
    """

    name: str
    message_name: str
    match_patterns: list[MatchPatternSpec] = Field(default_factory=list)
    action: ReceiveActionSpec | None = None
    mappings: list[ReceiveMappingSpec] = Field(default_factory=list)
    options: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


# ============================================================================
# Channel Specification
# ============================================================================


class ProviderConfigSpec(BaseModel):
    """
    Operational configuration for a channel provider.

    DSL syntax:
        provider_config:
          max_per_minute: 200
          max_concurrent: 10

    Attributes:
        max_per_minute: Rate limit (messages per minute)
        max_concurrent: Concurrency limit
        options: Additional provider-specific config
    """

    max_per_minute: int | None = None
    max_concurrent: int | None = None
    options: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class ChannelConfigSpec(BaseModel):
    """
    Channel-specific configuration.

    DSL syntax (email):
        config:
          from_address: "noreply@{{app.domain}}"
          from_name: "{{app.name}}"

    DSL syntax (queue):
        config:
          dead_letter_after: 3
          visibility_timeout: 30s

    DSL syntax (stream):
        config:
          retention: 7d
          partition_key: entity_id

    Attributes:
        options: Key-value configuration options
    """

    options: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class ChannelSpec(BaseModel):
    """
    Specification for a messaging channel.

    Channels define communication pathways with specific semantics.
    Three kinds are supported: email, queue, stream.

    DSL syntax:
        channel notifications:
          kind: email
          provider: auto

          config:
            from_address: "noreply@{{app.domain}}"

          send welcome:
            message: WelcomeEmail
            when: entity User created
            mapping:
              to -> User.email

          receive support:
            message: InboundEmail
            match:
              to: "support@{{app.domain}}"
            action: create SupportTicket

    Attributes:
        name: Channel identifier (snake_case)
        title: Human-readable title
        kind: Type of channel (email, queue, stream)
        provider: Provider name ('auto' for auto-detection)
        config: Channel-specific configuration
        provider_config: Operational provider limits
        send_operations: Outbound message operations
        receive_operations: Inbound message operations
    """

    name: str
    title: str | None = None
    kind: ChannelKind = ChannelKind.EMAIL
    provider: str = "auto"
    config: ChannelConfigSpec = Field(default_factory=ChannelConfigSpec)
    provider_config: ProviderConfigSpec | None = None
    send_operations: list[SendOperationSpec] = Field(default_factory=list)
    receive_operations: list[ReceiveOperationSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


# ============================================================================
# Asset and Document Specifications
# ============================================================================


class AssetKind(str, Enum):
    """Types of static assets."""

    FILE = "file"  # Generic file (PDF, etc.)
    IMAGE = "image"  # Image file (PNG, JPG, etc.)


class AssetSpec(BaseModel):
    """
    Specification for a static asset.

    DSL syntax:
        asset terms_of_service:
          kind: file
          path: "email/terms-of-service.pdf"
          description: "Current Terms of Service document"

    Attributes:
        name: Asset identifier (snake_case)
        kind: Type of asset
        path: Logical path within assets directory
        description: Optional description
    """

    name: str
    kind: AssetKind = AssetKind.FILE
    path: str = ""
    description: str | None = None

    model_config = ConfigDict(frozen=True)


class DocumentFormat(str, Enum):
    """Output formats for generated documents."""

    PDF = "pdf"
    CSV = "csv"
    XLSX = "xlsx"


class DocumentSpec(BaseModel):
    """
    Specification for a dynamically generated document.

    DSL syntax:
        document invoice_pdf:
          for_entity: Order
          format: pdf
          layout: invoice_layout
          description: "Invoice PDF for an order"

    Attributes:
        name: Document identifier (snake_case)
        for_entity: Entity this document is generated for
        format: Output format
        layout: Layout template name
        description: Optional description
    """

    name: str
    for_entity: str
    format: DocumentFormat = DocumentFormat.PDF
    layout: str = ""
    description: str | None = None

    model_config = ConfigDict(frozen=True)


# ============================================================================
# Template Specifications
# ============================================================================


class TemplateAttachmentSpec(BaseModel):
    """
    An attachment reference in an email template.

    DSL syntax:
        attachments:
          - asset: terms_of_service
            filename: "terms.pdf"
          - document: invoice_pdf
            entity: order
            filename: "invoice-{{order.number}}.pdf"

    Attributes:
        asset_name: Reference to AssetSpec (for static)
        document_name: Reference to DocumentSpec (for dynamic)
        entity_arg: Entity variable for document generation
        filename: Output filename (can be template)
    """

    asset_name: str | None = None
    document_name: str | None = None
    entity_arg: str | None = None
    filename: str = ""

    model_config = ConfigDict(frozen=True)


class TemplateSpec(BaseModel):
    """
    Specification for an email template.

    Templates use a restricted Jinja-ish syntax:
    - Variable lookup: {{ user.name }}
    - Dotted paths: {{ order.customer.email }}
    - Simple if: {% if user.is_premium %}...{% endif %}
    - No loops, filters, math, or function calls

    DSL syntax:
        template welcome_email:
          subject: "Welcome to {{app.name}}, {{user.display_name}}!"
          body: |
            Hi {{user.display_name}},

            Thanks for joining!

            {% if user.referrer %}
            You were referred by {{user.referrer.name}}.
            {% endif %}
          attachments:
            - asset: terms_of_service
              filename: "terms.pdf"

    Attributes:
        name: Template identifier (snake_case)
        subject: Subject line template
        body: Plain text body template
        html_body: Optional HTML body template
        attachments: List of attachments
    """

    name: str
    subject: str = ""
    body: str = ""
    html_body: str | None = None
    attachments: list[TemplateAttachmentSpec] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)
