"""
Unit tests for Messaging Channels parser (v0.9.0).

Tests parsing of message, channel, asset, document, and template constructs.
"""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import (
    ChannelKind,
    DeliveryMode,
    EntityEvent,
    MatchPatternKind,
    ReceiveActionKind,
    SendTriggerKind,
    ThrottleExceedAction,
    ThrottleScope,
)


class TestMessageParsing:
    """Tests for message construct parsing."""

    def test_basic_message(self):
        """Test parsing a basic message with required fields."""
        dsl = """
module test
app test "Test"

message WelcomeEmail "Welcome Email":
  to: email required
  subject: str required
  body: text required
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.messages) == 1
        msg = fragment.messages[0]
        assert msg.name == "WelcomeEmail"
        assert msg.title == "Welcome Email"
        assert len(msg.fields) == 3

        assert msg.fields[0].name == "to"
        assert msg.fields[0].type_name == "email"
        assert msg.fields[0].required is True

    def test_message_with_optional_fields(self):
        """Test message with optional fields and defaults."""
        dsl = """
module test
app test "Test"

message Notification:
  recipient: email required
  priority: str optional
  retry_count: int = 3
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        msg = fragment.messages[0]
        assert len(msg.fields) == 3

        assert msg.fields[1].name == "priority"
        assert msg.fields[1].required is False

        assert msg.fields[2].name == "retry_count"
        assert msg.fields[2].default == "3"

    def test_message_with_complex_types(self):
        """Test message with list, ref, and parameterized types."""
        dsl = """
module test
app test "Test"

message OrderDetails:
  items: list[OrderItem] required
  total: decimal(10,2) required
  notes: str(500) optional
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        msg = fragment.messages[0]
        assert msg.fields[0].type_name == "list[OrderItem]"
        assert msg.fields[1].type_name == "decimal(10,2)"
        assert msg.fields[2].type_name == "str(500)"


class TestChannelParsing:
    """Tests for channel construct parsing."""

    def test_basic_email_channel(self):
        """Test parsing a basic email channel."""
        dsl = """
module test
app test "Test"

channel notifications:
  kind: email
  provider: auto
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.channels) == 1
        ch = fragment.channels[0]
        assert ch.name == "notifications"
        assert ch.kind == ChannelKind.EMAIL
        assert ch.provider == "auto"

    def test_queue_channel(self):
        """Test parsing a queue channel."""
        dsl = """
module test
app test "Test"

channel tasks:
  kind: queue
  provider: rabbitmq
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        ch = fragment.channels[0]
        assert ch.kind == ChannelKind.QUEUE
        assert ch.provider == "rabbitmq"

    def test_stream_channel(self):
        """Test parsing a stream channel."""
        dsl = """
module test
app test "Test"

channel events:
  kind: stream
  provider: kafka
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        ch = fragment.channels[0]
        assert ch.kind == ChannelKind.STREAM
        assert ch.provider == "kafka"

    def test_channel_with_config(self):
        """Test channel with config block."""
        dsl = """
module test
app test "Test"

channel notifications:
  kind: email
  provider: auto

  config:
    from_address: "noreply@example.com"
    from_name: "My App"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        ch = fragment.channels[0]
        assert ch.config.options["from_address"] == "noreply@example.com"
        assert ch.config.options["from_name"] == "My App"

    def test_channel_with_provider_config(self):
        """Test channel with provider config."""
        dsl = """
module test
app test "Test"

channel notifications:
  kind: email
  provider: sendgrid

  provider_config:
    max_per_minute: 200
    max_concurrent: 10
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        ch = fragment.channels[0]
        assert ch.provider_config.max_per_minute == 200
        assert ch.provider_config.max_concurrent == 10


class TestSendOperationParsing:
    """Tests for send operation parsing."""

    def test_basic_send_operation(self):
        """Test parsing a basic send operation."""
        dsl = """
module test
app test "Test"

channel notifications:
  kind: email
  provider: auto

  send welcome:
    message: WelcomeEmail
    delivery_mode: outbox
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        ch = fragment.channels[0]
        assert len(ch.send_operations) == 1

        op = ch.send_operations[0]
        assert op.name == "welcome"
        assert op.message_name == "WelcomeEmail"
        assert op.delivery_mode == DeliveryMode.OUTBOX

    def test_send_with_entity_created_trigger(self):
        """Test send with entity created trigger."""
        dsl = """
module test
app test "Test"

