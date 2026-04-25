Single autonomous-improvement entrypoint for Dazzle. Each cycle: pick the highest-leverage lane based on signals and actionable rows, hand off to its playbook, record outcome, repeat.

Replaces /improve, /ux-cycle, /trial-cycle, /ux-converge. The lanes preserve those skills' bodies; the driver owns the scaffolding (lock, preflight, signal bus, log, /loop).

ARGUMENTS: $ARGUMENTS

If `$ARGUMENTS` is empty: driver picks the lane.
If `$ARGUMENTS` matches a lane name (`framework-ux` / `example-apps` / `trials` / `ux-converge`): force that lane.
If `$ARGUMENTS` is `<lane> <strategy>`: force that lane and that sub-strategy.
If `$ARGUMENTS` is `--status`: emit a status report across all lanes and exit (no cycle).

## Lanes

| Lane | Targets | Backlog section | Playbook |
|------|---------|-----------------|----------|
| framework-ux | Dazzle's UI layer (templates, contracts, fitness walks) | `## Lane: framework-ux` | `improve/lanes/framework-ux.md` |
| example-apps | example apps (DSL gaps, lint, conformance, fidelity, visual) | `## Lane: example-apps` | `improve/lanes/example-apps.md` |
| trials | qualitative persona scenarios (trial.toml) | `## Lane: trials` | `improve/lanes/trials.md` |
| ux-converge | example apps with nonzero UX contract failures | `## Lane: ux-converge` | `improve/lanes/ux-converge.md` |

## State files

| File | Purpose |
|------|---------|
| `dev_docs/improve-backlog.md` | All four lanes' backlog tables, one `## Lane:` section each |
| `dev_docs/improve-log.md` | Append-only cycle log (single source of truth across all lanes) |
| `.dazzle/improve.lock` | PID + timestamp; 15-min TTL |
| `.dazzle/improve-explore-count` | Single counter shared across all lanes' explore phases (cap 100) |
| `.dazzle/signals/` | Cross-lane signal bus (existing `ux_cycle_signals` infrastructure) |

All gitignored.

## Cycle

### Step 0a: Lock

1. If `.dazzle/improve.lock` exists and is < 15 min old → abort with the lock contents.
2. If older → delete as stale.
3. Create lock with `PID ISO-timestamp`.

### Step 0b: Preflight (always)

```bash
make test-ux-preflight
```

If red, **STOP and fix before continuing** — same rule as old /ux-cycle, applies to every lane now.

### Step 0c: Read signals

```python
from dazzle.cli.runtime_impl.ux_cycle_signals import since_last_run
signals = since_last_run(source="improve")
```

Categorise:
- `dazzle-updated` / `fix-deployed` → mark affected backlog rows for re-verification (delegated to each lane)
- `trial-friction` → bias next lane selection toward `framework-ux` (qualitative finding may need a contract)
- `ux-component-shipped` → bias toward `example-apps` (re-verify apps using that component)
- `ux-regression` → priority signal; jump straight to the relevant lane regardless of selection algorithm

### Step 1: Pick a lane

If `$ARGUMENTS` forces a lane, skip to Step 2.

For each lane, compute two numbers from the unified backlog:

| Number | Method |
|--------|--------|
| `actionable_count(lane)` | Count rows in the lane's section with status ∈ {`REGRESSION`, `PENDING`, `IN_PROGRESS`, `DRAFT`, or qa:`PENDING`} |
| `last_run_at(lane)` | Most recent `improve-log.md` entry for that lane that wasn't a housekeeping idle tick |

Selection priority:

1. **Any lane with REGRESSION rows** → that lane (most urgent — it shipped broken)
2. **Signal-biased pick**: if a `trial-friction` / `ux-component-shipped` / `ux-regression` signal is fresh, prefer the biased lane regardless of count
3. **Highest `actionable_count > 0`** → that lane; ties broken by oldest `last_run_at`
4. **All counts zero** → pick lane with oldest `last_run_at` and run its **explore phase**
5. **Explore budget at cap (100)** → housekeeping idle tick; log + release lock + exit

Record the choice. Bias from signals must be logged ("picked example-apps because of fresh ux-component-shipped from cycle N") so future operators can audit.

### Step 2: Hand off to lane

