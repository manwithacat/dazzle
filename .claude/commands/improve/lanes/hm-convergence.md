# Lane: hm-convergence

Standing directive (2026-07-08): **all frontend design lives in HaTchi-MaXchi
(HM)** — design system, tokens, layout. Dazzle emits markup + consumes HM dist.

## Status: drain COMPLETE

The Tailwind / Dazzle-native CSS **drain campaign finished** (reservoir grand
total 0). This lane is no longer a “pick a CSS file and delete/port it” loop.

**Remaining work** (quality locks + tooling depth — see
`docs/superpowers/plans/2026-07-11-hm-sophistication-plan.md`):

- Expand dual-locks (contract modules + schema/DOM gates)
- Subscription vision / taste policy (`docs/reference/taste.md`)
- Author new design **only** in `packages/hatchi-maxchi/`
- Keep permanent zero-floors green (below)

**Backlog section:** `## Lane: hm-convergence` in `improve-backlog.md` (`HMC-NNN`
rows). Historical aggressive-mode drain playbooks are retired; do not re-open
file-batch CSS deletion cycles unless a floor is red.

## Permanent floors (always on)

```bash
# Markup Tailwind + residual Dazzle design CSS (must both be 0; exit 1 if red)
python scripts/hm_tailwind_reservoir.py
python scripts/hm_tailwind_reservoir.py --json

# Exact served CSS allowlist (stronger CSS boundary — KEEP/MIGRATING)
# tests/unit/test_hm_delegation_proof.py  (gate suite)

# Optional classifier when touching HM or residual chrome
python scripts/hm_css_classify.py
python scripts/hm_css_classify.py --tokens-only
```

| Floor | Gate | Owns |
|-------|------|------|
| No Tailwind utilities in emitters | `test_hm_tailwind_reservoir` (`total_tailwind_tokens == 0`) | `class="…"` literals under `src/dazzle/render` + `page` |
| No residual Dazzle design CSS lines | same test (`css_lines_grand_total == 0`) | belt-and-braces |
| Exact CSS set | `test_hm_delegation_proof` | every served Dazzle-native stylesheet is allowlisted |

A red floor is a regression: restore zero (delete utility classes / move CSS to
HM / document a deliberate KEEP) — do **not** reintroduce a shrink-baseline
ceremony. Port-suggestion / `--write-baseline` drain tooling is retired.

## Hard rules (still load-bearing)

- **Author in HM, not Dazzle.** New design-system/token/layout CSS goes into the
  HM package and is consumed via dist — never a fresh rule in
  `src/dazzle/.../css/` (except documented KEEP in the delegation allowlist).
- **Functional gates over pixel perfection** for structural changes; subscription
  vision is advisory (never a ship gate). See Verification gate below.

## Verification gate (how to prove a change is safe)

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

## Actionable work when floors are green

Dual-lock expansion is the **primary** remaining product work for this lane.
Do **not** treat empty historical HMC drain rows as "lane idle" — consult the
machine queue first.

```bash
python packages/hatchi-maxchi/tools/dual_lock_queue.py --top 5
python packages/hatchi-maxchi/tools/dual_lock_coverage.py --write
```

| Signal | Action |
|--------|--------|
| Gallery probe FAILs / OWNED-IDLE `hm gallery interaction probes` | Run strategy **`gallery_probes`** — forceable via `/improve hm-convergence gallery_probes` |
| Queue depth > 0 | Run strategy **`dual_lock_expand`** (playbook below) — forceable via `/improve hm-convergence dual_lock_expand` |
| Queue empty + floors green + probes green | **dual_lock_visual_smoke** or HOUSEKEEPING; hand back to driver for other lanes |
| Floor red | Fix floor; never expand dual-locks on a red reservoir |

### Explore / promote strategies

1. **gallery_probes** — deterministic **interaction** contracts (Playwright) for
   gallery Hyperparts. Catches multi-open menubars, nav panels, etc. that dual-lock
   and static vision miss. Tool:
   `python scripts/hm_gallery_probes.py --run` (also `--discover`,
   `--validate-observation`). Playbook: **`improve/strategies/gallery_probes.md`**.
   Force: `/improve hm-convergence gallery_probes`. Prefer when capability map
   shows OWNED-IDLE / STALE for `hm gallery interaction probes`, or a human HMG
   observation needs machine validation.
2. **shadcn_parity** — close catalogue gaps vs shadcn/ui (placeholder Hyperparts
   first). Inventory: `python packages/hatchi-maxchi/tools/shadcn_parity.py --gaps-only`.
   Map: `packages/hatchi-maxchi/SHADCN_PARITY.md`. Playbook:
   **`improve/strategies/shadcn_parity.md`**. Force:
   `/improve hm-convergence shadcn_parity`. Prefer when `gap` count > 0 and
   the dual-lock queue is not more urgent (operator judgment / force path).
3. **dual_lock_expand** (default for existing surfaces) — promote the top
   dual-lock queue candidate(s) to schema+DOM (or DOM-only). Full cycle recipe:
   **`improve/strategies/dual_lock_expand.md`**.
   Queue tool: `packages/hatchi-maxchi/tools/dual_lock_queue.py`.
   Coverage: `packages/hatchi-maxchi/DUAL_LOCK_COVERAGE.md`.
4. **dual_lock_visual_smoke** (subscription default after a promote) — run
   `python scripts/hm_visual_smoke.py --dazzle-emit`.
   Output in gitignored `.dazzle/hm-visual-smoke/` (+ `.dazzle/hm-visual-last.json`).
   Structured scores without metered API:
   `python scripts/hm_subscription_vision.py --from-smoke --write-prompt` + host
   Read of PNGs; ingest with `--ingest`. Never a ship gate.
5. **dead_prune** — 0-reference class prune across **all** of `src/dazzle`
   (incl. top-level `page/*.py`), `tests/`, and JS dynamic construction
   (`'dz-x-' + var`). Grep-by-full-class misses JS-built names.
6. **legacy_card_chrome_retirement** (optional, careful) — the
   `_has_card_chrome` Tailwind-shaped branch is defence-in-depth only; delete
   only with a dedicated gate plan and fixture audit (emitters already at 0).
7. **taste_gate** (optional, credits-permitting) — aesthetic pass vs
   `dev_docs/taste/`; billing-blocked by default. Policy: `docs/reference/taste.md`.

Historical sub-strategies `reservoir_audit` / `css_migration` / `markup_drain`
are retired (floors already 0). Reopen only if a floor is red.

### Backlog rows for dual-locks

Use `HMC-NNN` with `scope` = `dual_lock <stem>` and status
`PENDING` / `IN_PROGRESS` / `DONE`. Seed from the queue when the lane is
picked and no dual-lock row is already `IN_PROGRESS`. The queue is the
authority for *what* is left; the backlog is the cycle ledger.

## Owns (capability-map)

Zero-floor + delegation gates, dual-lock expansion, subscription vision / taste
tooling, and any remaining contract_checker legacy-Tailwind retirement when that
path is deleted. Read `docs/reference/taste.md` before styling work.

## Outcome

Return `{status: PASS|FAIL|BLOCKED|EXPLORED|HOUSEKEEPING, summary, signals_to_emit,
budget_consumed}`. Prefer dual-lock / sophistication work when floors are green.
Consumes `dazzle-updated` after a release (re-check floors). Ship discipline for
HM + Dazzle changes: bump + HM dist rebuild + Dazzle dist rebuild + push.
