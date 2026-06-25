# `display: comparison` Implementation Plan (#1470)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `display: comparison` — a ranked-league region that ranks rows by a metric (aggregated groups or entity rows) and auto-flags statistical outliers, rendered as a ranked table with inline bars.

**Architecture:** Reuse the scope-safe `Repository.aggregate` GROUP BY spine (group mode) / `gated_list` (entity-row mode); rank + flag outliers in a pure post-fetch pass; render a typed `Table` reusing the format layer + `bar_track` cell. New DisplayMode + a few `WorkspaceRegion` fields; no new query semantics.

**Tech Stack:** Python 3.12, Pydantic IR, pytest. Layers `http → page → render → core`.

## Global Constraints

- Layer rule: `flag_outliers` + `_build_comparison` are pure → live in `render/` (no I/O); orchestration in `http/`; IR/parser/validation in `core/`. `core` must not import `page`/`http`.
- `ruff check src/ tests/` + `ruff format src/ tests/` clean; `mypy src/dazzle` clean.
- **Run the full `pytest -m "not e2e"` before shipping** — the golden-master + walk jobs live outside the `/ship` gate subset. (Two CI slips this session came from shipping on the subset.)
- The new `DisplayMode.COMPARISON` + IR fields **will drift two baselines** — regenerate both at ship time: golden-master snapshot (`pytest tests/integration/test_golden_master.py --snapshot-update`) and the api-surface ir-types baseline (`dazzle inspect api ir-types --write`). Each needs a CHANGELOG note (the api-surface drift gate requires it).
- Within-scope ranking: rank + flag run AFTER the scoped fetch — never widen scope.
- The 3 `test_fuzzer_oracle` failures in the full suite are pre-existing pollution (pass isolated) — ignore.

## File structure

- `src/dazzle/core/ir/workspaces.py` — `DisplayMode.COMPARISON`, `ComparisonOutlierSpec`, `WorkspaceRegion.{rank_by,order,outlier}`.
- `src/dazzle/core/ir/__init__.py` — export `ComparisonOutlierSpec`.
- `src/dazzle/core/dsl_parser_impl/workspace.py` — `_kw_rank_by`/`_kw_order`/`_kw_outlier_method` + state fields + builder wiring.
- `src/dazzle/core/validation/` (the region validator — locate via `grep -rn "display\|DisplayMode\|region" src/dazzle/core/validation/*.py`) — `E_COMPARISON_*`.
- `src/dazzle/render/fragment/outliers.py` (new) — `flag_outliers`.
- `src/dazzle/render/fragment/region/_builders_charts.py` — `_build_comparison`.
- `src/dazzle/render/fragment/region/_dispatcher.py` — register `"comparison": "_build_comparison"`.
- `src/dazzle/http/runtime/workspace_aggregation.py` (+ `workspace_region_orchestration.py`) — compute comparison rows into `ctx`.

---

## Task 1: IR — DisplayMode + ComparisonOutlierSpec + region fields

**Files:**
- Modify: `src/dazzle/core/ir/workspaces.py` (DisplayMode enum; new model; WorkspaceRegion fields)
- Modify: `src/dazzle/core/ir/__init__.py` (export)
- Test: `tests/unit/test_comparison_ir.py`

**Interfaces — Produces:**
- `DisplayMode.COMPARISON = "comparison"`
- `ComparisonOutlierSpec(method: Literal["iqr","sigma","threshold","none"] = "iqr", sigma_k: float | None = None, threshold_low: float | None = None, threshold_high: float | None = None)` (frozen BaseModel)
- `WorkspaceRegion.rank_by: str | None = None`, `.order: Literal["asc","desc"] = "desc"`, `.outlier: ComparisonOutlierSpec | None = None`

- [ ] **Step 1: failing test**

