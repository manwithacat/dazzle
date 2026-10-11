# HM Design-Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify Dazzle's three HM design-quality rubrics (deterministic sitespec-hygiene, judged sitespec-vision, judged app-internals taste) behind one agent-readable, drift-gated "design-context".

**Architecture:** A thin facade layer over the three rubrics — it does not change their shapes or scoring. `core/design_context.py` names a canonical concept vocabulary, maps every rubric dimension to exactly one concept, and lays the three rubrics on a surface × method matrix. A generator renders that module to `docs/reference/hm-design-context.md`; a hard claim-integrity gate keeps concept ↔ dimension coverage honest as the rubrics evolve. To let the facade import all three rubrics without a `core → testing` layer violation, `sitespec_hygiene.py` first moves from `testing/` to `core/`.

**Tech Stack:** Python 3.12+, frozen dataclasses, pytest (`-m gate` fast/DB-free), mkdocs (`--strict`), the existing `scripts/gen_*` generator pattern (render logic lives in the module, thin `--mode write|ci` CLI).

## Global Constraints

- **Clean break, no shims** (ADR-0003): move `sitespec_hygiene.py`, update all callers in the same change; no re-export at the old path.
- **No `from __future__ import annotations` only where a FastAPI route file** (ADR-0014) — not relevant here; keep `from __future__ import annotations` in these pure modules (matches the existing rubric files).
- **New gate tests carry `pytestmark = pytest.mark.gate`** and must be fast + DB-free (no Postgres/Playwright).
- **Concept vocabulary is exactly these 9 keys:** `type`, `rhythm`, `hierarchy`, `colour`, `motion`, `structure`, `finish`, `cta`, `family_fidelity`.
- **The three rubrics' dimension keys are the source of truth** — never hardcode the 20 keys anywhere but derive from `SITESPEC_HYGIENE_DIMENSIONS` / `SITESPEC_VISION_DIMENSIONS` / `TASTE_DIMENSIONS`.
- **British spelling** `colour` for the concept key (matches `colour_confidence`; note taste uses `color_discipline` — the concept key is `colour`, the dimension keys keep their own spelling).
- Commit message trailer on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/dazzle/core/sitespec_hygiene.py` | **Moved** from `testing/`. Unchanged content (deterministic hygiene rubric). |
| `src/dazzle/core/design_context.py` | **New.** The facade: `DesignConcept`, `RubricRef`, `DESIGN_CONCEPTS`, `RUBRICS`, `CONCEPT_MAP`, accessors, and `render_markdown()`. |
| `scripts/gen_design_context.py` | **New.** Thin CLI over `design_context.render_markdown()` (`--mode write|ci`), mirroring `scripts/gen_ux_catalogue.py`. |
| `docs/reference/hm-design-context.md` | **New (generated).** The single agent entry-point. |
| `tests/unit/test_design_context.py` | **New.** Hard claim-integrity gate + accessor tests + doc-drift gate. |
| `tests/unit/test_sitespec_hygiene.py` | **Modify** import path. |
| `tests/unit/test_hm_boundary.py` | **Modify** SANCTIONED path. |
| `tests/unit/fixtures/complexity_baseline.json` | **Regenerate** (moved-file key). |
| `mkdocs.yml` | **Modify** nav (add HM Design Context under Reference). |

The 20 dimensions and their concept assignment (locked here so tasks agree):

| Concept | Dimensions (`<rubric>.<key>`) |
|---------|-------------------------------|
| `type` | `hygiene.type_system`, `hygiene.fluid_type`, `vision.type_modernity` |
| `rhythm` | `hygiene.section_rhythm`, `vision.whitespace_rhythm`, `taste.spatial_rhythm` |
| `hierarchy` | `vision.visual_hierarchy`, `vision.hero_impact`, `taste.typographic_hierarchy` |
| `colour` | `vision.colour_confidence`, `taste.color_discipline` |
| `motion` | `hygiene.motion` |
| `structure` | `hygiene.responsive`, `hygiene.container` |
| `finish` | `vision.finish_polish`, `taste.perceived_craft`, `taste.state_completeness`, `taste.dark_mode_integrity` |
| `cta` | `vision.cta_prominence` |
| `family_fidelity` | `vision.family_fidelity` |

Rubric names → axes: `hygiene`=(marketing, deterministic), `vision`=(marketing, judged), `taste`=(app_internals, judged). The `app_internals × deterministic` matrix cell is intentionally empty.

---

## Task 1: Move `sitespec_hygiene` from `testing/` to `core/`

**Files:**
- Move: `src/dazzle/testing/sitespec_hygiene.py` → `src/dazzle/core/sitespec_hygiene.py`
- Modify: `tests/unit/test_sitespec_hygiene.py:23`
- Modify: `tests/unit/test_hm_boundary.py` (SANCTIONED set)
- Modify: `src/dazzle/core/sitespec_vision_rubric.py:4` (docstring path reference)
- Regenerate: `tests/unit/fixtures/complexity_baseline.json`

**Interfaces:**
- Produces: `dazzle.core.sitespec_hygiene` exporting `SITESPEC_HYGIENE_DIMENSIONS`, `HygieneDimension`, `hm_sitespec_css`, `score_sitespec_css` (unchanged signatures). Task 2 imports `SITESPEC_HYGIENE_DIMENSIONS` from here.

- [ ] **Step 1: Move the file with git (preserves history)**

```bash
git mv src/dazzle/testing/sitespec_hygiene.py src/dazzle/core/sitespec_hygiene.py
```

The file content is unchanged. Note: `hm_sitespec_css()` reads `Path(__file__).resolve().parents[3] / "packages" / ...`. The file moves from `src/dazzle/testing/` to `src/dazzle/core/` — both are 3 levels below the repo root (`src/dazzle/<pkg>/file.py`), so `parents[3]` still resolves to the repo root. **No path-depth change needed.**

- [ ] **Step 2: Update the real code importer (the test)**

In `tests/unit/test_sitespec_hygiene.py` line 23, change:

```python
from dazzle.testing.sitespec_hygiene import hm_sitespec_css, score_sitespec_css
```

to:

```python
from dazzle.core.sitespec_hygiene import hm_sitespec_css, score_sitespec_css
```

Also update the module docstring reference on line 4 (`dazzle.testing.sitespec_hygiene` → `dazzle.core.sitespec_hygiene`).

- [ ] **Step 3: Repoint the HM-boundary SANCTIONED path**

In `tests/unit/test_hm_boundary.py`, the `SANCTIONED` set (around line 43) contains `"src/dazzle/testing/sitespec_hygiene.py"`. Change it to `"src/dazzle/core/sitespec_hygiene.py"` and update the adjacent comment to say the rubric now lives in `core/`:

```python
    # Sitespec-hygiene rubric reads the HM sitespec component CSS to *measure*
    # its modern-landing structural properties (Goal-2 deterministic floor).
    "src/dazzle/core/sitespec_hygiene.py",
