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
| `dazzle demo reset-and-load` (#1627 closed-loop seed) | COGNITION | CLI | example-apps + agent DX | 1055 | USED |
| MCP `status` `demo_world`/`runtime` (#1629 world-model read) | COGNITION | MCP | example-apps + agent DX | 1039 | USED |
| MCP `db` project-local DATABASE_URL (#1629 G2) | COGNITION | MCP | example-apps + agent DX | 1039 | USED |
| `dazzle qa trial` | COGNITION | CLI | trials | 1039 | USED |
| `qa-trial` skill | COGNITION | skill | trials | 1039 | USED |
| **example product maturity** / WI D/N/L/J/G | COGNITION | script + strategy | **example-apps** | 1054 | USED |
| **demo fleet bar** (#1626) | COGNITION | script + strategy | **example-apps** | 1056 | USED |
| **example journey maturity** | COGNITION | script + strategy | **example-apps** | 1054 | USED |
| **unified example probes** | COGNITION | script | **example-apps** (driver) | 1054 | USED |
| `dazzle qa taste-panel` (metered; **use subscription substitute**) | COGNITION | CLI + `hm_visual_smoke` | **hm-convergence** + framework-ux | 1055 | USED |
| `dazzle qa component-vision` (metered; **use host-Read / gallery**) | COGNITION | CLI + substitute | **hm-convergence** + framework-ux | 1055 | USED |
| `dazzle qa property-vision` (metered; **use host-Read / gallery**) | COGNITION | CLI + substitute | **hm-convergence** | 1055 | USED |
| **HM hyperpart coherence** | COGNITION | script + strategy | **hm-convergence** | 1056 | USED |
| gallery_probes (`hm_gallery_probes.py`) | HYGIENE | script | **hm-convergence** | 1056 | USED |
| `dazzle validate` / `lint` | HYGIENE | CLI | example-apps (Tier 1) | 1030 | USED |
| `dazzle ux verify` (contracts/interactions) | HYGIENE | CLI | framework-ux, ux-converge, example-apps | 1029 | USED |
| `dazzle qa capture` (Tier-2 visual scrape) | HYGIENE | CLI | example-apps (visual_tier2) | 1032 | USED |
| `dazzle qa login` | HYGIENE | CLI | (support for capture/verify) | 1032 | USED |
| `hm gallery interaction probes` | HYGIENE | script + strategy | **hm-convergence** | 1027 | USED |
| `dazzle deploy plan` | HYGIENE | CLI | example-apps (Tier 1) | 1037 | USED |
| MCP `conformance` | HYGIENE | MCP | example-apps (Tier 1) | 1030 | USED |
| MCP `dsl` (fidelity/validate/lint/brief/…) | HYGIENE | MCP | example-apps (Tier 1) | 1030 | USED |
| fitness **engine** | HYGIENE | Python API | framework-ux | 1036 | USED |
| `dazzle sentinel mutate` | HYGIENE | CLI | test-suite | 1033 | USED |
| `dazzle rhythm` | HYGIENE | CLI | example-apps | 1037 | USED |
| `dazzle story` | HYGIENE | CLI + MCP | example-apps | 1037 | USED |
| `dazzle test-design` | HYGIENE | CLI | example-apps | 1037 | USED |
| `dazzle pulse` | HYGIENE | CLI | framework-ux | 1026 | USED |
| `dazzle sentinel scan` | HYGIENE | CLI + MCP | framework-ux | 1033 | USED |
| `dazzle fitness` CLI | HYGIENE | CLI | framework-ux | 1036 | USED |
| `dazzle discovery` | HYGIENE | CLI + MCP | example-apps | 1037 | USED |
| `dazzle composition` | HYGIENE | CLI + MCP | framework-ux | 1029 | USED |
| `dual_lock_queue` / `dual_lock_expand` | HYGIENE | script + strategy | **hm-convergence** | 1027 | USED |
| `shadcn_parity` | HYGIENE | script + strategy | **hm-convergence** | 1027 | USED |
| **HM zero-floor** | HYGIENE | script + gate | **hm-convergence** | 1027 | USED |
| `dazzle sweep` / `nightly` | HYGIENE | CLI | test-suite | 1031 | USED |
| `/fuzz` | HYGIENE | standalone loop | own entrypoint | 1031 | USED |
| `/smells` | HYGIENE | standalone loop | own entrypoint | 1036 | USED |
| `/xproject` | HYGIENE | standalone loop | own entrypoint | 1031 | USED |
| `dazzle rbac` | HYGIENE | CLI | framework-ux | 1029 | USED |
| `dazzle coverage` | HYGIENE | CLI | example-apps | 1031 | USED |
| `dazzle fragment-audit` | HYGIENE | CLI | framework-ux | 1029 | USED |
| `dazzle process` | HYGIENE | CLI + MCP | example-apps | 1037 | USED |
| `dazzle compliance` | HYGIENE | CLI + MCP | example-apps | 1026 | USED |
| MCP `policy` | HYGIENE | MCP | framework-ux | 1030 | USED |
| MCP `test_intelligence` | HYGIENE | MCP | test-suite | 1030 | USED |
| MCP `semantics` | HYGIENE | MCP | example-apps | 1030 | USED |
| `dazzle representation` + MCP `representation` | HYGIENE | CLI + MCP | framework-ux + example-apps | 1026 | USED |
| `dazzle prove` | HYGIENE | CLI | framework-ux + example-apps | 1026 | USED |
| `dazzle scaffold` | HYGIENE | CLI | example-apps | 1026 | USED |
| **CodeQL / code-scanning** | DRIVER | GitHub API + strategy | **driver (Step 0c2)** | 1054 | USED |
| **GitHub inbox** | DRIVER | script + strategies | **driver (Step 0c3)** | 1054 | USED |
| `dazzle pitch` | EXEMPT | CLI + MCP | — | — | EXEMPT (human-invoked) |
| `dazzle spec` / `spec-narrate` skill | EXEMPT | CLI + skill | — | — | EXEMPT (stakeholder docs) |
| `dsl-authoring` skill | EXEMPT | skill | — | — | EXEMPT (in-session) |
| `phase-contract` skill | EXEMPT | skill | — | — | EXEMPT (execution harness) |
| `stems` skill | EXEMPT | skill | — | — | EXEMPT (epistemic entry) |

---

## Cycle notes (newest first)

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
