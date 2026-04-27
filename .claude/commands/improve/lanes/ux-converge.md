# Lane: ux-converge

Drive UX contract failures to zero against an example app. Each cycle picks one app from the lane backlog, runs an internal RUN→CLASSIFY→FIX→RE-RUN convergence subroutine to completion, reports. Adapted from former /ux-converge.

## Targets

Example apps with nonzero `dazzle ux verify --contracts` failures. **Not** framework code — that's `framework-ux`. **Not** ad-hoc DSL gaps — that's `example-apps`.

## State

- **Backlog section:** `## Lane: ux-converge` in `dev_docs/improve-backlog.md`
- **Backlog row format:** `| app | last_failure_count | last_run | status | notes |`
- **status:** `PENDING` (failures > 0) / `CONVERGING` (in-progress) / `STUCK` (count unchanged ≥ 2 cycles) / `CLEAN` (zero failures, baseline updated)

## Prerequisites

- Running Dazzle server (`dazzle serve --local` from example dir) — or `ModeRunner` substrate
- PostgreSQL + Redis running
- `DAZZLE_SITE_URL` and `DAZZLE_API_URL` set (or `runtime.json` exists)

## Signals

| Direction | Kind | Notes |
|-----------|------|-------|
| Emit | `convergence-clean` | App reached zero failures — payload `{app, baseline_updated_at}` |
| Emit | `convergence-stuck` | Count unchanged ≥ 2 cycles — payload `{app, remaining_failures}` |
| Consume | `app-fixed` | Re-eligible the app for another converge run |
| Consume | `dazzle-updated` | Mark all apps PENDING for re-verification |

## actionable_count

Rows in `## Lane: ux-converge` with status ∈ {`PENDING`, `CONVERGING`}.

## Playbook

### 1. OBSERVE

Pick app:
1. Status `CONVERGING` → resume
2. Status `PENDING` with oldest `last_run` → pick
3. All status `CLEAN` or `STUCK` → run **explore phase** (Step 5 below)

Mark `CONVERGING`.

### 2. RUN CONTRACTS

```bash
cd examples/<app> && dazzle ux verify --contracts
```

Parse: total contracts, passed, failed, pending, each failure line. Record `current_failure_count`.

### 3. CLASSIFY each failure

For each failed contract, call the reconciler:

```python
from dazzle.testing.ux.reconciler import reconcile

diagnosis = reconcile(contract, triple, html, appspec.domain.entities, appspec.surfaces)
# diagnosis.kind → category (WIDGET_MISMATCH, ACTION_MISSING, TEMPLATE_BUG, …)
# diagnosis.levers → specific DSL changes to fix
# diagnosis.category → maps to fix strategy below
```

Read `diagnosis.levers` for specific DSL construct + suggested value.

| Category | diagnosis.kind | Action |
|----------|---------------|--------|
| **DSL fix** | `ACTION_MISSING`, `PERMISSION_GAP`, `SURFACE_MISSING`, `WIDGET_MISMATCH` | Apply `diagnosis.levers` to DSL |
| **Contract calibration** | `ACTION_UNEXPECTED`, `FIELD_MISSING` | Fix contract generation or checker |
| **Template bug** | `TEMPLATE_BUG` | Fix template in `src/dazzle_ui/`, or file GitHub issue (framework-level) |

If reconciler doesn't produce useful diagnosis (empty levers for non-template issue): manual investigation — boot app, hit URL, compare expected vs actual, decide.

### 4. FIX → RE-RUN → COMPARE

Apply fixes. Re-run `dazzle ux verify --contracts`. Compare new `failure_count` to `current_failure_count`:

- **Zero failures** → mark `CLEAN`, update baseline (`dazzle ux verify --contracts --update-baseline`), commit, emit `convergence-clean`. Exit cycle.
- **Count dropped** → continue: classify remaining, fix, re-run. Repeat.
- **Count unchanged for 2 inner iterations** → mark `STUCK`, file GitHub issues for genuine remaining failures (per reconciler kind), emit `convergence-stuck`. Exit cycle.
- **All remaining classified as "genuine"** → file issues, update baseline, mark `STUCK` (or `CLEAN` if baseline reflects the genuine state).

Inner iteration cap: 5 (prevent runaway). Each inner iteration is one "fix → re-run → classify" pass within a single outer cycle.

### 5. EXPLORE (when no PENDING/CONVERGING)

Re-scan all example apps for nonzero contract failures:

```bash
for app in examples/*/; do
    cd "$app"
    failed=$(dazzle ux verify --contracts 2>&1 | grep -c "FAIL ")
    if [ "$failed" -gt 0 ]; then
        echo "$app: $failed failures"
    fi
done
```

Add new rows to lane backlog. If still zero apps with failures → outcome `HOUSEKEEPING`. Counts against shared explore budget by 1.

### 6. REPORT (lane-internal)

1. Update lane backlog row: `CONVERGING` → `CLEAN` / `STUCK` (or stays `CONVERGING` if cycle ended mid-iteration — rare).
2. Note baseline update timestamp (if applicable) and commit SHA.
3. Return outcome: `{status: PASS|FAIL|BLOCKED, summary, signals_to_emit, budget_consumed: 0 (action) or 1 (explore)}`

## Hard rules

- **One app per cycle** — even though the inner subroutine may run 5 fix→retry iterations.
- **Always update baseline on CLEAN** — otherwise the next cycle will rediscover the same "failures" against a stale baseline.
- **Inner iteration cap is 5.** Never let a single cycle run forever.
- **Framework-level template bugs go to /issues, not fixed inline.** This lane targets DSL fixes and contract calibration. Template fixes belong in `framework-ux` or a GitHub issue.
