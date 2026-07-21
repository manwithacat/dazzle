# Improve dig contracts & process sensors

**Status:** Implemented (PR1–PR5, 2026-07-21)
**Date:** 2026-07-21
**Tracking:** #1626 (demo bake-off), story-walk / trial-verdict residual (shipped), agent QA ladder (#1625)
**Related shipped:** `scripts/story_walk_bar.py`, `scripts/trial_verdict_bar.py`, `scripts/improve_example_probes.py`, `improve/strategies/story_walk.md`, `agent_acceptance_panel.md`

---

## 1. Summary

`/improve` already has **efficient maps** (stories, stems, SPEC, seeds, stills, claims, trials) and **actuators** (CLI + MCP). After structural residual hit zero, the loop idled or stamped STALE capabilities. We re-armed **outcome residual** for landing walks and trial verdicts. That is necessary but not sufficient: agents can still clear residual by minimal YAML without *using* maps or *firing* actuators against a live app.

This design specifies **dig contracts**, **divergence sensors**, and **epistemic residual** so improve trajectory is shaped by *how* digs use context and tools—without inventing premature outcome bars for “full still quality,” “SPEC truth,” or “stem compliance” (those beg the question until operationalized elsewhere, e.g. human bake-off).

**One-line goal:** Residual chooses *where*; dig contracts force *how* maps and actuators are used; outcome residual only scores what we already know how to machine-check.

---

## 2. Problem

### 2.1 Efficient context is optional mid-dig

| Artifact class | Role today | Failure mode |
|----------------|------------|--------------|
| Stories / stems / SPEC | Map for authors | Dig never opens them |
| Scene walks / claims | Outcome / docs | Stub walk with generic asserts, residual edge-cases |
| Seeds / stills | Partial residual | Floors only on trio heroes; empty non-trio stills don’t heat |
| trial.toml / reports | trial_verdict residual | Apps without trial.toml never get acceptance heat |
| CLI / MCP | Actuators | PASS claimed without dry-run, seed, or trial |

Agents are not short on material. Selection optimizes **outcome residual**. Maps and actuators are playbook advice unless evidence is required for PASS.

### 2.2 Outcome sensors that beg the question

Do **not** implement these as residual bars in this workstream:

| Tempting bar | Why not yet |
|--------------|-------------|
| Full still commercial quality | *Is* the #1626 bake-off programme |
| SPEC “truth” | Multi-altitude docs; no single residual without a separate doctrine |
| Stem “compliance” | Reconstructive judgment, not a checklist |
| Claims evergreen / filmed | Lifecycle end-state; premature residual invents maturity theater |

Those remain **maps** and/or **human/#1626** until process + divergence sensors still leave shallow UX visible in stills/trials—then re-score, don’t invent a fake machine taste metric.

### 2.3 What we already shipped (baseline)

Selection order (example-apps):

```text
product_maturity → demo_fleet → journey → felt (product_quality)
  → story_walk → trial_verdict / agent_acceptance_panel
```

| Probe | Outcome residual |
|-------|------------------|
| `story_walk_bar` | Landing stories without walk coverage / no walks / load fail |
| `trial_verdict_bar` | Missing/failed/conditional last qa-trial report (if trial.toml exists) |

This design **extends** that baseline with process, divergence, and epistemic layers.

---

## 3. Goals and non-goals

### 3.1 Goals

