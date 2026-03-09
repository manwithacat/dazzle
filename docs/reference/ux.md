# UX Semantic Layer

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

The UX semantic layer expresses WHY interfaces exist and WHAT matters to users, without prescribing HOW to implement it. Personas, scopes, attention signals, and information needs adapt surfaces and workspaces for different roles and contexts.

---

## Persona

A role-based variant that adapts surfaces or workspaces for different user types without code duplication. Controls scope, visibility, and capabilities.

### Syntax

```dsl
for <persona_name>:
  scope: <filter_expression>
  purpose: "<persona-specific purpose>"
  [show: <field1>, <field2>, ...]
  [hide: <field1>, <field2>, ...]
  [show_aggregate: <metric1>, <metric2>, ...]
  [action_primary: <surface_name>]
  [read_only: true|false]
```

### Example

```dsl
for admin:
  scope: all
  purpose: "Full user management"
  show_aggregate: total_users, active_count
  action_primary: user_create

for manager:
  scope: department = current_user.department
  purpose: "Manage department users"
  hide: salary, ssn
  action_primary: user_invite

for member:
  scope: id = current_user.id
  purpose: "View own profile"
  read_only: true
```

### Best Practices

- ✅ Use lowercase role names (admin, manager, member)
- ✅ Base on roles or responsibilities
- ❌ Avoid device-specific personas (mobile, desktop)
- ❌ Avoid preference-based personas (dark-mode-user)

**Related:** [Ux Block](ux.md#ux-block), [Scope](ux.md#scope), [Workspace](workspaces.md#workspace)

---

## Purpose

A single-line statement capturing the semantic intent of a surface or workspace - explaining WHY it exists.

### Syntax

```dsl
purpose: "<single line explanation>"
```

### Example

```dsl
purpose: "Track customer support ticket resolution"
```

### Best Practices

- ✅ Focus on user intent, not implementation
- ✅ Answer 'why does this exist?'
- ✅ Keep to one line
- ❌ Avoid 'List of...' or 'CRUD for...'

**Related:** [Ux Block](ux.md#ux-block)

---

## Attention Signals

Data-driven conditions that require user awareness or action. Signals have severity levels and can trigger actions.

### Syntax

```dsl
attention <critical|warning|notice|info>:
  when: <condition_expression>
  message: "<user-facing message>"
  [action: <surface_name>]
```

### Example

```dsl
attention critical:
  when: due_date < today and status != done
  message: "Overdue task"
  action: task_edit

attention warning:
  when: priority = high and status = todo
  message: "High priority - needs assignment"
  action: task_assign
```

### Best Practices

- ✅ Use for data anomalies requiring action
- ✅ Use for time-sensitive conditions
- ❌ Don't use for purely visual styling
- ❌ Don't overuse - reserve for truly important conditions

**Related:** [Ux Block](ux.md#ux-block), [Conditions](entities.md#conditions)

---

## Scope

Filter expression defining what data a persona can see. Must be either 'all' or a comparison expression.

### Syntax

```dsl
scope: all
scope: <field> = current_user
scope: <field> = current_user.<attribute>
scope: <field> = <value>
scope: <expr1> and <expr2>
scope: <expr1> or <expr2>
```

### Example

```dsl
# Full access for admins
for admin:
  scope: all

# Personal data - matches current user
for member:
  scope: owner_id = current_user

# Team-scoped data
for manager:
  scope: team_id = current_user.team_id

# Combined ownership - "my tasks"
for member:
  scope: assigned_to = current_user or created_by = current_user

# Status-filtered with ownership
for agent:
  scope: status = open and assigned_to = current_user
```

**Related:** [Persona](ux.md#persona), [Conditions](entities.md#conditions)

---

## Information Needs

Specifications for how data should be displayed, sorted, filtered, and searched - the 'what' without the 'how'. On list surfaces these directives control the DataTable's interactive features.

### Syntax

```dsl
show: field1, field2, field3
sort: field1 desc, field2 asc
filter: status, category, assigned_to
search: title, description, tags
empty: "No items found. Create your first item."
```

**Related:** [Ux Block](ux.md#ux-block), [Datatable](surfaces.md#datatable)

---

## Defaults

Default field values for a persona in create/edit forms. Pre-populates fields based on the user's role or context.

### Syntax

```dsl
ux:
  for <persona_name>:
    defaults:
      <field>: <value>
      <field>: current_user
      <field>: current_user.<attribute>
```

### Example

```dsl
surface ticket_create "New Ticket":
  uses entity Ticket
  mode: create

  section main:
    field title
    field description
    field priority

  ux:
    purpose: "Create new support ticket"

    for customer:
      defaults:
        created_by: current_user
        status: open
        priority: medium

    for agent:
      defaults:
        created_by: current_user
        status: open
        assigned_to: current_user

surface order_create "New Order":
  uses entity Order
  mode: create

  ux:
    for sales_rep:
      defaults:
        created_by: current_user
        status: draft
        region: current_user.region
```

**Related:** [Persona](ux.md#persona), [Ux Block](ux.md#ux-block), [Surface](surfaces.md#surface)

---

## Ux Block

Optional metadata on surfaces and workspaces expressing WHY they exist and WHAT matters to users, without prescribing HOW to implement it.

### Syntax

```dsl
ux:
  purpose: "<semantic intent>"

  [show: <field1>, <field2>, ...]
  [sort: <field> [asc|desc], ...]
  [filter: <field1>, <field2>, ...]
  [search: <field1>, <field2>, ...]
  [empty: "<message>"]

  [attention <level>:]
    when: <condition>
    message: "<user message>"
    [action: <surface_name>]

  [for <persona>:]
    [scope: <filter_expression>]
    [purpose: "<persona purpose>"]
    [show: <fields>]
    [hide: <fields>]
    [show_aggregate: <metrics>]
    [action_primary: <surface>]
    [read_only: true|false]
```

### Example

```dsl
ux:
  purpose: "Manage user accounts"

  sort: name asc
  filter: role, is_active
  search: name, email

  attention warning:
    when: days_since(last_login) > 90
    message: "Inactive account"

  for admin:
    scope: all
    action_primary: user_create

  for member:
    scope: id = current_user.id
    read_only: true
```

**Related:** [Purpose](ux.md#purpose), [Information Needs](ux.md#information-needs), [Attention Signals](ux.md#attention-signals), [Persona](ux.md#persona), [Datatable](surfaces.md#datatable)

---
