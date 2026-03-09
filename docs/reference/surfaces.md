# Surfaces

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

Surfaces define the UI and API interfaces for interacting with entities. Each surface has a mode (list, view, create, edit, custom) that determines how data is rendered. This page covers surface definitions, sections, modes, actions, pagination, and DataTable rendering.

---

## Surface

A UI or API interface definition for interacting with entities.
Defines WHAT data to show and HOW users interact with it.

### Syntax

```dsl
surface <surface_name> "<Display Name>":
  uses entity <EntityName>
  mode: <list|view|create|edit>

  section <section_name> ["Section Title"]:
    field <field_name> ["Field Label"] [when: <expression>]
    ...

  [ux:]
    [purpose: "<semantic intent>"]
    [... UX directives ...]
```

### Example

```dsl
surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title
    field status

  ux:
    purpose: "Track team task progress"
    sort: status asc
    filter: status, assigned_to

# Conditional field visibility (v0.30.0)
surface task_detail "Task Detail":
  uses entity Task
  mode: view

  section main:
    field title "Title"
    field resolution "Resolution" when: status == "resolved"
    field urgent_note "Urgent" when: days_until(due_date) < 3
```

**Related:** [Entity](entities.md#entity), [Ux Block](ux.md#ux-block), [Surface Modes](surfaces.md#surface-modes), [Datatable](surfaces.md#datatable)

---

## Surface Modes

Interaction modes for surfaces. Each mode renders a different UI:
- list: DataTable with rows, pagination, action menu. Add sort/filter/search in ux: block.
- view: Read-only detail page with Edit/Delete buttons and state machine action buttons.
- create: Form with field inputs mapped by type (str->text input, enum->select, bool->checkbox, ref->search-select).
- edit: Pre-populated form. State machine fields show only valid transitions in dropdown.
- review: Read-only view optimized for approval/review workflows.
- custom: Free-form surface for dashboard panels or specialized views.

### Syntax

```dsl
surface <name> "<Title>":
  uses entity <EntityName>
  mode: <list|view|create|edit|review|custom>
```

### Example

```dsl
# List mode - DataTable with pagination
surface task_list "Tasks":
  uses entity Task
  mode: list
  section main:
    field title "Title"
    field status "Status"
  ux:
    sort: created_at desc
    filter: status
    search: title

# View mode - read-only detail page
surface task_detail "Task Detail":
  uses entity Task
  mode: view
  section main:
    field title
    field description
    field status

# Create mode - form for new records
surface task_create "New Task":
  uses entity Task
  mode: create
  section main:
    field title
    field description

# Edit mode - pre-populated form
surface task_edit "Edit Task":
  uses entity Task
  mode: edit
  section main:
    field title
    field description
    field status
```

**Related:** [Surface](surfaces.md#surface), [Datatable](surfaces.md#datatable)

---

## Section

Groups fields within a surface for visual organization. Sections provide logical grouping and can have display labels. Use to organize complex forms and detail views.

### Syntax

```dsl
section <section_name> ["Display Label"]:
  field <field_name> ["Field Label"]
  field <field_name>
  ...
```

### Example

```dsl
surface contact_detail "Contact Details":
  uses entity Contact
  mode: view

  section main "Contact Information":
    field first_name "First Name"
    field last_name "Last Name"
    field email "Email Address"
    field phone "Phone"

  section address "Address":
    field street
    field city
    field state
    field zip_code "ZIP Code"

  section meta "Record Info":
    field created_at "Created"
    field updated_at "Last Updated"
    field created_by "Created By"

surface contact_edit "Edit Contact":
  uses entity Contact
  mode: edit

  section main:
    field first_name
    field last_name
    field email

  section address:
    field street
    field city
    field state
    field zip_code
```

### Best Practices

- Use descriptive section names (main, address, meta)
- Group related fields together logically
- Use display labels for user-facing section headers
- Keep forms focused - don't show all fields in edit mode
- Use 'main' section for primary/required fields

**Related:** [Surface](surfaces.md#surface), Field, [Surface Modes](surfaces.md#surface-modes)

---

## Surface Actions

Buttons on surfaces that trigger navigation or side effects. Actions define what happens on user interaction (submit, click) and where to go next.

### Syntax

```dsl
action <action_name> "<Button Label>":
  on submit -> surface <target_surface>
  on submit -> experience <experience_name>
  on submit -> experience <experience_name> step <step_name>
  on submit -> integration <integration_name> action <action_name>
```

### Example

```dsl
surface task_create "New Task":
  uses entity Task
  mode: create

  section main:
    field title
    field description

  action save "Create Task":
    on submit -> surface task_list

  action cancel "Cancel":
    on submit -> surface task_list
```

**Related:** [Surface](surfaces.md#surface), [Experience](experiences.md#experience)

---

## Datatable

What the Dazzle runtime renders when a surface has mode: list. The base DataTable
always includes rows, action menu (View/Edit/Delete), pagination, and HTMX partial
updates. Adding sort/filter/search/empty directives in the ux: block enables
interactive features: clickable sort headers, filter dropdowns, debounced search,
column visibility toggle, and custom empty messages.

### Syntax

```dsl
surface <name> "<Title>":
  uses entity <Entity>
  mode: list

  section main:
    field <field1> "<Label>"
    field <field2> "<Label>"

  ux:
    sort: <field> [asc|desc], ...
    filter: <enum_field>, <bool_field>, ...
    search: <text_field1>, <text_field2>, ...
    empty: "<message when no results>"
```

### Example

```dsl
surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title "Title"
    field status "Status"
    field priority "Priority"
    field due_date "Due"

  ux:
    sort: due_date asc
    filter: status, priority
    search: title, description
    empty: "No tasks yet. Create your first task!"

# Produces: sortable column headers, status + priority dropdown filters,
# debounced search input, column visibility toggle (>3 cols), custom empty message
```

### Best Practices

- sort: pick the field users care about most (e.g. created_at desc for recent-first, name asc for alphabetical)
- filter: list enum, bool, and state machine fields — they render as dropdowns
- search: list text/string fields users would type into a search box
- empty: write a friendly message with a call to action (e.g. 'No tasks yet. Create your first task!')
- Every list surface should have a ux: block — the lint rule will warn if missing

**Related:** [Ux Block](ux.md#ux-block), [Surface](surfaces.md#surface), [Information Needs](ux.md#information-needs)

---

## Pagination

Automatic pagination on list surfaces. Renders page navigation buttons below the table. Preserves sort/filter/search state across page transitions. Default 20 items per page.

### Syntax

```dsl
# Pagination is automatic on list surfaces - no DSL configuration needed.
# The runtime renders Previous/Next buttons and page numbers.
# Query parameters: ?page=2&per_page=20
# Sort/filter/search state is preserved across page transitions.

# In workspace regions, use limit: to cap results instead:
<region_name>:
  source: <EntityName>
  limit: <number>       # Max records to show (1-1000)
```

### Example

```dsl
# List surface - pagination is automatic (20 per page)
surface contact_list "Contacts":
  uses entity Contact
  mode: list
  section main:
    field name
    field email
    field status
  ux:
    sort: name asc
    filter: status
    search: name, email

# Workspace region - use limit to cap results
workspace dashboard "Dashboard":
  purpose: "Overview"

  recent_tasks:
    source: Task
    sort: created_at desc
    limit: 5
    display: list
```

**Related:** [Datatable](surfaces.md#datatable), [Surface](surfaces.md#surface)

---