```

(This test scans `src/dazzle` + `scripts` for HM-package references and requires each referencing file to be listed by its current path — the move breaks it until repointed.)

- [ ] **Step 4: Fix the docstring path in the vision rubric**

`src/dazzle/core/sitespec_vision_rubric.py` line 4 says ``Where `testing/sitespec_hygiene.py` scores the CSS *structure*``. Change `testing/sitespec_hygiene.py` → `core/sitespec_hygiene.py`. (Docstring only — there is no code import to change.)

- [ ] **Step 5: Run the moved rubric's tests + the boundary gate**

Run: `pytest tests/unit/test_sitespec_hygiene.py tests/unit/test_hm_boundary.py -q`
Expected: PASS (import resolves at new path; boundary scan finds the moved file sanctioned).

- [ ] **Step 6: Regenerate the complexity baseline (moved-file key)**

The ratchet baseline keys the old path `dazzle/testing/sitespec_hygiene.py`. Regenerate so it keys the new path:

Run: `dazzle fitness code --write-baseline`
Then confirm the drift gate is green:
Run: `pytest tests/unit -k complexity -m gate -q`
Expected: PASS. Confirm the baseline no longer contains `dazzle/testing/sitespec_hygiene.py`:
Run: `grep -c 'testing/sitespec_hygiene' tests/unit/fixtures/complexity_baseline.json`
Expected: `0`.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/core/sitespec_hygiene.py tests/unit/test_sitespec_hygiene.py \
  tests/unit/test_hm_boundary.py src/dazzle/core/sitespec_vision_rubric.py \
  tests/unit/fixtures/complexity_baseline.json
git commit -m "refactor: move sitespec_hygiene testing/ -> core/ for #1566 facade

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `core/design_context.py` facade + claim-integrity gate

**Files:**
- Create: `src/dazzle/core/design_context.py`
- Create: `tests/unit/test_design_context.py`

**Interfaces:**
- Consumes: `dazzle.core.sitespec_hygiene.SITESPEC_HYGIENE_DIMENSIONS`, `dazzle.core.sitespec_vision_rubric.SITESPEC_VISION_DIMENSIONS`, `dazzle.core.taste_rubric.TASTE_DIMENSIONS` (each a `tuple` of dataclasses with a `.key: str`).
- Produces:
  - `RubricRef(name: str, surface: str, method: str, dimension_keys: tuple[str, ...])` — frozen dataclass.
  - `DesignConcept(key: str, definition: str, dimensions: tuple[str, ...])` — frozen dataclass; `dimensions` are `"<rubric>.<key>"` qualified ids.
  - `RUBRICS: tuple[RubricRef, ...]`, `DESIGN_CONCEPTS: tuple[DesignConcept, ...]`, `CONCEPT_MAP: dict[str, tuple[str, ...]]`.
  - `concepts() -> tuple[DesignConcept, ...]`, `dimensions_for(concept_key: str) -> tuple[str, ...]`, `matrix() -> dict[tuple[str, str], RubricRef | None]`.
  - `all_dimension_ids() -> frozenset[str]`, `method_of(qualified_id: str) -> str`, `surface_of(qualified_id: str) -> str`, `rubric_of(qualified_id: str) -> RubricRef`.
  - `render_markdown() -> str`, `DOC_PATH: Path` — used by Task 3.

- [ ] **Step 1: Write the failing claim-integrity tests**

Create `tests/unit/test_design_context.py`:

```python
"""#1566 hard gate: the HM design-context must claim every rubric dimension
exactly once, and every concept must measure something real."""

