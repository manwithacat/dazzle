---
description: Iterative UX improvement loop — one component per cycle through ux-architect governance and agent QA
---

# /ux-cycle

Bring Dazzle's UX layer under ux-architect governance one component at a time, and verify quality via agent-led QA against example apps. Builds on QA mode (#768) and the ux-architect skill.

## Cycle (7 steps)

### Step 0a: Preflight

1. Check `.dazzle/ux-cycle.lock`. If it exists and its timestamp is < 45 minutes old, **abort** with "Another ux-cycle is already running (lock at $LOCKFILE, PID $PID)". If it's older, delete it as stale.
2. Create `.dazzle/ux-cycle.lock` with current PID and ISO timestamp.
3. Read signals via `dazzle.cli.runtime_impl.ux_cycle_signals.since_last_run(source="ux-cycle")`. Handle any `dazzle-updated` or `fix-deployed` signals by marking affected backlog rows for re-verification.

### Step 0b: Init (first run only)

If `dev_docs/ux-backlog.md` does not exist, the backlog has been seeded manually — do not regenerate. Just read it.

### Step 1: OBSERVE

Read `dev_docs/ux-backlog.md`. Pick the highest-priority row using this order:
1. Any `REGRESSION` row (highest)
2. `PENDING` rows where `contract: MISSING` and `impl: PENDING` (new work)
3. `PENDING` rows where `contract: DRAFT` (in-progress work)
4. `DONE` rows where `qa: PENDING` (verification)
5. `VERIFIED` rows (lowest — re-verification)

If no rows match, jump to Step 6 (EXPLORE mode).

Mark the selected row `IN_PROGRESS` and update `last_cycle`. Increment `attempts`. If `attempts > 3`, mark `BLOCKED` and pick the next row instead.

### Step 2: SPECIFY (only if contract is MISSING or DRAFT)

Invoke the ux-architect skill to produce a component contract for this row's component. Save it to `~/.claude/skills/ux-architect/components/<component>.md` following the contract template at `~/.claude/skills/ux-architect/templates/component-contract.md`. Update the row's `contract` field to `DONE`.

If the contract already exists and is `DONE`, skip this step.

### Step 3: REFACTOR (only if impl is PENDING or PARTIAL)

Apply the contract to Dazzle's code. This typically touches:
- Templates in `src/dazzle_ui/templates/...` — restyle to pure Tailwind with design-system.css HSL variables
- Alpine controllers in `src/dazzle_ui/runtime/static/js/dz-alpine.js` — align with contract's state and interaction grammar
- Backend endpoints if the contract requires new server APIs
- Template compiler in `src/dazzle_ui/converters/template_compiler.py` — if the contract needs new context fields

Follow all rules from the stack adapter at `~/.claude/skills/ux-architect/stack-adapters/htmx-alpine-tailwind.md`.

Update the row's `impl` field to `DONE`.

### Step 4: QA

Two-phase verification against the row's `canonical` example plus one rotating sample from `applies`:

**Phase A — HTTP contracts (fast):**

```bash
cd examples/<canonical> && dazzle ux verify --contracts
```

If this fails, mark `qa: FAIL`, note the failures in the row's `notes`, and skip Phase B. Go to Step 5.

**Phase B — Fitness-engine contract walk (slow, only if Phase A passes AND the contract has quality gates):**

Phase B now routes through the fitness engine. Subprocess lifecycle is owned
by `dazzle.e2e.runner.ModeRunner` (v0.54.4+); the fitness strategy takes an
`AppConnection` from the runner and runs the engine against it:

