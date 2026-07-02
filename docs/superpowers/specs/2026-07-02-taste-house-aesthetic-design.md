# Taste: The Dazzle House Aesthetic — Design

**Date:** 2026-07-02
**Status:** Approved
**Owner:** James + in-session agent

## Problem

Dazzle's agent-first, DSL-driven, HTMX/SSR architecture produces strong results
efficiently — but the default look and feel lags what a modern audience expects.
A typical React app assembled from the shadcn/Tailwind/Vercel design dialect
(Lucide icons, Inter/Geist type, layered subtle shadows, disciplined neutral
ramps, first-class dark mode, micro-motion) *reads* as higher quality, even when
it is functionally inferior and architecturally heavier.

The infrastructure to enforce aesthetic opinions already exists (OKLCH token
sheet, cascade layers, theme resolver, composition audit/capture/analyze
pipeline, card-safety invariants, visual tier-2 subagent). What is missing is
the **opinions themselves**: there is no documented design philosophy, no icon
system, no motion or typography rationale, no accessibility contrast gate, and
the ux-architect material is locked in PDFs rather than agent-readable form.

**Goal:** an agent-accessible concept of "taste" — starting as a strongly
opinionated house aesthetic in the framework defaults, demonstrated end-to-end
in the example apps, and judged against an explicit parity gate.

**Non-goal:** accreting CSS until Dazzle imitates a generic React app, or
adopting the dialect's *mechanism* (utility-class proliferation, heavyweight
component frameworks). We target parity with the dialect's **perceived
quality**, achieved through principles, semantic CSS, and tokens.

## Decisions already made (brainstorming outcomes)

1. **Consumer:** framework defaults first; authoring-agent guidance and the
   evaluation loop are natural follow-ons and must be enabled by the artifact's
   structure, not built now.
2. **Direction:** derive the aesthetic from principles, while acknowledging the
   strong consumer preference for the shadcn/Tailwind/Vercel dialect. Achieve
   parity without agent-hostile class soup or oversized frameworks.
3. **Scope:** artifact + default theme rework + example-app refresh. The
   examples are the proof.
4. **Ingredients (all approved):** vendored Lucide SVG icon system; self-hosted
   variable UI font; first-class dark mode; systematic micro-motion & states.
5. **Parity gate:** blind vision-judge panel + composition-pipeline taste
   scores. Not eyeball-only, not endless tweaking.
6. **Approach:** oracle-first (approach B) — build and baseline the parity gate
   before any aesthetic work; write the taste artifact against observed
   evidence; converge in judged slices. Two contrasting example apps are the
   iteration vehicles; the full fleet is judged at the end.

## Architecture: five phases

### Phase 0 — The oracle (parity gate)

- **Reference library.** A capture script (Playwright, reusing `composition
  capture` machinery) screenshots ~6–10 canonical shadcn/Vercel-dialect
  surfaces — e.g. ui.shadcn.com/examples dashboard, the taxonomy demo, Vercel
  dashboard/marketing surfaces — at fixed viewports, light and dark.
  Screenshots are **gitignored** (third-party content: commit the script, never
  the pixels), stored under `.dazzle/composition/references/taste/`.
- **Blind judge panel.** Extend the `composition` pipeline with a `taste`
  focus: N independent vision-LLM judges receive shuffled, identity-stripped
  screenshots (references and Dazzle examples interleaved) and score each
  screenshot on the rubric dimensions defined in the taste artifact. Judges
  never know which screenshots are ours — blind interleaving is what keeps the
  gate honest.
- **Baseline.** Run the panel plus the existing `composition report` against
  all 12 example apps before any aesthetic change, and commit the scores
  (small JSON + markdown). This "before" record makes the effort measurable.
- **Parity definition.** Per rubric dimension, Dazzle's fleet mean must land
  within a defined margin of the reference mean. The exact margin is fixed in
  Phase 0 once baseline variance is known (it must be wider than judge noise,
  measured by re-running judges on identical inputs).

### Phase 1 — The taste artifact

`docs/reference/taste.md`, following the proven card-safety-invariants
pattern: canonical doc, machine-enforced where possible, drift-gated where
cheap. Three strata:

**Principles** (prose — the why; refined against Phase 0 evidence):

1. **Semantic surface, expressive result.** One root class + `data-dz-*`
   modifiers; tokens carry the aesthetic. Agent-hostile class soup is a rule
   violation, not a style choice.
2. **Type does the hierarchy.** A disciplined scale and weight system carries
   visual importance — not boxes and chrome.
3. **One accent; neutrals do the work.** Color appears when it means
   something.
4. **Depth is information.** Elevation encodes layering and interactivity,
   never decoration.
5. **Motion confirms, never entertains.** 100–200ms, `prefers-reduced-motion`
   honored everywhere.
6. **Dark is a material, not an inversion.** Elevation-via-lightness,
   recalibrated contrast and shadows.
7. **Density with rhythm.** Data-dense, but every gap sits on the spacing
   scale.
8. **Every state is designed.** Hover, focus, active, disabled, loading,
   empty, error — no browser defaults showing through.

**Numbered rules** (`TASTE-1…n` — concrete, checkable). Examples of the
intended register: "focus ring: 2px accent at 40% alpha, offset 2px, on every
interactive element"; "shadows are stacked low-alpha pairs, never single hard
drops"; "one accent hue per app; semantic tones come from the fixed ramp".
Final rule set is written in Phase 1 against Phase 0's observed deficits.

**Rubric dimensions** (what the judges score). Phrased as generic design
quality — **not** "how much does this resemble shadcn" — which is the primary
Goodhart guard: typographic hierarchy, spatial rhythm, color discipline, state
completeness, dark-mode integrity, perceived craft.

