# UX Component Expansion Design

**Date**: 2026-03-28
**Status**: Approved
**Goal**: Expand Dazzle's native UX component inventory to match standard frontend framework coverage, using the HTMX + Alpine.js + DaisyUI v4 ecosystem.

## Context

Dazzle's UI runtime (Jinja2 + HTMX + Alpine + DaisyUI) has strong coverage for data display (tables, kanban, timeline, metrics, charts, detail views) and forms (multi-step wizard, search-select, file upload, money). However, compared to standard frontend frameworks, there are significant gaps in five categories:

- **Feedback & communication** — no auto-dismissing toasts, banners, or notification patterns
- **Navigation & wayfinding** — no breadcrumbs, command palette, or visual stepper outside forms
- **Overlays & dialogs** — no general-purpose modal, drawer, popover, or rich tooltip
- **Data entry enhancements** — no rich text, tag input, multi-select, combobox, color picker, date range picker
- **Layout & composition** — no accordion, skeleton presets, or collapsible sections

## Architectural Constraints

- ADR-0011: No SPA frameworks. Server-side Jinja2 + HTMX.
- No Node.js build toolchain. All client JS is vendored or CDN-sourced.
- DaisyUI v4 is the CSS component baseline.
- Alpine.js 3.x for client-side interactivity.
- Phased approach: template-level primitives first (Phase B), DSL constructs later (Phase A).

## Design

### Integration Model

Components integrate at the template layer as Jinja2 macros and fragments. The rendering layer knows about them via a `widget:` hint on surface fields, but the DSL doesn't require them yet. This "stock the pantry" approach avoids premature DSL commitments while making components available immediately.

**Widget hint data flow:** `workspace_rendering.py` reads each field's `widget` attribute (if present) from the surface spec and passes it through to the template context as part of the field metadata dict. The `form_field.html` macro switches on `field.widget` (falling back to type-based rendering when no widget is specified). The same field walk feeds `asset_manifest.py` to derive which vendor scripts the page needs.

### Component Tiering

#### Tier 1 — DaisyUI CSS Components (Already Available, Needs Wiring)

These exist in DaisyUI v4 as CSS-only components. Dazzle just needs fragments and template integration.

| Component | DaisyUI class | Needs JS |
|-----------|--------------|----------|
| Alert/Banner | `alert` | No |
| Breadcrumbs | `breadcrumbs` | No |
| Steps (visual stepper) | `steps` | No |
| Accordion | `collapse` / radio group | No |
| Skeleton loader | `skeleton` | No |
| Radial progress | `radial-progress` | No |
| Divider | `divider` | No |
| Stat cards | `stat` | No |
| Bottom nav | `btm-nav` | No |

#### Tier 2 — HTMX-Native Patterns (No New Client JS)

Interaction patterns handled by HTMX with server endpoints and Jinja2 fragments.

| Component | Pattern |
|-----------|---------|
| Auto-dismissing toasts | OOB swap + `remove-me` extension |
| Server-loaded modals | `hx-get` + native `<dialog>.showModal()` |
| Server-loaded drawers | `hx-get` + DaisyUI drawer checkbox |
| Cascading selects | `hx-get` on parent change, swap child `<select>` |
| Inline editing | Click-to-edit with `hx-get`/`hx-post` swap |
| Lazy-loaded sections | `hx-trigger="revealed"` |
| Server-driven wizard | Step-by-step `hx-post`, server holds state |
| SSE notifications | Push toasts/updates via SSE (extension already present) |

**New HTMX extensions to vendor:**

| Extension | Size | Purpose |
|-----------|------|---------|
| `remove-me` | ~1KB | Auto-dismiss toasts, flash messages |
| `class-tools` | ~2KB | Timed CSS transitions without Alpine |
| `multi-swap` | ~2KB | Multi-target updates, cleaner than OOB |
| `path-deps` | ~3KB | Auto-refresh related panels on mutation |

#### Tier 3 — Thin Alpine Wrappers

Interactive components built as Alpine `x-data` components, adapted from Penguin UI / Pines UI patterns.

| Component | Alpine name | ~Lines | Key dependency |
|-----------|-------------|--------|----------------|
| Popover | `dzPopover` | ~30 | `@alpinejs/anchor` |
| Rich tooltip | `dzTooltip` | ~20 | `@alpinejs/anchor` |
| Context menu | `dzContextMenu` | ~40 | `@alpinejs/anchor` |
| Command palette | `dzCommandPalette` | ~80 | `@alpinejs/focus` |
| Slide-over / sheet | `dzSlideOver` | ~30 | `@alpinejs/focus` |
| Toggle group | `dzToggleGroup` | ~20 | None |

