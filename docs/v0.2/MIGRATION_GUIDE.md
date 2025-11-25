# DAZZLE v0.1 to v0.2 Migration Guide

## Overview

DAZZLE v0.2 introduces the UX Semantic Layer while maintaining full backward compatibility with v0.1. This guide helps you migrate existing projects and adopt new features.

## Key Points

✅ **All v0.1 DSL files are valid v0.2 files** - No breaking changes
✅ **UX features are entirely optional** - Add them incrementally
✅ **Existing stacks continue to work** - Generated code remains compatible

## What's New

### 1. UX Block for Surfaces
- Express purpose and information needs
- Define attention signals for important data
- Create persona-specific adaptations

### 2. Workspace Construct
- Compose multiple data views
- Create role-specific dashboards
- Define aggregate metrics

### 3. Enhanced Documentation Structure
- Version directories (v0.1/, v0.2/) instead of file suffixes
- Clearer separation of versions

## Migration Strategy

### Step 1: Update Documentation References

Move from versioned filenames to versioned directories:

```bash
# Old structure
docs/DAZZLE_DSL_REFERENCE_0_1.md
docs/DAZZLE_DSL_GRAMMAR_0_1.ebnf

# New structure
docs/v0.1/DAZZLE_DSL_REFERENCE.md
docs/v0.1/DAZZLE_DSL_GRAMMAR.ebnf
docs/v0.2/DAZZLE_DSL_REFERENCE.md
docs/v0.2/DAZZLE_DSL_GRAMMAR.ebnf
```

### Step 2: Add Purpose Statements

Start by adding purpose declarations to explain why surfaces exist:

```dsl
# Before (v0.1)
surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title
    field status

# After (v0.2)
surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title
    field status

  ux:
    purpose: "Track and manage team tasks"
```

### Step 3: Define Information Needs

Specify how data should be displayed and filtered:

```dsl
ux:
  purpose: "Track and manage team tasks"

  # Add information needs
  show: title, status, priority, assigned_to
  sort: priority desc, due_date asc
  filter: status, assigned_to
  search: title, description
  empty: "No tasks found. Create your first task!"
```

### Step 4: Add Attention Signals

Identify conditions that need user attention:

```dsl
ux:
  # ... previous directives ...

  attention critical:
    when: due_date < today and status != done
    message: "Overdue task"
    action: task_edit

  attention warning:
    when: priority = high and status = todo
    message: "High priority - needs assignment"
    action: task_assign
```

### Step 5: Create Persona Variants

Define role-specific views without duplicating surfaces:

```dsl
ux:
  # ... previous directives ...

  for team_member:
    scope: assigned_to = current_user
    purpose: "Your personal tasks"
    action_primary: task_complete

  for manager:
    scope: all
    purpose: "Team task oversight"
    show_aggregate: total_tasks, overdue_count
    action_primary: task_create

  for viewer:
    scope: all
    read_only: true
```

### Step 6: Compose Workspaces

Create unified experiences from multiple data sources:

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
      total_tasks: count(Task)
      completed_today: count(Task where completed_at = today)
      overdue: count(Task where due_date < today and status != done)
      completion_rate: round(count(Task where status = done) * 100 / count(Task))

  recent_activity:
    source: Task
    sort: updated_at desc
    limit: 10
    display: timeline
```

## Common Migration Patterns

### Pattern 1: Basic List Enhancement

```dsl
# Minimal v0.2 enhancement
surface user_list "Users":
  uses entity User
  mode: list

  section main:
    field name
    field email

  ux:
    purpose: "Manage system users"
    sort: name asc
    search: name, email
```

### Pattern 2: Status-Based Attention

```dsl
# For any entity with status field
ux:
  attention critical:
    when: status = failed
    message: "Failed - needs attention"

  attention warning:
    when: status = pending and days_since(created_at) > 3
    message: "Pending too long"
```

### Pattern 3: Role-Based Filtering

```dsl
# Common pattern for multi-tenant systems
ux:
  for customer:
    scope: customer_id = current_user.customer_id
    purpose: "Your organization's data"

  for admin:
    scope: all
    purpose: "System-wide administration"
```

### Pattern 4: Dashboard Composition

```dsl
# Standard dashboard pattern
workspace my_dashboard "My Dashboard":
  purpose: "Personal productivity overview"

  my_items:
    source: Item
    filter: owner = current_user
    sort: priority desc
    limit: 10

  my_metrics:
    aggregate:
      total: count(Item where owner = current_user)
      completed: count(Item where owner = current_user and status = done)
