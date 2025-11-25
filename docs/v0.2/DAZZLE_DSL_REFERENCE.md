# DAZZLE DSL v0.2 Reference

**Version**: 0.2.0
**Status**: Beta
**Date**: 2025-11-25

## Overview

DAZZLE DSL v0.2 introduces the **UX Semantic Layer** - a way to express user experience semantics without prescribing visual implementation. This version maintains full backward compatibility with v0.1 while adding powerful new constructs for:

- **Information Needs** - Why surfaces exist and what questions they answer
- **Attention Signals** - Data conditions requiring user awareness or action
- **Persona Variants** - Context-specific surface adaptations
- **Workspaces** - Composition of related information needs

## What's New in v0.2

### Major Features

1. **UX Block for Surfaces** - Optional semantic layer for user experience
2. **Workspace Construct** - Compose multiple data views into cohesive experiences
3. **Attention Signals** - Data-driven priority indicators
4. **Persona Variants** - Role-based adaptations without code duplication

### Design Philosophy

Express *what matters to users* and *why*, not *how to display it*. Stack generators interpret semantic intent into appropriate platform idioms.

## Core Constructs

### Module Declaration

```dsl
module myapp.core
```

Declares the module namespace. Required for multi-file projects.

### App Declaration

```dsl
app MyApp "My Application"
```

Defines the application name and optional title.

### Entity (Unchanged from v0.1)

```dsl
entity User "User":
  id: uuid pk
  email: str(200) unique required
  name: str(100) required
  role: enum[Admin, Manager, Member] = Member
  created_at: datetime auto_add
  updated_at: datetime auto_update

  index email
  unique email, name
```

### Surface (Enhanced with UX Block)

#### Basic Surface (v0.1 Compatible)

```dsl
surface user_list "Users":
  uses entity User
  mode: list

  section main "All Users":
    field email "Email"
    field name "Name"
    field role "Role"
```

#### Surface with UX Semantic Layer (v0.2)

```dsl
surface user_list "Users":
  uses entity User
  mode: list

  section main "All Users":
    field email "Email"
    field name "Name"
    field role "Role"
    field last_login "Last Login"

  ux:
    purpose: "Manage user accounts and permissions"

    # Information needs
    show: email, name, role, last_login
    sort: last_login desc, name asc
    filter: role, is_active
    search: email, name
    empty: "No users yet. Invite team members to get started."

    # Attention signals
    attention critical:
      when: days_since(last_login) > 90
      message: "Inactive account"
      action: user_edit

    attention warning:
      when: role = Admin and email_verified = false
      message: "Unverified admin"
      action: user_verify

    # Persona variants
    for admin:
      scope: all
      purpose: "Full user management capabilities"
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

## UX Semantic Layer

### Purpose Declaration

Captures the semantic intent of a surface or workspace.

```dsl
ux:
  purpose: "Single line explaining why this exists"
```

### Information Needs

#### show
Fields to display (overrides section fields if specified).

```dsl
show: field1, field2, field3
```

#### sort
Default sort order. Users can override in UI.

```dsl
sort: field1 desc, field2 asc
```

#### filter
Fields available for filtering.

```dsl
filter: status, category, assigned_to
```

#### search
Fields to include in text search.

```dsl
search: title, description, tags
```

#### empty
Message when no data is available.

```dsl
empty: "No items found. Create your first item to begin."
```

### Attention Signals

Define data-driven priority indicators without prescribing visual style.

```dsl
attention <level>:
  when: <condition>
  message: "<user message>"
  action: <surface_name>  # Optional
```

#### Signal Levels

- `critical` - Requires immediate action
- `warning` - Needs attention soon
- `notice` - Worth noting
- `info` - Informational only

#### Condition Expressions

```dsl
# Simple comparisons
when: status = "Failed"
when: count > 100
when: date < today

# Complex conditions
when: status in [Critical, Severe]
when: days_since(last_update) > 30
when: count(items) = 0 and status != Archived

