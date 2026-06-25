# `outlier_on` Statistical Decorator Implementation Plan (#1470, slice 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `outlier_on:` — a region keyword that flags statistically anomalous cells in one numeric column of a `display: list` region, rendered as a WCAG-safe badge (colour + icon + text).

**Architecture:** Reuse the `flag_outliers` engine + `ComparisonOutlierSpec` shipped with `display: comparison`. One new IR field (`outlier_on`); the method reuses the existing `outlier_method:` keyword → `region.outlier`. Compute an index-aligned flag list in a pure post-fetch pass; render a composite cell (value + tone badge) in `_build_list`. Layers `http → page → render → core`.

**Tech Stack:** Python 3.12, Pydantic IR, pytest. Reuses everything from the comparison slice.

## Global Constraints

- Layer rule: pure flagging in `render/` (`flag_outliers`, already shipped) + a pure helper in `http/runtime/`; orchestration in `http/`; IR/parser/validation in `core/`. `core` must not import `page`/`http`.
- `ruff check src/ tests/` + `ruff format src/ tests/` clean; bare `mypy src/dazzle` clean (matches CI).
- **Run the full `pytest -m "not e2e"` before shipping** — the golden-master + walk jobs live outside the `-m gate` subset.
- The new `WorkspaceRegion.outlier_on` field **drifts two baselines** — regenerate both at ship time: golden-master snapshot (`pytest tests/integration/test_golden_master.py --snapshot-update`) and the api-surface ir-types baseline (`dazzle inspect api ir-types --write`). Each needs a CHANGELOG note (the api-surface drift gate requires it). The parser-corpus snapshot (`tests/parser_corpus/__snapshots__/test_appspec_corpus.ambr`) drifts too if any corpus region serializes the field — regen with `pytest tests/parser_corpus/test_appspec_corpus.py --snapshot-update`.
- Within-scope flagging: the flag pass runs AFTER the scoped fetch over the displayed rows — never widens scope.
- The 3 `test_fuzzer_oracle` failures in the full suite are pre-existing pollution (pass isolated) — ignore.
- Complexity ratchet (`tests/unit/test_complexity_ratchet.py`): keep new functions ≤ CC 15. If a function exceeds it, extract a helper; if a file's MI rank drops, regenerate with `dazzle fitness code --write-baseline` and note why.

## File structure

- `src/dazzle/core/ir/workspaces.py` — `WorkspaceRegion.outlier_on: str | None`.
- `src/dazzle/core/dsl_parser_impl/workspace.py` — `_kw_outlier_on` + state field + builder wiring.
- `src/dazzle/core/validation/ux.py` — `validate_outlier_decorators` + `E_OUTLIER_*` (reuses `_NUMERIC_FIELD_KINDS` + `_validate_comparison_outlier`).
- `src/dazzle/core/lint.py`, `src/dazzle/core/validator.py`, `src/dazzle/core/validation/__init__.py` — register the new validator.
- `src/dazzle/http/runtime/workspace_region_computes.py` — `build_outlier_flags` (pure).
- `src/dazzle/http/runtime/workspace_region_orchestration.py` — compute branch.
- `src/dazzle/http/runtime/workspace_region_render.py` — `RegionRenderInputs.{outlier_flags,outlier_on}` + LIST adapter-ctx keys.
- `src/dazzle/render/fragment/region/_context.py` — RegionContext TypedDict keys.
- `src/dazzle/render/fragment/region/_builders_tables.py` — `_build_list` composite cell + `_outlier_badge`.
- `examples/ops_dashboard/dsl/app.dsl` — example `outlier_on` on a `display: list` region.

---

## Task 1: IR — `WorkspaceRegion.outlier_on`

**Files:**
- Modify: `src/dazzle/core/ir/workspaces.py` (new field on `WorkspaceRegion`)
- Test: `tests/unit/test_outlier_decorator_ir.py`

**Interfaces — Produces:** `WorkspaceRegion.outlier_on: str | None = None`. Reuses existing `WorkspaceRegion.outlier: ComparisonOutlierSpec | None`.

- [ ] **Step 1: failing test**

