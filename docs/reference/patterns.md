# Patterns

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

Patterns are reusable DSL recipes that combine multiple constructs into proven solutions. Each pattern includes a complete, copy-paste-ready example demonstrating how entities, surfaces, workspaces, and services work together for common use cases.

---

## Adapter Result

Result type for adapter operations using success/failure pattern instead of exceptions for expected errors.

### Syntax

```dsl
AdapterResult[T] = Success with data or Failure with error

result = await adapter.get_data(id)
if result.is_success:
    data = result.data  # Access the data
else:
    error = result.error  # Handle the error
```

### Example

```dsl
async def fetch_customer_data(customer_id: str):
    result = await crm_adapter.get_customer(customer_id)

    if result.is_success:
        return result.data

    # Handle specific error types
    if result.error.status_code == 404:
        return None  # Customer not found

    # Re-raise unexpected errors
    raise result.error

# Or use unwrap_or for defaults:
data = result.unwrap_or(default_data)

# Or map the result:
names = result.map(lambda data: data["name"])
```

**Related:** [External Adapter](patterns.md#external-adapter), [Error Normalization](patterns.md#error-normalization)

---

## Audit Trail

Track who changed what and when

### Example

```dsl
# Entity with full audit fields
entity Document "Document":
  id: uuid pk
  title: str(200) required
  content: text
  # Audit fields
  created_by: ref User required
  created_at: datetime auto_add
  updated_by: ref User optional
  updated_at: datetime auto_update
  version: int=1

surface document_history "Document History":
  uses entity Document
  mode: view
  section main:
    field title
    field version
  # `audit` is a reserved keyword — pick another section name.
  section history "Audit Trail":
    field created_by "Created By"
    field created_at "Created At"
    field updated_by "Last Updated By"
    field updated_at "Last Updated At"
```

---

## Business Logic Pattern

Complete entity with state machine, invariants, computed fields, and access rules

### Example

```dsl
# Complete v0.7.0 Entity with Business Logic
entity Ticket "Support Ticket":
  id: uuid pk
  ticket_number: str(20) unique
  title: str(200) required
  description: text required
  status: enum[open,in_progress,resolved,closed]=open
  priority: enum[low,medium,high,critical]=medium
  created_by: ref User required
  assigned_to: ref User
  resolution: text
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Computed field: days since opened
  days_open: computed days_since(created_at)

  # State machine: ticket lifecycle
  transitions:
    open -> in_progress: requires assigned_to
    in_progress -> resolved: requires resolution
    in_progress -> open
    resolved -> closed
    resolved -> in_progress
    closed -> open: role(manager)

  # Invariants: data integrity rules
  # IMPORTANT: Use single = for equality (not ==)
  invariant: status != resolved or resolution != null
  invariant: status != closed or resolution != null
  invariant: priority != critical or assigned_to != null

  # Access rules: visibility and permissions
  access:
    read: created_by = current_user or role(agent) or role(manager)
    write: role(agent) or role(manager)

  # Indexes for performance
  index status, priority
  index assigned_to
```

**Related:** [State Machine](entities.md#state-machine), [Invariant](entities.md#invariant), [Computed Field](entities.md#computed-field), [Access Rules](access-control.md#access-rules)

---

## Cedar Rbac

Role-based entity access using permit/forbid/audit blocks with NIST SP 800-162 alignment. Supports separation of duty, least privilege, default-deny, and audit trail requirements.

### Example

```dsl
# Cedar-style RBAC for a medical clinic
entity Prescription "Prescription":
  id: uuid pk
  patient: ref Patient required
  prescriber: ref Doctor required
  medication: str(200) required
  dosage: str(100) required
  status: enum[draft,active,dispensed,cancelled]=draft

  # Permit: who CAN perform actions. Operations are the fixed CRUD verbs
  # (create/read/update/delete/list); domain actions map onto them:
  # prescribe -> create, dispense -> update, cancel -> delete.
  permit:
    read: role(doctor) or role(pharmacist) or role(nurse)
    create: role(doctor)
    update: role(pharmacist)
    delete: role(doctor) or role(pharmacist)

  # Forbid: separation of duty overrides (FORBID > PERMIT > deny)
  forbid:
    create: role(pharmacist)
    update: role(doctor)

  # Audit: compliance logging — directive form (`all`, boolean, or an
  # operation list like `[create, update, delete]`)
  audit: all

  transitions:
    draft -> active: role(doctor)
    active -> dispensed: role(pharmacist)
    active -> cancelled: role(doctor) or role(pharmacist)
```

**Related:** [Access Rules](access-control.md#access-rules), [Role Based Access](patterns.md#role-based-access), [Business Logic Pattern](patterns.md#business-logic-pattern), [Rbac Validation](testing.md#rbac-validation)

---

## Crud

Complete create-read-update-delete interface for an entity

### Example

```dsl
# Complete CRUD for Task entity
entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text optional
  status: enum[todo,in_progress,done]=todo
  created_at: datetime auto_add

surface task_list "Tasks":
  uses entity Task
  mode: list
  section main:
    field title
    field status
  ux:
    purpose: "View and manage all tasks"
    sort: created_at desc
    filter: status

surface task_detail "Task Details":
  uses entity Task
  mode: view
  section main:
    field title
    field description
    field status
    field created_at

surface task_create "New Task":
  uses entity Task
  mode: create
  section main:
    field title
    field description

surface task_edit "Edit Task":
  uses entity Task
  mode: edit
  section main:
    field title
    field description
    field status
```

---

## Dashboard

Workspace aggregating multiple data views with metrics

### Example

```dsl
# Team dashboard with metrics and activity
workspace team_dashboard "Team Dashboard":
  purpose: "Real-time team overview and key metrics"

  # Urgent items needing attention
  urgent_items:
    source: Task
    filter: priority = high and status != done
    sort: due_date asc
    limit: 5
    action: task_edit
    empty: "All caught up!"

  # Recent completions
  recent_done:
    source: Task
    filter: status = done
    sort: completed_at desc
    limit: 10
    display: timeline

  # Key performance metrics — each metric is one aggregate call
  # (count/sum/avg/min/max, optionally with a `where` filter), or a
  # derived expression over metrics declared earlier in the block
  # (#1359): arithmetic + round/abs/nullif/coalesce, evaluated after
  # the scope-filtered queries (division by zero reads as 0).
  metrics:
    aggregate:
      total: count(Task)
      completed: count(Task where status = done)
      in_progress: count(Task where status = in_progress)
      completion_rate: round(completed / total * 100)
```

---

## Direct One To Many

The foundational relational shape. A parent entity has many children; each
child carries a `ref Parent` field. Reach for this *first* — it's the default
relational expression in Dazzle and underpins almost every other pattern.

Authors sometimes flatten into a `json[]` list on the parent or embed
entity-shaped data inline. Resist that: the relational shape composes with
scope rules, surfaces, aggregates, FK validation, and lifecycle in ways
JSON arrays can't.

### Example

```dsl
entity Order "Order":
  id: uuid pk
  customer: ref Customer required
  placed_at: datetime auto_add

entity LineItem "Line Item":
  id: uuid pk
  order: ref Order required        # 1:N parent FK — the canonical shape
  product_name: str(200) required
  quantity: int required
  unit_price: decimal(10,2) required

# Surfaces compose naturally — list LineItem rows for one Order via filter,
# aggregate via primary_aggregate: (see #1242), or scope via the FK chain.
surface order_lines "Order Lines":
  uses entity LineItem
  mode: list
  section main:
    field order "Order"
    field product_name "Product"
    field quantity "Qty"
```

**Related:** [Primary Aggregate N To One](patterns.md#primary-aggregate-n-to-one), [Junction Many To Many](patterns.md#junction-many-to-many), [Subtype Of](patterns.md#subtype-of)

---

## Domain Service Pattern

Custom business logic with DSL declaration and stub implementation

### Example

```dsl
# DSL declaration in app.dsl
entity Invoice "Invoice":
  id: uuid pk
  total: decimal(10,2) required
  country: str(2) required
  vat_amount: decimal(10,2) optional

service calculate_vat "Calculate VAT for Invoice":
  kind: domain_logic
  input:
    invoice_id: uuid required
    country_code: str(2)
  output:
    vat_amount: decimal(10,2)
    breakdown: json
  guarantees:
    - "Must not mutate the invoice record"
    - "Must raise domain error if config incomplete"
  stub: python

# Generate stub file:
# $ dazzle stubs generate --service calculate_vat

# Implement in stubs/calculate_vat.py:
def calculate_vat(invoice_id: str, country_code: str | None = None) -> CalculateVatResult:
    invoice = db.get_invoice(invoice_id)
    country = country_code or invoice.country

    # VAT rates by country
    rates = {"GB": 0.20, "DE": 0.19, "FR": 0.20, "US": 0.0}
    rate = rates.get(country, 0.0)

    return {
        "vat_amount": float(invoice.total) * rate,
        "breakdown": {
            "rate": rate,
            "country": country,
            "net": float(invoice.total),
            "gross": float(invoice.total) * (1 + rate)
        }
    }
```

---

## Ejection Pattern

Generate standalone application code from DAZZLE specification for custom deployment

### Example

```dsl
# Step 1: Add ejection configuration to dazzle.toml
[ejection]
enabled = true

[ejection.backend]
framework = "fastapi"
models = "sqlalchemy"
async_handlers = true

[ejection.frontend]
framework = "react"
api_client = "tanstack_query"

[ejection.testing]
contract = "schemathesis"
unit = "pytest"

[ejection.ci]
template = "github_actions"

[ejection.output]
directory = "generated"


# Step 2: Run the generated application
cd generated
docker compose -f docker-compose.dev.yml up

# Step 3: Run the generated tests
cd generated
pytest tests/

# Optional: Generate OpenAPI spec
dazzle specs openapi -o openapi.yaml

# Generated file structure:
generated/
├── README.md
├── docker-compose.yml
├── docker-compose.dev.yml
├── Makefile
├── .gitignore
├── backend/
│   ├── main.py
│   ├── models/
│   │   └── {entity}.py
│   ├── schemas/
│   │   └── {entity}.py
│   ├── routes/
│   │   └── {entity}.py
│   ├── guards/
│   │   └── {entity}_guards.py
│   ├── validators/
│   │   └── {entity}_validators.py
│   └── access/
│       └── {entity}_access.py
├── frontend/
│   └── src/
│       ├── types/
│       ├── schemas/
│       ├── hooks/
│       └── components/
├── tests/
│   ├── conftest.py
│   ├── contract/
│   └── unit/
└── .github/
    └── workflows/
        ├── ci.yml
        ├── contract.yml
        └── deploy.yml
```

**Related:** Ejection, Ejection Config, Ejection Adapter, Openapi Generation

---

## Enterprise Sso

Per-org enterprise SSO via OIDC connections — an opt-in capability. Connections are runtime data (dazzle auth connection ...), fenced per org and gated by domain verification. SAML and SCIM are sibling capabilities (auth.enterprise.saml / .scim).

### Syntax

```dsl
# 1. Opt in (declares the capability + prints the runbook):
dazzle capability enable auth.enterprise.oidc
# 2. Create a per-org connection (runtime data, not DSL):
dazzle auth connection create --tenant <org> --issuer <url> \
    --client-id <id> --client-secret <secret>
# 3. Verify the org's email domain (DNS-TXT), then sign in at /auth/enterprise/login.
```

### Example

```dsl
# dazzle.toml
[capabilities]
enabled = ["auth.enterprise.oidc"]

# Per org (CLI, runtime — secrets never in DSL):
$ dazzle auth connection create --tenant acme --issuer https://acme.okta.com \
    --client-id ... --client-secret ...
$ dazzle auth connection add-domain <id> acme.com   # publish the printed TXT record
$ dazzle auth connection verify-domain <id> acme.com
```

---

## Error Category

High-level error categories for routing and handling decisions in the GraphQL layer.

### Syntax

```dsl
ErrorCategory.AUTHENTICATION  # Redirect to login
ErrorCategory.AUTHORIZATION   # Show forbidden message
ErrorCategory.VALIDATION      # Show field-level errors
ErrorCategory.RATE_LIMIT      # Implement backoff
ErrorCategory.TIMEOUT         # Retry or show timeout
ErrorCategory.NOT_FOUND       # Show 404 message
ErrorCategory.EXTERNAL_SERVICE # Show service unavailable
ErrorCategory.INTERNAL        # Log and show generic error
```

### Example

```dsl
# Use categories to route error handling:
def handle_adapter_error(normalized: NormalizedError):
    match normalized.category:
        case ErrorCategory.AUTHENTICATION:
            return redirect_to_login()
        case ErrorCategory.RATE_LIMIT:
            return show_retry_message(normalized.retry_after)
        case ErrorCategory.VALIDATION:
            return show_field_errors(normalized.field_errors)
        case _:
            return show_generic_error(normalized.user_message)
```

**Related:** [Error Normalization](patterns.md#error-normalization), [Error Severity](patterns.md#error-severity)

---

## Error Normalization

System for converting diverse external API errors into a consistent format for GraphQL responses.

### Syntax

```dsl
from dazzle.http.graphql.adapters import (
    normalize_error,
    NormalizedError,
    ErrorCategory,
    ErrorSeverity,
)

normalized = normalize_error(error, service_name="hmrc")
```

### Example

```dsl
from dazzle.http.graphql.adapters import (
    normalize_error,
    ErrorCategory,
    ErrorSeverity,
)

try:
    result = await hmrc_adapter.get_vat_obligations(vrn)
except AdapterError as e:
    normalized = normalize_error(e, request_id="req-123")

    # Access normalized error properties
    print(normalized.code)           # "HMRC_RATE_LIMIT_EXCEEDED"
    print(normalized.category)       # ErrorCategory.RATE_LIMIT
    print(normalized.severity)       # ErrorSeverity.WARNING
    print(normalized.user_message)   # "Too many requests. Please try again in 30 seconds."
    print(normalized.retry_after)    # 30.0

    # Convert to GraphQL error extensions
    extensions = normalized.to_graphql_extensions()
    raise GraphQLError(normalized.user_message, extensions=extensions)
```

**Related:** [External Adapter](patterns.md#external-adapter), [Adapter Result](patterns.md#adapter-result), [Error Category](patterns.md#error-category)

---

## Error Severity

Error severity levels for logging and alerting decisions.

### Syntax

```dsl
ErrorSeverity.INFO      # Expected errors (validation, not found)
ErrorSeverity.WARNING   # Recoverable errors (rate limits, timeouts)
ErrorSeverity.ERROR     # Unexpected errors needing attention
ErrorSeverity.CRITICAL  # System errors requiring immediate action
```

### Example

```dsl
# Log based on severity:
def log_error(normalized: NormalizedError):
    log_data = normalized.to_log_dict()

    match normalized.severity:
        case ErrorSeverity.INFO:
            logger.info("Expected error", extra=log_data)
        case ErrorSeverity.WARNING:
            logger.warning("Recoverable error", extra=log_data)
        case ErrorSeverity.ERROR:
            logger.error("Unexpected error", extra=log_data)
        case ErrorSeverity.CRITICAL:
            logger.critical("System error", extra=log_data)
            alert_on_call_team(normalized)
```

**Related:** [Error Normalization](patterns.md#error-normalization), [Error Category](patterns.md#error-category)

---

## External Adapter

Abstract base class for integrating with external APIs (HMRC, banks, payment providers, etc.) with built-in retry logic, rate limiting, and error normalization.

### Syntax

```dsl
from dazzle.http.graphql.adapters import (
    BaseExternalAdapter,
    AdapterConfig,
    AdapterResult,
)

class MyServiceAdapter(BaseExternalAdapter[AdapterConfig]):
    async def get_data(self, id: str) -> AdapterResult[dict]:
        return await self._get(f"/api/data/{id}")
```

### Example

```dsl
from dazzle.http.graphql.adapters import (
    BaseExternalAdapter,
    AdapterConfig,
    RetryConfig,
    RateLimitConfig,
    AdapterResult,
)

class HMRCAdapter(BaseExternalAdapter[AdapterConfig]):
    """Adapter for HMRC VAT API."""

    def __init__(self, bearer_token: str):
        config = AdapterConfig(
            base_url="https://api.service.hmrc.gov.uk",
            timeout=30.0,
            headers={"Authorization": f"Bearer {bearer_token}"},
            retry=RetryConfig(max_retries=3, base_delay=1.0),
            rate_limit=RateLimitConfig(requests_per_second=4),
        )
        super().__init__(config)

    async def get_vat_obligations(
        self, vrn: str, from_date: str, to_date: str
    ) -> AdapterResult[list[dict]]:
        """Fetch VAT obligations for a business."""
        return await self._get(
            f"/organisations/vat/{vrn}/obligations",
            params={"from": from_date, "to": to_date, "status": "O"},
        )
```

**Related:** [Error Normalization](patterns.md#error-normalization), [Adapter Result](patterns.md#adapter-result), [Graphql Bff Pattern](patterns.md#graphql-bff-pattern)

---

## Graphql Bff Pattern

Backend-for-Frontend using GraphQL as the API layer between UI and backend services

### Example

```dsl
# GraphQL schema is auto-generated from your entities:
# entity Task → GraphQL type Task with Query/Mutation

# Enable the GraphQL endpoint while serving:
# $ dazzle serve --graphql

# Mount GraphQL endpoint in your app:
from dazzle.http.graphql import mount_graphql
mount_graphql(app, backend_spec)

# Query example:
query {
  tasks(status: "todo") {
    id
    title
    status
  }
}

# Mutation example:
mutation {
  createTask(input: {title: "New task"}) {
    id
    title
  }
}
```

---

## Graphql Schema Inspection

Ways to inspect generated API contracts from entity specs. GraphQL can be enabled at runtime, while OpenAPI and route inspection provide the primary CLI contract checks.

### Syntax

```dsl
# Emit the generated OpenAPI contract
dazzle specs openapi

# Emit OpenAPI as JSON for tooling
dazzle specs openapi -f json

# Boot the runtime and inspect mounted routes
dazzle inspect routes --runtime

# Serve with the optional GraphQL endpoint
dazzle serve --graphql
```

### Example

```dsl
$ dazzle specs openapi -f json
{
  "openapi": "3.1.0",
  "paths": {
    "/tasks": {
      "get": {
        "summary": "List Task"
      },
      "post": {
        "summary": "Create Task"
      }
    }
  }
}

$ dazzle serve --graphql
# GraphQL available at /graphql when strawberry-graphql is installed
```

**Related:** [Graphql Bff Pattern](patterns.md#graphql-bff-pattern), [External Adapter](patterns.md#external-adapter)

---

## Junction Many To Many

Many-to-many relationships are modelled with an explicit junction entity
that carries the FKs to both sides plus any relationship-specific data
(timestamps, role flags, revocation). The `via:` keyword expresses
aggregates / scope rules that walk through the junction without manual
JOIN composition.

The junction is a first-class entity — it can have its own surfaces,
scope rules, RBAC, and audit trail. That matters because the relationship
itself is often the thing the user cares about (e.g. "when was Alice
assigned to Project X?").

### Example

```dsl
entity User "User":
  id: uuid pk
  email: email required unique

entity Role "Role":
  id: uuid pk
  name: str(80) required unique

  # `via:` scope rule (EXISTS through the junction) — a member can read
  # a Role only if a UserRole row links them to it. Every scope rule
  # needs a matching permit op.
  permit:
    read: role(member)
  scope:
    read: via UserRole(user = current_user, role = id)
      as: member

entity UserRole "User Role":
  id: uuid pk
  user: ref User required
  role: ref Role required
  granted_at: datetime auto_add
  revoked_at: datetime optional   # revocation = tombstone, not deletion

# `via:` aggregate — count roles per user through the junction.
# (Row-level predicates ride inside the aggregate's parens, e.g.
# count(UserRole where revoked_at = null) for a direct junction count.)
workspace admin_dash "Admin Dashboard":
  user_role_counts:
    source: User
    display: cohort_strip
    cohort_strip_config:
      member_via: id
      lenses:
        - id: active_roles
          label: "Active Roles"
          primary_aggregate:
            aggregate: count(Role)
            via: UserRole(user = id)
```

**Related:** [Direct One To Many](patterns.md#direct-one-to-many), [Primary Aggregate N To One](patterns.md#primary-aggregate-n-to-one), [Shared Parent Join](patterns.md#shared-parent-join), [Soft Delete](patterns.md#soft-delete)

---

## Kanban Board

Status-based workflow visualization

### Example

```dsl
# Kanban-style task board
entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[backlog,todo,in_progress,review,done]=backlog
  priority: enum[low,medium,high]=medium
  assigned_to: ref User optional

workspace kanban "Task Board":
  purpose: "Visual workflow management"

  backlog:
    source: Task
    filter: status = backlog
    sort: priority desc
    display: grid
    action: task_edit

  in_progress:
    source: Task
    filter: status = in_progress
    sort: priority desc
    display: grid

  review:
    source: Task
    filter: status = review
    sort: priority desc
    display: grid

  done:
    source: Task
    filter: status = done
    sort: completed_at desc
    limit: 20
    display: grid
```

---

## Llm Cognition Pattern

Entity design optimized for LLM understanding with intent, semantic tags, archetypes, and example data

### Example

```dsl
# v0.7.1 LLM-Optimized Entity Design

# First, define reusable archetypes
archetype Timestamped:
  created_at: datetime auto_add
  updated_at: datetime auto_update

archetype Auditable:
  created_by: ref User
  updated_by: ref User

# Main entity with full LLM cognition features
entity Invoice "Invoice":
  intent: "Represent a finalized billing request from vendor to customer"
  domain: billing
  patterns: lifecycle, line_items, audit
  extends: Timestamped, Auditable

  id: uuid pk
  invoice_number: str(50) unique required
  status: enum[draft,sent,paid,overdue,cancelled] = draft
  customer: ref Customer required
  items: has_many InvoiceItem cascade
  subtotal: decimal(10,2) required
  tax_amount: decimal(10,2)
  total: decimal(10,2) required
  due_date: date required
  paid_at: datetime

  # Computed fields
  days_until_due: computed days_since(due_date)
  is_overdue: computed due_date < today and status != paid

  # State machine
  transitions:
    draft -> sent: requires customer
    sent -> paid: requires paid_at
    sent -> overdue: auto after 30 days
    sent -> cancelled: role(admin)
    overdue -> paid: requires paid_at
    * -> cancelled: role(admin)

  # Invariants with messages
  invariant: total = subtotal + tax_amount
    message: "Total must equal subtotal plus tax"
    code: INVOICE_TOTAL_MISMATCH

  invariant: status != paid or paid_at != null
    message: "Paid invoices must have a payment date"
    code: INVOICE_MISSING_PAYMENT_DATE

  # Access rules
  access:
    read: role(accountant) or role(admin) or customer = current_user.company
    write: role(accountant) or role(admin)

  # Example data
  examples:
    {invoice_number: "INV-2024-001", status: draft, subtotal: 1000.00, tax_amount: 200.00, total: 1200.00}
    {invoice_number: "INV-2024-002", status: sent, subtotal: 500.00, tax_amount: 100.00, total: 600.00}
    {invoice_number: "INV-2024-003", status: paid, subtotal: 750.00, tax_amount: 150.00, total: 900.00}

entity InvoiceItem "Invoice Line Item":
  intent: "Single line item on an invoice with quantity and pricing"
  domain: billing
  patterns: line_items
  extends: Timestamped

  id: uuid pk
  invoice: belongs_to Invoice
  description: str(500) required
  quantity: int required
  unit_price: decimal(10,2) required
  line_total: computed quantity * unit_price

  invariant: quantity > 0
    message: "Quantity must be positive"
    code: ITEM_INVALID_QUANTITY

  examples:
    {description: "Consulting hours", quantity: 10, unit_price: 150.00}
    {description: "Software license", quantity: 5, unit_price: 99.00}
```

**Related:** [Intent](entities.md#intent), [Archetype](entities.md#archetype), [Domain Patterns](entities.md#domain-patterns), [Examples](entities.md#examples), [Invariant Message](entities.md#invariant-message), [Relationships](entities.md#relationships)

---

## Master Detail

Parent-child relationship with nested views

### Example

```dsl
# Project with nested tasks
entity Project "Project":
  id: uuid pk
  name: str(200) required
  status: enum[active,completed,archived]=active

entity Task "Task":
  id: uuid pk
  title: str(200) required
  project: ref Project required
  status: enum[todo,done]=todo

surface project_list "Projects":
  uses entity Project
  mode: list
  section main:
    field name
    field status

surface project_detail "Project":
  uses entity Project
  mode: view
  section info:
    field name
    field status

# Sections render fields of the surface's own entity — a section can't
# embed another entity. Express the child list as its own surface,
# filterable by the parent FK.
surface project_tasks "Project Tasks":
  uses entity Task
  mode: list
  section main:
    field project "Project"
    field title
    field status
  ux:
    purpose: "Tasks for a project, filtered by the parent FK"
    filter: project
```

---

## Notifications

Alert users to important events

### Example

```dsl
# Entity with a computed field — time-based conditions live on computed
# fields (days_since/days_until), which attention rules then compare.
entity Order "Order":
  id: uuid pk
  order_number: str(20) required unique
  customer: ref Customer required
  status: enum[fresh,paid,shipped,delivered]=fresh
  payment_status: enum[pending,paid,failed]=pending
  total: decimal(10,2) required
  shipped_at: datetime optional
  created_at: datetime auto_add
  days_since_shipped: computed days_since(shipped_at)

# Surface with attention signals
surface order_list "Orders":
  uses entity Order
  mode: list

  section main:
    field order_number
    field customer "Customer"
    field status
    field total

  ux:
    purpose: "Process and fulfill orders"

    # Payment failed - critical
    attention critical:
      when: payment_status = failed
      message: "Payment failed!"
      action: order_retry_payment

    # Shipping delayed — compares the computed field
    attention warning:
      when: days_since_shipped > 5 and status = shipped
      message: "Delayed shipment"

    # New order awaiting payment
    attention notice:
      when: status = fresh and payment_status = pending
      message: "New order awaiting payment"
```

---

## Primary Aggregate N To One

Show a per-parent summary statistic computed over the parent's child rows —
e.g. "total revenue per Customer", "open Issue count per Repository",
"average response time per Ticket". Use `primary_aggregate:` on a
cohort_strip / bar_chart / metrics region: one scope-aware GROUP BY query
replaces N+1 enumeration.

Pairs with the direct 1:N shape (#1241). The aggregated entity carries a
`ref Parent` field; the region declares the aggregate against that FK.

### Example

```dsl
entity Customer "Customer":
  id: uuid pk
  name: str(200) required

entity Order "Order":
  id: uuid pk
  customer: ref Customer required
  total: decimal(12,2) required
  placed_at: datetime auto_add

workspace customer_overview "Customer Overview":
  customer_revenue:
    source: Customer
    display: cohort_strip
    cohort_strip_config:
      member_via: id
      lenses:
        - id: total_revenue
          label: "Total Revenue"
          primary_aggregate:
            aggregate: sum(Order.total)
```

**Related:** [Direct One To Many](patterns.md#direct-one-to-many), [Junction Many To Many](patterns.md#junction-many-to-many), [Shared Parent Join](patterns.md#shared-parent-join)

---

## Role Based Access

Persona variants controlling scope and capabilities

### Example

```dsl
# Role-based access with personas
surface ticket_list "Support Tickets":
  uses entity Ticket
  mode: list

  section main:
    field subject
    field status
    field assigned_to "Assignee"

  ux:
    purpose: "Manage support tickets by role"

    # Admins see everything, can reassign
    as admin:
      scope: all
      action_primary: ticket_assign
      show_aggregate: total, open, resolved_today

    # Agents see assigned + unassigned
    as agent:
      scope: assigned_to = current_user or assigned_to = null
      action_primary: ticket_respond

    # Customers see only their tickets
    as customer:
      scope: created_by = current_user
      hide: internal_notes, assigned_to
      read_only: true
```

---

## Search Filter

Full-text search with faceted filtering

### Example

```dsl
# Searchable product catalog
entity Product "Product":
  id: uuid pk
  name: str(200) required
  description: text
  category: enum[electronics,clothing,home,other]
  price: decimal(10,2)
  in_stock: bool=true

surface product_catalog "Products":
  uses entity Product
  mode: list

  section main:
    field name
    field category
    field price
    field in_stock

  ux:
    purpose: "Browse and find products"
    search: name, description
    filter: category, in_stock
    sort: name asc
    empty: "No products match your search"
```

---

## Self Referencing Hierarchy

Tree-shaped data where each row points at a parent of the same entity:
Category → parent Category, Department → parent Department, manager →
report chains. The `descendants_of` / `ancestors_of` field types resolve
the recursive walk in one CTE rather than per-level Python loops.

Two flavours: direct self-FK (`parent: ref self`) and chains-through-
junction (`descendants_of self via ManagerLink.manager`). The
declaration form `field all_reports: descendants_of self via
ManagerLink.manager` exposes the resolved descendant set as a virtual
field usable in surfaces, scope rules, and aggregates.

### Example

```dsl
entity Department "Department":
  id: uuid pk
  name: str(120) required
  parent: ref self optional    # nullable root → forest of trees

  # #1227 Phase 3(b): resolved virtual field via recursive CTE.
  all_descendants: descendants_of self via parent
  all_ancestors: ancestors_of self via parent

# Scope rule using the resolved set: a manager sees themselves + descendants.
surface visible_departments "My Departments":
  uses entity Department
  mode: list
  section main:
    field name "Department"

scope:
  read: id in current_user.department.all_descendants
    as: department_head
```

**Related:** [Direct One To Many](patterns.md#direct-one-to-many), [Temporal](patterns.md#temporal), [Subtype Of](patterns.md#subtype-of)

---

## Settings Archetype

System-wide configuration using the settings semantic archetype for admin-only singleton entities

### Example

```dsl
# v0.10.3: System-wide settings entity
entity AppSettings "Application Settings":
    archetype: settings
    id: uuid pk
    timezone: timezone = "UTC"          # IANA timezone (e.g., "Europe/London")
    default_currency: str(3) = "GBP"
    maintenance_mode: bool = false
    max_upload_size_mb: int = 10
    support_email: email

# What happens automatically:
# 1. Entity is marked as singleton (is_singleton = true)
# 2. Admin-only access rules are applied
# 3. Settings surface is auto-generated (if not explicitly defined):
#    - Name: app_settings_settings
#    - Mode: edit
#    - Access: admin only
#    - Route: /admin/settings/app_settings
#
# The singleton ensures only one record exists in the database.
# First access will create the record; subsequent accesses update it.
```

**Related:** [Tenant Archetype](patterns.md#tenant-archetype), [Tenant Settings Archetype](patterns.md#tenant-settings-archetype), Timezone Field

---

## Shared Parent Join

The cohort source rows and the aggregated rows both reference a common
pivot entity, but there is no direct FK between them. `share:` bridges
the diamond with a single GROUP BY query keyed on the source row's
primary key — the pivot itself doesn't appear in the FROM clause.

Surfaced concretely by AegisMark in #1213-#1216. Before `share:` shipped,
the only expression was a Python override route — agents went through
2-3 design rounds before landing on the canonical shape, which is why
discoverability (Phase 2) matters as much as the feature itself.

### Example

```dsl
# AegisMark's canonical surface: per-enrolment average marking score,
# where MarkingResult is keyed on StudentProfile, not ClassEnrolment.
entity StudentProfile "Student":
  id: uuid pk
  display_name: str(120) required

entity ClassEnrolment "Class Enrolment":
  id: uuid pk
  student_profile: ref StudentProfile required
  teaching_group: ref TeachingGroup required

entity MarkingResult "Marking Result":
  id: uuid pk
  student_profile: ref StudentProfile required   # shares the pivot
  score: decimal(4,2) required

workspace class_view "Class View":
  cohort_attainment:
    source: ClassEnrolment
    display: cohort_strip
    cohort_strip_config:
      member_via: id
      lenses:
        - id: attainment
          label: "Avg Score"
          primary_aggregate:
            aggregate: avg(MarkingResult.score)
            share: StudentProfile     # the diamond pivot
```

**Related:** [Primary Aggregate N To One](patterns.md#primary-aggregate-n-to-one), [Junction Many To Many](patterns.md#junction-many-to-many), [Subtype Of](patterns.md#subtype-of)

---

## Soft Delete

Mark rows as deleted without physically removing them (tombstone pattern).
Add the bare `soft_delete` directive to the entity body; the framework auto-injects a
nullable `deleted_at: datetime` tombstone field, auto-filters
`deleted_at IS NULL` on list / read / aggregate, and converts DELETE
requests into an UPDATE that stamps `deleted_at = NOW()`.

Composes with scope rules and aggregates through the same `QueryBuilder`
chain. `include_deleted=true` opt-out is available for admin / audit
views.

### Example

```dsl
entity User "User":
  id: uuid pk
  email: email required unique
  display_name: str(120) required
  soft_delete
  # Bare keyword directive (no value). Framework auto-injects:
  # `deleted_at: datetime optional` if missing.

# List / read / aggregate paths auto-filter deleted_at IS NULL — authors
# don't write the predicate. DELETE handler stamps deleted_at = NOW()
# instead of physically removing.

# Opt-out is per-call (e.g. admin audit view):
#   repo.list(include_deleted=True)  # returns ALL rows including tombstoned
```

**Related:** [Temporal](patterns.md#temporal), [Direct One To Many](patterns.md#direct-one-to-many), [Subtype Of](patterns.md#subtype-of)

---

## Subtype Of

Declare an IS-A relationship to a base entity. The child shares the base's
primary key via a shared-PK FK; the framework auto-adds a `kind` enum on the
base table as the discriminator and writes rows atomically across both tables
on create / update. Polymorphic detail surfaces dispatch via `subtype_panel:`.

**Escape hatch, not the default.** See `inference_kb: subtype_of_only_for_true_isa`
for the four cheaper alternatives to try first (separate entities, state machine,
nullable fields on one entity, has_many / via:). Reach for `subtype_of:` only
when all of: true IS-A relationship, subtype-specific fields need NOT NULL at
the schema level, and you need polymorphic queries ("show me all assets, mixed
kinds").

### Example

```dsl
module assets
app asset_registry "Asset Registry"

# Base — shared fields + the synthesised `kind` discriminator enum.
entity Asset "Asset":
  id: uuid pk
  acquired_at: date required
  acquired_value: decimal(12,2) required
  location: str(120)

# Each subtype: declare subtype_of: <Base>. Do NOT redeclare `id` (linker rule
# E_SUBTYPE_DUPLICATE_PK). Do NOT shadow base field names (#1236
# E_SUBTYPE_FIELD_NAME_OVERLAP). Multi-level (A subtype_of B subtype_of C) is
# rejected at linker time.
entity Vehicle "Vehicle":
  subtype_of: Asset
  wheels: int required
  vin: str(17) required unique

entity Building "Building":
  subtype_of: Asset
  floors: int required
  postcode: str(10) required

# Polymorphic detail view dispatches inline by row.kind. The `when` branches
# name snake_case discriminator values (lowercased child entity names).
surface asset_card "Asset Card":
  uses entity Asset
  mode: view
  section main:
    field acquired_at "Acquired"
    field location "Location"
    subtype_panel:
      when kind = vehicle: include surface vehicle_detail
      when kind = building: include surface building_detail

# A subtype detail surface receives the JOIN'd base columns automatically
# (Repository.read injects them when subtype_join_sql is active).
surface vehicle_detail "Vehicle":
  uses entity Vehicle
  mode: view
  section main:
    field wheels "Wheels"
    field vin "VIN"
```

**Related:** Subtype Of Only For True Isa, State Machine Pattern, [Audit Trail](patterns.md#audit-trail)

---

## Temporal

Each row is an open or closed interval (`start_date`, `end_date`) and most
queries want the row that is *currently active*. The `temporal:` block
auto-injects the tombstone-style filter on read paths, threads an
`?as_of=YYYY-MM-DD` URL parameter for historical lookups, enforces "at
most one active row per key" via a partial unique index, and exposes a
synthesised `active` computed field for use in scope predicates.

Real surfaces: Employment, Salary, ManagerLink (all in `examples/hr_records/`),
lease terms, price lists, GDPR consent records, feature flags with
effective dates, exchange-rate snapshots.

### Example

```dsl
# From examples/hr_records — the canonical surface for `temporal:`.
entity Person "Person":
  id: uuid pk
  display_name: str(120) required

entity Employment "Employment":
  id: uuid pk
  person: ref Person required
  role: ref Role required
  start_date: date required
  end_date: date              # implicit when temporal: is set

  temporal:
    start_field: start_date
    end_field: end_date
    key_field: person          # constrains 'at most one active row per person'
    default_filter: active     # list/read/aggregate auto-filter end IS NULL
    as_of_param: as_of         # workspaces accept ?as_of=YYYY-MM-DD

# Workspaces composed against the temporal entity automatically get the
# 'currently active' filter and the ?as_of= URL parameter. Manager scope
# rules can traverse Person → current Employment without hand-rolling
# `end_date = null` filters.
```

**Related:** [Soft Delete](patterns.md#soft-delete), [Self Referencing Hierarchy](patterns.md#self-referencing-hierarchy), [Junction Many To Many](patterns.md#junction-many-to-many)

---

## Tenant Archetype

Multi-tenant root entity that defines tenant boundaries and automatically injects tenant FK into other entities

### Example

```dsl
# v0.10.3: Multi-tenant application
entity Company "Company":
    archetype: tenant
    id: uuid pk
    name: str(200) required
    slug: str(50) required unique
    plan: enum[free,pro,enterprise] = free
    created_at: datetime auto_add

# Other entities automatically get tenant FK injected
entity Contact "Contact":
    id: uuid pk
    name: str(200) required
    email: email required
    # company: ref Company  <-- auto-injected by archetype expander

entity Project "Project":
    id: uuid pk
    name: str(200) required
    status: enum[active,completed,archived] = active
    # company: ref Company  <-- auto-injected

# What happens automatically:
# 1. Company is marked as tenant root (is_tenant_root = true)
# 2. All other entities (except archetype: settings) get company FK
# 3. Tenant admin surface is auto-generated:
#    - Name: company_admin
#    - Mode: list
#    - Access: admin only
#    - Route: /admin/tenants
```

**Related:** [Settings Archetype](patterns.md#settings-archetype), [Tenant Settings Archetype](patterns.md#tenant-settings-archetype)

---

## Tenant Settings Archetype

Per-tenant configuration using tenant_settings archetype for tenant-scoped singleton entities

### Example

```dsl
# v0.10.3: Complete multi-tenant app with settings
entity Company "Company":
    archetype: tenant
    id: uuid pk
    name: str(200) required
    slug: str(50) required unique

entity CompanySettings "Company Settings":
    archetype: tenant_settings
    id: uuid pk
    company: ref Company              # Explicit tenant ref
    timezone: timezone                # Override system default
    logo_url: url
    invoice_prefix: str(10) = "INV"
    default_payment_terms: int = 30   # days

# System-wide settings (not tenant-scoped)
entity SystemSettings "System Settings":
    archetype: settings
    id: uuid pk
    timezone: timezone = "UTC"
    maintenance_mode: bool = false

# What happens automatically:
# 1. CompanySettings is marked as singleton (per-tenant)
# 2. Tenant admin access rules are applied
# 3. Settings surface is auto-generated:
#    - Name: company_settings_settings
#    - Mode: edit
#    - Access: tenant admin only
#    - Route: /settings/company_settings
#
# Note: SystemSettings is NOT tenant-scoped because it has
# archetype: settings (not tenant_settings)
```

**Related:** [Settings Archetype](patterns.md#settings-archetype), [Tenant Archetype](patterns.md#tenant-archetype), Timezone Field

---

## User Archetype

Core user entity with built-in authentication fields for local auth and OAuth/SSO support

### Example

```dsl
# v0.10.4: User entity with automatic auth fields
entity User "User":
    archetype: user
    id: uuid pk
    email: email required unique
    name: str(200) required
    avatar_url: url optional

# What gets auto-injected:
# - password_hash: str(255) optional      # For local auth
# - email_verified: bool = false
# - email_verify_token: str(100) optional
# - password_reset_token: str(100) optional
# - password_reset_expires: datetime optional
# - is_active: bool = true
# - last_login: datetime optional
# - auth_provider: enum[local,google,apple,github] = local
# - auth_provider_id: str(255) optional    # External provider ID
# - created_at: datetime auto_add

# Auto-generated surfaces (admin-only):
# - user_list: List all users
# - user_detail: View user details
# - user_create: Create new user
# - user_edit: Edit user

# Important: User entity is system-wide (not tenant-scoped)
# Use UserMembership for tenant-user relationships
```

**Related:** [User Membership Archetype](patterns.md#user-membership-archetype), [Tenant Archetype](patterns.md#tenant-archetype)

---

## User Membership Archetype

User-tenant relationship with per-tenant personas (roles) for multi-tenant applications

### Example

```dsl
# v0.10.4: Complete multi-tenant user management
entity Company "Company":
    archetype: tenant
    id: uuid pk
    name: str(200) required
    slug: str(50) required unique

entity User "User":
    archetype: user
    id: uuid pk
    email: email required unique
    name: str(200) required

entity UserMembership "User Membership":
    archetype: user_membership
    id: uuid pk
    # Optionally define explicit refs (otherwise auto-injected):
    # user: ref User required
    # company: ref Company required

# What gets auto-injected:
# - user: ref User required              # Link to user
# - company: ref Company required        # Link to tenant
# - personas: json = []                  # ["admin", "member", "billing"]
# - is_primary: bool = false             # Primary membership flag
# - invited_by: ref User optional        # Who sent the invite
# - invited_at: datetime auto_add        # When invited
# - accepted_at: datetime optional       # When accepted

# Auto-generated surfaces (admin-only):
# - user_membership_list: List all memberships
# - user_membership_edit: Edit membership (assign personas)

# Usage: Assign personas to control per-tenant access
# personas: ["admin"]           -> Full tenant admin
# personas: ["member"]          -> Standard member
# personas: ["billing", "member"] -> Member with billing access
```

**Related:** [User Archetype](patterns.md#user-archetype), [Tenant Archetype](patterns.md#tenant-archetype)

---
