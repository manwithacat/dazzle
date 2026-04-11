# Dashboard Rebuild — Design Spec

**Date:** 2026-04-11
**Status:** Approved
**Skill:** ux-architect (component contracts: dashboard-grid, card; primitives: drag-and-drop, resize)

## Goal

Rewrite Dazzle's dashboard frontend (JS + template) to replace SortableJS with native pointer-event drag/resize governed by the ux-architect skill's component contracts, interaction primitives, and Linear token sheet.

This is a test of the skill's ability to support autonomous agent work — the spec should be self-contained enough for an agent with the ux-architect skill loaded to execute without human intervention.

## Scope

**Layers in play:** JavaScript + Jinja2 template only. Python backend is unchanged.

**What changes:**

| File | Change |
|---|---|
| `src/dazzle_ui/runtime/static/js/dashboard-builder.js` | Full rewrite — native pointer events, Alpine-only state, no SortableJS |
| `src/dazzle_ui/templates/workspace/_content.html` | Full rewrite — pure Tailwind utilities, semantic HTML, spec-governed card chrome |
| `src/dazzle_ui/runtime/asset_manifest.py` | Remove SortableJS from vendor asset list |

**What is deleted:**

| File | Reason |
|---|---|
| `src/dazzle_ui/runtime/static/vendor/sortable.min.js` | No remaining consumers after dashboard rewrite |

**What stays the same:**

- `base.html` — no changes needed; all required CSS variables already exist in `design-system.css`
- `workspace_renderer.py` — context building, preference merge, catalog generation
- `page_routes.py` — workspace handler, region endpoints, auth
- All 17 region templates in `workspace/regions/` — render inside card bodies unchanged
- `_card_picker.html` — card type picker popover
- Layout JSON format — `{id, region, col_span, row_order}`, version 2
- Persistence contract — `PUT /auth/preferences`, `DELETE /auth/preferences/{key}`
- Data island pattern — `<script id="dz-workspace-layout" type="application/json">`

## Decisions

### 1. Colour Integration: Option 2 (map through `--dz-*`)

Structural tokens (spacing, radius, motion, elevation, density, font) are frozen from the Linear token sheet and hard-coded. Colour tokens map through Dazzle's `--dz-*` CSS variables so per-project theming is preserved.

**Frozen structural tokens:**

| Token | Tailwind value | Source |
|---|---|---|
| Spacing | `gap-4`, `p-4`, `p-3`, `px-3 py-2` | Linear spacing scale (4px base) |
| Radius | `rounded-md` (6px) | Linear radius-md |
| Motion easing | `cubic-bezier(0.2, 0, 0, 1)` | Single curve everywhere |
| Motion instant | `80ms` | Hover, focus rings |
| Motion fast | `140ms` | Drag lift, tooltip |
| Motion base | `200ms` | Layout settle, drop animation |
| Elevation (drag) | `shadow-[0_12px_24px_rgb(0_0_0/0.12),0_4px_8px_rgb(0_0_0/0.06)]` | elev-4 |
| Density | 36px min card header height | Linear dense default |
| Font | Inter, system-ui, sans-serif | Linear type stack |

**Flexible colour tokens (mapped through existing CSS variables):**

Dazzle's `design-system.css` already defines HSL-based tokens (shadcn pattern) alongside `--dz-*` tokens. The dashboard uses whichever existing variable fits — no new variable systems.

| Spec token | CSS expression | Source |
|---|---|---|
| `surface-base` | `hsl(var(--background))` | design-system.css `:root` |
| `surface-raised` | `hsl(var(--card))` | design-system.css `:root` |
| `border-subtle` | `hsl(var(--border))` | design-system.css `:root` |
| `border-strong` | `var(--dz-border-input)` | design-system.css (stronger than --border) |
| `text-primary` | `hsl(var(--foreground))` | design-system.css `:root` |
| `text-secondary` | `hsl(var(--muted-foreground))` | design-system.css `:root` |
| `accent` | `hsl(var(--primary))` | design-system.css `:root` |
| `danger` | `hsl(var(--destructive))` | design-system.css `:root` |
| `success` | `hsl(var(--success))` | design-system.css `:root` |

**No new CSS variables needed.** All required tokens already exist in `design-system.css` with dark mode overrides. The `--dz-text-muted` variable also exists (oklch). Prefer the HSL-based tokens for consistency with the existing component system.

### 2. Drag Model: Placeholder + Reflow in CSS Grid

Cards live in a 12-column CSS grid flow. Dragging means reordering cards within that flow, not free-form positioning.

**How it works:**

