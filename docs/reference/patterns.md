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
  section audit "Audit Trail":
    field created_by.name "Created By"
    field created_at "Created At"
    field updated_by.name "Last Updated By"
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

  # Permit: who CAN perform actions
  permit:
    read: role(doctor) or role(pharmacist) or role(nurse)
    prescribe: role(doctor)
    dispense: role(pharmacist)
    cancel: role(doctor) or role(pharmacist)

  # Forbid: separation of duty overrides
  forbid:
    prescribe: role(pharmacist)
    dispense: role(doctor)

  # Audit: compliance logging
  audit:
    read: role(admin)
    prescribe: role(compliance_officer)
    dispense: role(compliance_officer)
    cancel: role(compliance_officer)

  transitions:
    draft -> active: role(doctor)
    active -> dispensed: role(pharmacist)
    active -> cancelled: role(doctor) or role(pharmacist)
```

**Related:** [Access Rules](access-control.md#access-rules), [Role Based Access](patterns.md#role-based-access), [Business Logic Pattern](patterns.md#business-logic-pattern), [Rbac Validation](testing.md#rbac-validation)

---

## Multi-Tenant Rbac

Field-condition RBAC for multi-tenant or ownership-scoped access. Combines role gates with row-level filters. See [Runtime Evaluation Model](access-control.md#runtime-evaluation-model) for how these rules are enforced at each tier.

### Example

```dsl
# Multi-tenant school management — teachers see only their school's data
entity Student "Student":
  id: uuid pk
  name: str(200) required
  school: ref School required
  grade: int required

  # Pure role gate: admins see everything (Tier 1 — fast rejection)
  permit:
    list: role(admin)
    read: role(admin)

  # Field-condition filter: teachers see only their school (Tier 2 — row filter)
  permit:
    list: school = current_user.school
    read: school = current_user.school

  # Write access: teachers can update their school's students
  permit:
    update: school = current_user.school
    create: role(teacher) or role(admin)

  # Nobody outside admin can delete
  forbid:
    delete: role(teacher)

# Ownership-scoped: users see only their own records
entity Timesheet "Timesheet":
  id: uuid pk
  employee: ref User required
  hours: decimal required
  submitted: bool = false

  # Owner sees their own timesheets
  permit:
    list: employee = current_user
    read: employee = current_user
    update: employee = current_user

  # Managers see all (pure role gate)
  permit:
    list: role(manager)
    read: role(manager)

  # Only managers can delete
  permit:
    delete: role(manager)
```

**Related:** [Cedar Rbac](patterns.md#cedar-rbac), [Runtime Evaluation Model](access-control.md#runtime-evaluation-model), [Access Rules](access-control.md#access-rules)

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

  # Key performance metrics
  metrics:
    aggregate:
      total: count(Task)
      completed: count(Task where status = done)
      in_progress: count(Task where status = in_progress)
      completion_rate: round(count(Task where status = done) * 100 / count(Task), 1)
```

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
from dazzle_dnr_back.graphql.adapters import (
    normalize_error,
    NormalizedError,
    ErrorCategory,
    ErrorSeverity,
)

normalized = normalize_error(error, service_name="hmrc")
```

### Example

```dsl
from dazzle_dnr_back.graphql.adapters import (
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
from dazzle_dnr_back.graphql.adapters import (
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
from dazzle_dnr_back.graphql.adapters import (
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

# Inspect the generated schema:
# $ dazzle dnr inspect --schema

# Mount GraphQL endpoint in your app:
from dazzle_dnr_back.graphql import mount_graphql
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

CLI command to inspect the auto-generated GraphQL schema from entity specs.

### Syntax

```dsl
# Display GraphQL SDL
dazzle dnr inspect --schema

# Get schema info as JSON
dazzle dnr inspect --schema --format json
```

### Example

```dsl
$ dazzle dnr inspect --schema
📊 GraphQL Schema

type Query {
  task(id: ID!): Task
  tasks(status: String, limit: Int): [Task!]!
}

type Mutation {
  createTask(input: TaskInput!): Task!
  updateTask(id: ID!, input: TaskInput!): Task!
  deleteTask(id: ID!): Boolean!
}

type Task {
  id: ID!
  title: String!
  status: String!
  createdAt: DateTime!
}

input TaskInput {
  title: String!
  status: String
}
```

**Related:** [Graphql Bff Pattern](patterns.md#graphql-bff-pattern), [External Adapter](patterns.md#external-adapter)

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
  section tasks "Tasks":
    uses entity Task
    filter: project = this
    field title
    field status
```

---

## Notifications

Alert users to important events

### Example

```dsl
# Surface with attention signals
surface order_list "Orders":
  uses entity Order
  mode: list

  section main:
    field order_number
    field customer.name
    field status
    field total

  ux:
    purpose: "Process and fulfill orders"

    # Payment failed - critical
    attention critical:
      when: payment_status = failed
      message: "Payment failed!"
      action: order_retry_payment

    # Shipping delayed
    attention warning:
      when: days_since(shipped_at) > 5 and status = shipped
      message: "Delayed shipment"

    # New order
    attention notice:
      when: status = new and created_at > today
      message: "New order today"
```

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
    field assigned_to.name

  ux:
    purpose: "Manage support tickets by role"

    # Admins see everything, can reassign
    for admin:
      scope: all
      action_primary: ticket_assign
      show_aggregate: total, open, resolved_today

    # Agents see assigned + unassigned
    for agent:
      scope: assigned_to = current_user or assigned_to = null
      action_primary: ticket_respond

    # Customers see only their tickets
    for customer:
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
# - user_view: View user details
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
