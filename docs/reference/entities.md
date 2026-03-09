# Entities

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

Entities are the core data models in DAZZLE. They define structure, relationships, constraints, state machines, and access rules. This page covers entity definitions, field types, enums, references, computed fields, invariants, and supporting constructs like indexes and unique constraints.

---

## Entity

A domain model representing a business concept (User, Task, Device, etc.).
Similar to a database table but defined at the semantic level. Includes fields
with types, constraints, relationships, and business logic. v0.7.1 adds LLM
cognition features: intent, domain/patterns tags, archetypes, and relationship semantics.

### Syntax

```dsl
entity <EntityName> "<Display Name>":
  [intent: "<why this entity exists>"]
  [domain: <tag>]
  [patterns: <tag1>, <tag2>, ...]
  [extends: <ArchetypeName1>, <ArchetypeName2>, ...]

  <field_name>: <type> [modifiers]
  ...

  [<computed_field>: computed <expression>]

  [transitions:
    <from_state> -> <to_state>
    <from_state> -> <to_state>: requires <field>
    <from_state> -> <to_state>: role(<role_name>)]

  [invariant: <condition>
    [message: "<error message>"]
    [code: <ERROR_CODE>]]

  [access:
    read: <condition>
    write: <condition>]

  [examples:
    {<field>: <value>, <field>: <value>, ...}
    {<field>: <value>, <field>: <value>, ...}]

  [index <field1>, <field2>]
  [unique <field1>, <field2>]
```

### Example

```dsl
entity Ticket "Support Ticket":
  intent: "Track and resolve customer issues through structured workflow"
  domain: support
  patterns: lifecycle, assignment, audit

  id: uuid pk
  title: str(200) required
  status: enum[open,in_progress,resolved,closed]=open
  assigned_to: ref User
  resolution: text
  created_at: datetime auto_add

  # Computed field
  days_open: computed days_since(created_at)

  # State machine
  transitions:
    open -> in_progress: requires assigned_to
    in_progress -> resolved: requires resolution
    resolved -> closed
    closed -> open: role(manager)

  # Invariants with messages
  invariant: status != resolved or resolution != null
    message: "Resolution is required before closing ticket"
    code: TICKET_NEEDS_RESOLUTION

  # Access rules
  access:
    read: role(agent) or role(manager)
    write: role(agent) or role(manager)

  # Example data for LLM understanding
  examples:
    {title: "Login page not loading", status: open, priority: high}
    {title: "Password reset email delayed", status: in_progress, priority: medium}
```

