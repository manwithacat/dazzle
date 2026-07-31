# Agent brief — antagonist residual for #1626

**Audience:** `/improve` example-apps / framework-ux agents
**Stance:** Product-surface only. Stills under `examples/*/.dazzle/qa/screenshots` are the human score source.
**Human score (2026-07-31 recapture):** fleet mean **~5.1 / 10** (pass ≥**5.5**). Short by **~0.4**.
**Do not claim bake-off pass** until a fresh human re-score says so.

Tracking: GitHub **#1626**. Product-maturity overview:
[`product-maturity.md`](./product-maturity.md) (Antagonist demo bar). Strategy:
`.claude/commands/improve/strategies/demo_fleet.md`.

---

## Doctrine agents must not violate

1. **Stills beat seeds.** Shipping seeds without recapture does not move the antagonist score.
2. **Machine residual 0 is necessary, not sufficient.** `demo_fleet_bar` / `product_quality` green ≠ fleet ≥5.5.
3. **No new example apps** to “fix” the bar. No chart proliferation for its own sake.
4. **Do not Goodhart empty heroes** by shrinking stills or renaming happy-path files.
5. Prefer **framework-wide** fixes (label glue, CTA grammar, capture timeout) over one-app hacks when the failure is cross-cutting.
6. Encode **floors** in probes — never human composite scores as CI gates.

---

## Scorecard snapshot (31 Jul human re-score)

| App | Composite | Δ vs 21 Jul | Hero still(s) to protect |
|-----|-----------|-------------|--------------------------|
| simple_task | 6.2 | −0.1 | `task_board_manager_desktop_light.png`, `my_work_member_desktop_light.png` |
| project_tracker | **6.0** | **+4.0** | `project_board_manager_desktop_light.png` |
| invoice_ops | 5.7 | −0.4 | `approval_desk_approver_desktop_light.png`, `finance_ops_finance_desktop_light.png` |
| fieldtest_hub | **5.5** | **+2.5** | `issue_triage_manager_desktop_light.png`, `device_fleet_manager_desktop_light.png` |
| support_tickets | 5.2 | −0.2 | `ticket_queue_agent_desktop_light.png` |
| contact_manager | **5.0** | **+2.5** | `contacts_user_desktop_light.png` |
| design_studio | 4.7 | +0.9 | `brand_desk_designer_desktop_light.png`, `asset_catalog_designer_desktop_light.png` |
| ops_dashboard | 4.0 | +0.5 | `command_center_ops_engineer_desktop_light.png` ⚠ 500, `incident_review_ops_engineer_desktop_light.png` |
| hr_records | 4.0 | +2.1 | `staff_directory_hr_admin_desktop_light.png` |

Fleet **5.1** · Trio **~5.7** · Pass **5.5**.

---

## Residual work queue (ordered for ≥5.5)

**Code status (2026-07-31 agent drain):** R1–R5 framework/example fixes landed;
R4 settle bug + R6 metric/email polish landed. **Human re-score still required**
before claiming fleet ≥5.5. Stills under `examples/*/.dazzle/qa/screenshots`
are the score source — recapture after each residual cluster.

### R1 · Label glue (framework — highest leverage) — **code done**

| | |
|--|--|
| **Symptom** | Queue/card meta runs together: `Amount:12550.0Currency:GBP`; `Assigned To: Support AgentCreated At: …`; HR preferred/email run-on |
| **Buyer read** | Auto-generated, unfinished |
| **Done when** | Separators/spaces between labels and values on list/queue/card chrome |
| **Evidence** | Re-capture invoice Approval Desk + support Ticket Queue + HR Staff Directory |
| **Score impact** | +0.2–0.4 Trust/First 10s → **likely clears fleet 5.5** |
| **Lane** | framework-ux (queue/list meta formatting) |
| **Residual id** | `label_glue` (human until OCR floor exists) |
| **Shipped** | meta chip spacing + catalogue CSS (`dz-queue-row-meta-line`) |

### R2 · ops Command Center Active Alerts 500 — **code done**

| | |
|--|--|
| **Symptom** | `command_center_ops_engineer_desktop_light.png` Active Alerts region: product **500** while Alert Timeline has real rows |
| **Done when** | Active Alerts renders rows or intentional empty — never 500 on happy-path capture |
| **Evidence** | Fresh command-center still |
| **Score impact** | ops 4.0 → ~5.0–5.5 |
| **Lane** | example-apps `ops_dashboard` + region error handling |
| **Residual id** | `hero_http_error` |
| **Shipped** | `StateMachineSpec.terminal_states` on `http.specs.entity` (HTMX poll-stop) |

