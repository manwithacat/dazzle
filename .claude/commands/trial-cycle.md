---
description: Qualitative trial loop — rotate apps × personas, run dazzle qa trial, triage findings into backlog or issues
---

# /trial-cycle

Complement to `/ux-cycle`. Where ux-cycle checks *shape* (contracts, DOM, card safety — deterministic) against a rotating component, this loop checks *substance* (did the user achieve the task, was the RBAC sensible, did the error page help — qualitative, LLM-driven). Findings become framework-improvement pressure via `dev_docs/trial-backlog.md` and GitHub issues.

One cycle runs a single `(example_app, persona_scenario)` trial and post-processes the report. Cycles take ~5 min and burn tokens — default to `/loop 60m /trial-cycle` or manual invocation, not tight intervals.

## Overview

```
ROTATE → TRIAL → TRIAGE → REPORT
   ↑                        │
   │  ┌─ findings ──────────┤
   │  │                     │
   │  │   concerning-class & cross-cycle → file issue
   │  │   one-off friction → append to trial-backlog.md
   └──┘
```

## State files

| File | Purpose |
|------|---------|
| `.dazzle/trial-cycle-state.json` | Rotation cursor: last (app, scenario) run, cycle counter |
| `dev_docs/trial-backlog.md` | Observation rows with cross-cycle reinforcement counts |
| `dev_docs/trial-log.md` | Append-only cycle log (timestamp, verdict summary, counts) |

All gitignored.

## Step 0: Preflight

1. Check `.dazzle/trial-cycle.lock`. If present and < 30 minutes old → abort "another cycle running". Older → delete as stale.
2. Create lock with current PID + ISO timestamp.
3. If `.dazzle/trial-cycle-state.json` missing → init with `{"cycle": 0, "last_app": null, "last_scenario": null}`.

## Step 1: ROTATE

Pick the next `(app, scenario)` to trial:

1. List all `examples/*/trial.toml`. For each, parse `[[scenario]]` entries.
2. Build the full matrix: every `(app_name, scenario_name)` pair.
3. Find the pair **after** `(last_app, last_scenario)` in the matrix (wrap around at the end). Use alphabetical app order, then scenario order as declared in the toml.
4. If the chosen pair has been run in the last 48 hours (check `trial-log.md` tail) → skip forward until an older or unseen pair is found. If all pairs are < 48h old → pick the oldest one (burn cache: the refresh is the point).

Update the state file with the chosen pair; increment `cycle`.

## Step 2: TRIAL

Run:

```bash
cd examples/<app> && dazzle qa trial --scenario <scenario_name> --fresh-db
```

Capture stdout + the generated markdown report path (defaults to `dev_docs/qa-trial-<scenario>-<ts>.md` — the tool prints the path).

If the trial fails (exit code ≠ 0, or the report file is missing): log the failure in `trial-log.md` with `outcome=error`, release the lock, exit this cycle. Do not retry — next cycle picks the next pair.

## Step 3: TRIAGE

Parse the report. The dedup post-processor from v0.57.83 already collapses near-duplicates; treat each remaining friction entry as a distinct signal. For each entry:

1. **Match against `dev_docs/trial-backlog.md`** — if a row with the same `(category, description[:80])` already exists, increment its `seen` counter and update `last_seen_cycle`. Cross-cycle reinforcement ≥ 3 is a signal to file an issue.
2. **Otherwise**, append a new row with:

   ```
   | TR-<N> | <category> | <severity> | <app>/<scenario> | <description[:120]> | seen=1 | cycle=<N> | status=OPEN |
   ```

3. **High-severity, first-time** entries (`severity=high`, `category ∈ {bug, missing}`) — consider filing a GitHub issue immediately rather than waiting for reinforcement. Use judgement; a clearly-framework-level bug doesn't need to be observed twice before we act.

4. **Verdict** — extract the one-paragraph verdict from the report. If it contains clear negative framing ("I couldn't recommend…", "the core … doesn't work", etc.), treat the cycle as `verdict=negative` and escalate the entire batch: that's your cue to look at the friction entries hard, not just bookkeep them.

### When to file an issue vs. stay in backlog

| Condition | Action |
|-----------|--------|
| `severity=high` + `category=bug` + clear framework-level mechanism visible in description | File issue with `needs-triage` label. Include: scenario, persona, the quoted friction, the evidence snippet from the report, link to the trial markdown |
| `seen ≥ 3` across cycles, regardless of severity | File issue — cross-cycle evidence is the strongest triage signal |
| Domain-specific (clearly about the example app's DSL, not the framework) | Note in backlog, do NOT file — unless the example is intentionally broken to test framework behaviour |
| `category=praise` | Record in backlog (informational — proves what's working) |

## Step 4: REPORT

1. Append a cycle entry to `dev_docs/trial-log.md`:

   ```
   ## Cycle <N> — <timestamp>
   **App:** <app> **Scenario:** <scenario> **Persona:** <login_persona>
   **Verdict:** <positive|negative|mixed> — <one-sentence extract>
   **Findings:** <raw_count> raw, <after_dedup> after dedup
   **New backlog rows:** <added>
   **Reinforced rows:** <incremented>
   **Issues filed:** <comma-separated #N or "none">
   **Report:** <path>
   ```

2. Commit changes with message `trial: cycle {N} — {app}/{scenario} ({verdict})`. Commit only the state file + backlog + log (the trial report is itself gitignored — users can find it locally via the path in the log).

3. Release the lock.

## Step 5: Secondary short-circuit

If the last **5 cycles** produced zero new backlog rows AND zero reinforced rows AND zero issues filed → skip the next cycle entirely and report "trial signal exhausted for now — review `trial-backlog.md` or add new scenarios to cover different personas". This prevents the loop spinning on apps whose trials have gone quiet.

## Hard rules

- **One `(app, scenario)` per cycle.** Don't chain.
- **Always `--fresh-db`.** Stale data from prior cycles corrupts signal (see #810). Trials without fresh DB are useful for humans debugging, not for this automated loop.
- **Never file duplicate issues.** Before filing, `gh search issues --repo manwithacat/dazzle "{quoted description fragment}" --state all` and skip if a match comes back.
- **Never run trials against live tenant data.** `--fresh-db` plus example apps means this shouldn't happen, but double-check `examples/<app>/.env` points at local Postgres.
- **Token budget.** Default `dazzle qa trial` burns ~50-100k tokens per run. A `/loop 60m /trial-cycle` running continuously for a day is 50-100M tokens. Use judgement about cadence.

## Usage

```bash
# Single cycle
/trial-cycle

# Hourly recurring
/loop 60m /trial-cycle

# Self-paced (model decides cadence based on signal)
/loop /trial-cycle
```

## Relationship to other loops

- **`/ux-cycle`** — complements this. That loop is deterministic (contract-walk, card-safety, DOM structure). Trial-cycle is qualitative (user narrative, task completion, RBAC sensibility). Some findings surface in both; most surface in exactly one.
- **`/improve`** — trial findings eventually flow into `/improve` via the issue queue. `/improve` picks up issues and ships fixes. Trial-cycle is the upstream signal generator.
- **`/issues`** — direct consumer. When trial-cycle files an issue, `/issues` triages and resolves it on its next run.