# Functions
days_since(datetime_field)
count(related_field)
sum(numeric_field)
avg(numeric_field)
```

### Persona Variants

Define role-specific adaptations to surfaces.

```dsl
for <persona_name>:
  scope: <filter_expression>
  purpose: "<persona-specific purpose>"
  show: field1, field2
  hide: field3, field4
  show_aggregate: metric1, metric2
  action_primary: surface_name
  read_only: true/false
```

#### Scope Expressions

```dsl
# All records
scope: all

# Filtered to current user
scope: owner = current_user
scope: team = current_user.team

# Complex filters
scope: status = Active and owner = current_user
```

## Workspace Construct (New in v0.2)

Compose related information needs into unified experiences.

```dsl
workspace dashboard "My Dashboard":
  purpose: "Daily operational overview"

  # Region with entity source
  active_items:
    source: Task
    filter: status = InProgress
    sort: priority desc, due_date asc
    limit: 10
    display: list
    action: task_edit
    empty: "No active tasks."

  # Region with surface source
  recent_updates:
    source: activity_feed
    limit: 20
    display: timeline

  # Metrics region
  key_metrics:
    aggregate:
      total_tasks: count(Task)
      completion_rate: count(Task where status = Done) * 100 / count(Task)
      avg_duration: avg(Task.duration_days)

  # Map visualization
  locations:
    source: Office
    display: map
    filter: is_open = true

  ux:
    for manager:
      purpose: "Team performance dashboard"

    for executive:
      purpose: "Strategic metrics overview"
```

### Region Directives

- `source:` - Entity or surface to pull data from
- `filter:` - Filter expression
- `sort:` - Sort expression
- `limit:` - Maximum records (1-1000)
- `display:` - Visualization mode
- `action:` - Primary action surface
- `empty:` - Empty state message
- `aggregate:` - Computed metrics

### Display Modes

- `list` - Traditional table/list (default)
- `grid` - Card grid layout
- `timeline` - Chronological timeline
- `map` - Geographic visualization (requires lat/lng fields)

### Aggregate Functions

```dsl
aggregate:
  # Count functions
  total: count(Entity)
  filtered: count(Entity where condition)

  # Math functions
  total_value: sum(Entity.amount)
  average_score: avg(Entity.score)
  min_value: min(Entity.value)
  max_value: max(Entity.value)

  # Expressions
  percentage: count(Entity where status = Complete) * 100 / count(Entity)
  rounded: round(avg(Entity.score), 2)
```

## Complete Example

```dsl
module app.main

app TaskManager "Task Management System"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[Todo, InProgress, Done, Blocked] = Todo
  priority: enum[Low, Medium, High, Critical] = Medium
  assigned_to: ref User
  due_date: date
  completed_at: datetime
  created_at: datetime auto_add
  updated_at: datetime auto_update

entity User "User":
  id: uuid pk
  email: email required unique
  name: str(100) required
  role: enum[Member, Lead, Manager] = Member
  team: str(50)

surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title
    field status
    field priority
    field assigned_to
    field due_date

  ux:
    purpose: "Track and manage team tasks"

    sort: priority desc, due_date asc
    filter: status, priority, assigned_to
    search: title, description
    empty: "No tasks yet. Create your first task to get started."

    attention critical:
      when: status = Blocked
      message: "Blocked - needs resolution"
      action: task_unblock

    attention warning:
      when: due_date < today and status != Done
      message: "Overdue"
      action: task_edit

    for member:
      scope: assigned_to = current_user
      purpose: "Your personal task list"
      show: title, status, priority, due_date
      action_primary: task_complete

    for lead:
      scope: assigned_to.team = current_user.team
      purpose: "Team task oversight"
      show_aggregate: blocked_count, overdue_count
      action_primary: task_assign

    for manager:
      scope: all
      purpose: "Full task management"
      action_primary: task_create

