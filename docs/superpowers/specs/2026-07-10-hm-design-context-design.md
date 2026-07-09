# HM design-context — unify the three design-quality rubrics (#1566)

**Date:** 2026-07-10
**Issue:** #1566
**Status:** Design approved

## Context

The HM sitespec-convergence arc produced **three** parallel design-quality
measurement systems that live apart:

1. **Sitespec hygiene** — `testing/sitespec_hygiene.py` (`SITESPEC_HYGIENE_DIMENSIONS`,
   `HygieneDimension` = key/weight/scorer-fn). **Deterministic** CSS-structure scoring,
   weighted /100, floor-gated at 90 (`test_sitespec_hygiene.py`, currently 97.2).
   Surface: marketing.
2. **Sitespec vision** — `core/sitespec_vision_rubric.py` (`SITESPEC_VISION_DIMENSIONS`,
   reuses `TasteDimension`). **Judged** by a blind LLM vision panel, 1–10 anchored.
   Surface: marketing.
3. **Taste** — `core/taste_rubric.py` (`TASTE_DIMENSIONS`, `TasteDimension` =
   key/title/question/anchors/applies_to). **Judged**, 1–10 anchored. Surface:
   app-internals.

They share overlapping *concepts* measured differently (type modernity, whitespace/
rhythm appear across all). This is the north-star doc's **gap #1**
(`dev_docs/2026-07-09-hm-agent-customizable-design-context.md`): two rubrics, no
unified context. Exemplars (gap #2), the Hyperpart taste-gate (gap #3 → #1567), and
the customise-affordance (gap #4) are **out of scope** for this issue.

## Goal

One **readable + machine-readable "HM design-context"** an agent consults when
customising HM for a new property — spanning marketing and app-internals — mirroring
how `docs/reference/taste.md` is drift-gated against `core/taste_rubric.py`. The
same artifact is **guide and gate** viewed from two directions.

## Design

A thin unifying layer over the three rubrics — **facade + concept map + drift-gated
doc**. The rubrics keep their shapes and scoring; the new layer organizes and
reconciles them. Two structural axes: **surface** (app-internals / marketing) ×
**method** (deterministic-structural / judged-perceptual).

### 1. Consolidate the three rubrics in `core/`

`taste_rubric.py` and `sitespec_vision_rubric.py` already live in `core/`.
**Move `sitespec_hygiene.py` from `testing/` to `core/sitespec_hygiene.py`** — it is
a pure rubric (CSS→score, no test deps), so it belongs beside the other two, and a
core-level facade can then import all three without a layer violation. Update the ~4
importers (`test_sitespec_hygiene.py`, `test_hm_boundary.py`'s SANCTIONED list, and
any `sitespec_vision_rubric` reference). Clean break, no shim (ADR-0003).

### 2. `core/design_context.py` — the facade / source of truth

Imports the three rubrics and exposes:

- **`DesignConcept`** — a canonical concept + one-line definition. Vocabulary
  (reconciles the overlaps): `type`, `rhythm` (whitespace / section-rhythm),
  `hierarchy`, `colour`, `motion`, `structure` (container / responsive), `finish`,
  `cta`, `family_fidelity`.
- **`CONCEPT_MAP`** — for each concept, the rubric dimensions that measure it and by
  which method. Example: `type` → deterministic `{hygiene.type_system,
  hygiene.fluid_type}` + judged `{taste.type_modernity, vision.type_modernity}`.
  This is the reconciliation of the overlapping dimensions.
- **`DESIGN_CONTEXT`** — the **surface × method matrix**: for each
  (surface ∈ app_internals | marketing) × (method ∈ deterministic | judged), the
  applicable rubric + its dimensions. Cells may be empty (app-internals has no
  deterministic rubric *today*) — the emptiness is honest and visible, and names a
  future gap without asserting a capability that doesn't exist.
- Accessors the doc generator (and any future consumer) use:
  `concepts()`, `dimensions_for(concept)`, `matrix()`.

### 3. Generated doc `docs/reference/hm-design-context.md`

`scripts/gen_design_context.py` renders the module → the single agent entry-point:
the surface × method matrix, the concept map, links to each rubric's source, and
pointers to the **vernacular** (the families + `docs/reference/taste.md`) with a
short "how to read this when customising HM for a new property" preamble. Mirrors the
`taste.md ← taste_rubric.py` generation pattern; added to `mkdocs.yml` nav.

### 4. Gates — `tests/unit/test_design_context.py` (+ doc drift)

Claim-integrity, all **hard** gates (keeps the context honest as rubrics evolve):
- Every `DesignConcept` maps to ≥1 real rubric dimension.
- **Every rubric dimension (across all three rubrics) is claimed by exactly one
  concept** — no orphan dimensions, and adding a future rubric dimension forces a
  concept assignment (fails CI until mapped).
- The generated `hm-design-context.md` is current (`gen_design_context.py` output ==
  committed), same pattern as the ux-catalogue / taste-doc drift gates.

## Out of scope (per #1566)

- Exemplars (gap #2), Hyperpart taste-gate (#1567 / gap #3), customise-affordance
  (gap #4).
- An MCP tool for the context — doc-first (matches how `taste.md` is consulted today);
  YAGNI until an in-session need is demonstrated.
- No change to the rubrics' dimensions, scoring, or the hygiene floor.

## Testing / verification

- `test_design_context.py` (concept/dimension claim-integrity + matrix well-formed) +
  doc-drift gate; both carry `pytest.mark.gate` (fast, DB-free).
- Existing `test_sitespec_hygiene.py` still green after the move (import path updated).
- `mypy src/dazzle` + `ruff` + `pytest -m gate` green; `mkdocs build --strict` clean
  (new nav entry resolves).
- The generated `docs/reference/hm-design-context.md` reads coherently as an agent
  entry-point (human check).
