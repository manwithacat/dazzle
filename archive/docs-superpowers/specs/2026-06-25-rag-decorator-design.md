# `rag_on` — fixed-band RAG decorator (#1470, closes item 3)

**Status:** Approved design — ready for implementation plan.
**Issue:** #1470 (UX region-primitive RFC), sequencing item 3 — the deterministic fixed-band half of the "outlier/rag decorator". The statistical half (`outlier_on`) shipped v0.86.24; this closes the item.

## Goal

Flag a `display: list` column with a **red/amber/green tone** by **author-defined fixed bands** (not statistics), rendered as a WCAG-safe badge (tone colour + icon + text). The deterministic sibling of `outlier_on`.

```dsl
system_health:
  source: System
  display: list
  rag_on: error_rate
  tone_bands:
    - at: 5
      tone: destructive   # >= 5% -> red
    - at: 1
      tone: warning       # >= 1% -> amber
    - at: 0
      tone: positive      # >= 0% -> green
```
Each `error_rate` cell renders its value + a tone badge whose colour/label come from the matched band: bands are walked in **descending `at`** order, the first where `value >= at` wins (the existing `ToneBandSpec` rule).

## Why this design (decided during brainstorm)

The framework already has `ToneBandSpec(at: float, tone: str)` + `_parse_tone_bands_block` (#1144, for cohort_strip lenses) — author thresholds → tone, "first band cleared wins". That is exactly the RAG band model, so `rag_on` is **`outlier_on` with author bands instead of a statistical test**. Maximal reuse; the two decorators are consistent siblings sharing the list-cell render path.

## Design decisions (locked)

1. **Deterministic, author-thresholds** (RAG), not statistical (that's `outlier_on`).
2. **Reuse `tone_bands` / `ToneBandSpec`** for the band grammar — no new band model or syntax.
3. **Region-list-column attachment** (`rag_on: <col>`), mirroring `outlier_on` exactly. Surface-field attachment + multi-column stay deferred.
4. **Band tone is the cell tone** — `positive`/`warning`/`destructive` (the RAG palette); the badge label is derived from the tone (`positive`→"good", `warning`→"watch", `destructive`→"critical", else the tone word) + an icon, so the WCAG triple (colour + icon + text) holds.
5. **Population = the cell's own value** — RAG is per-cell against fixed thresholds, needing no distribution (unlike `outlier_on`). So no scope/aggregation concern beyond the already-scoped fetch.

## Non-goals (deferred)

- Surface-list-field attachment; multi-column flagging.
- Author-labelled bands (a `label:` on `ToneBandSpec`) — the MVP derives the label from the tone.
- Non-list display modes; below-all-bands fallback styling beyond "no badge".
- Combining `rag_on` and `outlier_on` on the same column (validation may warn; MVP allows independent columns).

## Architecture — four layers, near-total `outlier_on` reuse

### core/ir (`src/dazzle/core/ir/workspaces.py`)
- Add `WorkspaceRegion.rag_on: str | None = None` and `tone_bands: list[ToneBandSpec] = Field(default_factory=list)`.
- Reuse the existing `ToneBandSpec` (no new model).
- Drifts api-surface ir-types (two fields) + golden-master + parser-corpus (`tone_bands` defaults to `[]`, `rag_on` to None → likely no corpus drift). Regenerate ir-types + golden-master with CHANGELOG notes.

### core/parser (`src/dazzle/core/dsl_parser_impl/workspace.py`)
- Add `rag_on: str | None = None` and `tone_bands: list[Any] = field(default_factory=list)` to `_WorkspaceRegionState`.
- `_kw_rag_on` (ident keyword, mirror `_kw_outlier_on`) → `state.rag_on`.
- `_kw_tone_bands` (ident keyword) → calls the existing `self._parse_tone_bands_block()` → `state.tone_bands`. (Confirm `_parse_tone_bands_block` is reachable as a parser method from the region-keyword dispatch; if it lives on a different mixin, call the same underlying parse.)
- Register both in `_WORKSPACE_REGION_IDENT_KEYWORDS`; wire into `_build_workspace_region`.

### core/validation (`src/dazzle/core/validation/ux.py`)
- New `validate_rag_decorators(appspec)` (mirror `validate_outlier_decorators`), wired into `lint.py` + exported.
- Rules (emit `E_RAG_*`):
  - `E_RAG_DISPLAY`: `rag_on` requires `display: list`.
  - `E_RAG_NOT_NUMERIC`: `rag_on` must name a numeric field (int/decimal/float/money) on the source — reuse `_NUMERIC_FIELD_KINDS`.
  - `E_RAG_BANDS_REQUIRED`: `rag_on` requires a non-empty `tone_bands`.

### http/orchestration (`workspace_region_computes.py` + `workspace_region_orchestration.py`)
- Pure `build_rag_tones(items, *, column, bands) -> list[str | None]` (mirror `build_outlier_flags`): per item, coerce the column to a finite float; evaluate against `bands` (descending `at`, first `value >= at` wins) → the band's tone, else `None`.
- For `display == "LIST"` with `rag_on` set and not scope-denied: compute `rag_tones` (index-aligned to `items`); thread `rag_tones` + `rag_on` into `RegionRenderInputs` → the LIST adapter ctx → `RegionContext` TypedDict (mirroring the `outlier_*` keys).

### render (`region/_builders_tables.py::_build_list`)
- Generalize the existing `outlier_on` composite-cell path: when `col["key"] == rag_on` and the row's tone is set, render the cell as `Row(value, _rag_badge(tone))`. `_rag_badge(tone)` emits the accessible `dz-badge` with `data-dz-tone=<tone>` + an icon + the tone-derived label (escaped). Reuse the `_outlier_badge` shape (a new sibling helper).

## Render detail — the RAG badge

Reuse the accessible `dz-badge` (`data-dz-tone` + `role="status"` + `aria-label`), with the **band's tone** as the colour and a derived label as the text: `positive`→"good", `warning`→"watch", `destructive`→"critical", any other tone → the tone word. Icon e.g. a small dot/flag. All label text escaped at emit (the tone is from a closed vocabulary; the label is derived, no user data in the badge — the cell value flows through the existing `_render_typed_value` escaping unchanged).

## Edge cases

- Value below all bands → `None` → no badge (plain value). If the author includes an `at: 0` band, a non-negative value always matches it.
- Non-finite / None / non-numeric value → `None` → no badge (coerced at the `build_rag_tones` read boundary, mirroring `build_outlier_flags`).
- Empty `tone_bands` → blocked by validation; at render, `build_rag_tones` returns all-None (inert).
- Unknown tone string in a band → still rendered as `data-dz-tone=<that string>` (the badge CSS degrades gracefully); the label falls back to the tone word.

## Testing (TDD per layer)

1. **IR** — `rag_on` + `tone_bands` defaults/round-trip; regen ir-types baseline.
2. **Parser** — `rag_on: error_rate` + a `tone_bands:` dash-list parse onto the region; parser-corpus regen if drifted.
3. **Validation** — `E_RAG_DISPLAY` (non-list), `E_RAG_NOT_NUMERIC` (string column), `E_RAG_BANDS_REQUIRED` (no bands); a valid region yields no errors; examples don't false-positive.
4. **Pure tone pass** — `build_rag_tones`: descending-`at` first-match, below-all → None, non-finite/None → None, index alignment to items.
5. **Render** — flagged cell has `data-dz-tone="destructive"` + the derived label; non-matching rows plain; HTML-escaping preserved; `rag_on` unset → ordinary list.
6. **Example + catalogue + ship** — add a `rag_on` region to `examples/ops_dashboard`; add `cat_rag` as the **10th catalogue mode** (fixture + manifest, auto-lands on the published page); `dazzle validate` exit 0; regen golden-master; full `pytest -m "not e2e"` (ignore the 3 `test_fuzzer_oracle` pollution failures); ruff + bare `mypy src/dazzle` clean; `/bump patch` with CHANGELOG (`### Added` + `### Agent Guidance` on `rag_on` vs `outlier_on` + the band semantics + the api-surface drift note); commit + tag + push; watch CI + docs deploy green.

## Complexity / risk notes (model-driven-failure-modes lens)

- **Traceability:** a flagged cell traces directly to `rag_on` + `tone_bands` in the DSL — no side code, no statistics, fully deterministic.
- **Detector:** validation (`E_RAG_*`) is live in `dazzle validate`; render is covered by the card-safety scanners + composite-DOM gate + catalogue fidelity gate.
- **Scope safety:** the tone pass runs after the scoped fetch over the displayed rows — never widens scope, identical to `outlier_on`.
- **No new escape hatch, no LLM** — deterministic, declarative, conformance-visible.

## Deferred (future)

- Surface-list-field attachment; multi-column RAG.
- Author-labelled bands (`label:` on `ToneBandSpec`) for custom badge text.
- RAG on aggregate/chart cells; combined RAG+outlier on one column.
