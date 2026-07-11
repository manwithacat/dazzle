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
| `dazzle validate` / `lint` | CLI | example-apps (Tier 1) | 302 | USED |
| `dazzle ux verify` (contracts/interactions) | CLI | framework-ux, ux-converge, example-apps | 294 | USED |
| `dazzle qa capture` (Tier-2 visual scrape) | CLI | example-apps (visual_tier2) | — | OWNED-IDLE |
| `dazzle qa trial` | CLI | trials | 301 | USED (API-billing-gated judgment) |
| `dazzle qa login` | CLI | (support for qa capture/verify) | — | OWNED-IDLE |
| `dazzle qa taste-panel` | CLI | **hm-convergence** + framework-ux | — | OWNED-IDLE |
| `dazzle qa component-vision` (advisory judged read, one HM showcase region) | CLI | **hm-convergence** + framework-ux | — | OWNED-IDLE |
| `dazzle qa property-vision` (advisory property page vs family exemplars) | CLI | **hm-convergence** | — | OWNED-IDLE |
| `dazzle deploy plan` (target-agnostic AppSpec→infra inference) | CLI | example-apps (Tier 1) | 295 | USED |
| MCP `conformance` (summary/cases/gaps) | MCP | example-apps (Tier 1) | 290 | USED |
| MCP `dsl` (fidelity/validate/lint/brief/…) | MCP | example-apps (Tier 1) | 291 | USED |
| fitness **engine** (`run_fitness_strategy`) | Python API | framework-ux (Phase B) | 292 | USED (API-billing-gated judgment) |
| `dazzle sentinel mutate` | CLI | test-suite (mutation floor) | — | OWNED-IDLE |
| `dazzle rhythm` (fidelity/gaps/evaluate/lifecycle/propose) | CLI | example-apps (Tier 1) | 298 | USED |
| `dazzle story` (scope-fidelity/list/generate-tests/propose) | CLI + MCP (composition/coverage) | example-apps (Tier 1) | 289 | USED |
| `dazzle test-design` (coverage-actions/runtime-gaps/…) | CLI | example-apps | — | OWNED-IDLE |
| `dazzle pulse` (run/radar/persona/timeline/decisions/wfs) | CLI | framework-ux | — | OWNED-IDLE |
| `dazzle sentinel scan` (findings/fuzz/history) | CLI + MCP | framework-ux | — | OWNED-IDLE |
| `dazzle fitness` CLI (investigate/vitality/clones/code/triage/queue) | CLI | framework-ux | — | OWNED-IDLE |
| `dazzle discovery` (coherence/run/report/verify-all-stories) | CLI + MCP | example-apps | — | OWNED-IDLE |
| `dazzle composition` (audit/report) | CLI + MCP | framework-ux | — | OWNED-IDLE |
| **Tailwind-reservoir metric** (emitter utils + Dazzle-native CSS not in HM) | script | **hm-convergence** | 293 | USED |
| `dazzle pitch` (review/update/enrich/…) | CLI + MCP | — | — | EXEMPT (human-invoked) |
| `dazzle spec` / `spec-narrate` skill | CLI + skill | — | — | EXEMPT (stakeholder docs) |
| `dazzle sweep` / `nightly` | CLI | test-suite (nightly = mutation backstop) | — | OWNED-IDLE |
| `dsl-authoring` skill | skill | — | — | EXEMPT (in-session authoring aid) |
| `phase-contract` skill | skill | — | — | EXEMPT (execution harness) |
| `qa-trial` skill | skill | trials (downstream authoring) | 301 | USED |
| `/fuzz` (boot-stderr integration sweep) | standalone loop | own entrypoint (complementary) | — | OWNED-IDLE (standalone) |
| `/smells` (code-smell scan; consumes `fitness code`) | standalone loop | own entrypoint (complementary) | — | OWNED-IDLE (standalone) |
| `/xproject` (cross-project scan; pulse/sentinel/discovery on siblings) | standalone loop | own entrypoint (complementary) | — | OWNED-IDLE (standalone) |
| `dazzle rbac` (matrix/prove/verify/routes/report/byte-routes/access-review) | CLI | framework-ux | 297 | USED |
| `dazzle coverage` (framework-artefact coverage across example apps) | CLI | example-apps | 300 | USED |
| `dazzle fragment-audit` (Fragment-rendering coverage per project) | CLI | framework-ux | 304 | USED |
| `dazzle process` (propose/save/diagram) | CLI + MCP `process` | example-apps | 303 | USED |
| `dazzle compliance` (compile/evidence/gaps/privacy/validate-citations) | CLI + MCP `compliance` | example-apps | 285 | USED |
| MCP `policy` (analyze/conflicts/coverage/simulate/access_matrix/verify_status) | MCP | framework-ux | 286 | USED |
| MCP `test_intelligence` (summary/failures/regression/coverage/context/journey) | MCP | test-suite | 287 | USED (KG-gated happy path) |
| MCP `semantics` (extract/validate_events/tenancy/compliance/analytics/extract_guards) | MCP | example-apps | 288 | USED |

