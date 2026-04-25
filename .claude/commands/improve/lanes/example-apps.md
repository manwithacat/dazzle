# Lane: example-apps

Find a gap in an example app, fix it, verify, commit, move on. Adapted from former /improve.

## Targets

DSL gaps in `examples/*/`: validation errors, lint violations, conformance gaps, fidelity gaps, visual quality findings. **Not** framework code — that's `framework-ux`.

## State

- **Backlog section:** `## Lane: example-apps` in `dev_docs/improve-backlog.md`
- **Backlog row format:** `| # | App | Gap Type | Description | Status | Attempts | Notes |`

## Signals

| Direction | Kind | Notes |
|-----------|------|-------|
| Emit | `app-fixed` | Payload `{app, gap_type, commit}` — triggers framework-ux re-walk if contract relates |
| Consume | `ux-component-shipped` | Re-verify apps using that component |
| Consume | `convergence-clean` | Clear stale rows for that app |
| Consume | `dazzle-updated` / `fix-deployed` | Re-scan affected apps |

## actionable_count

Rows in `## Lane: example-apps` with status ∈ {`PENDING`, `IN_PROGRESS`}.

## Playbook

### 1. OBSERVE

Read backlog section. Selection priority:
1. `IN_PROGRESS` with attempts < 3 → resume it
2. `IN_PROGRESS` with attempts ≥ 3 → mark `BLOCKED`, file issue if framework-related, pick next `PENDING`
3. All gaps DONE/BLOCKED → run **explore phase** (Step 6 below)
4. Pick next `PENDING` (priority: critical > warning > info, then app alphabetical)
5. Mark `IN_PROGRESS`

If `$ARGUMENTS` provided as `<app>`, filter to that app only.

### 2. ENHANCE

Apply the fix appropriate to the gap type:

| Gap type | Action |
|----------|--------|
| `lint` | Edit DSL to satisfy lint rule (add search_fields, persona, scope, etc.) |
| `scope` | Convert `permit:` to `permit:` + `scope:` per ADR-0010 predicate algebra |
| `validation` | Edit DSL to satisfy parser/validator |
| `conformance` | Add missing entity/surface/workspace per `mcp__dazzle__conformance` |
| `fidelity` | Add missing IR-graph edges per `mcp__dazzle__dsl operation=fidelity` |
| `visual_quality` | Implement design-system fix per `dazzle qa visual` finding |

For framework-related gaps (e.g. lint flagging an auto-generated entity), file a GitHub issue and mark `BLOCKED`.

### 3. BUILD

```bash
cd examples/<app> && dazzle validate && dazzle lint
```

If errors → fix and retry (up to 3 attempts).

### 4. VERIFY

```bash
cd examples/<app> && dazzle ux verify --contracts 2>&1 | tail -20
```

Verify the gap closed. For visual_quality fixes, optionally re-run `dazzle qa visual --json` and compare.

### 5. REPORT (lane-internal)

1. Update row in lane backlog: `IN_PROGRESS` → `DONE` (or `BLOCKED` after 3 attempts)
2. Note commit SHA in row's notes
3. Return outcome: `{status: PASS|FAIL|BLOCKED, summary, signals_to_emit: [{kind: "app-fixed", payload: {app, gap_type, commit}}], budget_consumed: 0}`

### 6. EXPLORE / TIERED GAP DISCOVERY (when backlog clean)

Tiered to manage cost — start free, escalate only when the previous tier is exhausted.

#### Tier 1 (every cycle, free): Re-scan DSL gaps

For each example app:
```bash
cd examples/<app>
dazzle validate 2>&1
dazzle lint 2>&1
mcp__dazzle__conformance operation=summary
mcp__dazzle__dsl operation=fidelity
```

Add new rows to backlog as `PENDING`. Increments shared budget by 1.

#### Tier 2 (when Tier 1 exhausted, medium cost): Visual quality

For each example app:
```bash
cd examples/<app> && dazzle qa visual --json 2>&1
```

Parse JSON output. Each finding becomes a row:
- Description: `[{category}] {description} at {location}`
- Severity: high → critical, medium → warning, low → info

Increments shared budget by 1 per app scanned.

#### Tier 3 (when Tier 2 exhausted, high cost): LLM cross-app review

Pick one app, run a review subagent that compares its DSL against patterns from a reference app (e.g. `support_tickets` vs `simple_task`). Surface gaps the static lints don't catch (missing rhythms, weak personas, no test_design coverage).

Increments shared budget by 5 (significantly more expensive).

## Hard rules

- **One gap per cycle.** Don't chain.
- **Three attempts then BLOCKED.** Never let a gap run forever.
- **Framework-related gaps file issues, don't fix.** This lane targets app DSL only — framework fixes belong in `framework-ux` or /issues.