import pytest

from dazzle.core.design_context import (
    CONCEPT_MAP,
    DESIGN_CONCEPTS,
    RUBRICS,
    all_dimension_ids,
    concepts,
    dimensions_for,
    matrix,
    method_of,
    surface_of,
)

pytestmark = pytest.mark.gate

EXPECTED_CONCEPT_KEYS = {
    "type", "rhythm", "hierarchy", "colour", "motion",
    "structure", "finish", "cta", "family_fidelity",
}


def test_concept_vocabulary_is_the_agreed_set() -> None:
    assert {c.key for c in DESIGN_CONCEPTS} == EXPECTED_CONCEPT_KEYS


def test_every_concept_maps_to_at_least_one_real_dimension() -> None:
    real = all_dimension_ids()
    for c in DESIGN_CONCEPTS:
        assert c.dimensions, f"concept {c.key} claims no dimensions"
        for d in c.dimensions:
            assert d in real, f"concept {c.key} claims non-existent dimension {d}"


def test_every_rubric_dimension_is_claimed_by_exactly_one_concept() -> None:
    claimed: list[str] = [d for c in DESIGN_CONCEPTS for d in c.dimensions]
    # no dimension claimed twice
    assert len(claimed) == len(set(claimed)), "a dimension is claimed by >1 concept"
    # every real dimension is claimed (no orphans)
    assert set(claimed) == all_dimension_ids()


def test_concept_map_matches_design_concepts() -> None:
    assert CONCEPT_MAP == {c.key: c.dimensions for c in DESIGN_CONCEPTS}
    for key in EXPECTED_CONCEPT_KEYS:
        assert dimensions_for(key) == CONCEPT_MAP[key]


