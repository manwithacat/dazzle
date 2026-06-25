# `rag_on` Fixed-Band RAG Decorator Implementation Plan (#1470, closes item 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `rag_on:` — a region keyword that flags a `display: list` column with a red/amber/green tone by author-defined `tone_bands`, rendered as a WCAG-safe badge.

**Architecture:** Mirror `outlier_on` across every layer, swapping the statistical test for author bands. Reuse the existing `ToneBandSpec` + `_parse_tone_bands_block`. A pure tone pass maps each cell value to a band tone; the `_build_list` composite-cell path renders a tone badge. Layers `http → page → render → core`.

**Tech Stack:** Python 3.12, Pydantic IR, pytest. Reuses `ToneBandSpec`, `_parse_tone_bands_block`, `_coerce_float`, the `outlier_on` registration + render pattern, and the catalogue harness.

## Global Constraints

- `ruff check src/ tests/` + `ruff format` clean; bare `mypy src/dazzle` clean (matches CI).
- **Run the full `pytest -m "not e2e"` before shipping.** The 3 `test_fuzzer_oracle` failures are pre-existing pollution (pass isolated) — ignore.
- New `WorkspaceRegion.rag_on` + `tone_bands` fields **drift baselines** — regenerate ir-types (`dazzle inspect api ir-types --write`) + golden-master (`pytest tests/integration/test_golden_master.py --snapshot-update`); each needs a CHANGELOG note. Parser-corpus regen only if a corpus region serializes `tone_bands: []` (regen if it drifts).
- Within-scope: the tone pass runs AFTER the scoped fetch over the displayed rows — never widens scope.
- Complexity ratchet: new functions ≤ CC 15; extract helpers if exceeded.
- The catalogue fidelity test gains a 10th mode — keep it green.

## File structure

- `src/dazzle/core/ir/workspaces.py` — `WorkspaceRegion.{rag_on, tone_bands}`.
- `src/dazzle/core/dsl_parser_impl/workspace.py` — `_kw_rag_on`, `_kw_tone_bands` + state fields + builder wiring.
- `src/dazzle/core/validation/ux.py` — `validate_rag_decorators` + `E_RAG_*`.
- `src/dazzle/core/lint.py`, `validator.py`, `validation/__init__.py` — register.
- `src/dazzle/http/runtime/workspace_region_computes.py` — `build_rag_tones`.
- `src/dazzle/http/runtime/workspace_region_orchestration.py` — compute branch.
- `src/dazzle/http/runtime/workspace_region_render.py` — `RegionRenderInputs.{rag_tones, rag_on}` + LIST adapter-ctx keys.
- `src/dazzle/render/fragment/region/_context.py` — RegionContext TypedDict keys.
- `src/dazzle/render/fragment/region/_builders_tables.py` — `_build_list` rag cell + `_rag_badge`.
- `examples/ops_dashboard/dsl/app.dsl`, `fixtures/component_showcase/dsl/app.dsl`, `src/dazzle/testing/ux_catalogue_manifest.py` — dogfood (10th catalogue mode).

---

## Task 1: IR — `rag_on` + `tone_bands` fields

**Files:**
- Modify: `src/dazzle/core/ir/workspaces.py`
- Test: `tests/unit/test_rag_decorator_ir.py`

**Interfaces — Produces:** `WorkspaceRegion.rag_on: str | None = None`, `WorkspaceRegion.tone_bands: list[ToneBandSpec] = Field(default_factory=list)`. Reuses existing `ToneBandSpec`.

- [ ] **Step 1: failing test**

```python
# tests/unit/test_rag_decorator_ir.py
from dazzle.core.ir.workspaces import DisplayMode, ToneBandSpec, WorkspaceRegion


def test_rag_on_default() -> None:
    r = WorkspaceRegion(name="r", display=DisplayMode.LIST)
    assert r.rag_on is None and r.tone_bands == []


def test_rag_on_with_bands() -> None:
    r = WorkspaceRegion(
        name="r",
        display=DisplayMode.LIST,
        rag_on="error_rate",
        tone_bands=[ToneBandSpec(at=5.0, tone="destructive"), ToneBandSpec(at=0.0, tone="positive")],
    )
    assert r.rag_on == "error_rate"
    assert r.tone_bands[0].at == 5.0 and r.tone_bands[0].tone == "destructive"
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_rag_decorator_ir.py -q` → FAIL.

