# List-render Convergence — Phase 1 + Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `render/` substrate the single source of the rich CRUD data-table's row HTML, and delete the duplicate `http/` row renderer — without changing a single byte of the fleet's rendered output.

**Architecture:** Add a capability-bearing `DataTable` primitive + a shared `render/` row-core that byte-reproduces today's `_render_table_row` (`dz-tr-row`) output (Phase 1, no caller switched → zero churn). Then point the `http/` HTMX list-refresh handler at the substrate and delete `htmx_render.py`'s row family (Phase 2, byte-golden-verified). The row-core is driven by an orthogonal `RowCapabilities` vector unified by one protocol — *the row owns the bare click; every interactive sub-element `stopPropagation`s*.

**Tech Stack:** Python 3.12, Pydantic Fragment primitives (`dazzle.render.fragment.primitives`), the `FragmentRenderer` mixin family (`render/fragment/renderer/_render_tables.py`), `html.escape`-based emission (no Jinja, ADR-0023), pytest characterization/byte-golden tests.

**Spec:** `docs/superpowers/specs/2026-06-28-list-render-convergence-design.md` (§3 row model, §4 architecture, §5 phasing). Read §3.2 (the orthogonality protocol) and §4 before starting. **Issue:** #1505.

## Global Constraints

- **`render/` is pure and acyclic** — the row-core lives in `render/`; it must NOT import `http/` or `page/` (ADR-0038; `test_import_contracts.py` / `test_import_boundaries.py`). `http/` calls *down* into `render/`, never the reverse.
- **No `from __future__ import annotations` in FastAPI route files** (ADR-0014). `render/` modules may keep it (the substrate already does).
- **No backward-compat shims** — when Phase 2 deletes `_render_table_row`, update every caller/re-exporter in the same commit (ADR-0003).
- **No Jinja** — emission is `html.escape` + f-strings only (ADR-0023). `tests/unit/test_typed_runtime_no_jinja.py` lists the covered modules; update its list when deleting from `htmx_render.py`.
- **Byte-stability per phase** — Phases 1 and 2 change *zero* rendered bytes on the fleet. Every switch is guarded by a characterization/byte-golden captured from the *current* output BEFORE the switch.
- **Orthogonality invariant (§3.2)** — a capability that cannot satisfy the stopPropagation protocol becomes a new archetype, never a conditional branch in the row-core.
- **Run the FULL unit suite before each ship** — golden-master + example snapshots drift differently than `-k`-filtered runs.
- **Ship discipline:** `/bump patch`, clean worktree, CHANGELOG entry (+ `### Agent Guidance` when a pattern lands), full suite green, monitor CI.
- **Card-safety invariants** (`docs/reference/card-safety-invariants.md`) — run `tests/unit/test_htmx_workspace_composite.py` on any changed list DOM.

---

## Phase 1 — Substrate `DataTable` + row-core that byte-reproduces `dz-tr-row`

No caller switched this phase. Closes nothing; builds the mechanism and proves it byte-equal.

### Task 1.1: Characterization harness — freeze the current `_render_table_row` output

Capture today's output as the migration's safety net, across a capability matrix.

**Files:**
- Create: `tests/unit/test_data_row_characterization_1505.py`
- Create (generated): `tests/unit/__snapshots__/data_row_char_1505/*.html` (committed fixtures)