### R3 · CTA grammar residual — **code done**

| | |
|--|--|
| **Symptom** | `+ New Add Person`, `+ New Add Department`, `+ New Add Role` on HR |
| **Done when** | `New Person` / `New Department` / `New Role` |
| **Evidence** | `staff_directory_hr_admin_desktop_light.png` |
| **Lane** | `human_create_cta_label` + HR surface titles |
| **Residual id** | `cta_add_double` |

### R4 · Capture holes — **code done**

| Desk | Failure |
|------|---------|
| `invoice_ops` `pay_desk` | `Page.wait_for_function` 8s timeout |
| `invoice_ops` `my_invoices` | same |
| `fieldtest_hub` engineer | auth `httpx.ReadTimeout` |
| Multi-persona same server | wedges — use per-persona serve |

| | |
|--|--|
| **Done when** | Fresh `pay_desk_finance_*` + `my_invoices_requester_*`; recapture restarts serve per persona; timeout ≥600s |
| **Lane** | qa capture readiness + `scripts/recapture_demo_fleet_1626.py` |
| **Residual id** | `capture_desk_timeout` |
| **Shipped** | Capture settle catches Playwright `TimeoutError` (not only builtin); HTMX settle budget 25s; per-persona recapture + preflight |

### R5 · Design visual minimum (P0-8) — **code done**

| | |
|--|--|
| **Symptom** | Brands show hex as text; assets text-only |
| **Done when** | Color chips and/or type placeholders visible in stills |
| **Evidence** | brand_desk + asset_catalog designer stills |
| **Lane** | framework color widget + design_studio |
| **Shipped** | color widget swatches + Brand/Asset story seeds |

### R6 · Soft polish (after R1–R4) — **code + recapture done**

- [x] Synthetic metric deltas (`800.0%`) when seed noise — omit `delta_pct` when `|pct| > 200`
- [x] Contact hero emails prefer story domains over `@example.test`
- [x] Support `manager_ops` recapture (hardened per-persona path + runtime port discovery)
- Category depth (conversation hub, invoice document hub, org tree) is **P1** (deferred)

**Agent OCR spot-checks (local stills, 2026-07-31):** ops Active Alerts rows / no 500;
contact story domains; HR no `New Add`; support meta spacing; design brand hex present.
Human re-score still required before fleet ≥5.5 claim.

---

## Machine floors (empty-hero)

Floors live in:

- `scripts/demo_fleet_bar.py` → `HERO_MIN_BYTES`
- `dazzle.product_quality.stills.HERO_MIN_BYTES` (`dazzle demo quality`)

Absent stills are **skipped** (CI without gitignored `.dazzle/` stills stays green).
Present stills under the byte floor → `empty_hero:<file>=size<min`.

After expanding floors (31 Jul), protect non-trio heroes the same way as the trio.

---

## Recapture recipe

```bash
# Preflight (volume TCC / git / venv / Postgres) — run first in agent shells:
.venv/bin/python scripts/agent_workspace_health.py --require-postgres
./scripts/macos_agent_volume_access.sh   # macOS /Volumes only; no silent grant

# Preferred (restart serve per persona — multi-persona on one process wedges):
# Default runs preflight; serve stdout → examples/<app>/.dazzle/recapture-logs/
# (never PIPE — unread PIPE deadlocks serve: LISTEN but no HTTP).
.venv/bin/python scripts/recapture_demo_fleet_1626.py
.venv/bin/python scripts/recapture_demo_fleet_1626.py --apps invoice_ops,ops_dashboard
.venv/bin/python scripts/recapture_demo_fleet_1626.py --capture-timeout 900
.venv/bin/python scripts/recapture_demo_fleet_1626.py --preflight-only
```

Requires Postgres `dazzle_<app>` and Playwright Chromium.

---

## Messaging constraints

| Safe | Forbidden until re-score ≥5.5 |
|------|-------------------------------|
| “Fleet density improved; mean ~5.1 after recapture” | “Fleet bake-off passed” |
| “Trio + project board + fieldtest triage are demo-safe with caveats” | “Competitive with Linear/Zendesk/Bill.com” |
| “Empty-hero theater largely fixed on recapture” | Closing #1626 on machine residual alone |

---

## Probe commands

```bash
python scripts/demo_fleet_bar.py --status
python scripts/demo_fleet_bar.py --strict
dazzle demo quality -p examples
python scripts/improve_example_probes.py --status
```
