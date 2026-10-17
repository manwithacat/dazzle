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

Post-mutation landing is decided by where the request came from (HX-Current-URL):
- create lands on the new record's detail page, unless it ran in a peek drawer or nested on another entity's hub, where it stays (#1667).
- a state transition or edit reloads the page it was issued from, unless the workspace region declares after: next, which lands on the next matching record (#1664).
- delete stays where it was issued: on a list page or workspace the row is removed in place and a toast confirms it. Only a delete from the record's own detail page (/app/<entity>/<id>) leaves, landing on the list surface /app/<entity> (#1790).

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

Buttons on surfaces that trigger navigation or side effects. Actions define what happens on user interaction (submit, click) and where to go next. An action block holds exactly one `on <trigger> -> <outcome>` line and, optionally, a `visible:` line (either order).

#### `visible:` — show an action by record state and role (#1787)

`visible:` takes the same condition grammar as field and section `visible:`: `role(x)`, `has_grant("rel", field)`, comparisons (`=`, `!=`, `<`, `>`, `in [...]`, `is null`), `current_user.<path>` on the value side, FK paths (`client.status`), and `and` / `or` / `not (...)`. It is evaluated per record on the detail page; a false predicate means the action is not rendered. `dazzle validate` checks every `visible:` (actions, sections, fields): fields must exist on the surface's entity, `role(x)` must name a declared persona, and the error names the surface, the action and the predicate.

What a false predicate does depends on the outcome kind:

| Outcome | Hidden on render | Refused on POST |
|---------|------------------|-----------------|
| `integration X action Y` | yes | yes — the manual-trigger route re-evaluates the predicate and answers 403 naming the surface, action and predicate. `Y` must be a mapping with a manual trigger on the surface's entity (validated). |
| `"url" external`, `surface X`, `experience X` | yes | no — the target is a host route (or another surface with its own permit/scope), and that route is the authorization boundary (#1310). `visible:` hides the control; it is not the permission. |

`"url" external` URLs may carry `{id}`, substituted with the record id on the detail page. Surface actions render on detail (`mode: view`) pages; per-row surface actions in `mode: list` and a `transition` outcome kind are parked in [DD-016](../decisions/DD-016-transition-outcome-and-row-surface-actions.md).

#### State-machine transitions are gated by their own guards

Transition buttons on detail pages and list rows come from the entity's `transitions:` block, not from surface actions. Since #1787 they are offered only when the transition's `role(...)` and expression guards pass for the viewer — evaluated by the same validator the PUT runs. `requires <field>` guards and `has_grant()` guards stay PUT-only (the 422 names the field to fill in; grants need a store connection). The state machine stays the permission: put role gating for a transition there, not in a surface action.

#### Model-driven failure modes

`visible:` risks MDF-02 (the rendered control and the enforced permission drift apart) and MDF-13 (dead-end controls). Detectors: `dazzle validate` (fields, personas, integration bindings), the POST-refusal and render-gate tests in `tests/unit/test_action_visibility_1787.py`, and `dazzle inspect page <URL>` to see what a principal is offered. Host-route outcomes are documented as hide-only rather than presented as enforcement.

### Syntax

```dsl
action <action_name> "<Button Label>":
  visible: <condition>                      # optional; either line order
  on submit -> surface <target_surface>
  on click -> "<url, may contain {id}>" external
  on submit -> experience <experience_name>
  on submit -> experience <experience_name> step <step_name>
  on click -> integration <integration_name> action <mapping_name>
```

### Example

```dsl
surface information_request_detail "Information Request":
  uses entity InformationRequest
  mode: view

  section main:
    field title "Title"
    field status "Status"

  action send_letter "Send the request letter":
    visible: status = draft and (role(agent) or role(manager))
    on click -> "/information-requests/{id}/letter" external

  action reconcile "Reconcile with HMRC":
    visible: nino_source = client and role(agent)
    on click -> integration hmrc action verify_nino
```

### Best Practices

- Gate state-machine transitions with role(...) on the transition, not with an action visible: — the SM is the permission source
- For external/surface/experience outcomes the host route must still check permission; visible: only hides the control
- Combine a record-state comparison with role(...) so the action appears only when it can succeed

**Related:** [Surface](surfaces.md#surface), [Experience](experiences.md#experience), [State Machine](entities.md#state-machine)

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

Automatic pagination on list surfaces: page buttons below the table whenever the matched total exceeds the page size, with sort/filter/search state kept across pages. The framework default is 20 rows per page (one constant, DEFAULT_PAGE_SIZE); `page_size: <1-100>` overrides it on a list surface or a workspace region (#1792). A region with `page_size:` fetches that many rows and renders a pager; `limit:` stays a row cap with no pager, and a region cannot set both.

### Syntax

```dsl
# List surface — automatic pages; page_size overrides the default 20.
surface <name> "<Title>":
  uses entity <EntityName>
  mode: list
  page_size: <1-100>
  section main:
    field <field>

# Workspace region — page_size pages with a pager; limit caps with none.
<region_name>:
  source: <EntityName>
  page_size: <1-100>    # rows per page + pager
  limit: <1-1000>       # OR: row cap, no pager (not both)

# Query parameters: ?page=2&page_size=25
```

### Example

```dsl
# List surface - 25 rows per page
surface contact_list "Contacts":
  uses entity Contact
  mode: list
  page_size: 25
  section main:
    field name
    field email
    field status
  ux:
    sort: name asc
    filter: status
    search: name, email

# Workspace region - limit caps a short list; page_size pages a long one
workspace dashboard "Dashboard":
  purpose: "Overview"

  recent_tasks:
    source: Task
    sort: created_at desc
    limit: 5
    display: list

  all_tasks:
    source: Task
    sort: title asc
    page_size: 25
    display: list
```

**Related:** [Datatable](surfaces.md#datatable), [Surface](surfaces.md#surface), [List Columns](workspaces.md#list-columns), [Regions](workspaces.md#regions)

---

## Emits Verification

Emitted-target verification (`emits:`). A custom surface (`mode: custom` / `render: <name>`) renders Turing-complete Python, so the framework can't see the links it emits — a dead "View"/drill button ships green and 404s only on click. Declare the surfaces it links to with `emits:` and the linker verifies each at build time (the custom-mode analogue of `primary_action -> surface`):

```dsl
surface task_board "Board":
  uses entity Task
  mode: custom
  render: kanban_viewer
  emits: [task_detail, task_create]   # surface names this viewer links to
```

Each name must resolve to a **declared surface**; an unresolvable target fails `dazzle validate` with `E_DEAD_EMIT_TARGET`. `emits:` is **opt-in** — a custom surface with no `emits:` is unconstrained; declaring it buys back the dead-target build gate.

**Route-overrides** declare the same contract via a `# dazzle:emits <path>` header alongside `# dazzle:route-override` (each path must match a mounted route):

```python
# dazzle:route-override GET /app/board
# dazzle:emits /app/tasks/{id}
```

See `fixtures/custom_renderer` (the `tag_cloud` surface) for a worked example.

**Related:** [Surface Modes](surfaces.md#surface-modes), [Surface Actions](surfaces.md#surface-actions)

---

## Route Override Contract

Route-override contract (custom routes). A project can hand-write routes in `routes/*.py` with declaration headers. The framework reads these headers statically (no code execution) so it can reason about custom routes. Two guardrails, two postures:

- **RBAC is the line — mandatory.** A handler that touches a domain entity declares `# dazzle:implements <Entity>.<op> via <param>` (permit/scope runs before the body) or fails `dazzle rbac routes --strict`. Novel UI does not skip permit/scope.
- **Response shape + chrome are your declared choice — novel UI welcome.** Declare `# dazzle:returns <kind>` so the framework knows what you return and whether you live in the app shell:

| `# dazzle:returns` | meaning | framework |
|---|---|---|
| `fragment` / `partial` | inner HTML for the app shell | chromed into the shell |
| `page` | a full HTML document (full-bleed / novel UI / island host) | served as-is, **never refused** |
| `json` | a JSON response | passed through |

```python
# routes/board.py
# dazzle:route-override GET /app/board
# dazzle:implements Task.list via task_id   # RBAC (mandatory)
# dazzle:returns fragment                    # lives in the app shell
# dazzle:emits /app/tasks/{id}               # declared link targets (#1392 item 3)

async def handler(request, task_id: str):
    return "<section>…</section>"            # inner HTML — the framework chromes it
```

The framework enforces *consistency with what you declared*: a `fragment`/`partial` that returns a full `<!doctype>` is a loud error; a `page` is untouched. An undeclared HTML override under `/app` gets a one-time advisory (a nudge, never a block). See the [`custom-route-undeclared-response`](https://github.com/manwithacat/dazzle/blob/main/docs/counter-priors/custom-route-undeclared-response.md) counter-prior.

**Related:** [Emits Verification](surfaces.md#emits-verification)

---
