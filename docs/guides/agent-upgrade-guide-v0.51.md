# Dazzle Agent Upgrade Guide — v0.51.x

**For AI agents working with existing Dazzle apps built before v0.51.**

This guide covers the UX component expansion (v0.51.1–v0.51.8) and how to apply it to existing apps. If you're building a new app, start with `bootstrap` — these features are available out of the box.

---

## What Changed

Dazzle v0.51.x added 35 UX components across 5 tiers, 4 vendored JavaScript libraries, and a `widget=` DSL annotation. The goal: match standard frontend framework coverage without breaking the server-rendered HTML + HTMX + Alpine architecture.

> **Historical note (v0.51 era):** At the time this guide was written, Dazzle rendered HTML via Jinja2 templates. Post-#1042 (v0.67.92, ADR-0023) the template engine is the typed Fragment substrate. The component patterns described here remain conceptually accurate; the on-disk implementation has moved from `.html` templates to typed fragment primitives.

### New Widget Types

You can now annotate surface fields with `widget=` to override default rendering:

```dsl
surface task_create "New Task":
  uses entity Task
  mode: create
  section basic:
    field title "Title"
    field description "Description" widget=rich_text
    field assigned_to "Assignee" widget=combobox
  section details:
    field due_date "Due Date" widget=picker
    field labels "Labels" widget=tags
    field priority "Priority" widget=slider
    field brand_color "Color" widget=color
```

| Widget | Library | Best for | Field types |
|--------|---------|----------|-------------|
| `rich_text` | Quill v2 | Long-form content, comments, descriptions | `text` |
| `combobox` | Tom Select | Entity references with search | `ref`, any with options |
| `tags` | Tom Select | Free-form tagging, labels | `str` |
| `picker` | Flatpickr | Date/datetime selection | `date`, `datetime` |
| `range` | Flatpickr | Date range filtering | `str` only (not `date`) |
| `color` | Pickr | Color selection (hex) | `str(7)` |
| `slider` | DaisyUI range | Numeric scale, ratings | `int`, `decimal` |

### Rules

1. **`widget=` only works on `mode: create` and `mode: edit` surfaces.** View and list surfaces ignore it — their templates don't check `field.widget`.
2. **`widget=range` is for `str` fields only.** Date range pickers return "YYYY-MM-DD to YYYY-MM-DD" — a compound string that can't be stored in a scalar `date` column.
3. **Without `widget=`, fields render with their default input type.** A `text` field gets a `<textarea>`, a `ref` field gets a search-select, a `date` gets a native date picker. The `widget=` annotation upgrades the input to a richer vendored component.

---

## New Template Fragments

These are available in all apps automatically — no DSL changes needed:

| Fragment | What it does | How it activates |
|----------|-------------|-----------------|
| Toast notifications | Auto-dismissing success/error/warning/info messages | Server calls `with_toast(response, message, level)` |
| Alert banner | Full-width dismissible page-level messages | Include `fragments/alert_banner.html` |
| Breadcrumbs | Navigation trail (Home → Project → Task) | Server calls `build_breadcrumb_trail(path, overrides)` |
| Steps indicator | Visual stepper for multi-section forms | Automatic when surface has 2+ sections |
| Accordion | Collapsible sections with optional lazy-load | Include `fragments/accordion.html` with sections list |
| Skeleton loader | Shimmer placeholders during loading | Import macros from `fragments/skeleton_patterns.html` |
| Modal | Server-loaded dialog via `<dialog>` element | `hx-get` targets `#dz-modal-slot` |

### New Alpine Interactive Components

| Component | Trigger | Use case |
|-----------|---------|----------|
| `dzPopover` | Click/hover | Contextual info panels |
| `dzTooltip` | Hover/focus | Rich HTML tooltips (vs. DaisyUI text-only) |
| `dzContextMenu` | Right-click | Asset management, grid actions |
| `dzCommandPalette` | Cmd+K / Ctrl+K | Cross-app navigation, action search |
| `dzSlideOver` | Programmatic | Side panel detail views |
| `dzToggleGroup` | Click | View mode switching, filter groups |

---

## How to Upgrade an Existing App

### Step 1: Identify widget opportunities

Look at your create and edit surfaces. Fields that benefit from widgets:

- **`text` fields for long content** (descriptions, comments, notes) → `widget=rich_text`
- **`ref` fields** (entity references) → `widget=combobox` (adds search)
- **`str` fields used for tags/labels** → `widget=tags` (tokenized input)
- **`date` and `datetime` fields** → `widget=picker` (Flatpickr vs. native)
- **`str(7)` fields storing hex colors** → `widget=color`
- **`int` fields representing scales/ratings** → `widget=slider`

### Step 2: Add widget annotations

Edit your DSL files. Only annotate fields on create and edit surfaces:

```dsl
# BEFORE
surface article_create "New Article":
  uses entity Article
  mode: create
  section main:
    field title "Title"
    field body "Body"
    field category "Category"
    field published_date "Publish Date"

# AFTER
surface article_create "New Article":
  uses entity Article
  mode: create
  section main:
    field title "Title"
    field body "Body" widget=rich_text
    field category "Category" widget=combobox
    field published_date "Publish Date" widget=picker
```

