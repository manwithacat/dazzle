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
| `dazzle domain` / MCP `domain` (extract/gaps/research/promote) | COGNITION | CLI+MCP | **example-apps** + agent DX | 1056 | USED |
| MCP `product_quality` (persona homes + stills + maturity + metric_list risk) | COGNITION | MCP | **example-apps** | 1055 | USED |
| `dazzle demo quality` (#1626 felt residual bar) | COGNITION | CLI | **example-apps** | 1055 | USED |
| `dazzle demo reset-and-load` (#1627 closed-loop seed) | COGNITION | CLI | example-apps + agent DX | 1059 | USED |
| MCP `status` `demo_world`/`runtime` (#1629 world-model read) | COGNITION | MCP | example-apps + agent DX | 1059 | USED |
| MCP `db` project-local DATABASE_URL (#1629 G2) | COGNITION | MCP | example-apps + agent DX | 1059 | USED |
| `dazzle qa trial` | COGNITION | CLI | trials | 1059 | USED |
| `qa-trial` skill | COGNITION | skill | trials | 1059 | USED |
| **example product maturity** / WI D/N/L/J/G | COGNITION | script + strategy | **example-apps** | 1086 | USED |
| **demo fleet bar** (#1626) | COGNITION | script + strategy | **example-apps** | 1056 | USED |
| **example journey maturity** | COGNITION | script + strategy | **example-apps** | 1054 | USED |
| **unified example probes** | COGNITION | script | **example-apps** (driver) | 1086 | USED |
| `dazzle qa taste-panel` (metered; **use subscription substitute**) | COGNITION | CLI + `hm_visual_smoke` | **hm-convergence** + framework-ux | 1055 | USED |
| `dazzle qa component-vision` (metered; **use host-Read / gallery**) | COGNITION | CLI + substitute | **hm-convergence** + framework-ux | 1055 | USED |
| `dazzle qa property-vision` (metered; **use host-Read / gallery**) | COGNITION | CLI + substitute | **hm-convergence** | 1055 | USED |
| **HM hyperpart coherence** | COGNITION | script + strategy | **hm-convergence** | 1056 | USED |
| gallery_probes (`hm_gallery_probes.py`) | HYGIENE | script | **hm-convergence** | 1064 | USED |
| `dazzle validate` / `lint` | HYGIENE | CLI | example-apps (Tier 1) | 1060 | USED |
| `dazzle ux verify` (contracts/interactions) | HYGIENE | CLI | framework-ux, ux-converge, example-apps | 1060 | USED |
| `dazzle qa capture` (Tier-2 visual scrape) | HYGIENE | CLI | example-apps (visual_tier2) | 1063 | USED |
| `dazzle qa login` | HYGIENE | CLI | (support for capture/verify) | 1063 | USED |
| `hm gallery interaction probes` | HYGIENE | script + strategy | **hm-convergence** | 1064 | USED |
| `dazzle deploy plan` | HYGIENE | CLI | example-apps (Tier 1) | 1064 | USED |
| MCP `conformance` | HYGIENE | MCP | example-apps (Tier 1) | 1061 | USED |
| MCP `dsl` (fidelity/validate/lint/brief/…) | HYGIENE | MCP | example-apps (Tier 1) | 1061 | USED |
| fitness **engine** | HYGIENE | Python API | framework-ux | 1062 | USED |
| `dazzle sentinel mutate` | HYGIENE | CLI | test-suite | 1061 | USED |
| `dazzle rhythm` | HYGIENE | CLI | example-apps | 1064 | USED |
| `dazzle story` | HYGIENE | CLI + MCP | example-apps | 1064 | USED |
| `dazzle test-design` | HYGIENE | CLI | example-apps | 1064 | USED |
| `dazzle pulse` | HYGIENE | CLI | framework-ux | 1057 | USED |
| `dazzle sentinel scan` | HYGIENE | CLI + MCP | framework-ux | 1061 | USED |
| `dazzle fitness` CLI | HYGIENE | CLI | framework-ux | 1062 | USED |
| `dazzle discovery` | HYGIENE | CLI + MCP | example-apps | 1064 | USED |
| `dazzle composition` | HYGIENE | CLI + MCP | framework-ux | 1060 | USED |
| `dual_lock_queue` / `dual_lock_expand` | HYGIENE | script + strategy | **hm-convergence** | 1060 | USED |
| `shadcn_parity` | HYGIENE | script + strategy | **hm-convergence** | 1060 | USED |
| **HM zero-floor** | HYGIENE | script + gate | **hm-convergence** | 1064 | USED |
| `dazzle sweep` / `nightly` | HYGIENE | CLI | test-suite | 1061 | USED |
| `/fuzz` | HYGIENE | standalone loop | own entrypoint | 1063 | USED |
| `/smells` | HYGIENE | standalone loop | own entrypoint | 1062 | USED |
| `/xproject` | HYGIENE | standalone loop | own entrypoint | 1063 | USED |
| `dazzle rbac` | HYGIENE | CLI | framework-ux | 1060 | USED |
| `dazzle coverage` | HYGIENE | CLI | example-apps | 1061 | USED |
| `dazzle fragment-audit` | HYGIENE | CLI | framework-ux | 1060 | USED |
| `dazzle process` | HYGIENE | CLI + MCP | example-apps | 1064 | USED |
| `dazzle compliance` | HYGIENE | CLI + MCP | example-apps | 1057 | USED |
| MCP `policy` | HYGIENE | MCP | framework-ux | 1061 | USED |
| MCP `test_intelligence` | HYGIENE | MCP | test-suite | 1062 | USED |
| MCP `semantics` | HYGIENE | MCP | example-apps | 1062 | USED |
| `dazzle representation` + MCP `representation` | HYGIENE | CLI + MCP | framework-ux + example-apps | 1057 | USED |
| `dazzle prove` | HYGIENE | CLI | framework-ux + example-apps | 1057 | USED |
| `dazzle scaffold` | HYGIENE | CLI | example-apps | 1057 | USED |
| **CodeQL / code-scanning** | DRIVER | GitHub API + strategy | **driver (Step 0c2)** | 1054 | USED |
| **GitHub inbox** | DRIVER | script + strategies | **driver (Step 0c3)** | 1054 | USED |
| `dazzle pitch` | EXEMPT | CLI + MCP | — | — | EXEMPT (human-invoked) |
| `dazzle spec` / `spec-narrate` skill | EXEMPT | CLI + skill | — | — | EXEMPT (stakeholder docs) |
| `dsl-authoring` skill | EXEMPT | skill | — | — | EXEMPT (in-session) |
| `phase-contract` skill | EXEMPT | skill | — | — | EXEMPT (execution harness) |
| `stems` skill | EXEMPT | skill | — | — | EXEMPT (epistemic entry) |

---

## Cycle notes (newest first)

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
