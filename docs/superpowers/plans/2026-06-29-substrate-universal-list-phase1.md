# Phase 1 — LIST: make the substrate the universal list render path, retire `render_filterable_table`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make every `mode: list` surface first-paint through the typed Fragment substrate (chrome + skeleton tbody), so `render_data_row` is the sole list-row source on both first paint and refresh, then **delete** the legacy `render_filterable_table` (~516 LOC).

**Architecture:** The substrate `_build_list` already emits most chrome primitives (SearchBox/FilterBar/SortHeader/BulkActionToolbar/CreateButton/Pagination/EmptyState). Phase 1 adds the missing chrome (skeleton tbody, `dzTable` mount, column-visibility menu, colgroup/loading/a11y), flips the list default so unset-`render` surfaces dispatch to the substrate, re-baselines list goldens to the substrate DOM (visual parity, **not** byte parity — ADR-0049 D1), and removes the legacy renderer. The `/api/<entity>` refresh path and `render_data_row` are untouched (ADR-0048).

**Tech Stack:** Pydantic Fragment primitives (`render/fragment/primitives/`), `FragmentRenderer` mixins (`render/fragment/renderer/`), `FragmentSurfaceAdapter` (`http/runtime/renderers/fragment_adapter.py`), the `dzTable` Alpine controller (`page/runtime/static/js/dz-alpine.js`), pytest + `dazzle ux verify` + card-safety composite.

**Spec:** `docs/superpowers/specs/2026-06-29-substrate-universal-render-path-design.md` (§4 Phase 1). **ADR:** ADR-0049. Read §3 (decisions D1–D5) before starting.

## Global Constraints

