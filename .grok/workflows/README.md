# Improve multi-agent workflows

Grok Build workflows that extract **parallel cognition panels** from the
`/improve` driver. The driver still owns lock, preflight, CI/CodeQL/inbox
preemption, lane pick, ship, explore budget, and self-schedule.

| Workflow | Replaces strategy panel | Fan-out | Args |
|----------|-------------------------|---------|------|
| `improve-self-audit` | `improve/strategies/self_audit.md` §3 | ≤5 commit skeptics | optional `max_commits`, `apply`, `window` via sample |
| `improve-capability-sweep` | driver capability-sweep cadence | 1 inventory + 3 dig recommenders | optional `apply` |
| `improve-visual-review` | `visual_tier2_subagent.md` §3–5 (judgment only) | 1 load + ≤6 app reviewers | **required** `manifest_path`; optional `max_apps` |

## Run

```text
/workflow improve-self-audit
/workflow improve-self-audit {"apply":true}
/workflow improve-capability-sweep
/workflow improve-visual-review {"manifest_path":"dev_docs/ux_cycle_runs/visual_tier2_…/manifest.json"}
```

Watch progress in `/workflows`. Each run writes a scratch report (`path` in the
result) for the pager.

## Driver contract

| Stage | Workflow | Driver after `complete()` |
|-------|----------|---------------------------|
| Self-audit | verdicts + `apply_hints` | REGRESSION / AUD rows; log `lane: self-audit`; `budget_consumed: 0` |
| Capability-sweep | counts + `recommendations` | log counts; optionally patch `capability-map.md`; `budget_consumed: 0` |
| Visual review | `findings` + `findings_path` | `ingest_visual_findings`; log visual_tier2; `budget_consumed: 5` |

Capture / server boot for visual stays **outside** the workflow (playbook steps
1–2). Pass the finished `manifest.json` as `args.manifest_path`.

## Agent budget (approx.)

| Workflow | Logical agents |
|----------|----------------|
| self-audit | 1 sample + ≤5 review (+1 apply if `apply`) ≈ **6–7** |
| capability-sweep | 1 + 3 (+1 apply) ≈ **4–5** |
| visual-review | 1 + ≤6 ≈ **7** |

Default run cap is 128; these are well under it.

## What stays a single-agent playbook

Product digs (`product_maturity`, `cimonitor`, `consumer-issues`, …) remain
markdown strategies under `.claude/commands/improve/` — sequential judgment +
ship, not multi-agent fan-out.

## Smoke-check (authoring)

```text
# In a Grok session with the workflow tool:
# validate_only with representative args, then a real run.
```

See the create-workflow skill for dialect rules (`#{…}`, unit `()`, fail-closed
verification, no nested workflows).
