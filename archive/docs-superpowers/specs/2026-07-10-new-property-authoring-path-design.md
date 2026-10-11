# New-property authoring path — ThemeSpec coherence gate + property vision (#1567, slice 2)

**Date:** 2026-07-10
**Issue:** #1567 (slice 2 of 2 — closes the issue)
**Status:** Design approved
**Depends on:** #1566 (design-context, v0.101.9), #1567 slice 1 (component gate, v0.101.10)

## Context

Slice 1 shipped the Hyperpart taste-gate. This slice delivers affordance 2: a documented,
supported path for an agent to stand up a **new property** (marketing site / sub-app /
brand) with a coherent, industry-credible look — pick or author an aesthetic, then be
**auto-scored (deterministic floor + judged vision) before it's considered done**.

### What already exists (the reframe)

Investigation found the authoring path is *partially built*, in two disconnected systems:

1. **HM aesthetic families** — 4 hand-authored, framework-owned token dialects
   (`packages/hatchi-maxchi/families/{stripe,paper,linear-dark,expressive}.css`, ~82–107
   HSL-triplet token overrides each in an `@layer overrides` block, light + dark), applied
   via `[ui] theme=` / `DAZZLE_OVERRIDE_THEME` / `app x: theme:`. Each family is anchored
   to **per-family exemplars** (`scripts/taste/capture_sitespec_references.py`: linear-dark
   → linear.app/vercel; stripe → stripe.com/mercury; paper → notion/apple; expressive →
   framer/arc) — dual-use as the vision judge's references AND the visual target an agent
   studies.
2. **ThemeSpec** — the parametric, project-side system: `sitespec scaffold_theme` writes
   `themespec.yaml` (palette hue/chroma, typography, spacing, shape — 8 sections);
   `generate_tokens` → `core/theme_generators.py` + `generate_dtcg_tokens` produce the
   concrete palette (DTCG `tokens.json`); `validate_theme` → `validate_themespec`.

**The genuine gap:** `validate_themespec` does **range checks only** (brand_hue 0–360,
chroma 0–0.4, base_size 12–24). There is **zero contrast / WCAG / palette-coherence
checking anywhere in the theme system** — a parametric palette can silently generate
illegible foreground/background pairs. And no theme output is ever auto-scored against
the vision rubric. The scaffold exists; the *gate* does not.

### Approved decisions

- **Build on ThemeSpec** (parametric, project-side) — not literal hand-authored
  `families/*.css` (agents shouldn't hand-write ~82 raw HSL tokens when the parametric
  system exists), and not a families↔ThemeSpec unification (a separate, larger arc).
- **Contrast failures are hard errors** in `validate_theme` (teeth, not advisory).
- **The framework's own 4 families get a live contrast gate**, calibrated with the
  slice-1 stance: a genuine sub-AA pair is a *finding* (fix it or document a justified
  exception), never a buried threshold.
- **Property-vision stays minimal and advisory** — the deterministic contrast gate is the
  durable deliverable; judged vision is on-demand, subscription-billed.

## Design

Five parts.

### Part A — `core/contrast.py` (deterministic colour math)

Pure, dependency-free, unit-tested:

- Parse the two colour shapes the theme systems emit: HM family HSL triplets
  (`"220 30% 15%"`) and the generated-token colour format (whatever
  `generate_dtcg_tokens` emits — hex or oklch; confirmed at implementation and parsed
  accordingly).
