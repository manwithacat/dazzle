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
  owned by HM (the larger reservoir). Baseline 2026-07-08: **869** across 7 files
  (`dz.css`, `dazzle-layer.css`, `dz-widgets.css`, `utilities.css`, `dazzle.css`,
  `dz-tones.css`, `dazzle-framework.css`). Excludes site-chrome scaffolding
  (`reset.css`, `feedback-widget.css`, `site-sections.css`).

Baseline snapshot: `.dazzle/hm-reservoir-baseline.json` (regenerate with
`--write-baseline` only when intentionally re-anchoring).

> **v1 caveat.** `css_lines_dazzle_native` is a coarse proxy — some of these files
> carry HM-alignment references and a few rules may already be HM-dist-sourced. The
> lane's first explore cycle (the reservoir audit) refines the HM-vs-Dazzle-native
> classification file-by-file before large moves.

## Regression detector (every cycle, cheap)

Run the metric and compare to `.dazzle/hm-reservoir-baseline.json`:
- Either number **rose** → a `HMC` regression: new Tailwind/legacy layout entered an
  emitter or a new Dazzle-native CSS rule was added instead of authoring in HM.
  File an `HMC-NNN` row (status `REGRESSION`) naming the file(s); the driver's rule 1
  picks it up. Do NOT re-anchor the baseline to hide it.
- Numbers **fell** → progress; update the row(s), emit `hm-convergence-progress`.

## Explore phase (when no actionable rows)

Sub-strategies, pick the highest-leverage:

1. **reservoir_audit** (run first, once) — map each Dazzle-native CSS file to its HM
   target: which rules belong in an HM `base`/`components` layer, which are already
   HM-dist-sourced (reclassify — not reservoir), which are genuinely legacy (e.g.
   `dz-widgets.css` DaisyUI overrides). Output `HMC-NNN` migration rows, one per
   coherent CSS chunk. This is the "full HM-reservoir audit" the governance rollout
   deferred to the loop.
2. **css_migration** — take one `HMC` migration row: move that CSS chunk into the HM
   package (`packages/hatchi-maxchi/`), rebuild the HM dist (`build.py`), repoint
   Dazzle to consume it, delete the Dazzle-native copy. Verify: `dazzle qa taste-panel`
   (blind parity) stays green + no visual-baseline dance + the reservoir metric fell.
3. **markup_drain** — retire the residual emitter Tailwind tokens (the spinner
   `opacity-*`) into semantic `dz-*`/HM classes. When `total_tailwind_tokens` hits 0,
   **delete the legacy Tailwind detection path in `contract_checker._has_card_chrome`**
   (the migration debt Phase 1 flagged) and its legacy fixtures.
4. **taste_gate** — run `dazzle qa taste-panel` (the blind fleet-vs-dialect aesthetic
   gate this lane co-owns) and act on regressions vs the baseline in
   `dev_docs/taste/`.

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
- **Blind parity is the safety net.** Every migration is gated by `dazzle qa taste-panel`
  staying green — the number falling is necessary, not sufficient.
- **No baseline laundering.** Re-anchor `.dazzle/hm-reservoir-baseline.json` only on a
  genuine, logged progress checkpoint — never to paper over a rise.
