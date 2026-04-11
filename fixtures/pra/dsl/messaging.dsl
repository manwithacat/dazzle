# Parser Reference: Messaging Channels
# =============================================================================
#
# COVERAGE CHECKLIST:
#
# MESSAGE SCHEMA:
# - [x] message Name "Title":
# - [x] message Name: (no title)
# - [x] description (docstring style)
# - [x] field: type required
# - [x] field: type optional
# - [x] field: type = default
# - [x] field: simple types (email, str, uuid, bool, datetime, json, money)
# - [x] field: str(N) with length
# - [x] field: decimal(p,s) with precision
# - [x] field: list[Type]
# - [x] field: ref Entity
#
# CHANNEL BASICS:
# - [x] channel name "Title":
# - [x] kind: email
# - [x] kind: queue
# - [x] kind: stream
# - [x] provider: auto
# - [x] provider: specific (mailpit, sendgrid, etc.)
#
# CHANNEL CONFIG:
# - [x] config: block with key-value pairs
# - [x] provider_config: max_per_minute
# - [x] provider_config: max_concurrent
#
# SEND OPERATION:
# - [x] send name:
# - [x] message: MessageName
# - [x] when: entity EntityName created
# - [x] when: entity EntityName updated
# - [x] when: entity EntityName deleted
# - [x] when: entity EntityName status -> state
# - [x] when: entity EntityName.field changed
# - [x] when: entity EntityName field -> value
# - [x] when: service name called
# - [x] when: service name succeeded
# - [x] when: service name failed
# - [x] when: every duration
# - [x] when: cron "expression"
# - [x] delivery_mode: outbox
# - [x] delivery_mode: direct
# - [x] mapping: block with field -> path
# - [x] mapping: template strings with {{...}}
#
# THROTTLE CONFIG:
# - [x] throttle: block
# - [x] per_recipient: scope
# - [x] per_entity: scope
# - [x] per_channel: scope
# - [x] window: duration
# - [x] max_messages: number
# - [x] on_exceed: drop
# - [x] on_exceed: error
# - [x] on_exceed: log
#
# RECEIVE OPERATION:
# - [x] receive name:
# - [x] message: MessageName
# - [x] match: exact pattern
# - [x] match: prefix pattern (value*)
# - [x] match: suffix pattern (*value)
# - [x] match: contains pattern (*value*)
# - [x] match: regex(pattern)
# - [x] match: in("v1", "v2")
# - [x] action: create Entity
# - [x] action: update Entity
# - [x] action: upsert Entity on field
# - [x] action: call service Name
# - [x] mapping: source -> target
#
# ASSET:
# - [x] asset name:
# - [x] kind: file
# - [x] kind: image
# - [x] path: "..."
# - [x] description: "..."
#
# DOCUMENT:
# - [x] document name:
# - [x] for_entity: Entity
# - [x] format: pdf
# - [x] format: csv
# - [x] format: xlsx
# - [x] layout: layout_name
# - [x] description: "..."
#
# TEMPLATE:
# - [x] template name:
# - [x] subject: "..."
# - [x] body: "..."
# - [x] html_body: "..."
# - [x] attachments: block
# - [x] attachments: - asset: name
# - [x] attachments: - document: name
# - [x] attachments: entity: arg
# - [x] attachments: filename: "..."
#
# =============================================================================

module pra.messaging

use pra
use pra.entities
use pra.services

# =============================================================================
# MESSAGE: BASIC WITH TITLE
# =============================================================================

message OrderConfirmation "Order Confirmation Email":
  "Sent to customers when their order is confirmed"

  to: email required
  order_number: str(255) required
  customer_name: str(255) required
  items_count: int required
  subtotal: money required
  tax: money required
  total: money required
  estimated_delivery: date

# =============================================================================
# MESSAGE: WITHOUT TITLE
# =============================================================================

message WelcomeEmail:
  "Welcome message for new users"

  to: email required
  user_name: str(255) required
  activation_link: str(255) required
  expires_at: datetime

# =============================================================================
# MESSAGE: ALL FIELD TYPES
# =============================================================================

message FullFieldsMessage "All Field Types Demo":
  "Demonstrates all supported message field types"

  # Simple types
  recipient_email: email required
  unique_id: uuid required
  title: str(255) required
  description: str(500)
  is_priority: bool = false
  created_at: datetime required
  metadata: json

  # Numeric types
  quantity: int = 1
  price: decimal(10,2) required
  amount: money required

  # Complex types
  line_items: list[OrderItem] required
  customer: ref Customer required

# =============================================================================
# MESSAGE: OPTIONAL FIELDS AND DEFAULTS
# =============================================================================