```python
from pathlib import Path
from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import run_fitness_strategy
from dazzle.e2e.modes import get_mode
from dazzle.e2e.runner import ModeRunner

dazzle_root = Path("/Volumes/SSD/Dazzle")
example_root = dazzle_root / "examples" / "<canonical>"
contract_path = Path.home() / ".claude/skills/ux-architect/components/<component>.md"

# For in-app components (data-table, detail-view, dashboard, etc.):
# pass an explicit persona list matching the DSL personas that should see
# the component. The ModeRunner auto-sets QA flags when personas is
# non-empty so the magic-link login flow (#768) works.
async with ModeRunner(
    mode_spec=get_mode("a"),
    project_root=example_root,
    personas=["admin", "agent", "customer"],
    db_policy="preserve",
) as conn:
    outcome = await run_fitness_strategy(
        conn,
        example_root=example_root,
        component_contract_path=contract_path,
        personas=["admin", "agent", "customer"],
    )

# For public/anonymous components (auth pages, landing pages):
# pass personas=None (or omit) to run a single anonymous cycle.
# async with ModeRunner(
#     mode_spec=get_mode("a"),
#     project_root=example_root,
#     personas=None,
#     db_policy="preserve",
# ) as conn:
#     outcome = await run_fitness_strategy(
#         conn,
#         example_root=example_root,
#         component_contract_path=contract_path,
#         personas=None,
#     )
```

The fitness engine's Pass 1 parses the contract and calls the
`walk_contract` mission — one ledger step per quality gate, with each
gate description recorded as EXPECT and the current DOM snapshot recorded
as OBSERVE. Findings flow through the normal engine pipeline and land in
`dev_docs/fitness-backlog.md` under the example app.

`ModeRunner` owns subprocess lifecycle: acquires PID lock at
`<example>/.dazzle/mode_a.lock` with 15-min TTL safety net, launches
`dazzle serve --local`, polls `.dazzle/runtime.json` for the deterministic
hashed ports, health-checks `/docs`, yields the `AppConnection`, and
tears down cleanly on exit (or on exception, with log tail printed to
stderr). The strategy no longer owns any of this — its only job is
running the engine against whatever URL the runner hands over.

Multi-persona fan-out runs one cycle per persona inside a single
subprocess lifetime. The Playwright browser is launched once, and each
persona gets a fresh `browser.new_context()` for cookie isolation.
Per-persona failures (login rejected, engine crashed, anchor navigation
failed) produce BLOCKED outcomes but do not abort the loop — remaining
personas still run. The aggregated `StrategyOutcome` sums per-persona
findings and surfaces the max independence score across all personas.

**Precondition:** the example app needs `DATABASE_URL` + `REDIS_URL`
reachable (set in `examples/<canonical>/.env` or exported in the shell).
See `docs/reference/e2e-environment.md` for details.

The row's `qa` field becomes:
- `PASS` if `outcome.degraded is False` (the contract walker completed
  without walker errors or infrastructure failures across all personas).
- `FAIL` if `outcome.degraded is True` and at least one persona ran
  (the walker erred or an infrastructure failure occurred mid-run).
