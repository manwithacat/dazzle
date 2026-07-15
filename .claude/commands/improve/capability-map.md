# Improve-loop capability map

**Purpose.** A registry of every capability the project has built (`dazzle` CLI +
MCP tools + `.claude` skills/commands + standalone loops), each with an owning lane
and a staleness status, so the `/improve` loop **polices its own coverage** — nothing
we build rots unexercised behind the framework's velocity. This is the governance
half of the "pull all skills under the aegis of the improve loop" directive
(2026-07-08); the driver's capability-coverage rule (see `improve.md` Step 1 rule 7)
reads this file to bias directed exploration toward `UNOWNED` / `STALE` /
**`OWNED-IDLE` first-exercise**. Product TR-rows are drained separately (rule 6 /
`trial_signal_action.md`) when autonomous-actionable.

**Status vocabulary**
- `USED` — a lane/strategy invokes it every relevant cycle.
- `OWNED-IDLE` — has an owning lane but runs only on demand / low frequency.
  **Rule 7 first-exercises these** when UNOWNED/STALE are clear (playbook:
  `improve/strategies/owned_idle_exercise.md`). Prefer subscription vision over
  metered `taste-panel` / `*-vision` judges.
- `STALE` — owned but not exercised for ≥ **20** cycles → the driver biases toward it.
  Also treat `USED` rows with lag ≥20 as **STALE-effective** even if the label lags.
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
| `dazzle validate` / `lint` | CLI | example-apps (Tier 1) | 697 | USED |
| `dazzle ux verify` (contracts/interactions) | CLI | framework-ux, ux-converge, example-apps | 707 | USED |
| `dazzle qa capture` (Tier-2 visual scrape) | CLI | example-apps (visual_tier2) | 710 | USED |
| `dazzle qa trial` | CLI | trials | 463 | STALE (lag 248 since @463) |
| `dazzle qa login` | CLI | (support for qa capture/verify) | 710 | USED |
| `hm gallery interaction probes` (Playwright exclusive/multi-open interaction contracts) | script `hm_gallery_probes.py` + strategy `gallery_probes` | **hm-convergence** | 696 | USED |
| `dazzle qa taste-panel` | CLI (metered) + **subscription substitute** `hm_subscription_vision` / visual_smoke | **hm-convergence** + framework-ux | 695 | USED |
| `dazzle qa component-vision` (advisory judged read, one HM showcase region) | CLI (metered) / subscription host-Read substitute | **hm-convergence** + framework-ux | 709 | USED |
| `dazzle qa property-vision` (advisory property page vs family exemplars) | CLI (metered) / subscription host-Read substitute | **hm-convergence** | 482 | STALE (lag 229 since @482) |
| **HM hyperpart coherence** (investigate sweep + drain queue) | `hm_pages_vision.py` + `hm_coherence_queue.py` + strategy `hyperpart_coherence` | **hm-convergence** | 709 | USED |
| `dazzle deploy plan` (target-agnostic AppSpec→infra inference) | CLI | example-apps (Tier 1) | 698 | USED |
| MCP `conformance` (summary/cases/gaps) | MCP | example-apps (Tier 1) | 697 | USED |
| MCP `dsl` (fidelity/validate/lint/brief/…) | MCP | example-apps (Tier 1) | 703 | USED |
| fitness **engine** (`run_fitness_strategy`) | Python API | framework-ux (Phase B) | 699 | USED |
| `dazzle sentinel mutate` | CLI | test-suite (mutation floor) | 694 | USED |
| `dazzle rhythm` (fidelity/gaps/evaluate/lifecycle/propose) | CLI | example-apps (Tier 1) | 700 | USED |
| `dazzle story` (scope-fidelity/list/generate-tests/propose) | CLI + MCP (composition/coverage) | example-apps (Tier 1) | 697 | USED |
| `dazzle test-design` (coverage-actions/runtime-gaps/…) | CLI | example-apps | 698 | USED |
| `dazzle pulse` (run/radar/persona/timeline/decisions/wfs) | CLI | framework-ux | 700 | USED |
| `dazzle sentinel scan` (findings/fuzz/history) | CLI + MCP | framework-ux | 699 | USED |
| `dazzle fitness` CLI (investigate/vitality/clones/code/triage/queue) | CLI | framework-ux | 699 | USED |
| `dazzle discovery` (coherence/run/report/verify-all-stories) | CLI + MCP | example-apps | 698 | USED |
| `dazzle composition` (audit/report) | CLI + MCP | framework-ux | 700 | USED |
| `dual_lock_queue` / `dual_lock_expand` (HM dual-lock promotion loop) | script + strategy | **hm-convergence** | 712 | USED |
| `shadcn_parity` (catalogue gaps → placeholder Hyperparts) | script + strategy | **hm-convergence** | 704 | USED |
| **HM zero-floor** (emitter Tailwind utils + residual Dazzle design CSS == 0; was reservoir metric) | script + gate | **hm-convergence** | 704 | USED |
| `dazzle pitch` (review/update/enrich/…) | CLI + MCP | — | — | EXEMPT (human-invoked) |
| `dazzle spec` / `spec-narrate` skill | CLI + skill | — | — | EXEMPT (stakeholder docs) |
| `dazzle sweep` / `nightly` | CLI | test-suite (nightly = mutation backstop) | 704 | USED |
| `dsl-authoring` skill | skill | — | — | EXEMPT (in-session authoring aid) |
| `phase-contract` skill | skill | — | — | EXEMPT (execution harness) |
| `qa-trial` skill | skill | trials (downstream authoring) | 488 | STALE (lag 223 since @488) |
| `/fuzz` (boot-stderr integration sweep) | standalone loop | own entrypoint (complementary) | 705 | USED |
| `/smells` (code-smell scan; consumes `fitness code`) | standalone loop | own entrypoint (complementary) | 709 | USED |
| `/xproject` (cross-project scan; pulse/sentinel/discovery on siblings) | standalone loop | own entrypoint (complementary) | 706 | USED |
| `dazzle rbac` (matrix/prove/verify/routes/report/byte-routes/access-review) | CLI | framework-ux | 699 | USED |
| `dazzle coverage` (framework-artefact coverage across example apps) | CLI | example-apps | 700 | USED |
| `dazzle fragment-audit` (Fragment-rendering coverage per project) | CLI | framework-ux | 700 | USED |
| `dazzle process` (propose/save/diagram) | CLI + MCP `process` | example-apps | 703 | USED |
| `dazzle compliance` (compile/evidence/gaps/privacy/validate-citations) | CLI + MCP `compliance` | example-apps | 703 | USED |
| MCP `policy` (analyze/conflicts/coverage/simulate/access_matrix/verify_status) | MCP | framework-ux | 703 | USED |
| MCP `test_intelligence` (summary/failures/regression/coverage/context/journey) | MCP | test-suite | 704 | USED |
| MCP `semantics` (extract/validate_events/tenancy/compliance/analytics/extract_guards) | MCP | example-apps | 704 | USED |
| **CodeQL / code-scanning** (open-alert poll + remediate; strategy `codeql`) | GitHub code-scanning API + `improve/strategies/codeql.md` | **driver (Step 0c2)** | 704 | USED |
| **GitHub inbox** (consumer + owner/pilot bugs + Dependabot/PR processing) | `scripts/improve_github_inbox.py` + strategies `consumer_issues` / `github_prs` | **driver (Step 0c3)** | 710 | USED |
| `stems` skill | skill | — | — | EXEMPT (epistemic entry; in-session) |















