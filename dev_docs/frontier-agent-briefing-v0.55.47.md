# Frontier Agent Briefing — Dazzle v0.55.47

**For:** Agents operating dev environments for Penny Dreadful, Aegismark, Cyfuture
**As of:** 2026-04-16
**Covers:** v0.55.35 → v0.55.47 (12 patch releases, 30 commits, 15 cycles of autonomous UX work)

Pull the latest Dazzle before starting. This briefing covers what changed, what you need to know, and what patterns to follow.

---

## 1. What changed (executive summary)

The UX layer underwent a systematic modernisation arc. The three headlines:

1. **DaisyUI is gone from the hot path.** ~210+ DaisyUI class instances migrated to design-token Tailwind. Only 3 remain (stepper `step-primary`). Every status badge, empty state, metric tile, tooltip, filter dropdown, and form field now renders through `hsl(var(--token))` from `design-system.css`. Dark mode adapts automatically.

2. **Persona-variant overrides now work end-to-end.** DSL `for <persona>:` blocks with `empty:`, `hide:`, and `read_only:` declarations actually affect the rendered UI. Before this arc they parsed but silently dropped. Also: new `backed_by` / `link_via` construct on personas for entity binding.

3. **8 new component contracts** govern the template menagerie. Status badge, metrics region, empty state, tooltip, toggle group, plus 6 parking-lot primitives (breadcrumbs, alert banner, accordion, context menu, skeleton patterns, date range picker).

---

## 2. New DSL constructs you should use

### 2.1 Per-persona empty copy

```dsl
surface task_list "Tasks":
  uses entity Task
  mode: list
  ux:
    empty: "No tasks yet"
    for member:
      empty: "You have no assigned tasks"
    for admin:
      empty: "No tasks yet — create one to get started"
```

**How it works:** The compiler collects per-persona overrides into a dict. At request time, `page_routes.py` matches the current user's role and swaps the empty message before rendering. First matching persona wins.

**When to use:** Any surface where different personas see different empty-state copy — especially when one persona can create and another can only view.

### 2.2 Per-persona field hiding

```dsl
surface ticket_create "Create Ticket":
  uses entity Ticket
  mode: create
  section main:
    field title "Title"
    field description "Description"
    field assigned_to "Assigned To"
  ux:
    for customer:
      hide: assigned_to
```

**How it works:** On list surfaces, hidden columns get `column.hidden=True` on the per-request copy. On form surfaces (create AND edit), hidden fields are removed from `req_form.fields`, every section's field list, AND `req_form.initial_values` (prevents hidden-field injection via pre-filled POST bodies).

**When to use:** When a persona shouldn't see or interact with a field. This is the direct fix for "customer sees the Assigned To field" (the EX-029 class of issue).

### 2.3 Per-persona read-only

```dsl
surface task_list "Tasks":
  uses entity Task
  mode: list
  ux:
    for viewer:
      read_only: true
```

**How it works:** On list surfaces: `create_url=None`, `bulk_actions=False`, `inline_editable=[]`. On form surfaces: returns HTTP 403 (forms are inherently mutation affordances).

### 2.4 Persona-entity binding

```dsl
persona tester "Field Tester":
  backed_by: Tester
  link_via: email
```

**How it works:** Declares that persona `tester` maps to entity `Tester` via the `email` field. At `dazzle validate` time, the linker checks: (1) entity exists, (2) link_via field exists on entity, (3) no two personas claim the same backing entity. At runtime (create handler only), when a `ref Tester` field is missing from the request body, the framework auto-injects the backing entity's ID by looking up `SELECT id FROM tester WHERE email = ?`.

**When to use:** Any app where a persona corresponds to a domain entity (Teacher/teacher, Agent/agent, Tester/tester). This replaces the fragile convention of matching auth user IDs to entity IDs in demo seeds.

**Default `link_via`:** `email`. Override to `id` if entity IDs match auth user IDs by convention (zero-cost, no DB lookup).

---

## 3. Template patterns that changed

### 3.1 Status badges — use the macro, never inline

```jinja
{% from 'macros/status_badge.html' import render_status_badge %}
{{ render_status_badge(value=item.status) }}
{{ render_status_badge(value=item.priority, size='sm') }}
{{ render_status_badge(value=item.severity, bordered=true) }}
```

5 tones: `neutral | success | warning | info | destructive`. Derived automatically from the value via `badge_tone` filter (~30 mapped values covering status/priority/severity axes). Never write inline `<span class="... badge_class ...">`.

### 3.2 Empty states — two canonical shapes

