# HaTchi-MaXchi — the Dazzle House Aesthetic

Canonical, agent-readable definition of Dazzle's visual taste — the
**HaTchi-MaXchi** style (pronounced "hachi machi"; the capitals spell its
HTMX substrate). Consumed by: framework CSS/token authors (now), the
authoring agent and the improve loop (follow-ons).

**Ship floor vs advisory taste (2026-07-11, epic #1580 Phase D):**

| Path | Role | Blocks CI / ship? |
|------|------|-------------------|
| Dual-locks + `pytest -m gate` + package suite | Structural / DOM regression floor | **Yes** |
| Subscription visual smoke (`scripts/hm_visual_smoke.py`) + host **Read** of PNGs | Cognitive review without metered APIs | **No** (`ship_gate: false` in manifest) |
| Pixel-diff of fleet captures (subscription) | Deterministic visual regression when used | Only when the **change author** opts in as a gate |
| `dazzle qa taste-panel` / `component-vision` | Blind LLM aesthetic parity (metered) | **No** unless a human sets a threshold *and* API credits are intentional |

CI stays deterministic. Vision scores never block green solely because a model
scored low.

### Subscription vision scores (no metered API)

Two playbooks — both bill cognition to the **host harness subscription**
(Claude Code Task / Grok Build Read / similar). Neither calls
`anthropic.Anthropic().messages.create`.

| Scope | Capture | Judge | Strategy / CLI |
|-------|---------|-------|----------------|
| Example-app fleet | `dazzle qa capture` | Subagent **Reads** PNGs → findings JSON | `.claude/commands/improve/strategies/visual_tier2_subagent.md` |
| HM dual-lock exemplars | `scripts/hm_visual_smoke.py` | Subagent **Reads** PNG → taste dimension scores | `scripts/hm_subscription_vision.py` |
| HM GitHub Pages gallery | `scripts/hm_pages_vision.py --capture` | Subagent **Reads** PNGs → findings + scores | `scripts/hm_pages_vision.py` |

```bash
# Dual-lock smoke → subscription scores
python scripts/hm_visual_smoke.py --dazzle-emit
python scripts/hm_subscription_vision.py --from-smoke --write-prompt
# → .dazzle/hm-subscription-vision-prompt.txt
# Dispatch host subagent (or Read PNGs in-session); Write scores JSON; then:
python scripts/hm_subscription_vision.py --ingest .dazzle/hm-visual-scores-raw.json
# → .dazzle/hm-visual-scores.json  (ship_gate: false, billing: subscription-host-read)
```

Avoid for day-to-day agent loops: `dazzle qa taste-panel` / `component-vision`
(those still use the metered vision client in `taste_panel.score_image`).

Also enforced by: the opt-in `composition analyze` taste focus (`focus=["taste"]`),
and the per-rule gates listed below. The blind taste panel remains available for
parity campaigns when credits exist — not the default ship gate.

- Spec: `docs/superpowers/specs/2026-07-02-taste-house-aesthetic-design.md`
- Baseline: `dev_docs/taste/baseline-2026-07-02.md` (all six dimensions
  FAIL; fleet 2.4–3.2 vs references 5.1–5.8 on a 10-point scale)
- Rubric source of truth: `src/dazzle/core/taste_rubric.py` (this document
  is drift-gated against it by `tests/unit/test_taste_doc_drift.py`)

**Parity target, not mimicry.** HaTchi-MaXchi competes with the
shadcn/Tailwind/Vercel dialect on *perceived quality*, never on mechanism:
semantic root classes + `data-dz-*` modifiers + design tokens, no
utility-class proliferation, no client-state framework. The judged rubric is
deliberately dialect-neutral (Goodhart guard).

## Principles

1. **Semantic surface, expressive result.** One root class per component +
   `data-dz-*` modifiers; tokens carry the aesthetic. Agent-hostile class
   soup is a rule violation, not a style choice.

2. **Type does the hierarchy.** A disciplined scale and weight system
   carries visual importance — headings, labels, values and captions each
   have a recognisable role. Boxes and chrome never substitute for type.

3. **One accent; neutrals do the work.** Color appears when it means
   something. Neutral ramps carry structure; the accent marks the primary
   action or focus; semantic tones (success/warning/danger) are reserved
   for meaning.

4. **Depth is information.** Elevation encodes layering and interactivity —
   never decoration. Shadows are stacked, low-alpha, and consistent per
   elevation level.

5. **Motion confirms, never entertains.** 100–200ms, derived from the
   request lifecycle, honoring `prefers-reduced-motion` everywhere.

6. **Dark is a material, not an inversion.** A designed dark neutral ramp;
   elevation reads through lightness; accents and semantic tones are
   recalibrated for the dark context.

7. **Density with rhythm.** Data-dense, but every gap sits on the spacing
   scale; related items cluster, unrelated items separate.

8. **Every state is designed.** Hover, focus, active, disabled, loading,
   empty, error — no browser defaults showing through, no accidental empty
   regions.

9. **The structure is the style.** The HaTchi-MaXchi signature: HTMX4
   anatomy is expressed, not hidden. Swap targets read as coherent surfaces,
   `hx-indicator` and the htmx request-lifecycle classes drive the
   loading/motion language (skeleton shimmer, settle transitions), boosted
   navigation feels like part of the material. The design language and the
   transport share one skeleton — a differentiator no client-state dialect
   can copy honestly.

## Rules

Each rule states its motivating baseline evidence and its enforcement.
Rules marked *advisory* become gated as Phases 2–3 land the machinery.

- **TASTE-1** — Every interactive element gets a designed focus ring: 2px
  accent at ~40% alpha, 2px offset, on `:focus-visible`. *(Principle 8;
  evidence: state_completeness gap 2.46 — judges saw browser-default
  focus/affordances. Enforcement: token + component CSS in Phase 2;
  panel dimension `state_completeness`.)*

- **TASTE-2** — Shadows are stacked low-alpha pairs bound to elevation
  tokens; never a single hard drop-shadow, never ad-hoc values.
  *(Principle 4; evidence: perceived_craft gap 3.24, the widest and
  most judge-agreed gap. Enforcement: shadow tokens in Phase 2; panel
  `perceived_craft`.)*

- **TASTE-3** — One accent hue per app, applied to the primary action and
  active states only; all other structure comes from the neutral ramp;
  semantic tones only where they carry meaning. *(Principle 3; evidence:
  color_discipline gap 2.59 — accent exists but semantics muddy.
  Enforcement: token sheet v2 ramps; panel `color_discipline`.)*

- **TASTE-4** — Every gap, padding and margin sits on the spacing scale;
  no off-scale one-off values in component CSS. *(Principle 7; evidence:
  spatial_rhythm gap 2.75. Enforcement: advisory until the Phase 3
  component pass; panel `spatial_rhythm`.)*

- **TASTE-5** — Text roles are typographically distinct: page title,
  section heading, label, value, caption each differ in at least two of
  size/weight/color-step. Tabular numerals in data tables. *(Principle 2;
  evidence: typographic_hierarchy gap 2.44 — "near-uniform text sizes".
  Enforcement: type-scale tokens + Geist in Phase 2; panel
  `typographic_hierarchy`.)*

- **TASTE-6** — Icons come only from the vendored Lucide registry via the
  `Icon` fragment primitive — inline SVG, sized on the type scale, never
  icon fonts, emoji-as-UI, or ad-hoc SVGs. *(Principle 1/8; evidence:
  perceived_craft — "no icon language" was a recurring judge note.
  Enforcement: icon registry drift gate, Phase 2.)*

- **TASTE-7** — Dark mode uses the designed dark ramp: surfaces lighten
  with elevation, borders replace shadows where shadows die, accents and
  semantic tones are dark-recalibrated. Never a naive inversion.
  *(Principle 6; evidence: dark_mode_integrity 3.13 — "inverted-looking".
  Enforcement: dark ramp tokens + WCAG pair test, Phase 2; panel
  `dark_mode_integrity`.)*

- **TASTE-8** — Empty states are designed: an icon, one sentence, and the
  primary action — never a bare "No X yet" line in an otherwise blank
  card, and never an unexplained blank region. *(Principle 8; evidence:
  worst-scoring screens were empty/denied workspaces, down to 1.27.
  Enforcement: advisory until Phase 3; panel `state_completeness`.)*

- **TASTE-9** — Loading and settling states derive from the htmx request
  lifecycle (`hx-indicator`, request/settle classes → skeleton shimmer,
  100–200ms settle transitions), with `prefers-reduced-motion` honored.
  *(Principle 9/5; evidence: not judgeable from stills — enforced by the
  interaction walks, not the panel. Advisory until Phase 2 motion tokens.)*

- **TASTE-10** — Corner radii come from the radius scale and are
  consistent per component family (inputs and buttons share a radius;
  cards share a larger one). *(Principle 1/4; evidence: perceived_craft —
  "inconsistent radii/borders". Enforcement: token sheet v2; panel
  `perceived_craft`.)*

- **TASTE-11** — Text contrast meets WCAG AA against its actual surface
  token in both themes; the token sheet is the unit under test.
  *(Principle 6/3. Enforcement: contrast unit test over token pairs,
  Phase 2 — closes a named gap: no machine contrast gate exists today.)*

- **TASTE-12** — No utility-class accretion: components keep one semantic
  root class + `data-dz-*` modifiers; new visual variation goes through
  tokens or a modifier, never a class pile. *(Principle 1. Enforcement:
  existing card-safety/contract scanners keep the floor; advisory beyond
  that.)*

## Rubric

The judged dimensions live in `src/dazzle/core/taste_rubric.py` (single
source of truth; this table is drift-gated).

| Key | Title | Applies to |
|---|---|---|
| `typographic_hierarchy` | Typographic hierarchy | both |
| `spatial_rhythm` | Spatial rhythm | both |
| `color_discipline` | Color discipline | both |
| `state_completeness` | State completeness | both |
| `dark_mode_integrity` | Dark-mode integrity | dark |
| `perceived_craft` | Perceived craft | both |

Composition note: `composition analyze focus=["taste"]` runs the
theme-agnostic five; `dark_mode_integrity` must be requested by name
against known-dark captures (composition captures carry no theme info).

## The parity campaign (advisory unless human-thresholded)

Metered blind-panel runs measure fleet parity vs references. They feed improve
backlog and Phase 2–4 taste *campaigns*; they are **not** a default CI ship
gate (see table above). Prefer `hm_visual_smoke.py` + host Read for day-to-day
agent review.

```
# capture references (third-party pixels stay gitignored)
python scripts/taste/capture_references.py

# capture the fleet, per app (above-fold + dark are REQUIRED for parity)
dazzle qa capture --app <app> --url <URL> --above-fold --manifest fleet.json
dazzle qa capture --app <app> --url <URL> --above-fold --dark --manifest fleet-dark.json

# run the blind panel (exit 0 = parity on every dimension) — requires API credits
dazzle qa taste-panel --manifest fleet-merged.json --judges 3 --noise-runs 2
```

The panel top-crops every image to the reference frame
(`normalize_pool_frames`), interleaves sources blindly, and applies
per-dimension margins locked by the 2026-07-02 baseline:
`margin = max(0.5, 2 × judge noise SD)` —

| Dimension | Locked margin | Baseline gap |
|---|---|---|
| perceived_craft | 0.50 | 3.24 |
| spatial_rhythm | 0.82 | 2.75 |
| color_discipline | 1.63 | 2.59 |
| state_completeness | 0.58 | 2.46 |
| typographic_hierarchy | 1.15 | 2.44 |
| dark_mode_integrity | 1.15 | 1.97 |

Phases 2–4 (foundations → component pass → example convergence) end when
the fleet clears every margin. Protocol invariants for re-judging: same
frame, same rubric, unseeded apps, persona-matched workspace sampling
(fixing the `_platform_admin` over-selection noted in the baseline).
