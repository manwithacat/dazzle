# Data Table Rebuild — Design Spec

**Date:** 2026-04-11
**Status:** Approved
**Skill:** ux-architect (component contract: data-table; primitives: sort, column-resize, inline-edit)

## Goal

Rewrite Dazzle's data table (template + JS + backend endpoints) to conform to the full ux-architect data-table contract: pure Tailwind chrome, column resize, inline edit, bulk delete, sticky header, keyboard navigation, and proper loading/error states.

## Scope

**Full contract.** Unlike the dashboard rebuild (frontend-only), this touches all three layers: JS, templates, and Python backend.

### Files Changed

| Layer | File | Change |
|---|---|---|
| JS | `src/dazzle_ui/runtime/static/js/dz-alpine.js` | Rewrite `dzTable` component: column resize, inline edit, enhanced bulk select, loading state |
| Template | `src/dazzle_ui/templates/components/filterable_table.html` | Rewrite: pure Tailwind, semantic `<table>`, `<colgroup>`, spec-governed chrome |
| Template | `src/dazzle_ui/templates/fragments/table_rows.html` | Rewrite: inline-editable cells, row states (hover/selected/editing/pending/error) |
| Template | `src/dazzle_ui/templates/fragments/table_pagination.html` | Rewrite: pure Tailwind pagination controls |
| Template | `src/dazzle_ui/templates/fragments/inline_edit.html` | Rewrite: phase-based cell editing per inline-edit primitive |
| Template | `src/dazzle_ui/templates/fragments/bulk_actions.html` | Rewrite: pure Tailwind, delete-only bulk action with confirmation |
| Template | `src/dazzle_ui/templates/fragments/search_input.html` | Restyle: pure Tailwind (same HTMX wiring) |
| Template | `src/dazzle_ui/templates/fragments/filter_bar.html` | Restyle: pure Tailwind (same HTMX wiring) |
| Python | `src/dazzle_ui/converters/template_compiler.py` | Modify: populate `inline_editable` from field types, set `bulk_actions=True` |
| Python | `src/dazzle_back/runtime/page_routes.py` or entity route builder | Add: PATCH field endpoint, POST bulk-delete endpoint |
| Tests | `tests/quality_gates/test_data_table_gates.py` | New: unit + Playwright integration tests for 5 quality gates |

### Files Unchanged

- `TableContext` and `ColumnContext` models — extended with new defaults, not replaced
- `workspace_renderer.py`, all region templates
- `dz-component-bridge.js`, `dz-widget-registry.js`
- Vendored libraries (Alpine, HTMX, etc.)

## Decisions

### 1. Colour Integration

Same as dashboard: structural tokens (spacing, radius, motion, elevation, density) frozen from Linear token sheet. Colours map through existing `design-system.css` HSL variables (`--card`, `--border`, `--foreground`, `--muted-foreground`, `--primary`, `--destructive`, `--success`).

### 2. Inline Edit Endpoint

**`PATCH /api/{entity}/{id}/field/{field_name}`**

- Request: `Content-Type: application/x-www-form-urlencoded` (HTMX default), body `value=newvalue`
- Validates field exists on entity, is not pk/computed/ref
- Validates value against field type (number, date, enum options, string length)
- Updates single column via SQLAlchemy
- Response: renders updated `<tr>` fragment using `table_rows.html`
- Error: returns 422 with error message
- RBAC: respects existing `permit:` / `scope:` rules

Why form-encoded: HTMX `hx-patch` sends form data by default. One field, one value — no need for JSON encoding extension.

### 3. Bulk Delete Endpoint

**`POST /api/{entity}/bulk-delete`**

- Request: `Content-Type: application/json`, body `{"ids": ["uuid1", "uuid2", ...]}`
- Validates user has delete permission on each (scope-filtered)
- Deletes matching rows in single query
- Response: returns updated `<tbody>` fragment (reloads current page with current sort/filter)
- Error: returns 422 with count of failed/forbidden deletes
- RBAC: scope-filters the ID list — silently skips IDs the user can't access

Why JSON: ID lists can be long. Form-encoded arrays are awkward. Alpine sends via `fetch()`, not HTMX.