**Full** (for list/grid/kanban/tree surfaces):
```jinja
{% include "fragments/empty_state.html" %}
```
Renders SVG icon + copy + optional Create-first CTA (only when `create_url` is set).

**Dense** (for inline card regions — metrics, charts, timelines):
```html
<p class="dz-empty-dense text-[13px] text-[hsl(var(--muted-foreground))]" role="status">
  {{ empty_message | default("No data available.") }}
</p>
```

### 3.3 Ref fields — auto-select from entity list

Plain `ref Entity` fields on create/edit surfaces automatically render as `<select>` dropdowns that fetch options from the entity's list API. No explicit `widget: search-select` needed. Works for every ref field across every app.

### 3.4 Metric tiles — auto-display for aggregate regions

DSL regions with `aggregate:` blocks now auto-infer `display: summary` if no explicit `display:` is set. Previously they silently rendered as empty list regions.

```dsl
workspace admin_dashboard "Admin Dashboard":
  metrics:
    source: Task
    aggregate:
      total_tasks: count(Task)
      done: count(Task where status = done)
```

This will now render as a KPI tile grid (was previously blank).

### 3.5 Number formatting on metric tiles

All aggregate values pass through the `metric_number` Jinja filter: `1234` → `1,234`. Applied automatically via the metrics region template.

---

## 4. Design token compliance

**Rule: every colour in a template must resolve through `hsl(var(--token))`.**

Available tokens (from `design-system.css`):

| Token | Purpose |
|---|---|
| `--background` / `--foreground` | Page body / text |
| `--card` | Card surfaces |
| `--muted` / `--muted-foreground` | Subdued surfaces / text |
| `--border` | Borders |
| `--primary` / `--primary-foreground` | Primary actions |
| `--destructive` / `--destructive-foreground` | Destructive actions |
| `--success` / `--success-foreground` | Positive states |
| `--warning` / `--warning-foreground` | Attention states |
| `--info` / `--info-foreground` | Informational states |
| `--ring` | Focus ring |
| `--popover` | Popover/dropdown surfaces |

**Never use:** `bg-base-100`, `text-base-content`, `btn-primary`, `badge-success`, `alert-info`, `card-body`, or any other DaisyUI class name. The framework has migrated away from DaisyUI; using legacy classes will produce unstyled or mis-styled output.

**Exception:** `step-primary` in the experience wizard stepper (3 instances, pending a dedicated stepper component rewrite).

---

## 5. Canonical class markers for automation

Every governed component now stamps a `dz-*` class marker and `data-dz-*` attributes:

| Component | Marker | Data attributes |
|---|---|---|
| Status badge | `dz-status-badge` | `data-dz-status-tone` |
| Metric tile | `dz-metric-tile` | `data-dz-metric-key`, `data-dz-tile-count` |
| Empty state (full) | `dz-empty-state` | `data-dz-empty-kind="actionable\|read-only"`, `data-dz-empty-cta` |
| Empty state (dense) | `dz-empty-dense` | — |
| Tooltip (rich) | `dz-tooltip` | `data-dz-position`, `data-dz-tooltip-panel` |
| Toggle group | `dz-toggle-group` | `data-dz-toggle-item`, `data-dz-value` |
| Breadcrumbs | `dz-breadcrumbs` | — |
| Alert banner | `dz-alert-banner` | `data-dz-alert-level` |
| Accordion | `dz-accordion` | `data-dz-accordion-item`, `data-dz-section-id` |
| Context menu | `dz-context-menu` | `data-dz-context-menu-panel`, `data-dz-context-menu-item` |
| Skeleton | `dz-skeleton` | — |
| Date range picker | `dz-date-range-picker` | — |
| Ref entity select | — | `data-dz-ref-entity`, `data-dz-ref-api` |
| Region wrapper | — | `data-dz-region`, `data-dz-region-name` |

Use these for Playwright selectors, fitness-engine walkers, and contract assertions.

---

## 6. ARIA and keyboard accessibility

Additions in this arc:

- `role="status"` on every status badge, empty state, and alert banner
- `aria-label` on breadcrumb nav, toggle groups, and icon-only buttons
- `aria-pressed` on toggle-group buttons
- `@keydown.left`/`@keydown.right` arrow-key navigation on toggle groups
- `@keydown.escape.window` on context menus
- `focus-visible:ring-1 focus-visible:ring-[hsl(var(--ring))]` on toggle group buttons (keyboard-only ring, no mouse flash)
- `[x-cloak] { display: none !important; }` CSS rule in `dazzle-layer.css` prevents first-paint flash on Alpine components

---

## 7. Security posture changes

Three latent XSS vectors were closed:

