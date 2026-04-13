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

Phase B now routes through the fitness engine instead of hand-rolling an
agent dispatch. The strategy owns the example-app subprocess, the
Playwright bundle, and the ledger; Phase B just hands it the component
contract path and reads the aggregated outcome:

```python
from pathlib import Path
from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import run_fitness_strategy

contract_path = Path.home() / ".claude/skills/ux-architect/components/<component>.md"

# For in-app components (data-table, detail-view, dashboard, etc.):
# pass an explicit persona list matching the DSL personas that should see
# the component. The strategy iterates once per persona, logging in via
# QA mode magic-link (#768) between iterations.
outcome = await run_fitness_strategy(
    example_app="<canonical>",
    project_root=Path("/Volumes/SSD/Dazzle"),  # Dazzle repo root
    component_contract_path=contract_path,
    personas=["admin", "agent", "customer"],  # or None for anonymous
)

# For public/anonymous components (auth pages, landing pages):
# pass personas=None (or omit) to run a single anonymous cycle.
# outcome = await run_fitness_strategy(
#     example_app="<canonical>",
#     project_root=Path("/Volumes/SSD/Dazzle"),
#     component_contract_path=contract_path,
#     personas=None,
# )
```

The fitness engine's Pass 1 will parse the contract and call the new
`walk_contract` mission — one ledger step per quality gate, with each
gate description recorded as EXPECT and the current DOM snapshot recorded
as OBSERVE. Findings flow through the normal engine pipeline and land in
`dev_docs/fitness-backlog.md` under the example app.

v1.0.3 ships multi-persona fan-out. When `personas` is a non-empty list,
the strategy runs one cycle per persona inside a single subprocess
lifetime — the Playwright browser is launched once, and each persona
gets a fresh `browser.new_context()` for cookie isolation. Per-persona
failures (login rejected, engine crashed, anchor navigation failed)
produce BLOCKED outcomes but do not abort the loop — remaining personas
still run. The aggregated `StrategyOutcome` sums per-persona findings
and surfaces the max independence score across all personas.

The row's `qa` field becomes:
- `PASS` if `outcome.degraded is False` and `outcome.findings_count == 0`
- `FAIL` if `outcome.findings_count > 0`
- `BLOCKED` if the strategy itself raised (subprocess failed to start,
  Playwright bundle couldn't spin up, all personas failed). Note that
  per-persona failures within a multi-persona run are absorbed into
  `outcome.degraded=True` and `outcome.findings_count=0` for that persona;
  the strategy only raises when there is nothing useful to return.

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

Check the session counter (stored in `.dazzle/ux-cycle-explore-count`). If count >= 30 OR the last 5 cycles produced 0 findings, skip EXPLORE and mark the cycle complete with "No work remaining, explore budget exhausted".

Otherwise, alternate between strategies:
- Odd-numbered explore cycles: `Strategy.MISSING_CONTRACTS`
- Even-numbered explore cycles: `Strategy.EDGE_CASES`

Dispatch the `build_ux_explore_mission` from `src/dazzle/agent/missions/ux_explore.py` with a rotating persona. Record the results:
- `propose_component` findings → new `PROP-NNN` rows in the backlog's "Proposed Components" table
- `record_edge_case` findings → new `EX-NNN` rows in the "Exploration Findings" table

Commit with message `ux: explore cycle — {N} findings`.

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
