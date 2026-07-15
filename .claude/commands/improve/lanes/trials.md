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

Two independent sources (driver uses either for rule 5 / rule 6):

1. **Fresh rotation work:** count `(app, scenario)` pairs in `trial.toml` files where the lane has NOT run a trial in the last 48h.
2. **Autonomous TR drain:** count rows in this section that pass the driver eligibility table in `improve.md` (rule 6 — OPEN_FRAMEWORK / OPEN_DSL / FIXED-VERIFY with clear evidence, etc.).

If either is non-zero, the lane (or the routed owning lane for TR-drain) has work. Prefer **TR drain** over a fresh rotation when an autonomous-actionable TR exists — product signal beats another exploratory trial. Full playbook: `improve/strategies/trial_signal_action.md`.

## Playbook

### 0. TR ACTION (when driver picks trial-signals or an autonomous TR routes here)

Follow `improve/strategies/trial_signal_action.md` for **one** row. Typical cases for this lane:

- `FIXED-VERIFY` → re-run `dazzle qa trial --scenario <name> --fresh-db` with subscription driver
- Trial-harness bugs (seed, DEBUG flood, truncate) with clear code path → fix in framework, re-smoke one scenario

Do **not** start a rotation trial in the same cycle.

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
cd examples/<app>
# Prefer an available subscription CLI. Examples often pin [llm] driver=claude-cli;
# on Grok-only hosts use --llm-driver grok-cli (or DAZZLE_LLM_DRIVER=grok-cli).
# Never skip trials solely because a prior cycle aborted — re-probe:
#   python -c "from dazzle.llm.driver import call_subscription_cli; print(call_subscription_cli('grok-cli','Reply: OK')[0])"
export DATABASE_URL="${DATABASE_URL:-postgresql://localhost:5432/dazzle_<app>}"  # app DB, not dazzle_test
dazzle qa trial --scenario <scenario_name> --fresh-db --llm-driver grok-cli
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
