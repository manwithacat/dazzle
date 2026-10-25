# Runtime UI Capabilities

What the Dazzle runtime actually renders for each DSL construct. Use this to understand
what UI features your DSL declarations produce — the gap between "what can I declare?" and
"what will the user see?"

## Display locale (#1597)

List/detail cells use **`DisplayLocaleProfile`** (not browser Accept-Language):

| Layer | Role |
|-------|------|
| Product default | **en-GB** + `Europe/London` + GBP + friendly `D MMM YYYY` |
| Tenant override | DSL `param locale.timezone` / `locale.date_format` (ParamResolver cascade) |
| Browser cookie / Accept-Language | **gettext only** — never cell dates/numbers |

- **date** fields: calendar day, never TZ-shifted (filing/VAT-safe).
- **datetime** fields: stored UTC (naive = UTC), **displayed** in tenant TZ.
- **`today()` / `days_until` / attention**: shared `calendar_today()` (tenant midnight).
- **`money(CODE)`**: code is authoritative; locale does not convert.

**Editors vs display:** C2.3 list edit for dates uses `input type=date` /
datetime-local (ISO value). Display is day-first en-GB; the edit payload stays
ISO so day/month swap cannot corrupt storage. Do not force `format: raw` on
temporal list fields (`dazzle validate` warns — #1597 E).

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
  as admin:
    scope: all
    purpose: "Manage all tasks"
    action_primary: task_create

  as member:
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

### Search-Select Widget (`source=`)

```dsl
field company_name "Company" source=companies_house_lookup.search_companies
```

**Renders:** Autocomplete input that queries an external API with debounce. Shows results in a dropdown with primary/secondary display fields. Selecting a result can autofill other form fields.

Supported field `key=value` options on create/edit forms: `source`,
`search_trigger` (alias — see below), `widget`, `accept`, `capture`,
`rich_text_toolbar`, `rich_text_max_length`. Other keys are ignored at
render; `dazzle validate` warns.

**`search_trigger=<pack>`** (#1599) is an alias for the pack’s primary search
operation (e.g. `search_trigger=companies_house_lookup` →
`source=companies_house_lookup.search_companies`). Prefer explicit
`source=<pack>.<op>` when you need a non-default search op.

**Pack fragment field maps** (#1600 P1) — API packs may declare per-operation
`[operations.<op>.fragment]` keys (`display_key`, `value_key`, `secondary_key`,
`items_key`, `query_param`, `detail_url`) and `[operations.<op>.field_map]`
aliases (e.g. Companies House search `title` → `company_name`, profile `type` →
`company_type`). Fragment search/select apply the map before reading display
keys, so host dual-lock remappers are not required for shape mismatches.

## Detail Surfaces (`mode: view`)

- Read-only field display
- Edit and Delete action buttons
- Back navigation link
- **State machine transitions** — rendered as action buttons for valid transitions from current state
- **Related groups** — `related name "Title": display: table|status_cards|file_list; show: ChildEntity`
  (reverse-FK tabs under the detail body). Optional `columns: field1, field2, …`
  projects scannable tabs instead of every entity field.
- **Multi-section overview** (#1600 Wedge B) — multiple `section` blocks stack as
  titled field groups (identity / role / timeline …), then related work below.
  Pair with list `open: Entity via fk` (#1603) for queue → context hub.
  Polymorphic clients: `open: first_non_null(company, sole_trader, partnership)`
  or pipe-chained `open: Company via company | SoleTrader via sole_trader`
  (first non-null FK wins; else same-entity fallback).
  Pipe order is **doors** (primary row click + extra hubs), not a reading
  folio (#1666). Author carbon order as stacked `section` blocks on the
  child VIEW. `related` is reverse-FK children only — not parent hops.
- **Status / RAG strip** — `layout: strip` on a VIEW section renders fields as a
  horizontal badge row (compliance status, lifecycle flags).

```dsl
surface client_overview "Client overview":
  uses entity Company
  mode: view
  section header "Client":
    field name "Name"
  section compliance "Compliance":
    layout: strip
    field vat_status "VAT"
    field aml_status "AML"
  related work "Work":
    display: table
    show: Engagement
    columns: name, status, due_date

surface engagement_list "Engagements":
  uses entity Engagement
  mode: list
  open: Company via company   # row → /app/company/{company} hub

# Polymorphic client FKs — first non-null hop (#1600 P2)
surface subscription_list "Subscriptions":
  uses entity ClientSubscription
  mode: list
  open: first_non_null(company, sole_trader, partnership)
  # or: open: Company via company | SoleTrader via sole_trader | Partnership via partnership
```

One `mode: view` surface per entity owns the detail route (`/app/<entity>/{id}`).

## Workspace Layouts

Workspaces group surfaces into navigable sections. The runtime renders:

- **Sidebar navigation** with workspace items
- **Active state highlighting** on current route
- **Collapsible sidebar** on mobile
- App name and branding in the header

## System Endpoints

### `/health`

Always-public endpoint. Returns a JSON object with the current health status of the running app:

```json
{
  "status": "healthy",
  "app": "my_app",
  "version": "0.48.2",
  "dsl_hash": "a3f9c1e2",
  "uptime_seconds": 142.3
}
```

| Field | Description |
|-------|-------------|
| `status` | Always `"healthy"` when the server is up |
| `app` | The `module` name from your DSL |
| `version` | Dazzle framework version |
| `dsl_hash` | First 8 hex chars of the SHA-256 of the compiled IR — changes whenever the DSL changes |
| `uptime_seconds` | Seconds since server startup |

Use `dsl_hash` in deployment pipelines to confirm a new DSL has been loaded without downtime.

### `/_diagnostics`

Admin-only endpoint (requires a session with `admin`, `super_admin`, or `trust_admin` role). Returns a richer snapshot for operational use:

```json
{
  "entities": 12,
  "surfaces": 8,
  "workspaces": 3,
  "features": {
    "auth": true,
    "files": false,
    "feedback_widget": true
  },
  "database": {
    "connected": true,
    "pending_migrations": 0
  },
  "dsl_hash": "a3f9c1e2",
  "version": "0.48.2"
}
```

Returns HTTP 403 for any authenticated user without an admin role. Returns HTTP 401 when no session is present.

## Feedback Widget

When `feedback_widget: enabled` is declared at the module level, the runtime:

1. **Auto-generates** a `FeedbackReport` entity with fields for category, severity, description, auto-captured context (URL, persona, viewport, user agent, console errors, navigation history, page snapshot, screenshot, and annotation data) and, since #1854, the review anchor (`anchor`, `context` as `json`; `surface`; `review_session`). The `category` / `severity` enums are built from the DSL's `categories:` / `severities:` lists; the first declared severity is the default.
2. **Mounts** the widget on every signed-in app page: the app chrome adds `/static/js/feedback-widget.js` plus the meta tags listed below. A user is toasted once per newly resolved report (`notification_sent` is set on display).
3. **Exposes** the widget status in `/_diagnostics` under `features.feedback_widget`.
4. **Runs a server-side policy** on `POST /feedbackreports` (identity stamping, caps, idempotent replay, a per-user rate limit) and extends `GET /feedbackreports` with the filters a reviewer's pins and an agent's read path need.

```dsl
feedback_widget: enabled
  position: bottom-right
  shortcut: backtick
  categories: [bug, ux, copy, data, question, idea]
  severities: [p1, p2, p3, note]
  capture: [url, persona, viewport, user_agent, console_errors, nav_history, page_snapshot]
  review:
    personas: [super_admin, trust_admin]
    shortcut: alt-shift-r
    screenshot: off
```

All fields except `enabled` are optional — the defaults below are used when omitted.

| Option | Default | Description |
|--------|---------|-------------|
| `position` | `bottom-right` | Screen corner for the floating button |
| `shortcut` | `backtick` | Key that toggles the panel. `none` turns it off; also a key name (`f1`, `slash`, `question`) or a combination joined by `+` or `-` (`ctrl+shift+f`, quote values containing `+`). A bare key is ignored while focus is in a text field, select, button, link or contenteditable; a Ctrl/Alt/Meta combination works anywhere. |
| `categories` | `bug, ux, visual, behaviour, enhancement, other` | The `FeedbackReport.category` enum and the widget's category toggles, in this order |
| `severities` | `blocker, annoying, minor` | The `FeedbackReport.severity` enum and the widget's severity toggles; the first value is the default (`minor` when the framework list applies) |
| `capture` | 7 fields | Context automatically attached to each report |
| `review` | absent | The review posture (below). Absent → nobody gets it and the review chord is `none` |

### Review posture (`review:`, #1854)

| Key | Default | Description |
|-----|---------|-------------|
| `personas` | required | Declared persona names that get the review posture (point at an element, leave a note anchored to it, see the page's pins). A name that is not a declared persona fails `dazzle validate`. |
| `shortcut` | `alt+shift+r` | Chord that arms anchor mode; same grammar as `shortcut:`; `none` turns it off. The bare-key rule applies. |
| `screenshot` | `off` | `off` or `optional` — `optional` shows "Attach screenshot" where `getDisplayMedia` exists. The image is stored as a data URL in `screenshot_data` (≤ 1.5 MB). |

A review note is an ordinary `FeedbackReport` whose `anchor` names the element (`dz_anchor` path, a unique CSS selector, a text quote and the rectangle), whose `context` holds the page context (surface, entity, record, workspace, persona, viewport, htmx history, console errors) and whose `surface` / `review_session` are also stored as their own columns so they filter.

### What the page carries

Meta tags on every app-shell page when the widget is mounted (`AppChrome.meta`):

| Meta | Value |
|------|-------|
| `dz-feedback-shortcut` | the panel shortcut (`backtick`, `none`, `ctrl-shift-f`, …) |
| `dz-feedback-categories` | the categories, comma-separated, DSL order |
| `dz-feedback-severities` | the severities, comma-separated; the first is the default |
| `dz-feedback-screenshot` | `off` or `optional` |
| `dz-feedback-review-shortcut` | the review chord, or `none` when there is no `review:` block |
| `dz-feedback-review-personas` | the review personas, comma-separated (absent without `review:`) |

Per request, for a signed-in user: `dz-user-email`, `dz-user-role` (the normalised first role) and, when one of the user's normalised roles is a review persona, `dz-feedback-review` = `1` (absent otherwise).

`<body>` carries the page context as data attributes on authenticated pages (empty values are omitted): `data-dz-surface` (the surface name), `data-dz-entity`, `data-dz-record` (the record id on a detail or edit page of one record), `data-dz-workspace` and `data-dz-persona` (the normalised first role).

### The server contract

`POST /feedbackreports` (JSON; CSRF-exempt; signed-in only — anonymous is refused as before):

- `reported_by` is the session email and `persona` the normalised first role; values in the payload are ignored.
- Caps, each a 422 with a message naming the field: `description` ≤ 4 000 characters; `anchor` + `context` + `page_snapshot` + `console_errors` ≤ 32 KB serialised; `screenshot_data` ≤ 1.5 MB.
- Idempotency (draft-ietf-httpapi-idempotency-key-header): send `Idempotency-Key: <uuid>` (the `idempotency_key` body field, or the legacy `X-Idempotency-Key` header, also works). A replay answers **200** with the stored row and `Idempotent-Replayed: true`, also when two submissions race on the unique column (never a 500). The same key with a different payload is a 422.
- Rate limit per user: 30 a minute and 300 a day, counted in process memory (one budget per worker), **429** with `Retry-After`. This is independent of the `[security] profile` limiter.

`GET /feedbackreports` accepts, besides the generated `page` / `page_size` / `sort` / `search`:

| Query | Meaning |
|-------|---------|
| `status=new,triaged` | one status, or a comma list (unknown values are dropped) |
| `since=2026-10-25T09:00:00Z` | `created_at >=` the ISO 8601 instant (naive = UTC); an unparseable value is a 422 |
| `page_url=`, `surface=`, `review_session=` | exact match |
| `category=`, `severity=`, `reported_by=`, `notification_sent=` | exact match (as before) |

Non-admins see only their own rows (`reported_by = current_user.email`); `admin` / `super_admin` see everything.

The widget is only injected on authenticated pages. Public surfaces (declared with `access: public`) do not receive the widget.
