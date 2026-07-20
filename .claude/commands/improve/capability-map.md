# Improve-loop capability map

**Purpose.** A registry of every capability the project has built (`dazzle` CLI +
MCP tools + `.claude` skills/commands + standalone loops), each with an owning lane,
**Class** (what kind of work it is), and staleness, so the `/improve` loop **polices
its own coverage** without confusing hygiene re-touch for agent cognition.

Driver rule 7 (see `improve.md`) reads this file to bias directed exploration toward
`UNOWNED` / **COGNITION** STALE / **HYGIENE** STALE / `OWNED-IDLE`. Product residual
probes and TR-rows outrank pure map lag.

**Status vocabulary**
- `USED` — exercised recently enough that lag < 20 (or re-stamped this cycle).
- `OWNED-IDLE` — has an owning lane but runs only on demand / low frequency.
- `STALE` / **STALE-effective** — owned but not exercised for ≥ **20** cycles
  (`USED` with lag ≥20 counts as STALE-effective even if the label lags).
- `UNOWNED` — built, but no lane invokes it. Strongest gap; capability-sweep flags these.
- `EXEMPT` — deliberately human-invoked; not a loop gap.

**Class vocabulary (selection weight)**
- **`COGNITION`** — changes agent *beliefs* about domain, demo world, seed spine,
  residual/risk, live trial. Prefer these when residual=0 and fleet under floor.
- **`HYGIENE`** — cheap CLI/MCP re-touch (validate, prove, coverage, sentinel, …).
  Keeps binaries honest; not epistemic progress by itself.
- **`DRIVER`** — improve-loop infrastructure (CodeQL, GitHub inbox). Re-stamped by
  the driver; not an explore dig target.
- **`EXEMPT`** — human-only (pitch, stems authoring, …).

**Metered vision:** `taste-panel` / `*-vision` are Class COGNITION but **must** be
exercised via subscription substitute (`hm_visual_smoke` / host-Read / gallery).
Never rank them as top dig on a paid metered path; never idle citing “metered STALE”.

