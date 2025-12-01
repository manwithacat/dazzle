"""
DAZZLE glossary content.

This module contains the static glossary text for DAZZLE terminology.
"""

GLOSSARY_TEXT = """# DAZZLE Glossary - Terms of Art (v0.2)

**Version**: 0.2.0
**Date**: 2025-11-25

This glossary defines DAZZLE DSL v0.2 concepts including the new UX Semantic Layer.

## Core Concepts

### Entity
A domain model representing a business concept (User, Task, Device, etc.). Similar to a database table but defined at the semantic level. Entities have fields with types, constraints, and relationships.

**Version**: Unchanged from v0.1

**Example:**
```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[todo,in_progress,done]=todo
  created_at: datetime auto_add
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

## Best Practices

1. **Entity names** - Use singular nouns (Task, not Tasks)
2. **Surface names** - Use `{entity}_{mode}` pattern (task_list, user_edit)
3. **Workspace names** - Use `{context}_dashboard` or `{role}_workspace`
4. **Persona names** - Use lowercase role names (admin, manager, member)
5. **Field names** - Use snake_case (first_name, not firstName)
6. **Enum values** - Use lowercase with underscores (in_progress, not InProgress)
7. **Purpose statements** - Single line, explain WHY not WHAT

## See Also

- DAZZLE DSL Quick Reference - Syntax examples
- DAZZLE DSL Reference v0.2 - Complete specification
"""


def get_glossary() -> str:
    """Return DAZZLE v0.2 glossary of terms."""
    return GLOSSARY_TEXT
