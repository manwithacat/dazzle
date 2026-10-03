# `/improve` — efficacy review and agent-ergonomics opportunities

**Reviewed:** 2026-10-03, against `main` at `4b70175b5`. **Method:** read the
driver and lanes, then measure the state it is supposed to maintain. Numbers
below are from the tree, not from the playbook's description of itself.

This is a review of a *harness*, so it holds the harness to the standard the
harness itself uses: a claim that nothing checks is not a claim, it is a hope.
Each section says what is measured, then what is not.

## Verdict

The **design** is unusually strong for an autonomous loop: a lock with a TTL, a
preflight that refuses to start product work on unpaid debt, a CI-badge gate
that preempts product lanes, a CodeQL gate, a signal bus, an append-only log, an
explicit-refusal vocabulary, and a capability map that is supposed to police the
loop's own coverage. Almost every idea a smaller loop would lack is here.

The **efficacy** is currently bounded by one external dependency with no
watchdog. The loop has not run since **cycle 2410, 2026-09-04 — 29 days**. Its
last recorded act was to schedule the next cycle:

```json
{ "action": "schedule", "interval": "15m", "fire_immediately": false,
  "reason": "ci_waiting in_progress work=actionable=6" }
```

That `scheduler_create` call is a **host** capability. When the host stopped
scheduling, the loop stopped — silently. No gate, no issue, no CI job, no
dashboard reports a stale heartbeat. A stopped loop is indistinguishable from a
loop with nothing to do, and every courtesy it performs (inbox poll, CodeQL
poll, compaction, self-audit, capability sweep) silently stopped with it.

## What the stall cost, measured

| Symptom | Evidence | Consequence |
|---|---|---|
| Backlog over its own compaction line | `dev_docs/improve-backlog.md` = **202 KB** vs the driver's 100 KB threshold in SKILL.md | Compaction runs at Step 0d *inside* a cycle, so a stopped loop never compacts. The driver reads the backlog every cycle: ~50k tokens of settled rows (554 settled vs 6 actionable) per cycle |
| Capability map carries no signal | **70 of 80** rows `STALE`, 6 never exercised, `last-exercised` spanning cycles 1216→2409 | The map's own rule is `STALE` at lag ≥ 20 cycles. With the loop stopped, *everything* is stale by construction, so "STALE" no longer discriminates |
| Explore budget frozen mid-run | `explore_used: 29 / 100` | The counter that rations exploration stopped being rationed |
| Cycle log frozen | `dev_docs/improve-log.md` last entry cycle 2410 | 26 cycles of cadence lost, with no signal |

The deeper point is structural: **housekeeping lives inside the loop**. Anything
the loop maintains, the loop stopping takes with it, and nothing outside notices.
Every gate that *did* fire in that month was a `-m gate` pytest under
`make ci-fast` — i.e. the parts of this repo that are checks rather than
courtesies held.

## The record drifted too, and nothing looked

With the loop parked, its GitHub-inbox strategy was not running, so the issue
tracker accumulated work whose fix had already shipped. Two examples found by
hand on 2026-10-03, both open while `main` contained the fix:

- **#1746** — the six-copy `_product_name` dedup shipped in `beaf67485`.
- **#1747** — the three-loader validation accumulator shipped in `f5bc6d335`.

Both commit messages cite the issue number. A machine could have known; nothing
did.

Meanwhile **34 Dependabot alerts** sat open, all already in the terminal
`fixed` state (verified: every `uv.lock` / `package-lock.json` package resolves at
or above its first patched version, and the `authlib`/`pydantic-settings` hits
are against dependencies no longer in those manifests). GitHub does not allow
dismissing a `fixed` alert, so 30 fixed alerts is the correct end state — but
nothing had *verified* that, which is the part that mattered. It also turned out
that `make security`, the local entry point for the audit, was **broken**:
delegating to a `ci_local.sh` subcommand that did not exist. The gate that
supposed to police pip-audit usage checks the *flags*, not whether the target
exists, so it stayed green.

## Agent-ergonomics opportunities, in leverage order

1. **A heartbeat the loop cannot lose.** The single highest-value change: treat
   "last cycle older than N days" as a *gate*, not a dashboard field. It is one
   comparison against a file mtime, it needs no scheduler, and it converts the
   failure mode from silent to loud. Delivered as part of `scripts/repo_reconcile.py`
   below rather than as a CI failure, because "the loop is off" is an operator
   fact, not a code defect.
2. **One command for "is the record coherent?"** Reconciling the record took six
   ad-hoc `gh` queries and about an hour of context this session. `make reconcile`
   (`scripts/repo_reconcile.py`) now answers it in one call: stale issues (open but
   cited by a merged commit), PRs mergeable behind main, advisories not in a
   terminal state, loop heartbeat, backlog over threshold, harness-path rot.
   Advisory by design — it reports, it does not fail a build — and it says so in
   the caveat, because the common stale-issue hit is a commit citing an issue as a
   *residual* tracker rather than as finished work.
3. **Delegation targets must exist, wherever the delegation lives.** Found twice in
   one session: `make security` → a `ci_local.sh` subcommand that did not exist,
   and two playbooks naming a doc that had been renamed. Gates now cover the
   Makefile→`ci_local.sh` edges (`tests/unit/test_pip_audit.py`) and the harness's
   own runnable paths and cited doctrine docs
   (`tests/unit/test_improve_harness_paths.py`, 67 paths across 36 playbooks).
   The general form is worth stating as a rule: **the harness is documentation
   that executes, so it needs the same reference-integrity gate as code.**
4. **Do not make a loop's own outputs load-bearing for its maintenance.** The
   compaction threshold is documented in SKILL.md and enforced only by the cycle it
   was written for. Moving `improve_compact.py` out of Step 0d into a scheduled
   or operator-triggered path would make the invariant hold whether or not the
   loop runs.
5. **The map needs an "unknown" state.** With the loop stopped, every row read
   `STALE` and the status column stopped carrying information. A `LAST SEEN:
   <date>` column that keeps its value when nothing runs would let a reader tell
   "stale because neglected" from "stale because the clock stopped".

## What is *not* wrong with it

Worth recording, because a review that only lists defects misleads:

- The refusals are explicit and specific ("residual 0 → do not densify",
  "harness_only ≠ bake-off lift", "metered vision is never the top dig"). That is
  the discipline that keeps an autonomous loop from inventing work.
- `dev_docs/improve-log.md`'s per-cycle entries record `budget_consumed`, seeds,
  and the *next* forced action, so a cycle is auditable after the fact. The log
  is the strongest artifact in the harness.
- Lane/skill separation is right: SKILL.md owns scaffolding, lanes own judgment,
  strategies own one dig each. A cycle's structure is legible without reading
  5,700 lines of playbook.
- The strategy count (29) is high, but each is a narrow dig with a probe command,
  and `--status`/`--reset-budget` give an operator the two escape hatches that
  matter.

## Reproducing this review

```bash
make reconcile                        # heartbeat, backlog, stale issues, PRs, advisories
uv run python scripts/improve_example_probes.py --status
uv run python scripts/improve_policy.py --status
wc -c dev_docs/improve-backlog.md dev_docs/improve-log.md
python3 -c "import re,collections,pathlib; ..."   # capability-map status histogram
```

The capability-map histogram in this review (70 `STALE` / 4 `USED` / 1
`OWNED-IDLE` / 5 `EXEMPT` of 80 rows) is worth re-deriving rather than trusting:
it is a hand-rolled parse of a markdown table, which is exactly the kind of
number that goes stale silently.