**New Alpine plugins to vendor:**

| Plugin | Size | Purpose |
|--------|------|---------|
| `@alpinejs/anchor` | ~4KB | Floating UI positioning for popovers/tooltips |
| `@alpinejs/collapse` | ~2KB | Smooth accordion expand/collapse animation |
| `@alpinejs/focus` | ~3KB | Focus trapping for modals/slide-overs |

**Component contracts (all Tier 3):**
- Registered in `dz-alpine.js` via `Alpine.data('dzComponentName', ...)`
- Configurable via `data-dz-*` attributes
- Emit standard DOM events (`dz:open`, `dz:close`, `dz:select`) for HTMX `hx-trigger`
- Stable DOM structure with `id` attributes for Idiomorph compatibility
- ARIA roles, keyboard navigation, focus trapping

**Component specs:**

`dzPopover`: Anchored floating content panel. Trigger: click or hover. Position: auto via `@alpinejs/anchor`. Content: inline HTML or `hx-get` loaded. Dismiss: click outside, Escape. A11y: `aria-expanded`, `aria-controls`, `role="dialog"`.

`dzTooltip`: Rich content tooltip (upgrades DaisyUI's text-only `data-tip`). Trigger: hover/focus. Position: auto via `@alpinejs/anchor`. Content: HTML. Configurable show/hide delay. A11y: `role="tooltip"`, `aria-describedby`.

`dzContextMenu`: Right-click menu. Trigger: contextmenu event. Position: at cursor via `@alpinejs/anchor`. Content: DaisyUI menu. Dismiss: click outside, Escape, item click. A11y: `role="menu"`, arrow key navigation.

`dzCommandPalette`: Spotlight-style search and action launcher. Trigger: Cmd+K / Ctrl+K. Structure: modal + search input + filtered action list. Data: JSON array or `hx-get` fetched. Features: fuzzy filter, keyboard nav, grouped sections. A11y: `role="combobox"`, `aria-activedescendant`, focus trap.

`dzSlideOver`: Side sheet overlay (distinct from DaisyUI drawer — overlays content, does not push it). Trigger: programmatic open. Position: right edge (configurable). Width: sm/md/lg/xl/full. Content: server-loaded via `hx-get`. A11y: `role="dialog"`, focus trap, `aria-modal`.

`dzToggleGroup`: Exclusive or multi-select button group. Behavior: single-select (radio) or multi-select (checkbox). Rendering: DaisyUI `join` + `btn`. Value synced to hidden input. A11y: `role="radiogroup"` or `role="group"`, `aria-pressed`.

#### Tier 4 — Vendored JS Libraries (Complex Inputs)

Battle-tested libraries wrapped in thin Alpine `x-data` components.

| Component | Library | License | Size | Alpine wrapper |
|-----------|---------|---------|------|----------------|
| Combobox | Tom Select | Apache 2.0 | ~50KB | `dzCombobox` |
| Multi-select | Tom Select | Apache 2.0 | (same) | `dzMultiSelect` |
| Tag input | Tom Select | Apache 2.0 | (same) | `dzTagInput` |
| Date picker | Flatpickr | MIT | ~16KB | `dzDatePicker` |
| Date range picker | Flatpickr | MIT | (same) | `dzDateRange` |
| Color picker | Pickr | MIT | ~20KB | `dzColorPicker` |
| Rich text editor | Quill v2 | BSD-3 | ~40KB | `dzRichText` |
| Slider with tooltip | DaisyUI `range` + vanilla JS | — | ~10 lines | `dzRange` |

Total new vendored JS: ~130KB (Tom Select + Flatpickr + Pickr + Quill). All have UMD/CDN builds — no npm required.

#### Tier 5 — Deferred

| Component | Reason |
|-----------|--------|
| Split pane / resizable panels | Niche, adds split.js dependency |
| Masonry grid | CSS `grid-template-rows: masonry` is coming natively |
| Calendar view | Complex, better as island component |
| Gantt chart | Better as island component |
| Kanban drag-drop reorder | Separate concern from display |

### Component Lifecycle Bridge

A new `dz-component-bridge.js` (~50 lines) manages vendored library lifecycle across HTMX DOM swaps:

```
htmx:beforeSwap  →  destroy vendored instances in swap target
htmx:afterSettle →  Alpine.initTree() + re-init vendored instances
```

Each vendored library registers a mount/unmount pair keyed by `data-dz-widget`:

```html
<input data-dz-widget="datepicker" data-dz-options='{"mode":"range"}' />
```

The bridge scans for `data-dz-widget` elements in swapped DOM and calls the correct init function. This generalizes the existing `dz-islands.js` pattern for `data-island` elements.

### JS Asset Loading Strategy

**Four-phase loading with conditional Phase 3:**

```
Phase 1: Core (blocking, <head>)
  htmx.min.js
  └── htmx extensions (all, including new ones)

Phase 2: Framework (blocking, <head>)
  alpine.min.js
  └── alpine plugins (anchor, persist, sort, collapse, focus)
  └── dz-alpine.js (all dz* component registrations)
      └── Alpine.start()

Phase 3: Vendor widgets (deferred, <body end>, CONDITIONAL)
  tom-select.min.js      — only if page uses combobox/multiselect/tags
  flatpickr.min.js       — only if page uses date picker/range
  pickr.min.js           — only if page uses color picker
  quill.min.js           — only if page uses rich text
  sortable.min.js        — always (existing)
  lucide.min.js          — always (existing)

Phase 4: Bridge (deferred, after Phase 3)
  dz-component-bridge.js
  dz-islands.js
  dz-a11y.js
```

**Conditional loading via server-side manifest.** The rendering layer walks the surface spec and collects widget requirements:

```python
# src/dazzle_back/runtime/asset_manifest.py
required_assets: set[str] = set()
for field in surface.fields:
    if field.widget == "rich_text":
        required_assets.add("quill")
    elif field.widget in ("combobox", "multi_select", "tags"):
        required_assets.add("tom-select")
    elif field.widget in ("picker", "range") and field.type in ("date", "datetime"):
        required_assets.add("flatpickr")
    elif field.widget == "color":
        required_assets.add("pickr")
```

The `base.html` template receives `required_assets` and emits conditional `<script>`/`<link>` tags for Phase 3 assets.

For HTMX swaps that introduce new widgets (e.g., opening a modal with a rich text field), the modal response includes an OOB swap into `<div id="dz-dynamic-assets">` that loads the needed script if not already present.

### Server-Side Patterns

**New modules:**

`response_helpers.py` — Response decorators for OOB swaps:
- `with_toast(response, message, level)` — Appends auto-dismissing toast HTML via OOB swap to `#dz-toast-container`. Levels: success, error, warning, info. Toast element carries `remove-me="5s"`.
- `with_oob(response, target_id, html)` — Generic OOB swap helper.

`breadcrumbs.py` — Route-to-breadcrumb derivation:
- `breadcrumb_trail(request, app_spec) -> list[Crumb]` — Derives trail from route + workspace/surface hierarchy. Updated via OOB swap on every HTMX navigation.

`asset_manifest.py` — Conditional JS loading:
- `collect_required_assets(surface_spec) -> set[str]` — Walks surface fields and collects widget dependencies.

**Extensions to existing modules:**

| Module | Change |
|--------|--------|
| `workspace_rendering.py` | Emit `required_assets` in template context |
| `form_field.html` macro | New widget cases for Tier 4 libraries |
| `base.html` | Add `#dz-toast-container`, `#dz-modal-slot`, `#dz-dynamic-assets`, conditional asset loading, new HTMX extensions in `hx-ext` |

**Server-loaded modal pattern:**
- `base.html` gets `<div id="dz-modal-slot"></div>` at body end
- Trigger: `hx-get="/modal/..." hx-target="#dz-modal-slot" hx-on::after-settle="document.getElementById('dz-modal').showModal()"`
- Server returns complete `<dialog>` element. Form inside uses `hx-post`. On success, server returns updated content + OOB that closes modal.
- Fragment: `fragments/modal.html` — Jinja2 macro wrapping `<dialog>` with DaisyUI classes.

**Server-loaded slide-over pattern:**
- Trigger: `hx-get="/drawer/..." hx-target="#dz-slideover-content" hx-on::after-settle="$dispatch('dz:slideover-open')"`
- `dzSlideOver` Alpine component manages open/close animation and focus trap. Server provides content only.

**Cascading selects:**
- Parent select: `hx-get="/api/options/{child}" hx-trigger="change" hx-target="#{child}-select" hx-include="this"`
- Server returns fresh `<select>` with filtered options.
- `form_field.html` macro detects `cascade_from` hint and wires automatically.

**Inline click-to-edit (enhanced):**
- Display mode: rendered value with `hx-get="/inline-edit/field/123" hx-trigger="click"`
- Edit mode: server returns input + save/cancel. Save is `hx-put`. Cancel is `hx-get` back to display.
- `class-tools` adds brief highlight after save.

**Lazy-loaded accordion:**
```html
<details hx-get="/related/entity/123/section"
         hx-trigger="toggle once"
         hx-target="find .accordion-content">
  <summary>Section Title</summary>
  <div class="accordion-content">
    <span class="loading loading-dots"></span>
  </div>
</details>
```
Content loads on first open, cached in DOM. `once` modifier prevents re-fetching.

### Template Layer Organization

```
templates/
  macros/
    form_field.html          ← extend: datepicker, colorpicker, richtext,
                               combobox, multiselect, tagsinput, range-with-tooltip
  fragments/
    toast.html               ← NEW: auto-dismissing toast (remove-me)
    breadcrumbs.html         ← NEW: server-generated breadcrumb trail
    steps_indicator.html     ← NEW: visual stepper for wizard flows
    alert_banner.html        ← NEW: full-width alert/banner
    command_palette.html     ← NEW: dzCommandPalette
    popover.html             ← NEW: dzPopover
    tooltip_rich.html        ← NEW: rich content tooltip
    context_menu.html        ← NEW: right-click menu
    slide_over.html          ← NEW: side sheet overlay
    skeleton_patterns.html   ← NEW: skeleton presets (table row, card, detail)
    accordion.html           ← NEW: DaisyUI accordion with optional lazy-load
    inline_edit.html         ← EXISTS: enhance with click-to-edit HTMX pattern
  components/
    modal.html               ← NEW: general-purpose server-loaded modal
```

### Static Asset Organization

```
static/
  vendor/
    htmx.min.js              ← exists
    alpine.min.js             ← exists
    sortable.min.js           ← exists
    lucide.min.js             ← exists
    htmx-ext-remove-me.js    ← NEW (~1KB)
    htmx-ext-class-tools.js  ← NEW (~2KB)
    htmx-ext-multi-swap.js   ← NEW (~2KB)
    htmx-ext-path-deps.js    ← NEW (~3KB)
    alpine-anchor.min.js     ← NEW (~4KB)
    alpine-collapse.min.js   ← NEW (~2KB)
    alpine-focus.min.js      ← NEW (~3KB)
    tom-select.min.js        ← NEW (~50KB)
    tom-select.css           ← NEW (~15KB, themed for DaisyUI)
    flatpickr.min.js         ← NEW (~16KB)
    flatpickr.css            ← NEW (~4KB, themed)
    pickr.min.js             ← NEW (~20KB)
    pickr.css                ← NEW (~5KB, nano theme)
    quill.min.js             ← NEW (~40KB)
    quill.snow.css           ← NEW (~10KB, themed)
  js/
    dz-alpine.js             ← extend: register new dz* components
    dz-islands.js            ← exists (unchanged)
    dz-component-bridge.js   ← NEW: HTMX lifecycle bridge
  css/
    dz-widgets.css           ← NEW: DaisyUI-aligned overrides for vendored styles
```

Total new payload: ~170KB JS + ~34KB CSS (before gzip; ~50KB JS + ~10KB CSS after gzip). Phase 3 assets are conditionally loaded — most pages load only the ~8KB of new HTMX extensions and Alpine plugins.

## Testing Strategy

### Three Testing Layers

**Layer 1: Component unit tests.** Each fragment/macro renders correct HTML, attributes, and ARIA roles. Fast Python tests (`pytest`, no browser). Verifies the template layer in isolation.

**Layer 2: Integration tests.** Server helpers produce correct responses, HTMX swap lifecycle works, component bridge re-initializes widgets after DOM replacement.
- `response_helpers.py`: assert `with_toast()` appends correct OOB HTML
- `breadcrumbs.py`: assert correct trail for known routes
- `asset_manifest.py`: assert correct assets collected for given surface specs
- Modal/drawer endpoints: assert valid `<dialog>` / content HTML
- Cascading selects: assert filtered options
- Component bridge: E2E browser tests — render widget, trigger HTMX swap, assert widget re-initializes

**Layer 3: Coverage-in-context.** Every component appears in at least 2 example apps, in different configurations, exercised by real user flows.

### New Example Apps

**`examples/project_tracker`** — Project management (teams, projects, tasks, milestones, comments, attachments).

Naturally exercises: rich text (project descriptions, comments), date range picker (milestones, sprints), tag input (task labels), combobox (assignee search), command palette (cross-project navigation), breadcrumbs (Home → Project → Milestone → Task), slide-over (task detail from list), inline editing (task title/status/assignee), cascading selects (project → milestone → dependency), toasts (save confirmations), accordion (task sections: description, comments, attachments, history), server-loaded modal (new task from any context), skeleton loaders (dashboard metrics).

**`examples/design_studio`** — Brand/design asset management (brands, color palettes, assets, campaigns, feedback).

Naturally exercises: color picker (brand colors), multi-select (asset categories, campaign targeting), rich text (campaign briefs), toggle group (asset type filters, view modes), context menu (right-click on asset grid), popover (color swatch preview), rich tooltip (color value hover), rating (feedback scoring), slider/range (quality settings), date picker (campaign dates), steps indicator (asset approval workflow), stat cards (campaign metrics), lazy accordion (version history).

### Coverage Matrix

Every component appears in at least 2 example apps:

| Component | project_tracker | design_studio | Existing examples |
|-----------|:-:|:-:|:-:|
| Alert/banner | x | x | fieldtest_hub |
| Breadcrumbs | x | x | — |
| Steps indicator | x | x | pra |
| Accordion | x | x | — |
| Skeleton loader | x | x | — |
| Toast (auto-dismiss) | x | x | — |
| Server-loaded modal | x | x | — |
| Slide-over | x | x | — |
| Inline edit | x | — | simple_task |
| Cascading selects | x | — | fieldtest_hub |
| Command palette | x | x | — |
| Popover | — | x | fieldtest_hub |
| Rich tooltip | — | x | ops_dashboard |
| Context menu | x | x | — |
| Toggle group | — | x | ops_dashboard |
| Combobox | x | x | — |
| Multi-select | x | x | — |
| Tag input | x | — | support_tickets |
| Date picker | x | x | — |
| Date range | x | — | — |
| Color picker | — | x | — |
| Rich text | x | x | — |
| Rating | — | x | — |
| Slider/range | — | x | — |

### Component Showcase

`examples/component_showcase` — A gallery page rendering every component in every configuration. Dazzle's Storybook equivalent (server-rendered). Quick-check for visual regression and component documentation reference.

### UX Contract Extension

Each new example app gets a full UX contract suite (like fieldtest_hub's 121 contracts). Contracts verify:
- Component renders on correct surface for correct persona
- Widget type matches field spec (rich text field renders Quill, not textarea)
- HTMX interactions produce correct responses (toast after save, breadcrumb after navigation)

The `/ux-converge` command runs contracts across all examples for project-wide regression detection.

## Rollout Phases

### Phase 1: Foundation

No new visible components. Lays the infrastructure.

- Vendor new HTMX extensions (`remove-me`, `class-tools`, `multi-swap`, `path-deps`)
- Vendor new Alpine plugins (`@alpinejs/anchor`, `@alpinejs/collapse`, `@alpinejs/focus`)
- Build `dz-component-bridge.js`
- Build `asset_manifest.py` + conditional loading in `base.html`
- Build `response_helpers.py` (`with_toast`, `with_oob`)
- Add `#dz-toast-container`, `#dz-modal-slot`, `#dz-dynamic-assets` to `base.html`
- Tests: unit tests for response helpers, asset manifest derivation

### Phase 2: Tier 1 + Tier 2 (Server-Driven Components)

Highest-value phase — fills the most visible gaps with zero new JS dependencies beyond Phase 1.

- Wire DaisyUI components: alert/banner, breadcrumbs, steps, accordion, skeleton, divider, stat, radial progress
- Build HTMX patterns: toast system, server-loaded modal, breadcrumb generation, inline edit enhancement, lazy-loaded accordion, cascading selects
- Build `breadcrumbs.py`
- Tests: UX contracts for all new fragments, integration tests for server helpers

### Phase 3: Tier 3 (Alpine Interactive Components)

- Build and register: `dzPopover`, `dzTooltip`, `dzContextMenu`, `dzCommandPalette`, `dzSlideOver`, `dzToggleGroup`
- Tests: template rendering assertions + E2E browser tests

### Phase 4: Tier 4 (Vendored Widget Libraries)

- Vendor Tom Select, Flatpickr, Pickr, Quill
- Build Alpine wrappers: `dzCombobox`, `dzMultiSelect`, `dzTagInput`, `dzDatePicker`, `dzDateRange`, `dzColorPicker`, `dzRichText`, `dzRange`
- Extend `form_field.html` macro with new widget cases
- Build `dz-widgets.css` (DaisyUI-aligned theme overrides)
- Tests: smoke tests per widget, HTMX swap survival tests

### Phase 5: Example Apps & Coverage

- Build `examples/project_tracker`
- Build `examples/design_studio`
- Build `examples/component_showcase`
- UX contract suites for each
- Verify coverage matrix — every component in 2+ apps

Each phase ends with a version bump and is independently shippable.
