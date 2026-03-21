# Workspace Layout Customization

**Date:** 2026-03-21
**Status:** Approved
**Author:** Claude + James

## Problem

Workspace dashboards render regions in a fixed order determined by the DSL, with stage-based grid layouts. Users cannot rearrange, hide, or resize regions to suit their workflow. This creates a one-size-fits-all experience that doesn't match SaaS UX norms (Grafana, Datadog, Notion all allow dashboard customization).

## Solution

Add a Notion-style edit mode to workspaces where users can drag-to-reorder regions, show/hide them, and snap-resize their widths. Layout preferences persist per user per workspace via the existing `user_preferences` system. The DSL-defined layout serves as the default; user preferences store a delta.

## Architecture

```
DSL region list --> WorkspaceContext (default layout)
                          |
User preferences --> merge at render time --> final layout
                          |
Template renders grid with Alpine x-data managing edit state
                          |
User customizes --> Alpine state updates --> Save --> dzPrefs.set() --> PUT /auth/preferences
```

### Tech Stack Additions

| Library | Purpose | Size |
|---------|---------|------|
| Alpine.js | Primary client-side reactivity (first-class, used beyond this feature) | ~15KB gzipped |
| alpine-sort | SortableJS wrapper as Alpine plugin for drag-and-drop | ~2KB |
| SortableJS | Drag-and-drop engine (dependency of alpine-sort) | ~15KB gzipped |

All three are vendored into `src/dazzle_ui/static/vendor/` (consistent with existing HTMX vendoring pattern).

### Key Principle

The DSL defines the *default* layout. User preferences store a *delta* (order, hidden set, width overrides). "Reset to default" = delete the preference key. If the DSL adds a new region, it appears at the end of the user's custom order automatically.

## Preference Data Model

### Storage

Single preference key per workspace: `workspace.{workspace_name}.layout`

Value is a JSON string:

```json
{
  "order": ["metrics", "open_tickets", "recent_activity"],
  "hidden": ["audit_log"],
  "widths": {"metrics": 4, "open_tickets": 8}
}
```

### Field Semantics

- **`order`** — Region names in display order. Regions not in this list (e.g. newly added in DSL) are appended at the end in their DSL order.
- **`hidden`** — Region names to suppress in normal mode. Hidden regions still appear in edit mode as compact greyed-out bars with a toggle to re-show.
- **`widths`** — Region name to col-span value (4, 6, 8, or 12). Regions not listed inherit their default width from the stage layout.

### Merge Rules

1. If no preference key exists, render as today (DSL order, stage widths, all visible).
2. Reorder regions to match saved `order`, appending any DSL regions not in the saved list.
3. If a saved `order` references a region that no longer exists in the DSL, silently drop it.
4. Apply `hidden` flag from the `hidden` list.
5. Override `col_span` from the `widths` map.

## Grid Layout

### Uniform 12-Column Grid

All workspaces use `grid grid-cols-12 gap-4` regardless of stage. Each region gets an individual `col_span` value.

The stage system provides *default* spans (preserving current visual appearance):

| Stage | Default span pattern |
|-------|---------------------|
| `focus_metric` | First region: 12, rest: 6 |
| `dual_pane_flow` | All: 6 |
| `scanner_table` | All: 12 |
| `monitor_wall` | All: 4 |
| `command_center` | Cycle: 12, 6, 6, 4, 4, 4 |

### Responsive Behavior

Below `md` breakpoint, all regions collapse to full width:
```html
<div class="col-span-12 md:col-span-{{ region.col_span }}">
```

### RegionContext Additions

```python
@dataclass
class RegionContext:
    # ... existing fields ...
    col_span: int = 12       # resolved column span (4, 6, 8, or 12)
    hidden: bool = False     # user has hidden this region
```

## Edit Mode UX

### Entry/Exit

A "Customize" button in the workspace header toggles edit mode. Alpine.js manages the `editing` boolean on the workspace container:

```html
<div x-data="dzWorkspaceEditor('{{ workspace.name }}', {{ layout_json }})">
```

`layout_json` is the server-rendered current layout state so Alpine initializes with correct values without an additional fetch.

### Edit Mode Controls

**Per-card controls** (visible only when `editing` is true):

- **Drag handle** — Grip icon at top-left of each card. alpine-sort handles reordering via `x-sort` directive on the grid container.
- **Visibility toggle** — Eye icon at top-right. Hidden cards render as compact greyed-out bars showing region title + eye-off icon.
- **Width selector** — 4 buttons below the drag handle: 1/3 (4), 1/2 (6), 2/3 (8), Full (12). Active width is highlighted. Clicking changes the card's span immediately.

**Floating toolbar** (fixed at bottom of viewport, visible in edit mode):

- "Save layout" (primary button) — persists state via `dzPrefs.set()`, exits edit mode
- "Cancel" (secondary) — discards changes, resets Alpine state to server-rendered values, exits edit mode
- "Reset to default" (text/danger) — deletes the preference key and reloads the workspace

### Transitions

- Edit controls fade in/out via Alpine `x-transition`
- SortableJS provides native drag animation
- Width changes animate via Tailwind `transition-all duration-200`

## Server-Side Integration

### `workspace_renderer.py`

New function `apply_layout_preferences(workspace_ctx, user_prefs)`:

1. Read `workspace.{name}.layout` from `user_prefs`
2. If absent, return unchanged
3. Reorder `workspace_ctx.regions` per saved `order`
4. Set `hidden` flag on regions in the `hidden` list
5. Override `col_span` from `widths` map

Called after `build_workspace_context()`, before template rendering.

### `_content.html`

- Outer grid: `grid grid-cols-12 gap-4` (replaces stage-specific grid class)
- Region divs: `col-span-12 md:col-span-{{ region.col_span }}` (replaces `{{ region.grid_class }}`)
- Alpine `x-data` on the workspace container
- `x-sort` on the grid container (active only in edit mode)
- `x-show` on regions for visibility toggling

### No Backend API Changes

The existing `PUT /auth/preferences` endpoint handles persistence. `dzPrefs.set()` handles client-side debouncing. No new endpoints needed.

## Testing Strategy

### Unit Tests

- `test_apply_layout_preferences` — merge logic: reorder, hidden, widths, unknown regions dropped, new DSL regions appended
- `test_col_span_defaults` — each stage produces correct default col_span values
- `test_layout_preference_round_trip` — JSON serialization/deserialization of layout state
- `test_hidden_regions_in_context` — hidden regions present in context but flagged
- `test_merge_with_deleted_dsl_region` — saved order references removed region, silently dropped
- `test_merge_with_new_dsl_region` — new region not in saved order appears at end

### Integration Tests

- Workspace renders correctly with no layout preference (backwards compatibility)
- Workspace renders with saved layout preference (order, hidden, widths applied)
- `PUT /auth/preferences` with layout JSON persists; subsequent page load reflects it
- Reset (delete preference key) restores DSL default layout

### Not Tested (Client-Side Library Behavior)

Drag-and-drop interaction is SortableJS/Alpine library behavior. We test the data contract: preference JSON in, correct HTML out.

## Scope

### In Scope

- Alpine.js + alpine-sort + SortableJS as vendored dependencies
- Edit mode toggle with save/cancel/reset
- Drag-to-reorder regions
- Show/hide regions with toggle
- Width selector (col-span 4/6/8/12 snapping)
- Persistent layout preferences per user per workspace
- Server-side merge of preferences with DSL defaults
- Uniform 12-column grid replacing stage-specific grid classes

### Out of Scope

- Refactoring existing vanilla JS to Alpine components (follow-on work)
- DSL syntax for explicit default widths (stage defaults suffice)
- Admin/role-based layout presets
- Drag-to-resize (drag card edge) — button-based width selector covers this
