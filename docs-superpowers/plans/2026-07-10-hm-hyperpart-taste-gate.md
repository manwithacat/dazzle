# HM Hyperpart Taste-Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A live, deterministic, per-component floor gate holding every HM component to token discipline — registered into #1566's design-context so it fills the empty `app_internals × deterministic` matrix cell — plus an on-demand advisory vision command and an authoring-workflow doc.

**Architecture:** A new deterministic rubric `core/component_hygiene.py` (mirrors `core/sitespec_hygiene.py`) scores each `packages/hatchi-maxchi/components/*.css` file on token discipline. It becomes the 4th `RubricRef` in `core/design_context.py`, filling the matrix cell #1566 flagged empty; a `pytest.mark.gate` test enforces a per-component floor. A `dazzle qa component-vision` command reuses the `taste_panel` machinery for an on-demand judged read of a rendered showcase region.

**Tech Stack:** Python 3.12+, frozen dataclasses, `re` for CSS-text scoring, pytest (`-m gate`, DB-free), Typer (`qa` CLI), Playwright (on-demand screenshot only), the existing `taste_panel` + `ux_catalogue` harnesses.

## Global Constraints

- **Live-in-workflow rule** (`docs/architecture/model-driven-failure-modes.md`): the gate must run in `pytest -m gate` + CI, not be documented-only.
- **Deterministic gate is DB-free and render-free** — pure `str -> (float, detail)` CSS-text checks. The judged vision path is on-demand only, never in CI.
- **Clean break, no shims** (ADR-0003).
- **New gate tests carry `pytestmark = pytest.mark.gate`** and stay fast + DB-free.
- **Concept vocabulary is unchanged** — the 4 new component dimensions map to *existing* #1566 concepts (`colour`, `structure`, `motion`, `rhythm`). No new concept.
- **`component_hygiene.py` reads the HM package to measure it** — add it to `test_hm_boundary.py` SANCTIONED (governance, not consumption), exactly like `sitespec_hygiene`.
- **British spelling** `colour` for the concept + dimension key (`colour_tokens`), matching `colour_confidence`.
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/dazzle/core/component_hygiene.py` | **New.** Deterministic per-component token-discipline rubric. |
| `src/dazzle/core/design_context.py` | **Modify.** Add 4th `RubricRef` + 4 concept-dimension mappings; make the empty-cell caveat conditional; add authoring-doc section to `render_markdown`. |
| `docs/reference/hm-design-context.md` | **Regenerate.** Matrix cell filled + authoring section. |
| `tests/unit/test_component_hygiene.py` | **New.** Per-component floor gate + ratchet-band (`pytest.mark.gate`). |
| `tests/unit/test_design_context.py` | **Modify.** 4th rubric: filled cell, 24 dims, component dims claimed. |
| `tests/unit/test_hm_boundary.py` | **Modify.** SANCTIONED += `component_hygiene.py`. |
| `src/dazzle/testing/ux_catalogue.py` | **Modify.** Add `render_region_by_name(name) -> str` helper (render logic stays in the harness). |
| `src/dazzle/qa/component_vision.py` | **New.** On-demand render→screenshot→score glue (reuses `taste_panel`). |
| `src/dazzle/cli/qa.py` | **Modify.** Add `qa component-vision` subcommand. |
| `tests/unit/test_component_vision.py` | **New.** Mocked-judge + mocked-capture glue test. |

The 4 component dimensions and their concept homes (locked so tasks agree):

| Dimension (`component.<key>`) | Weight | Concept |
|---|---|---|
| `colour_tokens` | 40 | `colour` |
| `namespace` | 20 | `structure` |
| `motion_tokens` | 20 | `motion` |
| `sizing_tokens` | 20 | `rhythm` |

---

## Task 1: `core/component_hygiene.py` — the deterministic rubric

**Files:**
- Create: `src/dazzle/core/component_hygiene.py`
- Create: `tests/unit/test_component_hygiene_scoring.py` (behaviour unit tests — separate from the floor gate in Task 3)
- Modify: `tests/unit/test_hm_boundary.py` (SANCTIONED set)

**Interfaces:**
- Produces:
  - `ComponentDimension(key: str, weight: int, description: str, check: Callable[[str], tuple[float, str]])` — frozen dataclass.
  - `COMPONENT_HYGIENE_DIMENSIONS: tuple[ComponentDimension, ...]` — 4 dims, weights sum 100.
  - `score_component_css(css: str) -> dict[str, object]` — `{"total": float, "breakdown": {key: {sub_score, weight, points, detail}}}` (same shape as `score_sitespec_css`).
  - `hm_component_paths() -> list[Path]` — sorted `packages/hatchi-maxchi/components/*.css`.

- [ ] **Step 1: Write the failing scoring tests**

Create `tests/unit/test_component_hygiene_scoring.py`:

```python
"""#1567 — behaviour of the deterministic component token-discipline rubric."""

import pytest

from dazzle.core.component_hygiene import (
    COMPONENT_HYGIENE_DIMENSIONS,
    hm_component_paths,
    score_component_css,
)

pytestmark = pytest.mark.gate


def test_weights_sum_to_100() -> None:
    assert sum(d.weight for d in COMPONENT_HYGIENE_DIMENSIONS) == 100


def test_perfect_token_css_scores_high() -> None:
    css = (
        ".dz-x{color:var(--dz-ink);background:var(--dz-surface);"
        "transition:opacity var(--dz-transition-fast);border-radius:var(--dz-radius);"
        "padding:var(--dz-space-2);gap:0.5rem}"
    )
    result = score_component_css(css)
    assert result["total"] >= 95.0


def test_raw_hex_colour_drops_colour_score() -> None:
    css = ".dz-x{color:#ff0000;background:#00ff00}"
    result = score_component_css(css)
    breakdown = result["breakdown"]  # type: ignore[index]
    assert breakdown["colour_tokens"]["sub_score"] == 0.0


def test_non_dz_selectors_drop_namespace_score() -> None:
    css = ".widget{color:var(--dz-ink)} .panel{color:var(--dz-ink)}"
    result = score_component_css(css)
    breakdown = result["breakdown"]  # type: ignore[index]
    assert breakdown["namespace"]["sub_score"] == 0.0


def test_raw_px_sizing_drops_sizing_score() -> None:
    css = ".dz-x{padding:12px;border-radius:4px}"
    result = score_component_css(css)
    breakdown = result["breakdown"]  # type: ignore[index]
    assert breakdown["sizing_tokens"]["sub_score"] == 0.0


def test_absent_properties_score_na_as_one() -> None:
    # A pure-layout component with no colour/motion/sizing scores those n/a = 1.0.
    css = ".dz-x{display:flex}"
    result = score_component_css(css)
    assert result["total"] == 100.0


def test_hm_component_paths_finds_the_corpus() -> None:
    paths = hm_component_paths()
    assert len(paths) >= 50
    assert all(p.suffix == ".css" for p in paths)
    assert any(p.name == "button.css" for p in paths)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_component_hygiene_scoring.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.core.component_hygiene'`.

- [ ] **Step 3: Write `core/component_hygiene.py`**

Create `src/dazzle/core/component_hygiene.py`:

```python
"""Deterministic per-component token-discipline rubric (#1567).

The LIVE half of the Hyperpart taste-gate: a cheap, render-free, DB-free score of
whether an HM component (`packages/hatchi-maxchi/components/*.css`) delegates to the
house token system rather than spraying raw values. It is the deterministic
app-internals rubric that `core/design_context.py`'s matrix flagged as its one empty
cell (#1566) — registered there as the 4th rubric.

Mirrors `core/sitespec_hygiene.py`: each dimension is a pure `str -> (0..1, detail)`
check; the weighted total is 0-100. Absence of a property class (a pure-layout
component with no colour declarations) scores that dimension 1.0 ("n/a") — absence is
not a violation.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "COMPONENT_HYGIENE_DIMENSIONS",
    "ComponentDimension",
    "hm_component_paths",
    "score_component_css",
]

_RAW_COLOUR = r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\("

_COLOUR_DECL_RE = re.compile(
    r"(?:color|background|background-color|border-color|outline-color|fill|stroke)\s*:\s*([^;{}]+)",
    re.I,
)


def _score_colour_tokens(css: str) -> tuple[float, str]:
    """Colours come from `var(--…)` tokens, not raw hex/rgb/hsl. Score = fraction of
    colour-bearing declarations that are token-driven (var, no raw literal)."""
    vals = [v.strip() for v in _COLOUR_DECL_RE.findall(css)]
    coloured = [v for v in vals if re.search(rf"var\(--|{_RAW_COLOUR}", v)]
    if not coloured:
        return (1.0, "no literal colour declarations (n/a)")
    tok = sum(1 for v in coloured if "var(" in v and not re.search(_RAW_COLOUR, v))
    raw = len(coloured) - tok
    return (tok / len(coloured), f"{tok}/{len(coloured)} colour decls token-driven; {raw} raw")


def _score_namespace(css: str) -> tuple[float, str]:
    """Selectors use the `.dz-` namespace (HM convention). Score = fraction of class
    selectors that are `.dz-`-prefixed."""
    classes = re.findall(r"\.([a-zA-Z][\w-]*)", css)
    if not classes:
        return (1.0, "no class selectors (n/a)")
    dz = sum(1 for c in classes if c.startswith("dz-"))
    return (dz / len(classes), f"{dz}/{len(classes)} class selectors .dz-namespaced")


_MOTION_DECL_RE = re.compile(r"(?:transition|animation)(?:-[a-z]+)?\s*:\s*([^;{}]+)", re.I)


def _score_motion_tokens(css: str) -> tuple[float, str]:
    """Motion timing comes from `var(--dz-transition…)` tokens, not inline durations.
    Score = fraction of transition/animation declarations referencing a var() token."""
    vals = [v.strip() for v in _MOTION_DECL_RE.findall(css)]
    if not vals:
        return (1.0, "no transition/animation declarations (n/a)")
    tok = sum(1 for v in vals if "var(" in v)
    return (tok / len(vals), f"{tok}/{len(vals)} motion decls token-driven")


_SIZE_DECL_RE = re.compile(
    r"(?:border-radius|padding|margin|gap|row-gap|column-gap)(?:-[a-z]+)?\s*:\s*([^;{}]+)",
    re.I,
)
_PX_RE = re.compile(r"\d*\.?\d+px\b")


def _score_sizing_tokens(css: str) -> tuple[float, str]:
    """Radius/spacing come from tokens or rem/em, not raw px. Score = fraction of
    sized radius/spacing declarations that are px-free."""
    vals = [v.strip() for v in _SIZE_DECL_RE.findall(css)]
    sized = [v for v in vals if re.search(r"var\(--|\d", v)]
    if not sized:
        return (1.0, "no sized spacing/radius declarations (n/a)")
    good = sum(1 for v in sized if not _PX_RE.search(v))
    px = len(sized) - good
    return (good / len(sized), f"{good}/{len(sized)} sizing decls px-free; {px} use px")


@dataclass(frozen=True)
class ComponentDimension:
    """One deterministic component token-discipline dimension."""

    key: str
    weight: int  # contribution to the /100 total
    description: str
    check: Callable[[str], tuple[float, str]]


# Weights sum to 100. Colour discipline is weighted highest — it is the clearest and
# most-varying token-discipline signal across the corpus.
COMPONENT_HYGIENE_DIMENSIONS: tuple[ComponentDimension, ...] = (
    ComponentDimension(
        "colour_tokens", 40, "Colours from var(--…) tokens, not raw hex/rgb", _score_colour_tokens
    ),
    ComponentDimension("namespace", 20, "Selectors use the .dz- namespace", _score_namespace),
    ComponentDimension(
        "motion_tokens", 20, "Motion timing from --dz-transition tokens", _score_motion_tokens
    ),
    ComponentDimension(
        "sizing_tokens", 20, "Radius/spacing from tokens or rem, not raw px", _score_sizing_tokens
    ),
)


def hm_component_paths() -> list[Path]:
    """The HM component CSS files under measurement, sorted by name."""
    root = Path(__file__).resolve().parents[3]
    comp_dir = root / "packages" / "hatchi-maxchi" / "components"
    return sorted(comp_dir.glob("*.css"))


def score_component_css(css: str) -> dict[str, object]:
    """Score one component's CSS against the token-discipline rubric. Returns the
    weighted /100 total plus a per-dimension breakdown (sub-score, points, detail)."""
    breakdown: dict[str, dict[str, object]] = {}
    total = 0.0
    for d in COMPONENT_HYGIENE_DIMENSIONS:
        sub, detail = d.check(css)
        sub = max(0.0, min(1.0, sub))
        pts = sub * d.weight
        total += pts
        breakdown[d.key] = {
            "sub_score": round(sub, 3),
            "weight": d.weight,
            "points": round(pts, 1),
            "detail": detail,
        }
    return {"total": round(total, 1), "breakdown": breakdown}
```

- [ ] **Step 4: Run the scoring tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_component_hygiene_scoring.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Sanction the module in the HM-boundary scan**

In `tests/unit/test_hm_boundary.py`, add to the `SANCTIONED` set (after the `sitespec_hygiene.py` entry):

```python
    # Component token-discipline rubric reads the HM component CSS to *measure*
    # its house-token delegation (the #1567 deterministic Hyperpart gate).
    "src/dazzle/core/component_hygiene.py",
```

- [ ] **Step 6: Run the boundary gate + lint + type**

Run: `.venv/bin/python -m pytest tests/unit/test_hm_boundary.py -q`
Expected: PASS.
Run: `.venv/bin/ruff check src/dazzle/core/component_hygiene.py tests/unit/test_component_hygiene_scoring.py --fix && .venv/bin/ruff format src/dazzle/core/component_hygiene.py tests/unit/test_component_hygiene_scoring.py`
Run: `.venv/bin/mypy src/dazzle/core/component_hygiene.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/core/component_hygiene.py tests/unit/test_component_hygiene_scoring.py \
  tests/unit/test_hm_boundary.py
git commit -m "feat: deterministic component token-discipline rubric (#1567)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Register the rubric into #1566's design-context (+ authoring doc)

**Files:**
- Modify: `src/dazzle/core/design_context.py`
- Modify: `tests/unit/test_design_context.py`
- Regenerate: `docs/reference/hm-design-context.md`

**Interfaces:**
- Consumes: `dazzle.core.component_hygiene.COMPONENT_HYGIENE_DIMENSIONS`.
- Produces: `RUBRICS` now length 4; `matrix()[("app_internals","deterministic")]` is the `component` rubric; `all_dimension_ids()` returns 24 ids; `render_markdown()` includes the filled cell + an "Authoring a new Hyperpart" section.

- [ ] **Step 1: Update the design-context tests to the 4-rubric world (failing)**

In `tests/unit/test_design_context.py`, make these edits:

Add the component dimensions to the concept expectations by updating `test_matrix_is_well_formed` (line ~71):

```python
    assert m[("app_internals", "deterministic")].name == "component"
```
(replacing the old `assert m[("app_internals", "deterministic")] is None`).

Update `test_accessor_shapes` (lines ~83-85):

```python
    assert len(RUBRICS) == 4
    # 24 dimensions total across the four rubrics
    assert len(all_dimension_ids()) == 24
```

Add a focused test for the newly-filled cell + mappings:

```python
def test_component_rubric_fills_the_deterministic_app_cell() -> None:
    from dazzle.core.design_context import dimensions_for, method_of, surface_of

    for key in ("colour_tokens", "namespace", "motion_tokens", "sizing_tokens"):
        qid = f"component.{key}"
        assert method_of(qid) == "deterministic"
        assert surface_of(qid) == "app_internals"
    assert "component.colour_tokens" in dimensions_for("colour")
    assert "component.namespace" in dimensions_for("structure")
    assert "component.motion_tokens" in dimensions_for("motion")
    assert "component.sizing_tokens" in dimensions_for("rhythm")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/unit/test_design_context.py -q`
Expected: FAIL (RUBRICS is 3, cell is None, component dims unclaimed).

- [ ] **Step 3: Add the 4th rubric + concept mappings in `design_context.py`**

In `src/dazzle/core/design_context.py`:

Add the import near the other rubric imports:

```python
from dazzle.core.component_hygiene import COMPONENT_HYGIENE_DIMENSIONS
```

Append the 4th `RubricRef` to `RUBRICS` (after the `taste` entry):

```python
    RubricRef(
        "component",
        "app_internals",
        "deterministic",
        tuple(d.key for d in COMPONENT_HYGIENE_DIMENSIONS),
    ),
```

Extend the mapped concepts. Add `component.*` dimensions to the existing `colour`, `structure`, `motion`, `rhythm` `DesignConcept` entries — append to each concept's `dimensions` tuple:
- `colour`: add `"component.colour_tokens"`
- `structure`: add `"component.namespace"`
- `motion`: add `"component.motion_tokens"`
- `rhythm`: add `"component.sizing_tokens"`

For example the `motion` concept becomes:

```python
    DesignConcept(
        "motion",
        "Subtle, consistent, token-driven motion that reads as considered.",
        ("hygiene.motion", "component.motion_tokens"),
    ),
```

Add the source label for the rubric-sources section:

```python
_RUBRIC_SOURCE = {
    "hygiene": "`core/sitespec_hygiene.py`",
    "vision": "`core/sitespec_vision_rubric.py`",
    "taste": "`core/taste_rubric.py`",
    "component": "`core/component_hygiene.py`",
}
```

- [ ] **Step 4: Make the empty-cell caveat conditional + add the authoring section in `render_markdown`**

In `render_markdown()`, replace the unconditional empty-cell caveat block with a conditional one (only emit when some cell is genuinely `None`):

```python
    if any(v is None for v in m.values()):
        lines.append(
            "> Cells marked “— (none today)” have no rubric yet — shown so the "
            "gap is visible, not hidden."
        )
        lines.append("")
```

At the very end of `render_markdown()` (after the rubric-sources loop, before `return`), append the authoring section:

```python
    lines.append("## Authoring a new Hyperpart")
    lines.append("")
    lines.append(
        "1. Use HM tokens (`var(--dz-…)`), the `.dz-` namespace, and `--dz-transition*` "
        "for motion. The **component-discipline floor** "
        "(`tests/unit/test_component_hygiene.py`) scores every component on this and "
        "fails a new one that sprays raw values."
    )
    lines.append(
        "2. If your component renders a card or region, the **card-safety composite gate** "
        "(`tests/unit/test_htmx_workspace_composite.py`) covers its rendered DOM "
        "automatically."
    )
    lines.append(
        "3. For a judged “does it look right” read, run "
        "`dazzle qa component-vision <name>` (on-demand, advisory, subscription-billed)."
    )
    lines.append("")
```

- [ ] **Step 5: Regenerate the doc + run the design-context tests**

Run: `.venv/bin/python scripts/gen_design_context.py`
Expected: `WROTE: …/docs/reference/hm-design-context.md`.
Run: `.venv/bin/python -m pytest tests/unit/test_design_context.py -q`
Expected: PASS (claim-integrity now covers 24 dims; matrix cell filled; doc current).

- [ ] **Step 6: Confirm the doc shows the filled cell + authoring section**

Run: `grep -n "component_hygiene\|Authoring a new Hyperpart\|none today" docs/reference/hm-design-context.md`
Expected: the App-internals row's deterministic column names `core/component_hygiene.py (4 dims)`; the "Authoring a new Hyperpart" heading present; **no** "none today" line (all cells filled).

- [ ] **Step 7: Lint + type + commit**

Run: `.venv/bin/ruff check src/dazzle/core/design_context.py tests/unit/test_design_context.py --fix && .venv/bin/ruff format src/dazzle/core/design_context.py tests/unit/test_design_context.py`
Run: `.venv/bin/mypy src/dazzle/core/design_context.py`
Expected: clean.

```bash
git add src/dazzle/core/design_context.py tests/unit/test_design_context.py \
  docs/reference/hm-design-context.md
git commit -m "feat: register component rubric into design-context, fill empty cell (#1567)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: The per-component floor gate

**Files:**
- Create: `tests/unit/test_component_hygiene.py`

**Interfaces:**
- Consumes: `hm_component_paths()`, `score_component_css()` from Task 1.

- [ ] **Step 1: Measure the corpus minimum to set FLOOR**

Run this to see the weakest component and the corpus min:

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0,'src')
from dazzle.core.component_hygiene import hm_component_paths, score_component_css
scored = sorted((score_component_css(p.read_text())['total'], p.name) for p in hm_component_paths())
for total, name in scored[:8]:
    print(f'{total:6.1f}  {name}')
print('CORPUS MIN =', scored[0][0])
"
```

Note the `CORPUS MIN`. Set `FLOOR` in the test to the largest multiple of 5 that is `<= floor(CORPUS_MIN) - 2` (a small margin below the current weakest, so the gate holds the line without being brittle). Example: if `CORPUS MIN = 88.0`, `FLOOR = 85.0`.

**If `CORPUS MIN` is surprisingly low (< 70)** for a real component, do not just lower the floor — read that component; a genuinely undisciplined existing component is a finding worth a one-line note in the commit body (and possibly a quick token fix), not a floor you bury. Use judgement; the gate exists to hold the standard, not to rubber-stamp the current state.

- [ ] **Step 2: Write the floor gate (with the measured FLOOR)**

Create `tests/unit/test_component_hygiene.py`:

```python
"""#1567 — the LIVE Hyperpart taste-gate: every HM component must clear the
deterministic token-discipline floor. A new component is scored automatically and
fails here if it sprays raw values instead of delegating to HM tokens."""

import pytest

from dazzle.core.component_hygiene import hm_component_paths, score_component_css

pytestmark = pytest.mark.gate

# The per-component token-discipline floor (out of 100). Set just below the current
# corpus minimum (Step 1). Raise it as the corpus improves so gains ratchet in.
FLOOR = 85.0  # <-- replace with the value measured in Step 1


@pytest.mark.parametrize("path", hm_component_paths(), ids=lambda p: p.name)
def test_component_clears_the_floor(path) -> None:
    result = score_component_css(path.read_text(encoding="utf-8"))
    total = result["total"]
    if total < FLOOR:
        weakest = min(
            result["breakdown"].items(), key=lambda kv: kv[1]["sub_score"]
        )
        pytest.fail(
            f"{path.name} scores {total} < floor {FLOOR}. "
            f"Weakest: {weakest[0]} ({weakest[1]['detail']}). "
            f"Use HM var(--dz-…) tokens instead of raw values."
        )


def test_floor_is_a_real_ratchet() -> None:
    # Guard against someone quietly zeroing the gate's teeth.
    assert 70.0 <= FLOOR <= 100.0
```

- [ ] **Step 3: Run the floor gate**

Run: `.venv/bin/python -m pytest tests/unit/test_component_hygiene.py -q`
Expected: PASS (every component clears FLOOR; the ratchet-band holds).

- [ ] **Step 4: Confirm the whole gate set is still green**

Run: `.venv/bin/python -m pytest tests/unit -m gate -q`
Expected: PASS (no regression in the broader gate set).

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_component_hygiene.py
git commit -m "test: per-component token-discipline floor gate (#1567)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `dazzle qa component-vision` (on-demand advisory)

**Files:**
- Modify: `src/dazzle/testing/ux_catalogue.py` (add `render_region_by_name`)
- Create: `src/dazzle/qa/component_vision.py`
- Modify: `src/dazzle/cli/qa.py` (add subcommand)
- Create: `tests/unit/test_component_vision.py`

**Interfaces:**
- Consumes: `ux_catalogue.load_showcase_appspec/iter_catalogue_regions/render_catalogue_region`, `taste_panel.PanelImage/score_image`, `taste_rubric` via `build_sitespec_judge_prompt`/`build_judge_prompt`.
- Produces:
  - `ux_catalogue.render_region_by_name(name: str) -> str` — HTML for the named showcase region (raises `KeyError` if unknown).
  - `ux_catalogue.showcase_region_names() -> list[str]` — the available region names.
  - `component_vision.score_component_region(name: str, *, judges: int, model: str, capture, client) -> dict` — render→screenshot→score glue; `capture` and `client` injectable for tests.

- [ ] **Step 1: Add the render-by-name helper to the harness (failing test)**

Create `tests/unit/test_component_vision.py` (first test targets the harness helper):

```python
"""#1567 — the on-demand component-vision glue (render→score), mocked heavy parts."""

import pytest

from dazzle.testing.ux_catalogue import render_region_by_name, showcase_region_names

pytestmark = pytest.mark.gate


def test_showcase_region_names_nonempty() -> None:
    names = showcase_region_names()
    assert names
    assert "cat_list" in names


def test_render_region_by_name_returns_html() -> None:
    html = render_region_by_name("cat_list")
    assert "<" in html and len(html) > 50


def test_render_region_by_name_unknown_raises() -> None:
    with pytest.raises(KeyError):
        render_region_by_name("no_such_region")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/unit/test_component_vision.py -q`
Expected: FAIL (`ImportError: cannot import name 'render_region_by_name'`).

- [ ] **Step 3: Implement the harness helpers**

In `src/dazzle/testing/ux_catalogue.py`, add to `__all__` (`"render_region_by_name"`, `"showcase_region_names"`) and add these functions (reusing the existing per-region render path that `generate_catalogue_markdown` already walks — read that function to mirror how it builds the `entry` dict for each region):

```python
def _region_entries() -> dict[str, tuple]:
    """Map showcase region name -> (appspec, ir_region, ctx_region, entry) using the
    same demo-data assembly as generate_catalogue_markdown."""
    appspec = load_showcase_appspec()
    out: dict[str, tuple] = {}
    for ir_region, ctx_region in iter_catalogue_regions(appspec):
        entry = _catalogue_entry_for(ir_region)  # existing demo-data lookup used by the markdown generator
        out[ir_region.name] = (appspec, ir_region, ctx_region, entry)
    return out


def showcase_region_names() -> list[str]:
    """Names of the renderable showcase regions (the component-vision targets)."""
    return sorted(_region_entries().keys())


def render_region_by_name(name: str) -> str:
    """Render one showcase region to HTML by name. Raises KeyError if unknown."""
    entries = _region_entries()
    if name not in entries:
        raise KeyError(f"unknown showcase region {name!r}; have: {sorted(entries)}")
    appspec, ir_region, ctx_region, entry = entries[name]
    return render_catalogue_region(appspec, ir_region, ctx_region, entry)
```

**Implementation note:** `generate_catalogue_markdown` (lines ~244-280) already assembles the `entry` dict per region — extract that lookup into `_catalogue_entry_for(ir_region)` and call it from both `generate_catalogue_markdown` and `_region_entries` (DRY; the markdown generator must stay byte-identical, so `test_ux_catalogue` still passes). If the entry is sourced inline from a fixture dict keyed by region name, reuse that dict directly instead of a new helper.

- [ ] **Step 4: Run the harness tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_component_vision.py -q`
Expected: PASS. Also confirm the catalogue generator is unbroken:
Run: `.venv/bin/python -m pytest tests/unit/test_ux_catalogue.py -q`
Expected: PASS.

- [ ] **Step 5: Write the scoring-glue test (mocked capture + judge)**

Append to `tests/unit/test_component_vision.py`:

```python
def test_score_component_region_glue(tmp_path) -> None:
    from dazzle.qa.component_vision import score_component_region

    captured = {}

    def fake_capture(html: str, out_png):
        captured["html"] = html
        out_png.write_bytes(b"\x89PNG\r\n\x1a\n fake")  # any bytes; judge is mocked
        return out_png

    class FakeJudge:
        def score(self, image, *, judge, repeat=0, model, client=None):
            from dazzle.qa.taste_panel import JudgeScore

            return [JudgeScore(image_id=image.image_id, judge=judge, scores={"finish_polish": 7})]

    result = score_component_region(
        "cat_list",
        judges=1,
        model="fake-model",
        capture=fake_capture,
        score_fn=FakeJudge().score,
        out_dir=tmp_path,
    )
    assert captured["html"]  # render happened
    assert result["region"] == "cat_list"
    assert "scores" in result


def test_score_component_region_unknown_raises(tmp_path) -> None:
    from dazzle.qa.component_vision import score_component_region

    with pytest.raises(KeyError):
        score_component_region("nope", judges=1, model="x", out_dir=tmp_path)
```

(Match the real `JudgeScore` field names when writing this — read `taste_panel.py` `JudgeScore` before finalising; adjust the fake to its actual constructor.)

- [ ] **Step 6: Implement `qa/component_vision.py`**

Create `src/dazzle/qa/component_vision.py`. It renders the region, wraps it in a minimal HTML doc with the catalogue CSS, screenshots via an injectable `capture` (default: a Playwright helper), scores via an injectable `score_fn` (default: `taste_panel.score_image` with a real client), and returns an advisory dict. Read `taste_panel.score_image`/`PanelImage`/`aggregate_scores` and the vision-pilot capture approach (`scripts/taste/capture_sitespec_references.py`) to fill in the real defaults. Structure:

```python
"""On-demand component vision score (#1567) — advisory, not a gate.

Renders a showcase region, screenshots it, and scores the image with the taste
vision panel. Subscription/API-billed; exit-0 always at the CLI. The heavy parts
(screenshot capture, judge client) are injectable so the glue is unit-testable.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from dazzle.core.model_defaults import DEFAULT_JUDGMENT_MODEL
from dazzle.qa.taste_panel import PanelImage, score_image
from dazzle.testing.ux_catalogue import generate_catalogue_css, render_region_by_name

__all__ = ["score_component_region"]


def _default_capture(html: str, out_png: Path) -> Path:
    """Screenshot rendered HTML at 1440x1024 via Playwright (import-local so the
    dependency only loads on the real path, never in unit tests)."""
    from playwright.sync_api import sync_playwright

    doc = f"<!doctype html><html><head><style>{generate_catalogue_css()}</style></head><body>{html}</body></html>"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1024})
        page.set_content(doc, wait_until="networkidle")
        page.screenshot(path=str(out_png), full_page=False)
        browser.close()
    return out_png


def score_component_region(
    name: str,
    *,
    judges: int = 3,
    model: str = DEFAULT_JUDGMENT_MODEL,
    out_dir: Path = Path(".dazzle/qa/component-vision"),
    capture: Callable[[str, Path], Path] = _default_capture,
    score_fn: Callable[..., list] = score_image,
    client: Any | None = None,
) -> dict[str, object]:
    """Render `name`, screenshot it, score it. Raises KeyError on an unknown region."""
    html = render_region_by_name(name)  # KeyError if unknown — surfaces as a usage error
    out_dir.mkdir(parents=True, exist_ok=True)
    png = capture(html, out_dir / f"{name}.png")
    image = PanelImage(
        image_id=name, source="dazzle", label=name, path=png, theme="light"
    )
    all_scores: list = []
    for j in range(judges):
        all_scores.extend(score_fn(image, judge=j, model=model, client=client))
    # aggregate to a simple per-dimension mean for the advisory report
    agg: dict[str, float] = {}
    counts: dict[str, int] = {}
    for js in all_scores:
        for dim, val in getattr(js, "scores", {}).items():
            agg[dim] = agg.get(dim, 0.0) + val
            counts[dim] = counts.get(dim, 0) + 1
    means = {d: round(agg[d] / counts[d], 2) for d in agg}
    return {"region": name, "judges": judges, "model": model, "scores": means, "image": str(png)}
```

- [ ] **Step 7: Add the CLI subcommand in `qa.py`**

In `src/dazzle/cli/qa.py`, add after the `taste-panel` command (~line 1115):

```python
@qa_app.command("component-vision")
def qa_component_vision(
    name: str = typer.Argument(..., help="Showcase region name, e.g. cat_list"),
    judges: int = typer.Option(3, "--judges", help="Independent judge passes"),
    model: str | None = typer.Option(None, "--model", help="Override judge model"),
    out: Path = typer.Option(
        Path(".dazzle/qa/component-vision"), "--out", help="Report output dir"
    ),
) -> None:
    """On-demand advisory vision score for one HM component (rendered showcase region).

    Subscription/API-billed. Advisory only — always exits 0 on a successful score.
    """
    import json

    from dazzle.core.model_defaults import DEFAULT_JUDGMENT_MODEL
    from dazzle.qa.component_vision import score_component_region
    from dazzle.testing.ux_catalogue import showcase_region_names

    try:
        result = score_component_region(
            name, judges=judges, model=model or DEFAULT_JUDGMENT_MODEL, out_dir=out
        )
    except KeyError:
        typer.echo(
            f"No showcase region {name!r}. Available: {', '.join(showcase_region_names())}",
            err=True,
        )
        raise typer.Exit(code=2) from None

    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    typer.echo(json.dumps(result["scores"], indent=2))
    typer.echo(f"Advisory score for {name} — report: {out / (name + '.json')}")
```

- [ ] **Step 8: Run the glue tests + lint + type**

Run: `.venv/bin/python -m pytest tests/unit/test_component_vision.py -q`
Expected: PASS.
Run: `.venv/bin/ruff check src/dazzle/qa/component_vision.py src/dazzle/cli/qa.py src/dazzle/testing/ux_catalogue.py tests/unit/test_component_vision.py --fix && .venv/bin/ruff format src/dazzle/qa/component_vision.py src/dazzle/cli/qa.py src/dazzle/testing/ux_catalogue.py tests/unit/test_component_vision.py`
Run: `.venv/bin/mypy src/dazzle/qa/component_vision.py src/dazzle/testing/ux_catalogue.py`
Expected: clean.

- [ ] **Step 9: Smoke the CLI wiring (no real judge)**

Run: `.venv/bin/dazzle qa component-vision no_such_region 2>&1 | head -2`
Expected: prints "No showcase region … Available: cat_list, …" and exits non-zero. (Confirms the command is wired without a real API call.)

- [ ] **Step 10: Commit**

```bash
git add src/dazzle/qa/component_vision.py src/dazzle/cli/qa.py \
  src/dazzle/testing/ux_catalogue.py tests/unit/test_component_vision.py
git commit -m "feat: dazzle qa component-vision on-demand advisory (#1567)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Ship + close scope-1

**Files:**
- Modify: `CHANGELOG.md`, version files (via `/bump`).

- [ ] **Step 1: CHANGELOG entry under Unreleased**

```markdown
### Added
- **HM Hyperpart taste-gate (#1567, slice 1)** — `core/component_hygiene.py`, a
  deterministic per-component token-discipline rubric (colour/namespace/motion/sizing
  from HM tokens), registered as the 4th rubric in `core/design_context.py` — filling
  the `app_internals × deterministic` matrix cell #1566 flagged empty. A per-component
  floor gate (`tests/unit/test_component_hygiene.py`) holds every component to the
  standard and auto-covers new ones. New advisory command `dazzle qa component-vision
  <region>` gives an on-demand judged read of a rendered showcase region.

### Agent Guidance
- Authoring a new HM Hyperpart? Use `var(--dz-…)` tokens, the `.dz-` namespace, and
  `--dz-transition*` — the component-discipline floor enforces it on every commit. See
  the "Authoring a new Hyperpart" section in `docs/reference/hm-design-context.md`.
```

- [ ] **Step 2: Bump + ship**

Run: `/bump patch`
Run: `/ship` (lint + mypy + `-m gate` + `mkdocs --strict`, commit, tag, push).

- [ ] **Step 3: Monitor CI to green**

Run: `gh run list --branch main --limit 3`
Watch the `ci.yml` run to `success`; fix + re-push on real red, note unrelated flake.

- [ ] **Step 4: Comment on #1567 — slice 1 shipped, leave open for slice 2**

```bash
gh issue comment 1567 --body "$(cat <<'EOF'
**Slice 1 shipped** (the Hyperpart taste-gate). `core/component_hygiene.py` is a
deterministic per-component token-discipline rubric (colour/namespace/motion/sizing from
HM tokens), now the 4th rubric in the #1566 design-context — it fills the
`app_internals × deterministic` matrix cell that was flagged empty. A per-component floor
gate (`tests/unit/test_component_hygiene.py`, `-m gate`) holds every component to the
standard and auto-covers new ones; card-safety already covers rendered DOM via the
composite gate. New advisory `dazzle qa component-vision <region>` gives an on-demand
judged read.

**Left open for slice 2:** the new-property authoring path (family pick/author against
exemplars + auto-score) — affordance 2, to be brainstormed into its own spec.

Spec: `docs/superpowers/specs/2026-07-10-hm-hyperpart-taste-gate-design.md`.

🔖 Claude-lens: dazzle
EOF
)"
```

Do **not** close #1567 — slice 2 keeps it open.

---

## Self-Review

**1. Spec coverage:**
- Part A (component_hygiene rubric) → Task 1. ✓
- Part B (register into design-context, fill cell, regen doc) → Task 2. ✓
- Part C (per-component floor gate) → Task 3. ✓
- Part D (qa component-vision advisory) → Task 4. ✓
- Part E (authoring doc section) → Task 2 Step 4 (emitted by `render_markdown`). ✓
- Boundary sanction → Task 1 Step 5. ✓
- Deferred affordance-2, #1567 left open → Task 5 Step 4. ✓

**2. Placeholder scan:** `FLOOR = 85.0` is a measured constant (Task 3 Step 1 sets it) with an explicit measurement command and judgement note — not a placeholder. The `_catalogue_entry_for` helper in Task 4 Step 3 is flagged as "read `generate_catalogue_markdown` and extract/reuse its existing per-region entry lookup" with a concrete fallback — grounded, not hand-wave. No TBD/TODO.

**3. Type consistency:** `score_component_css -> dict` shape matches across Tasks 1/3. `hm_component_paths -> list[Path]` used in Tasks 1/3. `render_region_by_name(name)->str` / `showcase_region_names()->list[str]` defined Task 4 Step 3, consumed in Steps 5-7. `score_component_region(name, *, judges, model, out_dir, capture, score_fn, client)` defined Step 6, consumed by the test (Step 5) and CLI (Step 7) — the test injects `capture`/`score_fn`, the CLI uses defaults; signatures align. `PanelImage(image_id, source, label, path, theme)` matches the dataclass read from `taste_panel.py`.

**Note on Task 4 risk:** the vision command depends on Playwright + a real judge client on its live path; only the glue is unit-tested (heavy parts injected/mocked), and the real path is verified once manually during implementation. It is advisory (exit 0), so a fiddly live path never blocks the deterministic gate — the actual value of this slice (Tasks 1-3) ships regardless. If Task 4 proves disproportionately fiddly, it is the one task safe to split into an immediate follow-up without weakening the gate.
