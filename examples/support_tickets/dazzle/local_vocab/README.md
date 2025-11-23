# Support Tickets - Vocabulary Reference

This directory contains advanced vocabulary entries for support ticket and help desk systems.

## Available Entries

### Data Patterns (7 entries)

#### `audit_fields` (macro)
Standard audit timestamp fields.
```dsl
@use audit_fields()
# Expands to:
# created_at: datetime auto_add
# updated_at: datetime auto_update
```

#### `ticket_status_enum` (macro)
Ticket lifecycle status field (new, open, pending, resolved, closed).
```dsl
@use ticket_status_enum()
# Expands to: status: enum[new,open,pending,resolved,closed]=new

@use ticket_status_enum(field_name=state, default_value=open)
# Expands to: state: enum[new,open,pending,resolved,closed]=open
```

#### `priority_enum` (macro)
Priority field with urgent level (low, medium, high, urgent).
```dsl
@use priority_enum()
# Expands to: priority: enum[low,medium,high,urgent]=medium
```

#### `user_reference` (alias)
Reference to User entity with configurable requirement.
```dsl
@use user_reference(field_name=assigned_to)
# Expands to: assigned_to: ref User

@use user_reference(field_name=created_by, required=true)
# Expands to: created_by: ref User required
```

#### `ticket_reference` (alias)
Reference to Ticket entity.
```dsl
@use ticket_reference()
# Expands to: ticket: ref Ticket required

@use ticket_reference(field_name=parent_ticket, required=false)
# Expands to: parent_ticket: ref Ticket
```

#### `assignment_fields` (macro)
Assignment tracking fields (assigned_to, assigned_at).
```dsl
@use assignment_fields()
# Expands to:
# assigned_to: ref User
# assigned_at: datetime optional

@use assignment_fields(user_required=true)
# Makes assigned_to required
```

#### `resolution_fields` (macro)
Resolution tracking fields (resolved_at, resolved_by, resolution_notes).
```dsl
@use resolution_fields()
# Expands to:
# resolved_at: datetime optional
# resolved_by: ref User
# resolution_notes: text
```

### Entity Templates (2 entries)

#### `comment_entity` (pattern)
Comment/note entity template for discussions.
```dsl
@use comment_entity(parent_entity=Ticket)
# Generates complete Comment entity with:
# - id, ticket ref, author, content, timestamps

@use comment_entity(
  entity_name=Note,
  parent_entity=Issue,
  parent_field=issue
)
```

#### `ticket_entity` (pattern)
Full-featured ticket entity with status, priority, assignment, and resolution tracking.
```dsl
@use ticket_entity()
# Generates complete Ticket entity with:
# - id, title, description
# - status, priority
# - created_by, assigned_to, assigned_at
# - resolved_at, resolved_by, resolution_notes
# - timestamps

@use ticket_entity(entity_name=Issue)
# Creates Issue entity instead of Ticket
```

### UI Patterns (4 entries)

#### `crud_surface_set` (pattern)
Complete CRUD surface set (4 surfaces: list, view, create, edit).
```dsl
@use crud_surface_set(entity_name=Ticket, title_field=title)
```

#### `ticket_dashboard` (macro)
Ticket list/dashboard surface with status and priority columns.
```dsl
@use ticket_dashboard()
# Creates ticket_dashboard surface

@use ticket_dashboard(surface_name=support_dashboard)
# Custom surface name
```

#### `ticket_detail_view` (macro)
Comprehensive ticket detail view with all sections.
```dsl
@use ticket_detail_view()
# Creates ticket_detail with sections:
# - Ticket Information
# - Assignment
# - Resolution
# - Audit
```

#### `comment_form` (macro)
Simple comment/reply form for adding comments.
```dsl
@use comment_form()
# Creates comment_create form

@use comment_form(entity_name=Note)
# For Note entity instead of Comment
```

### Workflow Patterns (1 entry)

#### `ticket_lifecycle` (pattern)
Basic ticket lifecycle experience (create → assign → resolve → close).
```dsl
@use ticket_lifecycle()
# Generates complete experience with 4 steps:
# - create_ticket
# - assign_ticket
# - resolve_ticket
# - close_ticket

@use ticket_lifecycle(experience_name=support_flow)
```