- `BLOCKED` if the strategy itself raised (subprocess failed to start,
  Playwright bundle couldn't spin up, all personas failed). Note that
  per-persona failures within a multi-persona run are absorbed into
  `outcome.degraded=True` for that persona; the strategy only raises
  when there is nothing useful to return.

`outcome.findings_count` is **not** used for qa pass/fail. It reports
Pass 2a story_drift / spec_stale / lifecycle observations from the
example app's overall spec/story coherence — completely orthogonal to
whether the widget contract walked correctly. The contract walker
(`walk_contract`) emits zero findings; it only records ledger steps.
`findings_count` should be reported as informational app-health context,
not used to gate per-component qa state. This is the cycle 156 fix —
prior to that cycle, the rule incorrectly used `findings_count > 0` as
the FAIL gate, blocking every widget contract from ever reaching PASS.

### Step 5: REPORT

1. Write an entry to `dev_docs/ux-log.md` with the cycle timestamp, component, phases run, and outcome.
2. Update `dev_docs/ux-backlog.md` with the new row status, contract/impl/qa fields, and notes (include the git SHA of any commits made this cycle).
3. If QA passed, move the row to `DONE`. If it was already `DONE` and just re-verified, move it to `VERIFIED`.
4. Commit changes with message `ux: cycle {component} — {outcome}`.
5. Emit a signal:
   ```python
   from dazzle.cli.runtime_impl.ux_cycle_signals import emit
   emit(source="ux-cycle", kind="ux-component-shipped", payload={"component": "<name>", "outcome": "<status>"})
   ```
   If the row was `DONE` and regressed to `FAIL`, emit `ux-regression` instead.

### Step 6: EXPLORE (only if no PENDING rows remain)

Check the session counter (stored in `.dazzle/ux-cycle-explore-count`). If count >= 30, skip EXPLORE and mark the cycle complete with "No work remaining, explore budget exhausted".

The secondary short-circuit — "last 5 cycles produced 0 findings" — MUST consider only cycles that actually *reached* Step 6 and ran an EXPLORE mission. Housekeeping cycles (retroactive qa-rule sweeps, log-only updates, exhausted-sticky runs) produce 0 EXPLORE findings by construction and must not count toward the streak. Track this via `explored_at` timestamps in `.dazzle/ux-cycle-state.json`.

### Strategy rotation

Alternate strategies by the post-increment counter:
- Odd-numbered explore cycles: `missing_contracts`
- Even-numbered explore cycles: `edge_cases` (not implemented in cycle 198 — falls back to `missing_contracts` until that strategy ships)

### Substrate (cycle 198+, v0.55.5)

EXPLORE runs as a Claude Code Task-tool subagent, NOT as a `DazzleAgent` on the direct Anthropic SDK. Cognitive work is billed to the Claude Code host subscription; browser work happens via a stateless Playwright helper subprocess. **The assistant running `/ux-cycle` composes this sequence directly — there is no async orchestrator function.**

**Prerequisites:**
- Claude Code host running this very session (the `Task` tool must be reachable).
- `examples/<canonical>/.env` with `DATABASE_URL` + `REDIS_URL`.
- Postgres + Redis reachable on the local dev box.
- No `ANTHROPIC_API_KEY` needed — cognition runs through the subscription.

### Playbook (numbered steps the assistant walks through)

**1. Initialise the per-run state directory.** Run via Bash:

```bash
python -c "
from pathlib import Path
from dazzle.cli.runtime_impl.ux_cycle_impl.subagent_explore import init_explore_run
import json
ctx = init_explore_run(
    example_root=Path('/Volumes/SSD/Dazzle/examples/<canonical>'),
    persona_id='<persona_id>',
)
print(json.dumps(ctx.to_dict(), indent=2))
"
```

This creates `dev_docs/ux_cycle_runs/<example>_<persona>_<run_id>/` with an empty `findings.json` + a generated `runner.py`. Capture the printed context dict — every subsequent step uses paths from it.

**2. Boot the example app via the generated runner script.** Run via Bash `run_in_background=true`:

```bash
python <runner_script_path>
```

The runner loads the example's `.env`, boots `ModeRunner`, writes `conn.json` inside the state dir, then blocks on SIGTERM. **Do not wait on this call** — it runs for the lifetime of the cycle.

**3. Poll for readiness.** Run via Bash (foreground, ~5s timeout):

```bash
for i in $(seq 1 20); do
  test -f <conn_path> && break
  sleep 0.5
done
cat <conn_path>
```

Grab `site_url` + `api_url` from the JSON.

**4. Log in as the persona.** Run via Bash:

```bash
python -m dazzle.agent.playwright_helper \
  --state-dir <state_dir> \
  login <api_url> <persona_id>
```

Verify the output JSON has `"status": "logged_in"`. If it has `"error"`, abort the cycle and jump to Step 7 (kill the runner, log the failure).

**5. Build the subagent mission prompt.** Run via Bash:

```bash
python -c "
from dazzle.agent.missions.ux_explore_subagent import build_subagent_prompt
from dazzle.core.appspec_loader import load_project_appspec
from pathlib import Path
import os

example_root = Path('<example_root>')
app_spec = load_project_appspec(example_root)
persona = next(p for p in app_spec.personas if p.id == '<persona_id>')

# List existing-contracted components so the subagent doesn't re-propose them
components_dir = Path(os.path.expanduser('~/.claude/skills/ux-architect/components'))
existing = sorted(p.stem for p in components_dir.glob('*.md')) if components_dir.exists() else []

prompt = build_subagent_prompt(
    strategy='missing_contracts',
    example_name='<example_name>',
    persona_id='<persona_id>',
    persona_label=persona.label,
    site_url='<site_url>',
    helper_command='python -m dazzle.agent.playwright_helper',
    state_dir='<state_dir>',
    findings_path='<findings_path>',
    existing_components=existing,
    start_route=persona.default_route or '/app',
    budget_calls=20,
    min_findings=3,
)
print(prompt)
"
```

Capture the printed prompt.

**6. Invoke the Task tool with the prompt.** Call the `Agent` / `Task` tool with:
- `subagent_type`: `general-purpose`
- `model`: `sonnet`
- `description`: `Cycle N /ux-cycle explore: <example> <persona>`
- `prompt`: the string from step 5

Wait for the subagent to complete. Its final message is the report; the findings file is the durable artifact.

**7. Read the findings.** Run via Bash:

```bash
python -c "
from pathlib import Path
from dazzle.cli.runtime_impl.ux_cycle_impl.subagent_explore import (
    ExploreRunContext, read_findings,
)
# Reconstruct context from the state_dir paths captured in step 1
ctx = ExploreRunContext(
    example_root=Path('<example_root>'),
    example_name='<example_name>',
    persona_id='<persona_id>',
    run_id='<run_id>',
    state_dir=Path('<state_dir>'),
    findings_path=Path('<findings_path>'),
    conn_path=Path('<conn_path>'),
    runner_script_path=Path('<runner_script_path>'),
)
findings = read_findings(ctx)
print(f'proposals: {len(findings.proposals)}, observations: {len(findings.observations)}')
import json
print(json.dumps(findings.to_dict(), indent=2))
"
```

**8. Tear down the runner.** Run via Bash:

```bash
pkill -TERM -f <runner_script_path> || true
```

The runner has a 20-minute safety cap anyway, but explicit teardown is cleaner. Verify `.dazzle/mode_a.lock` is released against the example.

**9. Record results.** For each entry in `findings.proposals`:
- Append a `PROP-NNN` row to the backlog's "Proposed Components" table (incrementing the highest existing ID).
- Skip if a proposal with the same `component_name` already exists (dedup by name).

For each entry in `findings.observations`:
- Append an `EX-NNN` row to the "Exploration Findings" table (again, incrementing from the highest existing ID).

Findings in `dev_docs/ux_cycle_runs/<run>/findings.json` are local-only (gitignored); only the backlog row updates get committed.

**10. Commit.** Message: `ux: explore cycle {N} — {proposals} proposals, {observations} observations`. Include the run_id in the body so future diagnosticians can find the raw findings file locally if it still exists.

### Step 7: Complete

1. Delete `.dazzle/ux-cycle.lock`.
2. Call `mark_run(source="ux-cycle")` to update the signal bus.
3. Report the cycle result (component touched, outcome, next row).

## Hard rules

- **One component per cycle.** Don't chain components even if the current one completes quickly.
- **Per-phase stagnation check.** If any phase (SPECIFY / REFACTOR / QA) makes no progress for 3 minutes, abort and mark the row `BLOCKED`.
- **Lock is mandatory.** Never run a cycle without creating the lock file.
- **Commit every cycle.** Even failures commit the `notes` update and signal emission.
- **Never modify rows in the DONE/VERIFIED state directly — let the cycle move them naturally via QA.**

## Usage

```bash
# One-off cycle
/ux-cycle

# Recurring (every 30 min interval between cycles)
/loop 30m /ux-cycle

# Self-paced (model decides cadence)
/loop /ux-cycle
```