**Interfaces:**
- Produces: `CAP_MATRIX` — a list of `(label, table_dict, item)` cases covering every capability combination the rich table emits: plain, `bulk_actions`, `inline_editable`, `detail_url_template` (drill), hidden columns, ref/badge/bool/currency/date/percentage/sensitive cell types, an `o'brien`-style id (the #1327 escaping case).

- [ ] **Step 1: Enumerate the matrix.** Build `CAP_MATRIX` calling the *current* `from dazzle.http.runtime.htmx_render import _render_table_row`. Cover at minimum: `{}`; `bulk_actions=True`; `inline_editable=["name"]`; `detail_url_template="/contacts/{id}"`; all three combined; each `col.type` in `{str,ref,badge,bool,currency,date,percentage,sensitive}`; a hidden column; ids `"abc-123"` and `"o'brien"`.
- [ ] **Step 2: Snapshot each case.** For each matrix entry, write `_render_table_row(table, item)` to `__snapshots__/data_row_char_1505/<label>.html` (use a `--snapshot-update` style env guard or `pytest`'s tmp+commit pattern already used in the repo; mirror an existing committed-fixture test).
- [ ] **Step 3: Add a guard test** that re-renders each case and asserts byte-equality with its committed fixture (this protects against accidental drift of the *current* renderer while we build the replacement).
- [ ] **Step 4: Run, verify green** — `uv run pytest tests/unit/test_data_row_characterization_1505.py -q`. Expected: PASS (fixtures match current output).
- [ ] **Step 5: Commit** (`test(render): characterization fixtures for _render_table_row output (#1505 P1)`).

### Task 1.2: `RowCapabilities` + `DataTable` primitive

**Files:**
- Modify: `src/dazzle/render/fragment/primitives.py` (add `RowCapabilities`, `DataTable`)
- Test: `tests/unit/test_data_table_primitive_1505.py` (create)

**Interfaces:**
- Produces: `RowCapabilities` (frozen Pydantic model / dataclass): `bulk_select: bool = False`, `inline_editable: tuple[str, ...] = ()`, `row_state: bool = False`, `drill: bool = False`, `row_actions: tuple[str, ...] = ()` (action kinds, e.g. `("view","edit","delete")`), `column_visibility: bool = False`, `peek: str = "off"`. `DataTable(Fragment)`: `columns`, `rows`, `entity_name`, `api_endpoint`, `detail_url_template`, `table_id`, `capabilities: RowCapabilities`, plus the existing table fields (sort/pagination/empty) carried for parity. Mirror the existing `Table`/`ListRegion` primitive definitions exactly for field style.

- [ ] **Step 1: Write the failing test** — construct `DataTable(...)` with a `RowCapabilities(bulk_select=True)`; assert field round-trips and defaults (`peek == "off"`, `drill is False`).
- [ ] **Step 2: Run, verify fail** (`ImportError`/`AttributeError`).
- [ ] **Step 3: Add `RowCapabilities` + `DataTable`** to `primitives.py`; export from the primitives `__all__`; import into `_render_tables.py`'s primitive import block.
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Regenerate any primitive/api-surface baseline** that enumerates Fragment primitives (`dazzle inspect api ir-types --write` if `DataTable` surfaces there; check `test_api_surface_drift.py`). Add the CHANGELOG note later.
- [ ] **Step 6: Commit** (`feat(render): RowCapabilities + DataTable primitive (#1505 P1)`).

### Task 1.3: Shared row-core `render_data_row` — byte-reproduce `dz-tr-row`

The heart of the convergence: one function emitting the rich row, gated by capabilities, byte-identical to `_render_table_row`.

**Files:**
- Create: `src/dazzle/render/fragment/renderer/_data_row.py` (the shared row-core + cell helpers)
- Test: `tests/unit/test_data_row_characterization_1505.py` (extend with the parity assertion)

**Interfaces:**
- Consumes: `RowCapabilities`, the cell-display logic (port `_render_cell_display`, `_render_inline_edit`, the ref/badge/bool/etc. branches from `http/runtime/htmx_render.py`), `dazzle.render.html.esc`.
- Produces: `render_data_row(columns: list[dict], item: dict, caps: RowCapabilities, *, entity_name, api_endpoint, detail_url_template, table_id) -> str` returning the `<tr class="dz-tr-row group" ...>` (+ peek panel row when `caps.peek == "expand"`, but Phase 1 keeps `peek` paths inert — peek is Phase 4).

- [ ] **Step 1: Write the failing parity test** — for every `CAP_MATRIX` case, translate the `table_dict` into `(columns, item, RowCapabilities, kwargs)` and assert `render_data_row(...) == <committed characterization fixture>`.
- [ ] **Step 2: Run, verify fail** (`ImportError: render_data_row`).
- [ ] **Step 3: Port the renderer.** Move/copy the row + cell + inline-edit logic from `htmx_render.py` into `_data_row.py`, restructured around `RowCapabilities` (the stopPropagation protocol §3.2 governs checkbox/edit/action/drill cells). Keep output **byte-identical** — same classes, same Alpine binds, same `# nosemgrep` markers, same `_item_id_js` single-quote handling (#1327). Reuse `dazzle.render.html.esc` / `html.escape` exactly as the source did.
- [ ] **Step 4: Run, verify pass** — every characterization case byte-matches. Iterate on §3 until green; do NOT alter the fixtures.
- [ ] **Step 5: Run the FULL suite** — `uv run pytest tests/ -m "not e2e" -q`; `uv run ruff check src/ tests/ --fix && uv run ruff format src/ tests/`; `uv run mypy src/dazzle`; `uv run lint-imports` (confirm `render is pure` still green — the row-core has no `http/` import).
- [ ] **Step 6: Commit** (`feat(render): render_data_row row-core byte-reproduces dz-tr-row (#1505 P1)`).

### Task 1.4: `_emit_data_table` + "render rows only" substrate entry

Wire the primitive to the row-core, and expose the rows-only entry the transport path will call.

**Files:**
- Modify: `src/dazzle/render/fragment/renderer/_render_tables.py` (add `_emit_data_table`)
- Modify: `src/dazzle/render/fragment/renderer/_emit.py` (dispatch `case DataTable():`)
- Create/Modify: a public `render/` entry `render_data_table_rows(dt: DataTable, ctx) -> str` returning just the `<tbody>` children (the `<tr>` set), used by both `_emit_data_table` and the Phase-2 transport adapter.
- Test: `tests/unit/test_data_table_emit_1505.py` (create)

**Interfaces:**
- Consumes: `render_data_row` (1.3), `DataTable`/`RowCapabilities` (1.2).
- Produces: `_emit_data_table(self, dt, ctx) -> str` (full table primitive incl. thead/tbody/pagination, for Phase-3 first-paint use); `render_data_table_rows(dt, ctx) -> str` (tbody-children only, for HTMX refresh).

- [ ] **Step 1: Write failing tests** — `render_data_table_rows(DataTable(rows=[item_a,item_b], caps=...))` equals the concatenation of `render_data_row` for each item; `_emit_data_table` wraps it in the table chrome. Build the `DataTable` from a `CAP_MATRIX` case so output ties back to the characterization fixtures.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** `_emit_data_table` + `render_data_table_rows`; register the `DataTable` dispatch case in `_emit.py`.
- [ ] **Step 4: Run, verify pass; full suite + lint/mypy/import-linter green.**
- [ ] **Step 5: Commit** (`feat(render): _emit_data_table + render_data_table_rows rows-only entry (#1505 P1)`).

### Phase 1 gate
- [ ] Every characterization case byte-matches via the row-core; `pytest -m "not e2e"` fully green; ruff/mypy/lint-imports clean (`render is pure` KEPT). No caller switched → fleet byte-stable. `/bump patch`, CHANGELOG (Added: `DataTable` primitive + `render_data_row`), ship, monitor CI.

---

## Phase 2 — Switch the HTMX refresh path onto the substrate; delete `_render_table_row`

Now the rich table has exactly one renderer. Byte-golden-verified against the live HTMX response.

### Task 2.1: Route `list_handlers` through the substrate

**Files:**
- Modify: `src/dazzle/http/runtime/handlers/list_handlers.py:505-530` (build a `DataTable` fragment from `items` + `request.state.htmx_*`; render via `render_data_table_rows`)
- Test: `tests/unit/test_list_handler_substrate_parity_1505.py` (create)

**Interfaces:**
- Consumes: `render_data_table_rows` + `DataTable`/`RowCapabilities` (Phase 1), the existing `request.state.htmx_columns`/`htmx_detail_url`/`htmx_entity_name` + `bulk`/`inline` flags.
- Produces: identical `<tbody>` HTML to the current `"".join(_render_table_row(...))` path.

- [ ] **Step 1: Write the failing parity test** — capture the current `_list_handler_body` HTMX HTML for a representative entity (reuse a fixtures app, e.g. `fixtures/shapes_validation` or `examples/simple_task`) as a golden; then assert the new substrate path produces byte-identical HTML. (If booting is heavy, characterize at the `table_dict → rows` seam: assert `render_data_table_rows(build_data_table(table_dict)) == "".join(_render_table_row(table_dict, i) for i in items)` over `CAP_MATRIX`.)
- [ ] **Step 2: Run, verify fail** (new path not wired).
- [ ] **Step 3: Implement** — add `build_data_table(table_dict) -> DataTable` (maps the dict + resolves `RowCapabilities` from `bulk_actions`/`inline_editable`/`detail_url_template`/`peek_mode`), and replace the `"".join(_render_table_row...)` line with `render_data_table_rows(build_data_table(table_dict), ctx)`. Leave `_render_table_empty`/`_render_table_sentinel`/`_render_table_pagination` callers untouched for now (they move in Phase 3 or stay as thin transport wrappers calling substrate equivalents — out of this task).
- [ ] **Step 4: Run, verify pass; full suite green.**
- [ ] **Step 5: Commit** (`refactor(http): list refresh renders rows via substrate render_data_table_rows (#1505 P2)`).

### Task 2.2: Delete the duplicate `_render_table_row` family

**Files:**
- Modify: `src/dazzle/http/runtime/htmx_render.py` (delete `_render_table_row`, `_render_cell_display`, `_render_inline_edit`; keep `_render_table_empty`/`_render_table_pagination`/`_render_table_sentinel` only if still called — otherwise delete too)
- Modify: `src/dazzle/http/runtime/route_generator.py:127-137` (drop the deleted names from the re-export block)
- Modify: `tests/unit/test_route_generator_row_class_1327.py` (repoint #1327 assertions at `render_data_row`, OR delete if the characterization suite subsumes it — keep the #1327 escaping case alive somewhere)
- Modify: `tests/unit/test_typed_runtime_no_jinja.py` (update the covered-module list)

**Interfaces:**
- Consumes: nothing new.
- Produces: a smaller `htmx_render.py` with no row renderer; all rich-row HTML now originates in `render/`.

- [ ] **Step 1: Grep every caller/patch-point** — `grep -rn "_render_table_row\|_render_cell_display\|_render_inline_edit" src tests`. Confirm the only runtime caller was `list_handlers.py:530` (now switched) and the re-export in `route_generator.py`.
- [ ] **Step 2: Delete** the functions + their re-exports; migrate the #1327 escaping assertion into `test_data_row_characterization_1505.py` (the `o'brien` case already covers it — assert it explicitly).
- [ ] **Step 3: Run, verify fail-then-fix** — full suite; fix any patch-point/import that referenced the deleted names. Update `test_typed_runtime_no_jinja.py`'s module list.
- [ ] **Step 4: Run the FULL suite + lint/mypy/lint-imports** — all green; `render is pure` KEPT; `test_typed_runtime_no_jinja` green with the shrunk list.
- [ ] **Step 5: Commit** (`refactor(http): delete duplicate _render_table_row family — substrate owns rich rows (#1505 P2)`).

### Task 2.3: ADR-0048 + ship

**Files:**
- Create: `docs/adr/0048-list-render-convergence.md`
- Modify: `docs/adr/INDEX.md`; `docs/adr/0038-rendering-layer-boundary.md` (add a "Completed by ADR-0048" note)
- Modify: `CHANGELOG.md` (+ `### Agent Guidance`: rich list rows now render via `render/`'s `render_data_row`; `http/` is transport-only; capability/orthogonality protocol)

- [ ] **Step 1: Write ADR-0048** — record the convergence: substrate owns list-row rendering; `http/` transport-only; the migration-artifact root cause; the orthogonality invariant as the standing rule; supersedes the post-hoc "transport concern" framing. Reference #1505 + the design spec.
- [ ] **Step 2: Update INDEX + ADR-0038 cross-ref.**
- [ ] **Step 3: Run `tests/unit/test_htmx_workspace_composite.py`** (card-safety on the now-substrate-rendered list DOM) + full suite.
- [ ] **Step 4: `/bump patch`, CHANGELOG, commit, push, monitor CI.** Comment on #1505 noting Phase 1+2 complete (rich table converged; duplicate deleted); leave #1505 open for Phase 3 (fold list-region/embedded) + Phase 4 (#1494 peek).

### Phase 2 gate
- [ ] HTMX list-refresh output byte-identical to pre-#1505; `_render_table_row` family deleted; one renderer for the rich table; full suite + card-safety + import-linter green. ADR-0048 landed.

---

## Phases 3–4 (follow-on plans, authored after Phase 2 lands)

Deliberately not detailed here — their concrete shape depends on what Phase 2 proves about the row-core and `build_data_table` seam.

- **Phase 3** — fold `_emit_list_region` + `_emit_table` onto the shared row-core as `list-region` / `embedded` archetype presets (capability subsets + the `data-dz-list-kind` marker). *May* churn workspace-region goldens — re-baseline deliberately, re-run card-safety. Separate plan: `…-list-render-convergence-p3.md`.
- **Phase 4** — add the `peek` capability + `when_empty` to the shared row-core, resolving #1494 in one place (the stashed `stash@{0}` peek WIP is superseded — re-derive on the converged core). Separate plan: `…-1494-peek-when-empty-on-converged-core.md`.

## Self-Review

- **Spec coverage:** §1 root-cause → ADR-0048 (2.3); §3.1 capability vector → `RowCapabilities` (1.2); §3.2 protocol → row-core port (1.3); §4.1 row-core in render/ → `_data_row.py` (1.3); §4.2 transport-only http/ → 2.1/2.2; §4.3 rows-only entry → `render_data_table_rows` (1.4); §5 phases 1–2 → this plan, 3–4 → forward-referenced; §6 testing/blast-radius → characterization (1.1) + parity (2.1) + card-safety (2.3); §7 MDF → ADR-0048. Covered.
- **Placeholder scan:** none — characterization-driven tasks pin output via committed fixtures rather than inlining 200 lines of HTML (the fixtures ARE the spec of the bytes).
- **Type consistency:** `RowCapabilities`/`DataTable` (1.2) → `render_data_row` (1.3) → `render_data_table_rows`/`_emit_data_table` (1.4) → `build_data_table` (2.1) — names/signatures consistent across tasks.
- **Open questions (spec §8)** resolved as: `RowCapabilities` = frozen model (1.2); rows-only entry = `render_data_table_rows(dt, ctx)` taking a built `DataTable` (1.4); `DataTable` vs `Table` merge deferred to Phase 3.
