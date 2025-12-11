# Messaging

DAZZLE v0.9 introduces a comprehensive messaging system for email, queues, and notifications.

## Overview

The messaging system consists of:
- **Messages**: Typed message schemas
- **Channels**: Communication pathways
- **Templates**: Reusable message templates
- **Assets**: Static file attachments
- **Documents**: Dynamic document generators

## Messages

Define typed message schemas:

```dsl
message MessageName "Display Title":
  "Optional description"
  field_name: type_name [required] [=default]
```

### Message Field Types

| Type | Description |
|------|-------------|
| `str` / `str(N)` | String (optionally bounded) |
| `email` | Email address |
| `uuid` | UUID identifier |
| `bool` | Boolean |
| `datetime` | Timestamp |
| `json` | JSON object |
| `list[Type]` | List of items |
| `ref Entity` | Reference to entity |

### Example

```dsl
message WelcomeEmail "Welcome Email":
  "Sent to new users after registration"
  to: email required
  user_name: str(100) required
  activation_link: str(500) required
  trial_end_date: date

message OrderConfirmation "Order Confirmation":
  to: email required
  order_number: str(20) required
  items: list[OrderItem] required
  subtotal: decimal(10,2) required
  tax: decimal(10,2) required
  total: decimal(10,2) required
  estimated_delivery: date

message InboundEmail "Inbound Email":
  from: email required
  to: email required
  subject: str(500)
  body: text
  attachments: json
```

## Channels

Channels define communication pathways:

```dsl
channel channel_name "Title":
  kind: email|queue|stream
  provider: auto|mailpit|sendgrid|ses|...

  config:
    option: "value"

  provider_config:
    max_per_minute: 100
    max_concurrent: 10

  send operation_name:
    # Send operation

  receive operation_name:
    # Receive operation
```

### Channel Kinds

| Kind | Description |
|------|-------------|
| `email` | Email messages |
| `queue` | Message queue (async) |
| `stream` | Event stream |

### Providers

| Provider | Kind | Description |
|----------|------|-------------|
| `auto` | email | Auto-detect (Mailpit in dev, configured in prod) |
| `mailpit` | email | Local development mail server |
| `sendgrid` | email | SendGrid email service |
| `ses` | email | AWS SES |
| `smtp` | email | Generic SMTP |

### Send Operations

Define outbound message operations:

```dsl
send operation_name:
  message: MessageName
  when: trigger
  delivery_mode: outbox|direct
  mapping:
    field -> source_path
  throttle:
    per_recipient:
      window: 1h
      max_messages: 5
      on_exceed: drop|queue|error
```

#### Send Triggers

| Trigger | Syntax | Description |
|---------|--------|-------------|
| Entity created | `entity Order created` | When entity is created |
| Entity updated | `entity Order updated` | When entity is updated |
| Entity deleted | `entity Order deleted` | When entity is deleted |
| Status transition | `entity Order status -> shipped` | When status changes to value |
| Field changed | `entity Order.priority changed` | When specific field changes |
| Service called | `service process_payment called` | When service is invoked |
| Service succeeded | `service process_payment succeeded` | When service succeeds |
| Service failed | `service process_payment failed` | When service fails |
| Schedule | `every 1h` | Periodic (1h, 30m, 1d) |
| Cron | `cron "0 9 * * *"` | Cron expression |

### Receive Operations

Define inbound message handling:

```dsl
receive operation_name:
  message: MessageName
  match:
    field: "pattern"
    field: regex("pattern")
    field: in("val1", "val2")
  action: create Entity | update Entity | upsert Entity on field | call service Name
  mapping:
    source_field -> target_field
```

### Complete Channel Example

```dsl
channel notifications "Email Notifications":
  kind: email
  provider: auto

  config:
    from_address: "noreply@example.com"
    from_name: "Example App"
    reply_to: "support@example.com"

  provider_config:
    max_per_minute: 60
    max_concurrent: 5

  # Send welcome email on user creation
  send welcome:
    message: WelcomeEmail
    when: entity User created
    delivery_mode: outbox
    mapping:
      to -> User.email
      user_name -> User.name
      activation_link -> "https://app.example.com/activate/{{User.activation_token}}"

  # Send order confirmation on order status change
  send order_confirmation:
    message: OrderConfirmation
    when: entity Order status -> confirmed
    delivery_mode: outbox
    mapping:
      to -> Order.customer.email
      order_number -> Order.order_number
      items -> Order.items
      subtotal -> Order.subtotal
      tax -> Order.tax
      total -> Order.total
    throttle:
      per_recipient:
        window: 24h
        max_messages: 10
        on_exceed: queue

  # Receive support emails
  receive support_ticket:
    message: InboundEmail
    match:
      to: "support@example.com"
    action: create SupportTicket
    mapping:
      from -> requester_email
      subject -> title
      body -> description
```