- [ ] **Step 3: implement.** In `workspaces.py`, find the `outlier_on` field on `WorkspaceRegion` (added for #1470: `outlier_on: str | None = None`). `ToneBandSpec` is already defined in this file. Add immediately after `outlier_on`:

```python
    # #1470 rag_on — fixed-band RAG decorator on a list region column.
    # Names the numeric column; `tone_bands` defines value->tone bands
    # (descending `at`, first `value >= at` wins). Only for display: list.
    rag_on: str | None = None
    tone_bands: list[ToneBandSpec] = Field(default_factory=list)
```

(Confirm `Field` is imported — it is, used by sibling fields. `ToneBandSpec` is defined earlier in the file.)

- [ ] **Step 4:** `uv run pytest tests/unit/test_rag_decorator_ir.py -q` → PASS.

- [ ] **Step 5:** `uv run mypy src/dazzle` clean; ruff.

- [ ] **Step 6: regen ir-types:** `uv run dazzle inspect api ir-types --write` then `uv run pytest tests/unit/test_api_surface_drift.py -q` → PASS. Confirm the diff is only the `rag_on` + `tone_bands` fields on `WorkspaceRegion`.

- [ ] **Step 7: commit**

```bash
git add src/dazzle/core/ir/workspaces.py docs/api-surface/ir-types.txt tests/unit/test_rag_decorator_ir.py
git commit -m "feat(#1470): IR for rag_on fixed-band decorator (rag_on + tone_bands fields)"
```

---

## Task 2: Parser — `rag_on:` + `tone_bands:`

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/workspace.py`
- Test: `tests/unit/test_rag_decorator_parser.py`

**Interfaces — Consumes:** the existing `_parse_tone_bands_block()` (a `WorkspaceParserMixin` method, callable as `parser._parse_tone_bands_block()`). **Produces:** parsed `region.rag_on` + `region.tone_bands`.

- [ ] **Step 1: failing test**

```python
# tests/unit/test_rag_decorator_parser.py
from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl

_DSL = """
module m
app a "A"
entity System "System":
  id: uuid pk
  name: str(40)
  error_rate: decimal(5,2)

workspace ops "Ops":
  health:
    source: System
    display: list
    rag_on: error_rate
    tone_bands:
      - at: 5
        tone: destructive
      - at: 1
        tone: warning
      - at: 0
        tone: positive
"""


def _region(name: str):
    *_, fragment = parse_dsl(_DSL, Path("t.dsl"))
    return next(r for r in fragment.workspaces[0].regions if r.name == name)


def test_parses_rag_on_and_bands() -> None:
    r = _region("health")
    assert r.rag_on == "error_rate"
    assert [(b.at, b.tone) for b in r.tone_bands] == [(5.0, "destructive"), (1.0, "warning"), (0.0, "positive")]
```

- [ ] **Step 2:** run → FAIL (unknown keyword `rag_on`).

- [ ] **Step 3: implement.** In `workspace.py`:

(a) Add to `_WorkspaceRegionState` (next to `outlier_on: str | None = None  # #1470`):

```python
    rag_on: str | None = None  # #1470 — RAG decorator target column
    tone_bands: list[Any] = field(default_factory=list)  # #1470 — RAG bands
```

(b) Add the keyword functions next to `_kw_outlier_on` (mirror it, plus the tone_bands block which mirrors the cohort_strip invocation at lines ~1275-1279):

```python
def _kw_rag_on(parser: Any, state: _WorkspaceRegionState) -> None:
    """#1470: ``rag_on: <column>`` — RAG-flag this numeric list column by `tone_bands`."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.rag_on = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _kw_tone_bands(parser: Any, state: _WorkspaceRegionState) -> None:
    """#1470: ``tone_bands:`` dash-list of `- at: <n>` + `tone:` — the RAG bands."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    parser.expect(TokenType.INDENT)
    state.tone_bands = parser._parse_tone_bands_block()
    parser.expect(TokenType.DEDENT)
    parser.skip_newlines()
```

(c) Register in `_WORKSPACE_REGION_IDENT_KEYWORDS` (next to `"outlier_on"`):

```python
    "rag_on": _kw_rag_on,  # #1470
    "tone_bands": _kw_tone_bands,  # #1470
```

(d) Wire into `_build_workspace_region` (next to `outlier_on=state.outlier_on`):

```python
        rag_on=state.rag_on,  # #1470
        tone_bands=state.tone_bands,  # #1470
```

- [ ] **Step 4:** run → PASS. Then `uv run pytest tests/unit/test_parser.py tests/parser_corpus/ -q` → no regression (regen corpus snapshot only if it drifts: `--snapshot-update`, then confirm the diff is only `'tone_bands': list([])` defaults).

- [ ] **Step 5:** ruff + mypy clean.

- [ ] **Step 6: commit** `feat(#1470): parse rag_on + tone_bands region keywords`.

---

## Task 3: Validation — `E_RAG_*`

**Files:**
- Modify: `src/dazzle/core/validation/ux.py`
- Modify: `src/dazzle/core/validation/__init__.py`, `src/dazzle/core/validator.py`, `src/dazzle/core/lint.py`
- Test: `tests/unit/test_rag_decorator_validation.py`

**Interfaces — Consumes:** `_NUMERIC_FIELD_KINDS` (in `ux.py` from the comparison slice). **Produces:** `validate_rag_decorators(appspec) -> tuple[list[str], list[str]]`.

Rules: `rag_on` set → (1) `display: list` (`E_RAG_DISPLAY`); (2) `rag_on` names a numeric source field (`E_RAG_NOT_NUMERIC`); (3) non-empty `tone_bands` (`E_RAG_BANDS_REQUIRED`).

- [ ] **Step 1: failing test**

```python
# tests/unit/test_rag_decorator_validation.py
from __future__ import annotations

from pathlib import Path

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.validator import validate_rag_decorators

_HEADER = """module t
app T "T"

entity System "System":
  id: uuid pk
  name: str(40)
  error_rate: decimal(5,2)

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


_BANDS = """    tone_bands:
      - at: 5
        tone: destructive
      - at: 0
        tone: positive
"""


def test_requires_list_display(tmp_path: Path) -> None:
    dsl = """  r:
    source: System
    display: grid
    rag_on: error_rate
""" + _BANDS
    errors, _ = validate_rag_decorators(_appspec(dsl, tmp_path))
    assert any("E_RAG_DISPLAY" in e for e in errors)


def test_must_be_numeric(tmp_path: Path) -> None:
    dsl = """  r:
    source: System
    display: list
    rag_on: name
""" + _BANDS
    errors, _ = validate_rag_decorators(_appspec(dsl, tmp_path))
    assert any("E_RAG_NOT_NUMERIC" in e for e in errors)


def test_requires_bands(tmp_path: Path) -> None:
    dsl = """  r:
    source: System
    display: list
    rag_on: error_rate
"""
    errors, _ = validate_rag_decorators(_appspec(dsl, tmp_path))
    assert any("E_RAG_BANDS_REQUIRED" in e for e in errors)


def test_valid(tmp_path: Path) -> None:
    dsl = """  r:
    source: System
    display: list
    rag_on: error_rate
""" + _BANDS
    errors, _ = validate_rag_decorators(_appspec(dsl, tmp_path))
    assert errors == []
```

- [ ] **Step 2:** run → FAIL (import error).

- [ ] **Step 3: implement.** In `ux.py`, after `validate_insight_summaries` (or `validate_outlier_decorators`), add:

```python
def validate_rag_decorators(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate `rag_on` fixed-band RAG decorators on list regions (#1470)."""
    errors: list[str] = []
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if not region.rag_on:
                continue
            label = f"Workspace '{workspace.name}' region '{region.name or region.source}'"
            if region.display != ir.DisplayMode.LIST:
                errors.append(
                    f"E_RAG_DISPLAY: {label} `rag_on` requires `display: list` "
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
                field = next((f for f in entity.fields if f.name == region.rag_on), None)
            if field is None or field.type.kind not in _NUMERIC_FIELD_KINDS:
                errors.append(
                    f"E_RAG_NOT_NUMERIC: {label} `rag_on: {region.rag_on}` must name a numeric "
                    f"field (int/decimal/float/money) on the source entity."
                )
            if not region.tone_bands:
                errors.append(
                    f"E_RAG_BANDS_REQUIRED: {label} `rag_on` requires a non-empty `tone_bands`."
                )
    return errors, []
```

- [ ] **Step 4: register** (mirror `validate_outlier_decorators` exactly):
  - `validation/__init__.py`: add `validate_rag_decorators` to the `from .ux import (...)` block + `__all__`.
  - `validator.py`: add to the `from .validation import (...)` block + `__all__`.
  - `lint.py`: add to the `from .validator import (...)` block + a call site after the outlier/insight ones:

```python
    # rag_on fixed-band decorator validation (#1470)
    errors, warnings = validate_rag_decorators(appspec)
    all_errors.extend(errors)
    all_warnings.extend(warnings)
```

- [ ] **Step 5:** run → PASS. Spot-check: `cd examples/ops_dashboard && uv run dazzle validate` exit 0; `cd ../simple_task && uv run dazzle validate` exit 0.

- [ ] **Step 6:** ruff + mypy clean; `uv run pytest -m gate -q`.

- [ ] **Step 7: commit** `feat(#1470): validate rag_on decorator (E_RAG_*)`.

---

## Task 4: Orchestration — `build_rag_tones` + ctx wiring

**Files:**
- Modify: `src/dazzle/http/runtime/workspace_region_computes.py` (`build_rag_tones`)
- Modify: `src/dazzle/http/runtime/workspace_region_orchestration.py` (compute branch)
- Modify: `src/dazzle/http/runtime/workspace_region_render.py` (`RegionRenderInputs` + LIST adapter ctx)
- Modify: `src/dazzle/render/fragment/region/_context.py` (TypedDict keys)
- Test: `tests/unit/test_rag_decorator_orchestration.py`

**Interfaces — Produces:** `build_rag_tones(items, *, column, bands) -> list[str | None]` (one tone per item, index-aligned); ctx keys `rag_tones` + `rag_on`.

- [ ] **Step 1: failing test**

```python
# tests/unit/test_rag_decorator_orchestration.py
from dazzle.core.ir.workspaces import ToneBandSpec
from dazzle.http.runtime.workspace_region_computes import build_rag_tones

_BANDS = [
    ToneBandSpec(at=5.0, tone="destructive"),
    ToneBandSpec(at=1.0, tone="warning"),
    ToneBandSpec(at=0.0, tone="positive"),
]


def test_tones_by_band() -> None:
    items = [{"r": 7.0}, {"r": 2.0}, {"r": 0.5}, {"r": -1.0}]
    tones = build_rag_tones(items, column="r", bands=_BANDS)
    assert tones == ["destructive", "warning", "positive", None]  # -1 below all bands


def test_non_finite_and_none() -> None:
    items = [{"r": None}, {"r": float("inf")}, {"r": "x"}, {"r": 3.0}]
    tones = build_rag_tones(items, column="r", bands=_BANDS)
    assert tones == [None, None, None, "warning"]


def test_bands_unsorted_still_descending() -> None:
    # Authoring order shouldn't matter — highest cleared band wins.
    bands = [ToneBandSpec(at=0.0, tone="positive"), ToneBandSpec(at=5.0, tone="destructive")]
    assert build_rag_tones([{"r": 9.0}], column="r", bands=bands) == ["destructive"]
```

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3: implement `build_rag_tones`.** In `workspace_region_computes.py`, after `build_outlier_flags`, add:

```python
def build_rag_tones(
    items: list[dict[str, Any]], *, column: str, bands: list[Any]
) -> list[str | None]:
    """Per-row RAG tone for one column, index-aligned to ``items`` (#1470).

    Reads ``column`` from each item, coercing non-numeric / non-finite / None to
    None (no badge), then maps the value to a band tone: bands are walked in
    descending ``at`` order, the first where ``value >= at`` wins. Below all bands
    (or no value) → None. Pure: runs after the scoped fetch, never widens scope.
    """
    sorted_bands = sorted(bands, key=lambda b: getattr(b, "at", 0.0), reverse=True)
    tones: list[str | None] = []
    for item in items:
        raw = item.get(column) if isinstance(item, dict) else None
        v = _coerce_float(raw)
        tone: str | None = None
        if v is not None and math.isfinite(v):
            for b in sorted_bands:
                if v >= getattr(b, "at", 0.0):
                    tone = getattr(b, "tone", None)
                    break
        tones.append(tone)
    return tones
```

- [ ] **Step 4:** run → PASS.

- [ ] **Step 5: thread through.** Mirror the `outlier_on` wiring exactly:
  - `workspace_region_orchestration.py`: import `build_rag_tones`; after the outlier-decorator compute block, add:

```python
    # RAG decorator (#1470): per-row band tones for one list column.
    rag_on = getattr(ctx.ir_region, "rag_on", None) or ""
    if display == "LIST" and rag_on and not scope_denied:
        rag_tones = build_rag_tones(
            items, column=rag_on, bands=getattr(ctx.ir_region, "tone_bands", None) or []
        )
    else:
        rag_tones = []
        rag_on = ""
```

    then add to the `RegionRenderInputs(...)` construction:

```python
        rag_tones=rag_tones,
        rag_on=rag_on,
```

  - `workspace_region_render.py`: add fields to `RegionRenderInputs` next to `outlier_flags`:

```python
    # #1470 rag_on — per-row band tones + the decorated column key.
    rag_tones: list[Any] = field(default_factory=list)
    rag_on: str = ""
```

    and in `_build_list_adapter_ctx`'s `LIST` branch (next to the outlier keys):

```python
        adapter_ctx["rag_tones"] = inputs.rag_tones
        adapter_ctx["rag_on"] = inputs.rag_on
```

  - `_context.py`: add to the RegionContext TypedDict (next to `outlier_*`):

```python
    # #1470 rag_on — list-column RAG decorator.
    rag_tones: Any
    rag_on: Any
```

- [ ] **Step 6:** `uv run pytest tests/unit/test_rag_decorator_orchestration.py -q` → PASS; ruff + mypy clean.

- [ ] **Step 7: commit** `feat(#1470): rag_on orchestration (band tones -> ctx)`.

---

## Task 5: Render — RAG cell in `_build_list`

**Files:**
- Modify: `src/dazzle/render/fragment/region/_builders_tables.py` (`_build_list` + `_rag_badge`)
- Test: `tests/unit/test_rag_decorator_render.py`

**Interfaces — Consumes:** `ctx["rag_tones"]` (index-aligned to `items`) + `ctx["rag_on"]` (Task 4), `Row`, `RawHTML`, `_render_typed_value`.

- [ ] **Step 1: failing test**

```python
# tests/unit/test_rag_decorator_render.py
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeRegion:
    def __init__(self) -> None:
        self.name = "health"
        self.title = None
        self.display = "list"
        self.empty_message = None
        self.row_action = None


def _render(ctx: dict) -> str:
    return FragmentRenderer().render(WorkspaceRegionAdapter().build(_FakeRegion(), ctx))


def _ctx() -> dict:
    return {
        "items": [{"name": "A", "rate": 7}, {"name": "B", "rate": 0.2}],
        "columns": [{"key": "name", "label": "Name", "type": "text"}, {"key": "rate", "label": "Rate", "type": "text"}],
        "rag_on": "rate",
        "rag_tones": ["destructive", "positive"],
    }


def test_rag_cell_has_band_tone_badge() -> None:
    html = _render(_ctx())
    assert 'data-dz-tone="destructive"' in html
    assert 'data-dz-tone="positive"' in html
    assert "critical" in html and "good" in html  # derived labels
    assert "7" in html and "0.2" in html  # values still render


def test_no_rag_when_unset() -> None:
    ctx = _ctx()
    ctx["rag_on"] = ""
    ctx["rag_tones"] = []
    html = _render(ctx)
    assert "data-dz-tone=" not in html or "destructive" not in html


def test_rag_label_escaping() -> None:
    ctx = _ctx()
    ctx["rag_tones"] = ['"><script>alert(1)</script>', "positive"]
    html = _render(ctx)
    assert "<script>alert(1)</script>" not in html
```

- [ ] **Step 2:** run → FAIL (no rag badge).

- [ ] **Step 3: implement.** In `_builders_tables.py`:

(a) Add the module-level helper near `_outlier_badge`:

```python
_RAG_LABELS = {"positive": "good", "warning": "watch", "destructive": "critical"}


def _rag_badge(tone: str) -> RawHTML:
    """WCAG-safe RAG badge: band tone colour + ● icon + derived label (#1470)."""
    from html import escape as _esc

    label = _RAG_LABELS.get(tone, tone)
    return RawHTML(
        f'<span class="dz-badge dz-badge-sm" data-dz-tone="{_esc(tone, quote=True)}" '
        f'role="status" aria-label="Status: {_esc(label)}">● {_esc(label)}</span>'
    )
```

(b) In `_build_list`, next to the existing `outlier_on`/`outlier_flags` ctx reads, add:

```python
        rag_on = str(ctx.get("rag_on") or "")
        rag_tones = ctx.get("rag_tones") or []
```

  and in the per-item / per-col cell loop, alongside the existing outlier composite-cell branch, add a parallel RAG branch (a column is at most one of outlier_on / rag_on):

```python
                rag_tone = (
                    rag_tones[item_idx]
                    if rag_on and str(col.get("key") or "") == rag_on and item_idx < len(rag_tones)
                    else None
                )
                if flag in ("low", "high") and str(col.get("key") or "") == outlier_on:
                    row_cells.append(Row(children=(value_cell, _outlier_badge(flag)), gap="sm", align="center"))
                elif rag_tone:
                    row_cells.append(Row(children=(value_cell, _rag_badge(str(rag_tone))), gap="sm", align="center"))
                else:
                    row_cells.append(value_cell)
```

  (Replace the existing two-branch outlier `if/else` with this three-branch form; keep `value_cell = _render_typed_value(item, col)` computed above it unchanged.)

- [ ] **Step 4:** run → PASS (3 cases incl. escaping).

- [ ] **Step 5:** ruff + mypy clean; `uv run pytest -m gate -q` + `uv run pytest tests/unit/test_region_adapter.py tests/unit/test_htmx_workspace_composite.py tests/unit/test_outlier_decorator_render.py -q` (complexity + card-safety + no outlier-render regression). If `_build_list` exceeds CC 15, extract the cell-badge choice into a `_list_cell_badge(...)` helper.

- [ ] **Step 6: commit** `feat(#1470): render rag_on band-tone badge in list cells`.

---

## Task 6: Example + catalogue + ship

**Files:**
- Modify: `examples/ops_dashboard/dsl/app.dsl`
- Modify: `fixtures/component_showcase/dsl/app.dsl`, `src/dazzle/testing/ux_catalogue_manifest.py`, `tests/unit/test_ux_catalogue.py`, `docs/reference/ux-catalogue.md` (regen)
- Modify: `CHANGELOG.md`, version files (`/bump`), golden-master snapshot

- [ ] **Step 1: ops_dashboard example.** Add a `rag_on` region (the System list flags `error_rate`):

```dsl
  system_rag:
    source: System
    display: list
    sort: name asc
    rag_on: error_rate
    tone_bands:
      - at: 5
        tone: destructive
      - at: 1
        tone: warning
      - at: 0
        tone: positive
```

  `cd examples/ops_dashboard && uv run dazzle validate` → exit 0.

- [ ] **Step 2: catalogue 10th mode.** Add `cat_rag` to the `ux_catalogue` workspace in `fixtures/component_showcase/dsl/app.dsl` (Box has `error_rate: decimal(5,2)`):

```dsl
  cat_rag:
    source: Box
    display: list
    rag_on: error_rate
    tone_bands:
      - at: 5
        tone: destructive
      - at: 1
        tone: warning
      - at: 0
        tone: positive
```

  Add a `cat_rag` entry to `CATALOGUE_MANIFEST` in `ux_catalogue_manifest.py` with `sample_items` = `_BOXES` (their `error_rate` spans the bands — 0.1..7.2 → green/amber/red) and a description. Add `("cat_rag", "dz-badge")` to the fidelity parametrize in `tests/unit/test_ux_catalogue.py` (verify the marker by a quick render probe first — the RAG badge emits `dz-badge` + `data-dz-tone`). Regenerate the page: `uv run python scripts/gen_ux_catalogue.py`. `uv run pytest tests/unit/test_ux_catalogue.py -q` → PASS (now 10 modes).

- [ ] **Step 3: regen golden-master:** `uv run pytest tests/integration/test_golden_master.py --snapshot-update -q`; re-run PASS; `git diff` shows only `rag_on`/`tone_bands` drift (new fields on regions).

- [ ] **Step 4: full suite:** `uv run pytest tests/ -m "not e2e" -q`. Expect only the 3 `test_fuzzer_oracle` pollution failures. Fix anything else (the validate-drift baseline for ops_dashboard/component_showcase should stay within the warning grace — check `test_dazzle_validate_drift`).

- [ ] **Step 5:** `uv run ruff check src/ tests/ && uv run mypy src/dazzle` clean.

- [ ] **Step 6:** `/bump patch` (6 version lines + `uv lock`). CHANGELOG `### Added` (the `rag_on` fixed-band RAG decorator — closes #1470 item 3) + `### Agent Guidance` (`rag_on` vs `outlier_on`: fixed author bands vs statistical; the descending-`at` first-match rule; tone→label mapping) + the api-surface drift note under `### Changed`.

- [ ] **Step 7: commit + tag + push**, then watch CI + the docs deploy green; confirm the catalogue page now shows 10 modes. Keep `git status` clean (commit `uv.lock`).

---

## Self-review

- **Spec coverage:** IR fields → Task 1; grammar (`rag_on` + `tone_bands` reusing `_parse_tone_bands_block`) → Task 2; validation (`E_RAG_DISPLAY`/`E_RAG_NOT_NUMERIC`/`E_RAG_BANDS_REQUIRED`) → Task 3; pure band-tone pass + ctx wiring → Task 4; composite-cell render with band tone + WCAG badge → Task 5; example + catalogue 10th mode + baselines + ship → Task 6. All spec sections covered.
- **Type consistency:** `WorkspaceRegion.{rag_on: str|None, tone_bands: list[ToneBandSpec]}` (Task 1) → parsed Task 2 → validated Task 3 → read via `ctx.ir_region.{rag_on,tone_bands}` Task 4 → `build_rag_tones(items, column, bands) -> list[str|None]` (Task 4) → `ctx["rag_tones"]`/`ctx["rag_on"]` consumed Task 5. `ToneBandSpec(at, tone)` reused unchanged throughout.
- **Placeholder scan:** the catalogue marker (Task 6 Step 2) is the only verify-against-reality note, flagged with how to confirm (render probe). Everything else is concrete; `_parse_tone_bands_block` reachability confirmed (a `WorkspaceParserMixin` method).
- **Reuse:** `ToneBandSpec`, `_parse_tone_bands_block`, `_coerce_float`, the `outlier_on` registration + render + ctx pattern, and the catalogue harness — all reused; genuinely new code is the two IR fields, `_kw_rag_on`/`_kw_tone_bands`, `validate_rag_decorators`, `build_rag_tones`, and `_rag_badge` + the `_build_list` three-branch cell.

## Notes

- `outlier_on` and `rag_on` are independent columns in the MVP; the `_build_list` cell branch checks outlier first, then rag, then plain — a single column is at most one decorator. If both ever target the same column, outlier wins (documented behaviour; combined RAG+outlier is deferred).
- The RAG badge label is derived from the tone (`positive`→good / `warning`→watch / `destructive`→critical); author-labelled bands are a deferred enhancement.
- Markers in the catalogue fidelity test (`dz-badge`) verified against the actual emitter before pinning.
```