message NotificationEmail:
  to: email required
  subject: str(255) required
  body: str(255) required
  cc: email optional
  bcc: email optional
  priority: str = "normal"
  track_opens: bool = false
  track_clicks: bool = false

# =============================================================================
# MESSAGE: FOR INBOUND
# =============================================================================

message InboundEmail:
  from_address: email required
  to_address: email required
  subject: str(255) required
  body_text: str(255) required
  body_html: str(255) optional
  received_at: datetime required

# =============================================================================
# MESSAGE: QUEUE MESSAGE
# =============================================================================

message TaskQueueMessage:
  "Task message for background processing queue"

  task_id: uuid required
  task_type: str(255) required
  payload: json required
  priority: int = 0
  retry_count: int = 0
  scheduled_at: datetime

# =============================================================================
# MESSAGE: STREAM EVENT
# =============================================================================

message AuditStreamEvent:
  "Audit event for event stream"

  event_id: uuid required
  event_type: str(255) required
  entity_type: str(255) required
  entity_id: uuid required
  actor_id: uuid required
  timestamp: datetime required
  changes: json
  metadata: json

# =============================================================================
# CHANNEL: EMAIL WITH AUTO PROVIDER
# =============================================================================

channel notifications "Notifications Channel":
  kind: email
  provider: auto

  config:
    from_address: "noreply@example.com"
    from_name: "Example App"
    reply_to: "support@example.com"

  send order_confirmation:
    message: OrderConfirmation
    when: entity Order status -> confirmed
    delivery_mode: outbox
    mapping:
      to -> Order.customer.email
      order_number -> Order.number
      customer_name -> Order.customer.name
      items_count -> Order.item_count
      subtotal -> Order.subtotal
      tax -> Order.tax
      total -> Order.total
      estimated_delivery -> Order.estimated_delivery

  send welcome_email:
    message: WelcomeEmail
    when: entity Employee created
    delivery_mode: outbox
    mapping:
      to -> Employee.email
      user_name -> Employee.first_name
      activation_link -> "https://app.example.com/activate/{{Employee.activation_token}}"

# =============================================================================
# CHANNEL: EMAIL WITH SPECIFIC PROVIDER
# =============================================================================

channel transactional "Transactional Emails":
  kind: email
  provider: sendgrid

  config:
    from_address: "orders@example.com"
    from_name: "Example Orders"

  provider_config:
    max_per_minute: 200
    max_concurrent: 20

  send shipping_notification:
    message: NotificationEmail
    when: entity Order status -> shipped
    delivery_mode: direct
    mapping:
      to -> Order.customer.email
      subject -> "Your order #{{Order.number}} has shipped!"
      body -> "Your order is on its way. Track it at: {{Order.tracking_url}}"

# =============================================================================
# CHANNEL: ALL TRIGGER TYPES
# =============================================================================

channel all_triggers "All Trigger Types Demo":
  kind: email
  provider: auto

  # Entity created trigger
  send on_created:
    message: NotificationEmail
    when: entity Task created
    mapping:
      to -> Task.assignee.email
      subject -> "New task assigned"
      body -> "You have been assigned: {{Task.title}}"

  # Entity updated trigger
  send on_updated:
    message: NotificationEmail
    when: entity Task updated
    mapping:
      to -> Task.assignee.email
      subject -> "Task updated"
      body -> "Task {{Task.title}} was updated"

  # Entity deleted trigger
  send on_deleted:
    message: NotificationEmail
    when: entity Task deleted
    mapping:
      to -> Task.creator.email
      subject -> "Task deleted"
      body -> "Task was deleted"

  # Status transition trigger
  send on_status_change:
    message: NotificationEmail
    when: entity Task status -> done
    mapping:
      to -> Task.assignee.email
      subject -> "Task completed"
      body -> "Task {{Task.title}} is now done"

  # Field changed trigger (with dot notation)
  send on_field_changed:
    message: NotificationEmail
    when: entity Task.priority changed
    mapping:
      to -> Task.assignee.email
      subject -> "Task priority changed"
      body -> "Priority updated for {{Task.title}}"

  # Field changed to specific value
  send on_priority_urgent:
    message: NotificationEmail
    when: entity Task priority -> urgent
    mapping:
      to -> Task.assignee.email
      subject -> "Urgent task!"
      body -> "{{Task.title}} is now urgent"

# =============================================================================
# CHANNEL: SERVICE TRIGGERS
# =============================================================================