> **Capability-sweep cycle 190 (2026-07-08).** First sweep to run. Re-derived the
> inventory from `dazzle --help` + the MCP table + the `.claude/` tree and found the
> 8 UNOWNED rows above — real, substantial quality/verification capabilities that no
> lane invokes. Flagship: `dazzle rbac` (the provable-RBAC substrate, shipped
> v0.90–0.91) had rotted unexercised by the loop. Owning lanes are *proposed*; the
> driver's capability-coverage rule (Step 1 rule 6) will route directed-explore
> cycles to exercise each, flipping UNOWNED → USED/OWNED-IDLE as they run.
> STALE recompute (cycle 190, threshold last-exercised ≤170): no existing numeric
> row (188/187/186/185) flips.

> **Capability-sweep cycle 216 (2026-07-09).** Second sweep. Re-derived inventory
> (`dazzle --help`, the 32-tool MCP table, `.claude/skills` + `.claude/commands` tree)
> — **no newly-built capability** since cycle 190: cycles 191–215 were the HM-convergence
> directive (CSS/JS migration + the dz-combobox/dz-tags Hyperparts), which added zero new
> CLI/MCP/skill surface. But the sweep's real finding is the **cost of that 25-cycle
> hm-convergence monomania**: with the loop parked in one lane for ~25 cycles, every other
> lane went unexercised, so 7 previously-`USED`/`OWNED-IDLE` rows now cross the STALE
> threshold (last-exercised ≤196 for cycle 216): `dazzle validate`/`lint` (188), `ux verify`
> (185), `qa trial` (187), MCP `conformance` (188), MCP `dsl` (188), fitness engine (186),
> `qa-trial` skill (187) → all flipped to **STALE**. The Tailwind-reservoir metric (214)
> is the only recently-exercised capability. The 8 cycle-190 `UNOWNED` rows (`rbac`,
> `coverage`, `fragment-audit`, `process`, `compliance`, MCP `policy`/`test_intelligence`/
> `semantics`) **remain UNOWNED** — their *proposed* owning lanes never got a directed-explore
> cycle because the loop never left hm-convergence. **Consequence for the driver:** now that
> hm-convergence is drained (0 actionable, directive complete), rule-6 directed exploration
> has a rich STALE+UNOWNED backlog and should rotate the loop back through the starved lanes,
> prioritising the UNOWNED gaps (strongest) then the freshly-STALE core capabilities. This is
> the capability-coverage governance mechanism catching a monomania exactly as designed.
> Operator/dev commands considered and classified out-of-scope (not quality-coverage gaps):
> `/issues`, `/cimonitor`, `/docs-update`, `/check`, `/bump`, `/ship` — human/operator-invoked
> workflow tooling, EXEMPT-class like `/fuzz`/`/smells`/`/xproject`.

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