1. **Dig contracts** — strategy PASS requires evidence that maps were cited and actuators fired.
2. **Divergence sensors** — residual when two first-class artifacts disagree (pair relations, not beauty).
3. **Epistemic residual** — “unknown / unproven” is a first-class state (not the same as “bad UX”).
4. **Optional recency** — seed/walk/capture/trial timestamps can deepen residual without scoring taste.
5. **Wire into OBSERVE** — `improve_example_probes` (or a sibling line) surfaces process/divergence/epistemic heat so agents don’t need culture alone.
6. **Preserve densify hard-stop** (#1637) — this work never reopens isomorphic `*_ops` densify.

### 3.2 Non-goals

- Replacing human bake-off (#1626) with a machine composite score.
- Auto-scoring SPEC or stem “correctness.”
- Requiring live Postgres for every cycle (contracts must allow dry-run-only PASS with explicit epistemic flag).
- Expanding explore budget or changing CI/CodeQL preemption order.
- New example apps or new DSL constructs.

---

## 4. Conceptual model

```text
┌─────────────────────────────────────────────────────────────┐
│ MAPS (efficient context)                                     │
│ stories · stems · SPEC/SPECIFICATION · claims · seeds        │
│ stills · trial.toml · #1626 notes                            │
└───────────────────────────┬─────────────────────────────────┘
                            │ dig contract: must cite / open
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ DIG (one app, one strategy)                                  │
│ residual pick → contract steps → evidence artifacts          │
└───────────────────────────┬─────────────────────────────────┘
                            │ dig contract: must fire
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ ACTUATORS (CLI + MCP)                                        │
│ validate · walk validate/run · demo quality · qa trial       │
│ seed / reset-and-load · qa capture · product_quality MCP     │
└───────────────────────────┬─────────────────────────────────┘
                            │ produce
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ SENSORS                                                      │
│ Outcome  — structure, floors, walk cover, trial recommend    │
│ Process  — contract checklist complete?                      │
│ Divergence — pair consistency                                │
│ Epistemic  — unknown / live_unproven / never_captured        │
└─────────────────────────────────────────────────────────────┘
```

**Trajectory rule:**

| Layer | Steers |
|-------|--------|
| Outcome residual | *Where* (which app / strategy) |
| Process residual | *Whether PASS is honest* this dig |
| Divergence residual | *Consistency* between maps and walks/trials |
| Epistemic residual | *Messaging / next dig type* (prove vs fix) |
| Maps without residual | Only mid-dig, unless contract forces contact |

---

## 5. Dig contracts

### 5.1 Definition

A **dig contract** is a machine-checkable (or log-parseable) checklist attached to a strategy. Completing residual reduction **without** the checklist is **not PASS**—outcome is `FAIL` or `BLOCKED` with `contract_incomplete`.

Contracts do not define product beauty. They define **minimum contact** with maps and actuators.

### 5.2 Evidence formats (priority order)

Prefer **files and command exit codes** over free-text logs:

| Evidence | Location / form |
|----------|-----------------|
| Walk dry-run | `dazzle test walk run … --dry-run` exit 0 (or equivalent runner) |
| Walk validate | loader/validate exit 0 |
| Dig receipt | `.dazzle/improve-digs/<cycle>-<app>-<strategy>.json` (optional but preferred) |
| Trial report | `examples/<app>/dev_docs/qa-trial-*.json` or `.dazzle/` |
| Map citation | receipt field `maps_cited: [{path, kind, story_ids?}]` |

If receipt files are deferred to a later PR, cycle log **must** include structured lines the self-audit can grep:

```text
contract: maps_cited=examples/contact_manager/stems/story-driven-jobs.md
contract: stories=ST-004,ST-005
contract: walk_validate=0 walk_dry_run=0
contract: live_run=skipped reason=no_db
```

### 5.3 Contract: `story_walk`

**Applies when:** strategy is `story_walk` (force or residual).

| # | Step | Required | Evidence |
|---|------|----------|----------|
| S1 | Identify residual landing story ids for app | MUST | receipt `stories: [ST-…]` or log line |
| S2 | Cite at least one **map**: stem path **or** SPEC/SPECIFICATION section **or** story `then:` quote | MUST | `maps_cited` |
| S3 | Author or edit walk YAML covering ≥1 missing landing (or fix load error) | MUST | path under `fixtures/scene_walks/` |
| S4 | Walk load + validate against AppSpec | MUST | exit 0 |
| S5 | Walk dry-run | MUST | exit 0 |
| S6 | Live walk run (seeded server) | SHOULD | exit 0 **or** explicit `live_run=skipped` + reason |
| S7 | Job claim row for new walk (`documented`) | MAY | `fixtures/job_claims.yaml` |
| S8 | Re-run `story_walk_bar --app` residual improved or app clear | MUST | residual count ↓ or app not residual |

**PASS:** S1–S5 + S8.
**PASS with epistemic flag:** PASS + S6 skipped → set `live_unproven` for those walks (see §7).
**FAIL:** residual “fixed” by deleting stories or lowering bars.
**BLOCKED:** tool/env prevents S4–S5 (record error; do not claim green).

### 5.4 Contract: `agent_acceptance_panel`

| # | Step | Required | Evidence |
|---|------|----------|----------|
| A1 | Confirm `trial.toml` exists or author scenarios from stories/SPEC jobs | MUST | file |
| A2 | Cite maps: ≥1 story id + adoption_criteria (existing or new) | MUST | receipt |
| A3 | Run ≥1 panel seat (journey or deep trial) | MUST | process completed; report JSON written |
| A4 | Verdict present (`recommend` + criteria_scores preferred) | MUST | parseable by `trial_verdict_bar` |
| A5 | Product friction with ownership → backlog row if recommend ≠ yes | SHOULD | improve-backlog |

**PASS:** A1–A4 (even if recommend=no—panel ran; residual may remain via trial_verdict).
**FAIL:** “panel” cycle that only edits trial.toml without a run, unless BLOCKED on LLM/tool with proof.

### 5.5 Contract: `demo_fleet` (light touch)

When residual is stills/seeds only:

| # | Step | Required |
|---|------|----------|
| D1 | Cite #1626 P0 or demo_fleet issue prefix | MUST |
| D2 | Seed and/or capture actuator when claiming still residual clear | MUST if stills residual |
| D3 | `demo_fleet_bar` / product_quality re-score | MUST |

No densify desks under `densify_allowed=0`.

### 5.6 Enforcement

| Phase | Mechanism |
|-------|-----------|
| **v1 (playbook)** | Strategy docs + self-audit greps contract lines; cultural + audit |
| **v2 (receipt)** | Write `.dazzle/improve-digs/*.json`; optional `scripts/improve_dig_receipt.py --check` |
| **v3 (gate)** | `improve_example_probes` or pre-ship check: last dig for residual app without receipt → process residual |

Recommendation: implement **v1 + v2** in the first PR stack; **v3** when receipt schema stabilizes.

---

## 6. Divergence sensors

### 6.1 Principle

Residual = **pair disagreement** between two artifacts we already treat as first-class. No aesthetic model.

### 6.2 Initial pair set (story_walk_bar or sibling)

| Id | Left | Right | Residual issue |
|----|------|-------|----------------|
| `div.entry_ws` | Story `given:` “on the X workspace” or persona `default_workspace` | Walk `entry` / `home_workspace` | `diverge:entry_ws:ST-…:expected=X:got=Y` |
| `div.weak_cues` | Landing story has title/then tokens | Walk `assert_any_text.texts` empty, only generic tokens (`Home`, `App`), or zero texts | `diverge:weak_cues:walk_id` |
| `div.persona` | Story.persona | Walk.persona | `diverge:persona:ST-…` |
| `div.story_orphan_walk` | Walk scene `story: ST-x` | ST-x not in AppSpec stories | `diverge:unknown_story:ST-x` (may already be validate) |

### 6.3 Later pair set (optional phases)

| Id | Left | Right | Notes |
|----|------|-------|-------|
| `div.seed_still` | Seed mtime for entity | Hero still mtime for desk | still older than seed after claim green |
| `div.walk_still` | Walk covers ST landing on workspace W | No still for W **or** still under floor when floors exist | epistemic + density |
| `div.trial_persona` | trial.toml `login_persona` | Persona default_workspace missing / no landing story | orphan scenario |

### 6.4 Severity

| Severity | Tier | Selection |
|----------|------|-----------|
| entry_ws / persona / unknown_story | thin or critical | counts as story_walk residual |
| weak_cues | deepen | residual but lower priority than no_walks |
| seed_still / walk_still | deepen or epistemic | after core coverage green |

### 6.5 Non-divergence

Do not residual:

- SPEC prose vs DSL entity count (SPEC truth).
- Stem text vs implementation (judgment).
- Still vs commercial SaaS (bake-off).

---

## 7. Epistemic residual

### 7.1 Principle

**Unknown ≠ bad.** Epistemic residual means “do not claim proven; prefer prove dig over polish dig.” Messaging and strategy choice change; we do not invent UX scores.

### 7.2 States (per app or per walk)

| State | Meaning | Residual? |
|-------|---------|-----------|
| `no_walk` | Landing without walk file | Yes (outcome, existing) |
| `dry_only` | Walk exists; never live-run (or last live older than seed change) | Yes → `live_unproven` |
| `live_green` | Live walk ran exit 0 after current seeds | No epistemic |
| `no_trial` | trial.toml missing on showcase | Optional residual (policy) |
| `trial_stale` | Report older than N days and seeds changed | Optional deepen |
| `never_captured` | Product desk walk green, no still for desk | deepen / optional |
| `claim_absent` | Walk exists, no job_claims row | MAY deepen (not evergreen) |

### 7.3 Policy defaults (v1)

| Flag | Default residual | Rationale |
|------|------------------|-----------|
| `live_unproven` | **deepen** (counts toward residual_total) | Forces eventually live dig without blocking dry-run progress |
| `no_trial` on showcase | **thin** if we adopt “showcase requires trial.toml” | Closes invoice/project/hr blind spot; **explicit opt-in** in PR plan |
| `claim_absent` | no residual v1 (MAY in contract) | Avoid maturity theater |
| `never_captured` | no residual v1 | Full still quality deferred |

### 7.4 Interaction with densify

Epistemic residual **never** authorizes WI densify. Prefer: live walk, seed fix, capture, trial.

---

## 8. Recency / coverage sensors (optional)

### 8.1 Signals

| Signal | Compute |
|--------|---------|
| `seed_mtime` | max mtime under `dsl/seeds/demo_data/` |
| `walk_mtime` | max mtime under `fixtures/scene_walks/` |
| `still_mtime` | max mtime under `.dazzle/qa/screenshots/` (local) |
| `trial_mtime` | max mtime of `qa-trial-*.json` |

### 8.2 Rules (v1 optional, v2 recommended)

- If `seed_mtime > walk_mtime` and walks exist → `stale_walks` deepen.
- If `seed_mtime > trial_mtime` and trial.toml exists → `stale_trial` deepen.
- If `seed_mtime > still_mtime` for floored heroes only → already partly empty_hero / floors.

Local stills are gitignored—recency sensors must **skip missing still dirs** (CI), not fail CI.

---

## 9. Integration with `/improve`

### 9.1 Selection order (target)

```text
CI / CodeQL / inbox  (unchanged preemption)
→ product_maturity
→ demo_fleet
→ journey_maturity
→ product_quality (felt)
→ story_walk          # outcome + divergence + epistemic live_unproven
→ trial_verdict       # outcome + optional no_trial policy
→ process residual    # last dig incomplete contract (v3)
→ densify if allowed
→ agent_acceptance_panel cadence
→ explore STALE
```

### 9.2 Playbook updates

| Doc | Change |
|-----|--------|
| `improve/strategies/story_walk.md` | Embed §5.3 contract; PASS criteria; evidence lines |
| `improve/strategies/agent_acceptance_panel.md` | Embed §5.4 |
| `improve/lanes/example-apps.md` | Process residual note; no densify when epistemic residual |
| `improve.md` | Short “dig contracts” pointer to this design |
| `docs/reference/product-maturity.md` | Link; maps vs sensors one paragraph |

### 9.3 Probe modules (implementation sketch)

| Module | Responsibility |
|--------|----------------|
| `scripts/story_walk_bar.py` | Extend with divergence issues + `live_unproven` if evidence file present |
| `scripts/trial_verdict_bar.py` | Optional `no_trial` for SHOWCASE |
| `scripts/improve_dig_receipt.py` (new) | Write/validate dig receipt schema |
| `scripts/improve_example_probes.py` | Aggregate new residual counts; force strategy unchanged unless process residual |

### 9.4 Dig receipt schema (v2)

```json
{
  "schema_version": 1,
  "cycle": 1260,
  "app": "contact_manager",
  "strategy": "story_walk",
  "ts": "2026-07-21T12:00:00Z",
  "stories": ["ST-004", "ST-005"],
  "maps_cited": [
    {"path": "examples/contact_manager/stems/story-driven-jobs.md", "kind": "stem"}
  ],
  "walks_touched": ["fixtures/scene_walks/user_st_004.yaml"],
  "actuators": {
    "walk_validate": 0,
    "walk_dry_run": 0,
    "walk_live_run": null,
    "live_skip_reason": "no_db"
  },
  "outcome": "PASS",
  "epistemic": ["live_unproven"],
  "residual_before": 9,
  "residual_after": 8
}
```

Path: `.dazzle/improve-digs/` (gitignored) **or** committed under `dev_docs/improve-digs/` if we want fleet auditability—**prefer gitignored + log excerpt** for v2 to avoid churn; self-audit reads log.

---

## 10. Relationship to maps (SPEC, stems, claims, stills)

| Map | Role under this design |
|-----|------------------------|
| **Stories** | Outcome residual (landings); contract S1; divergence pairs |
| **Stems** | Contract map citation (S2)—not scored for content |
| **SPEC / SPECIFICATION** | Alternate map citation; trial scenario authoring input |
| **Claims** | Contract MAY; optional deepen if claim_absent later |
| **Stills** | Existing floors only; epistemic never_captured deferred |
| **#1626 bake-off** | Human/programmatic re-score; not machine residual |

**Efficient context stays efficient:** agents are pointed at short stems/story ids, not forced to re-derive the product from the monorepo. Contracts ensure those pointers are **used**.

---

## 11. Actuators (CLI + MCP) — canonical menu

| Actuator | Strategies that may require it |
|----------|--------------------------------|
| `dazzle validate` / lint | Any example dig |
| `dazzle test walk validate` / `run --dry-run` | story_walk MUST |
| `dazzle test walk run` (live) | story_walk SHOULD |
| `dazzle demo quality` / product_quality MCP | demo_fleet / OBSERVE |
| `dazzle qa trial` / journey mode | acceptance MUST |
| seed / reset-and-load / `__test__/seed` | live walk, capture |
| `dazzle qa capture` | demo_fleet still residual |
| `story_walk_bar --write-stubs` | story_walk enhance |

Dig contracts pick a **subset** per strategy; they do not require all actuators every cycle.

---

## 12. Phased implementation plan

### PR1 — Dig contracts as playbook law (docs only + self-audit hints)

- Update `story_walk.md`, `agent_acceptance_panel.md`, `example-apps.md`, `improve.md`, this design status → Accepted.
- Document required `contract:` log lines.
- **Gate:** self_audit strategy greps recent improve commits for contract lines when strategy was story_walk/acceptance.
- **No** residual_total change yet.

### PR2 — Divergence in `story_walk_bar`

- Implement `div.entry_ws`, `div.weak_cues`, `div.persona`, walk story orphan check.
- Unit tests on support_tickets / simple_task fixtures + synthetic tmp walks.
- Residual includes divergence issues (deepen/thin as §6.4).

### PR3 — Dig receipts + epistemic `live_unproven`

- Receipt writer helper; story_walk strategy writes receipt on PASS.
- Optional marker file per walk: `fixtures/scene_walks/.live_green.json` or receipt scan for last live success.
- `live_unproven` deepen when walk covered but no live evidence.
- `improve_example_probes` remains source of force=.

### PR4 — Showcase `no_trial` policy (opt-in)

- `trial_verdict_bar`: SHOWCASE without trial.toml → residual thin.
- Author trial.toml for invoice_ops, project_tracker, hr_records from stories/SPEC jobs (separate digs or same PR if small).

### PR5 — Process residual (last dig incomplete)

- If backlog says IN_PROGRESS story_walk and no receipt/contract lines for N cycles → process residual force same strategy.
- Or: probe scans last cycle log—only if reliable.

### Out of scope for this stack

- Full still quality scorer
- SPEC truth residual
- Stem compliance residual
- Claims evergreen residual

---

## 13. Acceptance criteria (design complete when implemented)

| # | Criterion |
|---|-----------|
| AC1 | story_walk PASS without dry-run is invalid per playbook (PR1) and detectable by self-audit |
| AC2 | Divergence: walk entry mismatch with story given workspace → residual issue on that app |
| AC3 | weak_cues residual when assert texts are empty/generic |
| AC4 | dry-run-only walks can clear “no_walks” but leave `live_unproven` deepen |
| AC5 | agent_acceptance PASS requires trial report JSON trial_verdict_bar can parse |
| AC6 | densify_allowed=0 still blocks densify when only process/epistemic residual remains |
| AC7 | CI without local stills/receipts does not fail unrelated unit gates (skip missing) |
| AC8 | Documentation links from product-maturity + improve.md to this spec |

---

## 14. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Contract theater (fake log lines) | Prefer exit codes + file receipts (v2); self-audit samples files |
| Residual explosion (all apps deepen forever) | Cap issue lists; tier deepen lower priority than critical no_walks |
| Live DB requirement slows loop | live SHOULD; dry-run MUST; epistemic honest |
| Agents ignore playbook | PR5 process residual; self-audit cadence |
| Over-fitting weak_cues | Allow domain tokens from story title; only residual empty/generic |

---

## 15. Open questions

1. **Showcase requires trial.toml?** Default proposal: yes in PR4; confirm before shipping residual heat for invoice/project/hr.
2. **Receipt location:** gitignored `.dazzle/improve-digs/` vs committed `dev_docs/`? Prefer gitignored + log.
3. **Live evidence store:** per-walk sidecar vs global receipt scan? Sidecar is clearer for multi-walk apps.
4. **Should claims appear in residual v1?** Recommendation: no—contract MAY only.
5. **metric_list risk=2:** promote to residual later or leave warn-only? Out of this design’s v1.

---

## 16. Success metrics (after 2–4 weeks of improve cycles)

| Metric | Direction |
|--------|-----------|
| story_walk residual apps | ↓ toward 0 on showcase |
| Digs with contract evidence (log/receipt) | ↑ toward 100% of story_walk/acceptance cycles |
| Live-proven walks (not only dry-run) | ↑ on flagship trio first |
| Housekeeping idle while residual_total>0 | → 0 |
| Fleet bake-off mean (#1626) | Secondary; re-score after stills/live, not PR1 KPI |
| Densify commits under densify_allowed=0 | → 0 |

---

## 17. References

- `.claude/commands/improve.md` — driver selection
- `.claude/commands/improve/strategies/story_walk.md`
- `.claude/commands/improve/strategies/agent_acceptance_panel.md`
- `docs/reference/product-maturity.md` — antagonist + agent loop
- `docs/recipes/agent-qa-ladder.md` — L2 walks / L3 trials
- `docs/superpowers/specs/2026-03-14-improve-command-design.md` — historical improve
- GitHub #1626 — commercial bake-off tracker
- Shipped: `scripts/story_walk_bar.py`, `scripts/trial_verdict_bar.py`, `scripts/improve_example_probes.py`

---

## 18. Decision record (pre-implementation)

| Decision | Choice |
|----------|--------|
| Full still quality residual | **Out** — human/#1626 |
| SPEC/stem content residual | **Out** — maps + citation only |
| Dig contracts | **In** — playbook then receipt |
| Divergence pairs | **In** — walk↔story first |
| Epistemic live_unproven | **In** — deepen |
| no_trial for showcase | **Later PR, opt-in** |
| Beg-the-question outcome bars | **Explicitly rejected** in this workstream |

**Next step after acceptance:** implement PR1 (playbook contracts + self-audit hints), then PR2 (divergence sensors).