channel notifications:
  kind: email
  provider: auto

  send welcome:
    message: WelcomeEmail
    when: entity User created
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        op = fragment.channels[0].send_operations[0]
        assert op.trigger.kind == SendTriggerKind.ENTITY_EVENT
        assert op.trigger.entity_name == "User"
        assert op.trigger.event == EntityEvent.CREATED

    def test_send_with_status_transition_trigger(self):
        """Test send with status transition trigger."""
        dsl = """
module test
app test "Test"

channel notifications:
  kind: email
  provider: auto

  send order_shipped:
    message: ShippingNotification
    when: entity Order status -> shipped
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        op = fragment.channels[0].send_operations[0]
        assert op.trigger.kind == SendTriggerKind.ENTITY_STATUS_TRANSITION
        assert op.trigger.entity_name == "Order"
        assert op.trigger.to_state == "shipped"

    def test_send_with_mappings(self):
        """Test send with field mappings."""
        dsl = """
module test
app test "Test"

channel notifications:
  kind: email
  provider: auto

  send welcome:
    message: WelcomeEmail
    when: entity User created
    mapping:
      to -> User.email
      name -> User.display_name
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        op = fragment.channels[0].send_operations[0]
        assert len(op.mappings) == 2
        assert op.mappings[0].target_field == "to"
        assert op.mappings[0].source_path == "User.email"
        assert op.mappings[1].target_field == "name"
        assert op.mappings[1].source_path == "User.display_name"

    def test_send_with_throttle(self):
        """Test send with throttle configuration."""
        dsl = """
module test
app test "Test"

channel notifications:
  kind: email
  provider: auto

  send password_reset:
    message: PasswordResetEmail
    when: service request_reset called
    throttle:
      per_recipient:
        window: 1 hours
        max_messages: 5
        on_exceed: drop
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        op = fragment.channels[0].send_operations[0]
        assert op.throttle is not None
        assert op.throttle.scope == ThrottleScope.PER_RECIPIENT
        assert op.throttle.window_seconds == 3600  # 1 hour
        assert op.throttle.max_messages == 5
        assert op.throttle.on_exceed == ThrottleExceedAction.DROP

    def test_send_with_direct_delivery_mode(self):
        """Test send with direct delivery mode."""
        dsl = """
module test
app test "Test"

channel analytics:
  kind: stream
  provider: auto

  send page_view:
    message: PageViewEvent
    delivery_mode: direct
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        op = fragment.channels[0].send_operations[0]
        assert op.delivery_mode == DeliveryMode.DIRECT


class TestReceiveOperationParsing:
    """Tests for receive operation parsing."""

    def test_basic_receive_operation(self):
        """Test parsing a basic receive operation."""
        dsl = """
module test
app test "Test"

channel notifications:
  kind: email
  provider: auto

  receive support_ticket:
    message: InboundEmail
    action: create SupportTicket
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        ch = fragment.channels[0]
        assert len(ch.receive_operations) == 1

        op = ch.receive_operations[0]
        assert op.name == "support_ticket"
        assert op.message_name == "InboundEmail"
        assert op.action.kind == ReceiveActionKind.CREATE
        assert op.action.entity_name == "SupportTicket"

    def test_receive_with_match_patterns(self):
        """Test receive with match patterns."""
        dsl = """
module test
app test "Test"

channel notifications:
  kind: email
  provider: auto

  receive support:
    message: InboundEmail
    match:
      to: "support@example.com"
      subject: "Help:*"
    action: create SupportTicket
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        op = fragment.channels[0].receive_operations[0]
        assert len(op.match_patterns) == 2

        assert op.match_patterns[0].field_name == "to"
        assert op.match_patterns[0].kind == MatchPatternKind.EXACT
        assert op.match_patterns[0].value == "support@example.com"

        assert op.match_patterns[1].field_name == "subject"
        assert op.match_patterns[1].kind == MatchPatternKind.PREFIX
        assert op.match_patterns[1].value == "Help:"

    def test_receive_with_mappings(self):
        """Test receive with field mappings."""
        dsl = """
module test
app test "Test"

channel notifications:
  kind: email
  provider: auto

  receive support:
    message: InboundEmail
    action: create SupportTicket
    mapping:
      from_addr -> requester_email
      subject -> title
      body -> description
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        op = fragment.channels[0].receive_operations[0]
        assert len(op.mappings) == 3
        assert op.mappings[0].source_field == "from_addr"
        assert op.mappings[0].target_field == "requester_email"

    def test_receive_with_upsert_action(self):
        """Test receive with upsert action."""
        dsl = """
module test
app test "Test"