```python
# tests/unit/test_comparison_ir.py
from dazzle.core.ir.workspaces import ComparisonOutlierSpec, DisplayMode, WorkspaceRegion


def test_comparison_display_mode() -> None:
    assert DisplayMode.COMPARISON.value == "comparison"


def test_outlier_spec_defaults() -> None:
    s = ComparisonOutlierSpec()
    assert s.method == "iqr"
    assert s.sigma_k is None and s.threshold_low is None and s.threshold_high is None


def test_region_comparison_fields() -> None:
    r = WorkspaceRegion(
        name="league",
        display=DisplayMode.COMPARISON,
        rank_by="rate",
        order="asc",
        outlier=ComparisonOutlierSpec(method="sigma", sigma_k=2.0),
    )
    assert r.rank_by == "rate"
    assert r.order == "asc"
    assert r.outlier is not None and r.outlier.method == "sigma" and r.outlier.sigma_k == 2.0


def test_region_comparison_defaults() -> None:
    r = WorkspaceRegion(name="league", display=DisplayMode.COMPARISON)
    assert r.rank_by is None and r.order == "desc" and r.outlier is None
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_comparison_ir.py -q` → FAIL (no COMPARISON / model / fields).
- [ ] **Step 3: implement.** In `workspaces.py`: add `COMPARISON = "comparison"  # #1470: ranked-league` to `DisplayMode`. Add the model near `ReferenceBand` (the chart-config models):

```python
class ComparisonOutlierSpec(BaseModel):
    """Outlier-flag config for `display: comparison` (#1470)."""

    method: Literal["iqr", "sigma", "threshold", "none"] = "iqr"
    sigma_k: float | None = None
    threshold_low: float | None = None
    threshold_high: float | None = None

    model_config = ConfigDict(frozen=True)
```

Add to `WorkspaceRegion` (near `reference_bands`):

```python
    # #1470 display: comparison — ranked league
    rank_by: str | None = None  # aggregate name (group mode) or numeric field (entity-row mode)
    order: Literal["asc", "desc"] = "desc"
    outlier: ComparisonOutlierSpec | None = None
```

Ensure `Literal` and `ConfigDict` are imported in `workspaces.py` (they are — `ConfigDict` is used by sibling models; add `from typing import Literal` if absent). In `core/ir/__init__.py` add `ComparisonOutlierSpec` to the `from .workspaces import (...)` block and `__all__` (alphabetical-ish, near other Comparison/Workspace types).

- [ ] **Step 4:** `uv run pytest tests/unit/test_comparison_ir.py -q` → PASS.
- [ ] **Step 5:** `uv run mypy src/dazzle` clean; `uv run ruff check src/ tests/ --fix && uv run ruff format src/ tests/`.
- [ ] **Step 6: regen api-surface ir-types baseline** (the new BaseModel + enum member drift it): `uv run dazzle inspect api ir-types --write` then `uv run pytest tests/unit/test_api_surface_drift.py -q` → PASS. Confirm the diff is only `ComparisonOutlierSpec` + the `comparison` enum member + the 3 WorkspaceRegion fields.
- [ ] **Step 7: commit**

```bash
git add src/dazzle/core/ir/workspaces.py src/dazzle/core/ir/__init__.py docs/api-surface/ir-types.txt tests/unit/test_comparison_ir.py
git commit -m "feat(#1470): IR for display: comparison (DisplayMode + ComparisonOutlierSpec + region fields)"
```

---

## Task 2: Parser — `rank_by:` / `order:` / `outlier_method:`

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/workspace.py` (region keyword dispatch ~line 2766–2945: `_WORKSPACE_REGION_KEYWORDS`, `_WorkspaceRegionState`, the `_build_region` assembler, new `_kw_*`)
- Test: `tests/unit/test_comparison_parser.py`

**Interfaces — Consumes:** `ComparisonOutlierSpec`, `DisplayMode` (Task 1). **Produces:** parsed `region.rank_by`/`order`/`outlier`.

**Outlier value grammar:** `iqr` | `sigma:<k>` | `threshold:low=<x>,high=<y>` (either of low/high optional) | `none`.

- [ ] **Step 1: failing test**

```python
# tests/unit/test_comparison_parser.py
from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl

_DSL = """
module m
app a "A"
entity Sale "Sale":
  id: uuid pk
  region: str(40)
  amount: decimal(12,2)

workspace ops "Ops":
  region league "League":
    source: Sale
    display: comparison
    group_by: region
    aggregates:
      total: sum(amount)
    rank_by: total
    order: asc
    outlier_method: sigma:2
"""


def _region(name: str):
    *_, fragment = parse_dsl(_DSL, Path("t.dsl"))
    ws = fragment.workspaces[0]
    return next(r for r in ws.regions if r.name == name)


def test_parses_rank_order_outlier() -> None:
    r = _region("league")
    assert r.rank_by == "total"
    assert r.order == "asc"
    assert r.outlier is not None
    assert r.outlier.method == "sigma" and r.outlier.sigma_k == 2.0
