# Deterministic `insight_summary` Implementation Plan (#1470, Slice 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `display: insight_summary` — a region that computes a grouped aggregate and renders a deterministic, grounded narrative (scale + leader + outlier) above a trust block (underlying values + scope + "Computed" badge). No LLM.

**Architecture:** Reuse the `bar_chart` aggregation spine (`_compute_bucketed_aggregates`) and the shipped `flag_outliers`. A pure NLG function turns the buckets into narrative lines + citations; a new render builder emits a trust card. Mirrors the `comparison`/`outlier_on` wiring exactly. Layers `http → page → render → core`.

**Tech Stack:** Python 3.12, Pydantic IR, pytest. Reuses `flag_outliers`, `ComparisonOutlierSpec`, `_compute_bucketed_aggregates`, the `Text`/`Stack` fragment primitives, and the comparison slice's registration pattern.

## Global Constraints

- `ruff check src/ tests/` + `ruff format` clean; bare `mypy src/dazzle` clean (matches CI).
- **Run the full `pytest -m "not e2e"` before shipping** — golden-master + walk + docs-drift jobs live outside the gate subset. The 3 `test_fuzzer_oracle` failures are pre-existing pollution (pass isolated) — ignore.
- The new `DisplayMode.INSIGHT_SUMMARY` **drifts two baselines** — regenerate both at ship time: golden-master (`pytest tests/integration/test_golden_master.py --snapshot-update`) and api-surface ir-types (`dazzle inspect api ir-types --write`). Each needs a CHANGELOG note. Parser-corpus snapshot drifts only if a corpus region serializes nothing new (it won't — no new field), so likely no corpus regen.
- Within-scope: the narrative is computed AFTER the scoped aggregate fetch — never widens scope.
- Complexity ratchet: new functions ≤ CC 15; extract helpers if exceeded; regenerate the MI baseline with `dazzle fitness code --write-baseline` only if a file's rank legitimately drops (note why).
- The catalogue fidelity test (`tests/unit/test_ux_catalogue.py`) will gain a 9th mode — keep it green.

## File structure

- `src/dazzle/core/ir/workspaces.py` — `DisplayMode.INSIGHT_SUMMARY`.
- `src/dazzle/core/validation/ux.py` — `validate_insight_summaries` + `E_INSIGHT_*`.
- `src/dazzle/core/lint.py`, `validator.py`, `validation/__init__.py` — register the validator.
- `src/dazzle/render/fragment/insight.py` (new) — `InsightNarrative` + `build_insight_narrative` (pure NLG).
- `src/dazzle/http/runtime/workspace_region_computes.py` — `build_insight_inputs`.
- `src/dazzle/http/runtime/workspace_region_orchestration.py` — `_SINGLE_DIM_CHART_MODES` + compute branch.
- `src/dazzle/http/runtime/workspace_region_render.py` — `RegionRenderInputs.insight_narrative` + chart adapter-ctx key.
- `src/dazzle/render/fragment/region/_context.py` — RegionContext TypedDict key.
- `src/dazzle/render/fragment/region/_builders_charts.py` — `_build_insight_summary`.
- `src/dazzle/render/fragment/region/_dispatcher.py` + `coverage.py` — register the mode.
- `examples/ops_dashboard/dsl/app.dsl`, `fixtures/component_showcase/dsl/app.dsl`, `src/dazzle/testing/ux_catalogue_manifest.py` — dogfood.

---

## Task 1: IR — `DisplayMode.INSIGHT_SUMMARY`

**Files:**
- Modify: `src/dazzle/core/ir/workspaces.py`
- Test: `tests/unit/test_insight_summary_ir.py`

**Interfaces — Produces:** `DisplayMode.INSIGHT_SUMMARY = "insight_summary"`. No new `WorkspaceRegion` fields (reuses `source`/`group_by`/`aggregates`).

- [ ] **Step 1: failing test**

```python
# tests/unit/test_insight_summary_ir.py
from dazzle.core.ir.workspaces import DisplayMode


def test_insight_summary_display_mode() -> None:
    assert DisplayMode.INSIGHT_SUMMARY.value == "insight_summary"
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_insight_summary_ir.py -q` → FAIL.

- [ ] **Step 3: implement.** In `workspaces.py` `DisplayMode`, next to `COMPARISON = "comparison"  # #1470: ...`:

```python
    INSIGHT_SUMMARY = "insight_summary"  # #1470: deterministic grounded narrative
```

- [ ] **Step 4:** `uv run pytest tests/unit/test_insight_summary_ir.py -q` → PASS.

- [ ] **Step 5:** `uv run mypy src/dazzle` clean; `uv run ruff check src/ tests/ --fix && uv run ruff format src/ tests/`.

- [ ] **Step 6: regen api-surface ir-types baseline:** `uv run dazzle inspect api ir-types --write` then `uv run pytest tests/unit/test_api_surface_drift.py -q` → PASS. Confirm the only diff is the new `insight_summary` enum member.

- [ ] **Step 7: commit**

```bash
git add src/dazzle/core/ir/workspaces.py docs/api-surface/ir-types.txt tests/unit/test_insight_summary_ir.py
git commit -m "feat(#1470): IR for display: insight_summary (DisplayMode member)"
```

---

## Task 2: Validation — `E_INSIGHT_*`

**Files:**
- Modify: `src/dazzle/core/validation/ux.py`
- Modify: `src/dazzle/core/validation/__init__.py`, `src/dazzle/core/validator.py`, `src/dazzle/core/lint.py`
- Test: `tests/unit/test_insight_summary_validation.py`

**Interfaces — Produces:** `validate_insight_summaries(appspec) -> tuple[list[str], list[str]]`.

Rules: `display: insight_summary` requires (1) `group_by` (`E_INSIGHT_GROUP_BY_REQUIRED`); (2) at least one `aggregate` (`E_INSIGHT_AGGREGATE_REQUIRED`); (3) single-dim only — a list `group_by` is rejected (`E_INSIGHT_SINGLE_DIM_ONLY`).

- [ ] **Step 1: failing test**

```python
# tests/unit/test_insight_summary_validation.py
from __future__ import annotations

from pathlib import Path

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.validator import validate_insight_summaries

_HEADER = """module t
app T "T"

entity Alert "Alert":
  id: uuid pk
  team: str(40)

workspace w "W":
"""


def _appspec(region_dsl: str, tmp_path: Path):
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "app.dsl").write_text(_HEADER + region_dsl)
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "t"\nversion = "0.1.0"\nroot = "t"\n[modules]\npaths = ["./dsl"]\n'
    )
    modules = parse_modules([dsl_dir / "app.dsl"])
    return build_appspec(modules, "t")


def test_requires_group_by(tmp_path: Path) -> None:
    dsl = """  ins:
    source: Alert
    display: insight_summary
    aggregate:
      count: count(Alert)
"""
    errors, _ = validate_insight_summaries(_appspec(dsl, tmp_path))
    assert any("E_INSIGHT_GROUP_BY_REQUIRED" in e for e in errors)


def test_requires_aggregate(tmp_path: Path) -> None:
    dsl = """  ins:
    source: Alert
    display: insight_summary
    group_by: team
"""
    errors, _ = validate_insight_summaries(_appspec(dsl, tmp_path))
    assert any("E_INSIGHT_AGGREGATE_REQUIRED" in e for e in errors)


def test_rejects_multi_dim(tmp_path: Path) -> None:
    dsl = """  ins:
    source: Alert
    display: insight_summary
    group_by: [team, team]
    aggregate:
      count: count(Alert)
"""
    errors, _ = validate_insight_summaries(_appspec(dsl, tmp_path))
    assert any("E_INSIGHT_SINGLE_DIM_ONLY" in e for e in errors)


def test_valid(tmp_path: Path) -> None:
    dsl = """  ins:
    source: Alert
    display: insight_summary
    group_by: team
    aggregate:
      count: count(Alert)
"""
    errors, _ = validate_insight_summaries(_appspec(dsl, tmp_path))
    assert errors == []
```

- [ ] **Step 2:** run → FAIL (import error).

- [ ] **Step 3: implement.** In `ux.py`, after `validate_outlier_decorators`, add:

```python
def validate_insight_summaries(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate `display: insight_summary` regions (#1470 Slice 1)."""
    errors: list[str] = []
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if region.display != ir.DisplayMode.INSIGHT_SUMMARY:
                continue
            label = f"Workspace '{workspace.name}' region '{region.name or region.source}'"
            if region.group_by_dims:
                errors.append(
                    f"E_INSIGHT_SINGLE_DIM_ONLY: {label} `display: insight_summary` supports a "
                    f"single `group_by` only (got a multi-dimension list)."
                )
            elif region.group_by is None:
                errors.append(
                    f"E_INSIGHT_GROUP_BY_REQUIRED: {label} `display: insight_summary` requires "
                    f"a `group_by`."
                )
            if not region.aggregates:
                errors.append(
                    f"E_INSIGHT_AGGREGATE_REQUIRED: {label} `display: insight_summary` requires "
                    f"at least one `aggregate`."
                )
    return errors, []
```

(Confirm `region.group_by_dims` is the multi-dim field — `grep -n "group_by_dims" src/dazzle/core/ir/workspaces.py`. The parser sets it for `group_by: [a, b]`. If the single `group_by: team` form parses into `group_by` as a `str`, the `group_by_dims` check stays correct.)

- [ ] **Step 4: register the validator** (mirror `validate_comparison_regions` exactly):
  - `src/dazzle/core/validation/__init__.py`: add `validate_insight_summaries` to the `from .ux import (...)` block + `__all__`.
  - `src/dazzle/core/validator.py`: add to the `from .validation import (...)` block + `__all__`.
  - `src/dazzle/core/lint.py`: add to the `from .validator import (...)` block, then a call site after the outlier one:

```python
    # insight_summary deterministic-narrative validation (#1470)
    errors, warnings = validate_insight_summaries(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)
```

- [ ] **Step 5:** run → PASS. Spot-check examples: `cd examples/ops_dashboard && uv run dazzle validate` exit 0; `cd ../simple_task && uv run dazzle validate` exit 0.

- [ ] **Step 6:** ruff + mypy clean; `uv run pytest -m gate -q` (complexity).

- [ ] **Step 7: commit**

```bash
git add src/dazzle/core/validation/ux.py src/dazzle/core/validation/__init__.py src/dazzle/core/validator.py src/dazzle/core/lint.py tests/unit/test_insight_summary_validation.py
git commit -m "feat(#1470): validate display: insight_summary (E_INSIGHT_*)"
```

---

## Task 3: Pure NLG — `build_insight_narrative`

**Files:**
- Create: `src/dazzle/render/fragment/insight.py`
- Test: `tests/unit/render/fragment/test_insight_narrative.py`

**Interfaces — Produces:**
- `InsightNarrative` (frozen dataclass): `lines: tuple[str, ...]`, `citations: tuple[tuple[str, float], ...]`, `scope: str`, `badge: str`.
- `build_insight_narrative(buckets, *, measure_name, measure_func, group_label, scope_desc, outlier_spec) -> InsightNarrative`.

- [ ] **Step 1: failing test**

```python
# tests/unit/render/fragment/test_insight_narrative.py
from dazzle.core.ir.workspaces import ComparisonOutlierSpec
from dazzle.render.fragment.insight import InsightNarrative, build_insight_narrative

_SPEC = ComparisonOutlierSpec(method="iqr")


def _n(buckets, func="count"):
    return build_insight_narrative(
        buckets,
        measure_name="alerts",
        measure_func=func,
        group_label="teams",
        scope_desc="across all teams",
        outlier_spec=_SPEC,
    )


def test_additive_scale_leader_outlier() -> None:
    buckets = [
        {"label": "Platform", "value": 12},
        {"label": "Payments", "value": 11},
        {"label": "Growth", "value": 10},
        {"label": "Data", "value": 9},
        {"label": "Infra", "value": 9},
        {"label": "ML", "value": 1},
    ]
    n = _n(buckets)
    joined = " ".join(n.lines)
    assert "52 alerts across 6 teams" in joined  # total = sum
    assert "Platform leads at 12" in joined and "%" in joined  # additive → pct
    assert "anomalously low" in joined and "ML" in joined  # 1 is the low outlier
    assert ("Platform", 12.0) in n.citations
    assert n.scope == "across all teams"
    assert n.badge


def test_non_additive_skips_total_and_pct() -> None:
    buckets = [{"label": "A", "value": 40}, {"label": "B", "value": 50}, {"label": "C", "value": 45}]
    n = _n(buckets, func="avg")
    joined = " ".join(n.lines)
    assert "across 3 teams" in joined
    assert "%" not in joined  # non-additive → no percentage
    assert "B leads at 50" in joined


def test_flat_data_no_outlier_line() -> None:
    buckets = [{"label": x, "value": 5} for x in "ABCDE"]
    n = _n(buckets)
    assert not any("anomal" in line for line in n.lines)


def test_empty_buckets() -> None:
    n = _n([])
    assert n.lines == ("No data to summarise.",)
    assert n.citations == ()


def test_one_group_scale_and_leader_only() -> None:
    n = _n([{"label": "Solo", "value": 7}])
    joined = " ".join(n.lines)
    assert "7 alerts across 1 teams" in joined
    assert "Solo leads at 7" in joined
    assert not any("anomal" in line for line in n.lines)
```

- [ ] **Step 2:** run → FAIL (module missing).

- [ ] **Step 3: implement** `src/dazzle/render/fragment/insight.py`:

```python
"""Pure deterministic NLG for display: insight_summary (#1470 Slice 1)."""

import math
from dataclasses import dataclass

from dazzle.core.ir.workspaces import ComparisonOutlierSpec
from dazzle.render.fragment.outliers import flag_outliers

_ADDITIVE = {"count", "sum"}


@dataclass(frozen=True, slots=True)
class InsightNarrative:
    """Deterministic narrative + its grounding (the cited values)."""

    lines: tuple[str, ...]
    citations: tuple[tuple[str, float], ...]
    scope: str
    badge: str = "Computed from live data"


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else f"{v:.2f}"


def _num(value: object) -> float | None:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def build_insight_narrative(
    buckets: list[dict],
    *,
    measure_name: str,
    measure_func: str,
    group_label: str,
    scope_desc: str,
    outlier_spec: ComparisonOutlierSpec,
) -> InsightNarrative:
    """Build a grounded narrative (scale + leader + outlier) from grouped buckets.

    ``buckets`` are ``[{"label", "value"}, ...]``. Additive measures (count/sum)
    get a total + "% of total"; non-additive (avg/min/max) skip them. The outlier
    line reuses the shipped ``flag_outliers``. Every claim cites an exact value.
    """
    pairs = [(str(b.get("label") or ""), _num(b.get("value"))) for b in buckets]
    pairs = [(lbl, v) for lbl, v in pairs if v is not None]
    if not pairs:
        return InsightNarrative(("No data to summarise.",), (), scope_desc)

    citations = tuple(pairs)
    n = len(pairs)
    additive = measure_func in _ADDITIVE
    lines: list[str] = []

    total = sum(v for _lbl, v in pairs)
    if additive:
        lines.append(f"{_fmt(total)} {measure_name} across {n} {group_label}.")
    else:
        lines.append(f"{measure_name} across {n} {group_label}.")

    leader_lbl, leader_val = max(pairs, key=lambda p: p[1])
    if additive and total > 0:
        pct = round(leader_val / total * 100)
        lines.append(f"{leader_lbl} leads at {_fmt(leader_val)} ({pct}% of the total).")
    else:
        lines.append(f"{leader_lbl} leads at {_fmt(leader_val)}.")

    flags = flag_outliers([v for _lbl, v in pairs], outlier_spec)
    for (lbl, v), flag in zip(pairs, flags, strict=True):
        if flag in ("low", "high"):
            lines.append(f"{lbl} is anomalously {flag} at {_fmt(v)}.")
            break

    return InsightNarrative(tuple(lines), citations, scope_desc)
```

- [ ] **Step 4:** run → PASS (5 cases). The outlier vector `[12,11,10,9,9,1]` flags 1 as low (verify against the comparison slice's calibration; if borderline, widen the gap, e.g. ML=1 vs a tighter pack).

- [ ] **Step 5:** ruff + mypy clean; complexity (if `build_insight_narrative` > CC 15, extract the scale/leader/outlier blocks into helpers).

- [ ] **Step 6: commit**

```bash
git add src/dazzle/render/fragment/insight.py tests/unit/render/fragment/test_insight_narrative.py
git commit -m "feat(#1470): build_insight_narrative pure NLG (scale + leader + outlier)"
```

---

## Task 4: Orchestration — `build_insight_inputs` + ctx wiring

**Files:**
- Modify: `src/dazzle/http/runtime/workspace_region_computes.py` (`build_insight_inputs`)
- Modify: `src/dazzle/http/runtime/workspace_region_orchestration.py` (`_SINGLE_DIM_CHART_MODES` + compute branch)
- Modify: `src/dazzle/http/runtime/workspace_region_render.py` (`RegionRenderInputs.insight_narrative` + chart adapter ctx)
- Modify: `src/dazzle/render/fragment/region/_context.py` (TypedDict key)
- Test: `tests/unit/test_insight_summary_orchestration.py`

**Interfaces — Consumes:** `build_insight_narrative` (Task 3). **Produces:** `build_insight_inputs(bucketed_metrics, *, region, group_label, scope_desc, outlier_spec) -> InsightNarrative`; ctx key `insight_narrative`.

- [ ] **Step 1: failing test**

```python
# tests/unit/test_insight_summary_orchestration.py
from dazzle.core.ir.workspaces import ComparisonOutlierSpec, WorkspaceRegion, DisplayMode
from dazzle.core.ir import AggregateRef
from dazzle.http.runtime.workspace_region_computes import build_insight_inputs


def test_build_insight_inputs_picks_first_aggregate() -> None:
    region = WorkspaceRegion(
        name="ins",
        display=DisplayMode.INSIGHT_SUMMARY,
        group_by="team",
        aggregates={"count": AggregateRef(func="count", entity="Alert")},
    )
    buckets = [
        {"label": "Platform", "value": 12, "metrics": {"count": 12}},
        {"label": "ML", "value": 1, "metrics": {"count": 1}},
    ]
    nar = build_insight_inputs(
        buckets,
        region=region,
        group_label="teams",
        scope_desc="across all teams",
        outlier_spec=ComparisonOutlierSpec(method="iqr"),
    )
    assert nar.lines and "across 2 teams" in " ".join(nar.lines)
    assert ("Platform", 12.0) in nar.citations
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3: implement `build_insight_inputs`.** In `workspace_region_computes.py`, after `build_outlier_flags`, add (the file already imports `build_insight_narrative`'s deps; add `from dazzle.render.fragment.insight import InsightNarrative, build_insight_narrative`):

```python
def build_insight_inputs(
    bucketed_metrics: list[dict[str, Any]],
    *,
    region: Any,
    group_label: str,
    scope_desc: str,
    outlier_spec: ComparisonOutlierSpec,
) -> InsightNarrative:
    """Select the narrated measure (first aggregate) and build the narrative (#1470)."""
    aggregates = getattr(region, "aggregates", None) or {}
    measure_name, ref = next(iter(aggregates.items()), ("value", None))
    measure_func = getattr(ref, "func", "count") or "count"
    records = [
        {"label": b.get("label"), "value": (b.get("metrics") or {}).get(measure_name, b.get("value"))}
        for b in bucketed_metrics
    ]
    return build_insight_narrative(
        records,
        measure_name=measure_name,
        measure_func=measure_func,
        group_label=group_label,
        scope_desc=scope_desc,
        outlier_spec=outlier_spec,
    )
```

- [ ] **Step 4:** run → PASS.

- [ ] **Step 5: thread through orchestration.** In `workspace_region_orchestration.py`:
  - Add `"INSIGHT_SUMMARY"` to the `_SINGLE_DIM_CHART_MODES` frozenset (so `bucketed_metrics` is computed for it, like `COMPARISON`).
  - Add `build_insight_inputs` to the `from ...workspace_region_computes import (...)` block.
  - After the `display == "COMPARISON"` compute block, add:

```python
    # Insight summary (#1470): deterministic narrative over the grouped aggregate.
    if display == "INSIGHT_SUMMARY" and group_by and bucketed_metrics:
        _gb = group_by if isinstance(group_by, str) else str(group_by)
        group_label = _gb.replace("_", " ")
        scope_desc = f"across all {group_label}"
        if getattr(ctx.ir_region, "filter", None) is not None:
            scope_desc += " (filtered)"
        insight_narrative = build_insight_inputs(
            bucketed_metrics,
            region=ctx.ir_region,
            group_label=group_label,
            scope_desc=scope_desc,
            outlier_spec=getattr(ctx.ir_region, "outlier", None) or ComparisonOutlierSpec(),
        )
    else:
        insight_narrative = None
```

  - Add to the `RegionRenderInputs(...)` construction:

```python
        insight_narrative=insight_narrative,
```

- [ ] **Step 6: RegionRenderInputs + adapter ctx.** In `workspace_region_render.py`:
  - Add a field to `RegionRenderInputs` next to `comparison_rows`:

```python
    # #1470 insight_summary — the deterministic narrative (or None).
    insight_narrative: Any = None
```

  - In `_build_chart_adapter_ctx`, after the `elif display_upper == "COMPARISON":` branch, add:

```python
    elif display_upper == "INSIGHT_SUMMARY":
        adapter_ctx["insight_narrative"] = inputs.insight_narrative
```

  - Add `"INSIGHT_SUMMARY"` to the `_CHART_FAMILY` frozenset.

- [ ] **Step 7: RegionContext TypedDict.** In `_context.py`, next to the `comparison_*` keys:

```python
    # #1470 insight_summary — the deterministic narrative.
    insight_narrative: Any
```

- [ ] **Step 8:** `uv run pytest tests/unit/test_insight_summary_orchestration.py -q` → PASS; ruff + mypy clean.

- [ ] **Step 9: commit**

```bash
git add src/dazzle/http/runtime/workspace_region_computes.py src/dazzle/http/runtime/workspace_region_orchestration.py src/dazzle/http/runtime/workspace_region_render.py src/dazzle/render/fragment/region/_context.py tests/unit/test_insight_summary_orchestration.py
git commit -m "feat(#1470): insight_summary orchestration (narrative -> ctx)"
```

---

## Task 5: Render — `_build_insight_summary`

**Files:**
- Modify: `src/dazzle/render/fragment/region/_builders_charts.py` (`_build_insight_summary`)
- Modify: `src/dazzle/render/fragment/region/_dispatcher.py` (register)
- Modify: `src/dazzle/render/fragment/coverage.py` (`_SUPPORTED_DISPLAYS`)
- Test: `tests/unit/test_insight_summary_render.py`

**Interfaces — Consumes:** `ctx["insight_narrative"]` (Task 4), the `Text`/`Stack` primitives.

- [ ] **Step 1: failing test**

```python
# tests/unit/test_insight_summary_render.py
from dazzle.render.fragment.insight import InsightNarrative
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeRegion:
    def __init__(self) -> None:
        self.name = "ins"
        self.title = "Team Insight"
        self.display = "insight_summary"
        self.empty_message = None


def _render(ctx: dict) -> str:
    return FragmentRenderer().render(WorkspaceRegionAdapter().build(_FakeRegion(), ctx))


def test_renders_narrative_and_trust_block() -> None:
    nar = InsightNarrative(
        lines=("52 alerts across 6 teams.", "Platform leads at 12 (23% of the total)."),
        citations=(("Platform", 12.0), ("ML", 1.0)),
        scope="across all teams",
        badge="Computed from live data",
    )
    html = _render({"insight_narrative": nar})
    assert "Platform leads at 12" in html
    assert "across all teams" in html
    assert "Computed from live data" in html
    assert "Platform" in html and "12" in html  # citation values present


def test_empty_narrative_degrades() -> None:
    nar = InsightNarrative(lines=("No data to summarise.",), citations=(), scope="across all teams")
    html = _render({"insight_narrative": nar})
    assert "No data to summarise." in html


def test_html_escaping_of_labels() -> None:
    nar = InsightNarrative(
        lines=("<script>alert(1)</script> leads at 9.",),
        citations=(("<script>x</script>", 9.0),),
        scope="across all teams",
    )
    html = _render({"insight_narrative": nar})
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
```

- [ ] **Step 2:** run → FAIL (NotImplementedError — display not registered).

- [ ] **Step 3: implement.** In `_builders_charts.py`, ensure `Text` is imported in the `from dazzle.render.fragment import (...)` block (add it next to `Stack`/`EmptyState`); then add the method (place after `_build_comparison`):

```python
    def _build_insight_summary(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: insight_summary` renders a deterministic grounded narrative
        (scale + leader + outlier) above a trust block (the cited values + scope +
        a 'Computed' badge). All strings escaped at emit by the Text primitive. #1470.
        """
        title = _region_title(region)
        nar = ctx.get("insight_narrative")
        lines = tuple(getattr(nar, "lines", ()) or ())
        if not lines:
            body: Fragment = EmptyState(
                title="No insight",
                description=getattr(region, "empty_message", None) or "No data to summarise.",
            )
            return _wrap_surface(title, "report", body)

        children: list[Fragment] = [Text(body=str(line)) for line in lines]
        citations = getattr(nar, "citations", ()) or ()
        if citations:
            cite_str = " · ".join(f"{lbl} {_fmt_num(val)}" for lbl, val in citations)
            children.append(Text(body=f"Based on: {cite_str}", tone="muted"))
        footer = f"{getattr(nar, 'scope', '')} · {getattr(nar, 'badge', '')}".strip(" ·")
        children.append(Text(body=footer, tone="muted"))
        return _wrap_surface(title, "report", Stack(children=tuple(children), gap="sm"))
```

  Add a module-level helper near the top of the file (after the imports):

```python
def _fmt_num(v: object) -> str:
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f == int(f) else f"{f:.2f}"
```

- [ ] **Step 4: register.**
  - `_dispatcher.py` `_BUILDERS`: add `"insight_summary": "_build_insight_summary",  # #1470` next to the `"comparison"` entry.
  - `coverage.py` `_SUPPORTED_DISPLAYS`: add `"insight_summary",  # #1470` next to `"comparison"`.

- [ ] **Step 5:** run → PASS (3 cases). Then `uv run pytest tests/unit/render/fragment/test_coverage.py -q` → PASS (the supported-displays-match-adapter drift gate).

- [ ] **Step 6:** ruff + mypy clean; `uv run pytest -m gate -q` + `uv run pytest tests/unit/test_region_adapter.py tests/unit/test_htmx_workspace_composite.py -q` (complexity + card-safety + adapter).

- [ ] **Step 7: commit**

```bash
git add src/dazzle/render/fragment/region/_builders_charts.py src/dazzle/render/fragment/region/_dispatcher.py src/dazzle/render/fragment/coverage.py tests/unit/test_insight_summary_render.py
git commit -m "feat(#1470): _build_insight_summary trust-card render"
```

---

## Task 6: Example + catalogue + full suite + ship

**Files:**
- Modify: `examples/ops_dashboard/dsl/app.dsl`
- Modify: `fixtures/component_showcase/dsl/app.dsl`, `src/dazzle/testing/ux_catalogue_manifest.py`, `docs/reference/ux-catalogue.md`, `docs/assets/dazzle-catalogue.css` (regen)
- Modify: `CHANGELOG.md`, version files (`/bump`), golden-master snapshot

- [ ] **Step 1: ops_dashboard example.** Add an `insight_summary` region to `examples/ops_dashboard/dsl/app.dsl` (group an FK or enum + an aggregate), e.g.:

```dsl
  alert_insight:
    source: Alert
    display: insight_summary
    group_by: system
    aggregate:
      count: count(Alert)
```

  `cd examples/ops_dashboard && uv run dazzle validate` → exit 0.

- [ ] **Step 2: catalogue 9th mode.** Add `cat_insight` to the `ux_catalogue` workspace in `fixtures/component_showcase/dsl/app.dsl`:

```dsl
  cat_insight:
    source: Box
    display: insight_summary
    group_by: team
    aggregate:
      count: count(Box)
```

  Add a `cat_insight` entry to `CATALOGUE_MANIFEST` in `src/dazzle/testing/ux_catalogue_manifest.py` with a description + `canned_buckets` (a team distribution with one clear outlier, mirroring `cat_bar_chart` but with a low/high anomaly so the outlier line renders):

```python
    "cat_insight": {
        "description": "A grounded, deterministic narrative — scale + leader + outlier — over a grouped aggregate, with the underlying values cited. No LLM.",
        "sample_items": [],
        "canned_buckets": [
            {"dimensions": {"team": "platform", "team_label": "platform"}, "measures": {"count": 12}},
            {"dimensions": {"team": "payments", "team_label": "payments"}, "measures": {"count": 11}},
            {"dimensions": {"team": "growth", "team_label": "growth"}, "measures": {"count": 10}},
            {"dimensions": {"team": "data", "team_label": "data"}, "measures": {"count": 9}},
            {"dimensions": {"team": "infra", "team_label": "infra"}, "measures": {"count": 9}},
            {"dimensions": {"team": "ml", "team_label": "ml"}, "measures": {"count": 1}},
        ],
    },
```

  Add `("cat_insight", "dz-")` to the fidelity-test parametrize in `tests/unit/test_ux_catalogue.py` — first probe the real marker: run a quick render of `cat_insight` and grep the emitted class (the Stack/Text/`_wrap_surface` "report" wrapper), then pin the exact marker (e.g. `dz-region` / the surface wrapper class). Regenerate the page: `uv run python scripts/gen_ux_catalogue.py`. Run `uv run pytest tests/unit/test_ux_catalogue.py -q` → PASS (now 9 modes).

- [ ] **Step 3: regen golden-master:** `uv run pytest tests/integration/test_golden_master.py --snapshot-update -q`, re-run to confirm PASS; `git diff` shows only insight-related drift (the new enum doesn't add fields, so likely no change — regen regardless).

- [ ] **Step 4: full suite:** `uv run pytest tests/ -m "not e2e" -q`. Expect only the 3 `test_fuzzer_oracle` pollution failures (confirm isolated). Fix anything else (e.g. a new docs-drift if a reference page was added — not expected here).

- [ ] **Step 5:** `uv run ruff check src/ tests/ && uv run mypy src/dazzle` clean.

- [ ] **Step 6:** `/bump patch` (6 version lines + `uv lock`). CHANGELOG `### Added` (the deterministic `insight_summary` — grounded narrative + trust block, no LLM; Slice 1 of 3) + `### Agent Guidance` (when to use insight_summary; the deterministic-now / LLM-in-Slice-2 note; the measure-aware additive-vs-non-additive behaviour; the citation/trust-block contract) + the api-surface drift note under `### Changed`.

- [ ] **Step 7: commit + tag + push**, then watch CI + the docs deploy green (`gh run watch <ci-id> --exit-status`; confirm the `docs` workflow + Pages deploy succeed — the catalogue page now shows 9 modes). Keep `git status` clean (commit `uv.lock`).

---

## Self-review

- **Spec coverage:** DisplayMode (Task 1); validation rules (Task 2); pure measure-aware NLG with scale/leader/outlier + citations + edge cases (Task 3); orchestration reusing the bucket spine + ctx wiring (Task 4); trust-card render with escaping (Task 5); example + catalogue 9th mode + baselines + ship (Task 6). All spec sections covered. Parser correctly needs no task (free via the enum).
- **Type consistency:** `InsightNarrative{lines, citations, scope, badge}` (Task 3) is consumed unchanged by `build_insight_inputs` (Task 4) and `_build_insight_summary` (Task 5). `build_insight_narrative(buckets, *, measure_name, measure_func, group_label, scope_desc, outlier_spec)` signature is identical across Tasks 3/4. `ctx["insight_narrative"]` is the one ctx key across Tasks 4/5.
- **Placeholder scan:** the only verify-against-reality notes are the outlier test vector calibration (Task 3 Step 4, pinned from the comparison slice) and the catalogue marker probe (Task 6 Step 2) — both flagged with how to confirm, not left vague.
- **Reuse:** `flag_outliers`, `ComparisonOutlierSpec`, `_compute_bucketed_aggregates` (via `_SINGLE_DIM_CHART_MODES`), the comparison registration pattern (dispatcher/coverage/family/TypedDict/RegionRenderInputs), the `Text`/`Stack` primitives, and the catalogue harness — all reused; genuinely new code is `DisplayMode.INSIGHT_SUMMARY`, `validate_insight_summaries`, `build_insight_narrative`, `build_insight_inputs`, and `_build_insight_summary`.

## Notes

- No parser task: `display: insight_summary` parses through the existing enum dispatch once the `DisplayMode` member exists (confirmed pattern — `comparison` needed parser work only for its *new keywords* `rank_by`/`order`/`outlier_method`; insight_summary adds no keywords).
- The outlier line reuses `flag_outliers` directly, so its small-N (≥4) + zero-spread guards give the "no spurious anomaly on flat/tiny data" behaviour for free (Task 3 `test_flat_data_no_outlier_line` / `test_one_group_...`).
- Slice 2 (LLM prose + confidence) and Slice 3 (refresh/AIJob/clickable citations) are separate future specs — do not scope-creep them in here.
```
