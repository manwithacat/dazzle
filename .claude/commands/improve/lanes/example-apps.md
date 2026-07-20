# Lane: example-apps

Find a gap in an example app, fix it, verify, commit, move on. Adapted from former /improve.

## Targets

DSL gaps in `examples/*/`: validation errors, lint violations, conformance gaps,
fidelity gaps, **product maturity**, **demo fleet (#1626)**, journey maturity,
visual quality findings. **Not** framework code — that's `framework-ux`
(except when a demo_fleet residual is clearly a framework bug — file issue /
hand off).

## State

- **Backlog section:** `## Lane: example-apps` in `dev_docs/improve-backlog.md`
- **Backlog row format:** `| # | App | Gap Type | Description | Status | Attempts | Notes |`

## Signals

| Direction | Kind | Notes |
|-----------|------|-------|
| Emit | `app-fixed` | Payload `{app, gap_type, commit}` — triggers framework-ux re-walk if contract relates |
| Consume | `ux-component-shipped` | Re-verify apps using that component |
| Consume | `convergence-clean` | Clear stale rows for that app |
| Consume | `dazzle-updated` / `fix-deployed` | Re-scan affected apps; re-run example probes |

## actionable_count

Rows in `## Lane: example-apps` with status ∈ {`PENDING`, `IN_PROGRESS`}
**plus** non-zero residual from:

```bash
python scripts/improve_example_probes.py --status
# product_maturity residual=N
# demo_fleet residual=N
# journey_maturity residual=N
```

Probe residual alone is enough to pick this lane even if the markdown backlog
table is empty (agent-first loop).

## HM surface gate (fleet)

Example apps are **HM-owned surfaces**: pages compose Hyperparts (ADR-0053). Live
`dazzle build-ui` / serve emit pure `dz-*` / `data-dz-*` markup. Pre-HM residuals
(Alpine `x-*`, dead Tailwind `opacity-25/75`) in a local `examples/*/dnr-ui/` tree
are almost always a **stale preview**, not a live emit bug — those dirs are
gitignored and must not be grepped as truth.

**Machine check (rebuild + score):**

```bash
python scripts/example_hm_surface_audit.py          # rebuild all → .dazzle/example-hm-audit/
python scripts/example_hm_surface_audit.py --status # one-line for cycle logs
python scripts/example_hm_surface_audit.py --app simple_task --json
```

- Exit 0 + `HM_OK` for every app → surface is improve-accessible (contracts,
  dual-lock, visual_tier2, ux verify all see the same substrate).
- Exit 1 / `FAIL` with `alpine>0` or `tw>0` → **framework residual** (file under
  `framework-ux` / `hm-convergence`, not a per-app DSL gap) unless the hits are
  project-authored custom HTML outside the emitter.
- `BUILD_ERROR` → validate/lint the app first (Tier 1).

When a trial/visual finding says "Alpine residual" or "non-HM markup", re-run the
audit on a **fresh** rebuild before filing an example-apps row. Stale `dnr-ui/`
snapshots are not gaps.

## Force sub-strategies

| Arguments | Playbook |
|-----------|----------|
| `example-apps product_maturity` | `improve/strategies/product_maturity.md` |
| `example-apps demo_fleet` | `improve/strategies/demo_fleet.md` |
| `example-apps journey_dogfood` | `improve/strategies/journey_dogfood.md` |
| `example-apps story_walk` | `improve/strategies/story_walk.md` |
| `example-apps agent_acceptance_panel` | `improve/strategies/agent_acceptance_panel.md` |

## Playbook

### 1. OBSERVE

**Always start with the unified probe suite** (cheap, deterministic):

```bash
python scripts/improve_example_probes.py --status
# product_maturity … residual=… next=…
# demo_fleet … residual=… next=…
# journey_maturity … residual=… next=…
# story_walk … residual=… next=…          # landing stories ↔ scene walks
# trial_verdict … residual=… next=…       # last qa-trial recommend / missing panel
# example_probes residual_total=… next=… force=example-apps <strategy>
# (force= only when residual_total>0 — use that strategy this cycle)
```

Read backlog section. **First, prune stale findings** (see Stale-finding TTL under Hard rules): delete any `PENDING` `visual_quality` row with `seen=1` whose `ts=` is older than **14 days**. Don't action them and don't carry them — the next Tier-2 scrape re-discovers anything still extant with a fresh `ts`/`seen`. Never prune rows that track a filed issue (`FILED→#…`) or a shipped fix (`RESOLVED→#…`), and never prune reinforced rows (`seen≥2` — repeated observation is signal). Note the prune count in the cycle log.

Then selection priority:
1. `IN_PROGRESS` with attempts < 3 → resume it
2. `IN_PROGRESS` with attempts ≥ 3 → mark `BLOCKED`, file issue if framework-related, pick next `PENDING`
3. **`product_maturity` residual** — `python scripts/example_product_maturity.py --next` non-empty → force strategy `product_maturity` for that app (playbook `improve/strategies/product_maturity.md`). Prefer over demo/journey/Tier-1.
4. **`demo_fleet` residual (#1626)** — product residual empty and `python scripts/demo_fleet_bar.py --next` non-empty → force strategy `demo_fleet`. If probe residual empty but #1626 still has open P0-5…P0-9 (empty heroes, invoice queues, design_studio visuals), still pick `demo_fleet` and work the highest open P0.
5. **`journey_maturity` residual** — `python scripts/example_journey_maturity.py --next` non-empty → force `journey_dogfood`.
6. **`story_walk` residual** — landing stories without scene walks (`python scripts/story_walk_bar.py --next`) → force `story_walk` (playbook `improve/strategies/story_walk.md`). Prefer over densify / STALE; this is **direct interaction** residual.
7. **`trial_verdict` residual** — `python scripts/trial_verdict_bar.py --next` non-empty (missing/failed panel) → force `agent_acceptance_panel`.
8. **Warehouse Index (WI) feature_creep** — all probe residuals empty **and** `densify_allowed=1` (`wi_fleet > wi_floor`; see status `densify_allowed=` / `--warehouse-index`): minimize continuous warehouse-ness on `wi_next` by shipping a **job-backed** product DSL slice that moves `wi_primary` (D/N/L/J/G). Map-only commits do **not** count. **Hard stop (#1637):** when `densify_allowed=0`, skip this step entirely — do **not** add isomorphic `*_ops` filter desks, do not "skip soft-cap" densify, do not grind D under floor.
9. **Agent acceptance panel** (when residual_total=0 and densify closed, or force path): run `improve/strategies/agent_acceptance_panel.md` — multi-agent UAT against stories / adoption criteria (agent-first substitute for a human QA panel). Prefer over pure STALE re-touch when felt quality is stale.
10. All probe residuals empty, `densify_allowed=0`, and backlog gaps DONE/BLOCKED → **explore phase** (lane Step 6 / driver Rule 7 COGNITION → HYGIENE)
11. Else pick next `PENDING` backlog row (priority: critical > warning > info, then app alphabetical)
12. Mark chosen work `IN_PROGRESS`

If `$ARGUMENTS` provided as `<app>`, filter to that app only.
If `$ARGUMENTS` is `product_maturity` | `demo_fleet` | `journey_dogfood` | `story_walk` | `agent_acceptance_panel` (or lane+strategy), run that strategy playbook for one residual app and skip unrelated gap types.

### 2. ENHANCE

Apply the fix appropriate to the gap type:

| Gap type | Action |
|----------|--------|
| `lint` | Edit DSL to satisfy lint rule (add search_fields, persona, scope, etc.) |
| `scope` | Convert `permit:` to `permit:` + `scope:` per ADR-0010 predicate algebra |
| `validation` | Edit DSL to satisfy parser/validator |
| `conformance` | Add missing entity/surface/workspace per `mcp__dazzle__conformance` |
| `fidelity` | Add missing IR-graph edges per `mcp__dazzle__dsl operation=fidelity` |
| `product_maturity` | Full playbook: `improve/strategies/product_maturity.md`. Probe: `scripts/example_product_maturity.py`. Do **not** add entity lists to “pass”. |
| `demo_fleet` | Full playbook: `improve/strategies/demo_fleet.md`. Probe: `scripts/demo_fleet_bar.py` + #1626. Seeds/stills/honesty; one P0 or one app per cycle. |
| `journey_maturity` | Full playbook: `improve/strategies/journey_dogfood.md`. Force: `/improve example-apps journey_dogfood`. |
| `story_walk` | Full playbook: `improve/strategies/story_walk.md`. Probe: `scripts/story_walk_bar.py`. Landing stories ↔ scene walks; stubs + dry-run/live walk. |
| `agent_acceptance` | Full playbook: `improve/strategies/agent_acceptance_panel.md`. Also from `trial_verdict` residual (`scripts/trial_verdict_bar.py`). |
| `rhythm_fidelity` | A rhythm scores `< 1.0` (a scene's surface/action/entity can't resolve) — add the missing surface/derive-binding, or fix the cited story's `entities`/`trigger`. **Only non-advisory `evaluate` failures are actionable** (advisory `surface_specialization` + orphan-story gaps are design nudges, not defects). |
| `story_scope` | `dazzle story scope-fidelity` reports a story with `< full` process coverage (story⇄process axis) — add/point the implementing process. Distinct from `rhythm_fidelity` (story⇄rhythm axis). |
| `test_design_coverage` | `dazzle test-design coverage-actions` / `runtime-gaps` flags an uncovered persona action — add the test-design coverage row. |
| `discovery_coherence` | `mcp__dazzle__discovery operation=coherence` flags an incoherent spec edge — reconcile the DSL. |
| `visual_quality` | Implement design-system fix per the Tier-2 visual scrape (`dazzle qa capture` + the visual_tier2 subagent) finding |

For framework-related gaps (e.g. lint flagging an auto-generated entity), file a GitHub issue and mark `BLOCKED`.

### 3. BUILD

```bash
cd examples/<app> && dazzle validate && dazzle lint
```

If errors → fix and retry (up to 3 attempts).

### 4. VERIFY

Always:

```bash
cd examples/<app> && dazzle validate
```

By gap type, also:

| Gap type | Extra gate (must exit 0 / residual clear) |
|----------|-------------------------------------------|
| `product_maturity` | `python scripts/example_product_maturity.py --app <app>` (no residual reasons) |
| `demo_fleet` | `python scripts/demo_fleet_bar.py --app <app>`; still evidence if P0-6/9 |
| `journey_maturity` | `python scripts/example_journey_maturity.py --app <app> --min-bound 3` |
| `visual_quality` | optional re-capture + category re-check |
| default | `dazzle ux verify --contracts 2>&1 \| tail -20` |

Fleet smoke after product/demo/journey work:

```bash
python scripts/improve_example_probes.py --status
```

### 5. REPORT (lane-internal)

1. Update row in lane backlog: `IN_PROGRESS` → `DONE` (or `BLOCKED` after 3 attempts)
2. Note commit SHA in row's notes
3. Return outcome: `{status: PASS|FAIL|BLOCKED, summary, signals_to_emit: [{kind: "app-fixed", payload: {app, gap_type, commit}}], budget_consumed: 0}`

### 6. EXPLORE / TIERED GAP DISCOVERY (when backlog clean **and** probe residual_total=0)

Tiered to manage cost — start free, escalate only when the previous tier is exhausted.

#### Tier 0 (when HM purity is in doubt, free-ish): HM surface audit

```bash
python scripts/example_hm_surface_audit.py --status
# or per-app:
python scripts/example_hm_surface_audit.py --app <app>
```

If the fleet is `HM_OK`, skip residual-markup investigations and go to Tier 0.4.
If `FAIL`, treat as framework residual unless custom project HTML is the source
(see **HM surface gate** above). Do **not** open `visual_quality` rows for stale
`dnr-ui/` Alpine — delete the local tree or rebuild; `examples/*/dnr-ui/` is gitignored.

#### Tier 0.4 (every cycle, free): Product maturity probe

```bash
python scripts/example_product_maturity.py --status
python scripts/example_product_maturity.py --next
python scripts/example_product_maturity.py --warehouse-index   # continuous WI (minimize wi_next)
python scripts/example_product_maturity.py --next-wi
```

If `next` non-empty, open/refresh `product_maturity` backlog row and **prefer
strategy product_maturity on next OBSERVE**. One app per cycle.

#### Tier 0.45 (every cycle when product residual empty, free): Demo fleet probe

```bash
python scripts/demo_fleet_bar.py --status
python scripts/demo_fleet_bar.py --next
# if residual empty, still check open #1626 P0-5…9:
#   gh issue view 1626 --json body -q .body | head -40
```

If residual or open antagonist P0s, open/refresh `demo_fleet` row and prefer
strategy `demo_fleet`.

#### Tier 0.5 (every cycle when product+demo residual empty, free): Journey maturity

```bash
python scripts/example_journey_maturity.py --status
python scripts/example_journey_maturity.py --next
```

If `next` is non-empty, open/refresh a `journey_maturity` backlog row for that
app (`PENDING`) and **prefer it on the next OBSERVE**. Do not batch-fix the
whole residual list in one cycle — one app per cycle via
`improve/strategies/journey_dogfood.md`. When residual is empty, note
`journey_maturity: fleet ok` in the cycle log and continue Tier 1.

#### Tier 1 (every cycle, free): Re-scan DSL gaps

For each example app (all deterministic, JSON, near-free — the same shape):
```bash
cd examples/<app>
dazzle validate 2>&1
dazzle lint 2>&1
mcp__dazzle__conformance operation=summary
mcp__dazzle__dsl operation=fidelity
# quality-intelligence sweep (wired from capability-map, Phase 4):
dazzle story scope-fidelity --json                 # story⇄process axis → story_scope gaps
dazzle test-design coverage-actions 2>&1           # → test_design_coverage gaps
mcp__dazzle__discovery operation=coherence          # → discovery_coherence gaps
# rhythm sweep — ONLY if the app declares a rhythm (grep '^rhythm ' dsl/):
#   NB: every `dazzle rhythm …` invocation prints DEBUG lines before the payload — always --json | grep -v DEBUG
for r in <rhythm-names>; do dazzle rhythm fidelity "$r" --json | grep -v DEBUG; done
dazzle rhythm gaps --json | grep -v DEBUG           # project-wide, once per app
```

**Actionability filter for the quality-intelligence rows:** treat only *hard* failures
as gaps — a `rhythm evaluate` check with `pass:false AND advisory:false`, a rhythm
`fidelity < 1.0`, a story below `full` process coverage. Advisory-severity output
(`surface_specialization`, orphan-story `rhythm gaps`, coherence nudges) is a design
hint, NOT a defect — prune it like `visual_quality` single-observations rather than
inflating `actionable_count`. As of 2026-07-08 only `support_tickets` (`agent_daily`)
and `fieldtest_hub` (3 rhythms) carry rhythms, all at fidelity 1.0.

Add new rows to backlog as `PENDING`. Increments shared budget by 1. Stamp
`last-exercised` for the capabilities run this cycle in `improve/capability-map.md`
(driver Step 3).

#### Tier 2 (when Tier 1 exhausted, medium cost): Visual quality

Runs as a host-harness subagent (subagent-dispatch) — no direct API call, no API token spend; cognitive work bills to the harness subscription. See `improve/strategies/visual_tier2_subagent.md` for the full numbered playbook.

In short: `dazzle qa capture --manifest <path>` writes a fleet-wide JSON manifest of screenshots; `dazzle.qa.evaluate.build_subagent_prompt(...)` builds a multi-screen mission; the subagent Reads each PNG, evaluates against `dazzle.qa.categories.CATEGORIES`, and writes findings JSON; `dazzle.cli.runtime_impl.ux_cycle_impl.visual_tier2_ingest.ingest_visual_findings(...)` writes new `visual_quality` rows into this lane's section of the backlog (dedup by `(app, category, location)`, severity-sorted, `seen=K` reinforced on re-runs).

**Prerequisite for capture plans:** product personas only (not field archetypes) —
`dazzle.qa.capture.build_capture_plan` (#1626). Prefer seeded apps so happy-path
stills are non-empty.

Row shape: `| N | <app> | visual_quality | [<category>] <description> at <location> | PENDING | 0 | seen=1, screenshot=<path>, ts=<...> |`.

Increments shared budget by 5 (single heavy dispatch, ~25-50 screens).

#### Tier 3 (when Tier 2 exhausted, high cost): LLM cross-app review

Pick one app, run a review subagent that compares its DSL against patterns from a reference app (e.g. `support_tickets` vs `simple_task`). Surface gaps the static lints don't catch (missing rhythms, weak personas, no test_design coverage).

Increments shared budget by 5 (significantly more expensive).

## Hard rules

- **One gap per cycle.** Don't chain.
- **Three attempts then BLOCKED.** Never let a gap run forever.
- **Framework-related gaps file issues, don't fix.** This lane targets app DSL only — framework fixes belong in `framework-ux` or /issues.
- **Probe residual outranks all STALE / WI polish.** Never burn a cycle on lint field completeness or WI D diversify when `improve_example_probes.py` reports residual_total>0.
- **COGNITION STALE outranks WI D when residual=0 and wi_fleet ≤ floor.** Prefer domain / demo_world / product_quality / reset-and-load / qa-adjacent digs over warehouse-index diversify. WI D is optional polish under floor, not the default explore filler.
- **HYGIENE STALE is cheap re-touch** (validate/prove/coverage) — do not present it as agent-cognition progress.
- **Do not tick #1626 without still/probe evidence.**
- **Stale-finding TTL.** `visual_quality` rows come from Tier-2 `dazzle qa capture` scrapes (Step 6, via the visual_tier2 subagent). A single-observation row (`seen=1`) that stays `PENDING` longer than **14 days** ages out behind framework releases — by pickup time the issue is often already fixed, so it inflates `actionable_count`, mis-biases lane selection, and wastes investigation re-confirming non-issues. **Delete such rows in OBSERVE rather than carrying them**; the next Tier-2 scrape re-discovers anything still extant with a fresh `ts`/`seen` (cheap by design). Exceptions that are NEVER pruned on age: rows linked to a filed issue (`FILED→#…`), rows recording a shipped fix (`RESOLVED→#…`), and reinforced rows (`seen≥2`, where repeated observation across scrapes is signal). Validated by cycle 157 (2026-05-29): rows 103/106 sat `PENDING` 14 days, then proved stale — the empty list-region empty-state had since been wired (confirmed by direct `ListRegion` render at v0.80.27).
