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

**Grok workflow:** `/workflow improve-capability-sweep` (see `.grok/workflows/README.md`)
runs inventory + parallel dig recommenders; driver logs the three counts and may
apply map patches with `{"apply":true}`.

**Lore:** Durable loop lessons live in [`improve/oral-history.md`](../../../improve/oral-history.md) — not here.
**Stamp rule:** update **Last-exercised** + Status only (one table edit). Do **not** append multi-paragraph cycle digests.
Capability-sweep may replace the short “Last sweep” one-liner below (≤3 lines).

---

## Registry

| Capability | Class | Surface | Owning lane | Last-exercised | Status |
|---|---|---|---|---|---|
| `dazzle domain` / MCP `domain` (extract/gaps/research/promote) | COGNITION | CLI+MCP | **example-apps** + agent DX | 2051 | STALE |
| **domain lifecycle/process priors** (`domain_brief.lifecycles` + `domain_cognition_bar`) | COGNITION | script + extract | **example-apps** | 2051 | STALE |
| MCP `product_quality` (persona homes + stills + maturity + metric_list + **presentation residual**) | COGNITION | MCP | **example-apps** + framework-ux | 2184 | STALE |
| `dazzle demo quality` (#1626 felt residual bar) | COGNITION | CLI | **example-apps** + framework-ux | 2257 | USED |
| MCP `presentation` (cognition / opportunities / residual) | COGNITION | MCP | **framework-ux** + example-apps | 2184 | STALE |
| **hyperpart_presentation** process (`present()` matrix + strategy) | COGNITION | strategy + CLI + MCP | **framework-ux** (+ example-apps recapture) | 2184 | STALE |
| counter-prior `ref_as_repr` (dict/UUID chrome) | COGNITION | KG + docs | framework-ux + example-apps | 2253 | USED |
| **interesting_product** (post-5.8 Goal B depth menu + still proof) | COGNITION | strategy + doctrine | **example-apps** | 2108 | STALE |
| **goal_b_coat / distill** (Goal C subtract filter-wall / cartesian) | COGNITION | script + strategy | **example-apps** | 2109 | STALE |
| doctrine `interesting-saas-context` (Goal A harness vs Goal B) | COGNITION | docs | example-apps + driver | 2096 | STALE |
| `dazzle demo reset-and-load` (#1627 closed-loop seed) | COGNITION | CLI | example-apps + agent DX | 2262 | USED |
| MCP `status` `demo_world`/`runtime` (#1629 world-model read) | COGNITION | MCP | example-apps + agent DX | 1918 | STALE |
| MCP `db` project-local DATABASE_URL (#1629 G2) | COGNITION | MCP | example-apps + agent DX | 1331 | STALE |
| `dazzle qa trial` | COGNITION | CLI | trials | 1951 | STALE |
| `qa-trial` skill | COGNITION | skill | trials | 1633 | STALE |
| **example product maturity** / WI D/N/L/J/G | COGNITION | script + strategy | **example-apps** | 1997 | STALE |
| **demo fleet bar** (#1626) | COGNITION | script + strategy | **example-apps** | 1997 | STALE |
| **example journey maturity** | COGNITION | script + strategy | **example-apps** | 1997 | STALE |
| **unified example probes** | COGNITION | script | **example-apps** (driver) | 2288 | USED |
| **agent_acceptance_panel** (multi-seat trial) | COGNITION | strategy + qa trial | **example-apps** | 1951 | STALE |
| **agent_qa_smoke** (L2.5 smoke-crawl + hyperpart opps) | COGNITION | strategy + `qa smoke-crawl` / `smoke-dig` + `qa_smoke_bar.py` | **example-apps** + trials | 2269 | USED |
| `dazzle qa smoke-crawl` | COGNITION | CLI | **example-apps** + trials | 2269 | USED |
| `dazzle qa smoke-dig` (fleet random-seed dig cycle) | COGNITION | CLI | **example-apps** + trials | 2269 | USED |
| `dazzle qa hyperpart-opportunities` | COGNITION | CLI | **example-apps** + trials + framework-ux | 2184 | STALE |
| **work-surface utility ontology** | COGNITION | `work_surface_utility.toml` + `scripts/work_surface_utility.py` + `pick-a-work-surface.md` | **hm-convergence** + framework-ux | 1488 | STALE |
| **story_walk bar** / dig contracts (#1638) | COGNITION | script + strategy | **example-apps** | 1997 | STALE |
| `dazzle test walk` (validate/run/dry-run) | COGNITION | CLI | **example-apps** | 2264 | USED |
| **process_dig / dig contracts sensors** (`improve_dig_receipt`, probe process_dig) | COGNITION | script + probes | **example-apps** + driver | 2098 | STALE |
| `dazzle qa taste-panel` (metered; **use subscription substitute**) | COGNITION | CLI + `hm_visual_smoke` | **hm-convergence** + framework-ux | 2045 | STALE |
| `dazzle qa component-vision` (metered; **use host-Read / gallery**) | COGNITION | CLI + substitute | **hm-convergence** + framework-ux | 1233 | STALE |
| `dazzle qa property-vision` (metered; **use host-Read / gallery**) | COGNITION | CLI + substitute | **hm-convergence** | 1233 | STALE |
| **HM hyperpart coherence** | COGNITION | script + strategy | **hm-convergence** | 2045 | STALE |
| gallery_probes (`hm_gallery_probes.py`) | HYGIENE | script | **hm-convergence** | 2162 | STALE |
| `dazzle validate` / `lint` | HYGIENE | CLI | example-apps (Tier 1) | 2084 | STALE |
| `dazzle ux verify` (contracts/interactions) | HYGIENE | CLI | framework-ux, ux-converge, example-apps | 1534 | STALE |
| `dazzle qa capture` (Tier-2 visual scrape) | HYGIENE | CLI | example-apps (visual_tier2) | 2084 | STALE |
| `dazzle qa login` | HYGIENE | CLI | (support for capture/verify) | 1231 | STALE |
| `hm gallery interaction probes` | HYGIENE | script + strategy | **hm-convergence** | 2162 | STALE |
| `dazzle deploy plan` | HYGIENE | CLI | example-apps (Tier 1) | 1230 | STALE |
| MCP `conformance` | HYGIENE | MCP | example-apps (Tier 1) | 1259 | STALE |
| MCP `dsl` (fidelity/validate/lint/brief/…) | HYGIENE | MCP | example-apps (Tier 1) | 2117 | STALE |
| fitness **engine** | HYGIENE | Python API | framework-ux | 2117 | STALE |
| `dazzle sentinel mutate` | HYGIENE | CLI | test-suite | 1229 | STALE |
| `dazzle rhythm` | HYGIENE | CLI | example-apps | 1230 | STALE |
| `dazzle story` | HYGIENE | CLI + MCP | example-apps | 1460 | STALE |
| `dazzle test-design` | HYGIENE | CLI | example-apps | 1230 | STALE |
| `dazzle pulse` | HYGIENE | CLI | framework-ux | 1303 | STALE |
| `dazzle sentinel scan` | HYGIENE | CLI + MCP | framework-ux | 2116 | STALE |
| `/semgrep` / `scripts/semgrep_diff.py` (p/python + owasp + audit) | HYGIENE | skill + script | **framework-ux** + driver | 2116 | STALE |
| Semgrep MCP (`semgrep mcp`) | HYGIENE | MCP | framework-ux + Grok config | 2116 | STALE |
| `dazzle fitness` CLI | HYGIENE | CLI | framework-ux | 1645 | STALE |
| `dazzle discovery` | HYGIENE | CLI + MCP | example-apps | 1216 | STALE |
| `dazzle composition` | HYGIENE | CLI + MCP | framework-ux | 2273 | USED |
| `dual_lock_queue` / `dual_lock_expand` | HYGIENE | script + strategy | **hm-convergence** | 2172 | STALE |
| `shadcn_parity` | HYGIENE | script + strategy | **hm-convergence** | 1304 | STALE |
| **HM zero-floor** | HYGIENE | script + gate | **hm-convergence** | 1341 | STALE |
| `dazzle sweep` / `nightly` | HYGIENE | CLI | test-suite | 1229 | STALE |
| `/fuzz` | HYGIENE | standalone loop | own entrypoint | 1232 | STALE |
| `/smells` | HYGIENE | standalone loop | own entrypoint | 1232 | STALE |
| `/xproject` | HYGIENE | standalone loop | own entrypoint | 1232 | STALE |
| `dazzle rbac` | HYGIENE | CLI | framework-ux | 1417 | STALE |
| `dazzle coverage` | HYGIENE | CLI | example-apps | 1230 | STALE |
| `dazzle fragment-audit` | HYGIENE | CLI | framework-ux | 1676 | STALE |
| `dazzle process` | HYGIENE | CLI + MCP | example-apps | 1302 | STALE |
| `dazzle compliance` | HYGIENE | CLI + MCP | example-apps | 1216 | STALE |
| MCP `policy` | HYGIENE | MCP | framework-ux | 1235 | STALE |
| MCP `test_intelligence` | HYGIENE | MCP | test-suite | 1235 | STALE |
| MCP `semantics` | HYGIENE | MCP | example-apps | 1235 | STALE |
| `dazzle representation` + MCP `representation` | HYGIENE | CLI + MCP | framework-ux + example-apps | 1234 | STALE |
| `dazzle prove` | HYGIENE | CLI | framework-ux + example-apps | 1615 | STALE |
| `dazzle scaffold` | HYGIENE | CLI | example-apps | 1230 | STALE |
| `dazzle.risk` model-driven failure-mode scoring (MDF-01..14) | HYGIENE | Python package | **framework-ux** | 1230 | STALE |
| **CodeQL / code-scanning** | DRIVER | GitHub API + strategy | **driver (Step 0c2)** | 2287 | USED |
| **GitHub inbox** | DRIVER | GitHub API + strategies | **driver (Step 0c3)** | 2287 | USED |
| `dazzle pitch` | EXEMPT | CLI + MCP | — | — | EXEMPT |
| `dazzle spec` / `spec-narrate` skill | EXEMPT | CLI + skill | — | — | EXEMPT |
| `dsl-authoring` skill | EXEMPT | skill | — | — | EXEMPT |
| `phase-contract` skill | EXEMPT | skill | — | — | EXEMPT |
| `stems` skill | EXEMPT | skill | — | — | EXEMPT |

---

---

## Last sweep (≤5 one-liners — overwrite, do not accumulate)

> **Cycle 2252 (2026-08-18).** capability-sweep: UNOWNED=0 COGNITION_STALE_eff=31 HYGIENE_STALE_eff=40; no USED→STALE flips (probes/CodeQL/inbox @2252; presentation@2184 / gallery@2162 / dual_lock@2172 still STALE-eff). Goal B recommend=- (interesting_product_saturated); residual=1 smoke_stale_days only; densify_allowed=0; dual_lock=0 coherence=0. Next → framework-ux **different invent class** in a live app (not leftover-token stay-put; oral #121). Do not stamp presentation (residual=0) or smoke.