- `relative_luminance(rgb) -> float` and `contrast_ratio(a, b) -> float` per WCAG 2.x.
- A canonical **pair table** shared by Parts B and C: text pairs at **4.5:1**
  (`foreground/background`, `card-foreground/card`, `popover-foreground/popover`,
  `primary-foreground/primary`, `secondary-foreground/secondary`,
  `muted-foreground/background`, semantic `*-foreground/*`) and UI pairs at **3:1**
  (`border/background`, focus `ring/background`). Pairs a token map doesn't define are
  skipped (absence is not a violation — mirrors slice 1's n/a stance).

### Part B — coherence gate inside `validate_theme` (project-side teeth)

Extend `validate_themespec` (`core/themespec_loader.py`): generate the concrete palette
from the themespec (via the existing `theme_generators`/DTCG path), run the Part-A pair
table on it for **both light and dark** modes, and add each sub-threshold pair as an
**error** (`palette contrast foreground/background 3.8:1 < 4.5:1 (light)`), failing
validation. Existing range checks stay. The MCP `validate_theme` op and any CLI wrapper
inherit the behaviour — an agent's "done" check for a new property theme is now a real
deterministic floor, live in the authoring workflow (the model-driven-failure-modes bar).

If a generated default themespec (the `scaffold_theme` output) fails its own contrast
gate, that is a bug to fix in the generator defaults, not a reason to soften the gate.

### Part C — framework live gate: the 4 shipped families

`tests/unit/test_family_contrast.py` (`pytestmark = pytest.mark.gate`, DB-free): parse
each `packages/hatchi-maxchi/families/*.css` (both the light and dark `:root`/
`[data-theme]` blocks), extract the canonical pairs, assert AA via Part A. The framework
holds its own curated aesthetics to the same standard it enforces on user themespecs.
Calibrated against the real 4 during implementation: a genuine sub-AA pair found there is
a finding — fix the family or add a documented per-pair exception constant with rationale
(kept tiny and explicit, like slice 1's `PAGE_CHROME_EXEMPT`).

### Part D — advisory property-vision (thin reuse)

`dazzle qa property-vision [--url URL | --route /] --family <name>`: screenshot the
property's rendered page (1440×1024 fold, same capture approach as the vision pilot),
score it with the existing `taste_panel` machinery against `SITESPEC_VISION_DIMENSIONS`,
supplying the chosen family's exemplar references for the `family_fidelity` dimension
(from `.dazzle/composition/references/sitespec/`, captured by the existing script).
Advisory: exit 0 on a successful score; clear usage error when the exemplars for that
family haven't been captured (`run scripts/taste/capture_sitespec_references.py --family …`).
Heavy parts (capture, judge client) injectable — glue unit-tested with mocks, exactly the
slice-1 `component-vision` pattern.

### Part E — the unified "stand up a new property" doc

The missing narrative that ties the pieces into one supported path. A new section in the
generated `docs/reference/hm-design-context.md` (same emit mechanism as slice 1's
"Authoring a new Hyperpart" section — static prose in `render_markdown()`), titled
**"Standing up a new property"**:

1. **Pick** a shipped family (`[ui] theme = "stripe" | "paper" | "linear-dark" |
   "expressive"`) when one fits the brand — done.
2. **Or author**: study the target family's exemplars (capture via
   `scripts/taste/capture_sitespec_references.py`), then `sitespec scaffold_theme` →
   edit `themespec.yaml` (compact parametric spec, not raw tokens).
3. **Deterministic floor (must pass):** `validate_theme` — now contrast-gated; then
   `generate_tokens`.
4. **Judged read (advisory):** `dazzle qa property-vision` against the family's
   exemplars.

Cross-links `taste.md` and the slice-1 Hyperpart section. Doc-drift gate already covers
the page.

## Out of scope

- Unifying HM families ↔ ThemeSpec into one representation (regenerating families from
  themespecs) — its own future arc.
- Auto-fixing a low-contrast palette (the gate reports; the author adjusts hue/chroma).
- APCA — WCAG 2 AA only.
- New MCP tools (the existing `sitespec` ops inherit the gate; doc-first otherwise).
- Registering a 5th rubric in the #1566 design-context: families/themespecs are a
  *theming* axis orthogonal to the surface×method matrix (a family spans both surfaces),
  so the contrast gate is wired into `validate_theme` + a family gate test instead. The
  design-context doc's new section narrates this.

## Testing / verification

- `tests/unit/test_contrast.py` — colour parsing (HSL triplet + generated format),
  luminance/ratio math against known WCAG reference values, pair-table skip-on-absent.
- `tests/unit/test_themespec_contrast.py` — a good themespec passes; a deliberately
  low-contrast themespec fails `validate_themespec` with pair-named errors (both modes).
- `tests/unit/test_family_contrast.py` — the 4 shipped families clear AA (with any
  documented exceptions explicit); gate-marked, DB-free.
- `tests/unit/test_property_vision.py` — glue test with mocked capture + judge;
  missing-exemplars usage error.
- Regenerated `hm-design-context.md`; existing doc-drift + design-context gates green.
- `mypy src/dazzle`, `ruff`, `pytest -m gate`, `mkdocs build --strict` green.

## Ship

`/bump patch` + `/ship`. On green: close #1567 with a slice-2 summary comment (slice 1 +
slice 2 = both affordances delivered).
