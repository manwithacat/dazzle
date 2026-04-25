# Lane: trials

Qualitative persona scenarios via `dazzle qa trial`. Each cycle picks one `(example_app, scenario)` pair, runs the trial, triages findings into backlog or GitHub issues. Adapted from former /trial-cycle.

## Targets

`examples/*/trial.toml` scenarios. Sibling to `framework-ux` — that lane checks *shape* (contracts, DOM, card safety, deterministic). This lane checks *substance* (did the user achieve the task, was the RBAC sensible, did the error page help — qualitative, LLM-driven).

## State

- **Backlog section:** `## Lane: trials` in `dev_docs/improve-backlog.md`
- **Backlog row format:** `| id | category | severity | app/scenario | description[:120] | seen | cycle | status |`
- **Rotation cursor:** stored in lane-specific state file `.dazzle/trials-rotation.json` (last `(app, scenario)` and cycle counter)

Each cycle burns ~50–100k tokens (the `dazzle qa trial` invocation itself). Use sparingly.

## Signals

| Direction | Kind | Notes |
|-----------|------|-------|
| Emit | `trial-friction` | Fresh OPEN row with severity ∈ {high, concerning} — biases driver toward framework-ux next |
| Emit | `trial-cycle-complete` | Always at end — payload `{verdict, findings_count}` |
| Consume | `app-fixed` | Mark related rows for re-trial |

## actionable_count

For trials, "actionable" doesn't mean "row to action" — it means "verified state worth running a trial against".

Computation: count `(app, scenario)` pairs in `trial.toml` files where the lane has NOT run a trial in the last 48h. If non-zero, lane has work.

## Playbook

### 1. ROTATE

Pick the next `(app, scenario)` to trial:

1. List all `examples/*/trial.toml`. For each, parse `[[scenario]]` entries.
2. Build the full matrix: every `(app_name, scenario_name)` pair.
3. Find the pair **after** `(last_app, last_scenario)` in alphabetical app order, then declared scenario order. Wrap at end.
4. Skip forward if chosen pair was run < 48h ago (check `improve-log.md` tail filtered to lane: trials).
5. If all pairs run < 48h → pick the oldest one (burn cache: refresh is the point).

Update `.dazzle/trials-rotation.json`; increment cycle counter.

### 2. TRIAL

```bash
cd examples/<app> && dazzle qa trial --scenario <scenario_name> --fresh-db
```

Capture stdout + the generated markdown report path (`dev_docs/qa-trial-<scenario>-<ts>.md`).

If the trial fails (exit code ≠ 0, or report missing): outcome `BLOCKED` with summary of failure mode. Do not retry — next cycle picks next pair.

### 3. TRIAGE

Parse the report. Dedup post-processor (v0.57.83) collapses near-duplicates; treat each remaining friction entry as a distinct signal. For each entry:

1. **Match against existing trials backlog rows** — same `(category, description[:80])`? Increment `seen`, update `last_seen_cycle`. ≥3 cross-cycle reinforcement → file an issue.
2. **Otherwise**, append a new row:
   ```
   | TR-N | <category> | <severity> | <app>/<scenario> | <description[:120]> | seen=1 | cycle=N | status=OPEN |
   ```
3. **High-severity, first-time** entries (`severity=high`, `category ∈ {bug, missing}`) — consider filing immediately rather than waiting. Use judgement; clearly framework-level bugs don't need to be observed twice.
4. **Verdict** — extract one-paragraph verdict from report. Negative framing ("I couldn't recommend…", "the core … doesn't work") → `verdict=negative` and look at friction entries hard, not just bookkeep.

#### When to file vs stay in backlog

| Condition | Action |
|-----------|--------|
| `severity=high` + `category=bug` + clear framework-level mechanism | File issue with `needs-triage` label. Include scenario, persona, quoted friction, evidence snippet, link to trial markdown |
| `seen ≥ 3` across cycles | File issue — cross-cycle evidence is strongest triage signal |
| Domain-specific (clearly about example app's DSL, not framework) | Note in backlog only |
| `category=praise` | Record (informational — proves what's working) |

Before filing: `gh search issues --repo manwithacat/dazzle "{quoted description fragment}" --state all` — skip if match.

### 4. REPORT (lane-internal)

1. Update lane backlog section with new + reinforced rows.
2. Return outcome: `{status: PASS|FAIL|BLOCKED, summary, signals_to_emit, budget_consumed: 1}` (cycle counts as 1 against shared explore budget — the rotation IS the explore mechanism for this lane).

### 5. Secondary short-circuit

If last 5 lane cycles produced **zero** new backlog rows AND zero reinforced rows AND zero issues filed → lane returns `HOUSEKEEPING` outcome with summary "trial signal exhausted — review trials backlog or add new scenarios". Driver picks a different lane next cycle.

Track this via `improve-log.md` — count consecutive `lane: trials` housekeeping outcomes.

## Hard rules

- **One `(app, scenario)` per cycle.** Don't chain.
- **Always `--fresh-db`.** Stale data corrupts signal (#810).
- **Never run trials against live tenant data.** `--fresh-db` + example apps means this shouldn't happen, but verify `examples/<app>/.env` points at local Postgres.
- **Token budget awareness.** Default `dazzle qa trial` burns 50–100k tokens per run.
