# Silent-Drift Classes in the `/ux-cycle` Loop

**Date:** 2026-04-20 (cycle 317 framework_gap_analysis)
**Class:** Framework loop-discipline completeness
**Status:** Partially addressed — 4 of 6 identified classes now have automated gates; 2 remain manual-inspection-only

## Problem statement

The `/ux-cycle` autonomous loop commits framework code changes ~every 10 minutes but historically ran a narrower quality gate than `/ship`. This mismatch allowed multiple **classes of drift** to accumulate silently — the cycle would pass its own self-checks while real quality regressions piled up invisibly. Cycles 311-316 surfaced 6 distinct classes of this pattern; some are now automatically gated, some still require manual inspection.

## Evidence

| # | Drift class | Surfaced cycle | Gap duration | Detection mechanism | Status |
|---|---|---|---|---|---|
| 1 | **Syrupy baseline drift** — contract_audit cycles add canonical class markers to templates; `test_dom_snapshots.py` baselines don't regenerate | 311 | ~40 cycles (271-311) | `test_dom_snapshots.py` (existing, previously unrun) | **Gated** (cycle 312 preflight) |
| 2 | **UI type-error drift** — hypothetical; no empirical accumulation observed because preflight was added preemptively | 313 (hypothesised) / 314 (gated) | 0 cycles | `mypy src/dazzle_ui/` | **Gated** (cycle 314 preflight) |
| 3 | **Dist/ build artifact drift** — source changes to CSS/JS don't propagate to `dist/` until someone manually rebuilds | 313 | ≥20 cycles (297 → 313 footer CSS var) | `git status` (manual) | **Manual** — no automated gate |
| 4 | **Canonical-helper bypass** — file-local helper wraps raw responses for static-analysis discrimination; some call sites use raw constructor instead | 315 | Unknown (likely years) | Grep-style audit (manual) | **Manual** — one-time cycle fix, no lint |
| 5 | **DaisyUI tokens in Python-embedded HTML** — cycle 17 swept templates; Python string-literal HTML wasn't in scope | 316 | ~300 cycles (17 → 316) | Grep for DaisyUI class names (manual) | **Manual** — one-time cycle fix, no lint |
| 6 | **Snapshot-regeneration discipline in contract_audit strategy** — the strategy spec mentions "regression tests matching each quality gate" but doesn't explicitly require syrupy baseline refresh | 311 → 312 (inferred) | ~14 cycles (271-285) | Skill spec review (process fix) | **Gated** (cycle 312 preflight catches downstream manifestation) |

Related observations from cycles 300-309 that reinforce the theme:
- **Cycle 300 external-resource-integrity** — CDN loads without SRI hashes. Silent trust drift; manually surfaced.
- **Cycle 305 template-ship-without-wiring** — HTML page templates ship without server routes. Eventually gated by cycle 306-308's `test_page_route_coverage.py`.
- **Cycle 309 missing_contracts retrospective** — manual breadth scans for uncontracted components superseded by continuous lints.

Across 20+ cycles, the pattern is consistent: **a class of drift accumulates invisibly until a full test suite run or manual audit surfaces it, then one cycle either (a) adds a gate or (b) manually cleans up**.

## Root cause hypothesis

Three compounding factors:

### 1. Scope asymmetry between `/ux-cycle` and `/ship`

The `/ship` skill runs `ruff check`, `ruff format`, and `mypy` on the entire relevant framework subtree before every push. The `/ux-cycle` skill commits but doesn't push — and (pre-cycle-312) ran no pytest or mypy at all. The cron-fired loop could ship framework code through git for hours before anyone invoked `/ship`, by which point the damage was done.

Cycle 312's preflight gate closed the largest leak (lints + snapshots + card-safety), and cycle 314 added mypy(dazzle_ui). But the gate is deliberately **scoped to <10s** to not balloon the 10-minute cron cadence, which means:
- Broader mypy (dazzle_back, core, cli, mcp) is not in the gate
- `git status` / dist/ rebuild isn't checked
- Linting of Python string literals for embedded HTML class names isn't checked