1. When drag enters `dragging` phase (after 4px movement or 120ms hold), the dragged card gets `position: fixed` and follows the pointer via `transform: translate()`. A placeholder `<div>` of the same `col-span` stays in grid flow to hold the slot.
2. As pointer moves over other cards, the controller computes which card the pointer is nearest to (by comparing pointer Y to each card's vertical midpoint). The placeholder moves in the `cards` array to that position — Alpine re-renders the grid, other cards reflow via CSS.
3. On drop, the card animates from fixed position back to the placeholder's position (`motion-base`, 200ms), then switches back to normal grid flow.

**Why no collision solver:** In a CSS grid with integer col-spans, collision isn't geometric — it's arithmetic. If two cards on the same row have col-spans summing > 12, the second wraps. The grid handles this automatically.

**Keyboard alternative:** Focus card → Space to enter move mode → Up/Down arrow reorders → Enter confirms → Esc cancels. Live region announces position changes.

### 3. SortableJS: Removed

No remaining consumers after the dashboard rewrite. `vendor/sortable.min.js` is deleted and removed from the asset manifest.

### 4. Testing: Manual Then Playwright

Manual quality gate checklist for the initial implementation. Playwright tests added before the data-table component work begins.

## Alpine Controller Architecture

Single `dzDashboardBuilder` component on grid root. All interaction state owned by this controller — cards are dumb DOM.

```js
{
  // Data (from layout JSON)
  cards: [{id, region, title, col_span, row_order}],
  catalog: [{name, title, display, entity}],
  workspaceName: '',

  // UI state
  showPicker: false,
  saveState: 'clean',        // clean | dirty | saving | saved | error
  undoStack: [],             // previous card arrays for Cmd+Z

  // Drag state (null when not dragging)
  drag: null,                // {cardId, startX, startY, offsetX, offsetY, currentX, currentY, phase}
                             // phase: 'pressed' | 'dragging'

  // Resize state (null when not resizing)
  resize: null,              // {cardId, startX, startColSpan, currentColSpan}
}
```

**Key design decisions:**

- `saveState` replaces implicit dirty flag — exposes a 5-state lifecycle (`clean → dirty → saving → saved → clean`) so the template can render the save button correctly.
- `undoStack` is a simple array of card snapshots. `Cmd+Z` pops last snapshot and replaces `cards`. Cleared on save. No redo.
- `drag.phase` gates the visual transition. `pressed` = pointer down, no visual change. `dragging` = 4px threshold crossed, card lifts. Prevents jitter on click.
- All pointer event handlers registered/deregistered in Alpine lifecycle, not in a third-party library.

## Template Structure

```
grid-root (x-data="dzDashboardBuilder()")
├── grid-toolbar
│   ├── "Add card" button (opens picker popover)
│   ├── spacer
│   ├── "Reset" button (text-secondary, confirms if dirty)
│   └── "Save layout" button (reflects saveState)
├── grid-container (grid grid-cols-12 gap-4)
│   └── grid-card-wrapper (x-for="card in cards", col-span-{n})
│       └── card-root (article, role="article")
│           ├── card-header (drag handle zone)
│           │   ├── card-title (text-[15px] font-medium)
│           │   └── card-actions (remove button, visible on hover)
│           ├── card-body (hx-get region endpoint, hx-trigger="intersect once")
│           │   └── skeleton → region content (lazy loaded)
│           └── resize-handle (bottom-right, 12x12px, visible on hover)
└── card-picker-popover (from catalog)
```

**Save button states:**

| `saveState` | Appearance |
|---|---|
| `clean` | Grey text, disabled, "Saved" |
| `dirty` | Primary colour, enabled, "Save layout" |
| `saving` | Primary colour, disabled, spinner icon |
| `saved` | Success colour, check icon, auto-transitions to `clean` after 1200ms |
| `error` | Danger border, "Retry", tooltip with error message |

**Card chrome example (pure Tailwind, no DaisyUI):**

```html
<article
  class="rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))]
         transition-[border-color] duration-[80ms] [transition-timing-function:cubic-bezier(0.2,0,0,1)]
         hover:border-[var(--dz-border-input)]"
  role="article"
  :aria-labelledby="'card-title-' + card.id">
```

Structural tokens hard-coded (rounded-md, duration, easing), colours via existing design-system variables.

## Resize Primitive

Right-edge drag handle snaps col-span to `{3, 4, 6, 8, 12}`. CSS grid handles reflow — no per-card width calculation.

1. Pointer down on resize handle → record `startX`, `startColSpan`
2. Pointer move → compute nearest snap point from pointer delta
3. Update `card.col_span` via Alpine → grid reflows
4. Pointer up → push undo snapshot, set `saveState: 'dirty'`

Keyboard: Focus card → `R` to enter resize mode → Left/Right arrow changes col-span by one snap → Enter/Esc.

## Ux-Architect Skill Integration

The implementor MUST read these skill artefacts before writing code:

1. `~/.claude/skills/ux-architect/tokens/linear.md` — frozen token values
2. `~/.claude/skills/ux-architect/components/dashboard-grid.md` — grid component contract
3. `~/.claude/skills/ux-architect/components/card.md` — card component contract
4. `~/.claude/skills/ux-architect/primitives/drag-and-drop.md` — drag phase spec
5. `~/.claude/skills/ux-architect/primitives/resize.md` — resize phase spec
6. `~/.claude/skills/ux-architect/stack-adapters/htmx-alpine-tailwind.md` — stack rules + Dazzle integration

The contracts define exact states, transitions, tokens, and accessibility requirements. Do not invent values outside the token sheet. Do not skip interaction phases.

## Quality Gates

These must all pass before the implementation is considered done:

1. **Drag threshold** — Click a card header without moving. Does it stay put? Drag 3px — still stays put. Drag 5px — does it lift with scale 1.02, elevated shadow, 95% opacity?
2. **Drag performance** — Drag a card rapidly across the grid. Does it stay locked to the cursor without jank? Verify `transform: translate()` is used, not `left`/`top`.
3. **Save lifecycle** — Move a card. Does button change to "Save layout"? Click it. Does it show spinner → checkmark → back to "Saved"?
4. **Persistence boundary** — Move a card but don't save. Refresh the page. Does layout revert to last saved state?
5. **Keyboard accessibility** — Tab to a card. Press Space. Use arrow keys to reorder. Press Enter. Does it stay in new position? Does a screen reader announce the move?

**Verification app:** `examples/ops_dashboard` — has a workspace with multiple regions (metrics, lists, charts).
