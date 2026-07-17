# Strategy: journey_dogfood

**Lane:** example-apps
**Force path:** `/improve example-apps journey_dogfood`
**Probe:** `python scripts/example_journey_maturity.py`

Agent-first dogfood loop for example apps. Warehouse list/CRUD is **not**
enough — each cycle matures **one** residual app toward:

* Bound stories (`status: accepted` + `executed_by: surface.<real>`)
* List → hub hops (`open: Entity via field`)
* Multi-section VIEW hubs (`layout: strip`, `related` children)

Domains are not novel. If the app lacks story inventory, spin a **read-only
explore subagent** on `SPEC.md` / `SPECIFICATION.md` / stems + existing DSL
and author a priori journey stories (CRM, billing, ops, HR, fieldtest, …).

## Machine probe

```bash
python scripts/example_journey_maturity.py              # table + next=
python scripts/example_journey_maturity.py --status     # cycle log line
python scripts/example_journey_maturity.py --next       # single app id
python scripts/example_journey_maturity.py --json
python scripts/example_journey_maturity.py --app <name> --min-bound 3
# exit 0 when that app clears the bar
```

Tiers (from probe):

| Tier | Meaning | Cycle action |
|------|---------|--------------|
| `critical` | no stories **or** zero `executed_by` | Author/bind journeys + surface hubs |
| `thin` | bound &lt; 3 and/or missing open-via/hub | Upgrade surfaces + add binds |
| `deepen` | narrative-heavy; few bound | Promote 3–5 stories off narrative_only |
| `ok` | mature enough | Skip; pick next residual |

Fleet residual remaining → probe exit **1** (loop continues). Fleet mature →
exit **0** (strategy can idle / hand back to default example-apps explore).

## When to pick

Pick this strategy when **any** of:

* Probe reports `critical + thin > 0` (always prefer over STALE-clear noise)
* Force path: `/improve example-apps journey_dogfood`
* Signal `fix-deployed` / `dazzle-updated` and residual still non-empty
* Backlog has `PENDING` rows with gap type `journey_maturity`

Skip when:

* Probe `residual=0` (fleet mature) — fall through to normal example-apps Tier 1
* CI badge red / CodeQL high (driver preemption) — do not dogfood on broken main

`budget_consumed: 0` for probe-driven work (deterministic DSL edit).
`budget_consumed: 1` if an explore subagent was used for story drafting.

## Playbook (one app per cycle)

### 1. OBSERVE

```bash
python scripts/example_journey_maturity.py --status
APP=$(python scripts/example_journey_maturity.py --next)
```

If `APP` empty → report `{status: PASS, summary: "fleet journey mature", budget_consumed: 0}`
and return (no ship required).

Mark or create backlog row under `## Lane: example-apps`:

`| N | <app> | journey_maturity | <reasons from probe> | IN_PROGRESS | 0 | |`

### 2. INVENTORY (read-only)

In `examples/$APP/`:

1. `dazzle.toml`, `dsl/*.dsl` (entities, surfaces, workspaces, personas)
2. `SPEC.md` / `SPECIFICATION.md` / `README.md` / `stems/` if present
3. Existing stories: which are `narrative_only` vs `executed_by`
4. Real surface names — **never invent** `executed_by` targets

If inventory is thin and domain goals are unclear, dispatch explore subagent
(read-only) with the prompt template in § Subagent. Do **not** invent surface
names; if a hub is missing, list `ADD surface X` and author it in ENHANCE.

Reference patterns (already green):

* `examples/simple_task` — task/user hubs + ST-015/020/021
* `examples/support_tickets` — ticket hub + ST-019/021
* `examples/project_tracker` — project/task open-via + ST-001…004
* `examples/invoice_ops` / `hr_records` / `contact_manager` — recent dogfood

### 3. ENHANCE (smallest change that moves tier)

| Residual | Minimal patch |
|----------|----------------|
| no stories | Add `dsl/stories.dsl` (module if multi-file app) with 3–6 bound journeys |
| zero / low bound | Upgrade existing stories: `status: accepted`, `executed_by: surface.*` |
| no open-via | On primary list(s): `open: Entity via id` or `open: Parent via fk` |
| flat VIEW | Multi-section hub + `layout: strip` + `related` for children |
| missing hub entity | ADD list/detail only when probe reasons demand it |

Keep pure CRUD state-machine stories as `narrative_only: true` — do not bind
everything. Prefer persona jobs: queues, manager review, open-via context hops.

### 4. BUILD / GATE

```bash
cd examples/$APP
dazzle validate                    # exit 0 (warnings OK)
dazzle prove story --journey       # failed=0 for bound stories
dazzle prove representation -p .   # exit 0
cd ../..
python scripts/example_journey_maturity.py --app $APP --min-bound 3
# exit 0 = app cleared bar
```

If validate or prove fails → fix (max 3 attempts).
If acme_billing (or any app with `expected/compliance-auditspec.json`) drifts,
regenerate expected per the unit test message before ship.

### 5. FLEET SMOKE (cheap)

```bash
bash scripts/example_agent_prove.sh   # representation fleet green
python scripts/example_journey_maturity.py --status
```

### 6. SHIP

One gap per cycle (this app). `/bump patch` + CHANGELOG under Added/Changed +
commit + tag + push when version bumped. Pre-ship: `make ci-fast` (or lane's
usual ship discipline).

Update backlog row → `DONE` with commit SHA + journey counts.

Emit signal:

```python
from dazzle.cli.runtime_impl.ux_cycle_signals import emit
emit(source='journey_dogfood', kind='app-fixed',
     payload={'app': APP, 'gap_type': 'journey_maturity', 'commit': SHA})
```

### 7. REPORT

Return to driver:

```text
{status: PASS|FAIL|BLOCKED,
 summary: "<app> tier critical→ok bound=N open=M",
 signals_to_emit: [{kind: app-fixed, ...}],
 budget_consumed: 0|1}
```

Driver self-schedules next `/improve` (or operator uses `/loop Nm /improve
example-apps journey_dogfood`). Next cycle OBSERVE re-ranks residual.

## Subagent prompt (when stories missing)

```text
Read-only. App: examples/<APP>
Read dazzle.toml, dsl/*.dsl, SPEC.md/SPECIFICATION.md/README/stems.
Inventory stories and surfaces.
Propose 3–6 NEW or UPGRADED stories (status: accepted, executed_by real surfaces).
List SURFACE patches needed (open:, multi-section view, related, layout: strip).
Do NOT invent surface names — say ADD surface X if missing.
Return complete story DSL blocks + patch notes for the parent agent.
```

## Hard rules

- **One app per cycle.** Do not batch the fleet in a single improve cycle.
- **No invented surfaces** in `executed_by`.
- **Framework bugs** (prove false positives, open-via runtime) → file issue +
  `BLOCKED` / hand to framework-ux or /issues — do not paper over in every app.
- **Three attempts** then `BLOCKED` with notes.
- Prefer binding + hub chrome over adding more narrative-only CRUD stories.