## Usage Examples

### Example 1: Full Ticket System from Templates
```dsl
module support.core
app support_app "Support Tickets"

# Define User entity
entity User "User":
  id: uuid pk
  name: str(200) required
  email: email unique?
  @use audit_fields()

# Generate complete Ticket entity
@use ticket_entity()

# Generate Comment entity for ticket discussions
@use comment_entity(parent_entity=Ticket)

# Generate all ticket surfaces
@use crud_surface_set(entity_name=Ticket, title_field=title)
@use ticket_dashboard()
@use ticket_detail_view()

# Generate comment surfaces
@use crud_surface_set(entity_name=Comment, title_field=content)
@use comment_form()

# Add ticket workflow
@use ticket_lifecycle()
```

### Example 2: Custom Ticket Entity with Standard Patterns
```dsl
entity Ticket "Support Ticket":
  id: uuid pk
  title: str(200) required
  description: text required

  # Use vocabulary for common patterns
  @use ticket_status_enum()
  @use priority_enum()
  @use user_reference(field_name=created_by, required=true)
  @use assignment_fields()
  @use resolution_fields()
  @use audit_fields()
```

### Example 3: Multi-Entity Support System
```dsl
# Tickets
@use ticket_entity()
@use ticket_dashboard()
@use ticket_detail_view()

# Comments on tickets
@use comment_entity(parent_entity=Ticket)
@use comment_form()

# Knowledge base articles
entity Article "Article":
  id: uuid pk
  title: str(200) required
  content: text required
  @use user_reference(field_name=author, required=true)
  @use audit_fields()

# Link tickets to articles
entity TicketArticle "Related Article":
  id: uuid pk
  @use ticket_reference()
  article: ref Article required
  @use audit_fields()
```

### Example 4: Workflow-Centric System
```dsl
@use ticket_entity()

# Create ticket workflow
@use ticket_lifecycle()

# Could add more workflows:
# - escalation_flow
# - approval_flow
# - feedback_flow
```

## Commands

```bash
# List all vocabulary entries
dazzle vocab list

# List by category
dazzle vocab list --scope data
dazzle vocab list --scope ui
dazzle vocab list --scope workflow

# Show details of specific entry
dazzle vocab show ticket_entity
dazzle vocab show comment_entity
dazzle vocab show ticket_lifecycle

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
- `enum`, `status`, `priority`, `ticket` - Status and priority fields
- `reference`, `user`, `ticket` - Entity relationships
- `assignment`, `resolution`, `tracking` - Ticket tracking patterns
- `entity`, `comment`, `discussion`, `template`, `pattern` - Entity templates
- `crud`, `ui`, `dashboard`, `form` - User interface patterns
- `workflow`, `lifecycle`, `experience` - Process patterns

```bash
# Filter by tag
dazzle vocab list --tag ticket
dazzle vocab list --tag workflow
dazzle vocab list --tag ui
```

## Stability Levels

- **stable** - Production-ready, recommended for use (most entries)
- **experimental** - New patterns, may change (ticket_lifecycle)

## Comparison with Simple Task Example

The Support Tickets vocabulary includes everything from Simple Task plus:

**Additional Data Patterns**:
- `ticket_status_enum` - More detailed status lifecycle
- `ticket_reference` - Reference ticket entities
- `assignment_fields` - Track who/when assigned
- `resolution_fields` - Track resolution details

**Additional Entity Templates**:
- `comment_entity` - Discussion/notes on tickets
- `ticket_entity` - Full-featured ticket with all tracking

**Additional UI Patterns**:
- `ticket_dashboard` - Pre-configured ticket list view
- `ticket_detail_view` - Comprehensive detail view with sections
- `comment_form` - Comment/reply form

**Workflow Patterns**:
- `ticket_lifecycle` - Complete ticket workflow experience

## Best Practices

1. **Start with Entity Templates**: Use `ticket_entity` and `comment_entity` for quick setup
2. **Customize as Needed**: Start with templates, then customize with individual patterns
3. **Use Workflows**: The `ticket_lifecycle` provides a good starting point for processes
4. **Combine Patterns**: Mix entity templates with individual field patterns for flexibility
5. **Tag-Based Discovery**: Use tags to find related patterns quickly
