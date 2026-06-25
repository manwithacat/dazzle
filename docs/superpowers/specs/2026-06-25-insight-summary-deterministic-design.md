# Deterministic `insight_summary` — grounded narrative region (#1470, Slice 1)

**Status:** Approved design — ready for implementation plan.
**Issue:** #1470 (UX region-primitive RFC), sequencing item 5 (`insight_summary`).
**This spec is Slice 1 of 3** (decided during brainstorm): a deterministic, no-LLM narrative. Slice 2 swaps the template generator for a pre-computed `llm_intent`; Slice 3 adds refresh/AIJob/clickable citations.

## Goal

A region that renders a **grounded, deterministic narrative** over a grouped aggregate — *scale + leader + outlier* — above a **trust block** showing the exact underlying values, the scope, and a "Computed" badge. The prose is generated from the real numbers (template NLG), so it cannot hallucinate and every claim cites an exact value. No LLM.

```dsl
team_insight:
  source: Alert
  display: insight_summary
  group_by: team
  aggregate:
    count: count(Alert)
```
Renders, e.g.: *"142 alerts across 4 teams. Platform leads at 12 (34% of the total). Data is anomalously high (45 vs a typical ~10)."* + a trust block: the per-team values, "Scope: all teams", a "Computed from live data" badge.

## Why deterministic first (decided during brainstorm)

The trustworthy core of an insight summary doesn't need an LLM — both reference products (Tableau Pulse, Power BI Smart Narratives) lean on template-based NLG from the real aggregates. Deterministic prose is **grounded by construction** (computed from the actual numbers, exact citations), **testable + zero cost/latency**, and builds the hard, valuable parts (grounding + trust-UX) first. The LLM becomes a **swappable generator** in Slice 2, not the foundation — matching the framework's deterministic-first, conformance-visible philosophy ("AI narrates *verifiable* charts").

## Design decisions (locked)