channel service_events "Service Event Triggers":
  kind: email
  provider: auto

  send on_service_called:
    message: NotificationEmail
    when: service process_payment called
    mapping:
      to -> "monitoring@example.com"
      subject -> "Payment processing started"
      body -> "A payment processing request was initiated"

  send on_service_success:
    message: NotificationEmail
    when: service process_payment succeeded
    mapping:
      to -> "finance@example.com"
      subject -> "Payment processed successfully"
      body -> "Payment completed"

  send on_service_failure:
    message: NotificationEmail
    when: service process_payment failed
    mapping:
      to -> "alerts@example.com"
      subject -> "Payment processing failed!"
      body -> "Payment processing failed - please investigate"

# =============================================================================
# CHANNEL: SCHEDULE TRIGGERS
# =============================================================================

channel scheduled_emails "Scheduled Emails":
  kind: email
  provider: auto

  send hourly_digest:
    message: NotificationEmail
    when: every 1 hours
    mapping:
      to -> "digest@example.com"
      subject -> "Hourly Digest"
      body -> "Here is your hourly digest"

  send daily_report:
    message: NotificationEmail
    when: cron "0 9 * * *"
    mapping:
      to -> "reports@example.com"
      subject -> "Daily Report"
      body -> "Daily report is attached"

# =============================================================================
# CHANNEL: WITH THROTTLING
# =============================================================================

channel throttled_notifications "Throttled Notifications":
  kind: email
  provider: auto

  send per_recipient_throttled:
    message: NotificationEmail
    when: entity Task created
    delivery_mode: outbox
    mapping:
      to -> Task.assignee.email
      subject -> "New task"
      body -> "You have a new task"
    throttle:
      per_recipient:
        window: 1 hours
        max_messages: 10
        on_exceed: drop

  send per_entity_throttled:
    message: NotificationEmail
    when: entity Order updated
    delivery_mode: outbox
    mapping:
      to -> Order.customer.email
      subject -> "Order update"
      body -> "Your order was updated"
    throttle:
      per_entity:
        window: 30 minutes
        max_messages: 5
        on_exceed: log

  send per_channel_throttled:
    message: NotificationEmail
    when: entity Task status -> done
    delivery_mode: outbox
    mapping:
      to -> Task.assignee.email
      subject -> "Task done"
      body -> "Task completed"
    throttle:
      per_channel:
        window: 1 hours
        max_messages: 1000
        on_exceed: error

# =============================================================================
# CHANNEL: WITH RECEIVE OPERATIONS
# =============================================================================

channel support "Support Channel":
  kind: email
  provider: auto

  config:
    from_address: "support@example.com"

  receive support_ticket:
    message: InboundEmail
    match:
      to_address: "support@example.com"
    action: create SupportTicket
    mapping:
      from_address -> requester_email
      subject -> title
      body_text -> description

  receive sales_inquiry:
    message: InboundEmail
    match:
      to_address: "sales@example.com"
      subject: "Quote:*"
    action: create SalesLead
    mapping:
      from_address -> contact_email
      subject -> inquiry_subject
      body_text -> inquiry_body

  receive existing_customer:
    message: InboundEmail
    match:
      from_address: "*@enterprise.com"
    action: upsert Customer on email_address
    mapping:
      from_address -> email
      body_text -> last_message

# =============================================================================
# CHANNEL: MATCH PATTERNS
# =============================================================================

channel pattern_matching "Pattern Matching Demo":
  kind: email
  provider: auto

  # Exact match
  receive exact_match:
    message: InboundEmail
    match:
      to_address: "help@example.com"
    action: create SupportTicket
    mapping:
      from_address -> email
      subject -> title

  # Prefix match (value*)
  receive prefix_match:
    message: InboundEmail
    match:
      subject: "URGENT:*"
    action: create SupportTicket
    mapping:
      from_address -> email
      subject -> title

  # Suffix match (*value)
  receive suffix_match:
    message: InboundEmail
    match:
      subject: "*[Priority]"
    action: create SupportTicket
    mapping:
      from_address -> email
      subject -> title

  # Contains match (*value*)
  receive contains_match:
    message: InboundEmail
    match:
      subject: "*bug*"
    action: create SupportTicket
    mapping:
      from_address -> email
      subject -> title

  # Regex match
  receive regex_match:
    message: InboundEmail
    match:
      subject: regex("^\\[TICKET-[0-9]+\\]")
    action: update SupportTicket
    mapping:
      body_text -> latest_reply

  # In match
  receive in_match:
    message: InboundEmail
    match:
      to_address: in("support@example.com", "help@example.com", "tickets@example.com")
    action: create SupportTicket
    mapping:
      from_address -> email
      subject -> title

# =============================================================================
# CHANNEL: ALL RECEIVE ACTIONS
# =============================================================================

