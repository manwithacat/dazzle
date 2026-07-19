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
| `dazzle validate` / `lint` | CLI | example-apps (Tier 1) | 1008 | USED |
| `dazzle ux verify` (contracts/interactions) | CLI | framework-ux, ux-converge, example-apps | 1007 | USED |
| `dazzle qa capture` (Tier-2 visual scrape) | CLI | example-apps (visual_tier2) | 1010 | USED |
| `dazzle qa trial` | CLI | trials | 1017 | USED |
| `dazzle qa login` | CLI | (support for qa capture/verify) | 1010 | USED |
| `hm gallery interaction probes` (Playwright exclusive/multi-open interaction contracts) | script `hm_gallery_probes.py` + strategy `gallery_probes` | **hm-convergence** | 1006 | USED |
| `dazzle qa taste-panel` | CLI (metered) + **subscription substitute** `hm_subscription_vision` / visual_smoke | **hm-convergence** + framework-ux | 1006 | USED |
| `dazzle qa component-vision` (advisory judged read, one HM showcase region) | CLI (metered) / subscription host-Read substitute | **hm-convergence** + framework-ux | 1017 | USED |
| `dazzle qa property-vision` (advisory property page vs family exemplars) | CLI (metered) / subscription host-Read substitute | **hm-convergence** | 1017 | USED |
| **HM hyperpart coherence** (investigate sweep + drain queue) | `hm_pages_vision.py` + `hm_coherence_queue.py` + strategy `hyperpart_coherence` | **hm-convergence** | 1006 | USED |
| `dazzle deploy plan` (target-agnostic AppSpec→infra inference) | CLI | example-apps (Tier 1) | 1016 | USED |
| MCP `conformance` (summary/cases/gaps) | MCP | example-apps (Tier 1) | 1008 | USED |
| MCP `dsl` (fidelity/validate/lint/brief/…) | MCP | example-apps (Tier 1) | 1008 | USED |
| fitness **engine** (`run_fitness_strategy`) | Python API | framework-ux (Phase B) | 1015 | USED |
| `dazzle sentinel mutate` | CLI | test-suite (mutation floor) | 1011 | USED |
| `dazzle rhythm` (fidelity/gaps/evaluate/lifecycle/propose) | CLI | example-apps (Tier 1) | 1016 | USED |
| `dazzle story` (scope-fidelity/list/generate-tests/propose) | CLI + MCP (composition/coverage) | example-apps (Tier 1) | 1016 | USED |
| `dazzle test-design` (coverage-actions/runtime-gaps/…) | CLI | example-apps | 1016 | USED |
| `dazzle pulse` (run/radar/persona/timeline/decisions/wfs) | CLI | framework-ux | 1005 | USED |
| `dazzle sentinel scan` (findings/fuzz/history) | CLI + MCP | framework-ux | 1011 | USED |
| `dazzle fitness` CLI (investigate/vitality/clones/code/triage/queue) | CLI | framework-ux | 1015 | USED |
| `dazzle discovery` (coherence/run/report/verify-all-stories) | CLI + MCP | example-apps | 1016 | USED |
| `dazzle composition` (audit/report) | CLI + MCP | framework-ux | 1007 | USED |
| `dual_lock_queue` / `dual_lock_expand` (HM dual-lock promotion loop) | script + strategy | **hm-convergence** | 1006 | USED |
| `shadcn_parity` (catalogue gaps → placeholder Hyperparts) | script + strategy | **hm-convergence** | 1006 | USED |
| **HM zero-floor** (emitter Tailwind utils + residual Dazzle design CSS == 0; was reservoir metric) | script + gate | **hm-convergence** | 1006 | USED |
| `dazzle pitch` (review/update/enrich/…) | CLI + MCP | — | — | EXEMPT (human-invoked) |
| `dazzle spec` / `spec-narrate` skill | CLI + skill | — | — | EXEMPT (stakeholder docs) |
| `dazzle sweep` / `nightly` | CLI | test-suite (nightly = mutation backstop) | 1009 | USED |
| `dsl-authoring` skill | skill | — | — | EXEMPT (in-session authoring aid) |
| `phase-contract` skill | skill | — | — | EXEMPT (execution harness) |
| `qa-trial` skill | skill | trials (downstream authoring) | 1017 | USED |
| `/fuzz` (boot-stderr integration sweep) | standalone loop | own entrypoint (complementary) | 1009 | USED |
| `/smells` (code-smell scan; consumes `fitness code`) | standalone loop | own entrypoint (complementary) | 1015 | USED |
| `/xproject` (cross-project scan; pulse/sentinel/discovery on siblings) | standalone loop | own entrypoint (complementary) | 1009 | USED |
| `dazzle rbac` (matrix/prove/verify/routes/report/byte-routes/access-review) | CLI | framework-ux | 1007 | USED |
| `dazzle coverage` (framework-artefact coverage across example apps) | CLI | example-apps | 1009 | USED |
| `dazzle fragment-audit` (Fragment-rendering coverage per project) | CLI | framework-ux | 1007 | USED |
| `dazzle process` (propose/save/diagram) | CLI + MCP `process` | example-apps | 1016 | USED |
| `dazzle compliance` (compile/evidence/gaps/privacy/validate-citations) | CLI + MCP `compliance` | example-apps | 1005 | USED |
| MCP `policy` (analyze/conflicts/coverage/simulate/access_matrix/verify_status) | MCP | framework-ux | 1008 | USED |
| MCP `test_intelligence` (summary/failures/regression/coverage/context/journey) | MCP | test-suite | 1008 | USED |
| MCP `semantics` (extract/validate_events/tenancy/compliance/analytics/extract_guards) | MCP | example-apps | 1008 | USED |
| **CodeQL / code-scanning** (open-alert poll + remediate; strategy `codeql`) | GitHub code-scanning API + `improve/strategies/codeql.md` | **driver (Step 0c2)** | 1019 | USED |
| **GitHub inbox** (consumer + owner/pilot bugs + Dependabot/PR processing) | `scripts/improve_github_inbox.py` + strategies `consumer_issues` / `github_prs` | **driver (Step 0c3)** | 1019 | USED |
| `dazzle representation` + MCP `representation` (#1617 patterns/decide/classify/gin-sql) | CLI + MCP | framework-ux + example-apps | 1005 | USED |
| `dazzle prove` (story bindings + `prove representation`) | CLI | framework-ux + example-apps | 1005 | USED |
| `dazzle scaffold` (service/story/process-step skeletons; agent closed loop #1605) | CLI | example-apps | 1005 | USED |
| `stems` skill | skill | — | — | EXEMPT (epistemic entry; in-session) |
| **example product maturity** (anti-warehouse residual + continuous WI D/N/L/J/G) | `scripts/example_product_maturity.py` + strategy `product_maturity` / feature_creep | **example-apps** | 1019 | USED |
| **demo fleet bar** (#1626 antagonist: nav/seed/stills floors) | `scripts/demo_fleet_bar.py` + strategy `demo_fleet` | **example-apps** | 1012 | USED |
| **example journey maturity** (bound stories + open-via + hubs) | `scripts/example_journey_maturity.py` + strategy `journey_dogfood` | **example-apps** | 1016 | USED |
| **unified example probes** (product + demo + journey OBSERVE) | `scripts/improve_example_probes.py` | **example-apps** (driver Step 1 + status) | 1019 | USED |
| MCP `product_quality` (score — persona homes + stills + maturity) | MCP | **example-apps** | 1012 | USED |
| `dazzle demo quality` (#1626 felt residual bar) | CLI | **example-apps** | 1012 | USED |
| `dazzle demo reset-and-load` (#1627 closed-loop /__test__ seed) | CLI | example-apps + agent DX | 1012 | USED |
| MCP `status` `demo_world`/`runtime` (#1629 agent world-model read) | MCP | example-apps + agent DX | 1017 | USED |
| MCP `db` project-local DATABASE_URL resolve (#1629 G2) | MCP | example-apps + agent DX | 1017 | USED |








































> **Cycle 801 (2026-07-18).** **HOUSEKEEPING idle** — explore **100/100**; no heat; self-audit@798; sweep@792. Renewal: release or `/improve --reset-budget`. Stamps @801.

> **Cycle 800 (2026-07-18).** **HOUSEKEEPING idle** — explore **100/100** milestone; self-audit@798; sweep@792; no product heat. Renewal: release signal or `/improve --reset-budget`. Stamps @800.

> **Cycle 799 (2026-07-18).** **HOUSEKEEPING idle** — explore **100/100**; self-audit@798; sweep@792; no inbox heat. Renewal: `dazzle-updated` or `/improve --reset-budget`. Stamps @799.

> **Cycle 798 (2026-07-18).** **self-audit** (15 cycles since 783): window `aa1c8363f..HEAD`; 5 product commits **CLEAN**. Explore still **100/100**. Next self-audit ~**813**.

> **Cycle 797 (2026-07-18).** **HOUSEKEEPING idle** — explore **100/100**; no REGRESSION/bugs; self-audit lag14 (due ~798); sweep@792. Renewal: `dazzle-updated` or `/improve --reset-budget`. Stamps @797.

> **Cycle 796 (2026-07-18).** Preflight repair: deferred-imports baseline `_shared.py` 4→3 (burn-down from #1623 top-level format_cell import). Explore **100/100**. Stamps inbox/codeql @796.

> **Cycle 795 (2026-07-18).** **framework-ux** product fix **#1623** (not explore): workspace `_render_typed_value` datetime/date via `format_cell` + defensive ISO text. 4 unit tests. Explore still **100/100**. Stamps inbox/codeql @795.

> **Cycle 794 (2026-07-18).** **HOUSEKEEPING idle** — explore budget **100/100** cap; no REGRESSION/PENDING; self-audit lag11 (due ~798); sweep@792. Renewal: next `dazzle-updated` release signal, or `/improve --reset-budget`. Stamps inbox/codeql @794. Explore **100/100**.





> **Cycle 1019 (2026-07-19).** **example-apps** ordinary explore project_tracker (N): curated admin/manager/member navs (workspace ids). WI app **0.32→0.20** (N→0). wi_fleet **0.223≤floor**. Stamps product_maturity + probes + CodeQL/inbox **USED@1019**. Explore **76/100**. Next wi_next=**domain_join_co** (L). self-audit ~1028; sweep ~1034.

> **Cycle 1018 (2026-07-19).** **example-apps** ordinary explore invoice_ops (D+N): curated navs (N→0; fixed orphan projects_home/invoices_home), densified my_invoices/approval_desk, payments_trail (8 product workspaces). WI app **0.19**; wi_fleet **0.233≤floor**. Stamps product_maturity + probes + CodeQL/inbox **USED@1018**. Explore **75/100**. Next wi_next=**project_tracker** (N). self-audit ~1028; sweep ~1034.

> **Cycle 1017 (2026-07-19).** **trials + agent DX** STALE-clear (qa trial@980 lag~37; status/db/vision@981): trial-inventory + trial-coverage static (19 targets); `qa trial --llm-driver grok-cli` manager_evaluation started (record_friction; wall-timeout 180s EPIPE); MCP db status (project-local URL); status active_project; hm_visual_smoke (vision substitute). residual=0; wi_fleet **0.245≤floor**. Stamps qa trial/skill + status/db + component/property vision **USED@1017**. Explore **74/100**. Next: residual STALE thin or ordinary explore; self-audit ~1028; sweep ~1034.

> **Cycle 1016 (2026-07-19).** **example-apps** STALE-clear (journey@993 + story/rhythm/process/discovery@982 + deploy/test-design@985): journey residual=0 (12/12 ok); story list + scope-fidelity advisory; rhythm gaps advisory; discovery report; process propose (3 CRUD skipped); deploy plan + test-design coverage-actions. residual=0; wi_fleet **0.245≤floor**. Stamps journey/story/rhythm/discovery/process/deploy/test-design **USED@1016**. Explore **73/100**. Next STALE: qa trial@980 lag~36 or vision@981.

> **Cycle 1015 (2026-07-19).** **framework-ux/smells** STALE-clear (smells@974 lag~41): `dazzle fitness code` hotspot queue top30 (handlers_consolidated #1); complexity ratchet **6 pass**; bare-except gate **1 pass**; import contracts **1 pass**. residual=0; wi_fleet **0.245≤floor**. Stamps smells + fitness code **USED@1015**. Explore **72/100**. Next STALE: qa trial@980 lag~35 or journey@993 lag~22.

> **Cycle 1014 (2026-07-19) capability-sweep.** Inventory: MCP consolidated tools **38** (stable set; prior note 37); skills stable (dsl-authoring/phase-contract/qa-trial/spec-narrate/stems + agent skills); improve strategies/lanes unchanged; CLI groups present (demo quality/reset-and-load/prove/representation/scaffold). **No UNOWNED.** **WI** still owned under product_maturity (USED). STALE-effective @1014: **14** (highest: smells@974 lag40; qa trial@980 lag34; component/property vision + status/db@981 lag33; story/rhythm/process/discovery@982 lag32; deploy plan/test-design@985 lag29; journey@993 lag21). Re-stamp CodeQL + GitHub inbox + probes + product_maturity USED@1014. Next sweep ~**1034**. Next self-audit ~**1028** (last@1013). Explore **71/100**. residual=0; wi_fleet **0.245≤floor**.

> **Cycle 1013 (2026-07-19).** **self-audit** (cadence ≥15 since 998): window `8db899802..HEAD` (14 improve commits). Sampled top-5 by churn: **51645160d** prove/compliance STALE-clear CLEAN (prove story still 18/18 class; privacy on tree); **3cfad98a8** design_studio campaign/feedback desks + nav CLEAN (WI≈0.19 N=0); **f310bc63e** ops systems/alerts desks CLEAN (WI≈0.10 N=J=0); **0d4565f4c** acme curated nav CLEAN (N=0); **227bf7822** hr_records curated nav CLEAN (N=0). residual_total=0; wi_fleet **0.245≤floor**; maturity tests **10 pass**. **5 CLEAN / 0 DISCREPANCY**. End SHA post-stamp. budget_consumed 0. Explore **71/100**. Next: capability-sweep due@1013 (lag≥20 since 993); next self-audit ~**1028**.

> **Cycle 1012 (2026-07-19).** **example-apps** STALE-clear (demo quality/reset-and-load@979 lag~33): `demo quality` residual_total=0; demo_fleet_bar 9/9 ok; design_studio serve :3930 + `demo reset-and-load -y` **created_count=16**, persona_homes_residual=0, live_desk Brand×9 Asset×12 residual=0. residual=0; wi_fleet **0.245≤floor**. Stamps demo quality/reset-and-load/demo_fleet/product_quality **USED@1012**. Explore **71/100**. Next: self-audit (lag≥15 since 998 → due @1013) or capability-sweep (lag≥20 since 993 → due @1013).

> **Cycle 1011 (2026-07-19).** **test-suite** STALE-clear (sentinel mutate@978 lag~33): display_locale baseline **12 pass**; mutate **12 mutants, 58% kill** (min-kill 0) — 5 survivors (dataclass frozen/slots + 3 branch); support_tickets `sentinel scan` advisory findings (MT/PR/BL). residual=0; wi_fleet **0.245≤floor**. Stamps sentinel mutate/scan **USED@1011**. Explore **70/100**. Next: self-audit ~1013 (lag since 998); capability-sweep ~1013.

> **Cycle 1010 (2026-07-19).** **example-apps** STALE-clear (qa login+capture@977 lag~33): design_studio serve :3925 test-mode QA; magic-link login **designer** OK; capture **6** above-fold screens (studio_dashboard, asset_catalog, brand_desk, review_desk, campaign_desk, feedback_desk). residual=0; wi_fleet **0.245≤floor**. Stamps qa login/capture **USED@1010**. Explore **69/100**. Next STALE: sentinel mutate@978 lag~32; self-audit/sweep ~1013.

> **Cycle 1009 (2026-07-19).** **example-apps + xproject** STALE-clear (fuzz/xproject@976 lag~33): sibling validate AegisMark+cyfuture+pennydreadful exit 0; `dazzle sweep examples` exit 0 coverage **100%** (display 38/38, dsl 23/23); support_tickets boot-stderr sample no known-bug signatures (clean startup/shutdown). residual=0; wi_fleet **0.245≤floor**. Stamps fuzz/xproject/sweep/coverage **USED@1009**. Explore **68/100**. Next STALE: qa capture/login@977 lag~32 or sentinel mutate@978.

> **Cycle 1008 (2026-07-19).** **example-apps** STALE-clear (MCP cluster@975 lag~33): support_tickets MCP conformance summary **481** cases; dsl validate OK + lint 0 errors/17 warnings; policy analyze (User/SlaWaiver unprotected; 4 full coverage) + conflicts **0**; semantics extract + tenancy shared_schema configured; test_intelligence summary 0 runs. residual=0; wi_fleet **0.245≤floor**. Stamps MCP conformance/dsl/policy/semantics/test_intelligence + validate/lint **USED@1008**. Explore **67/100**. Next STALE: xproject/fuzz@976 lag~32 or qa capture@977.

> **Cycle 1007 (2026-07-19).** **framework-ux** STALE-clear (fitness/ux-verify@974 lag~33): support_tickets `ux verify --contracts --managed` **64/0/38**; fitness vitality (0 islets) + fitness code; composition audit **100/100**; rbac matrix OK; fragment-audit exit 0. residual=0; wi_fleet **0.245≤floor**. Stamps ux verify/fitness/composition/rbac/fragment-audit **USED@1007**. Explore **66/100**. Next STALE: MCP cluster@975 lag~32.

> **Cycle 1006 (2026-07-19).** **hm-convergence** STALE-clear (HM cluster@973 lag~33): gallery probes **6/6 PASS**; dual_lock queue **0**; shadcn gaps **0**; coherence queue=0 mean=8.7; zero-floor **GREEN** (tw=0 css=0); `hm_visual_smoke --dazzle-emit` taste substitute. residual=0; wi_fleet **0.245≤floor**. Stamps HM gallery/dual_lock/shadcn/coherence/zero-floor/visual_smoke + CodeQL/inbox/probes **USED@1006**. Explore **65/100**. Product STALE set largely cleared (next lag recompute at sweep ~1013).

> **Cycle 1005 (2026-07-19).** **example-apps** STALE-clear (prove/compliance@969 lag~36; representation/scaffold@970 lag~35; pulse@970): support_tickets `prove story` **18/18**, `prove representation` OK; `compliance gaps` 10 tier-3; `compliance privacy` regenerated; `representation patterns` OK; scaffold CLI present; `pulse radar` **68%**. residual=0; wi_fleet **0.245≤floor**. Stamps prove/compliance/representation/scaffold/pulse + CodeQL/inbox/probes **USED@1005**. Explore **64/100**. Remaining STALE: HM gallery/dual_lock/shadcn/zero-floor/coherence@973 lag~32.

> **Cycle 998 (2026-07-19).** **self-audit** (cadence ≥15 since 983): window `a47b1804d..HEAD` (13 improve commits). Sampled top-5 by churn: **752d6cb63** WI metric+acme invoices_home CLEAN; **a49a64301** invoice_ops suppliers/team desks+open-via CLEAN (G=0, ws=7); **448650d09** hr_records my_team/starters CLEAN; **0d13a38bb** platform-list exclusion + ST-013–018 binds CLEAN (G=0,J=0,bound 17/17; maturity tests 10 pass); **8e90e0584** project_tracker discussion/files desks CLEAN (G=0,ws=6). residual_total=0; wi_fleet≈0.334. **5 CLEAN / 0 DISCREPANCY**. End SHA post-stamp. budget_consumed 0. Explore **57/100**. Next self-audit ~**1013**. Next product feature_creep wi_next=acme_billing (N).

> **Cycle 993 (2026-07-19) capability-sweep.** Inventory: MCP still **37** tools; skills unchanged (dsl-authoring/phase-contract/qa-trial/spec-narrate/stems). CLI: `demo quality` / `reset-and-load` present. **New since last sweep:** continuous **Warehouse Index (WI)** on `example_product_maturity` (D/N/L/J/G, `--warehouse-index`, `wi_fleet`/`wi_next` in probes status) + example-apps feature_creep lane rule — owned by example-apps product_maturity (USED@993), **not UNOWNED**. Feature_creep shipped 987–992 (acme_billing/support_tickets/fieldtest_hub/llm_ticket_classifier/simple_task). STALE-effective @993: **10** (prove/compliance@969 lag24; pulse/representation/scaffold@970 lag23; HM gallery/dual_lock/shadcn/zero-floor/coherence@973 lag20). Re-stamp CodeQL + GitHub inbox + probes + maturity suite USED@993. Next sweep ~**1013**. Next self-audit ~**998** (last@983). Explore **53/100**. wi_fleet≈0.44 wi_next=hr_records (D).

> **Cycle 983 (2026-07-19).** **self-audit** (cadence ≥15 since 968): window `f0ae037f6..dce96082f`. 12 improve commits — all **capability-map only** (STALE-clear stamp campaign). Sampled re-verify NOW: gallery probes **6/6 PASS**, display_locale mutate **58% kill**, coverage 61/61, composition 100, trial report present, visual_smoke scores present, test_db_status 3 pass. Explore stamps scope-honest. **5 CLEAN / 0 DISCREPANCY**. End SHA (post-stamp). budget_consumed 0. Explore **44/100**. Next self-audit ~**998**.

> **Cycle 972 (2026-07-19) capability-sweep.** Inventory: CLI groups unchanged (representation/scaffold/prove/agent/demo quality/reset-and-load present); skills unchanged (dsl-authoring/phase-contract/qa-trial/spec-narrate/stems + agent skills); improve strategies/lanes unchanged; MCP still **37** tools. **No newly-built UNOWNED.** STALE recompute at @972: **25** STALE-effective (lag≥20) — highest lag HM gallery/vision @934 (38), ux verify/smells/fuzz @935 (37), MCP cluster @937 (35), qa capture/login @939, sentinel mutate/sweep @940, qa trial @941, demo maturity @943. Longstanding MCP surfaces not individually mapped (api_pack/e2e/guide/mock/param/perf/spec_analyze) remain covered under adjacent CLI/MCP rows; not flagged UNOWNED this cycle. Re-stamp **CodeQL + GitHub inbox + probes USED@972**. Next sweep ~**992**. Next self-audit ~**983** (last@968). Explore **34/100**.

> **Cycle 953 (2026-07-19).** **self-audit** (cadence ≥15 since 938): window `0daa756bb..bd3548fa2`. Sampled a53ab312a (qa DB pin) + 063e675ba (import hoist) + explore stamps 939/940/943/952. Tests **21 pass** (dotenv + deferred-import + display_locale). Module-top dotenv imports present; residual_total=0. Explore stamps scope-honest (capability-map only). **5 CLEAN / 0 DISCREPANCY**. End SHA `bd3548fa2`. budget_consumed 0. Explore **17/100**. Next self-audit ~**968**.

> **Cycle 952 (2026-07-19) capability-sweep.** Inventory: CLI groups unchanged (representation/scaffold/prove/agent/demo quality/reset-and-load present); skills unchanged (dsl-authoring/phase-contract/qa-trial/spec-narrate/stems + agent skills); improve strategies/lanes unchanged; MCP still **37** tools. **No newly-built UNOWNED.** STALE recompute at @952: **0** product STALE-effective (lag≥20) — recent STALE-clear 933–943 left map USED. Re-stamp **CodeQL + GitHub inbox USED@952**. Next sweep ~**972**. Next self-audit ~**953** (last@938). Explore **18/100**.

> **Cycle 943 (2026-07-19).** **example-apps** first-exercise OWNED-IDLE `dazzle demo reset-and-load` (#1627): design_studio serve :3930; reset-and-load **-y** exit 0 — created_count=16; persona_homes_residual=0 (admin/designer/reviewer); live_desk residual=0 (Brand×9, Asset×12). CI tip 063e675ba in_progress (preflight repair). Stamps **USED@943**. Explore **9/100**. Product STALE set cleared (only EXEMPT/idle remain).

> **Cycle 941 (2026-07-19).** **trials** STALE-clear `dazzle qa trial` @778: support_tickets `sla_waiver_already_signed` + grok-cli — seed **45/45** when DATABASE_URL correct; 2 friction (no auto-seed). **Product fix:** managed servers force project `.env` DATABASE_URL/REDIS_URL (`apply_project_infra_urls`) so multi-app shell pollution cannot pin trial to invoice_ops (missing User.role). trial-coverage static 19 targets. Stamps qa trial USED@941. Explore **8/100**.

> **Cycle 940 (2026-07-19).** **test-suite** STALE-clear `dazzle sentinel mutate` @786 lag~146: display_locale baseline 12 pass; mutate **12 mutants, 58% kill** (min-kill 0) — 5 survivors (dataclass frozen/slots + 3 branch mutants). CI in_progress (939). Stamps **USED@940**. Explore **7/100**. Remaining STALE: qa trial, qa-trial skill; OWNED-IDLE demo reset-and-load.

> **Cycle 939 (2026-07-19).** **example-apps** STALE-clear `qa login`+`qa capture` @787 lag~145: design_studio serve (dev+test mode :3920); magic-link login **designer** OK; capture **4** above-fold screens (studio_dashboard, asset_catalog, brand_desk, review_desk). CI in_progress (938). Stamps **USED@939**. Explore **6/100**. Remaining STALE: qa trial, sentinel mutate, qa-trial skill; OWNED-IDLE demo reset-and-load.

> **Cycle 938 (2026-07-19).** **self-audit** (cadence ≥15 since 923): window product sample post-923 — #1628 MCP multi-session, #1630 OR/cognition, #1626 queue/live_desk, CI repair 7ee087e8f. Tests **75 pass** (31+36+8). Artefacts on tree; residual_total=0. Explore stamp commits 933–937 scope-honest (capability-map only). **5 CLEAN / 0 DISCREPANCY**. End SHA `60e844567`. budget_consumed 0. Explore **5/100**. Next self-audit ~**953**.

> **Cycle 937 (2026-07-19).** **example-apps + xproject** STALE-clear (MCP cluster @787–790 lag~143–145; xproject@791): support_tickets MCP dsl validate+lint OK; conformance summary **481** cases; policy analyze (User/SlaWaiver unprotected; 4 full coverage) + conflicts 0; semantics extract + tenancy shared_schema configured; test_intelligence summary 0 runs; sibling validate cyfuture+AegisMark+pennydreadful exit 0 (Dazzle venv). CI in_progress (936). Stamps **USED@937**. Explore **5/100**. Remaining STALE: qa trial/login/capture, sentinel mutate, qa-trial skill.

> **Cycle 936 (2026-07-19).** **example-apps** STALE-clear (mid-band lag~140–147): support_tickets deploy plan (db+storage env list); test-design coverage-actions; compliance gaps 10 tier-3; scaffold CLI present; `sweep examples` exit 0 coverage 61/61; representation patterns + prove representation OK. sentinel mutate display_locale baseline-failed (not stamped). CI in_progress (935). Stamps **USED@936**. Explore **4/100**.

> **Cycle 935 (2026-07-19).** **framework-ux** STALE-clear (cluster @784 lag~148): support_tickets `ux verify --contracts --managed` **64/0/38** (seed 400 advisory User.role missing — non-strict); pulse radar **68%**; composition audit **100**; rbac matrix OK; fragment-audit exit 0; sentinel scan advisory findings; fitness code exit 0 (smells substitute). CI in_progress (934). Stamps **USED@935**. Explore **3/100**.

> **Cycle 934 (2026-07-19).** **hm-convergence** STALE-clear (cluster @782 lag~150): gallery probes **6/6 PASS**; dual_lock queue **0**; shadcn gaps **0**; coherence queue=0 mean=8.7; zero-floor **GREEN** (tw=0 css=0); `hm_visual_smoke --dazzle-emit` 11 parts (taste/component/property substitute); support_tickets `fitness vitality` exit 0. CI in_progress for 0a1a7d65b. Stamps HM cluster + fitness + driver gates **USED@934**. Explore **2/100**.

> **Cycle 933 (2026-07-19).** **example-apps** STALE-clear after explore budget reset (0→1): support_tickets `validate`+`lint` exit 0 (advisory warnings only), `story list`/`scope-fidelity` (20 advisory scope gaps), `coverage` **61/61**, `discovery report`, `rhythm gaps` advisory, `process propose` (3 CRUD skipped). shadcn gaps **0**. Residual still 0. Stamps validate/lint/story/coverage/discovery/rhythm/process + driver gates **USED@933**. Explore **1/100**.

> **Cycle 932 (2026-07-18) capability-sweep.** Inventory: CLI adds **`demo quality`**, **`demo reset-and-load`**; MCP still **37** tools including **`product_quality`** + **`status.demo_world`**. Flagged new rows; stamped **CodeQL + GitHub inbox + example probes + product/demo/journey maturity + product_quality/demo_world USED@932**. **No UNOWNED** (all new surfaces owned by example-apps / agent DX). STALE lag refresh @932. Next sweep ~**952**. Next self-audit ~**938** (last@923). Explore **100/100** (cap).

> **Cycle 912 (2026-07-18) capability-sweep.** Inventory: CLI groups unchanged (representation/scaffold/prove/agent present); skills unchanged; MCP **37**. **No newly-built UNOWNED.** STALE lag refresh @912. Re-stamp **CodeQL + GitHub inbox USED@912**. Next sweep ~**932**. Next self-audit ~**918** (last@903). Explore **100/100** (cap).

> **Cycle 892 (2026-07-18) capability-sweep.** Inventory: CLI groups unchanged (representation/scaffold/prove/agent present); skills unchanged; MCP **37**. **No newly-built UNOWNED.** STALE lag refresh @892. Re-stamp **CodeQL + GitHub inbox USED@892**. Next sweep ~**912**. Next self-audit ~**903** (last@888). Explore **100/100** (cap).

> **Cycle 872 (2026-07-18) capability-sweep.** Inventory: CLI groups unchanged (representation/scaffold/prove/agent present); skills unchanged; MCP **37**. **No newly-built UNOWNED.** STALE lag refresh @872. Re-stamp **CodeQL + GitHub inbox USED@872**. Next sweep ~**892**. Next self-audit ~**873** (last@858). Explore **100/100** (cap).

> **Cycle 852 (2026-07-18) capability-sweep.** Inventory: CLI groups unchanged (representation/scaffold/prove/agent present); skills unchanged; MCP **37**. **No newly-built UNOWNED.** STALE lag refresh @852 (product set still STALE). Re-stamp **CodeQL + GitHub inbox USED@852**. Next sweep ~**872**. Next self-audit ~**858** (last@843). Explore **100/100** (cap).

> **Cycle 832 (2026-07-18) capability-sweep.** Inventory: `dazzle --help` CLI groups unchanged vs 812 (representation/scaffold/prove/agent/…); skills unchanged (dsl-authoring/phase-contract/qa-trial/spec-narrate/stems). MCP tools still **37**. **No newly-built UNOWNED.** STALE recompute (lag≥20 @832): refresh lags on product STALE set from cycle-812 flip; scaffold@793, CodeQL/GitHub@812 also lag≥20 → STALE then re-stamp **CodeQL + GitHub inbox USED@832** (driver gates exercised every cycle). **already STALE:** qa-trial skill@488. Next sweep ~**852**. Next self-audit ~**843** (last@828). Explore **100/100** (cap — no product STALE-clear this cycle).

> **Cycle 812 (2026-07-18) capability-sweep.** Inventory: `dazzle --help` CLI groups (representation/scaffold/prove/agent/… unchanged set vs 792), MCP tools still **37** (representation present), skills unchanged (dsl-authoring/phase-contract/qa-trial/spec-narrate/stems + agent skills). **No newly-built UNOWNED.** STALE recompute (threshold ≤792 / lag≥20 @ cycle 812): **41 flips** USED→STALE-effective (incl. qa trial@778, hm-convergence cluster@782, framework-ux@784, example-apps mid-band 785–791, representation/prove@792). **already STALE:** qa-trial skill@488. Driver gates CodeQL+GitHub inbox exercised every cycle (not re-stamped as product). Next sweep ~**832**. Next self-audit ~**813** (last@798). Explore **100/100** (cap — no product explore this cycle).

> **Cycle 793 (2026-07-18).** **example-apps** first-exercise **UNOWNED scaffold**: service/process-step/story all OK; fixed absolute `--output` crash (`_display_path` + absolute out dir). Stamps scaffold **USED@793**. Explore **100/100**.

> **Cycle 792 (2026-07-18) capability-sweep.** Inventory: CLI groups (representation/scaffold/prove/…), MCP tools **37** (+1 `representation` vs 36@772), skills unchanged (dsl-authoring/phase-contract/qa-trial/spec-narrate/stems + agent skills). **New registry rows:** representation CLI+MCP + prove → USED@792 (first-exercise support_tickets patterns/classify + prove representation OK); scaffold → **UNOWNED**. STALE recompute: **0 new USED→STALE** (max product lag qa trial@778 = 14); **already STALE:** qa-trial skill@488. Next sweep ~**812**. Next self-audit ~**798**. Explore **99/100**.

> **Cycle 791 (2026-07-18).** **/xproject** lag-14: sibling validate cyfuture+AegisMark exit 0 (advisory surface gaps); pennydreadful parse fail #1559 → fixed actor→persona + scope→entities (16 stories); re-validate exit 0. Stamps @791. Explore **98/100**.

> **Cycle 790 (2026-07-18).** **test-suite** lag-13 MCP test_intelligence@777: KG init on support_tickets; summary/coverage/failures/regression/context all OK (0 runs — empty history). Stamps @790. Explore **97/100**.

> **Cycle 789 (2026-07-18).** **example-apps** lag-12 compliance/semantics: support_tickets compliance gaps (10 tier-3) + compile 29% coverage; MCP semantics extract/tenancy (shared_schema configured)/compliance (PII fields). Stamps @789. Explore **96/100**.

> **Cycle 788 (2026-07-18).** **framework-ux** lag-11 fitness/policy cluster: fitness vitality + code hotspots; MCP policy analyze (3 platform entities missing create/update/delete permits; 7/10 full coverage), conflicts 0, coverage matrix. Stamps @788. Explore **95/100**.

> **Cycle 787 (2026-07-18).** **example-apps**: MCP dsl validate+lint + conformance summary (411 cases, 0 gaps) on design_studio; qa login designer + capture 2 screens. **Product fix:** UX seed `*_color` fields emit #RRGGBB (Brand str(7) validation). Stamps @787. Explore **94/100**.

> **Cycle 786 (2026-07-18).** **test-suite** lag-15 `dazzle sweep`@771: `sweep examples` exit 0, coverage 61/61; `sentinel mutate` display_locale 12 mutants kill **58%** (min-kill 0). Stamps @786. Explore **93/100**.

> **Cycle 785 (2026-07-18).** **example-apps** lag-13/14 Tier-1 QI: support_tickets validate+lint; story scope-fidelity (20 advisory scope gaps); rhythm gaps advisory; test-design coverage-actions; discovery report; process propose (3 skipped CRUD); deploy plan env list; coverage **61/61**. No hard PENDING rows. Stamps @785. Explore **92/100**.

> **Cycle 784 (2026-07-18).** **framework-ux** lag-15 cluster: sentinel scan (support_tickets findings AA/MT/PR/BL advisory); fitness code hotspots; /smells via fitness; /fuzz via managed contracts 64/0/38; pulse radar 68%; composition audit design_studio **100**; rbac matrix; fragment-audit support_tickets exit 0. Stamps @784. Explore **91/100**.

> **Cycle 783 (2026-07-18).** **self-audit** (15 cycles since 768): window `48de8593f..7bcd5e615`; sampled 5 product fixes — all **CLEAN**. No REGRESSION/AUD rows. Explore **90/100** (budget 0). Next self-audit ~**798**.

> **Cycle 782 (2026-07-18).** **hm-convergence** directed explore (oldest last_run@775): zero-floor green (tw=0 css=0); dual_lock queue 0; shadcn gaps 0; coherence queue=0 mean=8.7; gallery probes **6/6**; `hm_visual_smoke --dazzle-emit` 11 parts (incl. dazzle-master-detail); reservoir+delegation unit **13 pass**. Stamps @782. Explore **90/100**.

> **Cycle 781 (2026-07-18).** Preflight red: `_check_workspace` CC 18>15 from cycle-780 master-detail region fix. Refactored into `_region_tokens` / `_regions_from_tag_attrs` / `_regions_from_layout_html`. preflight-surface + contract_checker tests green. Stamps ux verify + inbox/codeql @781. Explore **89/100** (budget 0 — preflight repair).

> **Cycle 780 (2026-07-18).** **ux-converge** explore (oldest last_run): fleet sample simple_task/support_tickets/design_studio/project_tracker/fieldtest_hub **0 failed**; contact_manager 2→0 after contract_checker master-detail region recognition. Stamps ux verify @780. Explore **89/100**.

> **Cycle 779 (2026-07-18).** **consumer-issues / owner_bug #1624** Tier-1 fix: STATIC_LIST without-replacement within generate_entity; support_tickets ticket_number strategy sequential. Unit test + regenerate 20 unique TKTs. Explore **87/100** (budget 0 for triage-fix? implemented → 1). Stamps inbox/codeql @779.

> **Cycle 778 (2026-07-18).** STALE-effective `dazzle qa trial`@758 lag20. Ran support_tickets `sla_waiver_already_signed` --fresh-db --llm-driver grok-cli: functional signing **pass**, agent praise (already-signed + Download CTA); seed 3× ticket_number conflict → **FILED #1624** (TR-48 seen=3). Stamps @778. Explore **87/100**.

> **Cycle 777 (2026-07-18).** lag-10 cluster: coverage 61/61; compliance gaps; fitness code+vitality; MCP policy/semantics/ti; xproject sibling validates. qa trial designer_portfolio started (grok-cli) but no new report within budget — leave @758. Stamps @777. Explore **86/100**. Release v0.105.11 green.

> **Cycle 776 (2026-07-18).** design_studio: serve + `qa login designer` magic-link; `qa capture` 2 screens (studio_dashboard + asset_gallery designer desktop light) exit 0. `sentinel mutate` display_locale: 12 mutants, 0% kill (min-kill 0 exercise). v0.105.11 still latest green release. Stamps @776. Explore **85/100**.

> **Cycle 775 (2026-07-18).** **v0.105.11 CI green** (29619812712). Local: date-fix re-pin 23 pass; dual_lock 0; shadcn 0; gallery 6/6; zero-floor filter 20 pass; design_studio validate+lint; MCP dsl/conformance. Stamps @775. Explore **84/100**.

> **Cycle 772 (2026-07-17) capability-sweep.** Inventory: CLI groups, MCP tools **36** (unchanged set vs 752), skills (dsl-authoring/phase-contract/qa-trial/spec-narrate/stems + agent skills), improve lanes/strategies **unchanged**. **No newly-built UNOWNED** in registry. STALE recompute (threshold ≤752): **0 flips** USED→STALE — all product USED last-exercised ≥758 (max lag 14 on `qa trial`). **already STALE:** `qa-trial` skill@488 (skip until LLM trial healthy). Exercised mid-lag: discovery **95**, pulse radar 66%, deploy plan, process propose, fragment-audit all ✓, test-design coverage-actions, taste/component substitute visual_smoke. Re-ran cancelled v0.105.10 CI. Explore **83/100**. Next sweep ~**792**. Next self-audit ~**783** (last@768).

> **Cycle 771 (2026-07-17) STALE-clear.** sweep examples exit 0 (coverage 100%); gallery probes 6/6; dual_lock queue 0; shadcn gaps 0; zero-floor unit filter 11 pass; design_studio composition 100, rbac matrix, story list 6 accepted, rhythm gaps advisory. Stamped @771. Explore **82/100**. v0.105.10 CI in_progress.

> **Cycle 770 (2026-07-17) product.** UX seed FK parents without surfaces — design_studio Feedback.reviewer; **v0.105.10**. Explore **81/100**.

> **Cycle 769 (2026-07-17) STALE-clear.** /fuzz via managed contracts boot: support_tickets 64/0/38, design_studio 41/0/32, simple_task 39/0/24 (seed 400s advisory only). /smells via fitness code hotspots. property-vision substitute hm_visual_smoke --dazzle-emit (11 parts). coherence queue=0 mean=8.7. Stamped fuzz/smells/property-vision/coherence/ux-verify **USED@769**. Explore **80/100**. Tip CI **green** (767).

> **Cycle 767 (2026-07-17) multi STALE-clear.** design_studio MCP dsl validate/lint/fidelity/brief; policy analyze/conflicts/coverage; conformance summary/gaps; semantics extract/tenancy/compliance; test_intelligence (KG init, empty runs OK); compliance gaps+compile; fitness code+vitality; coverage 61/61; sibling validate cyfuture+AegisMark+pennydreadful. Stamped MCP cluster + compliance + fitness + xproject **USED@767**. Explore **79/100**.

> **Cycle 752 (2026-07-16) capability-sweep.** Inventory: CLI/skills/commands/strategies
> **unchanged** vs 731. **No newly-built UNOWNED.** Preflight green after month_anchor
> baseline repair. **STALE recompute (threshold ≤732):** **1 flips** USED→STALE.
> **already STALE:** qa-trial skill@488. Prefer product STALE if any remain after flips;
> skip qa-trial until LLM driver healthy. Explore **69/100**. Next sweep ~**772**.
> Next self-audit ~**753** (last@738).

> **Cycle 747 (2026-07-16) hm-convergence + framework-ux STALE-clear.** property-vision:
> support_tickets landing capture (Playwright); subscription host-Read mean **7.8**
> (stripe-family SaaS; no metered API). fitness code exit 0; coherence queue=0 mean=8.7;
> smells via fitness code. Stamped property-vision, hyperpart coherence, /smells
> **USED@747**. Explore **69/100**.

> **Cycle 746 (2026-07-16) multi STALE-clear.** /fuzz support_tickets boot scrape
> HTTP 200 clean; /xproject validate cyfuture+AegisMark+pennydreadful exit 0;
> ux verify --structural inventory 341; shadcn gaps **0**; dual_lock queue **[]**.
> Stamped fuzz, xproject, ux verify, shadcn, dual_lock **USED@746**. Explore **68/100**.

> **Cycle 745 (2026-07-16) example-apps + framework-ux STALE-clear.** support_tickets:
> process propose 0; compliance gaps (10 tier-3); deploy plan 0; test-design
> coverage-actions 0; sentinel scan 0. Stamped process, compliance, deploy plan,
> test-design, sentinel scan **USED@745**. Explore **67/100**.

> **Cycle 744 (2026-07-16) example-apps + framework-ux STALE-clear.** support_tickets:
> validate+lint 0; story list; conformance summary; coverage **61/61**; discovery report;
> composition audit **100**; pulse radar **68%**; fragment-audit 0; rhythm gaps advisory;
> rbac matrix 0; fitness vitality 0. Stamped validate/lint, story, conformance, coverage,
> discovery, composition, pulse, fragment-audit, rhythm, rbac, fitness **USED@744**.
> Explore **66/100**.

> **Cycle 743 (2026-07-16) hm-convergence STALE-clear gallery probes.** Discover
> multi-details 3/3 catalog_ok. Run **6/6 PASS** (menubar/nav/accordion exclusive;
> tree multi_open; menubar/nav dismiss). Stamped gallery probes **USED@743**.
> Explore **65/100**.

> **Cycle 742 (2026-07-16) hm-convergence STALE-clear (taste/component vision).**
> `hm_visual_smoke --dazzle-emit` PASS; subscription host-Read scores mean **7.4**
> (billing=subscription-host-read; ship_gate=false). Stamped taste-panel +
> component-vision **USED@742**. CI repair HEAD `2a34139a0` still in_progress;
> local catalogue+HM gate tests green. Explore **64/100**.

> **Cycle 741 (2026-07-16) test-suite STALE-clear.** `dazzle sentinel mutate
> --suite security` **PASS** — all 5 modules ≥ floor (crypto 83%, rbac 71%,
> csrf 85%, rls 100%, predicate 77%) with DATABASE_URL. Stamped sentinel mutate
> **USED@741**. Explore **63/100**.

> **Cycle 740 (2026-07-16) test-suite + hm-convergence STALE-clear.** KG init +
> MCP test_intelligence summary/failures/regression/coverage/context (empty runs OK);
> journey no sessions. `dazzle sweep examples` exit 0 (38/38 display modes). HM
> zero-floor GREEN (0/0) + reservoir unit tests 11 pass. Stamped test_intelligence
> + sweep + zero-floor **USED@740**. Explore **62/100**.

> **Cycle 739 (2026-07-16) example-apps + framework-ux STALE-clear.** support_tickets
> `validate`+`lint` exit 0; `story list`; `rbac matrix` exit 0; fieldtest_hub validate 0;
> CodeQL poll 0 open. TR-35 → FIXED-VERIFY (device_attention queue). Stamped MCP dsl +
> policy + CodeQL **USED@739**. Explore **61/100**.

> **Cycle 731 (2026-07-16) capability-sweep.** Inventory: CLI/skills/strategies unchanged;
> toast dual-lock (288d17c51) rides hm-convergence dual_lock + fleet host (not a new UNOWNED row).
> **STALE recompute (threshold ≤711):** **23 flips** USED→STALE.
> **already STALE:** 1 (`qa-trial` skill@488 lag 243).
> **still USED:** 16 (hottest rbac/fitness/sentinel@730 … deploy plan@728 …).
> Prefer highest-lag product STALE (conformance@697 lag 34; pulse/composition/rhythm@700 lag 31).
> Explore **55/100**. Next sweep ~**751**.

> **Cycle 715 (2026-07-15) trials STALE-clear.** support_tickets `manager_evaluation` via `--llm-driver grok-cli` (subscription). Fixed grok-cli max_turns default 4→20 (agent 32) — was false-blocking trials after cycle 666. Trial complete: 1 friction (med confusion, agent_dashboard timeline-first). Stamped qa trial **USED@715**.
> **Cycle 714 (2026-07-15) test-suite STALE-clear.** `dazzle sentinel mutate --suite security` **PASS** — all 5 modules ≥ floor (crypto 83%, rbac 71%, csrf 85%, rls 100%, predicate 77%). Stamped sentinel mutate **USED@714**.
> **Cycle 713 (2026-07-15) hm-convergence property-vision STALE-clear.** support_tickets sitespec landing capture; subscription host-Read mean **7.6** (family stripe-like SaaS; no metered property-vision). Stamped property-vision **USED@713**.
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
