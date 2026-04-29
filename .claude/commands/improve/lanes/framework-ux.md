# Lane: framework-ux

Brings Dazzle's UX layer under ux-architect governance one component at a time, and verifies via agent-led QA against example apps. Adapted from former /ux-cycle.

## Targets

Dazzle framework's UI templates, contracts, fitness walks. **Not** example-app DSL — that's `example-apps` lane.

## State

- **Backlog section:** `## Lane: framework-ux` in `dev_docs/improve-backlog.md`
- **Component contracts:** `~/.claude/skills/ux-architect/components/<component>.md`
- **Gap docs:** `dev_docs/framework-gaps/<YYYY-MM-DD>-<theme-slug>.md`
- **Run state:** `dev_docs/ux_cycle_runs/<example>_<persona>_<run_id>/` (gitignored)

## Signals

| Direction | Kind | Notes |
|-----------|------|-------|
| Emit | `ux-component-shipped` | After QA PASS — payload `{component, outcome}` |
| Emit | `ux-regression` | A previously-DONE row went FAIL |
| Emit | `ux-gap-analysis` | Synthesis cycle wrote gap doc(s) — payload `{cycle, themes_count, theme_slugs}` |
| Emit | `ux-investigation-complete` | finding_investigation cycle ran — payload `{cycle, ex_id, outcome}` |
| Consume | `trial-friction` | Treat as candidate for SPECIFY (qualitative friction may need a contract) |
| Consume | `dazzle-updated` / `fix-deployed` | Mark affected backlog rows for re-verification |

## actionable_count

Rows in `## Lane: framework-ux` section with status ∈ {`REGRESSION`, `PENDING`, `IN_PROGRESS`, `READY_FOR_QA`} **OR** `qa: PENDING` **OR** `contract: DRAFT`.

## Playbook

### 1. OBSERVE

Pick highest-priority row from the lane's section using this order:
1. Any `REGRESSION` row (highest)
2. `PENDING` rows where `contract: MISSING` and `impl: PENDING` (new work)
3. `PENDING` rows where `contract: DRAFT` (in-progress work)
4. `DONE` rows where `qa: PENDING` (verification)
5. `VERIFIED` rows (lowest — re-verification)

If no rows match → run **explore phase** (Step 6 below).

Mark selected row `IN_PROGRESS`, update `last_cycle`, increment `attempts`. If `attempts > 3` → mark `BLOCKED`, pick next row.

### 2. SPECIFY (only if contract is MISSING or DRAFT)

Invoke the `ux-architect` skill via Skill tool. Save contract to `~/.claude/skills/ux-architect/components/<component>.md` per the contract template at `~/.claude/skills/ux-architect/templates/component-contract.md`. Update row's `contract` to `DONE`.

Skip if contract is already `DONE`.

### 3. REFACTOR (only if impl is PENDING or PARTIAL)

Apply contract to Dazzle code. Typical files:
- `src/dazzle_ui/templates/...` — restyle to pure Tailwind with design-system.css HSL variables
- `src/dazzle_ui/runtime/static/js/dz-alpine.js` — Alpine controllers aligning with contract's state grammar
- Backend endpoints for new server APIs
- `src/dazzle_ui/converters/template_compiler.py` — new context fields

Follow rules from `~/.claude/skills/ux-architect/stack-adapters/htmx-alpine-tailwind.md`.

Update row's `impl` to `DONE`.

### 4. QA

Two-phase against the row's `canonical` example plus one rotating sample from `applies`.

**Phase A — HTTP contracts (fast):**
```bash
cd examples/<canonical> && dazzle ux verify --contracts
```
If fails → mark `qa: FAIL`, note failures, skip Phase B.

**Phase B — Fitness-engine contract walk (slow, only if Phase A passed AND contract has quality gates):**

Routes through the fitness engine. `ModeRunner` owns subprocess lifecycle:

```python
from pathlib import Path
from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import run_fitness_strategy
from dazzle.e2e.modes import get_mode
from dazzle.e2e.runner import ModeRunner

example_root = Path("/Volumes/SSD/Dazzle/examples/<canonical>")
contract_path = Path.home() / ".claude/skills/ux-architect/components/<component>.md"

async with ModeRunner(
    mode_spec=get_mode("a"),
    project_root=example_root,
    personas=["admin", "agent", "customer"],   # or None for anonymous components
    db_policy="preserve",
) as conn:
    outcome = await run_fitness_strategy(
        conn,
        example_root=example_root,
        component_contract_path=contract_path,
        personas=["admin", "agent", "customer"],
    )
```

The fitness engine's Pass 1 parses the contract and calls `walk_contract` — one ledger step per quality gate.

`outcome.degraded` rules:
- `False` → `qa: PASS`
- `True` with at least one persona → `qa: FAIL`
- Strategy raises (subprocess never started) → `qa: BLOCKED`

`outcome.findings_count` is **NOT** used for qa pass/fail (cycle 156 fix). It's Pass 2a story_drift / spec_stale / lifecycle observations from the example app's overall spec/story coherence — orthogonal to whether the widget contract walked correctly.

### 5. REPORT (lane-internal — driver also writes a top-level entry)

1. Update row in lane backlog section with new status, contract/impl/qa, notes (include git SHA of any commits this cycle).
2. If QA passed → move to `DONE`. If was already `DONE` and re-verified → `VERIFIED`.
3. Return outcome to driver: `{status: PASS|FAIL|BLOCKED, summary, signals_to_emit, budget_consumed: 0}`

### 6. EXPLORE (when no actionable rows in Step 1)

Choose one of six sub-strategies based on accumulated state. Pick by judgment, not strict rotation.

#### Sub-strategy: missing_contracts

Scan for recurring UX patterns lacking a contract. Proposal-heavy. Use when (a) recently-touched template family may contain uncontracted components, or (b) >3 cycles since last `missing_contracts`.

Substrate: dispatches a Claude Code Task-tool subagent (model `sonnet`, type `general-purpose`) using the playbook in `improve/strategies/explore-subagent.md`. Findings go to per-run findings.json then ingested into the lane backlog as `PROP-NNN` proposals.

#### Sub-strategy: edge_cases

Probe friction, broken-state recovery, empty/error handling, dead-end navigation, affordance mismatches. Observation-heavy. Use when (a) persona/app axis hasn't been probed yet, or (b) recent framework fix needs cross-app regression evidence.

Same subagent substrate as `missing_contracts`. Findings go to lane backlog as `EX-NNN` observations.

#### Sub-strategy: contract_audit

**No browser, no subagent.** Pick a known-templated-but-ungoverned component and formalise it in one cycle:
1. HTTP-reproduce current rendering via `dazzle serve --local`
2. Grep every call site
3. Build contract at `~/.claude/skills/ux-architect/components/<name>.md` with quality gates mirroring canonical shape
4. Fix any drift across every call site in one commit (design-token migration, DaisyUI removal, canonical class markers, ARIA hooks)
5. Regression tests for each quality gate
6. Cross-app verification

Use when a templated component has cross-cutting drift that will snowball if not consolidated.

#### Sub-strategy: framework_gap_analysis

**No browser, no subagent — pure reasoning cycle.** Read accumulated EX-NNN observations since last analysis, group by defect-class, identify themes where 2+ observations point at the same gap. Write `dev_docs/framework-gaps/<YYYY-MM-DD>-<theme-slug>.md` per:

- **Problem statement** — generalisable defect class, framework-first not app-first
- **Evidence** — EX-NNN rows + GitHub issues, one-line each
- **Root cause hypothesis** — file paths if identifiable
- **Fix sketch** — concrete proposal that addresses all contributing observations
- **Blast radius** — affected apps/personas
- **Open questions** — what needs verification before fix is safe