**last-exercised** is the cycle number the owning lane last ran the capability
(stamped by the driver's Step-3 maintenance). `—` = never yet.

**Maintenance.** The driver stamps `last-exercised` each cycle (Step 3). Capability-sweep
(every 20 cycles) re-derives inventory and reports **actionable digs**:
`COGNITION_STALE=N`, `HYGIENE_STALE=N`, `UNOWNED=N` — not a single raw STALE total.

---

## Registry

| Capability | Class | Surface | Owning lane | Last-exercised | Status |
|---|---|---|---|---|---|
| `dazzle domain` / MCP `domain` (extract/gaps/research/promote) | COGNITION | CLI+MCP | **example-apps** + agent DX | 1094 | STALE |
| MCP `product_quality` (persona homes + stills + maturity + metric_list risk) | COGNITION | MCP | **example-apps** | 1094 | STALE |
| `dazzle demo quality` (#1626 felt residual bar) | COGNITION | CLI | **example-apps** | 1094 | STALE |
| `dazzle demo reset-and-load` (#1627 closed-loop seed) | COGNITION | CLI | example-apps + agent DX | 1096 | STALE |
| MCP `status` `demo_world`/`runtime` (#1629 world-model read) | COGNITION | MCP | example-apps + agent DX | 1095 | STALE |
| MCP `db` project-local DATABASE_URL (#1629 G2) | COGNITION | MCP | example-apps + agent DX | 1095 | STALE |
| `dazzle qa trial` | COGNITION | CLI | trials | 1097 | STALE |
| `qa-trial` skill | COGNITION | skill | trials | 1097 | STALE |
| **example product maturity** / WI D/N/L/J/G | COGNITION | script + strategy | **example-apps** | 1155 | USED |
| **demo fleet bar** (#1626) | COGNITION | script + strategy | **example-apps** | 1147 | USED |
| **example journey maturity** | COGNITION | script + strategy | **example-apps** | 1147 | USED |
| **unified example probes** | COGNITION | script | **example-apps** (driver) | 1155 | USED |
| `dazzle qa taste-panel` (metered; **use subscription substitute**) | COGNITION | CLI + `hm_visual_smoke` | **hm-convergence** + framework-ux | 1096 | STALE |
| `dazzle qa component-vision` (metered; **use host-Read / gallery**) | COGNITION | CLI + substitute | **hm-convergence** + framework-ux | 1096 | STALE |
| `dazzle qa property-vision` (metered; **use host-Read / gallery**) | COGNITION | CLI + substitute | **hm-convergence** | 1096 | STALE |
| **HM hyperpart coherence** | COGNITION | script + strategy | **hm-convergence** | 1096 | STALE |
| gallery_probes (`hm_gallery_probes.py`) | HYGIENE | script | **hm-convergence** | 1102 | STALE |
| `dazzle validate` / `lint` | HYGIENE | CLI | example-apps (Tier 1) | 1147 | USED |
| `dazzle ux verify` (contracts/interactions) | HYGIENE | CLI | framework-ux, ux-converge, example-apps | 1113 | STALE |
| `dazzle qa capture` (Tier-2 visual scrape) | HYGIENE | CLI | example-apps (visual_tier2) | 1114 | STALE |
| `dazzle qa login` | HYGIENE | CLI | (support for capture/verify) | 1113 | STALE |
| `hm gallery interaction probes` | HYGIENE | script + strategy | **hm-convergence** | 1102 | STALE |
| `dazzle deploy plan` | HYGIENE | CLI | example-apps (Tier 1) | 1100 | STALE |
| MCP `conformance` | HYGIENE | MCP | example-apps (Tier 1) | 1147 | USED |
| MCP `dsl` (fidelity/validate/lint/brief/…) | HYGIENE | MCP | example-apps (Tier 1) | 1147 | USED |
| fitness **engine** | HYGIENE | Python API | framework-ux | 1101 | STALE |
| `dazzle sentinel mutate` | HYGIENE | CLI | test-suite | 1113 | STALE |
| `dazzle rhythm` | HYGIENE | CLI | example-apps | 1100 | STALE |
| `dazzle story` | HYGIENE | CLI + MCP | example-apps | 1100 | STALE |
| `dazzle test-design` | HYGIENE | CLI | example-apps | 1100 | STALE |
| `dazzle pulse` | HYGIENE | CLI | framework-ux | 1101 | STALE |
| `dazzle sentinel scan` | HYGIENE | CLI + MCP | framework-ux | 1100 | STALE |
| `dazzle fitness` CLI | HYGIENE | CLI | framework-ux | 1101 | STALE |
| `dazzle discovery` | HYGIENE | CLI + MCP | example-apps | 1147 | USED |
| `dazzle composition` | HYGIENE | CLI + MCP | framework-ux | 1101 | STALE |
| `dual_lock_queue` / `dual_lock_expand` | HYGIENE | script + strategy | **hm-convergence** | 1102 | STALE |
| `shadcn_parity` | HYGIENE | script + strategy | **hm-convergence** | 1102 | STALE |
| **HM zero-floor** | HYGIENE | script + gate | **hm-convergence** | 1102 | STALE |
| `dazzle sweep` / `nightly` | HYGIENE | CLI | test-suite | 1113 | STALE |
| `/fuzz` | HYGIENE | standalone loop | own entrypoint | 1114 | STALE |
| `/smells` | HYGIENE | standalone loop | own entrypoint | 1114 | STALE |
| `/xproject` | HYGIENE | standalone loop | own entrypoint | 1114 | STALE |
| `dazzle rbac` | HYGIENE | CLI | framework-ux | 1099 | STALE |
| `dazzle coverage` | HYGIENE | CLI | example-apps | 1100 | STALE |
| `dazzle fragment-audit` | HYGIENE | CLI | framework-ux | 1101 | STALE |
| `dazzle process` | HYGIENE | CLI + MCP | example-apps | 1113 | STALE |
| `dazzle compliance` | HYGIENE | CLI + MCP | example-apps | 1147 | USED |
| MCP `policy` | HYGIENE | MCP | framework-ux | 1061 | STALE |
| MCP `test_intelligence` | HYGIENE | MCP | test-suite | 1062 | STALE |
| MCP `semantics` | HYGIENE | MCP | example-apps | 1062 | STALE |
| `dazzle representation` + MCP `representation` | HYGIENE | CLI + MCP | framework-ux + example-apps | 1099 | STALE |
| `dazzle prove` | HYGIENE | CLI | framework-ux + example-apps | 1099 | STALE |
| `dazzle scaffold` | HYGIENE | CLI | example-apps | 1101 | STALE |
| `dazzle.risk` model-driven failure-mode scoring (MDF-01..14) | HYGIENE | Python package | **framework-ux** | 1093 | STALE |
| **CodeQL / code-scanning** | DRIVER | GitHub API + strategy | **driver (Step 0c2)** | 1157 | USED |
| **GitHub inbox** | DRIVER | GitHub API + strategies | **driver (Step 0c3)** | 1157 | USED |
| `dazzle pitch` | EXEMPT | CLI + MCP | — | — | EXEMPT (human-invoked) |
| `dazzle spec` / `spec-narrate` skill | EXEMPT | CLI + skill | — | — | EXEMPT (stakeholder docs) |
| `dsl-authoring` skill | EXEMPT | skill | — | — | EXEMPT (in-session) |
| `phase-contract` skill | EXEMPT | skill | — | — | EXEMPT (execution harness) |
| `stems` skill | EXEMPT | skill | — | — | EXEMPT (epistemic entry) |

---

## Cycle notes (newest first)

> **Cycle 1157 (2026-07-20).** **capability-sweep** Class STALE recompute @ cycle **1157**
> (cadence ≥20 since 1112). Inventory CLI/skills/commands present; **UNOWNED=0**.
> **COGNITION_STALE=12** (domain/demo quality/reset-and-load/product_quality/
> demo_world/db/qa trial/hyperpart + 3 metered vision — use free substitutes only).
> **HYGIENE_STALE=33** incl. policy/test_intelligence/semantics (highest lag)
> + framework/hm/test-suite cluster. DRIVER CodeQL + GitHub inbox **USED@1157**.
> budget_consumed 0. Explore **0/100**. Next digs: COGNITION domain/demo_world over pure WI D,
> or HYGIENE policy/semantics/test_intelligence, or acme/hr densify (skip invoice soft-cap).

> **Cycle 1156 (2026-07-20).** **self-audit 5 CLEAN** — cadence ≥15 since 1103
> (`45106aefb`). Window `45106aefb..1d759a5eb` (52 improve commits). Sampled largest:
> ops densify 1106, acme public_billing 1148, fieldtest critical_ops 1116, capability
> stamps 1147, fieldtest active_ops 1155. All claim↔diff hold; acme auditspec drift
> 2/2 green; desks present in DSL. budget_consumed 0. Explore **0/100** (operator
> `--reset-budget`). Next: capability-sweep due or acme/hr WI D densify (skip invoice).

> **Cycle 1155 (2026-07-20).** **example-apps ordinary explore** fieldtest_hub WI D —
> skipped invoice_ops desk-cap; new **active_ops** desk + engineer/manager nav.
> dens ~0.29 (desk-entity soft cap); fleet **0.081**. budget_consumed 1. Explore **37/100**.

> **Cycle 1154 (2026-07-20).** **example-apps ordinary explore** ops_dashboard WI D —
> skipped invoice_ops desk-cap; new **critical_ops** desk + ops_nav.
> dens **0.29→0.25**; fleet **0.081**. budget_consumed 1. Explore **36/100**.

> **Cycle 1153 (2026-07-20).** **example-apps ordinary explore** llm_ticket_classifier WI D —
> skipped invoice_ops desk-cap; new **sentiment_ops** desk + agent/supervisor nav.
> dens **0.29→0.25**; fleet **0.082**. budget_consumed 1. Explore **35/100**.

> **Cycle 1152 (2026-07-20).** **example-apps ordinary explore** fieldtest_hub WI D —
> skipped invoice_ops desk-cap; new **released_ops** desk + engineer/manager nav.
> dens **0.29→0.27**; fleet **0.083**. budget_consumed 1. Explore **34/100**.

> **Cycle 1151 (2026-07-20).** **example-apps ordinary explore** design_studio WI D —
> skipped invoice_ops desk-cap; new **review_pipeline** desk + designer/reviewer nav.
> dens **0.29→0.27**; fleet **0.083**. budget_consumed 1. Explore **33/100**.

> **Cycle 1150 (2026-07-20).** **example-apps ordinary explore** project_tracker WI D —
> skipped invoice_ops desk-cap; new **todo_ops** desk + admin/manager/member nav.
> dens **0.29→0.28**; fleet **0.083**. budget_consumed 1. Explore **32/100**.

> **Cycle 1149 (2026-07-20).** **example-apps ordinary explore** hr_records WI D —
> skipped invoice_ops desk-cap; new **dept_ops** desk + hr_admin/manager/finance nav.
> dens **0.29→0.28**; fleet **0.084**. budget_consumed 1. Explore **31/100**.

> **Cycle 1148 (2026-07-20).** **example-apps ordinary explore** acme_billing WI D —
> skipped invoice_ops desk-cap; new **public_billing** desk + owner/auditor/member nav;
> co-ship auditspec dsl_hash **sha256:db2d02cd0cdc5650**.
> dens **0.29→0.28**; fleet **0.084**; wi_next still invoice_ops (capped dens edge).
> budget_consumed 1. Explore **30/100**.

> **Cycle 1147 (2026-07-20).** **COGNITION+HYGIENE STALE dig** — invoice_ops WI D at
> desk-entity soft cap (dens stuck ~0.30 despite 21 desks). Exercised demo_fleet +
> journey probes (residual=0), unified probes, validate/lint, conformance summary,
> discovery run, compliance evidence/gaps. Stamped STALE MCP conformance/dsl + lagging
> demo/journey/discovery/compliance **USED@1147**. No product DSL ship. budget_consumed 1.
> Explore **29/100**. Next: non-invoice_ops WI D or remaining STALE (policy/test_intelligence/semantics).

> **Cycle 1146 (2026-07-20).** **example-apps ordinary explore** invoice_ops WI D —
> new **pending_ops** desk (metrics/queue/grid/timeline/chart) + finance/auditor/admin nav.
> dens **0.26→0.25**; wi_next→**invoice_ops**; fleet **0.085**. budget_consumed 1.
> Explore **28/100**.

> **Cycle 1145 (2026-07-20).** **example-apps ordinary explore** invoice_ops WI D —
> new **region_ops** desk (metrics/queue/grid/timeline/chart) + finance/auditor/admin nav.
> dens **0.27→0.26**; wi_next→**invoice_ops**; fleet **0.085**. budget_consumed 1.
> Explore **27/100**.

> **Cycle 1144 (2026-07-20).** **example-apps ordinary explore** invoice_ops WI D —
> new **succeeded_ops** desk (metrics/queue/grid/timeline/chart) + finance/auditor/admin nav.
> dens **0.28→0.27**; wi_next→**invoice_ops**; fleet **0.085**. budget_consumed 1.
> Explore **26/100**.

> **Cycle 1143 (2026-07-20).** **example-apps ordinary explore** invoice_ops WI D —
> new **submitted_ops** desk (metrics/queue/grid/timeline/chart) + multi-persona nav.
> dens **0.30→0.28**; wi_next→**invoice_ops**; fleet **0.085**. budget_consumed 1.
> Explore **25/100**.

> **Cycle 1142 (2026-07-20).** **example-apps ordinary explore** fieldtest_hub WI D —
> new **draft_releases** desk (metrics/queue/grid/timeline/chart) + engineer/manager nav.
> dens **0.30→0.29**; wi_next→**invoice_ops**; fleet **0.085**. budget_consumed 1.
> Explore **24/100**.

> **Cycle 1141 (2026-07-20).** **example-apps ordinary explore** simple_task WI D —
> new **done_ops** desk (metrics/queue/grid/timeline/chart) + admin/manager/member nav.
> dens **0.30→0.27**; wi_next→**fieldtest_hub**; fleet **0.085**. budget_consumed 1.
> Explore **23/100**. Left dsl_generated_tests dirty alone.

> **Cycle 1140 (2026-07-20).** **example-apps ordinary explore** support_tickets WI D —
> new **progress_ops** desk (metrics/queue/grid/timeline/chart) + agent/manager/admin nav.
> dens **0.30→0.27**; wi_next→**simple_task**; fleet **0.086**. budget_consumed 1.
> Explore **22/100**. Left dsl_generated_tests dirty alone.

> **Cycle 1139 (2026-07-20).** **example-apps ordinary explore** invoice_ops WI D —
> new **approved_ops** desk (metrics/queue/grid/timeline/chart) + finance/auditor/admin nav.
> dens **0.30→0.29**; wi_next→**support_tickets**; fleet **0.086**. budget_consumed 1.
> Explore **21/100**.

> **Cycle 1138 (2026-07-20).** **example-apps ordinary explore** design_studio WI D —
> new **campaign_ops** desk (metrics/queue/grid/timeline/chart) + designer/reviewer nav.
> dens **0.31→0.29**; wi_next→**invoice_ops**; fleet **0.086**. budget_consumed 1.
> Explore **20/100**.

> **Cycle 1137 (2026-07-20).** **example-apps ordinary explore** acme_billing WI D —
> new **user_ops** desk (metrics/queue/grid/timeline/chart) + owner/auditor nav;
> co-ship auditspec dsl_hash **sha256:88b83eb24dd02cba**.
> dens **0.31→0.29**; wi_next→**design_studio**; fleet **0.087**. budget_consumed 1.
> Explore **19/100**.

> **Cycle 1136 (2026-07-20).** **example-apps ordinary explore** hr_records WI D —
> new **leavers_ops** desk (metrics/queue/grid/timeline/chart) + hr_admin/manager nav.
> dens **0.31→0.29**; wi_next→**acme_billing**; fleet **0.087**. budget_consumed 1.
> Explore **18/100**.

> **Cycle 1135 (2026-07-20).** **example-apps ordinary explore** project_tracker WI D —
> new **done_ops** desk (metrics/queue/grid/timeline/chart) + admin/manager/member nav.
> dens **0.31→0.29**; wi_next→**hr_records**; fleet **0.088**. budget_consumed 1.
> Explore **17/100**.

> **Cycle 1134 (2026-07-20).** **example-apps ordinary explore** fieldtest_hub WI D —
> new **retired_ops** desk (metrics/queue/grid/timeline/chart) + engineer/manager nav.
> dens **0.32→0.30**; wi_next→**project_tracker**; fleet **0.088**. budget_consumed 1.
> Explore **16/100**.

> **Cycle 1133 (2026-07-20).** **example-apps ordinary explore** invoice_ops WI D —
> new **paid_ops** desk (metrics/queue/grid/timeline/chart) + finance/auditor/admin nav.
> dens **0.32→0.30**; wi_next→**fieldtest_hub**; fleet **0.089**. budget_consumed 1.
> Explore **15/100**.

> **Cycle 1132 (2026-07-20).** **example-apps ordinary explore** acme_billing WI D —
> new **project_ops** desk (metrics/queue/grid/timeline/chart) + owner/auditor/member nav;
> co-ship auditspec dsl_hash **sha256:df7dd34decc08fd6**.
> dens **0.33→0.31**; wi_next→**invoice_ops**; fleet **0.089**. budget_consumed 1.
> Explore **14/100**.

> **Cycle 1131 (2026-07-20).** **example-apps ordinary explore** design_studio WI D —
> new **archive_ops** desk (metrics/queue/grid/timeline/chart) + designer/reviewer nav.
> dens **0.33→0.31**; wi_next→**acme_billing**; fleet **0.090**. budget_consumed 1.
> Explore **13/100**.

> **Cycle 1130 (2026-07-20).** **example-apps ordinary explore** fieldtest_hub WI D —
> new **recall_ops** desk (metrics/queue/grid/timeline/chart) + engineer/manager nav.
> dens **0.33→0.32**; wi_next→**design_studio**; fleet **0.090**. budget_consumed 1.
> Explore **12/100**.

> **Cycle 1129 (2026-07-20).** **example-apps ordinary explore** hr_records WI D —
> new **role_ops** desk (metrics/queue/grid/timeline/chart) + hr_admin/manager/finance nav.
> dens **0.33→0.31**; wi_next→**fieldtest_hub**; fleet **0.091**. budget_consumed 1.
> Explore **11/100**.

> **Cycle 1128 (2026-07-20).** **example-apps ordinary explore** invoice_ops WI D —
> new **partial_ops** desk (metrics/queue/grid/timeline/chart) + finance/auditor/admin nav.
> dens **0.33→0.32**; wi_next→**hr_records**; fleet **0.091**. budget_consumed 1.
> Explore **10/100**.

> **Cycle 1127 (2026-07-20).** **example-apps ordinary explore** llm_ticket_classifier WI D —
> new **category_ops** desk (metrics/queue/grid/timeline/chart) + agent/supervisor nav.
> dens **0.33→0.29**; wi_next→**invoice_ops**; fleet **0.092**. budget_consumed 1.
> Explore **9/100**.

> **Cycle 1126 (2026-07-20).** **example-apps ordinary explore** project_tracker WI D —
> new **delivery_ops** desk (metrics/queue/grid/timeline/chart) + admin/manager/member nav.
> dens **0.33→0.31**; wi_next→**llm_ticket_classifier**; fleet **0.093**. budget_consumed 1.
> Explore **8/100**.

> **Cycle 1125 (2026-07-20).** **example-apps ordinary explore** simple_task WI D —
> new **review_ops** desk (metrics/queue/grid/timeline/chart) + admin/manager/member nav.
> dens **0.33→0.30**; wi_next→**project_tracker**; fleet **0.093**. budget_consumed 1.
> Explore **7/100**. Left dsl_generated_tests dirty alone.

> **Cycle 1124 (2026-07-20).** **example-apps ordinary explore** support_tickets WI D —
> new **priority_ops** desk (metrics/queue/grid/timeline/chart) + agent/manager/admin nav.
> dens **0.33→0.30**; wi_next→**simple_task**; fleet **0.094**. budget_consumed 1.
> Explore **6/100**. Left dsl_generated_tests dirty alone.

> **Cycle 1123 (2026-07-20).** **example-apps ordinary explore** invoice_ops WI D —
> new **rejected_ops** desk (metrics/queue/grid/timeline/chart) + multi-persona nav.
> dens **0.35→0.33**; wi_next→**support_tickets**; fleet **0.095**. budget_consumed 1.
> Explore **5/100**.

> **Cycle 1122 (2026-07-20).** **example-apps ordinary explore** fieldtest_hub WI D —
> new **prototype_ops** desk (metrics/queue/grid/timeline/chart) + engineer/manager nav.
> dens **0.35→0.33**; wi_next→**invoice_ops**; fleet **0.095**. budget_consumed 1.
> Explore **4/100**.

> **Cycle 1121 (2026-07-20).** **example-apps ordinary explore** acme_billing WI D —
> new **org_ops** desk (metrics/queue/grid/timeline/chart) + owner/auditor/member nav;
> co-ship auditspec dsl_hash **sha256:4e7ab8eeda5bfeaf**.
> dens **0.36→0.33**; wi_next→**fieldtest_hub**; fleet **0.096**. budget_consumed 1.
> Explore **3/100**.

> **Cycle 1120 (2026-07-20).** **example-apps ordinary explore** hr_records WI D —
> new **salary_ops** desk (metrics/queue/grid/timeline/chart) + hr_admin/manager/finance nav.
> dens **0.36→0.33**; wi_next→**acme_billing**; fleet **0.097**. budget_consumed 1.
> Explore **2/100**.

> **Cycle 1119 (2026-07-20).** **example-apps ordinary explore** project_tracker WI D —
> new **priority_ops** desk (metrics/queue/grid/timeline/chart) + admin/manager/member nav.
> dens **0.36→0.33**; wi_next→**hr_records**; fleet **0.097**. budget_consumed 1.
> Explore **1/100** (manual reset 43→0 this session).

> **Cycle 1118 (2026-07-20).** **example-apps ordinary explore** design_studio WI D —
> new **draft_studio** desk (metrics/queue/grid/timeline/chart) + designer/reviewer nav.
> dens **0.364→0.333**; wi_next→**project_tracker**; fleet **0.098**. budget_consumed 1.
> Explore **43/100**.

> **Cycle 1117 (2026-07-20).** **example-apps ordinary explore** invoice_ops WI D —
> new **draft_ops** desk (metrics/queue/grid/timeline/chart) + multi-persona nav.
> dens **0.368→0.350**; wi_next→**design_studio**; fleet **0.098**. budget_consumed 1.
> Explore **42/100**.

> **Cycle 1116 (2026-07-20).** **example-apps ordinary explore** fieldtest_hub WI D —
> densify tester_dashboard (+severity chart); new **critical_ops** desk + eng/manager nav.
> dens **~0.375→0.353**; wi_next→**invoice_ops**; fleet **0.099**. budget_consumed 1.
> Explore **41/100**.

> **Cycle 1115 (2026-07-20).** **example-apps ordinary explore** simple_task WI D —
> new **priority_ops** desk (metrics/queue/grid/timeline/chart) + admin/manager/member nav.
> dens **~0.38→0.333**; wi_next→**fieldtest_hub**; fleet **0.099**. Left dsl_generated dirty alone.
> budget_consumed 1. Explore **40/100**.

> **Cycle 1114 (2026-07-20).** **HYGIENE dig** remaining STALE cluster — boot-fuzz
> simple_task/design_studio/fieldtest_hub (startup complete, no duplicate/FTS signatures);
> smells via fitness code + complexity ratchet green; xproject scout (AegisMark renderers
> advisory; cyfuture #1597 projection warnings); qa capture CLI exercised.
> Stamps fuzz/smells/xproject/qa capture **USED@1114**. HYGIENE STALE largely cleared.
> budget_consumed 1. Explore **39/100**.

> **Cycle 1113 (2026-07-20).** **example-apps/test-suite HYGIENE dig** — process propose +
> diagram; sentinel mutate domain_brief/models (29% kill); sweep examples (coverage 100%);
> ux verify --structural (338 interactions); qa login magic-link on simple_task :3971.
> Stamps process/sentinel mutate/sweep/qa login/ux verify **USED@1113**. budget_consumed 1.
> Explore **38/100**. Remaining HYGIENE: smells, fuzz, xproject, qa capture.

> **Cycle 1112 (2026-07-20) capability-sweep.** Inventory: CLI surface from `dazzle --help`
> (domain/demo/qa/validate/compliance/fitness/… still present); skills (dsl-authoring,
> qa-trial, stems, …); commands (/improve, /fuzz, /xproject, /smells). **UNOWNED=0**.
> **COGNITION_STALE=0** (domain/demo/qa trial/journey/vision substitutes all lag<20 after
> 1093–1111 digs). **HYGIENE_STALE=9** (ux verify, sentinel mutate, sweep, smells, qa
> capture/login, fuzz, xproject, process — lag≥48). DRIVER CodeQL+inbox re-stamped USED@1112.
> Recomputed STALE labels at current_cycle=1112. **Not** a product dig.
> budget_consumed 0. Explore **37/100**. Next sweep ~**1132**. Prefer next digs: HYGIENE
> ux-verify/process/sentinel cluster or ordinary WI D simple_task.

> **Cycle 1111 (2026-07-20).** **example-apps ordinary explore** support_tickets WI D —
> new **resolution_ops** desk (metrics/queue/grid/timeline/chart) + agent/manager/admin nav.
> dens **~0.38→0.333**; wi_next→**simple_task**; fleet **0.101**. Left dsl_generated_tests dirty alone.
> budget_consumed 1. Explore **37/100**.

> **Cycle 1110 (2026-07-20).** **example-apps ordinary explore** acme_billing WI D —
> new **collections_ops** desk + auditspec co-ship (sha256:8bc50f77b9b61bdf).
> dens **~0.38→0.357**; wi_next→**support_tickets**; fleet **0.102**. budget_consumed 1.
> Explore **36/100**.

> **Cycle 1109 (2026-07-20).** **example-apps ordinary explore** hr_records WI D —
> new **employment_ops** desk (metrics/queue/grid/timeline/chart) + hr/manager/finance nav.
> dens **~0.38→0.357**; wi_next→**acme_billing**; fleet **0.102**. budget_consumed 1.
> Explore **35/100**.

> **Cycle 1108 (2026-07-20).** **example-apps ordinary explore** project_tracker WI D —
> new **backlog_ops** desk (metrics/queue/grid/timeline/chart) + admin/manager/member nav.
> dens **~0.38→0.357**; wi_next→**hr_records**; fleet **0.103**. budget_consumed 1.
> Explore **34/100**.

> **Cycle 1107 (2026-07-20).** **example-apps ordinary explore** invoice_ops WI D —
> new **settlement_ops** desk (PaymentAttempt metrics/queue/grid/timeline/chart) + finance/auditor nav.
> dens **~0.39→0.368**; wi_next→**project_tracker**; fleet **0.104**. budget_consumed 1.
> Explore **33/100**.

> **Cycle 1106 (2026-07-20).** **example-apps ordinary explore** ops_dashboard WI D —
> densify systems_desk + alerts_desk (grid/queue/timeline/chart); new **integrations_desk**.
> dens **0.39→0.286**; wi **0.12→0.086**; wi_next→**invoice_ops**; fleet **0.104**.
> budget_consumed 1. Explore **32/100**.

> **Cycle 1105 (2026-07-20).** **example-apps ordinary explore** design_studio WI D —
> new **publish_desk** (metrics/queue/grid/timeline/chart) + designer/reviewer nav.
> dens **0.40→0.364**; wi_next→**ops_dashboard**; fleet **0.107**. budget_consumed 1.
> Explore **31/100**.

> **Cycle 1104 (2026-07-20).** **example-apps ordinary explore** fieldtest_hub WI D —
> new **device_fleet** desk (metrics/grid/queue/timeline/chart) + engineer/manager nav.
> dens **0.40→0.375**; wi_next→**design_studio**; fleet under floor. budget_consumed 1.
> Explore **30/100**.

> **Cycle 1103 (2026-07-20).** **self-audit 5 CLEAN** — window 379d949d7..1bc36a3d4
> (42 improve commits since last *git* self-audit; log-only 0000 entry not a ship).
> Sampled largest: 1094 domain, 1097 backend-only QA, 1095 complexity, 1098 auditspec,
> 1082 hr_records. All claim↔diff hold; 29 unit tests green on current tip. budget 0.
> Explore **29/100**.

> **Cycle 1102 (2026-07-20).** **hm-convergence HYGIENE dig** — dual_lock queue depth
> **0**; shadcn_parity gaps **0**; gallery_probes **6/6 PASS**; zero-floor **GREEN** (0/0);
> example_hm_surface **HM_OK 12/12**. Stamps dual_lock/shadcn/gallery/zero-floor **USED@1102**.
> budget_consumed 1. Explore **29/100**.

> **Cycle 1101 (2026-07-20).** **framework-ux HYGIENE dig** — fitness code top30 +
> vitality + clones; composition audit simple_task **100/100**; pulse run (quality/security
> 100%); fragment-audit all regions green; scaffold CLI exercised. Stamps fitness
> engine/CLI + composition + pulse + fragment-audit + scaffold **USED@1101**.
> budget_consumed 1. Explore **28/100**.

> **Cycle 1100 (2026-07-20).** **example-apps HYGIENE dig** — coverage 61/61 (100%);
> sentinel scan simple_task (info/low only); compliance acme compile (auditspec stable);
> deploy plan; story list; rhythm gaps advisory; discovery report; test-design coverage-actions.
> Stamps coverage/sentinel/compliance/deploy/story/rhythm/discovery/test-design **USED@1100**.
> budget_consumed 1. Explore **27/100**.

> **Cycle 1099 (2026-07-20).** **example-apps HYGIENE dig** — validate/lint simple_task +
> fieldtest_hub clean; prove story 13/13; prove representation OK (warn multi optional
> refs on Task); rbac report. Stamps validate/lint/prove/representation/rbac **USED@1099**.
> budget_consumed 1. Explore **26/100**.

> **Cycle 1097 (2026-07-20).** **trials COGNITION dig** — qa trial inventory/coverage +
> fix `serve --backend-only` so QA magic-link mounts (auth + DAZZLE_QA_MODE + shared
> `_mount_qa_mode_if_armed`). Live trial-coverage as manager after fix (18 targets probed).
> Stamps qa trial + skill **USED@1097**. budget_consumed 1. Explore **25/100**.

> **Cycle 1096 (2026-07-20).** **example-apps + hm-convergence COGNITION dig** —
> simple_task serve :3961 + `demo reset-and-load -y` **created_count=8**,
> persona_homes_residual=0, live_desk_residual=0. HM coherence queue=0 mean=8.7.
> Free vision substitute `hm_visual_smoke --dazzle-emit` (11 parts + full_page.png).
> Stamps reset-and-load + hyperpart + vision triad **USED@1096**. budget_consumed 1.
> Explore **24/100**.

> **Cycle 1095 (2026-07-20).** **preflight + COGNITION dig** — complexity ratchet red
> after 1094 extract helpers (`_try_add_discovered_noun` 21, `_collect_questions` 16).
> Refactored into small helpers; preflight green. Also exercised demo_world + resolve_db_url
> on simple_task, demo_fleet 9/9, journey residual=0. Stamps demo_world/db/demo_fleet/
> journey **USED@1095**. budget_consumed 1. Explore **23/100**.

> **Cycle 1094 (2026-07-20).** **example-apps COGNITION dig** — domain extract quality
> for generated SPECIFICATION.md + design_studio AGENT_DOMAIN. Extract: definitional
> sentences, tighter article_noun, product-title skip, broken-question filter.
> design_studio nouns 30→4 (Brand/DesignAsset/Campaign/DesignFeedback); ready_to_promote.
> demo quality residual_total=0. budget_consumed 1. Explore **22/100**.

> **Cycle 1093 (2026-07-20).** **framework-ux UNOWNED exercise** — `dazzle.risk` MDF
> catalogue (14 modes). Unit suite green; live `build_report` over full CATALOGUE with
> framework-shaped detectors (overall score 25; top residual MDF-12 correlated QA blind
> spots risk=25, MDF-13 demo cliff=23, MDF-04 escape-hatch collapse=20). UNOWNED→**USED**
> @1093. budget_consumed 1. Explore **21/100**. Prefer next digs: COGNITION
> domain/demo_world/product_quality over further WI D desks.

> **Cycle 1092 (2026-07-20) capability-sweep.** Inventory: CLI surface from `dazzle --help`
> (domain/demo/qa/validate/compliance/… still present); skills (dsl-authoring, qa-trial,
> stems, …); commands (/improve, /fuzz, /xproject, …). **UNOWNED=1**
> (`dazzle.risk` model-driven scoring package shipped cycle 1070, not yet exercised by a
> lane). **COGNITION_STALE=14** (domain/demo quality/reset-and-load/qa trial/
> journey/demo_fleet/hyperpart + metered vision substitutes). **HYGIENE_STALE=37**
> (validate/prove/coverage/sentinel/MCP cluster lag≥20 after long WI D streak).
> Recomputed STALE labels at current_cycle=1092. **Not** a product dig.
> budget_consumed 0. Explore **20/100**. Next sweep ~**1112**. Prefer next digs:
> COGNITION domain/demo_world/product_quality over further WI D desks.


> **Cycle 1069 (2026-07-19).** **example-apps ordinary explore** acme_billing WI D:
> invoices kanban+chart; team timeline; new orgs_home desk. WI **0.20→0.19** dens
> **0.52→0.47**; fleet **0.157**. Explore **14/100**.

> **Cycle 1068 (2026-07-19).** **example-apps ordinary explore** fieldtest_hub WI D cont:
> engineering_dashboard list→timeline/grid/chart. WI dens still ~0.51; fleet **0.159**.
> Explore **13/100**.

> **Cycle 1067 (2026-07-19).** **example-apps ordinary explore** project_tracker WI D:
> milestones/discussion/files/my_tasks diversify (timeline/grid/chart). WI **0.21→0.20**
> dens **0.54→0.51**; fleet **0.159**. Explore **12/100**.

> **Cycle 1066 (2026-07-19).** **example-apps ordinary explore** fieldtest_hub WI D:
> manager_ops timeline+kanban+chart; issue_triage grid+timeline; firmware grid+timeline;
> field_kit metrics+grid. WI **0.22→0.20** dens **0.56→0.51**; wi_next→**project_tracker**;
> fleet **0.160**. Explore **11/100**.

> **Cycle 1065 (2026-07-19).** **example-apps ordinary explore** invoice_ops WI D:
> pay_desk kanban+timeline; audit_review grid+timeline+chart. WI **0.23→0.19** dens
> **0.53→0.50**; wi_next→**fieldtest_hub**; wi_fleet **0.161**. residual=0. Explore **10/100**.

> **Cycle 1064 (2026-07-19).** **example-apps HYGIENE dig** — story/rhythm/discovery/process/deploy/
> test-design on support_tickets; HM gallery 6/6; zero-floor GREEN. budget_consumed 1. Explore **9/100**.

> **Cycle 1063 (2026-07-19).** **example-apps HYGIENE dig** — xproject sibling validate
> (cyfuture/AegisMark/pennydreadful exit 0 warn-only); support_tickets boot-stderr clean;
> design_studio qa capture **6** designer screens. budget_consumed 1. Explore **8/100**.

> **Cycle 1062 (2026-07-19).** **framework-ux HYGIENE dig** — fitness code top30 hotspots;
> vitality support_tickets 0 islets; qa login designer magic-link OK (design_studio :3948);
> MCP semantics tenancy shared_schema; test_intelligence summary (KG not init — exercised).
> budget_consumed 1. Explore **7/100**.

> **Cycle 1061 (2026-07-19).** **test-suite/example-apps HYGIENE dig** — sentinel scan
> support_tickets (MT/PR/BL findings advisory); coverage **61/61 100%**; sweep examples exit 0
> (warns only); MCP policy analyze (User/SlaWaiver unprotected; conflicts 0); conformance
> summary **481** cases. budget_consumed 1. Explore **6/100**.

> **Cycle 1060 (2026-07-19).** **framework-ux/example-apps HYGIENE dig** — support_tickets
> validate+lint OK (warns only); ux verify contracts **64/0/38** (seed 400 advisory created_by);
> composition **100/100**; rbac matrix OK; fragment-audit exit 0; dual_lock queue **0**;
> shadcn gaps **0**. budget_consumed 1. Explore **5/100**.

> **Cycle 1059 (2026-07-19).** **example-apps COGNITION dig** — demo_world + db + qa trial
> inventory: simple_task serve :3945, reset-and-load 8 fixtures, demo_world residual=0,
> db status Task×8 User×3; support_tickets trial-inventory + trial-coverage static 19 targets.
> budget_consumed 1. Explore **4/100**.

> **Cycle 1058 (2026-07-19).** **self-audit** (cadence ≥15 since 1043): window `f23faac93..HEAD`.
> Sampled 5: domain research, Core Entities filter, STALE policy, cimonitor auditspec, simple_task AGENT_DOMAIN — **5 CLEAN / 0 DISCREPANCY**. budget_consumed 0. Explore **3/100**. Next self-audit ~**1073**.

> **Cycle 1057 (2026-07-19).** **example-apps HYGIENE STALE dig** (COGNITION STALE cleared recently):
> support_tickets `prove story` 18+ OK; `prove representation` OK; representation patterns+classify;
> compliance gaps 10 tier-3; pulse radar 68%. scaffold CLI exercised. No WI D. budget_consumed 1.
> Explore **3/100**.

> **Cycle 1056 (2026-07-19).** **example-apps COGNITION dig** — domain extract quality on
> long SPECs: Core Entities headers + expanded deny; fieldtest_hub nouns **41→7**
> (Device, IssueReport, TestSession, FirmwareRelease, Task, …). demo_fleet 9/9;
> HM coherence queue=0 mean=8.7; gallery probes 6/6. metric_list risk=2 remains
> OBSERVE-only (F10). budget_consumed 1. Explore **2/100**.

> **Cycle 1055 (2026-07-19).** **example-apps COGNITION dig** after policy + budget reset:
> `domain extract/gaps/promote` on simple_task (Task+Taskcomment grounded; chrome rejected;
> ready_to_promote); serve :3942 + `demo reset-and-load` 8 fixtures persona_homes=0;
> `demo quality` residual_total=0 metric_list **risk=1**; free vision substitute
> `hm_visual_smoke --dazzle-emit` 11 parts. **Not** WI D (fleet under floor). budget_consumed 1.
> Explore **1/100**. Stamps domain/demo quality/reset-and-load/product_quality + vision substitutes @1055.

> **Cycle 1055 (policy).** STALE Class COGNITION vs HYGIENE; rule 7 cognition-first; budget reset.

> **Cycle 1054 (2026-07-19) capability-sweep.** Inventory MCP **38**; **0 UNOWNED**.
> Pre-policy STALE-effective raw count 26 (now report as COGNITION vs HYGIENE digs).
> Explore was **100/100** — no dig. Next sweep ~**1074**.

> **Cycle 1049 (2026-07-19).** **cimonitor** CI repair (mypy + research complexity + acme auditspec).

> **Cycle 1048 (2026-07-19).** housekeeping — explore cap (policy later forbids blaming STALE).

> **Cycle 1043 (2026-07-19).** **self-audit** 5 CLEAN. Next self-audit ~**1058**.