channel events:
  kind: queue
  provider: auto

  receive customer_update:
    message: CustomerEvent
    action: upsert Customer on external_id
    mapping:
      customer_id -> external_id
      name -> display_name
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        op = fragment.channels[0].receive_operations[0]
        assert op.action.kind == ReceiveActionKind.UPSERT
        assert op.action.entity_name == "Customer"
        assert op.action.upsert_field == "external_id"

    def test_receive_with_call_service_action(self):
        """Test receive with call service action."""
        dsl = """
module test
app test "Test"

channel events:
  kind: queue
  provider: auto

  receive process_payment:
    message: PaymentEvent
    action: call service process_payment
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        op = fragment.channels[0].receive_operations[0]
        assert op.action.kind == ReceiveActionKind.CALL_SERVICE
        assert op.action.service_name == "process_payment"


class TestAssetParsing:
    """Tests for asset construct parsing."""

    def test_basic_asset(self):
        """Test parsing a basic asset."""
        dsl = """
module test
app test "Test"

asset terms_of_service:
  kind: file
  path: "legal/terms.pdf"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.assets) == 1
        asset = fragment.assets[0]
        assert asset.name == "terms_of_service"
        assert asset.kind.value == "file"
        assert asset.path == "legal/terms.pdf"

    def test_image_asset(self):
        """Test parsing an image asset."""
        dsl = """
module test
app test "Test"

asset company_logo:
  kind: image
  path: "branding/logo.png"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        asset = fragment.assets[0]
        assert asset.kind.value == "image"


class TestDocumentParsing:
    """Tests for document construct parsing."""

    def test_basic_document(self):
        """Test parsing a basic document."""
        dsl = """
module test
app test "Test"

document invoice_pdf:
  for_entity: Order
  format: pdf
  layout: invoice_layout
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.documents) == 1
        doc = fragment.documents[0]
        assert doc.name == "invoice_pdf"
        assert doc.for_entity == "Order"
        assert doc.format.value == "pdf"
        assert doc.layout == "invoice_layout"


class TestTemplateParsing:
    """Tests for template construct parsing."""

    def test_basic_template(self):
        """Test parsing a basic template."""
        dsl = """
module test
app test "Test"

template welcome_email:
  subject: "Welcome to our app"
  body: "Hello, thanks for signing up!"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        assert len(fragment.templates) == 1
        tpl = fragment.templates[0]
        assert tpl.name == "welcome_email"
        assert tpl.subject == "Welcome to our app"
        assert tpl.body == "Hello, thanks for signing up!"

    def test_template_with_html_body(self):
        """Test template with HTML body."""
        dsl = """
module test
app test "Test"

template welcome_email:
  subject: "Welcome"
  body: "Plain text version"
  html_body: "<h1>Welcome</h1><p>HTML version</p>"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        tpl = fragment.templates[0]
        assert tpl.html_body == "<h1>Welcome</h1><p>HTML version</p>"


class TestComprehensiveParsing:
    """Tests for comprehensive messaging DSL."""

    def test_full_messaging_spec(self):
        """Test parsing a complete messaging specification."""
        dsl = """
module ecommerce.messaging
app shop "Online Shop"

message OrderConfirmation:
  to: email required
  order_number: str required
  items: json required
  total: decimal(10,2) required

message InboundEmail:
  from_addr: email required
  to: email required
  subject: str required
  body: text required

asset terms_pdf:
  kind: file
  path: "legal/terms.pdf"

document invoice:
  for_entity: Order
  format: pdf
  layout: invoice

template order_confirmation:
  subject: "Order Confirmation"
  body: "Thank you for your order!"

channel notifications:
  kind: email
  provider: auto

  config:
    from_address: "orders@shop.com"

  send order_confirmed:
    message: OrderConfirmation
    when: entity Order status -> confirmed
    delivery_mode: outbox
    mapping:
      to -> Order.customer.email
      order_number -> Order.number

  receive returns:
    message: InboundEmail
    match:
      to: "returns@shop.com"
    action: create ReturnRequest
    mapping:
      from_addr -> customer_email
      subject -> reason

channel order_events:
  kind: stream
  provider: auto

  send order_placed:
    message: OrderConfirmation
    when: entity Order created
    delivery_mode: direct
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        # Verify all constructs parsed
        assert len(fragment.messages) == 2
        assert len(fragment.assets) == 1
        assert len(fragment.documents) == 1
        assert len(fragment.templates) == 1
        assert len(fragment.channels) == 2

        # Verify email channel
        email_ch = fragment.channels[0]
        assert email_ch.name == "notifications"
        assert email_ch.kind == ChannelKind.EMAIL
        assert len(email_ch.send_operations) == 1
        assert len(email_ch.receive_operations) == 1

        # Verify stream channel
        stream_ch = fragment.channels[1]
        assert stream_ch.name == "order_events"
        assert stream_ch.kind == ChannelKind.STREAM
        assert len(stream_ch.send_operations) == 1
        assert stream_ch.send_operations[0].delivery_mode == DeliveryMode.DIRECT