**Related:** [Surface](surfaces.md#surface), [Field Types](entities.md#field-types), [Relationships](entities.md#relationships), [State Machine](entities.md#state-machine), [Invariant](entities.md#invariant), [Computed Field](entities.md#computed-field), [Access Rules](access-control.md#access-rules), [Archetype](entities.md#archetype), [Intent](entities.md#intent), [Examples](entities.md#examples)

---

## Enum

Enumeration type defining a fixed set of allowed values. Values are comma-separated inside square brackets with no spaces. Can specify a default value with =.

### Syntax

```dsl
<field_name>: enum[value1,value2,value3]
<field_name>: enum[value1,value2,value3]=default_value
```

### Example

```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required

  # Basic enum with default
  priority: enum[low,normal,high,urgent]=normal

  # Status enum for state tracking
  task_status: enum[todo,in_progress,blocked,done]=todo

  # Type classification
  task_type: enum[bug,feature,chore,spike]=feature
```

**Related:** [Field Types](entities.md#field-types), [Reserved Keywords](entities.md#reserved-keywords), [Entity](entities.md#entity)

---

## Field Types

Data types available for entity fields: str(N), text, int, decimal(P,S), bool, date, datetime, uuid, email, json, money, file, url, timezone, enum[...], ref Entity, has_many/has_one/embeds/belongs_to.

### Syntax

```dsl
# Scalar types:
#   str(N)          - String with max length N (e.g., str(200))
#   text            - Unlimited-length text
#   int             - Integer
#   decimal(P,S)    - Decimal with precision P and scale S (e.g., decimal(10,2))
#   bool            - Boolean (true/false)
#   date            - Date (YYYY-MM-DD)
#   datetime        - Date+time with timezone
#   uuid            - UUID identifier
#   email           - Email address with validation
#   json            - Flexible JSON data (maps to JSONB)
#   money           - Currency amount (integer minor units + ISO 4217 code)
#   money(GBP)      - Money with explicit currency
#   file            - File reference/upload path
#   url             - URL/URI with validation
#   timezone        - IANA timezone identifier (e.g., "Europe/London")

# Enum type:
#   enum[val1,val2,val3]         - Enumeration of fixed values
#   enum[val1,val2]=default_val  - With default value

# Reference types:
#   ref <Entity>               - Foreign key reference
#   has_many <Entity> [cascade|restrict|nullify|readonly]
#   has_one <Entity> [cascade|restrict|nullify]
#   embeds <Entity>            - Embedded value object
#   belongs_to <Entity>        - Inverse of has_many/has_one

# Modifiers (after type):
#   required       - Field must have a value
#   optional       - Field can be null (default for most types)
#   pk             - Primary key
#   unique         - Unique constraint
#   unique?        - Unique but nullable
#   auto_add       - Set automatically on creation (datetime)
#   auto_update    - Set automatically on update (datetime)
#   sensitive      - PII/credential masking in logs and exports
#   searchable     - Include in full-text search index (v0.34.0)

# Defaults:
#   = <value>      - Scalar default (e.g., = false, = "draft")
#   = today        - Date default
#   = now          - Datetime default
#   = today + 7d   - Date arithmetic default
```

### Example

```dsl
entity Order "Order":
  id: uuid pk
  title: str(200) required
  description: text
  quantity: int required
  price: decimal(10,2) required
  total: money required
  is_urgent: bool = false
  due_date: date = today + 7d
  created_at: datetime auto_add
  updated_at: datetime auto_update
  status: enum[draft,confirmed,shipped,delivered]=draft
  customer_email: email required sensitive
  customer: ref Customer required
  items: has_many OrderItem cascade
  metadata: json
  receipt_url: url
  timezone: timezone = "UTC"
```

**Related:** [Entity](entities.md#entity), [Json](entities.md#json), [Money](entities.md#money), [Timezone](entities.md#timezone)

---

## Json

Flexible JSON data type for storing structured but schema-less data. Maps to JSONB in PostgreSQL, JSON in MySQL/SQLite. Use for metadata, settings, external API payloads, or any data with variable structure.

### Syntax

```dsl
<field_name>: json
```

### Example

```dsl
entity Contact "Contact":
  id: uuid pk
  name: str(200) required

  # Flexible metadata - structure can vary per record
  metadata: json

  # User preferences (UI settings, notifications, etc.)
  preferences: json

  # External system data (from integrations)
  external_data: json
```

### Best Practices

- Use for truly dynamic data where schema varies
- Prefer explicit fields when structure is known
- Consider embeds for structured nested data
- JSON fields have limited query/filter support
- Validate JSON structure in application code if needed

**Related:** [Field Types](entities.md#field-types), [Entity](entities.md#entity), Embeds

---

## Money

Canonical money representation for monetary values. Uses integer minor units (pence/cents) + ISO 4217 currency code for precision and JSON serialization safety. REQUIRED for monetary fields in FACT/INTENT streams.

### Syntax

```dsl
<field_name>: money [required|optional]
<field_name>: money(GBP) [required|optional]  # Explicit currency
```

### Example

```dsl
entity Order "Order":
  id: uuid pk
  customer: ref Customer required

  # Money field - expands to amount_minor (int) + currency (str)
  total: money required

  # With explicit currency
  shipping_cost: money(GBP)

  # Optional money field
  discount: money optional

entity Invoice "Invoice":
  id: uuid pk
  order: ref Order required

  # Multiple money fields
  subtotal: money required
  tax_amount: money required
  total_amount: money required
```

**Related:** [Field Types](entities.md#field-types), [Entity](entities.md#entity), Decimal

---

## Timezone

IANA timezone identifier field type for storing timezone names like 'Europe/London', 'America/New_York', 'UTC'. Used for timezone configuration in settings entities.

### Syntax

```dsl
<field_name>: timezone [= "default_timezone"]
```

### Example

```dsl
entity AppSettings "Application Settings":
    archetype: settings
    id: uuid pk

    # System timezone with default
    timezone: timezone = "UTC"

entity UserPreferences "User Preferences":
    id: uuid pk
    user: ref User required

    # User-specific timezone
    display_timezone: timezone = "Europe/London"

entity Company "Company":
    archetype: tenant
    id: uuid pk
    name: str(200) required

    # Per-tenant timezone
    timezone: timezone = "UTC"
```

**Related:** [Field Types](entities.md#field-types), [Settings Archetype](patterns.md#settings-archetype), [Tenant Archetype](patterns.md#tenant-archetype)

---

## Ref

Reference (foreign key) to another entity. Creates a relationship between entities. The referenced entity must be defined in the same module or imported.

### Syntax

```dsl
<field_name>: ref <EntityName> [required|optional]
```

### Example

```dsl
entity Contact "Contact":
  id: uuid pk
  name: str(200) required

  # Optional reference (can be null)
  assigned_agent: ref User optional

  # Required reference (must have value)
  company: ref Company required

  # Self-reference (same entity)
  manager: ref Contact optional

  # Multiple references to same entity
  created_by: ref User required
  updated_by: ref User optional
```

**Related:** [Field Types](entities.md#field-types), [Relationships](entities.md#relationships), [Entity](entities.md#entity)

---

## Relationships

References and ownership relationships between entities. v0.7.1 adds semantic relationship types (has_many, has_one, embeds, belongs_to) with delete behaviors.

### Syntax

```dsl
# Simple reference (foreign key)
field_name: ref <EntityName> [required|optional]

# v0.7.1 Ownership relationships
field_name: has_many <EntityName> [cascade|restrict|nullify|readonly]
field_name: has_one <EntityName> [cascade|restrict|nullify]
field_name: embeds <EntityName>
field_name: belongs_to <EntityName>
```

### Example

```dsl
# Parent entity with children
entity Order "Order":
  id: uuid pk
  items: has_many OrderItem cascade  # Delete items when order deleted
  shipping_address: embeds Address   # Embedded value object
  customer: ref Customer required    # Foreign key reference

entity OrderItem "Order Item":
  id: uuid pk
  order: belongs_to Order            # Inverse of has_many
  product: ref Product required

# Readonly relationship (prevents modification through parent)
entity Customer "Customer":
  id: uuid pk
  orders: has_many Order readonly    # View orders but don't modify through Customer
```

**Related:** [Entity](entities.md#entity), [Field Types](entities.md#field-types), [Archetype](entities.md#archetype)

---

## Index

Database index for query optimization. Improves performance for filtered and sorted queries. Can be single-column or composite (multi-column).

### Syntax

```dsl
# Single column index
index <field_name>

# Composite index (multi-column)
index <field1>, <field2>, ...

# Place at end of entity definition after fields
```

### Example

```dsl
entity Contact "Contact":
  id: uuid pk
  email: email unique required
  first_name: str(100)
  last_name: str(100)
  status: enum[active,inactive]=active
  created_at: datetime auto_add

  # Single column index for status filtering
  index status

  # Composite index for name sorting
  index last_name, first_name

  # Index for date-based queries
  index created_at
```

### Best Practices

- Index fields used frequently in filters (WHERE clauses)
- Index fields used in ORDER BY clauses
- Use composite indexes for multi-column sorts/filters
- Unique fields are automatically indexed
- Primary keys are automatically indexed
- Don't over-index - each index has write overhead

**Related:** [Entity](entities.md#entity), [Field Types](entities.md#field-types)

---

## Unique Constraint

Uniqueness constraint on one or more fields. Single-field unique uses the 'unique' modifier. Multi-field unique uses the 'unique' statement.

### Syntax

```dsl
# Single field
<field_name>: <type> unique

# Multi-field composite unique
unique <field1>, <field2>
```

### Example

```dsl
entity User "User":
  id: uuid pk
  email: str(255) required unique    # Single field unique

entity Membership "Membership":
  id: uuid pk
  user: ref User required
  organization: ref Organization required

  # Composite unique: one membership per user per org
  unique user, organization
```

**Related:** [Index](entities.md#index), [Entity](entities.md#entity)

---

## Computed Field

Derived values calculated from other fields. Computed at query time, not stored. Part of the declarative business logic layer.

### Syntax

```dsl
<field_name>: computed <expression>

# Functions:
# days_since(datetime_field) - Days since the field's value
# sum(related.field) - Sum of related records
# count(related) - Count of related records
```

### Example

```dsl
entity Ticket "Ticket":
  created_at: datetime auto_add
  due_date: date

  # Days since ticket was opened
  days_open: computed days_since(created_at)

  # Days until due (negative if overdue)
  days_until_due: computed days_since(due_date)
```

**Related:** [Entity](entities.md#entity), [Field Types](entities.md#field-types)

---

## Invariant

Cross-field validation rules that must always hold. Enforced on create and update. Part of the declarative business logic layer.

### Syntax

```dsl
invariant: <condition>

# Operators:
# Comparison: =, !=, >, <, >=, <=
# Logical: and, or, not
# Null check: field != null, field = null

# IMPORTANT: Use single = for equality (not ==)
```

### Example

```dsl
entity Booking "Booking":
  start_date: datetime required
  end_date: datetime required
  priority: enum[low,medium,high]=medium
  due_date: date

  # End must be after start
  invariant: end_date > start_date

  # High priority bookings must have a due date
  invariant: priority != high or due_date != null
```

### Best Practices

- Use = for equality (consistent with access rules)
- Express as 'A or B' for 'if A then B' rules
- Keep invariants simple and focused
- Document the business rule in a comment
- Invariants use comparison operators (>, <, =, !=) - state machines use 'requires field' instead

**Related:** [Entity](entities.md#entity), [State Machine](entities.md#state-machine), [Access Rules](access-control.md#access-rules)

---

## State Machine

Define allowed status/state transitions with optional guards. Prevents invalid state changes and documents workflow rules declaratively.

### Syntax

```dsl
transitions:
  <from_state> -> <to_state>
  <from_state> -> <to_state>: requires <field_name>
  <from_state> -> <to_state>: role(<role_name>)
  <from_state> -> <to_state>: auto after <N> days
  <from_state> -> <to_state>: auto after <N> hours OR manual
  * -> <to_state>: role(admin)  # wildcard: from any state

# Supported conditions:
#   requires <field_name>     - Field must not be null
#   role(<role_name>)         - User must have this role
#   auto after <N> days       - Auto-transition after delay
#   auto after <N> hours      - (also: minutes)
#   auto ... OR manual        - Allow manual trigger too

# NOT supported in transitions (use invariants instead):
#   field != null        - Use: requires field
#   field = value        - Not supported
#   field > value        - Not supported
#   Comparison operators - Not supported
```

### Example

```dsl
entity Task "Task":
  status: enum[todo,in_progress,done,archived]=todo
  assigned_to: ref User

  transitions:
    todo -> in_progress: requires assigned_to
    in_progress -> done
    in_progress -> todo
    done -> todo: role(admin)  # Only admin can reopen
    done -> archived: auto after 30 days OR manual

entity Ticket "Ticket":
  status: enum[open,resolved,closed]=open
  resolution_note: text

  transitions:
    open -> resolved: requires resolution_note
    resolved -> closed: auto after 7 days OR manual
    resolved -> open
    * -> open: role(admin)  # Admin can reopen from any state
```

### Best Practices

- Use for status fields with defined workflows
- Document transition rules that match business processes
- Use role guards for administrative overrides
- Use requires guards for data integrity
- Transition conditions are simpler than invariants - use 'requires field' not 'field != null'
- For complex validations (field > value, field = specific_value), use invariants with status conditions instead

**Related:** [Entity](entities.md#entity), [Invariant](entities.md#invariant), [Access Rules](access-control.md#access-rules)

---

## Invariant Message

Human-readable error message and machine-readable error code for invariant violations. Improves API responses and internationalization.

### Syntax

```dsl
invariant: <condition>
  message: "<human-readable error message>"
  code: <ERROR_CODE>
```

### Example

```dsl
entity Booking "Booking":
  start_date: datetime required
  end_date: datetime required
  status: enum[pending,confirmed,cancelled] = pending
  confirmed_at: datetime

  # Invariant with message and code
  invariant: end_date > start_date
    message: "End date must be after start date"
    code: BOOKING_INVALID_DATE_RANGE

  invariant: status != confirmed or confirmed_at != null
    message: "Confirmed bookings must have a confirmation timestamp"
    code: BOOKING_MISSING_CONFIRMATION

  # Invariant without message (generates default)
  invariant: status != cancelled or end_date > today
```

### Best Practices

- Use SCREAMING_SNAKE_CASE for error codes
- Make messages user-friendly and actionable
- Include entity prefix in error codes (BOOKING_, USER_)
- Message and code are optional - defaults are generated

**Related:** [Entity](entities.md#entity), [Invariant](entities.md#invariant), [Access Rules](access-control.md#access-rules)

---

## Intent

A single-line declaration explaining WHY an entity exists in the domain. Helps LLMs understand the semantic purpose of data structures.

### Syntax

```dsl
intent: "<explanation of entity purpose>"
```

### Example

```dsl
entity Invoice "Invoice":
  intent: "Represent a finalized billing request with line items and tax calculations"

entity User "User":
  intent: "Authenticate and authorize system access with role-based permissions"

entity AuditLog "Audit Log":
  intent: "Track all data modifications for compliance and debugging"
```

### Best Practices

- Focus on WHY the entity exists, not WHAT it contains
- Describe the business/domain purpose
- Keep to one sentence
- Avoid technical implementation details

**Related:** [Entity](entities.md#entity), [Archetype](entities.md#archetype), [Examples](entities.md#examples)

---

## Examples

Inline example records that demonstrate valid data for an entity. Helps LLMs understand data formats, relationships, and realistic values.

### Syntax

```dsl
examples:
  - <field>: <value>, <field>: <value>, ...
  - <field>: <value>, <field>: <value>, ...
```

### Example

```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[todo,in_progress,done] = todo
  priority: enum[low,medium,high] = medium
  due_date: date

  examples:
    - title: "Write documentation", status: todo, priority: high, due_date: "2024-03-15"
    - title: "Fix login bug", status: in_progress, priority: high
    - title: "Update dependencies", status: done, priority: low

entity User "User":
  id: uuid pk
  email: email required unique
  name: str(100) required
  role: enum[admin,manager,member] = member

  examples:
    - email_address: "admin@example.com", name: "Alice Admin", role: admin
    - email_address: "bob@example.com", name: "Bob Manager", role: manager
    - email_address: "carol@example.com", name: "Carol Member", role: member
```

### Best Practices

- Include 2-3 representative examples
- Show different states/variations
- Use realistic but non-sensitive values
- Demonstrate enum values and relationships

**Related:** [Entity](entities.md#entity), [Intent](entities.md#intent), [Field Types](entities.md#field-types)

---

## Archetype

Reusable template defining common field patterns. Entities can extend archetypes to inherit fields, computed fields, and invariants. Promotes consistency and reduces repetition.

### Syntax

```dsl
archetype <ArchetypeName>:
  <field_name>: <type> [modifiers]
  ...
  [<computed_field>: computed <expression>]
  [invariant: <condition>]

# Entity extending an archetype
entity <EntityName> "<Display Name>":
  extends: <ArchetypeName1>, <ArchetypeName2>, ...
  <additional_fields>
```

### Example

```dsl
# Define reusable archetypes
archetype Timestamped:
  created_at: datetime auto_add
  updated_at: datetime auto_update

archetype Auditable:
  created_by: ref User
  updated_by: ref User
  version: int = 1

archetype SoftDelete:
  is_deleted: bool = false
  deleted_at: datetime
  deleted_by: ref User

# Entity using archetypes
entity Document "Document":
  extends: Timestamped, Auditable, SoftDelete
  intent: "Store versioned documents with full audit trail"

  id: uuid pk
  title: str(200) required
  content: text
  status: enum[draft,published,archived] = draft
```

### Best Practices

- Use for cross-cutting concerns (audit, timestamps, soft delete)
- Keep archetypes focused on one pattern
- Name archetypes as adjectives or nouns (Timestamped, Auditable)
- Entity fields override archetype fields with same name

**Related:** [Entity](entities.md#entity), [Intent](entities.md#intent), [Relationships](entities.md#relationships)

---

## Domain Patterns

Semantic tags that classify entities by domain area and common patterns. Helps LLMs understand entity relationships and generate consistent code.

### Syntax

```dsl
# Single domain tag
domain: <tag>

# Multiple pattern tags
patterns: <tag1>, <tag2>, <tag3>
```

### Example

```dsl
entity Invoice "Invoice":
  domain: billing
  patterns: lifecycle, audit, line_items

entity User "User":
  domain: identity
  patterns: authentication, authorization, profile

entity Order "Order":
  domain: commerce
  patterns: lifecycle, workflow, aggregate_root
```

**Related:** [Entity](entities.md#entity), [Intent](entities.md#intent), [Archetype](entities.md#archetype)

---

## Semantic Archetype

Built-in archetype kinds (settings, tenant, tenant_settings) that trigger automatic behavior like singleton enforcement, tenant FK injection, and admin surface generation. Different from custom archetypes which only provide field inheritance.

### Syntax

```dsl
# Semantic archetypes use archetype: declaration in entity body
entity <EntityName> "<Title>":
    archetype: <settings|tenant|tenant_settings>
    <fields...>

# Custom archetypes use extends: for field inheritance only
entity <EntityName> "<Title>":
    extends: <CustomArchetype1>, <CustomArchetype2>
    <fields...>
```

### Example

```dsl
# Semantic archetype: settings (system-wide singleton)
entity AppSettings "Application Settings":
    archetype: settings
    id: uuid pk
    timezone: timezone = "UTC"
    maintenance_mode: bool = false

# Semantic archetype: tenant (multi-tenant root)
entity Company "Company":
    archetype: tenant
    id: uuid pk
    name: str(200) required
    slug: str(50) required unique

# Semantic archetype: tenant_settings (per-tenant singleton)
entity CompanySettings "Company Settings":
    archetype: tenant_settings
    id: uuid pk
    company: ref Company
    timezone: timezone

# Custom archetype: field inheritance only (no automatic behavior)
archetype Timestamped:
    created_at: datetime auto_add
    updated_at: datetime auto_update

entity Task "Task":
    extends: Timestamped  # Gets created_at, updated_at fields
    id: uuid pk
    title: str(200) required
```

**Related:** [Archetype](entities.md#archetype), [Settings Archetype](patterns.md#settings-archetype), [Tenant Archetype](patterns.md#tenant-archetype), [Tenant Settings Archetype](patterns.md#tenant-settings-archetype)

---

## Conditions

Boolean expressions used in filters, access rules, attention signals, persona scopes,
workspace region filters, invariants, and approval thresholds. Conditions support
field comparisons, function calls, role checks, date arithmetic, and logical operators.

### Syntax

```dsl
# Comparison operators:
#   =, !=, >, <, >=, <=, in, not in, is, is not

# Logical operators:
#   and, or

# Special values:
#   current_user  - The logged-in user's ID
#   null          - Null/missing value (use with is/is not)
#   true, false   - Boolean literals

# Role check:
#   role(<name>)  - User has the specified role

# Function calls:
#   days_since(<field>)  - Days since a datetime field
#   count(<relation>)    - Count of related records

# Date arithmetic (v0.10.2):
#   today, now           - Current date/datetime
#   today + 7d           - Date plus duration
#   now - 24h            - Datetime minus duration

# List membership:
#   field in [val1, val2, val3]
#   field not in [val1, val2]

# Compound conditions:
#   condition1 and condition2
#   condition1 or condition2
```

### Example

```dsl
# Workspace region filter
overdue_tasks:
  source: Task
  filter: status = open and due_date < today

# Access rule conditions
access:
  read: owner = current_user or is_public = true or role(admin)
  write: owner = current_user and status != closed

# Invariant conditions
invariant: end_date > start_date
invariant: priority != high or due_date != null

# Attention signal condition
attention:
  overdue: due_date < today and status != closed

# Approval threshold
threshold: amount > 1000

# Date arithmetic in filters
recent:
  source: AuditLog
  filter: created_at > now - 24h
```

**Related:** [Attention Signals](ux.md#attention-signals), [Scope](ux.md#scope), [Regions](workspaces.md#regions), [Access Rules](access-control.md#access-rules), [Invariant](entities.md#invariant)

---

## Reserved Keywords

Words reserved by the DAZZLE DSL that cannot be used as field names, enum values, or identifiers. Using these will cause parse errors with suggestions for alternatives.

### Syntax

```dsl
# If you see: "'schedule' is a reserved keyword and cannot be used as an identifier"
# Choose an alternative name:

entity Appointment "Appointment":
  # WRONG: schedule: datetime          # 'schedule' is reserved
  scheduled_at: datetime required       # CORRECT alternative

  # WRONG: status: enum[...]            # 'status' is reserved
  state: enum[pending,confirmed,done]   # CORRECT alternative

  # WRONG: message: text                # 'message' is reserved
  content: text                         # CORRECT alternative
```

### Example

```dsl
# Common reserved words and their alternatives:

# Timing/Scheduling:
#   schedule    -> timing, scheduled_at, appointment_time
#   start       -> start_at, begins_at, start_time
#   created     -> created_at, added_at, initialized_at

# Communication:
#   message     -> notification, msg, content
#   email       -> email_address, contact_email

# Status/State:
#   status      -> state, condition, progress, current_status
#   stage       -> current_stage, phase, step_number

# Data:
#   data        -> payload, content, record_data
#   query       -> search_query, query_text

# Actions:
#   create      -> add, new_record
#   update      -> modify, change
#   delete      -> remove, archive
```

**Related:** [Enum](entities.md#enum), [Field Types](entities.md#field-types), [Entity](entities.md#entity)

---
