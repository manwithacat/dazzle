# Runtime UI Capabilities

What the Dazzle runtime actually renders for each DSL construct. Use this to understand
what UI features your DSL declarations produce — the gap between "what can I declare?" and
"what will the user see?"

## List Surfaces (`mode: list`)

A surface with `mode: list` renders a **DataTable** component. The base table always includes:

- Rows with click-to-navigate to detail view
- Row action menu (View, Edit, Delete) with confirmation dialog on delete
- Pagination (page buttons below table)
- HTMX-powered partial updates (no full page reloads)

### With `sort:` directive

```dsl
ux:
  sort: created_at desc, title asc
```

**Renders:**
- All column headers become **clickable** with hover state
- Active sort column shows a **direction indicator arrow** (up/down)
- Clicking a sorted column **toggles direction** (asc/desc)
- Clicking a different column **sorts by that column** (asc default)
- Sort state is preserved across pagination

The first `sort:` entry becomes the default sort on page load.

### With `filter:` directive

```dsl
ux:
  filter: status, priority, is_active
```

**Renders a filter bar** above the table with per-field inputs:

| Field Type | Rendered As |
|------------|-------------|
| **Enum** field | `<select>` dropdown with all enum values + "All" option |
| **Bool** field | `<select>` dropdown with Yes/No/All options |
| **State machine** field | `<select>` dropdown with all states + "All" option |
| **Text/other** fields | Debounced text input (300ms delay) |

- Filter changes trigger an HTMX request that swaps just the table body
- Multiple filters combine (AND logic)
- Filter state is preserved across pagination
- Empty filter values are ignored (selecting "All" clears that filter)

### With `search:` directive

```dsl
ux:
  search: title, description, tags
```

**Renders:**
- Search input field with **debounced type-ahead** (300ms delay)
- Clear button appears when search has text
- Search targets the fields listed in the directive
- Combines with active filters and sort
- Supported repository operators: `__contains` (text), `__gte`/`__lte` (dates/numbers), `__in` (lists)

**Without `search:`**, no search input is rendered.

### With `empty:` directive

```dsl
ux:
  empty: "No tasks yet. Create your first task!"
```

**Renders:** Custom message in the empty state row when no items match the current filters/search. Without this directive, defaults to "No items found."

### Column Visibility

When a table has **more than 3 columns**, a "Columns" dropdown button appears next to the "New" button. Users can toggle column visibility. Preferences persist in `localStorage`.

### Combined Example

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
```

**Produces:** A table with sortable headers, status dropdown filter, priority dropdown filter, search bar, custom empty message, column visibility toggle, and stateful pagination.

## Attention Signals

```dsl
ux:
  attention critical:
    when: due_date < today and status != done
    message: "Overdue task"
    action: task_edit
```

**Renders:** Row-level visual indicators based on data conditions. Signal levels map to CSS severity classes:

| Level | CSS Class | Typical Use |
|-------|-----------|-------------|
| `critical` | `danger` (red) | Data loss risk, compliance violations |
| `warning` | `warning` (amber) | Approaching deadlines, threshold breaches |
| `notice` | `info` (blue) | Stale data, items needing review |
| `info` | `secondary` (grey) | Informational flags |

Signals with an `action:` link to the referenced surface for quick resolution.

## Persona Variants

```dsl
ux:
  for admin:
    scope: all
    purpose: "Manage all tasks"
    action_primary: task_create

  for member:
    scope: assigned_to = current_user
    purpose: "View my tasks"
    read_only: true
```

**Renders:** Role-filtered views from a single surface definition:

- **`scope:`** — Server-side data filtering (admin sees all, member sees own)
- **`show:`/`hide:`** — Controls which columns/fields are visible per persona
- **`read_only: true`** — Hides create/edit/delete actions
- **`action_primary:`** — Highlights the primary CTA for that persona
- **`defaults:`** — Pre-populates form fields on create surfaces

## Form Surfaces (`mode: create` / `mode: edit`)

Base form rendering:

| Field Type | Rendered As |
|------------|-------------|
| `str` | Text input |
| `text` | Textarea |
| `int`, `decimal`, `money` | Number input |
| `bool` | Checkbox |
| `date` | Date picker |
| `datetime` | Datetime picker |
| `email` | Email input |
| `enum` | Select dropdown with enum values |
| State machine field | Select dropdown with valid states |
| Field with `source:` | **Search-select** widget (debounced autocomplete from external API) |

### Search-Select Widget (`source:`)

```dsl
field company_name "Company" source=companies_house.search_companies
```

**Renders:** Autocomplete input that queries an external API with debounce. Shows results in a dropdown with primary/secondary display fields. Selecting a result can autofill other form fields.

## Detail Surfaces (`mode: view`)

- Read-only field display
- Edit and Delete action buttons
- Back navigation link
- **State machine transitions** — rendered as action buttons for valid transitions from current state

## Workspace Layouts

Workspaces group surfaces into navigable sections. The runtime renders:

- **Sidebar navigation** with workspace items
- **Active state highlighting** on current route
- **Collapsible sidebar** on mobile
- App name and branding in the header