### 4. Inline Edit Field Selection

Convention-based from field types. The compiler populates `TableContext.inline_editable` automatically:

- **Editable:** text (→ `<input type="text">`), number (→ `<input type="number">`), bool (→ `<input type="checkbox">`), enum (→ `<select>` with enum options), date (→ `<input type="date">`)
- **Not editable:** pk, ref/belongs_to, computed, sensitive, money (complex input needs full widget)

Explicit DSL syntax (`field title "Title" inline_edit`) deferred to when `widget:` parsing lands.

### 5. Bulk Actions

Delete only for v1. Status change and other entity-specific actions deferred to process/workflow system.

### 6. Testing Strategy

Both unit-level quality gates AND Playwright integration tests from the start. Lesson learned from dashboard rebuild (manwithacat/dazzle#770): unit tests calling controller methods directly missed the `setPointerCapture` bug. Integration tests exercise real DOM event wiring.

## Alpine Controller Architecture

```js
Alpine.data("dzTable", (tableId, endpoint, config) => ({
  // ── Data ──
  tableId,
  endpoint,
  sortField: config.sortField || "",
  sortDir: config.sortDir || "asc",

  // ── Column visibility (localStorage per tableId) ──
  hiddenColumns: [],

  // ── Column widths (localStorage per tableId) ──
  columnWidths: {},             // {colKey: widthPx}

  // ── Selection ──
  selected: new Set(),
  bulkCount: 0,

  // ── Inline edit (null when idle) ──
  editing: null,                // {rowId, colKey, originalValue, saving, error}

  // ── Column resize (null when idle) ──
  resize: null,                 // {colKey, startX, startWidth}

  // ── Loading ──
  loading: false,

  // ── Column menu ──
  colMenuOpen: false,
}))
```

**Config parameter** replaces positional args. Contains: `sortField`, `sortDir`, `inlineEditable` (list of column keys), `bulkActions` (bool).

**Methods:**

Sort:
- `toggleSort(field)` — tri-state cycle: unsorted → asc → desc → unsorted. Optimistic sort indicator update, HTMX reload.

Column resize:
- `startColumnResize(colKey, e)` — pointer down on resize handle, record startX/startWidth
- `onResizeMove(e)` — update `<col>` width, clamp [80px, 800px], snap to 8px
- `endResize(e)` — persist to localStorage, no server round-trip

Inline edit:
- `startEdit(rowId, colKey, currentValue)` — triggered by double-click or Enter on focused cell
- `commitEdit()` — HTMX PATCH, optimistic update, row enters pending state
- `cancelEdit()` — restore original value, no server round-trip
- `handleEditKeydown(e)` — Enter commits, Esc cancels, Tab commits and advances to next editable cell in row

Bulk actions:
- `bulkDelete()` — confirmation prompt, POST bulk-delete with selected IDs, reload tbody

Selection:
- `toggleRow(id)`, `toggleSelectAll()`, `clearSelection()` — same as current but using Set for O(1) lookup

## Template Structure

```
table-root (x-data="dzTable(tableId, endpoint, config)")
├── table-toolbar
│   ├── search input (left, debounced 300ms)
│   ├── filter chips (centre)
│   ├── bulk actions (right, visible when selected.size > 0)
│   │   └── "Delete N items" button → confirm → POST bulk-delete
│   └── column visibility menu (far right)
├── table-scroll (overflow-x-auto)
│   └── <table>
│       ├── <colgroup> (widths from columnWidths)
│       ├── <thead> (position: sticky; top: 0; z-index: 10)
│       │   └── <tr>
│       │       ├── <th> select-all checkbox
│       │       ├── <th> per column (sort indicator + resize handle)
│       │       └── <th> actions
│       └── <tbody> (HTMX target)
│           └── <tr> per row
│               ├── <td> checkbox
│               ├── <td> per column (display or inline-edit)
│               └── <td> row actions (hover-revealed)
├── table-footer
│   ├── "X of Y selected" (left)
│   └── pagination (right)
├── table-empty-state (icon + headline + CTA)
└── table-loading-overlay (semi-transparent, spinner)
```

**Spec-governed chrome:**

- Real `<table>` markup with `<colgroup>` for column widths
- Sticky header: `position: sticky; top: 0; background: hsl(var(--card)); z-index: 10`
- Header text: `text-[12px] font-medium uppercase tracking-[0.04em] text-[hsl(var(--muted-foreground))]`
- Body text: `text-[13px] text-[hsl(var(--foreground))]`
- Numeric columns: `tabular-nums` + right-aligned
- Row height: 36px default (dense)
- Row hover: `bg-[hsl(var(--card))]`, row actions fade in over 80ms
- Selected row: `hsl(var(--primary))` at 10% opacity
- Sort indicator: 12px SVG chevron, never unicode arrows
- Resize handle: 4px wide on right edge of `<th>`, `cursor-col-resize`, 1px accent line during drag
- Cell edit border: `hsl(var(--primary))` 1px, focus ring
- Pending row: 70% opacity during optimistic update
- Error row: 2px left border `hsl(var(--destructive))`
- Easing: `cubic-bezier(0.2, 0, 0, 1)` everywhere

## Backend Changes

### PATCH Field Endpoint

Added to the entity route builder alongside existing CRUD routes:

```python
@router.patch("/api/{entity_name}/{id}/field/{field_name}")
async def patch_field(entity_name: str, id: str, field_name: str, request: Request):
    # 1. Validate entity exists, field exists, field is editable
    # 2. Validate RBAC (user has edit permission, scope filters pass)
    # 3. Parse value from form data, validate against field type
    # 4. Update single column via SQLAlchemy
    # 5. Reload row, render <tr> fragment, return as HTML response
```

### Bulk Delete Endpoint

```python
@router.post("/api/{entity_name}/bulk-delete")
async def bulk_delete(entity_name: str, request: Request):
    # 1. Parse {"ids": [...]} from JSON body
    # 2. Validate RBAC (user has delete permission)
    # 3. Scope-filter IDs (silently skip inaccessible)
    # 4. DELETE matching rows in single query
    # 5. Reload current page, render <tbody> fragment, return as HTML
```

### Compiler Changes

In `_compile_list_surface()`:

```python
# Populate inline_editable from field types
inline_editable = [
    col.key for col in columns
    if col.type in ("text", "date", "bool")
    and col.key not in ("id", "created_at", "updated_at")
    and not col.key.endswith("_id")
]

# Enable bulk actions for all list surfaces
table_ctx.inline_editable = inline_editable
table_ctx.bulk_actions = True
```

## Quality Gates

From `ux-architect/components/data-table.md`:

1. **Sort + loading** — Sort a column with 1000 rows. Does loading overlay appear immediately and clear on response?
2. **Column resize via colgroup** — Resize a column to 200px. Do all cells reflow without per-cell width attributes?
3. **Inline edit Tab navigation** — Double-click a cell, type, press Tab. Does focus advance to next editable cell in same row?
4. **Selection persistence** — Select 5 rows, scroll, scroll back. Are the same 5 rows still selected?
5. **Keyboard navigation** — Tab into table from outside, navigate with arrow keys. Does focus move predictably between cells?

### Playwright Integration Tests (new, from dashboard lesson)

- Real pointer drag on column resize handle → verify `<col>` width changes in DOM
- Real double-click on editable cell → verify `<input>` appears with value selected
- Real Tab keypress in edit mode → verify focus moves to next editable `<td>`
- Real Cmd+A in table → verify all visible row checkboxes checked

## Ux-Architect Skill Integration

The implementor MUST read these skill artefacts before writing code:

1. `~/.claude/skills/ux-architect/tokens/linear.md` — frozen token values
2. `~/.claude/skills/ux-architect/components/data-table.md` — full component contract
3. `~/.claude/skills/ux-architect/primitives/sort.md` — sort phase spec
4. `~/.claude/skills/ux-architect/primitives/column-resize.md` — resize phase spec
5. `~/.claude/skills/ux-architect/primitives/inline-edit.md` — inline edit phase spec
6. `~/.claude/skills/ux-architect/stack-adapters/htmx-alpine-tailwind.md` — stack rules + Dazzle integration