```

(Confirm `fragment.workspaces[0].regions` is the access path; if the harness differs, mirror `tests/unit/test_surface_format_modifier.py`'s navigation.)

- [ ] **Step 2:** run → FAIL (unknown keyword `rank_by` / `outlier_method`).
- [ ] **Step 3: implement.** Add fields to `_WorkspaceRegionState` (dataclass): `rank_by: str | None = None`, `order: str = "desc"`, `outlier: Any = None`. Add `_kw_*` functions mirroring `_kw_limit`/`_kw_display`:

```python
def _kw_rank_by(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.expect(TokenType.COLON)
    state.rank_by = parser.expect_identifier_or_keyword().value


def _kw_order(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.expect(TokenType.COLON)
    val = parser.expect_identifier_or_keyword().value
    if val not in ("asc", "desc"):
        raise make_parse_error(f"order must be asc|desc, got {val!r}", parser.file, ...)
    state.order = val


def _kw_outlier_method(parser: Any, state: _WorkspaceRegionState) -> None:
    parser.expect(TokenType.COLON)
    state.outlier = _parse_outlier_spec(parser)
```

`_parse_outlier_spec` reads the method ident then optional params:

```python
def _parse_outlier_spec(parser: Any) -> "ir.ComparisonOutlierSpec":
    method = parser.expect_identifier_or_keyword().value  # iqr|sigma|threshold|none
    sigma_k = threshold_low = threshold_high = None
    if method == "sigma" and parser.match(TokenType.COLON):
        parser.advance()
        sigma_k = float(parser.advance().value)
    elif method == "threshold":
        # threshold:low=<x>,high=<y> — parse key=value pairs after a ':'
        if parser.match(TokenType.COLON):
            parser.advance()
            while True:
                key = parser.expect_identifier_or_keyword().value  # low|high
                parser.expect(TokenType.EQUALS)
                num = float(parser.advance().value)
                if key == "low":
                    threshold_low = num
                elif key == "high":
                    threshold_high = num
                if parser.match(TokenType.COMMA):
                    parser.advance()
                    continue
                break
    return ir.ComparisonOutlierSpec(
        method=method, sigma_k=sigma_k, threshold_low=threshold_low, threshold_high=threshold_high
    )
```

Register the keywords in `_WORKSPACE_REGION_KEYWORDS` (token-keyed) or `_WORKSPACE_REGION_IDENT_KEYWORDS` (ident-text-keyed) — match how `limit`/`sort` are registered (read lines ~3560–3580 for the registry). `rank_by`/`order`/`outlier_method` are likely IDENT keywords (no dedicated tokens). Wire `state.rank_by/order/outlier` into the `WorkspaceRegion(...)` construction in `_build_region`.

- [ ] **Step 4:** run → PASS. Then `uv run pytest tests/unit/test_parser.py tests/parser_corpus/ -q` → no regression.
- [ ] **Step 5:** ruff + mypy clean.
- [ ] **Step 6: commit** `feat(#1470): parse comparison rank_by/order/outlier_method`.

---

## Task 3: `flag_outliers` pure function

**Files:**
- Create: `src/dazzle/render/fragment/outliers.py`
- Test: `tests/unit/render/fragment/test_flag_outliers.py`

**Interfaces — Produces:** `flag_outliers(values: list[float | None], spec: ComparisonOutlierSpec) -> list[Literal["low","high"] | None]` (one entry per input, aligned by index).

- [ ] **Step 1: failing test**

```python
# tests/unit/render/fragment/test_flag_outliers.py
from dazzle.core.ir.workspaces import ComparisonOutlierSpec
from dazzle.render.fragment.outliers import flag_outliers


def test_iqr_flags_low_and_high() -> None:
    vals = [10, 11, 12, 13, 14, 100, -50]  # 100 high, -50 low vs the pack
    out = flag_outliers(vals, ComparisonOutlierSpec(method="iqr"))
    assert out[5] == "high"
    assert out[6] == "low"
    assert out[0] is None


def test_iqr_small_n_no_flags() -> None:
    assert flag_outliers([1, 99, 2], ComparisonOutlierSpec(method="iqr")) == [None, None, None]


def test_all_equal_no_flags() -> None:
    assert flag_outliers([5, 5, 5, 5, 5], ComparisonOutlierSpec(method="iqr")) == [None] * 5


def test_sigma() -> None:
    out = flag_outliers([10, 10, 10, 10, 200], ComparisonOutlierSpec(method="sigma", sigma_k=2.0))
    assert out[4] == "high"


def test_threshold_low_high() -> None:
    spec = ComparisonOutlierSpec(method="threshold", threshold_low=90.0, threshold_high=120.0)
    assert flag_outliers([85, 100, 130], spec) == ["low", None, "high"]


def test_threshold_applies_at_small_n() -> None:
    spec = ComparisonOutlierSpec(method="threshold", threshold_low=90.0)
    assert flag_outliers([85, 100], spec) == ["low", None]


def test_none_excluded_and_not_flagged() -> None:
    out = flag_outliers([10, 11, 12, 13, None, 100], ComparisonOutlierSpec(method="iqr"))
    assert out[4] is None  # None never flagged
    assert out[5] == "high"


def test_method_none() -> None:
    assert flag_outliers([1, 2, 3, 4, 99], ComparisonOutlierSpec(method="none")) == [None] * 5
```

- [ ] **Step 2:** run → FAIL (module missing).
- [ ] **Step 3: implement**

```python
# src/dazzle/render/fragment/outliers.py
"""Pure statistical outlier flagging for display: comparison (#1470)."""

import statistics
from typing import Literal

from dazzle.core.ir.workspaces import ComparisonOutlierSpec

Flag = Literal["low", "high"]


def flag_outliers(
    values: list[float | None], spec: ComparisonOutlierSpec
) -> list[Flag | None]:
    """Return a per-row flag aligned to ``values`` (``None`` where not flagged).

    ``iqr``/``sigma`` skip flagging below 4 numeric values (small-N guard) and
    when the spread is zero (all-equal). ``threshold`` applies at any N. ``None``
    values are excluded from the distribution and never flagged.
    """
    out: list[Flag | None] = [None] * len(values)
    if spec.method == "none":
        return out

    if spec.method == "threshold":
        low, high = spec.threshold_low, spec.threshold_high
        for i, v in enumerate(values):
            if v is None:
                continue
            if low is not None and v < low:
                out[i] = "low"
            elif high is not None and v > high:
                out[i] = "high"
        return out

    nums = [float(v) for v in values if v is not None]
    if len(nums) < 4:
        return out

    if spec.method == "iqr":
        q1, _q2, q3 = statistics.quantiles(nums, n=4)  # exclusive method (default)
        iqr = q3 - q1
        if iqr == 0:
            return out
        low_fence, high_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        for i, v in enumerate(values):
            if v is None:
                continue
            if v < low_fence:
                out[i] = "low"
            elif v > high_fence:
                out[i] = "high"
        return out

    if spec.method == "sigma":
        k = spec.sigma_k or 2.0
        mean = statistics.fmean(nums)
        sd = statistics.pstdev(nums)
        if sd == 0:
            return out
        for i, v in enumerate(values):
            if v is None:
                continue
            if v < mean - k * sd:
                out[i] = "low"
            elif v > mean + k * sd:
                out[i] = "high"
        return out

    return out
```

- [ ] **Step 4:** run → PASS (8 cases). If the IQR fence test is borderline, adjust the test vector — the asserted behaviour (100 high, −50 low) holds for `statistics.quantiles` exclusive on `[10..14,100,-50]`; verify and pin the exact vector.
- [ ] **Step 5:** ruff + mypy clean. (`render/` importing `core.ir` is allowed — core is the bottom layer.)
- [ ] **Step 6: commit** `feat(#1470): flag_outliers pure function (iqr/sigma/threshold)`.

---

## Task 4: Validation — `E_COMPARISON_*`

**Files:**
- Modify: the region validator (find: `grep -rln "WorkspaceRegion\|region.display\|DisplayMode" src/dazzle/core/validation/*.py`; likely `graphs.py` or a workspace validator — confirm)
- Test: `tests/unit/test_comparison_validation.py`

**Interfaces — Consumes:** the region IR (Task 1). **Produces:** validation errors for comparison regions.

Rules: a `display: comparison` region (1) requires `rank_by`; (2) if `group_by` set → `rank_by` must be a key in `aggregates`; (3) if no `group_by` → `rank_by` must name a field on `source` whose type is numeric (`int/decimal/float/money`); (4) `order ∈ {asc,desc}` (parser already guards, but validate defensively); (5) outlier params well-formed (`sigma` needs `sigma_k>0`; `threshold` needs at least one of low/high).

- [ ] **Step 1: failing test** — assert a comparison region missing `rank_by` yields `E_COMPARISON_RANK_BY_REQUIRED`; group-mode `rank_by` not in `aggregates` yields `E_COMPARISON_RANK_BY_UNKNOWN`; entity-row `rank_by` on a non-numeric field yields `E_COMPARISON_METRIC_NOT_NUMERIC`. (Build the AppSpec the way the other validation tests do — see how `tests/unit/test_format_validation.py` / existing region-validation tests construct input; if a full AppSpec is needed, extract a pure helper `_validate_comparison_region(region, entity, errors)` and unit-test it directly with stub IR, mirroring `_format_kind_error`.)
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement** the rule set in the region validator, emitting `E_COMPARISON_*` strings (follow the existing `E_`/error-append convention in that file).
- [ ] **Step 4:** run → PASS; `cd examples/* && uv run dazzle validate` for a couple examples → no false positives.
- [ ] **Step 5:** ruff + mypy clean; `uv run pytest -m gate -q` (a new E_-code may need registration in the error-code list — follow the pattern).
- [ ] **Step 6: commit** `feat(#1470): validate display: comparison (E_COMPARISON_*)`.

---

## Task 5: Orchestration — compute comparison rows into `ctx`

**Files:**
- Modify: `src/dazzle/http/runtime/workspace_aggregation.py` (+ `workspace_region_orchestration.py` where display→ctx is dispatched)
- Test: `tests/unit/test_comparison_orchestration.py`

**Interfaces — Consumes:** `flag_outliers` (Task 3). **Produces:** `ctx["comparison_rows"] = [{"rank": int, "label": str, "value": float|None, "bar_fraction": float, "columns": dict, "outlier": "low"|"high"|None}]` and `ctx["comparison_max"]: float`.

**Read first:** how `bar_track` builds its `ctx` rows from aggregate buckets (`grep -rn "bar_track_rows" src/dazzle/http/runtime/`) — mirror that for the group path. Group mode: the buckets are already produced via `agg_repo.aggregate(...)` (workspace_aggregation.py:302+). Entity-row mode: rows come from the scope-safe list read (`gated_list`).

- [ ] **Step 1: failing test** — extract a pure row-builder `build_comparison_rows(records, *, label_key, value_key, order, outlier_spec, extra_keys) -> tuple[list[dict], float]` and test it with stub records: assert sort order (desc/asc), rank numbering 1..N, `bar_fraction = value/max`, and `outlier` populated from `flag_outliers`. This keeps the orchestration logic pure + unit-testable without a DB.

```python
# sketch
rows, mx = build_comparison_rows(
    [{"region": "A", "total": 10}, {"region": "B", "total": 100}, {"region": "C", "total": 95},
     {"region": "D", "total": 92}, {"region": "E", "total": 5}],
    label_key="region", value_key="total", order="desc",
    outlier_spec=ComparisonOutlierSpec(method="iqr"), extra_keys=[],
)
assert [r["rank"] for r in rows] == [1, 2, 3, 4, 5]
assert rows[0]["label"] == "B" and rows[0]["value"] == 100
assert rows[0]["bar_fraction"] == 1.0
assert rows[-1]["outlier"] == "low"  # 5 is the low outlier
```

- [ ] **Step 2–4:** implement `build_comparison_rows` (pure) in `workspace_aggregation.py`; wire both modes to call it (group: over aggregate buckets keyed by `rank_by`; entity-row: over list records keyed by the `rank_by` field, with `extra_keys` from `fields`), and set `ctx["comparison_rows"]`/`ctx["comparison_max"]` when `display == COMPARISON`. Run the pure test → PASS.
- [ ] **Step 5:** ruff + mypy clean.
- [ ] **Step 6: commit** `feat(#1470): comparison orchestration (rank + flag → ctx rows)`.

---

## Task 6: Render — `_build_comparison`

**Files:**
- Modify: `src/dazzle/render/fragment/region/_builders_charts.py` (`_build_comparison`)
- Modify: `src/dazzle/render/fragment/region/_dispatcher.py` (`"comparison": "_build_comparison"`)
- Test: `tests/unit/render/fragment/test_build_comparison.py`

**Interfaces — Consumes:** `ctx["comparison_rows"]`/`ctx["comparison_max"]` (Task 5), the format layer (`format_cell`), `_cell_value` ref-display, `bar_track`'s track cell.

- [ ] **Step 1: failing test** — build a `RegionContext`/ctx stub with two `comparison_rows` (one flagged `low`) and assert the rendered `Surface`/HTML contains: a rank column with `1`/`2`, the labels, the formatted metric values, an outlier badge (`⚠`/`low`) on the flagged row, and an inline track element. (Mirror `tests/unit/test_region_adapter.py` / an existing `_build_*` test for the harness.)
- [ ] **Step 2:** run → FAIL (`_build_comparison` missing / dispatcher entry missing).
- [ ] **Step 3: implement** `_build_comparison` mirroring `_build_bar_track` (rows → labelled track) but emitting a `Table` with: rank col, label (via `_cell_value` for ref-display), the metric cell (track + `format_cell`-formatted value), `columns` cells (format-layer), and a badge cell when `outlier` is set. Register the dispatcher entry.
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5:** ruff + mypy clean; `uv run pytest -m gate -q` (complexity ratchet — if `_build_comparison` exceeds CC 15, extract a row-cell helper).
- [ ] **Step 6: commit** `feat(#1470): _build_comparison ranked-table render`.

---

## Task 7: Example + full-suite + ship

**Files:**
- Modify: one example app's workspace (e.g. `examples/ops_dashboard` — it already has `bar_chart`/`pivot_table`) — add a `display: comparison` group-mode region.
- Modify: `CHANGELOG.md`, version files (`/bump`), `docs/api-surface/ir-types.txt` (already regen'd Task 1), golden-master snapshot.
- Test: the example's `dazzle validate` + the full suite.

- [ ] **Step 1:** add a `display: comparison` region to the example (group_by an FK + an aggregate + `rank_by` + `outlier_method: iqr`); `cd examples/<app> && uv run dazzle validate` → exit 0.
- [ ] **Step 2: regen golden-master** (new DisplayMode / IR fields drift it if the simple_test fixture touches regions; regen regardless to be safe): `uv run pytest tests/integration/test_golden_master.py --snapshot-update -q` then re-run to confirm PASS. Inspect the diff is comparison-related only.
- [ ] **Step 3: full suite** — `uv run pytest tests/ -m "not e2e" -q`. Expect only the 3 pre-existing `test_fuzzer_oracle` pollution failures. Fix anything else.
- [ ] **Step 4:** `uv run ruff check src/ tests/ && uv run mypy src/dazzle` clean.
- [ ] **Step 5:** `/bump patch`; CHANGELOG entry under `### Added` (the `display: comparison` primitive — modes, outlier methods, render) + `### Agent Guidance` (when to use comparison vs bar_chart; the within-scope-ranking semantic; the outlier methods) + an api-surface drift note under `### Changed`.
- [ ] **Step 6: commit + tag + push**, then watch CI to green (`gh run watch`). The walks render the example region for the first time — confirm they pass.

---

## Self-review

- **Spec coverage:** modes/grammar → Tasks 1–2; outlier methods + compute + edges → Task 3; validation → Task 4; orchestration (both modes, within-scope) → Task 5; render (table + inline bar + format layer + ref-display + badge) → Task 6; example + testing + baselines → Task 7. All spec sections covered.
- **Type consistency:** `ComparisonOutlierSpec(method, sigma_k, threshold_low, threshold_high)` (Task 1) used unchanged in Tasks 2/3/5; `flag_outliers(values, spec) -> list["low"|"high"|None]` (Task 3) consumed in Task 5; `comparison_rows`/`comparison_max` ctx keys (Task 5) consumed in Task 6.
- **Known unknowns flagged read-first (not fabricated):** the region keyword-registry shape (Task 2), the region validator file (Task 4), the `bar_track` orchestration to mirror (Task 5), and the `_build_*`/RegionContext test harness (Task 6). Each task says where to look + the contract.
- **Placeholder scan:** `flag_outliers` test vector noted as verify-and-pin (Step 4 Task 3) — that's a calibration note, not a missing step.

## Notes

- Spec said "reuse box_plot's quartile helper" — corrected: `box_plot` *receives* pre-computed quartiles, so `flag_outliers` computes its own via stdlib `statistics.quantiles` (Task 3).
- Two baselines drift (golden-master, api-surface ir-types) — regenerate both (Tasks 1 + 7), each with a CHANGELOG note.
