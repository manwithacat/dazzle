# Plan: HaTchi-MaXchi sophistication + Dazzle tooling

**Date:** 2026-07-11
**Status:** Active
**Owner:** monorepo (Dazzle + `packages/hatchi-maxchi`)
**Source evaluation:** session analysis of HM package + dual-locks + vision/reservoir tools

## Goal

Raise the sophistication of (1) HM as a design system and (2) Dazzle tools that keep Dazzle and HM honest — without treating LLM taste as a ship gate.

**Success looks like:**
- Every controller-bearing Hyperpart has a formal contract (or an explicit, shrinking exception).
- Dual-lock coverage is greppable and CI-enforced for the contracted set.
- Reservoir / drain tools can *suggest* ports, not only count debt.
- Vision/taste tools can optionally close the loop when billing allows — never required for green CI.

## Non-goals

- Pixel-perfect redesign of the whole gallery in one pass.
- Replacing dual-locks with vision judges.
- Expanding HM CDN packaging / tree-shaking (separate product track).

## Context (baseline 2026-07-11)

| Surface | Count |
|---------|------:|
| Component CSS modules | 62 |
| Controllers (`dz-*.js`) | 19 |
| Formal contract modules | 19 |
| Schema + DOM dual-lock (`CONTRACT_MODELS`) | 4 (grid_edit, combobox, tags, money) |
| Root-only dual-lock (`DOM_ONLY_CONTRACTS`) | 15 (incl. confirm, pdf, wizard, master_detail) |
| Root-only deferred (contract exists, no DOM lock fixture) | 0 (drained) |

Reservoir metric (`scripts/hm_tailwind_reservoir.py`): **GRANDTOTAL 0** — migration thermometer is drained; remaining work is *quality locks* and *tooling depth*, not Tailwind drain.

## Phases

### Phase A — Measurement (inventory)

**Deliverables**
1. Living coverage map: Hyperpart × (CSS | controller | contract | schema lock | DOM lock | Dazzle emitter).
2. Script to regenerate the map from repo state (no hand-maintained tables that rot).
3. GitHub epic + child issues for B–D.

**Exit:** Agents can answer “what is dual-locked?” in one greppable artifact.

### Phase B — Contract factory + dual-lock expansion (high ROI)

**Deliverables**
1. Scaffold: registry id / contract stem → stub `contracts/<part>.py` (model + DOM_CONTRACT + exemplars + render).
2. Promote deferred DOM locks where emission is stable (priority queue).
3. Expand schema dual-locks for high-churn form/table parts still root-only if a real ingest model exists.
4. Policy: new controller without contract fails CI (PENDING shrink-only already partial).

**Exit:** Dual-lock set grows intentionally each release; no silent uncontracted controllers.

### Phase C — Smarter convergence tooling

**Deliverables**
1. Reservoir tool gains *port suggestions* (rule → candidate HM component / duplicate selector).
2. Load-bearing CSS classifier (display/z-index/pointer vs pure aesthetic) for aggressive drain safety.
3. Optional: monorepo stylelint-or-equivalent for token literals outside `tokens.css`.

**Exit:** A drain PR can be proposed with mechanical evidence, not only agent taste.

### Phase D — Taste closed-loop (optional, billing-aware)

**Deliverables**
1. Subscription default: `scripts/hm_visual_smoke.py` on dual-locked exemplars +
   Dazzle emission (`--dazzle-emit`); host-harness **Read** of PNGs.
2. Persist last-run pointer under gitignored `.dazzle/hm-visual-last.json`
   (and PNG/manifest under `.dazzle/hm-visual-smoke/`).
3. Document: vision never blocks ship without human threshold; dual-locks + gate
   suite remain the floor. Metered `component-vision` / `taste-panel` only when
   credits are intentional.

**Exit:** Taste tools feed improve backlog on the subscription path; CI stays deterministic.

## Working agreements

- Dual-locks and package suite gates are the regression floor.
- `dazzle qa taste-panel` / component-vision are advisory unless credits + human threshold.
- Prefer monorepo edits in `packages/hatchi-maxchi/`; subtree sync remains the publish path.
- Update this plan’s “Progress” section when a phase exits.

## Cost model (subscription-first)

Prefer **in-subscription** paths over metered vision/LLM APIs:

| Task | Preferred | Avoid (unless credits intentional) |
|------|-----------|-------------------------------------|
| Screenshots | Playwright (`dazzle qa capture`, `scripts/hm_visual_smoke.py`) | — |
| Visual judgment | Host-harness subagent **Read**s PNGs | `dazzle qa component-vision` / `taste-panel` |
| Regression | Dual-locks + gate suite + pixel-diff of captures | Vision score deltas as ship gates |
| Explore fleet UX | `visual_tier2_subagent` strategy | API-bound visual scrape CLIs |

`scripts/hm_visual_smoke.py` renders dual-locked exemplars with local HM dist +
Playwright full-page PNG — no Anthropic/OpenAI call.

## Progress

| Phase | Status | Issue | Notes |
|-------|--------|------:|-------|
| A | **Done** | #1581 | Plan + coverage generator + map + gate test |
| B | **Done** | #1582 | confirm/pdf/wizard/master_detail dual-locks; dual_pane_flow emits Hyperpart |
| C | **Done** | #1583 | `--suggest` + `hm_css_classify.py` (load-bearing + token literals) |
| D | **Done** | #1584 | Subscription smoke + last-run pointer; taste.md ship-vs-advisory policy |

**Epic:** #1580 — phases A–D complete. Metered vision score persistence remains
optional follow-on if API credits are intentional (not required for D exit).

## Related paths

- HM package: `packages/hatchi-maxchi/`
- Coverage map: `packages/hatchi-maxchi/DUAL_LOCK_COVERAGE.md`
- Coverage generator: `packages/hatchi-maxchi/tools/dual_lock_coverage.py`
- Dual-lock registry: `tests/unit/hm_contract_registry.py`
- Reservoir: `scripts/hm_tailwind_reservoir.py`
- CSS classify (Phase C): `scripts/hm_css_classify.py`
- Taste ship policy: `docs/reference/taste.md` (ship floor vs advisory)
- Improve lane: `.claude/commands/improve/lanes/hm-convergence.md`
- Vision: `src/dazzle/qa/taste_panel.py`, `component_vision.py`, `property_vision.py`
- Contract authoring: `packages/hatchi-maxchi/contracts/AUTHORING.md`
- Contract scaffold: `packages/hatchi-maxchi/tools/scaffold_contract.py`
- Subscription visual smoke: `scripts/hm_visual_smoke.py`
- dual_pane → master-detail: `src/dazzle/page/runtime/dual_pane_master_detail.py`
