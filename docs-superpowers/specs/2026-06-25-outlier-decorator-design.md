# `outlier_on` — Statistical Outlier Decorator on Region List Columns (#1470, slice 4)

**Status:** Approved design — ready for implementation plan.
**Issue:** #1470 (UX region-primitive RFC), sequencing item 3 (second half: the `outlier`/`rag` decorator).
**Predecessor:** `display: comparison` (slice shipped v0.86.23) — this slice reuses its `flag_outliers` engine and `ComparisonOutlierSpec`.

## Goal

Let a `display: list` region flag statistically anomalous cells in one numeric column,
rendered as a WCAG-safe badge (colour + icon + text). One new region keyword names the
column; the existing `outlier_method:` keyword chooses the statistical test. This
generalises the outlier flagging the `comparison` region already does on its ranked metric
to an ordinary list/table column.

```dsl
system_health:
  source: System
  display: list
  fields: [name, response_time_ms, error_rate]
  outlier_on: response_time_ms     # NEW keyword — the column to flag
  outlier_method: iqr              # REUSED from comparison; defaults to iqr if omitted
```

Each `response_time_ms` cell renders its formatted value; rows whose value is a statistical
outlier (vs the displayed rows) additionally render a `⚠ high` / `⚠ low` badge. Other
columns are untouched.

## Non-goals (explicit YAGNI — deferred follow-ons, noted not built)

- **Multi-column** flagging in one region (would promote the flat `fields: [a,b,c]` list to a
  rich per-column dash-list — see "Deferred" below).
- **Surface-list-field** attachment (a `format:`-style trailing modifier on a `SurfaceElement`).
- **Full-scoped-set population** (a separate aggregate fetch of the column so the flag is
  statistically sound under pagination). v1 judges against the displayed rows only.
