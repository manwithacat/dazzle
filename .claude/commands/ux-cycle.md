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

Alternate strategies by the post-increment counter:
- Odd-numbered explore cycles: `Strategy.MISSING_CONTRACTS`
- Even-numbered explore cycles: `Strategy.EDGE_CASES`

Run the explore strategy via the production driver (added 2026-04-14 in v0.55.2):

```python
from pathlib import Path
from dazzle.agent.missions.ux_explore import Strategy
from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import run_explore_strategy
from dazzle.e2e.modes import get_mode
from dazzle.e2e.runner import ModeRunner

example_root = Path("/Volumes/SSD/Dazzle/examples/<canonical>")

async with ModeRunner(
    mode_spec=get_mode("a"),
    project_root=example_root,
    personas=["admin"],           # rotating persona from the DSL personas list
    db_policy="preserve",
) as conn:
    outcome = await run_explore_strategy(
        conn,
        example_root=example_root,
        strategy=Strategy.MISSING_CONTRACTS,   # or EDGE_CASES
        personas=["admin"],
    )
```

`run_explore_strategy` builds the explore mission via `build_ux_explore_mission`, wires it into `DazzleAgent(use_tool_calls=True)` with a `PlaywrightObserver` + `PlaywrightExecutor`, and returns an `ExploreOutcome` with flat `proposals` / `findings` lists tagged with `persona_id`. Per-persona failures (login rejected, agent crash) are absorbed into `blocked_personas` without aborting remaining personas; all-blocked triggers a `RuntimeError`.

**Precondition:** same as Phase B — `examples/<canonical>/.env` with `DATABASE_URL` + `REDIS_URL`, plus `ANTHROPIC_API_KEY` in the environment because the agent loop calls the Anthropic SDK directly. `DazzleAgent(use_tool_calls=True)` is a strict requirement — the legacy text-action protocol was empirically confirmed in cycle 147 to stagnate at 8 steps with 0 findings, and the 2026-04-14 tool-use + robust-parser fix is what unblocks explore mode.

Record results:
- Each entry in `outcome.proposals` → one new `PROP-NNN` row in the backlog's "Proposed Components" table
- Each entry in `outcome.findings` → one new `EX-NNN` row in the "Exploration Findings" table
- `outcome.blocked_personas` → notes on the cycle log entry

Commit with message `ux: explore cycle — {N} proposals, {M} findings`.

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