```

## Testing Your Migration

### 1. Validate Existing DSL

Ensure v0.1 files still validate:

```bash
dazzle validate
```

### 2. Test with UX Features

Add UX blocks incrementally and validate:

```bash
# After adding each UX feature
dazzle validate
dazzle lint --strict
```

### 3. Generate and Compare

Compare generated code before and after:

```bash
# Generate with v0.1
dazzle build --stack django_micro --output build_v01

# Add UX features
# Generate with v0.2
dazzle build --stack django_micro --output build_v02

# Compare outputs
diff -r build_v01 build_v02
```

## Best Practices

### Do's

✅ **Start with purpose** - Always add purpose statements first
✅ **Be semantic** - Express what and why, not how
✅ **Think personas** - Consider different user needs
✅ **Compose thoughtfully** - Group related information in workspaces
✅ **Validate often** - Check each change with `dazzle validate`

### Don'ts

❌ **Don't prescribe visuals** - Avoid color, layout, or style specifications
❌ **Don't duplicate surfaces** - Use personas instead of multiple similar surfaces
❌ **Don't over-signal** - Reserve attention for truly important conditions
❌ **Don't force workspaces** - Only create them for genuine composition needs

## Stack-Specific Notes

### Django Stacks

- UX directives map to Django QuerySets
- Attention signals become CSS classes
- Personas integrate with Django auth
- Workspaces generate dashboard views

### Express/React Stacks

- Information needs configure React hooks
- Attention signals trigger conditional rendering
- Personas check user context
- Workspaces use component composition

### API Stacks

- UX metadata in OpenAPI extensions
- Attention logic in response schemas
- Personas as security schemes
- Workspaces as endpoint groups

## Troubleshooting

### Issue: "Unknown directive 'ux'"

**Cause**: Parser not updated to v0.2
**Solution**: Update DAZZLE to latest version

### Issue: "Field not found in entity"

**Cause**: UX directive references non-existent field
**Solution**: Check field names in entity definition

### Issue: "Invalid condition expression"

**Cause**: Syntax error in when: condition
**Solution**: Check operators and value types

### Issue: "Surface not found for action"

**Cause**: Action references non-existent surface
**Solution**: Verify surface name exists

## Example: Complete Migration

### Original v0.1 File

```dsl
module myapp.core

app MyApp "My Application"

entity Task:
  id: uuid pk
  title: str(200) required
  status: enum[todo,done]=todo
  created_at: datetime auto_add

surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title
    field status
```

### Migrated v0.2 File

```dsl
module myapp.core

app MyApp "My Application"

entity Task:
  id: uuid pk
  title: str(200) required
  status: enum[todo,done]=todo
  priority: enum[low,high]=low
  assigned_to: str(100)
  created_at: datetime auto_add

surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title
    field status
    field priority
    field assigned_to

  ux:
    purpose: "Track team tasks and progress"

    sort: priority desc, created_at desc
    filter: status, assigned_to
    search: title
    empty: "No tasks yet. Create your first task!"

    attention warning:
      when: priority = high and status = todo
      message: "High priority"
      action: task_edit

    for member:
      scope: assigned_to = current_user
      purpose: "Your assigned tasks"

    for manager:
      scope: all
      purpose: "All team tasks"

workspace dashboard "Dashboard":
  purpose: "Task overview"

  high_priority:
    source: Task
    filter: priority = high and status = todo
    sort: created_at asc
    limit: 5
    action: task_edit

  metrics:
    aggregate:
      total: count(Task)
      done: count(Task where status = done)
      todo: count(Task where status = todo)
```

## Getting Help

- Check the [v0.2 Reference](DAZZLE_DSL_REFERENCE.md)
- Review [v0.2 Examples](DAZZLE_EXAMPLES.dsl)
- See implementation in `examples/simple_task/dsl/app_v2.dsl`
- See complex example in `examples/support_tickets/dsl/app_v2.dsl`

## Summary

Migration to v0.2 is:
1. **Optional** - Only adopt features you need
2. **Incremental** - Add features one at a time
3. **Backward compatible** - Existing code continues to work
4. **Semantic** - Focus on meaning, not implementation

Start with purpose statements and gradually add richer UX semantics as your understanding of user needs evolves.