workspace team_dashboard "Team Dashboard":
  purpose: "Real-time team performance overview"

  urgent_tasks:
    source: Task
    filter: priority = Critical or status = Blocked
    sort: priority desc
    limit: 5
    action: task_edit
    empty: "No urgent tasks!"

  my_tasks:
    source: Task
    filter: assigned_to = current_user and status != Done
    sort: due_date asc
    limit: 10
    action: task_complete

  team_metrics:
    aggregate:
      total_tasks: count(Task)
      completed_this_week: count(Task where completed_at > 7_days_ago)
      blocked_count: count(Task where status = Blocked)
      completion_rate: round(count(Task where status = Done) * 100 / count(Task))

  recent_completions:
    source: Task
    filter: status = Done
    sort: completed_at desc
    limit: 10
    display: timeline
```

## Migration from v0.1

### Backward Compatibility

All v0.1 DSL files are valid v0.2 files. The UX semantic layer is entirely optional.

### Migration Strategy

1. **Start with purpose** - Add purpose declarations to explain intent
2. **Add information needs** - Specify show, sort, filter, search
3. **Identify attention signals** - What conditions need highlighting?
4. **Consider personas** - Do different roles need different views?
5. **Compose workspaces** - Group related surfaces into dashboards

### Example Migration

#### Before (v0.1)

```dsl
surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title
    field status
    field assigned_to
```

#### After (v0.2)

```dsl
surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title
    field status
    field assigned_to

  ux:
    purpose: "Track team task progress"
    sort: status asc, title asc
    filter: status, assigned_to

    attention warning:
      when: status = Blocked
      message: "Needs attention"
```

## Best Practices

### Purpose Statements

✅ Good:
- "Monitor tree health and coordinate stewardship"
- "Track customer support ticket resolution"
- "Manage inventory levels and reorder points"

❌ Avoid:
- "List of tasks" (too generic)
- "CRUD for users" (implementation detail)
- "Dashboard" (what kind of dashboard?)

### Attention Signals

✅ Use signals for:
- Data anomalies requiring action
- Time-sensitive conditions
- Status changes needing review
- Threshold violations

❌ Don't use for:
- Purely visual styling
- Static categorization
- User preferences
- Decorative elements

### Persona Variants

✅ Good personas:
- Based on roles (admin, manager, member)
- Based on responsibility (owner, reviewer, viewer)
- Based on context (internal, external, public)

❌ Avoid:
- Device-specific (mobile, desktop)
- Preference-based (dark-mode-user)
- Technical (api-user, web-user)

### Workspaces

✅ Compose workspaces for:
- Role-specific dashboards
- Activity centers
- Monitoring views
- Analytical overviews

❌ Don't create workspaces for:
- Single data views
- Navigation menus
- Settings pages
- Static content

## Stack Implementation Notes

### Django

- UX directives map to QuerySet operations
- Attention signals generate CSS classes
- Personas use Django's auth system
- Workspaces become dashboard views

### React

- Information needs configure data hooks
- Attention signals trigger conditional rendering
- Personas check context providers
- Workspaces use component composition

### API/OpenAPI

- UX metadata in OpenAPI extensions
- Attention logic in response schemas
- Personas as security schemes
- Workspaces as grouped endpoints

## Validation Rules

### Required Fields

- Surfaces with UX blocks should have purpose (warning if missing)
- Attention signals must have level, when, and message
- Persona variants must have persona name
- Workspace regions must have source

### Type Compatibility

- Sort fields must exist in entity
- Filter fields must exist in entity
- Condition expressions must be type-safe
- Aggregate expressions must be numeric

### Reference Validation

- Action surfaces must exist
- Source entities/surfaces must exist
- Field references must be valid
- Function calls must use known functions

## Future Enhancements (Post-v0.2)

### Planned for v0.3

- Custom attention functions
- Computed fields in aggregates
- Multi-level workspace composition
- Export/import declarations

### Under Consideration

- Real-time sync specifications
- GraphQL schema generation
- Advanced persona detection
- ML-based attention signals

## Summary

DAZZLE v0.2's UX Semantic Layer enables you to:

1. **Express intent** without implementation details
2. **Adapt to users** without code duplication
3. **Highlight importance** without visual prescription
4. **Compose experiences** without framework lock-in

The goal: Write once, generate everywhere, adapt to everyone.