> **Cycle 712 (2026-07-15) hm-convergence dual_lock STALE-clear.** Floors GREEN; dual_lock queue=0; coherence queue=0; shadcn gaps=0. Re-ran coverage+queue write; `hm_visual_smoke --dazzle-emit` PASS. dual_lock **692 → 712 USED**.
> **Capability-sweep cycle 711 (2026-07-15).** Sweep due (20 cycles since 691; self-audit last@708 lag 3).
> Re-derived inventory: skills/commands/strategies/CLI **unchanged** vs cycle 691. **No newly-built UNOWNED.** Owner_bug inbox heat remains Step 0c3 extension.
> **STALE recompute (threshold last-exercised ≤691):** **0 flip(s)** USED→STALE.
> **already STALE:** 3 (deepest `dazzle qa trial`@463 lag 248). **still USED:** 38.
> **Governance:** clear dual_lock STALE next if flipped; else highest-lag product STALE (skip qa trial until LLM driver healthy). Explore **42/100**. Next sweep ~**731**.
> **Cycle 710 (2026-07-15) example-apps STALE-clear.** support_tickets: `qa login manager` exit 0 (magic-link 303); `qa capture --above-fold` **6 screens**. GitHub inbox polled idle. Stamped qa login + qa capture + GitHub inbox **USED@710**.
> **Cycle 709 (2026-07-15) hm-convergence + smells STALE-clear.** coherence queue=0 mean=8.7; fitness code (smells substrate); component-vision subscription re-score mean 7.4. Stamped component-vision, hyperpart coherence, /smells **USED@709**.
> **Cycle 707 (2026-07-15) framework-ux STALE-clear.** support_tickets: `ux verify --contracts` **60/0/38**; `--structural` inventory 383. Stamped ux verify **USED@707**.
> **Cycle 706 (2026-07-15) standalone /xproject STALE-clear.** Scouted siblings with dazzle.toml: pennydreadful, AegisMark, cyfuture. validate+lint exit 0 all three; pulse radar AegisMark 98% / cyfuture 94% launch-ready (pennydreadful pulse exit 1, non-blocking). Stamped /xproject **USED@706**.
> **Cycle 705 (2026-07-15) standalone /fuzz STALE-clear.** Boot-stderr scrape 4 apps (support_tickets, simple_task, contact_manager, fieldtest_hub) — clean start/stop; no hard signatures (duplicate route / text-shaped / Traceback). Stamped /fuzz **USED@705**.
> **Cycle 704 (2026-07-15) multi STALE-clear.** floors GREEN; shadcn gaps 0; `dazzle sweep examples` exit 0; MCP semantics extract/validate_events/guards OK; CodeQL 0 open; test_intelligence KG present. Stamped semantics, sweep/nightly, shadcn, zero-floor, CodeQL, test_intelligence **USED@704**.
> **Cycle 703 (2026-07-15) example-apps + framework-ux STALE-clear.** support_tickets: process propose; compliance gaps+evidence; story scope-fidelity; schema; ux maturity; rbac matrix. Stamped process, compliance, MCP dsl, policy **USED@703**.
> **Cycle 700 (2026-07-15) framework-ux + example-apps STALE-clear.** coverage 61/61; composition audit 100; pulse radar 68% launch-ready; fragment-audit; rhythm gaps. Stamped coverage, pulse, composition, fragment-audit, rhythm **USED@700**.
> **Cycle 699 (2026-07-15) framework-ux STALE-clear.** support_tickets: `fitness code` + `fitness vitality`; `rbac matrix`; `sentinel scan`; `inspect project`. Stamped fitness engine/CLI, sentinel scan, rbac **USED@699**.
> **Cycle 698 (2026-07-15) example-apps STALE-clear.** support_tickets: `discovery report` exit 0; `deploy plan` (Postgres+s3); `test-design coverage-actions` exit 0. Stamped discovery, deploy plan, test-design **USED@698**.
> **Cycle 697 (2026-07-15) example-apps STALE-clear.** support_tickets: `validate`+`lint` exit 0 (warnings only); `story list` 18 stories; `conformance summary` 481 cases. Stamped validate/lint, story, conformance **USED@697**.
> **Cycle 696 (2026-07-15) hm-convergence STALE-clear gallery_probes.** Discover multi-details 3/3 catalog_ok. Run **6/6 PASS** (menubar/nav/accordion exclusive; tree multi_open; menubar/nav dismiss). Stamped gallery probes **USED@696**.
> **Cycle 695 (2026-07-15) hm-convergence STALE-clear taste-panel (subscription).** Floors GREEN; `hm_visual_smoke --dazzle-emit` PASS; host-Read scores ingested mean **7.4** (no metered taste-panel). Stamped taste-panel **USED@695**.
> **Cycle 694 (2026-07-15) test-suite STALE-clear.** `dazzle sentinel mutate --suite security` **PASS** — all 5 modules ≥ floor (crypto 83%, rbac 71%, csrf 85%, rls 100%, predicate 77%). Stamped sentinel mutate **USED@694**.
> **Cycle 692 (2026-07-15) hm-convergence dual_lock STALE-clear.** Floors GREEN; dual_lock queue=0; coherence queue=0. Re-ran coverage+queue write; `hm_visual_smoke --dazzle-emit` PASS. dual_lock **671 STALE → 692 USED**.
> **Capability-sweep cycle 691 (2026-07-15).** Sweep due (21 cycles since 670; self-audit last@678 lag 13).
> Re-derived inventory: skills/commands/strategies/CLI **unchanged** vs cycle 670. **No newly-built UNOWNED.** Inbox owner_bug heat is Step 0c3 extension (already mapped GitHub inbox@690).
> **STALE recompute (threshold last-exercised ≤671):** **1 flip(s)** USED→STALE — `dual_lock_queue` / `dual_lock_expand` (HM dual-lock pr@671 lag 20.
> **already STALE:** 5 (deepest `dazzle qa trial`@463 lag 228). **still USED:** 35 (hottest gallery/qa cluster @690…).
> **Governance:** clear dual_lock STALE next (hm-convergence) if flipped; else rotate high-lag product STALE. Explore budget **27/100**. Next sweep ~**711**.
> **Cycle 690 (2026-07-15) consumer-issues.** owner_bug heat: fixed #1590 steps equal columns + #1591 nav wrap. GitHub inbox **USED@690**.
> **Cycle 689 (2026-07-15) example-apps STALE-clear.** support_tickets: `qa login manager` exit 0; `qa capture --above-fold` **6 screens**. Stamped qa login + qa capture **USED@689**.
> **Cycle 688 (2026-07-15) hm-convergence + smells STALE-clear.** coherence queue=0 mean=8.7; fitness code (smells substrate); component-vision subscription re-score mean 7.2. Stamped component-vision, hyperpart coherence, /smells **USED@688**.
> **Cycle 687 (2026-07-15) framework-ux STALE-clear.** support_tickets: `ux verify --contracts` **60/0/38**; `--structural` inventory 383. GitHub inbox polled idle. Stamped ux verify + GitHub inbox **USED@687**.
> **Cycle 684 (2026-07-15) multi STALE-clear.** floors GREEN; shadcn gaps 0; `dazzle sweep examples` exit 0; MCP semantics extract/validate_events/extract_guards OK; CodeQL poll clean; test_intelligence KG present (coverage handler needs init in-process). Stamped semantics, sweep/nightly, shadcn, zero-floor, CodeQL, test_intelligence **USED@684**.
> **Cycle 682 (2026-07-15) example-apps + framework-ux STALE-clear.** support_tickets: process propose; compliance gaps+evidence; story scope-fidelity; schema/ux maturity. Stamped process, compliance, MCP dsl, policy **USED@682**.
> **Cycle 679 (2026-07-15) framework-ux + example-apps STALE-clear.** coverage 61/61; composition audit 100; pulse radar; fragment-audit; rhythm gaps. Stamped coverage, pulse, composition, fragment-audit, rhythm **USED@679**.
> **Cycle 677 (2026-07-15) framework-ux STALE-clear.** support_tickets: `fitness code` + `fitness vitality`; `rbac matrix`; `sentinel scan`; `inspect project`. Stamped fitness engine/CLI, sentinel scan, rbac **USED@677**.
> **Cycle 676 (2026-07-15) example-apps STALE-clear.** support_tickets: `discovery report` exit 0; `deploy plan` exit 0; `test-design coverage-actions` exit 0. Stamped discovery, deploy plan, test-design **USED@676**.
> **Cycle 675 (2026-07-15) example-apps STALE-clear.** support_tickets: `validate`+`lint` exit 0; `story list` 18; `conformance summary` 481 cases. Stamped validate/lint, story, conformance **USED@675**.
> **Cycle 674 (2026-07-15) hm-convergence STALE-clear gallery_probes.** Discover multi-details 3/3 catalog_ok. Run **6/6 PASS** (menubar/nav/accordion exclusive; tree multi_open; menubar/nav dismiss). Stamped gallery probes **USED@674**.
> **Cycle 673 (2026-07-15) hm-convergence STALE-clear taste-panel (subscription).** `hm_visual_smoke --dazzle-emit` PASS; host-Read scores ingested mean **7.2** (no metered taste-panel). Stamped taste-panel **USED@673**.
> **Cycle 672 (2026-07-15) test-suite STALE-clear.** `dazzle sentinel mutate --suite security` **PASS** — all 5 modules ≥ floor (crypto 83%, rbac 71%, csrf 85%, rls 100%, predicate 77%). Stamped sentinel mutate **USED@672**.
> **Cycle 671 (2026-07-15) hm-convergence dual_lock STALE-clear.** Floors GREEN; dual_lock queue=0; coherence queue=0; shadcn gaps=0. Re-ran coverage+queue write; `hm_visual_smoke --dazzle-emit` PASS. dual_lock **650 STALE → 671 USED**.
> **Capability-sweep cycle 670 (2026-07-15).** Sweep due (21 cycles since 649; self-audit 663).
> Re-derived inventory: skills (dsl-authoring, phase-contract, qa-trial, spec-narrate, stems) +
> agents skills (bump/check/cimonitor/docs-update/ship/smells/…) + commands
> (improve/fuzz/smells/xproject/issues/ship/check/bump/cimonitor/docs-update) + improve strategies
> (incl. github_prs, consumer_issues, self_audit, owned_idle_exercise) **unchanged**. CLI quality
> surface intact (`dazzle --help`). **No newly-built UNOWNED.** New infra since 649 already mapped:
> GitHub inbox@664, schedule_next/watchdog (driver Step 6, not UNOWNED). htmx pin beta5 is vendor,
> not a capability row.
> **STALE recompute (threshold last-exercised ≤650):** **1 flip** USED→STALE —
> dual_lock@650 lag **20**. **already STALE:** 10 (deepest qa trial@463 lag 207).
> **still USED (hot):** gallery@652 … qa capture@669. Explore **13/100**.
> Prefer STALE-clear dual_lock (hm-convergence) or highest-lag product STALE (qa trial blocked on
> grok-cli → taste/vision subscription path or sentinel mutate). Next sweep ~**690**.

> **Capability-sweep cycle 649 (2026-07-15).** Sweep due (20 cycles since 629; self-audit 648
> mid-window). Re-derived inventory: skills (dsl-authoring, phase-contract, qa-trial, spec-narrate,
> stems) + commands (improve/fuzz/smells/xproject/issues/ship/check/bump/cimonitor/docs-update) +
> improve strategies (incl. self_audit, owned_idle_exercise, trial_signal_action) **unchanged**.
> New infrastructure (not product capabilities): `scripts/improve_schedule_next.py` + watchdog —
> driver Step 6 self-chain, not UNOWNED. CLI quality surface intact. **No newly-built UNOWNED.**
> **STALE recompute (threshold last-exercised ≤629):** **0 flips** USED→STALE (still **0 USED**).
> dual_lock@608 lag **41** (was 21 @629). **already STALE:** 40 (deepest semantics@455 lag 194).
> **Governance:** explore budget renewed on dazzle-updated v0.104.0 (cycle 648 reset). Prefer
> STALE-clear dual_lock / highest-lag product STALE when product lanes run. Next sweep ~**669**.

> **Capability-sweep cycle 629 (2026-07-14).** Sweep due (20 cycles since 609; self-audit 618
> mid-window). Re-derived inventory: skills (dsl-authoring, phase-contract, qa-trial, spec-narrate,
> stems) + commands (improve/fuzz/smells/xproject/issues/ship/check/bump/cimonitor/docs-update)
> **unchanged**. CLI quality surface intact. **No newly-built UNOWNED.**
> **STALE recompute (threshold last-exercised ≤609):** **1 flip** USED→STALE —
> dual_lock@608 (lag 21).
> **still USED (0):** none.
> **already STALE:** 40 (deepest semantics@455 lag 174).
> **Governance:** gallery dual-lock drained @608; dual_lock went cold under explore-cap housekeeping
> (610–628). Prefer STALE-clear dual_lock or highest-lag STALE (semantics) when explore budget renews.
> Explore **100/100**. Next sweep ~**649**.

> **Capability-sweep cycle 609 (2026-07-14).** Sweep due (20 cycles since 589; self-audit 603
> mid-window). Re-derived inventory: skills (dsl-authoring, phase-contract, qa-trial, spec-narrate,
> stems) + commands (improve/fuzz/smells/xproject/issues/ship/check/bump/cimonitor/docs-update)
> **unchanged**. CLI quality surface intact (`dazzle --help`). **No newly-built UNOWNED.**
> **STALE recompute (threshold last-exercised ≤589):** **0 flips** USED→STALE —
> dual_lock monomania kept the only hot capability (gallery dual-lock queue drained @608 HMC-154).
> **still USED (1):** dual_lock@608 (lag 1).
> **already STALE:** 39 (deepest semantics@455 lag 154).
> **Governance:** gallery dual-lock arc complete (queue depth 0). Prefer STALE-clear highest lag
> when explore budget renews, or hm strategies (shadcn/coherence/gallery_probes). Explore **100/100**.
> Next sweep ~**629**.

> **Capability-sweep cycle 589 (2026-07-14).** Sweep due (20 cycles since 569; self-audit 588
> mid-window). Re-derived inventory: skills (dsl-authoring, phase-contract, qa-trial, spec-narrate,
> stems) + commands (improve/fuzz/smells/xproject/issues/ship/check/bump/cimonitor/docs-update)
> **unchanged**. CLI quality surface intact (`dazzle --help`). **No newly-built UNOWNED.**
> **STALE recompute (threshold last-exercised ≤569):** **0 flips** USED→STALE —
> dual_lock monomania kept the only hot capability.
> **still USED (1):** dual_lock@587 (lag 2).
> **already STALE:** 33 (deepest semantics@455 lag 134).
> **Governance:** dual-lock gallery DOM-only monomania (HMC-123–136) continues under explore cap.
> Prefer dual_lock residual gallery (center/field/separator) or STALE-clear highest lag when
> explore budget renews. Explore **100/100**. Next sweep ~**609**.

> **Capability-sweep cycle 569 (2026-07-14).** Sweep due (20 cycles since 549; self-audit 558
> mid-window). Re-derived inventory: skills (dsl-authoring, phase-contract, qa-trial, spec-narrate,
> stems) + commands (improve/fuzz/smells/xproject/issues/ship/check/bump/cimonitor/docs-update)
> **unchanged**. **No newly-built UNOWNED.** **STALE recompute (threshold last-exercised ≤549):**
> **0 flips** USED→STALE — dual_lock monomania kept the only hot capability.
> **still USED (1):** dual_lock@568 (lag 1).
> **already STALE:** 39 (deepest semantics@455 lag 114).
> **Governance:** dual-lock packing/DOM-only monomania (HMC-097–119) continues under explore cap.
> Prefer dual_lock product continue or STALE-clear highest lag when budget renews. Explore **100/100**.
> Next sweep ~**589**.





> **Cycle 669 (2026-07-15) example-apps STALE-clear.** support_tickets: `qa capture --above-fold` **6 screens** under `.dazzle/qa/screenshots/` (ticket_queue/agent_dashboard/my_tickets × Timestamped/Auditable). Stamped qa capture **USED@669**.
> **Cycle 668 (2026-07-15) example-apps STALE-clear.** support_tickets: `dazzle serve` + `qa login` for manager/agent/admin/customer exit 0; magic-link GET → 303. Stamped qa login **USED@668**.
> **Cycle 665 (2026-07-15) framework-ux STALE-clear.** support_tickets: `dazzle serve` + `ux verify --contracts` **60 passed / 0 failed / 38 pending**; `ux verify --structural` inventory 383. Stamped ux verify **USED@665**.

> **Cycle 650 (2026-07-15) hm-convergence dual_lock STALE-clear.** Floors GREEN; coherence queue=0; dual_lock queue=0; shadcn gaps=0. Re-ran coverage+queue write; `hm_visual_smoke --dazzle-emit` PASS (playwright chromium). dual_lock last-exercised **650 → USED**.

> **Capability-sweep cycle 549 (2026-07-14).** Sweep due (20 cycles since 529; self-audit 543
> ran mid-window). Re-derived inventory: `dazzle --help` quality surface intact; skills
> (dsl-authoring, phase-contract, qa-trial, spec-narrate, stems) + commands
> (improve/fuzz/smells/xproject/issues/ship/check/bump/cimonitor/docs-update) **unchanged**.
> **No newly-built UNOWNED.** **STALE recompute (threshold last-exercised ≤529):**
> **1 flip** USED→STALE — gallery probes@512 (lag 37).
> **still USED (1):** dual_lock@548 (lag 1).
> **already STALE:** 38 (validate/rbac/vision/… cold set; deepest semantics@455 lag 94).
> **Governance:** dual-lock monomania (HMC-079–101) kept one capability hot; gallery probes
> rolled cold. Prefer dual_lock product continue under explore cap, or STALE-clear highest lag
> when budget renews (semantics@455, story@456 deepest). Explore **100/100**. Next sweep ~**569**.


> **Cycle 652 (2026-07-15) hm-convergence gallery_probes STALE-clear.** Discover: multi-details 3/3 catalog_ok. Run: **6/6 PASS** (menubar, navigation_menu, accordion exclusive; tree multi_open; menubar/nav dismiss). gallery probes last-exercised **652 → USED**.

> **Capability-sweep cycle 486 (2026-07-13).** Sweep due (20 cycles since 466). Re-derived
> inventory: MCP consolidated tools **34** (unchanged); skills/commands tree unchanged; no new
> UNOWNED. **STALE recompute (threshold last-exercised ≤466):** **20 flips**
> USED→STALE among mid-window stamps (validate@449 … semantics@455; deepest sentinel mutate@447
> lag 39). **still USED** (lag≤19): test-design@467 … xproject@485 (OWNED-IDLE first-exercises
> + recent STALE-clear tail). OWNED-IDLE queue drained (all three vision + /fuzz/smells/xproject
> now USED). **Governance:** after full OWNED-IDLE graduation, the mid-arc stamps roll cold
> again — prefer highest lag next (sentinel mutate@447, qa-trial skill@448, validate@449).
> Explore budget at sweep: **90/100**. Next sweep due ~**506**.


> **Cycle 653 (2026-07-15) example-apps STALE-clear.** support_tickets: `dazzle validate`+`lint` exit 0 (warnings only); `story list` 10 stories; `conformance summary` 481 cases; HM surface HM_OK 12/12. Stamped validate/lint, story, conformance **USED@653**.

> **Capability-sweep cycle 466 (2026-07-13).** Sweep due (32 cycles since 434; self-audit 465
> ran first). Re-derived inventory: quality CLI surface intact; MCP consolidated tools **34**
> (unchanged); skills 5 + commands improve/fuzz/smells/xproject/issues/ship/…. **No newly-built
> UNOWNED** — cycles 435–465 were STALE-clear re-stamps + self-audit (0 new CLI/MCP/skill
> entrypoints). **STALE recompute (threshold last-exercised ≤446):** **12 flips** USED→STALE
> — test-design@435, sentinel scan@436, fitness CLI@437, rbac@438, rhythm@439, coverage@440,
> pulse@441, composition@442, fragment-audit@443, qa login@444, qa capture@445, sweep@446.
> **still USED** (lag≤19): sentinel mutate@447 … gallery@464. OWNED-IDLE unchanged (6).
> **Governance:** trailing edge of the 434 STALE-clear arc now rolls back into STALE on a
> 20-cycle lag; prefer highest lag next (`test-design`@435, `sentinel scan`@436) over
> re-stamping still-USED rows. Explore budget at sweep: **72/100**. Next sweep due ~**486**.

> **Capability-sweep cycle 434 (2026-07-13).** Sweep overdue (38 cycles since 396; self-audit
> 432 and TR-47 VERIFIED 433 ran first). Re-derived inventory: `dazzle --help` quality
> surface intact (validate/lint/ux/qa/deploy/rbac/pulse/sentinel/discovery/composition/
> fitness/story/rhythm/coverage/process/compliance/test-design/…); MCP consolidated tools
> **34** (unchanged names vs cycle 376); `.claude/skills` (5: dsl-authoring, phase-contract,
> qa-trial, spec-narrate, stems) + `.agents/skills` + `.claude/commands` (improve/fuzz/
> smells/xproject/issues/ship/check/bump/cimonitor/docs-update). **No newly-built UNOWNED**
> loop capability — cycles 409–433 were pure product TR drain (signing storage, activity_feed,
> demo blueprints, seed timestamps, nav hooks, trial logging) on already-mapped surfaces;
> `dazzle signing` remains operator/substrate (CI + unit suites), not a new loop gap.
> **STALE recompute (threshold last-exercised ≤414):** **massive cold set** — every previously
> USED row is now STALE (highest stamp was gallery@407, lag 27). Already-STALE test-design/
> sentinel-scan/fitness-CLI deepen to lag 59–61. **OWNED-IDLE unchanged (6):** taste/vision
> trio + /fuzz/smells/xproject. **Governance:** inverse of capability re-stamp monomania —
> TR drain delivered product value but **zero capability-map stamps** for 27+ cycles, so
> coverage governance now correctly forces a STALE clear rotation. Prefer highest-lag core
> first (`test-design`@373, `sentinel scan`@374, `fitness` CLI@375, then `rbac`/`rhythm`/
> `pulse`/…), not more residual low TRs. Explore budget at sweep: **42/100**. Next sweep due
> ~**454**.

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


> **Cycle 654 (2026-07-15) example-apps STALE-clear.** support_tickets: `discovery report` exit 0; `deploy plan` (Postgres+s3); `test-design coverage-actions` exit 0. Stamped discovery, deploy plan, test-design **USED@654**.

> **Cycle 655 (2026-07-15) framework-ux STALE-clear.** `fitness code` + `fitness vitality` (support_tickets); `rbac matrix`; `sentinel scan`; `inspect project`. Stamped fitness engine/CLI, sentinel scan, rbac **USED@655**.

> **Cycle 656 (2026-07-15) multi-lane STALE-clear.** coverage 61/61; composition audit 100; pulse run 68% launch-ready; fragment-audit support_tickets; rhythm gaps; schema summary. Stamped coverage, pulse, composition, fragment-audit, rhythm **USED@656**.

> **Cycle 657 (2026-07-15) STALE-clear process/compliance/MCP dsl+policy.** process propose; compliance gaps+evidence; MCP dsl validate/lint/modules; fidelity score 0.99; policy analyze. Stamped process, compliance, MCP dsl, policy **USED@657**. semantics still no handler module (STALE).

> **Cycle 658 (2026-07-15) STALE-clear semantics/sweep/test_intelligence/codeql/shadcn/zero-floor.** MCP semantics via event_first_tools (extract/validate_events/guards); `dazzle sweep examples` exit 0; test_intelligence after KG init; CodeQL poll clean; shadcn gaps 0; HM floor GREEN. Stamped six capabilities **USED@658**.
---


> **Capability-sweep cycle 509 (2026-07-14).** Sweep due (23 cycles since 486; self-audit 508 ran first).
> Re-derived inventory: `dazzle --help` quality surface intact (validate/lint/qa/deploy/rbac/pulse/
> sentinel/discovery/composition/fitness/story/rhythm/coverage/process/compliance/…); MCP tool
> surface unchanged vs prior sweeps; `.claude/skills` (5: dsl-authoring, phase-contract, qa-trial,
> spec-narrate, stems) + `.agents/skills` + `.claude/commands` (improve/fuzz/smells/xproject/issues/
> ship/check/bump/cimonitor/docs-update). **No newly-built UNOWNED** — cycles 487–508 were STALE
> clears, cimonitor, CodeQL, coherence product drains (tags/tree/app-shell/radar/…), and self-audit;
> hyperpart_coherence already mapped @507; CodeQL driver gate @496. Operator EXEMPT unchanged.
> **STALE recompute (threshold last-exercised ≤489):** **21 flips** USED→STALE.
> Deepest new cold set includes mid/OWNED-IDLE graduation arc (validate@489 … vision/fuzz@481–485).
> **still USED** (lag≤19): dual_lock/shadcn/zero-floor@490, process@491 … CodeQL@496, hyperpart@507.
> **Governance:** coherence drain monomania (498–507) + STALE-clear 487–494 left the mid-window
> cold again — prefer highest-lag STALE next (story@456, semantics@455, conformance@457) once
> explore budget renews; product dual_lock `menu` remains available without explore budget.
> Explore budget at sweep: **100/100**. Next sweep due ~**529**.


> **Capability-sweep cycle 529 (2026-07-14).** Sweep due (20 cycles since 509; self-audit 523).
> Re-derived inventory: `dazzle` quality CLI surface unchanged; `.claude/skills` (5) +
> `.agents/skills` + `.claude/commands` (improve/fuzz/smells/xproject/issues/ship/…).
> **No newly-built UNOWNED** — cycles 510–528 were cimonitor + dual-lock DOM-only expansion
> (menu→surface HMC-068–083) + gallery probes + self-audit; dual_lock already mapped.
> Operator EXEMPT unchanged.
> **STALE recompute (threshold last-exercised ≤509):** **8 flips** USED→STALE.
> **still USED (lag≤19):** dual_lock@528 and any mid-window stamps ≤19 lag.
> **Governance:** dual-lock monomania kept one capability hot; broad STALE cold set returns for
> validate/rbac/vision once explore budget renews (`dazzle-updated` or `/improve --reset-budget`).
> Explore budget at sweep: **100/100**. Next sweep due ~**549**.

## Lanes

| Lane | Owns | Playbook |
|---|---|---|
| `framework-ux` | ux contracts/fitness walks, taste-panel, sentinel scan, fitness investigate, composition, pulse | `lanes/framework-ux.md` |
| `example-apps` | validate/lint/conformance/fidelity, rhythm, story, test-design, discovery | `lanes/example-apps.md` |
| `trials` | qa trial scenarios | `lanes/trials.md` |
| `ux-converge` | contract-failure convergence | `lanes/ux-converge.md` |
| `test-suite` | redundancy-cluster collapse, sentinel mutate/nightly | `lanes/test-suite.md` |
| `hm-convergence` | HM ownership floors + dual-locks / taste (drain complete); zero-floor + delegation gates | `lanes/hm-convergence.md` |

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

> **Capability-sweep cycle 316 (2026-07-11).** Sweep due (20 cycles since 296). Re-derived
> inventory: `dazzle --help` (+ `qa` / `deploy` / quality subtrees), MCP tool schemas
> (`dazzle inspect api mcp-tools` → **35 tools**, unchanged names), `.claude/skills` +
> `.claude/commands` + `.agents/skills`. **No newly-built loop capability** since 296:
> cycles 297–315 were pure USED re-stamp rotation (rbac→…→Tailwind@313, self-audit 314,
> ux verify@315) with **zero product code** and no new CLI/MCP/skill entrypoints. Skills
> tree still: dsl-authoring, phase-contract, qa-trial, spec-narrate (+ agents: ship/check/
> bump/cimonitor/docs-update/smells). Commands: improve, fuzz, smells, xproject, issues,
> ship, check, bump, cimonitor, docs-update. NOT added (operator/CI EXEMPT): auth/db/
> backup family, `deploy heroku`, dual locks, `/ship`/`/check`/`/bump`. STALE recompute
> (threshold last-exercised ≤296): **one flip** — `dazzle deploy plan`@295 (lag 21) USED→
> **STALE**. Nearest lag risks: rbac@297 (19), rhythm@298 (18), coverage@300 (16),
> qa-trial@301 (15). OWNED-IDLE never-exercised still ~**16**. Governance: third consecutive
> sweep window with empty UNOWNED + empty TR backlog; next directed-explore should clear
> the single STALE (`deploy plan`) then **first-exercise IDLE** rather than another full
> USED re-rotation. Explore budget at sweep: 70/100.

> **Capability-sweep cycle 336 (2026-07-11).** Sweep due (20 cycles since 316). Re-derived
> inventory: `dazzle --help` (+ quality subtrees), MCP tool schemas (`dazzle inspect api
> mcp-tools` → **35 tools**, unchanged), `.claude/skills` + `.claude/commands` +
> `.agents/skills`. **No newly-built loop capability** since 316: cycles 317–335 were pure
> USED re-stamp rotation (deploy plan→…→Tailwind@334, self-audit 329, ux verify@335) plus
> zero product code. Skills/commands tree unchanged (dsl-authoring, phase-contract,
> qa-trial, spec-narrate; improve/fuzz/smells/xproject/issues/ship/check/bump/…). NOT added
> (operator/CI EXEMPT): auth/db/backup, `deploy heroku`, `/ship`/`/check`/`/bump`. STALE
> recompute (threshold last-exercised ≤316): **none** flip — post-316 directed-explore kept
> every previously USED row inside the 20-cycle window (nearest: deploy plan@317 lag 19,
> rbac@318 lag 18, rhythm@319 lag 17). OWNED-IDLE never-exercised still ~**16**. **Hard
> governance finding:** fifth consecutive sweep window with empty UNOWNED + empty TR
> backlog; the loop continues to spend almost all explore budget re-stamping STALE USED
> capabilities. Prefer **first-exercise of remaining OWNED-IDLE** (discovery, qa login,
> test-design, sentinel, composition, pulse, fitness CLI, taste/vision, …) when no STALE
> queue, not another full USED re-rotation. Explore budget at sweep: 88/100.

> **Capability-sweep cycle 356 (2026-07-12).** Sweep due (20 cycles since 336). Re-derived
> inventory: `dazzle --help` (77 top-level commands; quality subtrees qa/deploy/ux/rbac/pulse/
> sentinel/discovery/composition/fitness/story/rhythm/coverage/process/compliance present),
> MCP tools baseline still **35** (local venv lacks `mcp` package so `inspect api mcp-tools`
> cannot re-snapshot — same count as cycle 336), `.claude/skills` (5 including stems) +
> `.agents/skills` + `.claude/commands` (improve/fuzz/smells/xproject/issues/ship/…). **No
> newly-built UNOWNED loop capability** since 336: cycles 337–355 added product surfaces
> already mapped — `dual_lock_expand`@354 and `shadcn_parity`@355 (USED); stems skill EXEMPT.
> NOT added (operator/CI EXEMPT): auth/db/backup, `deploy heroku`, `/ship`/`/check`/`/bump`/
> `/cimonitor`, dual-lock pytest gates. STALE recompute (threshold last-exercised ≤336):
> **13 flips** to STALE — validate/lint@322, ux verify@335, qa trial@321, story@330,
> conformance@331, dsl@332, fitness engine@333, process@323, compliance@325, policy@326,
> test_intelligence@327, semantics@328, qa-trial skill@321. OWNED-IDLE never-exercised still
> ~**16**. **Governance:** hm-convergence dual-lock/shadcn monomania re-created cold core
> verify paths. Next rule-6 cycles should clear STALE (validate first) before more gallery
> placeholders. Explore budget: 0/100.

> **Capability-sweep cycle 376 (2026-07-12).** Sweep due (20 cycles since 356). Re-derived
> inventory: typer app **77** unique top-level commands/groups; MCP consolidated tools
> **34** (mcp package available this run); `.claude/skills` (5: dsl-authoring, phase-contract,
> qa-trial, spec-narrate, stems) + `.agents/skills` + `.claude/commands` (improve/fuzz/smells/
> xproject/issues/ship/check/bump/cimonitor/docs-update). **No newly-built UNOWNED** loop
> capability since 356 — cycles 357–375 were STALE clears + OWNED-IDLE first-exercise
> (discovery@372, test-design@373, sentinel scan@374, fitness CLI@375) + shadcn drain@358–359
> + dual_lock code deferred@360. STALE recompute (threshold last-exercised ≤356): **7 flips**
> — deploy plan@337, rbac@338, rhythm@339, coverage@340, pulse/composition/fragment-audit@341;
> **still STALE** qa-trial + qa-trial skill@321 (lag 55, no LLM driver). **still USED** 18
> (validate@357 through fitness CLI@375). OWNED-IDLE never-exercised remaining: qa capture/
> login/taste/vision, sentinel mutate, sweep/nightly, standalone /fuzz/smells/xproject (~10).
> **Governance:** STALE monomania risk shifted to mid-window Tier-1 (rbac/coverage/pulse) after
> successful core STALE clear + OWNED-IDLE graduation. Prefer clear 7 new STALE next, then
> remaining OWNED-IDLE. Explore budget: 15/100.

> **Capability-sweep cycle 396 (2026-07-12).** Inventory re-derived: `dazzle --help` /
> `dazzle commands` surface intact; MCP handler modules 42 under `handlers/`;
> `.claude/skills` = dsl-authoring, phase-contract, qa-trial, spec-narrate, stems;
> commands = improve/fuzz/smells/xproject/issues/ship/check/bump/cimonitor/docs-update.
> **new UNOWNED: none** (quality CLI/MCP already registered; remaining unmapped MCP
> handlers are platform plumbing — bootstrap/db/status/serializers — not loop gaps).
> **STALE flips (11):** last-exercised ≤376 crossed the 20-cycle threshold after
> the post-376 STALE-clear arc finished and the loop rotated process/compliance/policy.
> Prefer rule-6 drain of highest lag next (test_intelligence@365 → story@367 → …).
> **OWNED-IDLE unchanged (6):** taste-panel / component-vision / property-vision +
> standalone /fuzz /smells /xproject. **still USED** recent stamps through policy@395.
> Self-audit last@392 (lag 4); next capability-sweep due cycle **416**.