### Phase 2 — Foundations

- **Token sheet v2** (`design-system.css` / `tokens.css`): full OKLCH neutral
  ramps (~12 steps, separately designed light and dark ramps), one accent
  ramp, semantic tones mapped onto ramps, stacked-shadow tokens, focus-ring
  tokens, motion tokens. The custom-property surface is preserved — the theme
  resolver, `[data-theme]`/`[data-theme-name]` switching, and shipped themes
  keep working.
- **Self-hosted variable font:** vendored woff2, `font-display: swap`,
  preloaded. **Decision: Geist** (James's call — start with the dialect's own
  face and see what happens; OFL. Geist Mono for `--font-mono`. Inter remains
  the fallback candidate if Geist underwhelms in the judged slices; enable
  tabular-numeral feature settings for data-dense tables either way).
- **Icon system:** vendor a curated Lucide subset (~120 icons, ISC license
  file included) as SVG path data in a generated Python registry
  (`src/dazzle/render/fragment/icons.py`, marked `# AUTO-GENERATED`,
  regeneration script + drift gate). A new `Icon` fragment primitive renders
  inline `<svg>` — no JS, no icon font, no CDN. Semantic mapping conventions:
  action→icon (create/edit/delete/search/filter…), status→icon (reconciled
  with the existing #1493 `badge_icon_html` WCAG glyphs), nav→icon.
- **First-class dark mode:** designed dark neutral ramp; surfaces lighten with
  elevation; borders replace shadows where shadows die; WCAG-checked token
  pairs. Switching mechanism unchanged.
- **Micro-motion & states:** systematic interactive-state coverage in
  component CSS (hover/focus-visible/active/disabled/loading), press feedback,
  focus rings. Skeleton shimmer already exists (skeleton+hydrate) and is tuned,
  not rebuilt.

### Phase 3 — Component pass

Sweep the 17 component CSS families (buttons, forms, tables, badges,
dashboard/regions, detail, nav) to embody the new tokens; integrate icons at
the natural points (nav items, empty states, table row actions, status
badges). Markup changes are limited to icon insertion. That churns HTML
goldens and UX-walk baselines — re-baselined deliberately with full-suite runs
(golden-master, viewport-geometry, and contract gates all react differently to
the same change). **Card-safety invariants stay green throughout — they are
the floor under this work.**

### Phase 4 — Examples + convergence

Two vehicles iterate first: **`ops_dashboard`** (dense workspace) and
**`design_studio`** (content-forward). Slice → re-judge → slice until both
clear the gate. Then the full 12-example fleet is judged; stragglers get
per-app theme/sitespec fixes. Final deliverable: a convergence report
(before/after scores per app per dimension) committed alongside the baseline.

## Machine gates that outlive the effort

1. **WCAG contrast unit test** over token pairs — pure function of the token
   sheet; closes a named gap.
2. **Icon registry drift gate** — registry ↔ vendored source ↔ regeneration
   script.
3. **Taste rubric in `composition analyze`** — permanent; this is the
   follow-on evaluation loop, pre-wired for the improve lanes.

## Error handling / failure modes

- **Judge noise:** measured in Phase 0 by re-running judges on identical
  inputs; the parity margin must exceed it, otherwise the gate is theater.
- **Judge-chasing (Goodhart):** principles are written first-class before
  iteration begins; rubric dimensions are dialect-neutral; James retains veto
  on any slice that scores well but looks wrong.
- **Baseline churn:** icon markup re-baselines goldens and walks — budgeted
  into Phase 3; the IR-field lesson applies (run the full suite, `-k` filtered
  runs give false confidence).
- **Viewport-geometry gates** assert region grid geometry; spacing changes may
  trip them. Gates are updated in the same change that moves the geometry (the
  #1494 lesson: `skip_if_absent`-style gate evolution, never gate deletion).
- **`dist/` rebuild** after CSS/JS changes, after version bump — standing trap
  (`build_dist.py`).
- **Model-driven failure modes check (CLAUDE.md rule):** this effort adds no
  new DSL construct or escape hatch; the taste rubric is a detector-backed
  quality dimension (MDF question 2/3: the detector is `composition analyze`,
  live in the improve loop, not merely documented).

## Testing

- All existing gates stay green per slice: card-safety, UX contracts,
  guide/interaction walks, viewport geometry, e2e, golden masters
  (re-baselined only where markup deliberately changed).
- New unit gates land with their features: contrast test with token sheet v2,
  drift gate with the icon registry.
- The oracle itself is the acceptance test: Phase 4 ends when the fleet clears
  the parity margin on every rubric dimension.

## Explicit decision points resolved

| Decision | Choice |
|---|---|
| Font | Geist + Geist Mono (variable, self-hosted, OFL); Inter is the fallback candidate |
| Icon set | Lucide (curated ~120 subset, vendored SVG paths, ISC) |
| Reference screenshots | Gitignored; capture script committed |
| Artifact home | `docs/reference/taste.md` (card-safety pattern) |
| Iteration vehicles | `ops_dashboard` + `design_studio` |
| Parity margin | Fixed in Phase 0 after measuring judge noise |

## Out of scope (follow-ons this design enables but does not build)

- Authoring-agent taste guidance (MCP op / skill consuming `taste.md`).
- Per-app taste derivation from domain/persona.
- Framework-level visual tier-2 lane in the improve loop (the rubric makes it
  possible; wiring it is follow-on).
- Replacing the shipped `linear-dark` / `paper` / `stripe` themes — they
  remain as alternates on top of token sheet v2.
