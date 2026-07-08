# Lane: hm-convergence

Drives the standing directive (2026-07-08): **delegate all frontend design —
design system, tokens, layout — into HaTchi-MaXchi (HM).** The lane measures the
remaining reservoir of Tailwind utilities + Dazzle-native design-system CSS, drains
it into HM one target per cycle, and guards against regression (new Tailwind/legacy
layout creeping back into the emitters).

This is the loop's instrument for *finishing* the HM migration rather than leaving it
a manual push. It complements the HM-grid `PLAN.md` arc (LAYOUTS/BLUEPRINTS workstream)
— that builds new HM primitives; this lane retires the legacy substrate they replace.

**Backlog section:** `## Lane: hm-convergence` in `improve-backlog.md` (`HMC-NNN` rows).

## Instrument — the reservoir metric

```bash
python scripts/hm_tailwind_reservoir.py           # human summary
python scripts/hm_tailwind_reservoir.py --json     # machine-readable
```

Two numbers, both must trend to **zero**:
- **`total_tailwind_tokens`** — Tailwind utility classes in the render/page emitters'
  `class="…"` attributes (markup reservoir). Baseline 2026-07-08: **8** (4 files;
  `opacity-25/75` — a spinner). Nearly drained already.
- **`css_lines_dazzle_native`** — lines of Dazzle-native design-system CSS not yet
  owned by HM (the larger reservoir). Baseline (HMC-001 audit, 2026-07-08): **4037**
  across the **13** served files, derived from `css_loader`'s source-of-truth list
  (`CSS_SOURCE_FILES` + `CSS_UNLAYERED_FILES`) minus the HM dist, `vendor/*`,
  `reset.css`, and site-chrome (`site-sections.css`). Biggest: `components/fragments.css`
  (1214), `components/dashboard.css` (596), `components/onboarding.css` (497),
  `components/pdf-viewer.css` (444); the unlayered override trio `dz.css` (234) /
  `dz-widgets.css` (135) / `dz-tones.css` (69) exists specifically to win the cascade
  over the HM dist — the clearest debt.

Baseline snapshot: `.dazzle/hm-reservoir-baseline.json` (regenerate with
`--write-baseline` only when intentionally re-anchoring).

> **HMC-001 correction (2026-07-08).** The v1 metric globbed only top-level `css/*.css`
> and reported **869** — it missed the entire `css/components/` subdir (the bulk) and
> counted non-served reference files. Corrected to derive from `css_loader`; real
> reservoir is ~4.6× larger. Drain order (ratified: Tier-A-first, incremental): the
> legacy/override cruft first — `dz-widgets` (dead DaisyUI overrides), `dazzle-layer`
> (aliases referencing a deleted `design-system.css`, several rules already 0-ref),
> `dz-tones` → HM `tokens/`, `dz.css` → HM `htmx-states.css` — then Tier-B component
> CSS overlapping existing HM components, `fragments.css` last.

## Regression detector (every cycle, cheap)

Run the metric and compare to `.dazzle/hm-reservoir-baseline.json`:
- Either number **rose** → a `HMC` regression: new Tailwind/legacy layout entered an
  emitter or a new Dazzle-native CSS rule was added instead of authoring in HM.
  File an `HMC-NNN` row (status `REGRESSION`) naming the file(s); the driver's rule 1
  picks it up. Do NOT re-anchor the baseline to hide it.
- Numbers **fell** → progress; update the row(s), emit `hm-convergence-progress`.

## Verification gate (how to prove a migration is safe)

**Do NOT rely on `dazzle qa taste-panel` as the gate — its LLM judge is
billing-blocked** (Anthropic API key has no credit balance → 400) *and* it answers
the wrong question (aesthetic quality vs Linear/shadcn refs, not "did this change
rendering?"). The regression gate that works, on the **subscription** (zero API
credits), has two tiers — pick by the change's nature:

**Tier A — byte-faithful move (rule relocation, HM-tokenised, no value change).**
Proof = the *served bundle* emits the rule identically and the cascade winner is
unchanged. Verify with `get_bundled_css()`: the moved selectors appear **once each**,
byte-identical to the pre-move rule, and (if a class is dual-defined) the new HM
component is registered so it still wins source-order ties. Confirm `dz-*` keyframe/token
values aren't silently swapped (hardcoded→token is NOT byte-faithful — that's Tier B).
No fleet capture needed. Precedents: HMC-005 (metric-tile tints), 007b (drawer chrome).

**Tier B — genuinely-visual change (anything a static screenshot would show).**
Run the deterministic capture + pixel-diff loop (the `visual_tier2` idiom — cognitive
work bills to the CC subscription, no API spend):
1. Boot: `dazzle e2e env start simple_task` (daemonises) → URL from `dazzle e2e env status`
   (NOT the port the CLI prints).