Use when 3+ cross-cycle observations point at same theme, OR you want to consolidate evidence before escalating to a GitHub issue, OR >7 cycles since last analysis.

Counts against shared explore budget.

#### Sub-strategy: finding_investigation

**No subagent, but you may use your own tools to reproduce and root-cause.** Pick one OPEN EX-NNN row (prefer severity=concerning, prefer cross-cycle reinforcement):

1. Reproduce the defect locally — boot relevant example app, isolate conditions
2. Trace to framework code (Grep/Read), starting from symptom's most-likely call site
3. Either file a GitHub issue with code-level evidence OR propose a fix directly if small
4. Update EX row's status: `OPEN` → `FILED→#NNN` / `FIXED_LOCALLY` / `VERIFIED_FALSE_POSITIVE`

Counts against shared explore budget.

**HEURISTIC 1 (mandatory): Try the real thing first.** Before writing fix code OR committing to a gap doc's framework infrastructure, reproduce the defect end-to-end at the lowest layer that can exhibit it. Track record: 4 of last 6 investigations had the hypothesised framework fix turn out to be unnecessary or wrong. See `improve/references/heuristics.md` for the full rule and `improve/references/substrate-failure-modes.md` for the catalog of observer-artifact failure modes.

**HEURISTIC 2: Helper-audit propagation.** When fixing a single-source-of-truth helper miss, grep for other call sites before writing the fix.

**HEURISTIC 3: Cross-app verification.** Any framework-layer fix must be verified against all 5 example apps before commit.

**HEURISTIC 4: Defaults propagation audit.** When a canonical intent declaration exists, trace it from declaration through resolver to every consumer. Missing propagation is its own defect class.

#### Sub-strategy: api_surface_audit

**No subagent — pure reasoning cycle.** Walk one of the five committed API-surface baselines (DSL constructs, IR types, MCP tools, public helpers, runtime URLs) top-to-bottom asking "is this what we'd design today?". Files findings as `API-NNN` proposals into the framework-ux backlog. Closes the loop on #961 cycle 6 (1.0-prep walkthrough as a recurring exercise).

Use when:
- Last `api_surface_audit` cycle was ≥7 cycles ago
- A `dazzle-updated` signal fired since last audit
- Approaching 1.0 — flip from opportunistic to mandatory weekly cadence

Skip if:
- ≥3 unresolved `API-NNN` rows already open (consolidate before adding more)

Detailed playbook: `improve/strategies/api_surface_audit.md`. Counts against shared explore budget.

### Sub-strategy choosing

When EXPLORE is entered:
1. Scan recent cycle outcomes (last 5 in `improve-log.md`) and OPEN EX row counts by severity
2. List candidates with one-line reason each
3. Pick one and record the choice in the cycle log entry
4. Proceed with that strategy's playbook

Prefer diverse cycles over mechanical rotation. Three `edge_cases` runs in a row is fine if signal keeps converging on interesting framework themes; two back-to-back `framework_gap_analysis` cycles is fine if first surfaced a promising theme.

## Hard rules

- **One row or one strategy per cycle.** Don't chain.
- **Per-phase stagnation check.** If SPECIFY/REFACTOR/QA makes no progress for 3 minutes, abort and mark `BLOCKED`.
- **Never modify rows in DONE/VERIFIED state directly** — let the cycle move them naturally via QA.

## Subagent substrate (for missing_contracts and edge_cases)

EXPLORE runs as a Claude Code Task-tool subagent, NOT as a `DazzleAgent` on the direct Anthropic SDK. Cognitive work bills to Claude Code subscription; browser work happens via stateless Playwright helper subprocess.

Detailed playbook: `improve/strategies/explore-subagent.md`. Numbered steps for: init run state directory, boot example app via runner script, poll for readiness, log in as persona, build mission prompt, invoke Task tool, read findings, tear down runner, ingest results.