channel actions_demo "Receive Actions Demo":
  kind: email
  provider: auto

  receive action_create:
    message: InboundEmail
    match:
      to_address: "new@example.com"
    action: create Ticket
    mapping:
      from_address -> email
      subject -> title

  receive action_update:
    message: InboundEmail
    match:
      subject: "Re:*"
    action: update Ticket
    mapping:
      body_text -> latest_reply

  receive action_upsert:
    message: InboundEmail
    match:
      to_address: "contacts@example.com"
    action: upsert Contact on contact_email
    mapping:
      from_address -> email
      subject -> last_subject

  receive action_service:
    message: InboundEmail
    match:
      to_address: "process@example.com"
    action: call service process_inbound_email
    mapping:
      from_address -> sender
      subject -> subject
      body_text -> content

# =============================================================================
# CHANNEL: QUEUE
# =============================================================================

channel task_queue "Background Task Queue":
  kind: queue
  provider: auto

  config:
    dead_letter_after: 3
    visibility_timeout: 30

  provider_config:
    max_concurrent: 10

  send queue_task:
    message: TaskQueueMessage
    when: entity Task created
    delivery_mode: outbox
    mapping:
      task_id -> Task.id
      task_type -> "process_task"
      payload -> Task

# =============================================================================
# CHANNEL: STREAM
# =============================================================================

channel audit_stream "Audit Event Stream":
  kind: stream
  provider: auto

  config:
    retention_days: 30
    partition_field: entity_id

  send audit_event:
    message: AuditStreamEvent
    when: entity Task updated
    delivery_mode: outbox
    mapping:
      event_id -> Task.id
      event_type -> "task_updated"
      entity_type -> "Task"
      entity_id -> Task.id
      actor_id -> current_user.id
      timestamp -> current_timestamp
      changes -> Task.changes

# =============================================================================
# ASSET: FILE
# =============================================================================

asset terms_of_service:
  kind: file
  path: "legal/terms-of-service.pdf"

asset privacy_policy:
  kind: file
  path: "legal/privacy-policy.pdf"

# =============================================================================
# ASSET: IMAGE
# =============================================================================

asset company_logo:
  kind: image
  path: "branding/logo.png"

asset signature_image:
  kind: image
  path: "branding/email-signature.png"

# =============================================================================
# DOCUMENT: PDF
# =============================================================================

document invoice_pdf:
  for_entity: Invoice
  format: pdf
  layout: invoice_layout

document receipt_pdf:
  for_entity: Order
  format: pdf
  layout: receipt_layout

# =============================================================================
# DOCUMENT: CSV
# =============================================================================

document order_export_csv:
  for_entity: Order
  format: csv
  layout: order_export_layout

# =============================================================================
# DOCUMENT: XLSX
# =============================================================================

document monthly_report_xlsx:
  for_entity: Report
  format: xlsx
  layout: monthly_report_layout

# =============================================================================
# TEMPLATE: BASIC
# =============================================================================

template welcome_template:
  subject: "Welcome to {{app.name}}, {{user.name}}!"
  body: "Hi {{user.name}},\n\nWelcome to our platform!\n\nBest regards,\nThe Team"

# =============================================================================
# TEMPLATE: WITH HTML
# =============================================================================

template styled_welcome:
  subject: "Welcome to {{app.name}}"
  body: "Hi {{user.name}}, welcome to our platform!"
  html_body: "<html><body><h1>Welcome, {{user.name}}!</h1><p>Thanks for joining us.</p></body></html>"

# =============================================================================
# TEMPLATE: WITH ATTACHMENTS
# =============================================================================

template onboarding_email:
  subject: "Your account is ready!"
  body: "Welcome! Please review the attached documents."
  attachments:
    - asset: terms_of_service
      filename: "terms-of-service.pdf"
    - asset: privacy_policy
      filename: "privacy-policy.pdf"

# =============================================================================
# TEMPLATE: WITH DOCUMENT ATTACHMENT
# =============================================================================

template invoice_email:
  subject: "Invoice #{{invoice.number}} from {{app.name}}"
  body: "Please find your invoice attached."
  html_body: "<html><body><p>Invoice #{{invoice.number}} is attached.</p></body></html>"
  attachments:
    - document: invoice_pdf
      entity: invoice
      filename: "invoice-{{invoice.number}}.pdf"

# =============================================================================
# TEMPLATE: COMPLEX WITH MULTIPLE ATTACHMENTS
# =============================================================================

template order_complete_email:
  subject: "Order #{{order.number}} Complete!"
  body: "Your order is complete. Receipt and terms attached."
  html_body: "<html><body><h1>Order Complete!</h1><p>Order #{{order.number}} has been processed.</p></body></html>"
  attachments:
    - document: receipt_pdf
      entity: order
      filename: "receipt-{{order.number}}.pdf"
    - asset: terms_of_service
      filename: "terms.pdf"
    - asset: company_logo
      filename: "logo.png"