1. **Deterministic, no LLM** (Slice 1). Computed at render.
2. **Self-contained data binding** — reuses the existing `source`/`group_by`/`aggregate` on `WorkspaceRegion` (exactly like `bar_chart`); pairs with a chart by authoring convention. The explicit `narrates: <sibling_region>` link is a Phase 2 DRY tightening.
3. **Fixed framework vocabulary** — scale + leader + outlier. Author declares the region + data; the framework writes the narrative. Author-configurable vocabulary is deferred.
4. **Outlier callout reuses the shipped `flag_outliers`** (`dazzle.render.fragment.outliers`) + `ComparisonOutlierSpec` (default `iqr`).
5. **Trust block** = narrative lines + the underlying-values citation list + scope descriptor + a "Computed" badge. **No confidence score** (a deterministic narrative is exact; confidence is Slice 2's LLM concern). For the MVP the **scope descriptor is a simple derived string** — `"across all <group_label>"` (e.g. "across all teams"), plus `" (filtered)"` when the region carries a `filter:`. A full scope-predicate description is deferred.
6. **Measure-aware NLG** — additive measures (`count`/`sum`) get totals + "% of total"; non-additive (`avg`/`min`/`max`) get "leader by value" with no total/% (you cannot sum averages).

## Non-goals (deferred, noted not built)

- LLM-authored prose + confidence scoring (Slice 2).
- Refresh triggers / AIJob cost-tracking / clickable-to-datapoint citations (Slice 3).
- Author-configurable insight vocabulary; multi-dimension (`group_by: [a, b]`); delta-vs-prior-period narration.
- The `narrates: <sibling_region>` cross-region link.

## Architecture — four layers, heavy reuse

The stack is `http → page → render → core`.

### core/ir (`src/dazzle/core/ir/workspaces.py`)
- Add one `DisplayMode.INSIGHT_SUMMARY = "insight_summary"`.
- **No new `WorkspaceRegion` fields** — reuses `source`, `group_by`, `aggregate`.
- Drifts the api-surface ir-types baseline (one new enum member) + golden-master + parser-corpus snapshots — regenerate with CHANGELOG notes.

### core/parser (`src/dazzle/core/dsl_parser_impl/workspace.py`)
- **No change** — `display: insight_summary` parses through the existing `_kw_display` enum dispatch once the enum member exists.

### core/validation (`src/dazzle/core/validation/ux.py`)
- New `validate_insight_summaries(appspec)` (mirrors `validate_comparison_regions`), wired into `core/lint.py` + exported from `validator.py` / `validation/__init__.py`.
- Rules (emit `E_INSIGHT_*`):
  - `E_INSIGHT_GROUP_BY_REQUIRED`: `display: insight_summary` requires `group_by`.
  - `E_INSIGHT_AGGREGATE_REQUIRED`: requires at least one `aggregate`.
  - (Multi-dim `group_by: [a, b]` is out of scope → `E_INSIGHT_SINGLE_DIM_ONLY` if a list is given.)

### render/ — pure NLG (`src/dazzle/render/fragment/insight.py`, new)
- `build_insight_narrative(buckets, *, measure_name, measure_func, group_label, scope_desc, outlier_spec) -> InsightNarrative`.
  - `buckets`: the computed `[{"label", "value"}, ...]` (the same shape `bar_track`/`comparison` consume).
  - Computes: **scale** (group count; total = sum of values for additive measures), **leader** (max-value bucket + its share for additive), **outlier** (first `flag_outliers` "high"/"low" flag over the bucket values).
  - Returns a frozen `InsightNarrative` dataclass: `lines: tuple[str, ...]` (the rendered statements), `citations: tuple[tuple[str, float], ...]` (label, value — the underlying values), `scope: str`, `badge: str` ("Computed from live data").
  - Pure, no I/O. Reuses `flag_outliers`. Additive detection: `measure_func in {"count", "sum"}`.

### http/orchestration (`workspace_region_orchestration.py` + `workspace_region_computes.py`)
- For `display == "INSIGHT_SUMMARY"` with `group_by` + `aggregate` and not scope-denied: compute `bucketed_metrics` via the existing `_compute_bucketed_aggregates` (the same call `bar_chart` makes), then call `build_insight_narrative`, threading the result into `RegionRenderInputs` (one new field `insight_narrative`) → the chart-family adapter ctx → `RegionContext` TypedDict (mirroring the `comparison_*` keys). A thin pure wrapper `build_insight_inputs(bucketed_metrics, ir_region, ...)` lives beside `build_comparison_inputs`.

### render/fragment (`region/_builders_charts.py` + `_dispatcher.py`)
- `_build_insight_summary(region, ctx)` → a trust card: the narrative `lines` as a stacked text block, then a trust footer (the citation values as a compact list/inline table, the scope, and the "Computed" badge via the accessible `data-dz-tone` badge shape). All strings escaped at emit. Register `"insight_summary": "_build_insight_summary"` in the dispatcher + `_SUPPORTED_DISPLAYS` (coverage.py) + the chart family.

## Render detail — the trust card

- **Narrative**: each statement on its own line (a `Stack` of text), e.g. scale / leader / outlier.
- **Trust footer** (the grounding): a compact rendering of `citations` (e.g. `Platform 12 · Payments 11 · Growth 10 · Data 45 · ML 1`) so the reader verifies the prose against the numbers; the `scope` descriptor; a "Computed from live data" badge (`data-dz-tone="neutral"` or similar). Every value is escaped at emit; the citation values are framework-computed numbers (no injection surface), the group labels come from data and are escaped.

## Edge cases

- **0 groups** → a single "No data" line (degrade; no leader/outlier).
- **1 group** → scale + leader only (no outlier; `flag_outliers` small-N guard returns no flags anyway).
- **All-equal / small-N** → no outlier line (the `flag_outliers` zero-spread + ≥4-value guards).
- **Non-additive measure** (`avg`/`min`/`max`) → leader-by-value, no total/%; scale line says "across N groups" without a summed total.
- **Non-finite values** → excluded from the outlier distribution (coerced to None at the bucket-read boundary, mirroring the comparison render's defensiveness).

## Testing (TDD per layer)

1. **IR** — `DisplayMode.INSIGHT_SUMMARY` value; regen ir-types baseline.
2. **Validation** — `E_INSIGHT_GROUP_BY_REQUIRED` (no group_by), `E_INSIGHT_AGGREGATE_REQUIRED` (no aggregate), `E_INSIGHT_SINGLE_DIM_ONLY` (list group_by); a valid region yields no errors; examples don't false-positive.
3. **Pure NLG** — `build_insight_narrative` over several vectors: additive count (scale+leader%+outlier), additive sum, non-additive avg (no %), a clear-outlier set (reuses the verified `[100,98,96,94,92,5]`-style vector), a flat set (no outlier), 1 group, 0 groups. Assert the statement strings + the citation list + the additive/non-additive branch.
4. **Orchestration** — `build_insight_inputs` over stub buckets: produces the narrative; INSIGHT_SUMMARY threads it into `RegionRenderInputs`.
5. **Render** — the trust card contains the narrative lines, the citation values, the scope, the "Computed" badge; HTML-escaping of group labels preserved; empty buckets → "No data".
6. **Example + catalogue + ship** — add an `insight_summary` region to `examples/ops_dashboard`; add `cat_insight_summary` as the 9th mode in the `ux_catalogue` fixture + a manifest entry (it auto-lands on the published catalogue page via the harness); `dazzle validate` exit 0; regen golden-master; full `pytest -m "not e2e"` (ignore the 3 `test_fuzzer_oracle` pollution failures); ruff + bare `mypy src/dazzle` clean; `/bump patch` with CHANGELOG (`### Added` + `### Agent Guidance` on when to use insight_summary + the deterministic-now/LLM-later note + the api-surface drift note); commit + tag + push; watch CI + docs deploy green.

## Complexity / risk notes (model-driven-failure-modes lens)

- **Traceability:** the narrative traces directly to `group_by` + `aggregate` in the DSL — no side code, no LLM. `build_insight_narrative` is pure + fully tested.
- **Detector:** validation (`E_INSIGHT_*`) is live in `dazzle validate`; render is covered by the card-safety scanners + the composite-DOM gate + the catalogue fidelity gate.
- **No hallucination surface:** the prose is computed from the real aggregates; the trust block shows those same numbers — the narrative is verifiable by construction. This is the structural answer to the 4GL/AI "plausible-but-wrong" failure mode.
- **Scope safety:** narrative computed *after* the scoped aggregate fetch — never widens scope, identical to `comparison`/`bar_chart`.
- **No new escape hatch, no LLM** in this slice — deterministic, declarative, conformance-visible.

## Deferred (future slices / brainstorms)

- **Slice 2:** swap the template generator for a pre-computed `llm_intent` over the same grounded buckets (the deterministic narrative becomes the fallback + the grounding contract the LLM must respect); add confidence scoring to the trust block.
- **Slice 3:** refresh triggers (schedule / on-data-change), AIJob cost-tracking integration, verified clickable citations (drill from a claim to the cited datapoint).
- Author-configurable vocabulary; `narrates: <sibling_region>` link; multi-dimension; delta-vs-prior-period.