- **Fixed-band RAG decorator** (good/bad tone by author threshold). That is a *separate*
  primitive (#1470 sequencing); this slice is deliberately the purely-statistical half and
  does NOT bake good/bad semantics into a statistical signal.
- Display modes other than `list` (`grid`, `table`, `kanban`, …).

## Design decisions (locked during brainstorm)

1. **Statistical only**, not RAG bands (RAG deferred).
2. **Region columns**, not surface fields (surface attachment deferred).
3. **Population = displayed region rows** (bounded by `limit:`). Honest; documented. The
   `flag_outliers` small-N guard (< 4 numeric values → no flags) means tiny lists never flag.
4. **Single-column keyword** grammar: `outlier_on: <col>` + reuse `outlier_method:`.
5. **Uniform `warning` tone** for both directions; direction carried by icon + text. An outlier
   is *notable*, not inherently good/bad (a high response-time is bad, a high score is good —
   the framework can't know). Good/bad-by-direction is the deferred RAG decorator's job.
6. **Reuse `region.outlier`** (the `ComparisonOutlierSpec` already set by `outlier_method:`) —
   no new spec model; only one new IR field (`outlier_on`).

## Architecture — four layers, maximal reuse

The stack is `http → page → render → core`. Each layer's change:

### core/ir (`src/dazzle/core/ir/workspaces.py`)
- Add one field: `WorkspaceRegion.outlier_on: str | None = None` (the column name).
- The statistical method reuses the existing `WorkspaceRegion.outlier: ComparisonOutlierSpec | None`
  (already populated by `outlier_method:`, shared with `comparison`). No new model.
- Drifts the api-surface ir-types baseline (one new field) + golden-master + parser-corpus
  snapshots — regenerate with CHANGELOG notes.

### core/parser (`src/dazzle/core/dsl_parser_impl/workspace.py`)
- Add `outlier_on: str | None = None` to `_WorkspaceRegionState`.
- Add `_kw_outlier_on` (ident keyword, mirrors `_kw_rank_by`) → `state.outlier_on`. Register in
  `_WORKSPACE_REGION_IDENT_KEYWORDS`.
- `outlier_method:` / `_parse_outlier_spec` already exist (from comparison) — no change.
- Wire `outlier_on=state.outlier_on` into `_build_workspace_region(...)`.

### core/validation (`src/dazzle/core/validation/ux.py`)
- New `validate_outlier_decorators(appspec)` (mirrors `validate_comparison_regions`), wired into
  `core/lint.py` + exported from `validator.py` / `validation/__init__.py`.
- Rules (emit `E_OUTLIER_*`):
  - `E_OUTLIER_DISPLAY`: `outlier_on` set but `display != list`.
  - `E_OUTLIER_NOT_NUMERIC`: `outlier_on` must name a numeric field (int/decimal/float/money) on
    the source entity (reuse `_NUMERIC_FIELD_KINDS` from the comparison validator). Missing field
    → same code.
  - Reuse the comparison outlier-param check (`sigma_k > 0`; `threshold` needs ≥ 1 bound) via the
    shared `_validate_comparison_outlier` helper.
  - If `outlier_on` is set without `outlier_method:`, that is valid — defaults to `iqr` at compute
    time (mirrors `comparison`). No error.

### http/runtime (orchestration)
- In `workspace_region_orchestration.py`, for a `display == "LIST"` region with `outlier_on` set
  and not scope-denied: pull that column's values from the fetched `items` (index order),
  coerce to `float | None`, run `flag_outliers(values, spec)` where
  `spec = region.outlier or ComparisonOutlierSpec()` (iqr default).
- Produce an index-aligned `outlier_flags: list[Literal["low","high"] | None]`.
- Extract a pure, unit-testable helper `build_outlier_flags(items, *, column, spec) ->
  list[Flag | None]` in `workspace_region_computes.py` (sits beside `build_comparison_rows`).
- Thread `outlier_flags` + `outlier_on` (the column key) into `RegionRenderInputs` (two new
  fields, mirroring `comparison_rows`/`comparison_max`) → the list-family adapter ctx
  (`_build_list_adapter_ctx` or the LIST branch) → `ctx["outlier_flags"]` / `ctx["outlier_on"]`.
- Add the two keys to the `RegionContext` TypedDict (mirrors the `comparison_*` keys).

### render (`src/dazzle/render/fragment/region/_builders_tables.py::_build_list`)
- `_build_list` already builds each cell via `_render_typed_value(item, col)` returning a
  **Fragment** (cells are `list[object]`, not strings), so a composite cell is natural.
- Read `outlier_on` (column key) + `outlier_flags` (index-aligned to `items`) from ctx.
- In the per-item / per-col loop: when `col["key"] == outlier_on` and the row's flag is set,
  render the cell as a composite of the typed value **+** an outlier-badge fragment; otherwise the
  plain typed value.
- Extract a small helper `_outlier_badge(flag) -> Fragment` emitting the WCAG triple.

## Render detail — the WCAG badge

Reuse the existing accessible badge mechanism (the `data-dz-tone` + `role="status"` +
`aria-label` shape used by `_render_status_badge_html`), layered with the redundant channels:

- **Colour:** `data-dz-tone="warning"` (uniform — see decision 5).
- **Icon:** `⚠`.
- **Text:** `high` / `low` (the flag direction), and an `aria-label` like
  `"Outlier: high"` for screen readers.

All user/data strings are escaped at emit (the badge value text is the hardcoded `high`/`low`
literal, not user data, so no injection surface; the cell value itself flows through the existing
`_render_typed_value` escaping unchanged). The composite cell keeps the value first, badge second.

## Edge cases (inherited from `flag_outliers`, already tested)

- Small-N guard: < 4 numeric values → no flags (tiny lists never flag).
- Zero spread (all-equal) → no flags.
- `None` values excluded from the distribution and never flagged.
- Non-finite (`inf`/`nan`): `build_outlier_flags` coerces them to `None` when reading the column,
  so they are excluded from the distribution and never flagged — keeps anomalous float storage
  from skewing the quartiles (the `comparison` render added the same defensiveness at its seam).
- `outlier_method: none` → no flags (decorator is inert).

## Testing (TDD per task)

1. **IR** — `outlier_on` field defaults + round-trips; regen ir-types baseline.
2. **Parser** — `outlier_on: response_time_ms` + `outlier_method: sigma:2` parses onto the region;
   regen parser-corpus snapshot if drifted.
3. **Validation** — `E_OUTLIER_DISPLAY` (non-list), `E_OUTLIER_NOT_NUMERIC` (string column),
   reused outlier-param errors; a valid list region yields no errors; examples don't false-positive.
4. **Orchestration** — pure `build_outlier_flags(items, column, spec)`: index alignment, low/high
   from `flag_outliers`, `None`-value handling, small-N → all-None.
5. **Render** — composite cell on a flagged row contains the value AND a `data-dz-tone="warning"`
   badge with `⚠` + `high`/`low`; non-flagged rows render the plain value; HTML-escaping of the
   cell value preserved; empty/`outlier_on`-unset region renders an ordinary list.
6. **Example + ship** — add `outlier_on` to an `examples/ops_dashboard` `display: list` region
   (e.g. the systems list flagging `response_time_ms`); `dazzle validate` exit 0; regen
   golden-master; full `pytest -m "not e2e"` (ignore the 3 known `test_fuzzer_oracle` pollution
   failures, which pass in isolation); ruff + bare `mypy src/dazzle` clean; `/bump patch` with
   CHANGELOG (`### Added` + `### Agent Guidance` + the api-surface drift note); commit + tag +
   push; watch CI green (the walks render the decorated list).

## Complexity / risk notes (model-driven-failure-modes lens)

- **Traceability:** the runtime behaviour (a flagged cell) traces directly to `outlier_on` +
  `outlier_method:` in the DSL — no side code. The `flag_outliers` engine is pure + already tested.
- **Detector:** validation (`E_OUTLIER_*`) is live in `dazzle validate`; the render path is covered
  by the card-safety scanners + the composite-DOM gate.
- **Scope safety:** flagging runs *after* the scoped fetch over the displayed rows — never widens
  scope, identical to the `comparison` within-scope contract.
- **No new escape hatch / no LLM** — deterministic, declarative, conformance-visible.

## Deferred (each its own future brainstorm)

- Multi-column flagging via a rich `fields:` dash-list (`- field: x` + `outlier: iqr`).
- Surface-list-field attachment (a `format:`-style modifier on `SurfaceElement`).
- Full-scoped-set population (sound stats under pagination).
- The fixed-band **RAG decorator** (good/bad tone by author threshold) — the other half of
  #1470's "outlier/rag decorator".
- `insight_summary` (the next planned brainstorm after this slice).