- **`render/` is pure** — new chrome rendering lives in `render/`; no `http/`/`page/` imports (ADR-0038; import-linter `render is pure`).
- **Visual parity, not byte parity** (D1) — inspect every re-baselined golden diff; gate on `dazzle ux verify` + `test_htmx_workspace_composite` (card-safety) + a11y, not byte-equality with the legacy output.
- **`render_data_row` is the sole list-row source** (D2) — the substrate list first-paint emits a skeleton tbody pointing at `/api`; it must NOT render rows inline.
- **No `from __future__ import annotations` in FastAPI route files** (ADR-0014).
- **No backward-compat shims** — when `render_filterable_table` is deleted, repoint every caller in the same commit (ADR-0003).
- **Byte-exact `.html` fixtures** (if any added) — exclude from the trailing-whitespace/eof pre-commit hooks (the #1505 P1 scar).
- **Run the FULL unit suite before each ship**; ship discipline: `/bump patch`, CHANGELOG (+ Agent Guidance), CI green.
- **Independent review at the flip + delete** (Tasks 5–6) — the high-risk steps; insert a fresh adversarial review before shipping each.

---

## Task 1: Characterize the legacy list first-paint (the parity anchor)

**Files:**
- Create: `tests/unit/test_legacy_list_chrome_char_phase1.py`
- Create (generated, committed): `tests/unit/__snapshots__/legacy_list_chrome/*.html`

**Interfaces:**
- Produces: committed fixtures of `render_filterable_table(table_ctx)` output across a matrix (no-search/with-search, no-filter/with-filter, sortable cols, bulk on/off, pagination on/off, empty-state, refresh_interval). These are the **visual-parity reference** for the substrate chrome — NOT a byte gate after the flip (they document what the substrate must reproduce visually).

- [ ] **Step 1: Build the matrix** calling `from dazzle.page.runtime.table_renderer import render_filterable_table` with representative `TableContext` objects (read `table_renderer.py:204` for the ctx shape). Cover the chrome variants above.
- [ ] **Step 2: Snapshot** each to `__snapshots__/legacy_list_chrome/<label>.html` under an `UPDATE_LEGACY_LIST_CHAR=1` guard; assert equality otherwise. Exclude the dir from whitespace/eof pre-commit hooks.
- [ ] **Step 3: Run, verify green** (`uv run pytest tests/unit/test_legacy_list_chrome_char_phase1.py -q`).
- [ ] **Step 4: Commit** (`test(render): characterize legacy list chrome — Phase 1 parity anchor`).

## Task 2: `Table` primitive skeleton mode + `_emit_table` skeleton tbody

**Files:**
- Modify: `src/dazzle/render/fragment/primitives/data.py` (`Table` — add `skeleton: bool = False`, `hx_endpoint: str = ""`, `hx_trigger: str = "load"`, optional `refresh_interval` passthrough)
- Modify: `src/dazzle/render/fragment/renderer/_render_tables.py::_emit_table` (skeleton branch)
- Test: `tests/unit/test_table_skeleton_phase1.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces: a `Table` that, when `skeleton=True`, emits `<tbody id="..-body" hx-get="{hx_endpoint}" hx-trigger="{hx_trigger}" hx-swap="innerMorph" ...></tbody>` (empty) instead of inline `<tr>` rows. Matches the legacy `render_filterable_table` tbody (table_renderer.py:431-442) so the hydrate is identical.

- [ ] **Step 1: Write failing test** — `_emit_table` of a `Table(skeleton=True, hx_endpoint="/api/tasks")` contains `hx-trigger="load"` + `hx-get="/api/tasks"` + an empty tbody (no `<tr>`); a `Table(skeleton=False, rows=...)` still renders inline rows (unchanged).
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** the skeleton fields + the `_emit_table` branch (mirror the legacy tbody attrs incl. `refresh_interval` → `every Ns`).
- [ ] **Step 4: Run, verify pass; full suite + lint/mypy/import-linter green.**
- [ ] **Step 5: Commit.**

## Task 3: `dzTable` controller mount on the list Region

**Files:**
- Modify: `src/dazzle/render/fragment/primitives/containers.py` (`Region` — add optional `controller: str = ""` + `controller_config: Mapping = {}` , or a typed `DzTableMount` sidecar — pick at Step 0)
- Modify: the region renderer (`render/fragment/renderer/_render_layout.py::_emit_region` or wherever Region emits) — emit `x-data="dzTable(id, endpoint, config)"` when `controller == "dzTable"`
- Modify: `src/dazzle/http/runtime/renderers/fragment_adapter.py::_build_list` — set the controller + config (sortField/sortDir/bulkActions/inlineEditable/entityName/columns) from ctx
- Test: `tests/unit/test_region_dztable_mount_phase1.py` (create)

**Interfaces:**
- Consumes: the `dzTable` config shape (read `table_renderer.py:243-250` + `dz-alpine.js:919` for the exact keys).
- Produces: a list Region whose wrapper carries `x-data="dzTable(...)"` with byte-equivalent config JSON to the legacy mount, so refresh rows' `toggleRow`/`startEdit`/`isColumnVisible` bindings resolve.

- [ ] **Step 0: Confirm** the Region primitive + its renderer location and the exact legacy `dzTable` config JSON (table_renderer.py:243-250).
- [ ] **Step 1: Write failing test** — `_build_list` ctx with bulk/sort produces a Region rendering `x-data='dzTable("dt-..","/api/..",{...})'` with the expected config keys; no controller when the list is non-interactive.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** the Region controller field + emit + adapter wiring.
- [ ] **Step 4: Run, verify pass; full suite + gates green.**
- [ ] **Step 5: Commit.**

## Task 4: Substrate-canonical comprehensive list chrome (RE-SCOPED 2026-06-29)

**Re-scope decision (James, 2026-06-29):** the Step-0 diff found the gap is larger
than the original 4-element list, AND that the substrate's reused *workspace*
toolbar primitives are behaviourally wrong for surface lists. James chose
**substrate-canonical** (accept the FTS-dropdown search divergence; do NOT port
legacy inline-filter search) AND asked for the *whole* legacy-chrome surface to be
audited + delivered in **one big bang** so we don't revisit. So Task 4 is now a
comprehensive substrate-canonical list-chrome build, not 4 patches.

**Element ledger (legacy → substrate-canonical disposition):**
- visually-hidden page-title `<h1>` → **drop** (substrate header already has a visible `<h1>`; it serves the a11y role).
- dzTable wrapper attrs → **done** (Task 3).
- column-visibility menu (>3 cols) → **build** (`ColumnVisibilityMenu` primitive).
- create button, bulk toolbar, sort headers → **present** ✓.
- search: legacy inline-table-filter → **substrate FTS dropdown is canonical** (keep; documented divergence).
- filter selects: legacy `filter[key]`→tbody → substrate emits `filter_key`→dead `#region-task` AND passes option dicts where the renderer wants tuples (doubly broken). → **build working list filters**: target `#{id}-body`, `name="filter[key]"`, correct options.
- colgroup + column-resize handles → **drop** (discretionary polish; substrate lists are not resizable in Phase 1 — documented divergence).
- `<table class="dz-table-grid">` + visually-hidden `<caption>` → **build** (in `Table` skeleton mode).
- trailing actions `<th>` → **build** (CRITICAL: `render_data_row` always emits a trailing actions `<td>`; thead must match column count post-flip).
- `dz-table-scroll`(--dz-list-rows) + loading-spinner overlay + `dz-table-scroll-x`(role=region,tabindex) → **build** (`DataListScroll` primitive).
- `dz-table-empty` sibling (role=status) → **build** (shown when the hydrate returns no rows; replaces the `if not items: EmptyState` branch — list always renders the skeleton table now).
- `-loading-sr` htmx-indicator (sr-only) → **build** (the skeleton tbody / filters `hx-indicator` target).
- `#dz-live-region` (dzTable JS announces sort/loading here) → **build** (once per list Region).

**Files:**
- Modify: `src/dazzle/render/fragment/primitives/data.py` (`Table` skeleton: caption + actions-th + grid class), `containers.py` (Region live-region), new primitives `DataListScroll` + `ColumnVisibilityMenu`.
- Modify: the matching renderers in `render/fragment/renderer/` (pure).
- Modify: `fragment_adapter.py::_build_list` — compose the canonical shell (always skeleton; no inline-row branch) + working filter selects.
- Test: `tests/unit/test_list_chrome_parity_phase1.py` (create), sub-step test files.

- [x] **Step 0: Diff** substrate `_build_list` vs Task-1 legacy fixtures → element ledger above.
- [x] **4a:** `Table` skeleton enrich — `dz-table-grid` class + sr `<caption>` + trailing actions `<th>` + `data-dz-col`/sortable `toggleSort` headers. TDD.
- [x] **4b:** `DataListScroll` primitive — `.dz-table` scope + scroll(--dz-list-rows) + loading-spinner overlay + scroll-x(role=region) + empty sibling + loading-sr + pagination footer. TDD.
- [x] **4c:** `ColumnVisibilityMenu` primitive (>3 cols). TDD.
- [x] **4d:** working list filters — `ListFilterBar` (tbody target + `filter[key]` names + select/text/ref + correct options). TDD.
- [x] **4e:** `_build_list` rewrite — composes the canonical shell (always skeleton+hydrate, no inline branch) + Region live-region; migrated the inline-row-pinning dispatch/adapter/renderer/pagination/search-filter tests to the canonical model; full unit suite (19262) + gates green. The 6 `render: fragment` opt-in surfaces now render the canonical chrome (integration substring tests hold).
- [x] **Done.** The page_routes *dispatch* flip stays in Task 5 (gated by independent review).

## Task 5: Flip the list default to the substrate (+ re-baseline + verify)  — INDEPENDENT REVIEW

**Files:**
- Modify: `src/dazzle/http/runtime/page_routes.py::_maybe_dispatch_inner_html` (dispatch `mode: list` surfaces even when `surface.render is None`, using skeleton mode)
- Modify: re-baseline all churned list goldens (fleet) — deliberate per D1
- Test: existing list emission/golden tests (re-baselined); `dazzle ux verify`; `test_htmx_workspace_composite`

**Interfaces:**
- Consumes: Tasks 2–4 (skeleton, dzTable mount, chrome parity).
- Produces: every `mode: list` surface first-paints via the substrate (chrome + skeleton), hydrating rows via `/api` → `render_data_row`.

- [x] **Step 0: Independent adversarial review** — fresh reviewer ran the matrix + traced the hydrate cycle. Chrome shape + plumbing were sound; found `_build_dispatch_ctx` was an INCOMPLETE adapter for the canonical `_build_list` (SEV-1 per-column filter_type/ref dropped → text/ref filters dead; SEV-1 `_build_list` 500s on zero/keyless columns; SEV-2 inline_editable/refresh_interval/pagination_mode/search_first dropped; SEV-3 generic empty title + missing select-all :checked/:indeterminate). **All fixed + 13 tests before the flip** (commit `harden the canonical list before the flip`).
- [x] **Step 1: Implement the flip** — `_maybe_dispatch_inner_html`: `surface.render is None and mode != LIST → legacy`; list dispatches to `dispatch_render` (defaults `render or "fragment"`). View/create/edit stay legacy. The `/api` row hydrate + `render_data_row` untouched.
- [x] **Step 2: Run the FULL suite** — green (19275), NO failures. No page-level byte-goldens pin default lists (they were substring-asserted), so there is no golden churn to re-baseline at the unit level.
- [x] **Step 3: Run the oracles** — `test_htmx_workspace_composite` (card-safety) green; verified the flip LIVE via TestClient boots of 4 default-`render` apps → 15 lists all render the substrate (`dz-region--kind-list` + skeleton + dzTable mount) with **0** card-safety/a11y violations (nested-chrome / duplicate-title / hidden-primary scanners). NOTE: the browser `dazzle ux verify` oracle needs a live `dazzle serve --local` + test DB (not runnable in-session) — the structural card-safety + a11y scanners stand in; flag for CI/e2e.
- [x] **Step 4: Commit + ship.**

## Task 6: Delete `render_filterable_table` + repoint callers — INDEPENDENT REVIEW

**Files:**
- Modify/Delete: `src/dazzle/page/runtime/table_renderer.py` (delete `render_filterable_table` + `_render_search_input`/`_render_filter_bar`/`_render_bulk_actions`/`_render_column_header` — ~516 LOC; delete the module if nothing remains)
- Modify: `src/dazzle/page/runtime/experience_renderer.py:~230` (repoint the experience table-step to the substrate)
- Modify: `src/dazzle/page/runtime/template_renderer.py:~81` (repoint / remove the legacy list branch)
- Modify: tests pinning the legacy path (`test_create_cta_entity_title_1487.py`, `test_surface_refresh_1399.py`) → re-point to the substrate or migrate assertions
- Modify: `tests/unit/test_typed_runtime_no_jinja.py` module list if it references table_renderer

**Interfaces:**
- Produces: one list render path. `render_filterable_table` gone.

- [ ] **Step 0: Grep all callers** — `grep -rn "render_filterable_table\|_render_filter_bar\|_render_search_input\|_render_bulk_actions" src tests`. Confirm only the 2 non-test callers + the named tests.
- [ ] **Step 1: Independent adversarial review** — dispatch a reviewer to confirm no live caller is missed, the experience/template repoints preserve behaviour, and the no-fallback removal (D4) is safe (substrate robust for list).
- [ ] **Step 2: Delete + repoint** in one commit; migrate the legacy-pinning tests.
- [ ] **Step 3: Run the FULL suite + lint/mypy/import-linter** — green; `render is pure` KEPT.
- [ ] **Step 4: Commit** (`refactor(render): delete render_filterable_table — substrate is the sole list path (Phase 1)`).

## Task 7: ADR status + CHANGELOG + ship

- [ ] **Step 1:** Update ADR-0049 status (Phase 1 / list shipped). CHANGELOG entry (+ Agent Guidance: list surfaces render via the substrate; `render_filterable_table` deleted; one list-render model).
- [ ] **Step 2:** Comment on the tracking issue; `/bump patch`; full suite green; push; monitor CI.

## Phase 1 gate
- [ ] All list surfaces first-paint via the substrate (skeleton+hydrate); `render_data_row` the sole row source; `render_filterable_table` deleted; full suite + `ux verify` + card-safety + a11y green; `render is pure` KEPT; goldens re-baselined with inspected diffs. ADR-0049 Phase 1 done.

## Self-Review

- **Spec coverage:** §4-Phase-1 chrome gaps → Tasks 2 (skeleton), 3 (dzTable mount), 4 (column-vis/colgroup/loading/a11y); flip → Task 5; delete → Task 6; D1 visual-parity gate → Tasks 5/6 oracles; D2 skeleton+hydrate → Task 2; D4 no-fallback → Task 6 Step 1. Covered.
- **Placeholder scan:** Step-0 investigations (Tasks 3/4/6) are first-steps grounding the few specifics the spec couldn't pin from the investigation alone — not placeholders.
- **Type consistency:** `Table.skeleton`/`hx_endpoint` (Task 2) → `_build_list` skeleton wiring (Task 5); `Region.controller`/`controller_config` (Task 3) → `_build_list` config. Consistent.
- **Risk:** Tasks 5 (flip) and 6 (delete) carry the fleet-churn + no-fallback risk → each gated by an independent adversarial review (Step 0/1) before ship, per the Global Constraints.
