"""
DAZZLE glossary content.

This module contains the static glossary text for DAZZLE terminology.
"""

GLOSSARY_TEXT = """# DAZZLE Glossary - Terms of Art

This glossary defines DAZZLE DSL concepts including LLM Cognition features (intent, archetypes, examples, relationship semantics), Business Logic features (state machines, invariants, computed fields), and the UX Semantic Layer.

## Core Concepts

### Entity
A domain model representing a business concept (User, Task, Device, etc.). Similar to a database table but defined at the semantic level. Entities have fields with types, constraints, relationships, and business logic.

**Version**: Enhanced in v0.7 with state machines, invariants, computed fields, and access rules. Enhanced in v0.7.1 with intent, domain/patterns, archetypes, examples, and relationship semantics.

**Example (v0.7.1 with LLM cognition features):**
```dsl
entity Ticket "Support Ticket":
  intent: "Track and resolve customer issues through structured workflow"
  domain: support
  patterns: lifecycle, assignment, audit
  extends: Timestamped, Auditable

  id: uuid pk
  title: str(200) required
  status: enum[open,in_progress,resolved,closed]=open
  priority: enum[low,medium,high]=medium
  assigned_to: ref User
  resolution: text
  created_by: ref User required
  comments: has_many Comment cascade

  # Computed field: derived value
  days_open: computed days_since(created_at)

  # State machine: allowed status transitions
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
    read: created_by = current_user or role(agent) or role(manager)
    write: role(agent) or role(manager)

  # Example data
  examples:
    {title: "Login page error", status: open, priority: high}
    {title: "Password reset issue", status: in_progress, priority: medium}
```

### Surface
A UI or API interface definition for interacting with entities. Surfaces define WHAT data to show and HOW users interact with it, without prescribing visual implementation.

**Version**: Enhanced in v0.2 with optional UX block

**Modes:**
- `list` - Display multiple records (table, grid, cards)
- `view` - Display single record details (read-only)
- `create` - Form for creating new records
- `edit` - Form for modifying existing records

**Example (v0.2 with UX block):**
```dsl
surface task_list "Task List":
  uses entity Task
  mode: list

  section main "Tasks":
    field title "Title"
    field status "Status"

  ux:
    purpose: "Track team task progress"
    sort: status asc, title asc
    filter: status, assigned_to

    attention warning:
      when: status = blocked
      message: "Needs attention"
```

### Workspace (NEW in v0.2)
A composition of multiple data views into a cohesive dashboard or information hub. Workspaces aggregate related surfaces and data for specific user needs.

**Version**: NEW in v0.2

**Example:**
```dsl
workspace dashboard "Team Dashboard":
  purpose: "Real-time team overview"

  urgent_tasks:
    source: Task
    filter: priority = high and status != done
    sort: due_date asc
    limit: 5
    action: task_edit
    empty: "No urgent tasks!"

  team_metrics:
    aggregate:
      total: count(Task)
      completed: count(Task where status = done)
      completion_rate: count(Task where status = done) * 100 / count(Task)
```

### Experience
A multi-step user flow or wizard that guides users through a sequence of steps. Experiences define navigation, branching, and error recovery across multiple screens.

**Step kinds**: `surface` (UI screen), `process` (background operation), `integration` (external call)

**Transitions**: Steps declare `on <event> -> step <target>` to define navigation between steps. Common events include `continue`, `back`, `success`, `failure`, `cancel`.

**Example:**
```dsl
experience user_onboarding "User Onboarding":
  start at step welcome

  step welcome:
    kind: surface
    surface onboarding_welcome
    on continue -> step profile

  step profile:
    kind: surface
    surface onboarding_profile
    on continue -> step preferences
    on back -> step welcome

  step preferences:
    kind: surface
    surface onboarding_preferences
    on continue -> step complete
    on back -> step profile

  step complete:
    kind: surface
    surface onboarding_complete
```

### Persona (NEW in v0.2)
A role-based variant that adapts surfaces or workspaces for different user types (admin, manager, member, etc.). Personas control scope, visibility, and capabilities without code duplication.

**Version**: NEW in v0.2

**Example:**
```dsl
ux:
  for admin:
    scope: all
    purpose: "Full task management"
    action_primary: task_create

  for member:
    scope: assigned_to = current_user
    purpose: "Your personal tasks"
    read_only: true
```

### UX Semantic Layer (NEW in v0.2)
Optional metadata on surfaces and workspaces expressing WHY they exist and WHAT matters to users, without prescribing HOW to implement it.

**Version**: NEW in v0.2

**Components:**
- `purpose` - Single-line explanation of semantic intent
- `show`, `sort`, `filter`, `search` - Information needs
- `attention` - Data-driven alerts (critical, warning, notice, info)
- `for {persona}` - Role-based variants

**Example:**
```dsl
ux:
  purpose: "Manage user accounts and permissions"

  sort: name asc
  filter: role, is_active
  search: name, email

  attention warning:
    when: days_since(last_login) > 90
    message: "Inactive account"

  for admin:
    scope: all
  for member:
    scope: id = current_user.id
    read_only: true
```

### Attention Signal (NEW in v0.2)
Data-driven conditions that require user awareness or action. Signals have severity levels and can trigger actions.

**Version**: NEW in v0.2

**Levels**: critical, warning, notice, info

**Example:**
```dsl
attention critical:
  when: due_date < today and status != done
  message: "Overdue task"
  action: task_edit

attention warning:
  when: priority = high and status = todo
  message: "High priority - needs assignment"
```

### Module
A namespace for organizing DSL definitions across multiple files. Modules can depend on other modules and define entities, surfaces, workspaces, and services.

**Example:**
```dsl
module myapp.core

app MyApp "My Application"

entity User "User":
  # ... fields
```

## Field Types

### Basic Types
- `str(N)` - String with max length N
- `text` - Long text (no length limit)
- `int` - Integer number
- `decimal(P,S)` - Decimal number (precision, scale)
- `bool` - Boolean (true/false)
- `date` - Date only
- `time` - Time only
- `datetime` - Date and time
- `uuid` - UUID identifier

### Special Types
- `email` - Email address (with validation)
- `url` - URL (with validation)
- `enum[V1,V2,V3]` - Enumeration of values

### Modifiers
- `required` - Field must have a value
- `optional` - Field can be null (default)
- `unique` - Value must be unique across records
- `pk` - Primary key
- `auto_add` - Auto-set on creation (datetime)
- `auto_update` - Auto-update on save (datetime)

## Surface Modes

### list
Display multiple records in tabular, grid, or card format. Supports sorting, filtering, searching, and bulk actions.

### view
Display single record details in read-only format. Shows complete information for a specific entity instance.

### create
Form for creating new entity records. Defines which fields to collect and validation rules.

### edit
Form for modifying existing entity records. Can control which fields are editable.

## Common Patterns

### CRUD Pattern
Complete create-read-update-delete interface for an entity:
- `{entity}_list` (list mode)
- `{entity}_detail` (view mode)
- `{entity}_create` (create mode)
- `{entity}_edit` (edit mode)

### Dashboard Pattern
Workspace aggregating multiple data views:
- Metrics/KPIs
- Recent activity
- Alerts/attention items
- Quick actions

### Role-Based Access
Persona variants controlling scope and capabilities:
- Admin: full access, all records
- Manager: department/team scope
- Member: own records only

## Business Logic (v0.7)

### State Machine (NEW in v0.7)
Define allowed status/state transitions with optional guards. Prevents invalid state changes and documents workflow rules.

**Syntax:**
```dsl
transitions:
  from_state -> to_state
  from_state -> to_state: requires field_name
  from_state -> to_state: role(role_name)
  * -> to_state: role(admin)  # wildcard: from any state
```

**Guards:**
- `requires field_name` - Field must be non-null before transition
- `role(name)` - User must have the specified role
- No guard - Transition always allowed

**Example:**
```dsl
entity Task "Task":
  status: enum[todo,in_progress,done]=todo
  assigned_to: ref User

  transitions:
    todo -> in_progress: requires assigned_to
    in_progress -> done
    in_progress -> todo
    done -> todo: role(admin)  # Only admin can reopen
```

### Computed Field (NEW in v0.7)
Derived values calculated from other fields. Computed at query time, not stored.

**Syntax:**
```dsl
field_name: computed expression
```

**Functions:**
- `days_since(datetime_field)` - Days since the field's value
- `sum(related.field)` - Sum of related records
- `count(related)` - Count of related records

**Example:**
```dsl
entity Ticket "Ticket":
  created_at: datetime auto_add
  due_date: date

  days_open: computed days_since(created_at)
  days_until_due: computed days_since(due_date)
```

### Invariant (NEW in v0.7)
Cross-field validation rules that must always hold. Enforced on create and update.

**Syntax:**
```dsl
invariant: condition
```

**Operators:**
- Comparison: `=`, `!=`, `>`, `<`, `>=`, `<=`
- Logical: `and`, `or`, `not`
- Null check: `field != null`, `field = null`

**IMPORTANT:** Use single `=` for equality (not `==`) for consistency with access rules.

**Example:**
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

### Access Rules (Enhanced in v0.7)
Inline access control rules defining read/write permissions.

**Syntax:**
```dsl
access:
  read: condition
  write: condition
```

**Expressions:**
- `field = current_user` - Field matches logged-in user
- `role(name)` - User has the specified role
- `field = value` - Field equals literal value
- Combine with `and`, `or`

**Example:**
```dsl
entity Document "Document":
  owner: ref User required
  is_public: bool = false

  access:
    read: owner = current_user or is_public = true or role(admin)
    write: owner = current_user or role(admin)
```

## Extensibility (v0.5)

### Domain Service (NEW in v0.5)
Custom business logic declaration in DSL with implementation in Python/TypeScript stubs. Part of the Anti-Turing extensibility model.

**Kinds**:
- `domain_logic` - Business calculations (tax, pricing)
- `validation` - Complex validation rules
- `integration` - External API calls
- `workflow` - Multi-step processes

**Example:**
```dsl
service calculate_vat "Calculate VAT":
  kind: domain_logic
  input:
    invoice_id: uuid required
    country_code: str(2)
  output:
    vat_amount: decimal(10,2)
    breakdown: json
  guarantees:
    - "Must not mutate the invoice record"
  stub: python
```

### Stub (NEW in v0.5)
Turing-complete implementation of a domain service. Auto-generated from DSL with typed function signatures.

**Commands:**
- `dazzle stubs generate` - Generate stub files
- `dazzle stubs list` - List services and implementation status

### Three-Layer Architecture (NEW in v0.5)
DAZZLE's separation of concerns:
1. **DSL Layer** - Declarative definitions (Anti-Turing: no arbitrary computation)
2. **Kernel Layer** - DNR runtime (CRUD, auth, routing)
3. **Stub Layer** - Custom business logic (Turing-complete)

### Access Rules (NEW in v0.5)
Inline access control rules on entities defining read/write permissions.

**Example:**
```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required

  access:
    read: owner = current_user or shared = true
    write: owner = current_user
```

## LLM Cognition (v0.7.1)

### Intent (NEW in v0.7.1)
A single-line declaration explaining WHY an entity exists in the domain. Helps LLMs understand the semantic purpose of data structures.

**Syntax:**
```dsl
intent: "explanation of entity purpose"
```

**Example:**
```dsl
entity Invoice "Invoice":
  intent: "Represent a finalized billing request from vendor to customer"
```

### Archetype (NEW in v0.7.1)
Reusable template defining common field patterns. Entities can extend archetypes to inherit fields, computed fields, and invariants.

**Syntax:**
```dsl
archetype ArchetypeName:
  field_name: type modifiers
  ...

entity EntityName "Title":
  extends: Archetype1, Archetype2
```

**Example:**
```dsl
archetype Timestamped:
  created_at: datetime auto_add
  updated_at: datetime auto_update

archetype Auditable:
  created_by: ref User
  updated_by: ref User

entity Document "Document":
  extends: Timestamped, Auditable
  id: uuid pk
  title: str(200) required
```

### Domain and Patterns (NEW in v0.7.1)
Semantic tags that classify entities by domain area and behavioral patterns.

**Syntax:**
```dsl
domain: tag
patterns: tag1, tag2, tag3
```

**Common domains:** identity, billing, commerce, support, content, analytics
**Common patterns:** lifecycle, audit, workflow, aggregate_root, lookup, line_items

**Example:**
```dsl
entity Invoice "Invoice":
  domain: billing
  patterns: lifecycle, line_items, audit
```

### Examples Block (NEW in v0.7.1)
Inline example records demonstrating valid data for an entity.

**Syntax:**
```dsl
examples:
  {field: value, field: value, ...}
  {field: value, field: value, ...}
```

**Example:**
```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[todo,in_progress,done]=todo

  examples:
    {title: "Write documentation", status: todo}
    {title: "Fix login bug", status: in_progress}
```

### Relationship Semantics (NEW in v0.7.1)
Ownership relationships between entities with delete behaviors.

**Types:**
- `has_many Entity` - Parent owns multiple children
- `has_one Entity` - Parent owns exactly one child
- `embeds Entity` - Value object embedded in parent
- `belongs_to Entity` - Child side of relationship

**Behaviors:**
- `cascade` - Delete children when parent deleted
- `restrict` - Prevent parent deletion if children exist
- `nullify` - Set FK to null on parent delete
- `readonly` - Cannot modify children through this relationship

**Example:**
```dsl
entity Order "Order":
  items: has_many OrderItem cascade
  shipping_address: embeds Address

entity OrderItem "Order Item":
  order: belongs_to Order
```

### Invariant Message and Code (NEW in v0.7.1)
Human-readable error message and machine-readable error code for invariant violations.

**Syntax:**
```dsl
invariant: condition
  message: "User-friendly error message"
  code: ERROR_CODE
```

**Example:**
```dsl
invariant: end_date > start_date
  message: "End date must be after start date"
  code: BOOKING_INVALID_DATE_RANGE
```

## Best Practices

1. **Entity names** - Use singular nouns (Task, not Tasks)
2. **Surface names** - Use `{entity}_{mode}` pattern (task_list, user_edit)
3. **Workspace names** - Use `{context}_dashboard` or `{role}_workspace`
4. **Persona names** - Use lowercase role names (admin, manager, member)
5. **Field names** - Use snake_case (first_name, not firstName)
6. **Enum values** - Use lowercase with underscores (in_progress, not InProgress)
7. **Purpose statements** - Single line, explain WHY not WHAT
8. **Domain services** - Use for complex calculations, external APIs, multi-step workflows
9. **Intent declarations** - Explain WHY the entity exists (v0.7.1)
10. **Archetypes** - Use for cross-cutting concerns (timestamps, audit, soft delete) (v0.7.1)
11. **Examples** - Include 2-3 representative records per entity (v0.7.1)

## Specs Toolchain

### Spec Generation
Generate API specifications from your DAZZLE AppSpec.

**Commands:**
```bash
dazzle specs openapi -o api.yaml    # Generate OpenAPI spec
dazzle specs openapi -f json        # Generate in JSON format
dazzle specs asyncapi -o async.yaml # Generate AsyncAPI spec
```

### OpenAPI Generation
Generates OpenAPI 3.1 specification from AppSpec including:
- Entity schemas (Base, Create, Update, Read, List)
- CRUD endpoints with proper HTTP methods
- State transition action endpoints
- Enum schemas for enum fields

**Example:**
```bash
dazzle specs openapi -o openapi.yaml
dazzle specs openapi -f json
```

## See Also

- DAZZLE DSL Quick Reference - Syntax examples
- DAZZLE DSL Reference v0.7 - Complete specification
- DAZZLE Extensibility Guide - Stubs and custom logic
- Business Logic Extraction - Design philosophy for v0.7 features
- Ejection Toolchain Guide - Standalone code generation (v0.7.2)
"""


def get_glossary() -> str:
    """Return DAZZLE glossary of terms."""
    return GLOSSARY_TEXT