### Step 3: Validate

```bash
dazzle validate
```

Widget annotations are parsed as standard `key=value` options — no grammar changes needed. If validation passes, the widgets will render automatically.

### Step 4: Add related groups (optional)

If your detail surfaces show related entities as flat tabs, consider grouping them:

```dsl
surface project_detail "Project":
  uses entity Project
  mode: view
  section main:
    field name "Name"
    field description "Description"

  related tasks "Tasks":
    display: table
    show: Task

  related files "Documents":
    display: file_list
    show: Attachment

  related milestones "Milestones":
    display: status_cards
    show: Milestone
```

Display modes: `table` (default tabular), `status_cards` (card grid with status badges), `file_list` (download-oriented list).

### Step 5: Check CRUD completeness

Every entity with `permit:` rules for `update` should have a corresponding `mode: edit` surface. Every entity with `permit:` for `list` should have a `mode: list` surface. Missing surfaces mean broken Edit buttons (404) or unreachable entities.

Use the MCP tools to check:

```
dsl operation=analyze    → identifies entities without complete CRUD surfaces
policy operation=coverage → shows which personas can access what
```

### Step 6: Add multi-section forms (optional)

If a create/edit surface has many fields, split into sections for a wizard-style experience:

```dsl
surface task_create "New Task":
  uses entity Task
  mode: create
  section basic:
    field title "Title"
    field description "Description" widget=rich_text
  section assignment:
    field assigned_to "Assignee" widget=combobox
    field priority "Priority"
    field due_date "Due Date" widget=picker
    field labels "Labels" widget=tags
```

When a surface has 2+ sections, Dazzle automatically renders a step indicator and Next/Back/Submit navigation.

---

## Decision Tree: Which Widget?

```
Is the field on a create or edit surface?
├── No → Don't add widget= (it's ignored on view/list)
└── Yes →
    What's the field type?
    ├── text → widget=rich_text (Quill editor)
    ├── ref → widget=combobox (Tom Select with search)
    ├── str (for tags/labels) → widget=tags (tokenized input)
    ├── str(7) (hex color) → widget=color (Pickr)
    ├── date/datetime → widget=picker (Flatpickr)
    ├── int (scale/rating) → widget=slider (range with tooltip)
    └── other → leave default (widget= not needed)
```

---

## Server-Side Helpers

If you're writing custom route handlers or extending the runtime:

```python
from dazzle_http.runtime.response_helpers import with_toast, with_oob

# Append a toast notification to any HTMX response
response = with_toast(response, "Task saved", "success")

# Append an OOB swap (update breadcrumbs, sidebar, etc.)
response = with_oob(response, "breadcrumb-container", breadcrumb_html)
```

```python
from dazzle_http.runtime.breadcrumbs import build_breadcrumb_trail

crumbs = build_breadcrumb_trail("/projects/123/tasks", {
    "/projects/123": "Acme Website",
})
# → [Crumb("Home", "/"), Crumb("Projects", "/projects"),
#    Crumb("Acme Website", "/projects/123"), Crumb("Tasks", None)]
```

```python
from dazzle_http.runtime.asset_manifest import collect_required_assets

# Derive which vendor JS needs to load for this surface
assets = collect_required_assets(surface)
# → {"quill", "tom-select", "flatpickr"}
```

---

## Reference Examples

| Example | Focus | Key patterns |
|---------|-------|-------------|
| `examples/project_tracker` | Project management | rich_text, combobox, tags, picker, kanban, related groups |
| `examples/design_studio` | Brand/design assets | color, slider, multi-select, status_cards, review queue |
| `examples/component_showcase` | Kitchen sink | Every widget type on one form — visual regression reference |
| `examples/simple_task` | Basic CRUD | Baseline without widgets — good before/after comparison |
| `examples/fieldtest_hub` | Multi-entity | 9 entities, 24 surfaces, UX contracts — integration reference |

---

## MCP Tools for Upgrade Assistance

```
# Analyze your DSL for gaps
dsl operation=analyze

# Check RBAC coverage
policy operation=coverage

# Inspect a specific entity
dsl operation=inspect_entity entity=Task

# Check what a surface looks like
dsl operation=inspect_surface surface=task_create

# Validate after changes
dsl operation=validate

# Run UX contracts (requires running server)
dazzle ux verify --contracts
```

---

## Common Pitfalls

1. **Adding `widget=` to view/list surfaces** — They're silently ignored. Only create/edit surfaces render widgets.
2. **Using `widget=range` on `date` fields** — Use `widget=picker` instead. Range mode returns a compound string.
3. **Missing edit surfaces** — If an entity has `update` in `permit:`, add a `mode: edit` surface or the Edit button 404s.
4. **Forgetting `scope:` blocks** — Entities with `permit:` but no `scope:` default-deny on list endpoints (return 0 rows).
5. **Using standalone `enum` as field type** — The parser doesn't resolve `status: MyEnum` references. Use inline `enum[a,b,c]` syntax.
6. **Reserved keywords** — `project`, `icon`, `email`, `create`, `update`, `delete`, `attachments` are reserved. Use alternatives like `parent_project`, `icon_glyph`, `mail`.
