# Simple Task - Vocabulary Reference

This directory contains reusable vocabulary entries for task management applications.

## Available Entries

### Data Patterns (4 entries)

#### `audit_fields` (macro)
Standard audit timestamp fields.
```dsl
@use audit_fields()
# Expands to:
# created_at: datetime auto_add
# updated_at: datetime auto_update
```

#### `status_enum` (macro)
Standard status enum field (todo, in_progress, done).
```dsl
@use status_enum()
# Expands to: status: enum[todo,in_progress,done]=todo

@use status_enum(field_name=state, default_value=in_progress)
# Expands to: state: enum[todo,in_progress,done]=in_progress
```

#### `priority_enum` (macro)
Standard priority enum field (low, medium, high).
```dsl
@use priority_enum()
# Expands to: priority: enum[low,medium,high]=medium

@use priority_enum(default_value=high)
# Expands to: priority: enum[low,medium,high]=high
```

#### `user_reference` (alias)
Reference to User entity.
```dsl
@use user_reference(field_name=assigned_to)
# Expands to: assigned_to: ref User

@use user_reference(field_name=owner, required=true)
# Expands to: owner: ref User required
```

### UI Patterns (5 entries)

#### `crud_surface_set` (pattern)
Complete CRUD surface set (4 surfaces: list, view, create, edit).
```dsl
@use crud_surface_set(entity_name=Task, title_field=title)
# Generates: task_list, task_detail, task_create, task_edit
```

#### `list_surface` (macro)
Simple list surface for an entity.
```dsl
@use list_surface(entity_name=Task, display_field=title)
```

#### `detail_surface` (macro)
Simple detail/view surface for an entity.
```dsl
@use detail_surface(entity_name=Task, display_field=title)
```

#### `create_form` (macro)
Simple create form surface for an entity.
```dsl
@use create_form(entity_name=Task, main_field=title)
```

#### `edit_form` (macro)
Simple edit form surface for an entity.
```dsl
@use edit_form(entity_name=Task, main_field=title)
```

### Entity Templates (1 entry)

#### `timestamped_entity` (pattern)
Complete entity template with ID, title, description, status, and timestamps.
```dsl
@use timestamped_entity(entity_name=Task)
# Generates complete entity with:
# - id: uuid pk
# - title: str(200) required
# - description: text
# - status: enum[todo,in_progress,done]=todo
# - created_at/updated_at timestamps
```

## Usage Examples

### Example 1: Quick CRUD Application
```dsl
module my_app.core
app my_app "My App"

# Define entity with timestamps
@use timestamped_entity(entity_name=Task)

# Generate all CRUD surfaces
@use crud_surface_set(entity_name=Task, title_field=title)
```

### Example 2: Custom Entity with Standard Patterns
```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  @use status_enum()
  @use priority_enum()
  @use user_reference(field_name=assigned_to)
  @use audit_fields()
```

### Example 3: Selective Surface Generation
```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text

# Generate only specific surfaces
@use list_surface(entity_name=Task, display_field=title)
@use create_form(entity_name=Task, main_field=title)
```

## Commands

```bash
# List all vocabulary entries
dazzle vocab list

# Show details of specific entry
dazzle vocab show crud_surface_set

# Expand DSL file to see generated code
dazzle vocab expand dsl/app.dsl

# Validate and build with vocabulary
dazzle validate
dazzle build
```

## Tags

Find entries by tag:
- `common` - Frequently used patterns
- `audit`, `timestamp` - Time tracking
- `enum`, `status`, `priority` - Enumeration fields
- `reference`, `user` - Entity relationships
- `crud`, `ui` - User interface patterns
- `form`, `list`, `detail` - Specific surface types
- `entity`, `template` - Complete entity templates

```bash
# Filter by tag
dazzle vocab list --tag common
dazzle vocab list --tag ui
```

## Stability Levels

All entries in this manifest are marked as **stable** - they are production-ready and recommended for use.