1. **`fragments/tooltip_rich.html`** — `{{ content | safe }}` removed. Content is now HTML-escaped via Jinja autoescape. Trigger blocks still use `| safe` (callers supply markup for the trigger element).

2. **`fragments/accordion.html`** — `{{ section.content | safe }}` removed. Static content is now autoescaped. Structured content should lazy-load from a template endpoint via `section.endpoint`.

3. **`.badge-error` CSS rule** — referenced undefined `--er` variable instead of `--destructive`. Every rendered destructive badge was silently mis-coloured. Fixed.

**Rule:** Never pipe user-supplied or DSL-authored content through `| safe` in a template. Jinja autoescape is the security posture. Only `{% block %}` overrides where the caller explicitly supplies HTML markup should use `| safe`.

---

## 8. PersonaVariant resolver pattern (for framework-level work)

If you need to wire a new PersonaVariant field through to the runtime:

1. **Add a dict** to `TableContext` (or `FormContext`) in `src/dazzle_ui/runtime/template_context.py`
2. **Populate it** in `_compile_list_surface` (or `_compile_form_surface`) from `ux.persona_variants` in `src/dazzle_ui/converters/template_compiler.py`
3. **Resolve it** in `_apply_persona_overrides` (tables) or `_apply_persona_form_overrides` (forms) in `src/dazzle_ui/runtime/page_routes.py`

Both helpers use first-wins role matching with `role_` prefix stripping. The pattern is documented in the helper docstrings.

Currently wired: `empty_message`, `hide`, `read_only`. Remaining unwired (no template consumer exists yet): `purpose`, `show`, `show_aggregate`, `action_primary`, `defaults`, `focus`.

---

## 9. What to watch for

When building apps on v0.55.47:

- **Aggregate regions now render.** If your workspace has `aggregate:` blocks without `display:`, they'll now render as metric tiles (was previously blank). If you intended a list with aggregates, add explicit `display: summary`.

- **Ref fields are now selects.** Every `ref Entity` field on create/edit surfaces renders as a `<select>` dropdown fetching from the entity's list API (max 100 items). If your entity has >100 records, the dropdown will truncate. For large collections, use explicit `source:` with a search endpoint.

- **`backed_by` changes scope-rule semantics.** If you declare `backed_by: Tester`, the create handler will auto-inject the tester's ID for `ref Tester` fields. This may change behaviour for apps that previously relied on the field being empty or manually filled. Test your create flows after adding `backed_by`.

- **Per-persona `hide:` removes fields from forms.** Hidden fields are removed from the POST body, not just visually hidden. If your backend has a `required` constraint on a hidden field and no default/auto-injection, you'll get a 422 validation error. Either: (a) add a `defaults:` block on the persona variant, (b) make the field optional in the DSL, or (c) use `inject_current_user_refs` / `backed_by` auto-injection.

---

## 10. Quick reference: file locations

| Concern | File |
|---|---|
| Component contracts | `~/.claude/skills/ux-architect/components/*.md` |
| Design tokens | `src/dazzle_ui/runtime/static/css/design-system.css` |
| Status badge macro | `src/dazzle_ui/templates/macros/status_badge.html` |
| Empty state fragment | `src/dazzle_ui/templates/fragments/empty_state.html` |
| Region wrapper macro | `src/dazzle_ui/templates/macros/region_wrapper.html` |
| Persona resolver (tables) | `src/dazzle_ui/runtime/page_routes.py` → `_apply_persona_overrides` |
| Persona resolver (forms) | `src/dazzle_ui/runtime/page_routes.py` → `_apply_persona_form_overrides` |
| Backed-by auto-injection | `src/dazzle_back/runtime/route_generator.py` → `resolve_backed_entity_refs` |
| Badge tone map | `src/dazzle_ui/runtime/template_renderer.py` → `_STATUS_TONE_MAP` |
| Metric number formatter | `src/dazzle_ui/runtime/template_renderer.py` → `_metric_number_filter` |
| Aggregate display inference | `src/dazzle_ui/runtime/workspace_renderer.py` line ~260 |
| PersonaVariant IR | `src/dazzle/core/ir/ux.py` → `PersonaVariant` |
| PersonaSpec IR | `src/dazzle/core/ir/personas.py` → `PersonaSpec` |
| Linker validation | `src/dazzle/core/validator.py` → `_validate_persona_backed_by` |
| UX cycle backlog | `dev_docs/ux-backlog.md` |
| UX cycle log | `dev_docs/ux-log.md` |
| Component roadmap | `dev_docs/framework-gaps/2026-04-15-component-menagerie-roadmap.md` |