> **Capability-sweep cycle 236 (2026-07-10).** Re-derived inventory post the #1566/#1567/
> #1568 arc (v0.99.3–v0.101.11). THREE new capabilities flagged UNOWNED and wired in the
> same pass: `qa component-vision` → hm-convergence+framework-ux, `qa property-vision` →
> hm-convergence, `deploy plan` → example-apps (Tier-1 manifest check). NOT added (self-
> exercising via `pytest -m gate` in CI every commit): design-context claim-integrity +
> doc-drift gates (#1566), component-hygiene floor (#1567 s1), family-contrast gate +
> themespec contrast-in-validate (#1567 s2). Retired capabilities (deploy generate/
> preflight/dockerfile/compose, docuseal pack — removed v0.100.0/v0.101.0) had no map rows,
> nothing to prune. STALE recompute (threshold ≤216): none — oldest numeric is rbac@217,
> which crosses next cycle if unexercised.

> **Capability-sweep cycle 256 (2026-07-11).** Sweep due (20 cycles since 236). Re-derived
> inventory: `dazzle --help` (+ `qa` / `deploy` / `fitness` subtrees), MCP tool schemas
> (`inspect api mcp-tools` → **35 tools**), `.claude/skills` + `.claude/commands` tree.
> **No newly-built loop capability** since 236: the v0.101.36–0.101.42 arc (HM dual locks,
> form→ingest #1577, root-only DOM #1578, prose Contract drift #1579, PersonaVariant
> action_primary/defaults, dispatch_ctx split) added product/substrate surface and CI
> gates, not CLI/MCP/skill entrypoints for the improve loop. NOT added (self-exercising
> via `pytest -m gate` / unit dual-lock suite every commit): `hm_contract_registry`
> schema parity + DOM_ONLY fixtures + `test_contract_prose_drift`. Operator-only still
> EXEMPT: `deploy heroku`, auth/db/backup family, `/ship`/`/check`/`/bump`/etc. MCP
> count 35 (was noted as 32 schema / 34 CLAUDE table in older notes) — no new
> quality-coverage tools vs the existing map rows; long-standing tools without rows
> (e.g. `sitespec`, `graph`, `knowledge`) remain out-of-scope the same way prior sweeps
> treated non-quality operator/MCP surface. STALE recompute (threshold last-exercised
> ≤236): **none** flip. Nearest: `dazzle rbac`@237 (lag 19 → STALE next cycle if still
> unexercised), then `coverage`@238 (lag 18), `qa-trial` skill@239 (lag 17). OWNED-IDLE
> never-exercised rows (`qa capture`/`login`/`taste-panel`/`component-vision`/
> `property-vision`/`deploy plan`/`sentinel mutate`/`rhythm`/`story`/`test-design`/
> `pulse`/`sentinel scan`/`fitness` CLI/`discovery`/`composition`/`sweep`/`nightly` +
> standalone `/fuzz`/`/smells`/`/xproject`) stay OWNED-IDLE awaiting directed exercise.

> **Capability-sweep cycle 276 (2026-07-11).** Sweep due (20 cycles since 256). Re-derived
> inventory: `dazzle --help` (+ `qa`/`deploy` subtrees), MCP tool schemas (**35 tools**,
> unchanged), `.claude/skills` + `.claude/commands` + `.agents/skills`. **No newly-built
> loop capability** since 256: cycles 257–275 were un-STALE directed-explore (rbac,
> coverage, process, fragment-audit, compliance, policy, test_intelligence, semantics,
> conformance, dsl, fitness engine, Tailwind reservoir, ux verify) plus product fixes
> TR-56/57/58/50 and first exercise of `deploy plan` (OWNED-IDLE→USED@275). Product
> work (workspace CTA, already_signed token state, demo seed dates/job titles) extended
> existing surfaces — no new CLI/MCP/skill entrypoints. NOT added (still CI self-
> exercising / operator EXEMPT): dual-lock gates, `deploy heroku`, auth/db family,
> `/ship`/`/check`/`/bump`. STALE recompute (threshold last-exercised ≤256): **none**
> flip — the post-256 directed-explore rotation kept every previously USED row inside
> the 20-cycle window. Nearest risk: `dazzle rbac`@257 (lag 19 → STALE next cycle if
> idle). Remaining OWNED-IDLE never-exercised (18 after deploy plan graduated):
> `qa capture`/`login`/`taste-panel`/`component-vision`/`property-vision`,
> `sentinel mutate`/`scan`, `rhythm`/`story`/`test-design`/`pulse`/`fitness` CLI,
> `discovery`/`composition`/`sweep`/`nightly`, standalone `/fuzz`/`/smells`/`/xproject`.
> Governance note: cycles 257–274 were almost pure capability-coverage bookkeeping;
> product findings (TR-*) only landed when rule 6 had no STALE queue — healthy, but
> the next explore budget should prefer OWNED-IDLE first-exercise over re-stamping
> recently USED rows once the queue is clear again.

> **Capability-sweep cycle 296 (2026-07-11).** Sweep due (20 cycles since 276). Re-derived
> inventory: `dazzle --help` (+ `qa`/`deploy`), MCP **35 tools** (unchanged), `.claude`
> skills/commands. **No newly-built loop capability** since 276. Graduations since 276:
> `rhythm` OWNED-IDLE→USED@278, `story` OWNED-IDLE→USED@289; remaining never-exercised
> OWNED-IDLE ~**16** (`qa capture`/`login`/`taste-panel`/`component-vision`/
> `property-vision`, `sentinel mutate`/`scan`, `test-design`/`pulse`/`fitness` CLI,
> `discovery`/`composition`/`sweep`/`nightly`, `/fuzz`/`/smells`/`/xproject`). Product
> fixes: **none** in the 277–295 window (pure un-STALE rotation + self-audit 284).
> STALE recompute (threshold ≤276): **none** flip — lag-max among USED is rbac@277
> (lag 19). Explore budget mid-run ~53/100. **Hard governance finding:** the loop has
> now spent ~40 cycles almost exclusively re-stamping STALE USED capabilities; with
> product TR backlog empty and no new UNOWNED, rule 6 is correctly busy but delivers
> little product value. Prefer first-exercise of remaining OWNED-IDLE when no STALE
> (and after stamping lag-19s, bias next cycles to IDLE not re-rotation of the same
> set). Operator EXEMPT still: `deploy heroku`, auth/db, `/ship`/`/check`/`/bump`.
