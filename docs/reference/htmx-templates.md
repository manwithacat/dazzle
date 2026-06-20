# HTMX Template Specification

**Version:** 1.0.1 | **Status:** Active for HTMX patterns; **template-engine references stale** — see banner below (the "Customising rendered output" section is current as of #1297) | **MCP Resource:** `dazzle://docs/htmx-templates`

> **Status note (2026-05-25):** This document captures the HTMX interaction patterns Dazzle's UI runtime emits (server-rendered HTML, `hx-*` attributes, composable fragments). Those patterns are unchanged. The *template engine* mentioned below (Jinja2 `ChoiceLoader`, `TemplateResponse` etc.) was retired in #1042 (v0.67.92). Rendering now goes through the **typed Fragment substrate** — see [ADR-0023](../adr/0023-template-emission-patterns.md) and [`typed-fragment-pilot-guide.md`](../typed-fragment-pilot-guide.md). The conceptual HTMX-patterns content below still applies; the Jinja2-specific override mechanism does not.

## Purpose

This specification enables LLM coding agents to produce rich, powerful HTMX interfaces with minimal context. Design principles:

1. **Server Authority** — Server renders HTML, client displays it
2. **Visible Behavior** — All interactions are `hx-*` attributes, not hidden JavaScript
3. **Predictable Structure** — Same patterns across all entities
4. **Composable Fragments** — Complex UIs from simple, reusable parts

## Quick Reference

### HTMX Attributes

| Pattern | Attributes | Use Case |
|---------|-----------|----------|
| **Search** | `hx-get` `hx-trigger="keyup changed delay:400ms"` `hx-target` | Debounced input |
| **Navigate** | `hx-get` `hx-push-url="true"` `hx-target="body"` | Row click |
| **Delete** | `hx-delete` `hx-confirm` `hx-target="closest tr"` `hx-swap="outerHTML"` | Inline delete |
| **Submit** | `hx-post` `hx-target` `hx-swap="outerHTML"` | Form submission |
| **Autofill** | `hx-swap-oob="outerHTML"` | Multi-field update |

### Target Naming

| Type | Pattern | Example |
|------|---------|---------|
| Table body | `#{entity}-table-body` | `#contact-table-body` |
| Pagination | `#{entity}-pagination` | `#contact-pagination` |
| Search results | `#{field}-results` | `#company-search-results` |
| Form field | `#field-{name}` | `#field-company_number` |
| Spinner | `#{context}-spinner` | `#search-spinner` |

---

## Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    COMPONENTS                           │
│  Full page content: list_view, detail_view, form        │
│  One component per surface mode (~100-150 lines)        │
└────────────────────────┬────────────────────────────────┘
                         │ include
┌────────────────────────▼────────────────────────────────┐
│                    FRAGMENTS                            │
│  HTMX-swappable partials: table_rows, search_select     │
│  Addressable by DOM id, communicate via events (~20-50) │
└────────────────────────┬────────────────────────────────┘
                         │ call
┌────────────────────────▼────────────────────────────────┐
│                    MACROS                               │
│  Rendering helpers: form_field, status_badge            │
│  Pure functions: params in, HTML out (~10-30 lines)     │
└─────────────────────────────────────────────────────────┘
```

### Layer Rules

- **Components** define layout, include fragments, set up swap targets
- **Fragments** are swapped by HTMX, emit/listen to events, have formal contracts
- **Macros** are pure rendering, never called by HTMX directly

---

## Fragment Contracts

Each fragment has a formal interface. Discover via MCP:

```
mcp__dazzle__dsl(operation="list_fragments")
```

### Contract Structure

```yaml
fragment: search_select
template: fragments/search_select.html

params:
  required:
    - field.name
    - field.label
    - field.source.endpoint
  optional:
    - field.placeholder
    - field.source.debounce_ms  # default: 400
    - field.source.min_chars    # default: 3

emits:
  - itemSelected    # Fired on selection

listens: []

swap_targets:
  - "#{{ field.name }}-results"

oob_targets:       # Fields populated on selection
  - "#field-{{ autofill_target }}"
```

### Standard Events

| Event | Meaning | Emitted By |
|-------|---------|------------|
| `itemSelected` | User selected from list/dropdown | search_select, table row |
| `formSaved` | Form successfully submitted | form components |
| `rowDeleted` | Table row removed | delete button |
| `searchCleared` | Search input cleared | search_input |

---

## Cognition Strategies

### Before Modifying Templates

1. **Check fragment contracts**: `mcp__dazzle__dsl(operation="list_fragments")`
2. **Inspect surface spec**: `mcp__dazzle__dsl(operation="inspect_surface", name="...")`
3. **Understand entity**: `mcp__dazzle__dsl(operation="inspect_entity", name="...")`

### Modification Patterns

| Task | Where to Edit | Lines Changed |
|------|---------------|---------------|
| Add table column | Component: add `<th>` and `<td>` | ~4 |
| Add search filter | Fragment: add input with `hx-get` | ~8 |
| Add delete button | Fragment: add button with `hx-delete` | ~5 |
| Add form field | Macro call: add `{{ form_field(field) }}` | ~1 |
| Add autofill | Server: add OOB fragment to response | ~10 |

### Context Window Efficiency

Templates fit in small context windows:

| Component | Lines | Rationale |
|-----------|-------|-----------|
| List view | 100-150 | Table + search + pagination targets |
| Form | 80-120 | Field iteration + validation display |
| Fragment | 20-50 | Single responsibility |
| Macro | 10-30 | Pure rendering |

**Full feature**: component + 2-3 fragments ≈ 300 lines

---

## OOB Swap Pattern

For updating multiple DOM elements from one response:

```html
<!-- Server response -->

<!-- Primary swap: goes to hx-target -->
<div id="company-selected" class="alert alert-success">
  Selected: Acme Ltd
</div>

<!-- OOB swaps: go to their own element ids -->
<input id="field-company_number" value="12345678"
       hx-swap-oob="outerHTML" readonly />
<input id="field-company_status" value="active"
       hx-swap-oob="outerHTML" readonly />
```

Server renders OOB fields using the **same macro** as the original form for consistency.

---

## Event Communication

Fragments communicate through events, not shared state:

```html
<!-- Fragment A emits -->
<button hx-get="..."
        hx-on::after-request="htmx.trigger(this, 'itemSelected')">

<!-- Fragment B listens -->
<div hx-get="..."
     hx-trigger="itemSelected from:closest form">
```

### Communication Channels

1. **HTMX Events** — `hx-trigger="eventName from:selector"`
2. **OOB Swaps** — Server response includes multiple fragments
3. **URL Parameters** — For cross-page state (pagination, filters)

---

## DSL Integration

### Surface → Template Mapping

```
surface contact_list           → components/list_view.html
  mode: list                      └── fragments/table_rows.html
  section main:                   └── fragments/table_pagination.html
    field first_name

surface contact_edit           → components/form_edit.html
  mode: edit                      └── fragments/form_errors.html
  section info:                   └── macros/form_field.html
    field company_name:
      source: companieshouse      └── fragments/search_select.html
```

### Field Type → Rendering

| DSL Type | Renders As |
|----------|------------|
| `string`, `text` | `<input type="text">` via form_field macro |
| `email` | `<input type="email">` via form_field macro |
| `date` | `<input type="date">` via form_field macro |
| `enum` | `<select>` via form_field macro |
| `boolean` | Checkbox via form_field macro |
| Field with `source:` | search_select fragment |

---

## Dependencies

The workspace runtime ships HTMX inline and links a single bundled
stylesheet from the server:

```html
<script src="/static/vendor/htmx.min.js"></script>
<link rel="stylesheet" href="/styles/dazzle.css">
```

Site/marketing pages additionally load DaisyUI + Tailwind via CDN for
legacy `stat-value` / `bg-base-*` class names emitted by
`site_section_builder` — see `docs/CSS_MIGRATION_GUIDE.md`.

### Vanilla JS Scope (Limited)

Vanilla JS manages **UI state only**: dropdown open/close, modal visibility, accordion state.

JS does **NOT** manage: form data, API responses, selection state. HTMX handles all server communication.

---

## Non-Goals

This specification does not cover:

- Virtual DOM or client-side diffing
- Client-side state management
- Build toolchains (webpack, vite)
- TypeScript (server-rendered HTML needs no client types)
- Real-time collaboration / WebSockets
- Offline-first / service workers

---

## Customising rendered output

> **Removed mechanism (ADR-0023 / #1042, v0.67.92).** Earlier versions
> let projects override framework Jinja templates by dropping a
> same-named file in `templates/` (a `ChoiceLoader` + `dz://` /
> `{# dazzle:override … #}` / `{# dazzle:blocks … #}` scheme, and a
> `dazzle overrides scan|check|list` CLI). **None of that exists any
> more** — there is no Jinja engine to load project templates, and the
> `dazzle overrides` commands were removed. If you are looking for the
> old "override `components/detail_view.html`" recipe, it is dead code;
> use a custom renderer instead (below). This was the dead end behind
> [#1297](https://github.com/manwithacat/dazzle/issues/1297).

Rendering now goes through the **typed Fragment substrate** (pure
Python → HTML). Two supported extension points replace template
overrides:

### 1. Custom renderers (`render: <name>`)

Declare `render: <name>` on a surface and register a handler. This is
the canonical way to take over rendering for a specific surface —
including a **per-entity detail viewer** on a `mode: view` surface. The
handler can delegate back to the framework's generic rendering:

```python
from dazzle.page.runtime import render_detail_view

class ManuscriptViewer:
    def render(self, surface, ctx) -> str:
        detail = ctx["detail_context"]            # original DetailContext (#1297)
        return f'<section>{self._panel(detail.item)}{render_detail_view(detail)}</section>'
```

See [`fixtures/custom_renderer/`](https://github.com/manwithacat/dazzle/tree/main/fixtures/custom_renderer)
for the full two-halves-of-the-contract recipe (link-time `[renderers]
extra` allowlist + runtime `register(...)`) and the worked per-entity
detail-viewer (`app/render/feedback_detail.py`).

### 2. Custom primitives / renderers in `dazzle.toml`

`[renderers] extra` (allowlist names) and the `@primitive` registry let
projects add reusable renderers and Fragment primitives. Inspect what's
registered with `dazzle inspect renderers` / `dazzle inspect primitives
--runtime`.

For the substrate itself, see [ADR-0023](../adr/0023-template-emission-patterns.md)
and [`typed-fragment-pilot-guide.md`](../typed-fragment-pilot-guide.md).
