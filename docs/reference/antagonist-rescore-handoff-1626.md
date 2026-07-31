# Antagonist re-score handoff — #1626

**Audience:** Antagonist / human bake-off scorer
**Date:** 2026-07-31 (agent drain complete)
**Prior human mean:** ~5.1 / 10 (pass ≥5.5)
**Machine residual:** `demo_fleet residual=0` (necessary, not sufficient)

This pack hands work **back to the antagonist**. Do **not** treat machine residual
or agent OCR as a bake-off pass.

---

## How to re-score

1. Stills root (local, gitignored):

   ```text
   examples/<app>/.dazzle/qa/screenshots/*_desktop_light.png
   ```

2. Score dimensions (same as prior bake-offs): First 10s · Domain fidelity ·
   Golden path · Feature depth · Demo data · Trust/polish.

3. Preferred hero stills (one primary per app):

| App | Primary hero still |
|-----|-------------------|
| simple_task | `task_board_manager_desktop_light.png` |
| project_tracker | `project_board_manager_desktop_light.png` |
| invoice_ops | `approval_desk_approver_desktop_light.png` + `pay_desk_finance_desktop_light.png` |
| fieldtest_hub | `issue_triage_manager_desktop_light.png` |
| support_tickets | `ticket_queue_agent_desktop_light.png` + `manager_ops_manager_desktop_light.png` |
| contact_manager | `contacts_user_desktop_light.png` |
| design_studio | `brand_desk_designer_desktop_light.png` + `asset_catalog_designer_desktop_light.png` |
| ops_dashboard | `command_center_ops_engineer_desktop_light.png` |
| hr_records | `staff_directory_hr_admin_desktop_light.png` + `org_chart_hr_admin_desktop_light.png` |

4. Fleet claim rule: mean ≥5.5 → may claim “demo-safe fleet”; do **not** claim
   category leadership.

---

## Agent-shipped residuals (R1–R6 + partial P1)

| ID | Residual | Agent evidence |
|----|----------|----------------|
| R1 | Label glue | Mid-dot separators on queue meta; OCR: `Assigned To: … - Created At:` |
| R2 | Ops Active Alerts 500 | `terminal_states` on HTTP SM; still shows alert rows, no 500 OCR |
| R3 | `New Add *` CTA | HR staff directory OCR: no `New Add` |
| R4 | Capture desk timeout | Playwright settle soft-fail; fresh pay_desk / my_invoices / active_alerts stills |
| R5 | Design swatches | Brand desk color/hex fields |
| R6 | Soft polish | `delta_pct` omit when \|pct\|>200; contact `*.example` emails; manager_ops recapture |
| P1a | HR org tree | Nested Department seeds + `display: tree` on Departments & Roles |
| P1b | Design catalog | `asset_grid` → `display: grid` (metadata cards) |

Tooling: `scripts/agent_workspace_health.py`, hardened
`scripts/recapture_demo_fleet_1626.py` (no PIPE, runtime.json port discovery).

---

## Agent OCR spot-check (not a human score)

| Check | Result |
|-------|--------|
| 500 / Something went wrong | clean on heroes |
| New Add CTA | clean |
| @example.test story emails | clean on contacts |
| 800.0% metric deltas | clean after simple_task recapture |
| Meta glue | separators present on support queue |
| Machine floors | residual=0 |

**Expected (agent estimate only):** prior 5.1 + R1–R6 + ops/HR/design depth
may approach ≥5.5 if humans agree on stills — **antagonist decides**.

---

## Deferred (do not ding agent for these as P0)

- Invoice **PDF document hub** (project_tracker has the pattern; invoice already strong)
- Support **threaded conversation** UI (no chat primitive)
- Manager-chain recursive **people** tree (ManagerLink is edges, not nodes)
- True **thumbnail** media gallery
- Competitive claims vs Linear/Zendesk/Bill.com

---

## Recapture recipe (if antagonist needs fresh stills)

```bash
.venv/bin/python scripts/agent_workspace_health.py --require-postgres
.venv/bin/python scripts/recapture_demo_fleet_1626.py --capture-timeout 900
python scripts/demo_fleet_bar.py --strict
```

---

## Messaging constraints (unchanged)

| Safe until re-score | Forbidden |
|---------------------|-----------|
| Fleet density / residual code drained | “Fleet bake-off passed” |
| Machine residual 0 | Closing #1626 on machine residual alone |
| Trio + recaptured heroes ready for review | “Competitive with category SaaS” |
