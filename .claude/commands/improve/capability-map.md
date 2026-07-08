# Improve-loop capability map

**Purpose.** A registry of every capability the project has built (`dazzle` CLI +
MCP tools + `.claude` skills/commands + standalone loops), each with an owning lane
and a staleness status, so the `/improve` loop **polices its own coverage** — nothing
we build rots unexercised behind the framework's velocity. This is the governance
half of the "pull all skills under the aegis of the improve loop" directive
(2026-07-08); the driver's `capability-coverage` rule (see `improve.md` Step 1) reads
this file to bias directed exploration toward `UNOWNED`/`STALE` rows.

**Status vocabulary**
- `USED` — a lane/strategy invokes it every relevant cycle.
- `OWNED-IDLE` — has an owning lane but runs only on demand / low frequency (exercised when the driver's capability-coverage rule picks it).
- `STALE` — owned but not exercised for ≥ **20** cycles → the driver biases toward it.
- `UNOWNED` — built, but no lane invokes it. The strongest gap; the capability-sweep cadence flags these.
- `EXEMPT` — deliberately human-invoked (authoring aids, stakeholder docs); not a loop gap.

**last-exercised** is the cycle number the owning lane last ran the capability
(stamped by the driver's Step-3 maintenance). `—` = never yet.

**Maintenance.** The driver stamps `last-exercised` each cycle (Step 3) and a periodic
**capability-sweep** cadence (every 20 cycles, like self-audit) re-derives the
inventory from `dazzle --help` + the MCP table + `.claude/` tree and flags anything
new as `UNOWNED`. To re-derive by hand: `dazzle --help`, the MCP table in
`.claude/CLAUDE.md`, `ls .claude/skills .claude/commands`.

---

## Registry

| Capability | Surface | Owning lane | Last-exercised | Status |
|---|---|---|---|---|
| `dazzle validate` / `lint` | CLI | example-apps (Tier 1) | 188 | USED |
| `dazzle ux verify` (contracts/interactions) | CLI | framework-ux, ux-converge, example-apps | 185 | USED |
| `dazzle qa capture` (Tier-2 visual scrape) | CLI | example-apps (visual_tier2) | — | OWNED-IDLE |
| `dazzle qa trial` | CLI | trials | 187 | USED |
| `dazzle qa login` | CLI | (support for qa capture/verify) | — | OWNED-IDLE |
| `dazzle qa taste-panel` | CLI | **hm-convergence** + framework-ux | — | OWNED-IDLE |
| MCP `conformance` (summary/cases/gaps) | MCP | example-apps (Tier 1) | 188 | USED |
| MCP `dsl` (fidelity/validate/lint/brief/…) | MCP | example-apps (Tier 1) | 188 | USED |
| fitness **engine** (`run_fitness_strategy`) | Python API | framework-ux (Phase B) | 186 | USED |
| `dazzle sentinel mutate` | CLI | test-suite (mutation floor) | — | OWNED-IDLE |
| `dazzle rhythm` (fidelity/gaps/evaluate/lifecycle/propose) | CLI | example-apps (Tier 1) | — | OWNED-IDLE |
| `dazzle story` (scope-fidelity/list/generate-tests/propose) | CLI + MCP (composition/coverage) | example-apps (Tier 1) | — | OWNED-IDLE |
| `dazzle test-design` (coverage-actions/runtime-gaps/…) | CLI | example-apps | — | OWNED-IDLE |
| `dazzle pulse` (run/radar/persona/timeline/decisions/wfs) | CLI | framework-ux | — | OWNED-IDLE |
| `dazzle sentinel scan` (findings/fuzz/history) | CLI + MCP | framework-ux | — | OWNED-IDLE |
| `dazzle fitness` CLI (investigate/vitality/clones/code/triage/queue) | CLI | framework-ux | — | OWNED-IDLE |
| `dazzle discovery` (coherence/run/report/verify-all-stories) | CLI + MCP | example-apps | — | OWNED-IDLE |
| `dazzle composition` (audit/report) | CLI + MCP | framework-ux | — | OWNED-IDLE |
| **Tailwind-reservoir metric** (emitter utils + Dazzle-native CSS not in HM) | script | **hm-convergence** | 191 | USED |
| `dazzle pitch` (review/update/enrich/…) | CLI + MCP | — | — | EXEMPT (human-invoked) |
| `dazzle spec` / `spec-narrate` skill | CLI + skill | — | — | EXEMPT (stakeholder docs) |
| `dazzle sweep` / `nightly` | CLI | test-suite (nightly = mutation backstop) | — | OWNED-IDLE |
| `dsl-authoring` skill | skill | — | — | EXEMPT (in-session authoring aid) |
| `phase-contract` skill | skill | — | — | EXEMPT (execution harness) |
| `qa-trial` skill | skill | trials (downstream authoring) | 187 | OWNED-IDLE |
| `/fuzz` (boot-stderr integration sweep) | standalone loop | own entrypoint (complementary) | — | OWNED-IDLE (standalone) |
| `/smells` (code-smell scan; consumes `fitness code`) | standalone loop | own entrypoint (complementary) | — | OWNED-IDLE (standalone) |
| `/xproject` (cross-project scan; pulse/sentinel/discovery on siblings) | standalone loop | own entrypoint (complementary) | — | OWNED-IDLE (standalone) |
| `dazzle rbac` (matrix/prove/verify/routes/report/byte-routes/access-review) | CLI | framework-ux *(proposed)* | — | UNOWNED |
| `dazzle coverage` (framework-artefact coverage across example apps) | CLI | example-apps *(proposed)* | — | UNOWNED |
| `dazzle fragment-audit` (Fragment-rendering coverage per project) | CLI | framework-ux *(proposed)* | — | UNOWNED |
| `dazzle process` (propose/save/diagram) | CLI + MCP `process` | example-apps *(proposed)* | — | UNOWNED |
| `dazzle compliance` (compile/evidence/gaps/privacy/validate-citations) | CLI + MCP `compliance` | example-apps *(proposed)* | — | UNOWNED |
| MCP `policy` (analyze/conflicts/coverage/simulate/access_matrix/verify_status) | MCP | framework-ux *(proposed)* | — | UNOWNED |
| MCP `test_intelligence` (summary/failures/regression/coverage/context/journey) | MCP | test-suite *(proposed)* | — | UNOWNED |
| MCP `semantics` (extract/validate_events/tenancy/compliance/analytics/extract_guards) | MCP | example-apps *(proposed)* | — | UNOWNED |

> **Capability-sweep cycle 190 (2026-07-08).** First sweep to run. Re-derived the
> inventory from `dazzle --help` + the MCP table + the `.claude/` tree and found the
> 8 UNOWNED rows above — real, substantial quality/verification capabilities that no
> lane invokes. Flagship: `dazzle rbac` (the provable-RBAC substrate, shipped
> v0.90–0.91) had rotted unexercised by the loop. Owning lanes are *proposed*; the
> driver's capability-coverage rule (Step 1 rule 6) will route directed-explore
> cycles to exercise each, flipping UNOWNED → USED/OWNED-IDLE as they run.
> STALE recompute (cycle 190, threshold last-exercised ≤170): no existing numeric
> row (188/187/186/185) flips.

---

## Lanes

| Lane | Owns | Playbook |
|---|---|---|
| `framework-ux` | ux contracts/fitness walks, taste-panel, sentinel scan, fitness investigate, composition, pulse | `lanes/framework-ux.md` |
| `example-apps` | validate/lint/conformance/fidelity, rhythm, story, test-design, discovery | `lanes/example-apps.md` |
| `trials` | qa trial scenarios | `lanes/trials.md` |
| `ux-converge` | contract-failure convergence | `lanes/ux-converge.md` |
| `test-suite` | redundancy-cluster collapse, sentinel mutate/nightly | `lanes/test-suite.md` |
| `hm-convergence` | Tailwind-reservoir drain into HaTchi-MaXchi, taste-panel, legacy-Tailwind retirement | `lanes/hm-convergence.md` |

> `pitch`, `spec-narrate`, `dsl-authoring`, `phase-contract` are `EXEMPT` — deliberately
> human-invoked, not loop gaps. The three standalone loops (`/fuzz`, `/smells`, `/xproject`)
> have their own entrypoints and are not driver-dispatched, but are listed here so the
> capability-sweep counts them as covered.