## Templates

Define reusable email templates:

```dsl
template template_name:
  subject: "Subject with {{variables}}"
  body: "Plain text body with {{variables}}"
  html_body: "<html>HTML body with {{variables}}</html>"
  attachments:
    - asset: asset_name
      filename: "attachment.pdf"
    - document: document_name
      entity: Order
      filename: "invoice_{{Order.number}}.pdf"
```

### Example

```dsl
template welcome_email:
  subject: "Welcome to {{app.name}}, {{user.name}}!"
  body: |
    Hi {{user.name}},

    Welcome to {{app.name}}! We're excited to have you.

    Your account has been created with email: {{user.email}}

    To get started, click here: {{activation_link}}

    Best regards,
    The {{app.name}} Team
  attachments:
    - asset: getting_started_guide
      filename: "getting-started.pdf"

template invoice_email:
  subject: "Invoice #{{invoice.number}} from {{company.name}}"
  body: |
    Dear {{customer.name}},

    Please find attached your invoice #{{invoice.number}}.

    Amount due: {{invoice.total}}
    Due date: {{invoice.due_date}}

    Thank you for your business.
  attachments:
    - document: invoice_pdf
      entity: Invoice
      filename: "invoice_{{invoice.number}}.pdf"
```

## Assets

Define static file attachments:

```dsl
asset asset_name:
  kind: file|image|pdf
  path: "relative/path/to/file.ext"
  description: "Description of the asset"
```

### Example

```dsl
asset terms_of_service:
  kind: pdf
  path: "assets/legal/terms-of-service.pdf"
  description: "Current Terms of Service document"

asset company_logo:
  kind: image
  path: "assets/images/logo.png"
  description: "Company logo for email headers"

asset getting_started_guide:
  kind: pdf
  path: "assets/docs/getting-started.pdf"
  description: "New user getting started guide"
```

## Documents

Define dynamic document generators:

```dsl
document document_name:
  for_entity: EntityName
  format: pdf|html|csv
  layout: layout_name
  description: "Description"
```

### Example

```dsl
document invoice_pdf:
  for_entity: Invoice
  format: pdf
  layout: invoice_layout
  description: "PDF invoice for customer"

document order_packing_slip:
  for_entity: Order
  format: pdf
  layout: packing_slip_layout
  description: "Packing slip for warehouse"

document monthly_report:
  for_entity: Report
  format: pdf
  layout: report_layout
  description: "Monthly summary report"
```

## Complete Messaging Example

```dsl
# Message schemas
message WelcomeEmail:
  to: email required
  user_name: str(100) required
  activation_link: str(500) required

message PasswordReset:
  to: email required
  reset_link: str(500) required
  expires_at: datetime required

message OrderShipped:
  to: email required
  order_number: str(20) required
  tracking_number: str(100)
  carrier: str(50)
  estimated_delivery: date

# Assets
asset logo:
  kind: image
  path: "assets/logo.png"

asset terms:
  kind: pdf
  path: "assets/terms.pdf"

# Documents
document invoice_pdf:
  for_entity: Invoice
  format: pdf
  layout: invoice_layout

# Templates
template welcome:
  subject: "Welcome to Our App!"
  body: |
    Hi {{user_name}},
    Click here to activate: {{activation_link}}
  attachments:
    - asset: terms
      filename: "terms-of-service.pdf"

# Channel with operations
channel transactional "Transactional Emails":
  kind: email
  provider: auto

  config:
    from_address: "noreply@app.com"

  send welcome:
    message: WelcomeEmail
    when: entity User created
    mapping:
      to -> User.email
      user_name -> User.name
      activation_link -> "https://app.com/activate/{{User.token}}"

  send password_reset:
    message: PasswordReset
    when: service request_password_reset succeeded
    mapping:
      to -> User.email
      reset_link -> "https://app.com/reset/{{reset_token}}"
      expires_at -> expiry_time

  send order_shipped:
    message: OrderShipped
    when: entity Order status -> shipped
    mapping:
      to -> Order.customer.email
      order_number -> Order.number
      tracking_number -> Order.tracking_number
      carrier -> Order.carrier
```
