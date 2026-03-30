# Dashboard Builder — Configurable Card-Based Workspaces

**Date:** 2026-03-30
**Status:** Approved
**Author:** Claude + James
**Supersedes:** 2026-03-21-workspace-layout-customization-design.md

## Problem

The current workspace customization system (v0.51.16) allows reorder, hide/show, and 2-width snap (6 or 12 columns) via Alpine Sort. AegisMark's agents cannot make meaningful progress building fully customizable dashboards because:

1. Width options are too rigid (only Column/Full — no finer granularity)
2. No drag-to-resize — width changes are click-only buttons
3. No way to add/remove cards — users can only rearrange DSL-defined regions
4. Alpine Sort plugin doesn't support drag-from-external-container (palette)
5. Edit mode toggle adds friction — modern dashboards are always-interactive

## Solution

Replace the workspace editor with a **dashboard builder**. Users compose dashboards from a DSL-defined card catalog using drag-and-drop, snap-grid resize, and an "Add Card" widget picker. Breaking change — the old `workspace-editor.js` and Alpine Sort plugin are removed.

## Architecture

```
DSL workspace block          User's saved layout (v2)
    │                              │
    ▼                              ▼
Card Catalog                 Layout Store
(available widgets)          (user_preferences)
    │                              │
    └──────────┬───────────────────┘
               ▼
        Dashboard Renderer
    ┌──────────────────────────┐
    │  12-col CSS Grid         │
    │  ┌─────┐ ┌──────────┐   │
    │  │Card │ │  Card     │   │
    │  │ 4col│ │  8col     │   │
    │  └─────┘ └──────────┘   │
    │  ┌──────────────────┐   │
    │  │  Card  (12col)   │   │
    │  └──────────────────┘   │
    │  ┌──── + Add Card ────┐ │
    │  └────────────────────┘ │
    └──────────────────────────┘
```

### Tech Stack

| Library | Purpose | Replaces |
|---------|---------|----------|
| SortableJS (vendored) | Drag-to-reorder, drag-from-palette | Alpine Sort plugin |
| Custom resize handler | Drag-to-resize with snap grid | Column/Full buttons |
| Alpine.js (existing) | Reactivity, component state | Unchanged |
| HTMX (existing) | Lazy-load card content | Unchanged |
| DaisyUI (existing) | Card styling | Unchanged |

### What stays the same

- 12-column CSS Grid (responsive: 1 col mobile, 12 col desktop)
- `user_preferences` table for persistence
- HTMX lazy-loading of card content via region endpoints
- DaisyUI card styling
- Region templates (list, grid, metrics, kanban, timeline, etc.)
- Detail drawer for click-through
- Context selector for multi-scope filtering
- SSE live updates

## Data Model

### Layout Schema v2

Stored as JSON in `user_preferences` under key `workspace.{name}.layout`:

```json
{
  "version": 2,
  "cards": [
    {
      "id": "card-1",
      "region": "critical_issues",
      "col_span": 6,
      "row_order": 0
    },
    {
      "id": "card-2",
      "region": "metrics",
      "col_span": 6,
      "row_order": 1
    },
    {
      "id": "card-3",
      "region": "critical_issues",
      "col_span": 12,
      "row_order": 2
    }
  ]
}
```

**Fields:**
- `id` — unique per card instance (e.g., `card-{sequential}`). Allows the same region to appear multiple times.
- `region` — references a DSL-defined workspace region name (the catalog entry).
- `col_span` — snap points: 3, 4, 6, 8, 12.
- `row_order` — integer for vertical ordering within CSS grid flow.
- `version: 2` — distinguishes from v1 layouts.

### Default layout

When no saved preference exists, DSL regions auto-populate as cards in DSL-defined order with their default `col_span` values. Existing workspaces look identical until the user customizes.

### Catalog endpoint

`GET /api/workspaces/{name}/catalog` returns available regions:

```json
{
  "regions": [
    {"name": "critical_issues", "title": "Critical Issues", "display": "list", "entity": "IssueReport"},
    {"name": "metrics", "title": "Metrics", "display": "metrics", "entity": "IssueReport"}
  ]
}
```

### v1 → v2 migration

When the renderer encounters a layout without `"version": 2`, it auto-migrates:

```python
def _migrate_v1_to_v2(v1_layout, dsl_regions):
    cards = []
    for i, name in enumerate(v1_layout.get("order", [])):
        if name in v1_layout.get("hidden", []):
            continue  # hidden cards simply omitted in v2
        cards.append({
            "id": f"migrated-{i}",
            "region": name,
            "col_span": v1_layout.get("widths", {}).get(name, 6),
            "row_order": i,
        })
    return {"version": 2, "cards": cards}
```

The migrated v2 layout is saved back on first access. Seamless upgrade.

## Interaction Layer

### Drag-to-reorder (SortableJS)

The grid container is a SortableJS instance. Cards are draggable by their title bar (handle). On drop, `row_order` values are recalculated from DOM order.

Visual feedback: ghost card with reduced opacity, blue drop-indicator line between cards.

```
User drags card → SortableJS onEnd → update cards[] order → auto-save
```

### Drag-to-resize (custom)

Each card gets a resize handle on its right edge (4px vertical bar, `cursor: col-resize`). On mousedown/touchstart:

1. Track horizontal mouse movement
2. Calculate which snap column the pointer is nearest (3, 4, 6, 8, 12)
3. Update `col_span` live — the card resizes in real-time
4. On mouseup — commit the new span, auto-save

Snap breakpoints at 25% (3col), 33% (4col), 50% (6col), 67% (8col), 100% (12col) of grid width. Visual feedback: subtle column guides appear on drag-start, active breakpoint highlighted.

### Add card

A `+ Add Card` button at the bottom of the grid. Click opens a popover listing available regions from the catalog (grouped by entity). Selecting one appends a new card instance with default `col_span`. The card is HTMX-loaded immediately.

### Remove card

Each card has an `×` button visible on hover. Clicking removes the card instance from `cards[]` and auto-saves. The region stays in the catalog for re-adding.

### Auto-save

Every layout change (reorder, resize, add, remove) triggers a 500ms debounced PUT to `/auth/preferences`. No explicit save button. The floating toolbar is removed.

A "Reset to default layout" option is accessible from a `⋯` menu on the dashboard header.

### Always-on interactions

No edit mode toggle. Drag handles visible on hover, resize handles always active, remove button on hover. Matches modern dashboard UX (Notion, Linear, Grafana).

## File Changes

### Create

| File | Purpose |
|------|---------|
| `src/dazzle_ui/runtime/static/js/dashboard-builder.js` | New Alpine component replacing `workspace-editor.js` |
| `src/dazzle_ui/runtime/static/vendor/sortable.min.js` | Vendored SortableJS |
| `src/dazzle_ui/templates/workspace/_card_picker.html` | Popover template for "Add Card" widget picker |

### Modify

| File | Changes |
|------|---------|
| `src/dazzle_ui/templates/workspace/_content.html` | Rewrite: SortableJS grid, resize handles, add-card button, remove edit-mode gating |
| `src/dazzle_ui/runtime/workspace_renderer.py` | v2 schema in `apply_layout_preferences()`, v1→v2 migration, catalog data builder |
| `src/dazzle_ui/runtime/page_routes.py` | Register `/api/workspaces/{name}/catalog` route |
| `src/dazzle_ui/templates/base.html` | Replace `alpine-sort.min.js` script tag with `sortable.min.js` |

### Remove

| File | Reason |
|------|--------|
| `src/dazzle_ui/runtime/static/vendor/alpine-sort.min.js` | Replaced by SortableJS |
| `src/dazzle_ui/runtime/static/js/workspace-editor.js` | Replaced by `dashboard-builder.js` |

## Testing

| Test | What it verifies |
|------|-----------------|
| v1→v2 migration unit test | Round-trip preserves order/widths, hidden cards dropped |
| Catalog endpoint unit test | Returns correct regions for a workspace |
| Layout persistence unit test | Add, remove, reorder, resize → correct JSON in preferences |
| Default layout unit test | No saved pref → DSL regions populate correctly |
| Resize snap unit test | Mouse position → correct snap breakpoint calculation |

## Success Criteria

- Any workspace renders as a customizable dashboard without DSL changes
- Users can add duplicate cards of the same region type
- Drag-to-reorder works smoothly with SortableJS
- Drag-to-resize snaps cleanly to column breakpoints
- Layouts persist across sessions via user_preferences
- Existing v1 layouts auto-migrate without data loss
- AegisMark's agents can build customizable dashboards using standard DSL constructs