### 2. Manual sweeps have naming-pattern limitations

Cycle 17's "DaisyUI token sweep" (EX-001) closed at 62 template files. Cycle 316 found 6 more sites in Python string literals. The cycle 17 sweep matched `**/*.html` — it was implicitly scoped. Same pattern for cycle 302's `test_template_orphan_scan.py` — it only finds orphans under `src/dazzle_ui/templates/`, not equivalent orphan Python modules.

**When a sweep's scope is file-extension-based, drift accumulates in adjacent file types using the same pattern.**

### 3. Contract_audit cycles don't have a discipline checklist

The `contract_audit` strategy playbook says (step e) "regression tests matching each quality gate" but doesn't enumerate: does that include snapshot refresh? Mypy check? Grep for DaisyUI tokens? As a result, each contract_audit cycle's hygiene depended on the runner's judgment — and cycles 271-284 consistently forgot to refresh syrupy baselines.

## Fix sketch

Two-axis strategy:

### Axis A — Close remaining gates

**A1: Add broader mypy to a separate, slower gate.**
- Create `make test-ux-deep` target running `mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp src/dazzle_back/runtime` (~13s total). Not part of preflight (keeps cron-cadence tight) but runnable manually or as a pre-commit hook for cycles that touch framework Python.
- Alternative: add dazzle_back/runtime to preflight, accept ~13s gate. Trade-off: 4s extra per cycle = ~24s/hour = 10 minutes/day. Probably worth it given cron cadence is 10 minutes.

**A2: Add `dist/` drift detection.**
- Git-status check as preflight's last step: if `dist/` has uncommitted changes, log a warning (non-blocking, to avoid blocking cycles that happen while a build is in progress).
- Or: require `make build` to complete cleanly; this is what `/ship` implicitly assumes.

**A3: Extend DaisyUI-token lint beyond templates.**
- New horizontal-discipline lint: grep Python source for DaisyUI token patterns (`text-error`, `alert alert-*`, `btn-primary`, etc.). The allowlist handles legitimate uses (dispatch tables, fallback HTML).
- Adds 1 file, ~80 LOC, <0.5s to preflight.

### Axis B — Codify contract_audit hygiene

**B1: Contract_audit checklist.**
Edit the `/ux-cycle` skill's contract_audit strategy description to explicitly list:

> After template edits in contract_audit cycles:
> 1. Run `make test-ux-preflight` — this catches snapshot drift
> 2. If snapshots fail, verify diff is additive-only, then `pytest tests/unit/test_dom_snapshots.py --snapshot-update`
> 3. Grep for DaisyUI tokens in the touched files: `grep -E "(text-error|btn-primary|alert-)" <touched-files>`
> 4. Verify canonical class markers are added (the cycle's stated goal)

This turns implicit discipline into explicit checklist — reduces the cost of "remembering the right hygiene" on each audit cycle.

**B2: Add a `/contract_audit` subcommand.**
Extract the recurring audit discipline into a named skill at `.claude/commands/contract_audit.md`. Invoked as `/contract_audit <component>` with the component name. The skill embodies the checklist above. Makes the workflow more reproducible than informal cycles.

## Blast radius

- **Classes 1 + 2 + 6** already gated — zero ongoing exposure.
- **Class 3 (dist/)** — affects runtime CSS/JS bundle shipped in wheels. Impact: users installing the dist wheel get an older CSS/JS. Repro: cycle 313 found 20+ cycles of drift. Severity: cosmetic for now (just a version header + one CSS variable), but could become functional if a JS change doesn't propagate.
- **Class 4 (canonical-helper bypass)** — narrow impact, only 5 sites in one file. Security story intact (already-escaped inputs). Ongoing risk: new framework files could introduce the same drift — no automated lint detects it.
- **Class 5 (DaisyUI in Python strings)** — 6 sites fixed in cycle 316, 3 intentionally deferred (dispatch table + dev fallback + data mapping). Ongoing risk: new Python code embedding HTML class names could reintroduce DaisyUI tokens — no automated lint detects it.

Affected apps: all 5 example apps load `dist/dazzle.min.css` for runtime styling, so dist/ drift reaches every app in practice.

## Open questions

1. **Is the `/ux-cycle` preflight gate the right escalation path?** The cycle 312 addition fits naturally (runs on every cycle), but the trade-off is latency: every added check eats into the 10-minute cron cadence. At what point does the gate's cost exceed its value? Cycle 314 already decided 9s was acceptable; cycle 317's recommendation to add dazzle_back/runtime mypy would push to ~13s. Is there a "gate cycle" vs "fast cycle" distinction worth introducing?

2. **Should `test_canonical_pointer_lint.py` grow to cover Python-embedded HTML?** The cycle 310 lint is template-scoped. An analogous Python lint that checks "inline HTML strings in Python should use canonical helpers + canonical tokens" would catch classes 4 + 5 automatically. Scope estimate: ~100 LOC, AST walk for string literals starting with `<` (roughly).

3. **Is cycle 309's "retire missing_contracts" call still right?** It concluded the strategy was superseded because 3 lints now run continuously. But cycle 316 found DaisyUI drift that none of those lints would catch. Maybe a narrower breadth-scan strategy — "drift sweep" — should replace `missing_contracts` rather than nothing replacing it.

4. **Is Heuristic 1 enough to prevent this class of accumulation?** Heuristic 1 is "try the real thing at raw layer before writing framework code." It's aimed at INVESTIGATION cycles. The silent-drift cases here weren't investigations — they were routine IMPLEMENTATION cycles (contract_audit adds class markers) that forgot a hygiene step. Maybe Heuristic 5: "after template/Python edits, run `make test-ux-preflight` before commit." Candidate for promotion.

5. **Can we teach the gate the concept of "relevant"?** Cycle 314's mypy runs on ALL 54 files of dazzle_ui regardless of whether this cycle touched them. Incremental mypy could restrict to changed files. Faster gate, same coverage. But mypy's module-graph resolution makes "changed files" nonobvious — imports from unchanged files still matter. Practical budget: probably not worth the engineering cost right now.

## Recommendation

**Ship Axis A1 + A3 this cycle or next.** Both are concrete, small (<200 LOC each), and close remaining classes without major process changes.

**Defer Axis B (contract_audit checklist / skill).** The hygiene gap existed in cycles 271-284 but cycle 312's preflight now catches the downstream effect automatically. Writing a new skill or editing skill docs has lower marginal value than it did pre-cycle-312.

**Elevate the meta-pattern in `/ux-cycle` durable heuristics.** Add Heuristic 5:

> After any cycle that edits template files, Python files emitting HTML, or CSS, run `make test-ux-preflight`. Do not commit if red.

This turns the existing preflight gate (currently a Step 0a of next cycle) into an **outbound** gate of each cycle too — drift is caught on introduction, not one cron tick later.

## Status tracking

| Class | Status | Next step |
|---|---|---|
| 1 — syrupy baselines | GATED | — |
| 2 — UI type errors | GATED | — |
| 3 — dist/ drift | MANUAL | Axis A2 candidate |
| 4 — canonical-helper bypass | MANUAL | Axis A3 partial coverage |
| 5 — DaisyUI in Python HTML | MANUAL | Axis A3 candidate |
| 6 — contract_audit hygiene | GATED (downstream) | Axis B optional |

Cross-refs:
- cycle 311 log — snapshot debt discovery + cleanup
- cycle 312 log — test-ux-preflight shipped
- cycle 313 log — dist/ drift flagged; 4 flavours of silent drift enumerated
- cycle 314 log — mypy(dazzle_ui) added to gate
- cycle 315 log — helper_audit on HTMLResponse bypass
- cycle 316 log — DaisyUI Python sweep
- `tests/unit/test_dom_snapshots.py` — the syrupy catcher
- `Makefile` `test-ux-preflight` target — the gate itself