```python
# tests/unit/test_outlier_decorator_ir.py
from dazzle.core.ir.workspaces import ComparisonOutlierSpec, DisplayMode, WorkspaceRegion


def test_outlier_on_default_none() -> None:
    r = WorkspaceRegion(name="r", display=DisplayMode.LIST)
    assert r.outlier_on is None


def test_outlier_on_set_with_method() -> None:
    r = WorkspaceRegion(
        name="r",
        display=DisplayMode.LIST,
        outlier_on="response_time_ms",
        outlier=ComparisonOutlierSpec(method="sigma", sigma_k=2.0),
    )
    assert r.outlier_on == "response_time_ms"
    assert r.outlier is not None and r.outlier.method == "sigma"
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_outlier_decorator_ir.py -q` → FAIL (`outlier_on` not a field).

- [ ] **Step 3: implement.** In `workspaces.py`, find the comparison fields block on `WorkspaceRegion` (added for #1470 — the lines `rank_by: str | None = None`, `order: ...`, `outlier: ComparisonOutlierSpec | None = None`). Add immediately after `outlier`:

```python
    # #1470 outlier_on — statistical outlier decorator on a list region column.
    # Names the numeric column to flag; the test reuses `outlier` (set by
    # outlier_method:). Only meaningful for display: list (validated).
    outlier_on: str | None = None
```

- [ ] **Step 4:** `uv run pytest tests/unit/test_outlier_decorator_ir.py -q` → PASS.

- [ ] **Step 5:** `uv run mypy src/dazzle` clean; `uv run ruff check src/ tests/ --fix && uv run ruff format src/ tests/`.

- [ ] **Step 6: regen api-surface ir-types baseline:** `uv run dazzle inspect api ir-types --write` then `uv run pytest tests/unit/test_api_surface_drift.py -q` → PASS. Confirm the only diff is the single `outlier_on: str | None = None` line on `WorkspaceRegion`.

- [ ] **Step 7: commit**

```bash
git add src/dazzle/core/ir/workspaces.py docs/api-surface/ir-types.txt tests/unit/test_outlier_decorator_ir.py
git commit -m "feat(#1470): IR for outlier_on statistical decorator (WorkspaceRegion field)"
```

---

## Task 2: Parser — `outlier_on:` keyword

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/workspace.py`
- Test: `tests/unit/test_outlier_decorator_parser.py`

**Interfaces — Consumes:** `WorkspaceRegion.outlier_on` (Task 1), the existing `outlier_method:` keyword + `_parse_outlier_spec` (shipped with comparison). **Produces:** parsed `region.outlier_on` + `region.outlier`.

- [ ] **Step 1: failing test**

```python
# tests/unit/test_outlier_decorator_parser.py
from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl

_DSL = """
module m
app a "A"
entity System "System":
  id: uuid pk
  name: str(40)
  response_time_ms: int

workspace ops "Ops":
  health:
    source: System
    display: list
    fields: [name, response_time_ms]
    outlier_on: response_time_ms
    outlier_method: sigma:2
"""


def _region(name: str):
    *_, fragment = parse_dsl(_DSL, Path("t.dsl"))
    ws = fragment.workspaces[0]
    return next(r for r in ws.regions if r.name == name)


def test_parses_outlier_on_and_method() -> None:
    r = _region("health")
    assert r.outlier_on == "response_time_ms"
    assert r.outlier is not None
    assert r.outlier.method == "sigma" and r.outlier.sigma_k == 2.0
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_outlier_decorator_parser.py -q` → FAIL (unknown keyword `outlier_on`).

- [ ] **Step 3: implement.** In `workspace.py`:

(a) Add to `_WorkspaceRegionState` (next to the comparison fields `rank_by`/`order`/`outlier` added for #1470):

```python
    outlier_on: str | None = None  # #1470 — outlier decorator target column
```

(b) Add the keyword function next to `_kw_rank_by` (mirror it exactly):

```python
def _kw_outlier_on(parser: Any, state: _WorkspaceRegionState) -> None:
    """#1470: ``outlier_on: <column>`` — flag statistical outliers in this
    numeric list column (method via the reused ``outlier_method:`` keyword)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.outlier_on = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()
```

(c) Register it in `_WORKSPACE_REGION_IDENT_KEYWORDS` next to the comparison entries:

```python
    "outlier_on": _kw_outlier_on,  # #1470
```

(d) Wire it into the `ir.WorkspaceRegion(...)` construction in `_build_workspace_region` (next to `outlier=state.outlier`):

```python
        outlier_on=state.outlier_on,  # #1470
```

- [ ] **Step 4:** `uv run pytest tests/unit/test_outlier_decorator_parser.py -q` → PASS. Then `uv run pytest tests/unit/test_parser.py tests/parser_corpus/ -q`. If a parser-corpus snapshot drifts (a region now serializes `outlier_on`), regen it: `uv run pytest tests/parser_corpus/test_appspec_corpus.py --snapshot-update -q`, then re-run to confirm PASS and `git diff` to confirm the only change is `'outlier_on': None` lines.

- [ ] **Step 5:** `uv run ruff check src/ tests/ --fix && uv run ruff format src/ tests/`; `uv run mypy src/dazzle` clean.

- [ ] **Step 6: commit**

```bash
git add src/dazzle/core/dsl_parser_impl/workspace.py tests/unit/test_outlier_decorator_parser.py tests/parser_corpus/
git commit -m "feat(#1470): parse outlier_on keyword for the statistical decorator"
```

---

## Task 3: Validation — `E_OUTLIER_*`

**Files:**
- Modify: `src/dazzle/core/validation/ux.py` (new `validate_outlier_decorators` + helper)
- Modify: `src/dazzle/core/validation/__init__.py`, `src/dazzle/core/validator.py`, `src/dazzle/core/lint.py` (register)
- Test: `tests/unit/test_outlier_decorator_validation.py`

**Interfaces — Consumes:** the region IR (Task 1), the existing `_NUMERIC_FIELD_KINDS` + `_validate_comparison_outlier` helpers in `ux.py` (shipped with comparison). **Produces:** `validate_outlier_decorators(appspec) -> tuple[list[str], list[str]]`.

Rules: a region with `outlier_on` set → (1) `display` must be `list` (`E_OUTLIER_DISPLAY`); (2) `outlier_on` must name a numeric field (int/decimal/float/money) on `source` (`E_OUTLIER_NOT_NUMERIC` — also covers an unknown field); (3) outlier params well-formed via the reused `_validate_comparison_outlier` (`E_COMPARISON_OUTLIER_INVALID`). A missing `outlier_method:` is valid (defaults to iqr at compute time).

- [ ] **Step 1: failing test**

```python
# tests/unit/test_outlier_decorator_validation.py
from __future__ import annotations

from pathlib import Path

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.validator import validate_outlier_decorators

_HEADER = """module t
app T "T"

entity System "System":
  id: uuid pk
  name: str(40)
  response_time_ms: int

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


def test_outlier_on_requires_list_display(tmp_path: Path) -> None:
    dsl = """  health:
    source: System
    display: bar_chart
    group_by: name
    aggregate:
      count: count(System)
    outlier_on: response_time_ms
"""
    errors, _ = validate_outlier_decorators(_appspec(dsl, tmp_path))
    assert any("E_OUTLIER_DISPLAY" in e for e in errors)


def test_outlier_on_must_be_numeric(tmp_path: Path) -> None:
    dsl = """  health:
    source: System
    display: list
    fields: [name, response_time_ms]
    outlier_on: name
"""
    errors, _ = validate_outlier_decorators(_appspec(dsl, tmp_path))
    assert any("E_OUTLIER_NOT_NUMERIC" in e for e in errors)


def test_outlier_on_valid(tmp_path: Path) -> None:
    dsl = """  health:
    source: System
    display: list
    fields: [name, response_time_ms]
    outlier_on: response_time_ms
    outlier_method: iqr
"""
    errors, _ = validate_outlier_decorators(_appspec(dsl, tmp_path))
    assert errors == []
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_outlier_decorator_validation.py -q` → FAIL (`validate_outlier_decorators` not importable).

- [ ] **Step 3: implement.** In `ux.py`, after `validate_comparison_regions`, add:

```python
def validate_outlier_decorators(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate `outlier_on` statistical decorators on list regions (#1470)."""
    errors: list[str] = []
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if not region.outlier_on:
                continue
            label = f"Workspace '{workspace.name}' region '{region.name or region.source}'"
            if region.display != ir.DisplayMode.LIST:
                errors.append(
                    f"E_OUTLIER_DISPLAY: {label} `outlier_on` requires `display: list` "
                    f"(got {region.display.value})."
                )
            source_name = (
                region.source.split(".")[0]
                if region.source and "." in region.source
                else region.source
            )
            entity = appspec.get_entity(source_name) if source_name else None
            field = None
            if entity is not None:
                field = next((f for f in entity.fields if f.name == region.outlier_on), None)
            if field is None or field.type.kind not in _NUMERIC_FIELD_KINDS:
                errors.append(
                    f"E_OUTLIER_NOT_NUMERIC: {label} `outlier_on: {region.outlier_on}` must "
                    f"name a numeric field (int/decimal/float/money) on the source entity."
                )
            if region.outlier is not None:
                errors.extend(_validate_comparison_outlier(region.outlier, label))
    return errors, []
```

(`_NUMERIC_FIELD_KINDS` and `_validate_comparison_outlier` already exist in this file from the comparison slice — reuse, do not redefine.)

- [ ] **Step 4: register the validator.**
  - In `src/dazzle/core/validation/__init__.py`: add `validate_outlier_decorators` to the `from .ux import (...)` block and to `__all__` (alphabetical, near `validate_comparison_regions`).
  - In `src/dazzle/core/validator.py`: add `validate_outlier_decorators` to the `from .validation import (...)` block and to `__all__` (near `validate_comparison_regions`).
  - In `src/dazzle/core/lint.py`: add `validate_outlier_decorators` to the `from .validator import (...)` block, then add a call site immediately after the comparison one:

```python
    # outlier_on statistical decorator validation (#1470)
    errors, warnings = validate_outlier_decorators(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)
```

- [ ] **Step 5:** `uv run pytest tests/unit/test_outlier_decorator_validation.py -q` → PASS. Then spot-check no example false-positives: `cd examples/ops_dashboard && uv run dazzle validate` → exit 0; `cd ../simple_task && uv run dazzle validate` → exit 0.

- [ ] **Step 6:** `uv run ruff check src/ tests/ --fix && uv run ruff format src/ tests/`; `uv run mypy src/dazzle` clean; `uv run pytest -m gate -q` (complexity ratchet — if `validate_outlier_decorators` exceeds CC 15, extract the rank-by-style field lookup into a helper).

- [ ] **Step 7: commit**

```bash
git add src/dazzle/core/validation/ux.py src/dazzle/core/validation/__init__.py src/dazzle/core/validator.py src/dazzle/core/lint.py tests/unit/test_outlier_decorator_validation.py
git commit -m "feat(#1470): validate outlier_on decorator (E_OUTLIER_*)"
```

---

## Task 4: Orchestration — `build_outlier_flags` + ctx wiring

**Files:**
- Modify: `src/dazzle/http/runtime/workspace_region_computes.py` (`build_outlier_flags`)
- Modify: `src/dazzle/http/runtime/workspace_region_orchestration.py` (compute branch)
- Modify: `src/dazzle/http/runtime/workspace_region_render.py` (`RegionRenderInputs` fields + LIST adapter ctx)
- Modify: `src/dazzle/render/fragment/region/_context.py` (TypedDict keys)
- Test: `tests/unit/test_outlier_decorator_orchestration.py`

**Interfaces — Consumes:** `flag_outliers` + `ComparisonOutlierSpec` (already imported in `workspace_region_computes.py` from the comparison slice). **Produces:** `build_outlier_flags(items, *, column, spec) -> list[Literal["low","high"] | None]` (one entry per item, index-aligned); ctx keys `outlier_flags` + `outlier_on`.

- [ ] **Step 1: failing test**

```python
# tests/unit/test_outlier_decorator_orchestration.py
from dazzle.core.ir.workspaces import ComparisonOutlierSpec
from dazzle.http.runtime.workspace_region_computes import build_outlier_flags


def test_flags_aligned_to_items() -> None:
    items = [
        {"name": "A", "ms": 100},
        {"name": "B", "ms": 98},
        {"name": "C", "ms": 96},
        {"name": "D", "ms": 94},
        {"name": "E", "ms": 92},
        {"name": "F", "ms": 5},
    ]
    flags = build_outlier_flags(items, column="ms", spec=ComparisonOutlierSpec(method="iqr"))
    assert len(flags) == len(items)
    assert flags[5] == "low"  # 5 is the low outlier vs the tight pack
    assert flags[0] is None


def test_small_n_no_flags() -> None:
    items = [{"ms": 1}, {"ms": 99}, {"ms": 2}]
    assert build_outlier_flags(items, column="ms", spec=ComparisonOutlierSpec(method="iqr")) == [
        None,
        None,
        None,
    ]


def test_non_finite_and_none_excluded() -> None:
    items = [
        {"ms": 100},
        {"ms": 98},
        {"ms": 96},
        {"ms": 94},
        {"ms": None},
        {"ms": float("inf")},
        {"ms": 5},
    ]
    flags = build_outlier_flags(items, column="ms", spec=ComparisonOutlierSpec(method="iqr"))
    assert flags[4] is None and flags[5] is None  # None + inf never flagged
    assert flags[6] == "low"


def test_method_none_inert() -> None:
    items = [{"ms": 1}, {"ms": 2}, {"ms": 3}, {"ms": 4}, {"ms": 99}]
    assert build_outlier_flags(items, column="ms", spec=ComparisonOutlierSpec(method="none")) == [
        None
    ] * 5
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_outlier_decorator_orchestration.py -q` → FAIL (`build_outlier_flags` missing).

- [ ] **Step 3: implement `build_outlier_flags`.** In `workspace_region_computes.py`, after `build_comparison_inputs`, add (reuse the module's existing `_coerce_float`, `flag_outliers`, `ComparisonOutlierSpec`, and the `Flag` type — import `Flag` if not already: `from dazzle.render.fragment.outliers import Flag, flag_outliers`):

```python
def build_outlier_flags(
    items: list[dict[str, Any]], *, column: str, spec: ComparisonOutlierSpec
) -> list[Flag | None]:
    """Per-row outlier flag for one column, index-aligned to ``items`` (#1470).

    Reads ``column`` from each item, coercing non-numeric / non-finite / None to
    None (excluded from the distribution and never flagged), then runs the shared
    ``flag_outliers`` pass. Pure: runs after the scoped fetch, never widens scope.
    """
    values: list[float | None] = []
    for item in items:
        v = _coerce_float(item.get(column))
        values.append(v if v is not None and math.isfinite(v) else None)
    return flag_outliers(values, spec)
```

Add `import math` to the file's imports if absent.

- [ ] **Step 4:** `uv run pytest tests/unit/test_outlier_decorator_orchestration.py -q` → PASS.

- [ ] **Step 5: thread through `RegionRenderInputs`.** In `workspace_region_render.py`, add fields to the `RegionRenderInputs` dataclass next to `comparison_rows`/`comparison_max`:

```python
    # #1470 outlier_on — per-row flags + the decorated column key.
    outlier_flags: list[Any] = field(default_factory=list)
    outlier_on: str = ""
```

Then in `_build_list_adapter_ctx`, inside the `if display_upper == "LIST":` branch, add:

```python
        adapter_ctx["outlier_flags"] = inputs.outlier_flags
        adapter_ctx["outlier_on"] = inputs.outlier_on
```

- [ ] **Step 6: RegionContext TypedDict.** In `src/dazzle/render/fragment/region/_context.py`, next to the `comparison_rows`/`comparison_max` keys, add:

```python
    # #1470 outlier_on — list-column outlier decorator.
    outlier_flags: Any
    outlier_on: Any
```

- [ ] **Step 7: orchestration compute branch.** In `workspace_region_orchestration.py`, near the comparison compute branch (after the `display == "COMPARISON"` block), add (it uses the already-imported `ComparisonOutlierSpec` + `build_outlier_flags` — add `build_outlier_flags` to the `workspace_region_computes` import block):

```python
    # Outlier decorator (#1470): per-row flags for one list column.
    outlier_on = getattr(ctx.ir_region, "outlier_on", None) or ""
    if display == "LIST" and outlier_on and not scope_denied:
        outlier_flags = build_outlier_flags(
            items,
            column=outlier_on,
            spec=getattr(ctx.ir_region, "outlier", None) or ComparisonOutlierSpec(),
        )
    else:
        outlier_flags = []
        outlier_on = ""
```

Then add to the `RegionRenderInputs(...)` construction (next to `comparison_rows=...`):

```python
        outlier_flags=outlier_flags,
        outlier_on=outlier_on,
```

- [ ] **Step 8:** `uv run pytest tests/unit/test_outlier_decorator_orchestration.py -q` → PASS; `uv run ruff check src/ tests/ --fix && uv run ruff format src/ tests/`; `uv run mypy src/dazzle` clean.

- [ ] **Step 9: commit**

```bash
git add src/dazzle/http/runtime/workspace_region_computes.py src/dazzle/http/runtime/workspace_region_orchestration.py src/dazzle/http/runtime/workspace_region_render.py src/dazzle/render/fragment/region/_context.py tests/unit/test_outlier_decorator_orchestration.py
git commit -m "feat(#1470): outlier_on orchestration (per-row flags -> ctx)"
```

---

## Task 5: Render — composite cell in `_build_list`

**Files:**
- Modify: `src/dazzle/render/fragment/region/_builders_tables.py` (`_build_list` + `_outlier_badge`)
- Test: `tests/unit/test_outlier_decorator_render.py`

**Interfaces — Consumes:** `ctx["outlier_flags"]` (index-aligned to `items`) + `ctx["outlier_on"]` (Task 4), `_render_typed_value`, the `Row` layout primitive. **Produces:** a `display: list` region whose `outlier_on` column shows a tone badge on flagged rows.

- [ ] **Step 1: failing test** (mirror `tests/unit/test_region_adapter.py`'s harness)

```python
# tests/unit/test_outlier_decorator_render.py
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeRegion:
    def __init__(self, name: str) -> None:
        self.name = name
        self.title = None
        self.display = "list"
        self.empty_message = None
        self.row_action = None


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


def _ctx() -> dict:
    return {
        "items": [
            {"name": "Fast", "ms": 100},
            {"name": "Slow", "ms": 5},
        ],
        "columns": [
            {"key": "name", "label": "Name", "type": "text"},
            {"key": "ms", "label": "Response (ms)", "type": "text"},
        ],
        "outlier_on": "ms",
        "outlier_flags": [None, "low"],
    }


def test_flagged_cell_has_tone_badge() -> None:
    html = _render(WorkspaceRegionAdapter().build(_FakeRegion("health"), _ctx()))
    assert 'data-dz-tone="warning"' in html
    assert "⚠" in html
    assert "low" in html
    # Both row values still render.
    assert "100" in html and "5" in html


def test_no_flags_renders_plain_list() -> None:
    ctx = _ctx()
    ctx["outlier_flags"] = [None, None]
    html = _render(WorkspaceRegionAdapter().build(_FakeRegion("health"), ctx))
    assert 'data-dz-tone="warning"' not in html
    assert "100" in html and "5" in html


def test_outlier_on_unset_is_ordinary_list() -> None:
    ctx = _ctx()
    ctx["outlier_on"] = ""
    ctx["outlier_flags"] = []
    html = _render(WorkspaceRegionAdapter().build(_FakeRegion("health"), ctx))
    assert "⚠" not in html
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_outlier_decorator_render.py -q` → FAIL (no badge in output).

- [ ] **Step 3: implement.** In `_builders_tables.py`:

(a) Add `Row` to the `from dazzle.render.fragment import (...)` block (next to `Stack`), and `RawHTML` if not already imported there (it is imported in `_shared.py`; add to `_builders_tables` import block if absent).

(b) Add a module-level helper (above the mixin class):

```python
def _outlier_badge(flag: str) -> RawHTML:
    """WCAG-safe outlier badge: tone colour + ⚠ icon + direction text (#1470).

    Uniform `warning` tone (an outlier is *notable*, not good/bad); the
    direction is carried by the ⚠ icon + `high`/`low` text + aria-label.
    """
    from html import escape as _esc

    direction = flag if flag in ("low", "high") else "outlier"
    return RawHTML(
        f'<span class="dz-badge dz-badge-sm" data-dz-tone="warning" role="status" '
        f'aria-label="Outlier: {_esc(direction)}">⚠ {_esc(direction)}</span>'
    )
```

(c) In `_build_list`, before the `for item in items:` cell loop, read the decorator ctx:

```python
        outlier_on = str(ctx.get("outlier_on") or "")
        outlier_flags = ctx.get("outlier_flags") or []
```

Then inside the loop, the cell build currently is:

```python
            for col in columns:
                if not isinstance(col, dict):
                    continue
                row_cells.append(_render_typed_value(item, col))
```

Replace the `row_cells.append(...)` line with a flag-aware composite. Track the item index (use `enumerate`); when this column is the decorated one and the row's flag is set, wrap value + badge in a `Row`:

```python
        for item_idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            row_cells: list[object] = []
            for col in columns:
                if not isinstance(col, dict):
                    continue
                value_cell = _render_typed_value(item, col)
                flag = (
                    outlier_flags[item_idx]
                    if outlier_on
                    and str(col.get("key") or "") == outlier_on
                    and item_idx < len(outlier_flags)
                    else None
                )
                if flag in ("low", "high"):
                    row_cells.append(Row(children=(value_cell, _outlier_badge(flag)), gap="sm", align="center"))
                else:
                    row_cells.append(value_cell)
            list_rows.append(tuple(row_cells))
            row_items.append(item)
            # ... (leave the existing row_action / drill handling below unchanged)
```

(Keep the existing `row_action_spec` / `row_items` / drill logic that follows in the loop body intact — only the cell-append changed, and the loop header now carries `enumerate`. The non-dict `item` guard must run before indexing `outlier_flags`; since skipped items break index alignment, this is acceptable for the MVP because `build_outlier_flags` and `_build_list` both skip non-dict items in the same order — but to stay exactly aligned, note that `outlier_flags` is built over ALL `items` in Task 4. Non-dict items in a region's fetched rows do not occur in practice; the `item_idx < len(outlier_flags)` guard prevents any IndexError.)

- [ ] **Step 4:** `uv run pytest tests/unit/test_outlier_decorator_render.py -q` → PASS.

- [ ] **Step 5:** `uv run ruff check src/ tests/ --fix && uv run ruff format src/ tests/`; `uv run mypy src/dazzle` clean; `uv run pytest -m gate -q` (complexity — if `_build_list` exceeds CC 15 after the change, extract the cell-build into a `_list_cell(item, col, item_idx, outlier_on, outlier_flags) -> object` helper). Also run `uv run pytest tests/unit/test_region_adapter.py tests/unit/test_htmx_workspace_composite.py -q` to confirm no list-render regression + card-safety still holds.

- [ ] **Step 6: commit**

```bash
git add src/dazzle/render/fragment/region/_builders_tables.py tests/unit/test_outlier_decorator_render.py
git commit -m "feat(#1470): render outlier_on tone badge in list cells"
```

---

## Task 6: Example + full-suite + ship

**Files:**
- Modify: `examples/ops_dashboard/dsl/app.dsl` (add `outlier_on` to a `display: list` region)
- Modify: `CHANGELOG.md`, version files (`/bump`), golden-master snapshot
- Test: the example's `dazzle validate` + the full suite

- [ ] **Step 1:** Find a `display: list` region in `examples/ops_dashboard/dsl/app.dsl` whose source has a numeric field (e.g. a System/Alert list with `response_time_ms` / `error_rate` / `hours_open`). Add `outlier_on: <numeric_col>` to it (the column must be in the region's `fields:`/`repr_fields` and numeric). If no suitable list region exists, add a small one sourced from `System` listing `[name, response_time_ms]` with `outlier_on: response_time_ms` + `outlier_method: iqr`. Then `cd examples/ops_dashboard && uv run dazzle validate` → exit 0.

- [ ] **Step 2: regen golden-master:** `uv run pytest tests/integration/test_golden_master.py --snapshot-update -q`, then re-run to confirm PASS. `git diff` to confirm the only change is `'outlier_on': None` lines on regions.

- [ ] **Step 3: full suite:** `uv run pytest tests/ -m "not e2e" -q`. Expect only the 3 pre-existing `test_fuzzer_oracle` pollution failures (confirm they pass in isolation: `uv run pytest tests/unit/test_fuzzer_oracle.py -q`). Fix anything else.

- [ ] **Step 4:** `uv run ruff check src/ tests/ && uv run mypy src/dazzle` clean.

- [ ] **Step 5:** `/bump patch` (bump all 6 canonical version lines via the single sed block, then `uv lock`). CHANGELOG entry under `### Added` (the `outlier_on` decorator — list-column statistical flagging, reuses comparison's engine, WCAG badge) + `### Agent Guidance` (when to use `outlier_on` vs the comparison region; uniform-warning-tone rationale; deferred RAG/multi-column/surface-field follow-ons) + the api-surface drift note under `### Changed`.

- [ ] **Step 6: commit + tag + push**, then `gh run watch <run-id> --exit-status` to green. Confirm `git status` clean (commit `uv.lock` if the bump drifted it — run `uv lock` after the version sed, before commit).

```bash
git add -A
git commit -m "feat(#1470): outlier_on example + ship"
git tag vX.Y.Z   # the bumped version
git push origin main && git push origin vX.Y.Z
```

---

## Self-review

- **Spec coverage:** IR field → Task 1; grammar → Task 2; validation (`E_OUTLIER_DISPLAY`/`E_OUTLIER_NOT_NUMERIC` + reused outlier-param) → Task 3; pure flag pass + population=displayed-rows + non-finite/None handling + ctx wiring → Task 4; WCAG composite-cell render (uniform warning tone + icon + text) → Task 5; example + baselines + ship → Task 6. All spec sections covered.
- **Type consistency:** `WorkspaceRegion.outlier_on: str | None` (Task 1) → parsed in Task 2 → validated in Task 3 → read via `ctx.ir_region.outlier_on` in Task 4 → `build_outlier_flags(items, column, spec) -> list[Flag | None]` (Task 4) → `ctx["outlier_flags"]`/`ctx["outlier_on"]` consumed in Task 5. `region.outlier: ComparisonOutlierSpec` reused unchanged from the comparison slice throughout.
- **Known-unknowns flagged read-first (not fabricated):** the exact example list region to decorate (Task 6 Step 1 says how to pick or add one). Everything else (parser registry, validator helpers, RegionRenderInputs, LIST adapter ctx branch, `_build_list` cell loop, ListRegion fragment-cell emit) was located during design — exact files + line-anchored patterns given.
- **Placeholder scan:** none — every code step shows the actual code; the one calibration note (IQR test vector `[100,98,96,94,92,5]`) is pinned from the comparison slice's verified behaviour.

## Notes

- Reuses the comparison slice wholesale: `flag_outliers`, `ComparisonOutlierSpec`, `_NUMERIC_FIELD_KINDS`, `_validate_comparison_outlier`, `_coerce_float`. The only genuinely new code is `outlier_on` (IR/parser), `validate_outlier_decorators`, `build_outlier_flags`, and the `_build_list` composite cell + `_outlier_badge`.
- Uniform `warning` tone is deliberate (decision 5 in the spec) — good/bad-by-direction is the deferred RAG decorator. Don't infer direction semantics here.
- One baseline-regen difference from comparison: `outlier_on` is a single nullable field, so the api-surface + golden-master diffs are smaller (one line per region), but still gated — regen both with CHANGELOG notes.