2. Capture **before**: `dazzle qa capture --url <URL> --app simple_task -p admin [--dark] -m /tmp/b.json`; snapshot the affected PNGs from `examples/simple_task/.dazzle/qa/screenshots/`.
3. Migrate, rebuild HM + Dazzle dist, **restart the env** (it caches the bundle at boot).
4. Capture **after**; pixel-diff via PIL `ImageChops.difference(before,after).getbbox()`.
5. `None` = identical → pass. **Any diff → investigate before shipping:** crop the bbox
   and Read both crops; re-capture after-vs-after — if the *same* band differs regardless,
   it's a non-deterministic skeleton/lazy-load flake (not your change), not a regression
   (precedent HMC-007c team_overview). A real, reproducible diff blocks the ship.
6. `dazzle e2e env stop simple_task`.

Transient animations (row-highlight easing, spinner) aren't captured by a static
screenshot — for those, reason about token/value equality (Tier A) or defer.
`dazzle qa taste-panel` remains available as an *optional aesthetic-quality* pass **iff
credits are topped up** — never the regression gate.

## Explore phase (when no actionable rows)

Sub-strategies, pick the highest-leverage:

1. **reservoir_audit** (run first, once) — map each Dazzle-native CSS file to its HM
   target: which rules belong in an HM `base`/`components` layer, which are already
   HM-dist-sourced (reclassify — not reservoir), which are genuinely legacy (e.g.
   `dz-widgets.css` DaisyUI overrides). Output `HMC-NNN` migration rows, one per
   coherent CSS chunk. This is the "full HM-reservoir audit" the governance rollout
   deferred to the loop.
2. **css_migration** — take one `HMC` migration row: move that CSS chunk into the HM
   package (`packages/hatchi-maxchi/`), register it in `build.py` (order matters — put a
   component that **dual-defines** a selector *after* the file it must out-win, e.g. the
   Dazzle-side load position it had before), rebuild the HM dist (`build.py`), repoint
   Dazzle to stop bundling the native copy, delete/trim it. **Verify per the Verification
   gate above** — Tier A (byte-faithful) or Tier B (genuinely-visual capture+pixel-diff) —
   AND the reservoir metric fell. Drop, don't duplicate, any keyframe/token HM already owns.
   **Prefer byte-faithful moves** (rules already `var(--…)`-tokenised); a hardcoded→token
   rewrite is a Tier-B visual change, do it as a separate, gated step.
3. **markup_drain** — retire the residual emitter Tailwind tokens (the spinner
   `opacity-*`) into semantic `dz-*`/HM classes. When `total_tailwind_tokens` hits 0,
   **delete the legacy Tailwind detection path in `contract_checker._has_card_chrome`**
   (the migration debt Phase 1 flagged) and its legacy fixtures.
4. **dead_prune** — a section whose classes are 0-reference is a provably-inert prune
   (no gate needed). **Scope the deadness check to ALL of `src/dazzle` (incl.
   `page/*.py` top-level like `command_render.py`, not just `render/`), `tests/`, and JS
   dynamic construction (`'dz-x-' + var`)** — grep-by-full-class MISSES JS-applied and
   dynamically-built classes (fragments.css HMC-009 caught `dz-island`/`dz-error` as
   false-dead this way). Prune only what survives that scope.
5. **taste_gate** (optional, credits-permitting only) — `dazzle qa taste-panel` is an
   *aesthetic-quality* pass vs `dev_docs/taste/`, NOT the regression gate, and is
   billing-blocked by default. Skip unless credits are known-available.

## Owns (capability-map)

`dazzle qa taste-panel`, the Tailwind-reservoir metric, and the contract_checker
legacy-Tailwind retirement. Read `docs/reference/taste.md` before any styling work.

## Outcome

Return `{status: PASS|FAIL|BLOCKED|EXPLORED|HOUSEKEEPING, summary, signals_to_emit,
budget_consumed}`. Emits `hm-convergence-progress` (payload: the two numbers) on a
drop; consumes `dazzle-updated` (re-baseline check after a release). A `css_migration`
that ships HM + Dazzle changes must follow ship discipline (bump + HM dist rebuild +
push) inside the cycle.

## Hard rules

- **Author in HM, not Dazzle.** New design-system/token/layout CSS goes into the HM
  package and is consumed via dist — never a fresh rule in `src/dazzle/.../css/`. That
  is the whole point; a new Dazzle-native rule is the regression this lane exists to catch.
- **Pixel-diff is the regression gate, not taste-panel.** Every genuinely-visual
  migration is gated by the capture + pixel-diff loop (see Verification gate); byte-faithful
  moves by served-bundle equality. The reservoir number falling is necessary, not
  sufficient. `dazzle qa taste-panel` (LLM judge) is billing-blocked and is not the gate.
- **No baseline laundering.** Re-anchor `.dazzle/hm-reservoir-baseline.json` only on a
  genuine, logged progress checkpoint — never to paper over a rise.