Read `improve/lanes/{name}.md` and follow its playbook end-to-end. The lane:

- Operates only on its own section of `improve-backlog.md`
- Returns an outcome: `{status: PASS|FAIL|BLOCKED|EXPLORED|HOUSEKEEPING, summary: str, signals_to_emit: list, budget_consumed: int}`
- Does **not** touch the lock, the preflight, the log, or other lanes' state

If the lane requires sub-strategy dispatch (framework-ux explore phase has 5: `missing_contracts`, `edge_cases`, `contract_audit`, `framework_gap_analysis`, `finding_investigation`), the lane reads from `improve/strategies/*.md` and picks one per its own rules.

### Step 3: Apply outcome

1. **Increment explore budget** by `outcome.budget_consumed`
2. **Append log entry** to `improve-log.md`:
   ```
   ## Cycle N — YYYY-MM-DD — lane: {name} — outcome: {status}
   {outcome.summary}
   ```
3. **Emit signals**:
   ```python
   from dazzle.cli.runtime_impl.ux_cycle_signals import emit
   for sig in outcome.signals_to_emit:
       emit(source="improve", kind=sig.kind, payload=sig.payload)
   ```
4. **Mark run**:
   ```python
   from dazzle.cli.runtime_impl.ux_cycle_signals import mark_run
   mark_run(source="improve")
   ```
5. **Commit** if the lane modified tracked files (the lane's playbook reports this). Use message format: `improve: cycle N {lane} — {summary}`

### Step 4: Release lock

```bash
rm -f .dazzle/improve.lock
```

### Step 5: Report

One-paragraph summary: lane chosen, outcome, what changed, budget remaining, next-cycle hint (which lane is likely next based on current backlog state).

## Cross-lane signal contract

| Kind | Emitted by | Consumed by |
|------|-----------|-------------|
| `ux-component-shipped` | framework-ux | example-apps (re-verify), ux-converge (refresh contracts) |
| `ux-regression` | framework-ux | driver (priority pick) |
| `trial-friction` | trials | framework-ux (consider contract), driver (lane bias) |
| `gap-doc-written` | framework-ux | driver (informational; logged) |
| `app-fixed` | example-apps | framework-ux (re-walk if contract relates), trials (re-trial scenarios) |
| `convergence-clean` | ux-converge | example-apps (clear stale rows for that app) |
| `dazzle-updated` | (external — releases) | all lanes (mark affected rows) |
| `fix-deployed` | (external — /issues, /ship) | all lanes (mark affected rows) |

Lanes declare which kinds they emit and consume in their own files. Driver wires the consumption side.

## Hard rules

- **One lane per cycle.** Don't chain across lanes — the next /improve invocation handles that.
- **Lock is mandatory.** No cycle without `.dazzle/improve.lock` held.
- **Always preflight.** Even for lanes whose strict checks don't seem relevant — preflight is the floor.
- **Commit every cycle that modifies tracked files.** Even failure cycles commit if they updated notes.
- **Explore budget is global.** A lane's explore phase always increments the shared counter.

## Status mode

When invoked with `--status`, skip the cycle and emit:

```
## /improve status — YYYY-MM-DD HH:MM

Budget: X/100
Lock: free | held by PID since TIME
Last cycle: N — lane: {name} — outcome: {status}

Lane:           Actionable    Last run     Likely next?
framework-ux    N             cycle M      yes/no
example-apps    N             cycle M      yes/no
trials          N             cycle M      yes/no
ux-converge     N             cycle M      yes/no

Recent signals (last 24h):
- {kind} from {source} at TIME
```

Read-only — does not modify state, log, or lock.

## Usage

```bash
/improve                                # driver picks the lane
/improve framework-ux                   # force a lane
/improve framework-ux contract_audit    # force lane + sub-strategy
/improve --status                       # status report, no cycle
/loop 30m /improve                      # recurring; lane-pickup auto each fire
```

## Migration note

This driver is currently shipping **alongside** the old /improve, /ux-cycle, /trial-cycle, /ux-converge skills. The old skills still work; this driver is opt-in via `/improve` (the old `/improve` skill has been moved to `improve/lanes/example-apps.md` body). When operator confirms the new driver is solid, the old commands will be removed.

See `dev_docs/2026-04-25-improve-consolidation-design.md` for the consolidation rationale.