def test_matrix_is_well_formed() -> None:
    m = matrix()
    assert set(m.keys()) == {
        ("marketing", "deterministic"),
        ("marketing", "judged"),
        ("app_internals", "deterministic"),
        ("app_internals", "judged"),
    }
    assert m[("marketing", "deterministic")].name == "hygiene"
    assert m[("marketing", "judged")].name == "vision"
    assert m[("app_internals", "judged")].name == "taste"
    # the honest empty cell
    assert m[("app_internals", "deterministic")] is None


def test_method_and_surface_lookups() -> None:
    assert method_of("hygiene.type_system") == "deterministic"
    assert method_of("vision.hero_impact") == "judged"
    assert surface_of("taste.perceived_craft") == "app_internals"
    assert surface_of("vision.cta_prominence") == "marketing"


def test_accessor_shapes() -> None:
    assert concepts() == DESIGN_CONCEPTS
    assert len(RUBRICS) == 3
    # 20 dimensions total across the three rubrics
    assert len(all_dimension_ids()) == 20
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_design_context.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.core.design_context'`.

- [ ] **Step 3: Write `core/design_context.py`**

Create `src/dazzle/core/design_context.py`:

```python
"""HM design-context — the unified facade over Dazzle's three design-quality rubrics.

Dazzle measures HM design quality with three rubrics that live apart:

- **taste** (`core.taste_rubric`) — judged, app-internals density/craft.
- **sitespec vision** (`core.sitespec_vision_rubric`) — judged, marketing landing pages.
- **sitespec hygiene** (`core.sitespec_hygiene`) — deterministic, marketing CSS structure.

They share overlapping *concepts* measured differently (type, whitespace/rhythm, finish
appear across more than one rubric). This module is the single place that names those
concepts, maps every rubric dimension to exactly one concept, and lays the rubrics on a
surface x method matrix. It is the source of truth the generated
``docs/reference/hm-design-context.md`` renders (via ``scripts/gen_design_context.py``) and
that the claim-integrity gate in ``tests/unit/test_design_context.py`` enforces — the same
guide-and-gate pattern as ``docs/reference/taste.md`` <- ``core.taste_rubric``.

Scope (#1566) is the unification of the *measurement/standard* only. Exemplars, the
Hyperpart taste-gate (#1567), the customise-affordance, and any MCP tool are out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dazzle.core.sitespec_hygiene import SITESPEC_HYGIENE_DIMENSIONS
from dazzle.core.sitespec_vision_rubric import SITESPEC_VISION_DIMENSIONS
from dazzle.core.taste_rubric import TASTE_DIMENSIONS

__all__ = [
    "RubricRef",
    "DesignConcept",
    "RUBRICS",
    "DESIGN_CONCEPTS",
    "CONCEPT_MAP",
    "SURFACES",
    "METHODS",
    "concepts",
    "dimensions_for",
    "matrix",
    "all_dimension_ids",
    "rubric_of",
    "method_of",
    "surface_of",
    "render_markdown",
    "DOC_PATH",
]

SURFACES: tuple[str, str] = ("marketing", "app_internals")
METHODS: tuple[str, str] = ("deterministic", "judged")


@dataclass(frozen=True)
class RubricRef:
    """One measurement rubric, placed on the two structural axes.

    ``dimension_keys`` are the rubric's own bare keys; a fully-qualified dimension
    id used by the concept map is ``f"{name}.{key}"``.
    """

    name: str  # "hygiene" | "vision" | "taste"
    surface: str  # one of SURFACES
    method: str  # one of METHODS
    dimension_keys: tuple[str, ...]


RUBRICS: tuple[RubricRef, ...] = (
    RubricRef(
        "hygiene",
        "marketing",
        "deterministic",
        tuple(d.key for d in SITESPEC_HYGIENE_DIMENSIONS),
    ),
    RubricRef(
        "vision",
        "marketing",
        "judged",
        tuple(d.key for d in SITESPEC_VISION_DIMENSIONS),
    ),
    RubricRef(
        "taste",
        "app_internals",
        "judged",
        tuple(d.key for d in TASTE_DIMENSIONS),
    ),
)

_RUBRIC_BY_NAME: dict[str, RubricRef] = {r.name: r for r in RUBRICS}


@dataclass(frozen=True)
class DesignConcept:
    """A canonical HM design concept — one design idea the rubrics measure, possibly
    several times across surfaces/methods.

    ``dimensions`` are fully-qualified rubric dimension ids (``"<rubric>.<key>"``).
    """

    key: str
    definition: str
    dimensions: tuple[str, ...]


# The concept vocabulary. Every rubric dimension is claimed by exactly one concept
# (enforced by tests/unit/test_design_context.py); a concept may own many dimensions
# across rubrics — that overlap is the reconciliation this module exists to make.
DESIGN_CONCEPTS: tuple[DesignConcept, ...] = (
    DesignConcept(
        "type",
        "Type from a real scale: token-driven sizes, fluid display, modern faces.",
        ("hygiene.type_system", "hygiene.fluid_type", "vision.type_modernity"),
    ),
    DesignConcept(
        "rhythm",
        "Whitespace and vertical rhythm: consistent, confident spacing between things.",
        ("hygiene.section_rhythm", "vision.whitespace_rhythm", "taste.spatial_rhythm"),
    ),
    DesignConcept(
        "hierarchy",
        "Editorial reading order: one dominant element leads; the eye is led, not lost.",
        ("vision.visual_hierarchy", "vision.hero_impact", "taste.typographic_hierarchy"),
    ),
    DesignConcept(
        "colour",
        "Cohesive palette used with intent: a clear accent, tasteful depth.",
        ("vision.colour_confidence", "taste.color_discipline"),
    ),
    DesignConcept(
        "motion",
        "Subtle, consistent, token-driven motion that reads as considered.",
        ("hygiene.motion",),
    ),
    DesignConcept(
        "structure",
        "Layout skeleton: responsive reflow and width-constrained, readable content.",
        ("hygiene.responsive", "hygiene.container"),
    ),
    DesignConcept(
        "finish",
        "Overall craft: alignment, state completeness, dark-mode integrity, no rough edges.",
        (
            "vision.finish_polish",
            "taste.perceived_craft",
            "taste.state_completeness",
            "taste.dark_mode_integrity",
        ),
    ),
    DesignConcept(
        "cta",
        "The primary action is unmistakable, inviting, and reinforced at decision points.",
        ("vision.cta_prominence",),
    ),
    DesignConcept(
        "family_fidelity",
        "The page convincingly reads as its intended aesthetic-family vernacular.",
        ("vision.family_fidelity",),
    ),
)

CONCEPT_MAP: dict[str, tuple[str, ...]] = {c.key: c.dimensions for c in DESIGN_CONCEPTS}


def concepts() -> tuple[DesignConcept, ...]:
    """All design concepts, in canonical order."""
    return DESIGN_CONCEPTS


def dimensions_for(concept_key: str) -> tuple[str, ...]:
    """The qualified rubric dimension ids that measure ``concept_key``."""
    return CONCEPT_MAP[concept_key]


def all_dimension_ids() -> frozenset[str]:
    """Every fully-qualified rubric dimension id across all three rubrics."""
    return frozenset(f"{r.name}.{k}" for r in RUBRICS for k in r.dimension_keys)


def rubric_of(qualified_id: str) -> RubricRef:
    """The rubric owning a ``"<rubric>.<key>"`` dimension id."""
    return _RUBRIC_BY_NAME[qualified_id.split(".", 1)[0]]


def method_of(qualified_id: str) -> str:
    """"deterministic" | "judged" for a qualified dimension id."""
    return rubric_of(qualified_id).method


def surface_of(qualified_id: str) -> str:
    """"marketing" | "app_internals" for a qualified dimension id."""
    return rubric_of(qualified_id).surface


def matrix() -> dict[tuple[str, str], RubricRef | None]:
    """The surface x method matrix. Cells with no rubric today (app_internals x
    deterministic) are ``None`` — an honest, visible gap, not a hidden capability."""
    cell: dict[tuple[str, str], RubricRef | None] = {
        (s, m): None for s in SURFACES for m in METHODS
    }
    for r in RUBRICS:
        cell[(r.surface, r.method)] = r
    return cell


# --- doc generation (render logic lives here so it is importable + unit-tested) -----

DOC_PATH: Path = Path(__file__).resolve().parents[3] / "docs" / "reference" / "hm-design-context.md"

_SURFACE_LABEL = {"marketing": "Marketing / sitespec", "app_internals": "App internals"}
_METHOD_LABEL = {"deterministic": "Deterministic", "judged": "Judged (LLM panel)"}
_RUBRIC_SOURCE = {
    "hygiene": "`core/sitespec_hygiene.py`",
    "vision": "`core/sitespec_vision_rubric.py`",
    "taste": "`core/taste_rubric.py`",
}


def render_markdown() -> str:
    """Render the design-context reference doc from this module (the source of truth)."""
    lines: list[str] = []
    lines.append("<!-- GENERATED by scripts/gen_design_context.py — do not edit by hand. -->")
    lines.append("<!-- Source of truth: src/dazzle/core/design_context.py -->")
    lines.append("")
    lines.append("# HM Design Context")
    lines.append("")
    lines.append(
        "The single entry-point for HM design quality. When you customise HM for a new "
        "property, this is the standard your work is measured against — spanning both "
        "marketing/sitespec pages and app internals. It unifies three rubrics that "
        "otherwise live apart, on two axes: **surface** (marketing vs app internals) x "
        "**method** (deterministic structure vs judged perception)."
    )
    lines.append("")
    lines.append(
        "The *vernacular* — how to actually make something on-family — lives in the "
        "aesthetic families (`packages/hatchi-maxchi/families/*.css`) and the house "
        "taste principles in [taste.md](taste.md). This page is the *measurement*."
    )
    lines.append("")

    # Matrix
    lines.append("## Surface x method matrix")
    lines.append("")
    lines.append("| Surface \\ Method | Deterministic | Judged (LLM panel) |")
    lines.append("|---|---|---|")
    m = matrix()
    for s in SURFACES:
        cells = []
        for meth in METHODS:
            r = m[(s, meth)]
            cells.append(
                f"{_RUBRIC_SOURCE[r.name]} ({len(r.dimension_keys)} dims)" if r else "— (none today)"
            )
        lines.append(f"| **{_SURFACE_LABEL[s]}** | {cells[0]} | {cells[1]} |")
    lines.append("")
    lines.append(
        "> The app-internals x deterministic cell is empty today — there is no "
        "deterministic app-internals rubric yet. It is shown so the gap is visible, "
        "not hidden."
    )
    lines.append("")

    # Concept map
    lines.append("## Concept map")
    lines.append("")
    lines.append(
        "Each concept is one design idea; the rubrics measure it in the columns below. "
        "Every rubric dimension is claimed by exactly one concept (enforced by "
        "`tests/unit/test_design_context.py`)."
    )
    lines.append("")
    lines.append("| Concept | What it means | Measured by |")
    lines.append("|---|---|---|")
    for c in DESIGN_CONCEPTS:
        dims = ", ".join(
            f"`{d}` ({method_of(d)[0]})" for d in c.dimensions
        )
        lines.append(f"| `{c.key}` | {c.definition} | {dims} |")
    lines.append("")
    lines.append("_Method key: (d) deterministic, (j) judged._")
    lines.append("")

    # Rubric sources
    lines.append("## Rubric sources")
    lines.append("")
    for r in RUBRICS:
        lines.append(
            f"- **{r.name}** — {_RUBRIC_SOURCE[r.name]} — "
            f"{_SURFACE_LABEL[r.surface].lower()}, {_METHOD_LABEL[r.method].lower()}; "
            f"{len(r.dimension_keys)} dimensions."
        )
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run the claim-integrity tests to verify they pass**

Run: `pytest tests/unit/test_design_context.py -q`
Expected: PASS (all 7 tests).

- [ ] **Step 5: Type-check + lint the new module**

Run: `ruff check src/dazzle/core/design_context.py tests/unit/test_design_context.py --fix && ruff format src/dazzle/core/design_context.py tests/unit/test_design_context.py`
Run: `mypy src/dazzle/core/design_context.py`
Expected: clean (no errors).

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/design_context.py tests/unit/test_design_context.py
git commit -m "feat: core/design_context facade unifying the 3 HM rubrics (#1566)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Generator, generated doc, nav, and doc-drift gate

**Files:**
- Create: `scripts/gen_design_context.py`
- Create: `docs/reference/hm-design-context.md` (generated)
- Modify: `mkdocs.yml` (nav)
- Modify: `tests/unit/test_design_context.py` (append doc-drift test)

**Interfaces:**
- Consumes: `dazzle.core.design_context.render_markdown()`, `dazzle.core.design_context.DOC_PATH`.
- Produces: `docs/reference/hm-design-context.md` on disk; a `--mode ci` that exits non-zero when the committed doc is stale.

- [ ] **Step 1: Write the doc-drift test (failing)**

Append to `tests/unit/test_design_context.py`:

```python
def test_generated_doc_is_current() -> None:
    from dazzle.core.design_context import DOC_PATH, render_markdown

    assert DOC_PATH.exists(), "docs/reference/hm-design-context.md must be generated"
    committed = DOC_PATH.read_text(encoding="utf-8")
    assert committed == render_markdown() + "\n", (
        "hm-design-context.md is stale — run: python scripts/gen_design_context.py"
    )
```

(The trailing `+ "\n"` matches the convention that files end with a single newline; Step 3 writes `render_markdown() + "\n"`.)

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_design_context.py::test_generated_doc_is_current -q`
Expected: FAIL on `AssertionError: docs/reference/hm-design-context.md must be generated`.

- [ ] **Step 3: Write the generator**

Create `scripts/gen_design_context.py` (mirrors `scripts/gen_ux_catalogue.py`):

```python
#!/usr/bin/env python3
"""Generate docs/reference/hm-design-context.md from core.design_context.

Thin CLI over ``dazzle.core.design_context.render_markdown`` (the render logic lives
in the module so it is importable + unit-tested). ``--mode=ci`` fails when the committed
doc is stale, so the docs workflow / gate can enforce freshness.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dazzle.core.design_context import DOC_PATH, render_markdown  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["write", "ci"], default="write")
    args = ap.parse_args()

    content = render_markdown() + "\n"

    if args.mode == "ci":
        if not DOC_PATH.exists() or DOC_PATH.read_text(encoding="utf-8") != content:
            print(
                f"STALE: {DOC_PATH} is out of date — run: python scripts/gen_design_context.py",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {DOC_PATH} is current")
        return 0

    DOC_PATH.write_text(content, encoding="utf-8")
    print(f"WROTE: {DOC_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Generate the doc**

Run: `python scripts/gen_design_context.py`
Expected: `WROTE: .../docs/reference/hm-design-context.md`. Confirm it exists:
Run: `head -20 docs/reference/hm-design-context.md`
Expected: the generated header + intro.

- [ ] **Step 5: Run the doc-drift test to verify it passes**

Run: `pytest tests/unit/test_design_context.py::test_generated_doc_is_current -q`
Expected: PASS.

- [ ] **Step 6: Add the page to mkdocs nav**

In `mkdocs.yml`, under the Reference section, add an entry immediately after the `UX Catalogue` line (currently `- UX Catalogue: reference/ux-catalogue.md`):

```yaml
      - HM Design Context: reference/hm-design-context.md
```

- [ ] **Step 7: Build the docs strict**

Run: `mkdocs build --strict`
Expected: exit 0, no warnings (new nav entry resolves, no broken internal links — the `taste.md` link is relative within `docs/reference/` so it resolves).

- [ ] **Step 8: Full gate sweep**

Run: `pytest tests/unit -m gate -q`
Expected: PASS (claim-integrity + doc-drift + the repointed boundary/complexity gates all green).

- [ ] **Step 9: Commit**

```bash
git add scripts/gen_design_context.py docs/reference/hm-design-context.md \
  mkdocs.yml tests/unit/test_design_context.py
git commit -m "feat: generated hm-design-context.md + doc-drift gate (#1566)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Ship

**Files:**
- Modify: `CHANGELOG.md`, `pyproject.toml` + the other 5 version locations (via `/bump`).

- [ ] **Step 1: CHANGELOG entry under Unreleased**

Add to `CHANGELOG.md` `## [Unreleased]`:

```markdown
### Added
- **HM design-context (#1566)** — `core/design_context.py` unifies the three HM
  design-quality rubrics (deterministic sitespec-hygiene, judged sitespec-vision,
  judged app-internals taste) behind one facade: a 9-concept vocabulary, a concept
  map claiming every rubric dimension exactly once, and a surface x method matrix.
  Generated `docs/reference/hm-design-context.md` is the agent entry-point; a hard
  claim-integrity + doc-drift gate (`tests/unit/test_design_context.py`) keeps it honest.

### Changed
- Moved `sitespec_hygiene` from `dazzle.testing` to `dazzle.core` (clean break) so the
  design-context facade can import all three rubrics without a `core -> testing` layer
  violation. Importers updated in the same change.

### Agent Guidance
- When customising HM for a new property, read `docs/reference/hm-design-context.md`
  first — it is the measurement standard across marketing + app-internals. To add or
  reassign a design concept, edit `src/dazzle/core/design_context.py`; every rubric
  dimension must be claimed by exactly one concept or CI fails.
```

- [ ] **Step 2: Bump the version**

Run: `/bump patch`

- [ ] **Step 3: Ship (runs lint + type + gate + docs gates, commits, tags, pushes)**

Run: `/ship`
Expected: lint/mypy/`-m gate`/`mkdocs --strict` all green; commit + tag + push; worktree clean.

- [ ] **Step 4: Monitor CI to green**

Run: `gh run list --branch main --limit 3`
Watch the `ci.yml` run to `success`. If red on these changes, fix and re-push (`/bump patch` again). If red on unrelated flake, note and continue.

- [ ] **Step 5: Close the issue**

```bash
gh issue comment 1566 --body "$(cat <<'EOF'
Shipped. `core/design_context.py` now unifies the three HM design-quality rubrics
(sitespec-hygiene / sitespec-vision / taste) behind one facade — a 9-concept vocabulary,
a concept map claiming every rubric dimension exactly once, and a surface × method matrix.
The agent entry-point is the generated `docs/reference/hm-design-context.md`; a hard
claim-integrity + doc-drift gate keeps concept↔dimension coverage honest as the rubrics
evolve. `sitespec_hygiene` moved `testing/`→`core/` to make the facade layer-clean.

Out of scope (as scoped on this issue): exemplars, the Hyperpart taste-gate (#1567),
the customise-affordance, and an MCP tool.

🔖 Claude-lens: dazzle
EOF
)"
gh issue close 1566
gh issue edit 1566 --remove-label "needs-triage" 2>/dev/null || true
```

---

## Self-Review

**1. Spec coverage:**
- Consolidate rubrics in `core/` (move hygiene) → Task 1. ✓
- `core/design_context.py` facade (DesignConcept, CONCEPT_MAP, DESIGN_CONTEXT matrix, accessors) → Task 2. ✓ (matrix exposed via `matrix()`; the spec's `DESIGN_CONTEXT` name is realised as the `matrix()` accessor + `RUBRICS` — noted below.)
- Generated drift-gated doc + mkdocs nav → Task 3. ✓
- Hard gates: every concept ≥1 dimension, every dimension claimed by exactly one concept, doc current → Task 2 (first two) + Task 3 (doc). ✓
- Out-of-scope items untouched. ✓

**2. Placeholder scan:** No TBD/TODO; every code + command step is concrete. ✓

**3. Type consistency:** `render_markdown() -> str` and `DOC_PATH: Path` defined in Task 2, consumed in Task 3. `all_dimension_ids() -> frozenset[str]`, `method_of`/`surface_of`/`rubric_of` defined and used consistently. `matrix()` returns `dict[tuple[str,str], RubricRef | None]` — Task 2 test and Task 3 renderer both index `m[(surface, method)]` and check `.name` / `is None`. ✓

**Naming note:** the spec named the matrix constant `DESIGN_CONTEXT`. This plan realises the same concept as the `matrix()` accessor plus `RUBRICS` (the matrix is derived from the rubric list — one source of truth, no duplicated cell table to drift). This is a faithful, DRY realisation of the spec's intent, not a scope change.
