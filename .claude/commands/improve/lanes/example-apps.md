# Lane: example-apps

Find a gap in an example app, fix it, verify, commit, move on. Adapted from former /improve.

## Targets

DSL gaps in `examples/*/`: validation errors, lint violations, conformance gaps, fidelity gaps, visual quality findings. **Not** framework code — that's `framework-ux`.

## State

- **Backlog section:** `## Lane: example-apps` in `dev_docs/improve-backlog.md`
- **Backlog row format:** `| # | App | Gap Type | Description | Status | Attempts | Notes |`

## Signals

| Direction | Kind | Notes |
|-----------|------|-------|
| Emit | `app-fixed` | Payload `{app, gap_type, commit}` — triggers framework-ux re-walk if contract relates |
| Consume | `ux-component-shipped` | Re-verify apps using that component |
| Consume | `convergence-clean` | Clear stale rows for that app |
| Consume | `dazzle-updated` / `fix-deployed` | Re-scan affected apps |

## actionable_count

Rows in `## Lane: example-apps` with status ∈ {`PENDING`, `IN_PROGRESS`}.

## Playbook

### 1. OBSERVE

Read backlog section. **First, prune stale findings** (see Stale-finding TTL under Hard rules): delete any `PENDING` `visual_quality` row with `seen=1` whose `ts=` is older than **14 days**. Don't action them and don't carry them — the next Tier-2 scrape re-discovers anything still extant with a fresh `ts`/`seen`. Never prune rows that track a filed issue (`FILED→#…`) or a shipped fix (`RESOLVED→#…`), and never prune reinforced rows (`seen≥2` — repeated observation is signal). Note the prune count in the cycle log.

Then selection priority:
1. `IN_PROGRESS` with attempts < 3 → resume it
2. `IN_PROGRESS` with attempts ≥ 3 → mark `BLOCKED`, file issue if framework-related, pick next `PENDING`
3. All gaps DONE/BLOCKED → run **explore phase** (Step 6 below)
4. Pick next `PENDING` (priority: critical > warning > info, then app alphabetical)
5. Mark `IN_PROGRESS`

If `$ARGUMENTS` provided as `<app>`, filter to that app only.

### 2. ENHANCE

Apply the fix appropriate to the gap type:

| Gap type | Action |
|----------|--------|
| `lint` | Edit DSL to satisfy lint rule (add search_fields, persona, scope, etc.) |
| `scope` | Convert `permit:` to `permit:` + `scope:` per ADR-0010 predicate algebra |
| `validation` | Edit DSL to satisfy parser/validator |
| `conformance` | Add missing entity/surface/workspace per `mcp__dazzle__conformance` |
| `fidelity` | Add missing IR-graph edges per `mcp__dazzle__dsl operation=fidelity` |
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

```bash
cd examples/<app> && dazzle ux verify --contracts 2>&1 | tail -20
```

Verify the gap closed. For visual_quality fixes, optionally re-run the Tier-2 visual scrape (`dazzle qa capture` + the visual_tier2 subagent) and compare.

### 5. REPORT (lane-internal)

1. Update row in lane backlog: `IN_PROGRESS` → `DONE` (or `BLOCKED` after 3 attempts)
2. Note commit SHA in row's notes
3. Return outcome: `{status: PASS|FAIL|BLOCKED, summary, signals_to_emit: [{kind: "app-fixed", payload: {app, gap_type, commit}}], budget_consumed: 0}`

### 6. EXPLORE / TIERED GAP DISCOVERY (when backlog clean)

Tiered to manage cost — start free, escalate only when the previous tier is exhausted.

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

Runs as a Claude Code Task subagent — no Anthropic API call, no API token spend. Cognitive work bills to the Claude Code subscription. See `improve/strategies/visual_tier2_subagent.md` for the full numbered playbook.

In short: `dazzle qa capture --manifest <path>` writes a fleet-wide JSON manifest of screenshots; `dazzle.qa.evaluate.build_subagent_prompt(...)` builds a multi-screen mission; the subagent Reads each PNG, evaluates against `dazzle.qa.categories.CATEGORIES`, and writes findings JSON; `dazzle.cli.runtime_impl.ux_cycle_impl.visual_tier2_ingest.ingest_visual_findings(...)` writes new `visual_quality` rows into this lane's section of the backlog (dedup by `(app, category, location)`, severity-sorted, `seen=K` reinforced on re-runs).

Row shape: `| N | <app> | visual_quality | [<category>] <description> at <location> | PENDING | 0 | seen=1, screenshot=<path>, ts=<...> |`.

Increments shared budget by 5 (single heavy dispatch, ~25-50 screens).

#### Tier 3 (when Tier 2 exhausted, high cost): LLM cross-app review

Pick one app, run a review subagent that compares its DSL against patterns from a reference app (e.g. `support_tickets` vs `simple_task`). Surface gaps the static lints don't catch (missing rhythms, weak personas, no test_design coverage).

Increments shared budget by 5 (significantly more expensive).

## Hard rules

- **One gap per cycle.** Don't chain.
- **Three attempts then BLOCKED.** Never let a gap run forever.
- **Framework-related gaps file issues, don't fix.** This lane targets app DSL only — framework fixes belong in `framework-ux` or /issues.
- **Stale-finding TTL.** `visual_quality` rows come from Tier-2 `dazzle qa capture` scrapes (Step 6, via the visual_tier2 subagent). A single-observation row (`seen=1`) that stays `PENDING` longer than **14 days** ages out behind framework releases — by pickup time the issue is often already fixed, so it inflates `actionable_count`, mis-biases lane selection, and wastes investigation re-confirming non-issues. **Delete such rows in OBSERVE rather than carrying them**; the next Tier-2 scrape re-discovers anything still extant with a fresh `ts`/`seen` (cheap by design). Exceptions that are NEVER pruned on age: rows linked to a filed issue (`FILED→#…`), rows recording a shipped fix (`RESOLVED→#…`), and reinforced rows (`seen≥2`, where repeated observation across scrapes is signal). Validated by cycle 157 (2026-05-29): rows 103/106 sat `PENDING` 14 days, then proved stale — the empty list-region empty-state had since been wired (confirmed by direct `ListRegion` render at v0.80.27).
