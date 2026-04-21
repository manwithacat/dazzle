---
description: Iterative UX improvement loop — one component per cycle through ux-architect governance and agent QA
---

# /ux-cycle

Bring Dazzle's UX layer under ux-architect governance one component at a time, and verify quality via agent-led QA against example apps. Builds on QA mode (#768) and the ux-architect skill.

## Cycle (7 steps)

### Step 0a: Preflight

1. Check `.dazzle/ux-cycle.lock`. If it exists and its timestamp is < 45 minutes old, **abort** with "Another ux-cycle is already running (lock at $LOCKFILE, PID $PID)". If it's older, delete it as stale.
2. Create `.dazzle/ux-cycle.lock` with current PID and ISO timestamp.
3. Read signals via `dazzle.cli.runtime_impl.ux_cycle_signals.since_last_run(source="ux-cycle")`. Handle any `dazzle-updated` or `fix-deployed` signals by marking affected backlog rows for re-verification.
4. **Infrastructure-drift gate** (~5s): run `make test-ux-preflight`. This runs the 6 horizontal-discipline lints (template-orphan, page-route-coverage, canonical-pointer, template-none-safety, daisyui-python, external-resource) + DOM snapshots + card-safety invariants + `mypy src/dazzle_ui/` + a non-blocking `git status dist/` warning. **If red, STOP and fix before continuing** — cycle 311 exposed ~40 cycles of silent snapshot drift from contract_audit cycles that never refreshed syrupy baselines. This gate prevents that class recurring. Common red causes and their fixes:
   - **Snapshot drift** (additive template changes): `pytest tests/unit/test_dom_snapshots.py --snapshot-update` after verifying the diff is additive-only.
   - **New CDN load or DaisyUI token**: either self-host / migrate to canonical tokens, OR add an allowlist entry with a reason citing a gap doc / issue / cycle.
   - **mypy regression in `src/dazzle_ui/`**: fix inline; if the error is in a file outside dazzle_ui, run `make test-ux-deep` to see if it's a broader issue.
   - **dist/ drift** (non-blocking warning only): surfaces uncommitted dist/ files; run `make build` or commit the regenerated assets before `/ship`.

   For deeper-scope audits before `/ship`, `make test-ux-deep` runs the preflight plus broader mypy across core/cli/mcp/back (~15s warm).

### Step 0b: Init (first run only)

If `dev_docs/ux-backlog.md` does not exist, the backlog has been seeded manually — do not regenerate. Just read it.

### Step 1: OBSERVE

Read `dev_docs/ux-backlog.md`. Pick the highest-priority row using this order:
1. Any `REGRESSION` row (highest)
2. `PENDING` rows where `contract: MISSING` and `impl: PENDING` (new work)
3. `PENDING` rows where `contract: DRAFT` (in-progress work)
4. `DONE` rows where `qa: PENDING` (verification)
5. `VERIFIED` rows (lowest — re-verification)

If no rows match, jump to Step 6 (EXPLORE mode).

Mark the selected row `IN_PROGRESS` and update `last_cycle`. Increment `attempts`. If `attempts > 3`, mark `BLOCKED` and pick the next row instead.

### Step 2: SPECIFY (only if contract is MISSING or DRAFT)

Invoke the ux-architect skill to produce a component contract for this row's component. Save it to `~/.claude/skills/ux-architect/components/<component>.md` following the contract template at `~/.claude/skills/ux-architect/templates/component-contract.md`. Update the row's `contract` field to `DONE`.

If the contract already exists and is `DONE`, skip this step.

### Step 3: REFACTOR (only if impl is PENDING or PARTIAL)

Apply the contract to Dazzle's code. This typically touches:
- Templates in `src/dazzle_ui/templates/...` — restyle to pure Tailwind with design-system.css HSL variables
- Alpine controllers in `src/dazzle_ui/runtime/static/js/dz-alpine.js` — align with contract's state and interaction grammar
- Backend endpoints if the contract requires new server APIs
- Template compiler in `src/dazzle_ui/converters/template_compiler.py` — if the contract needs new context fields

Follow all rules from the stack adapter at `~/.claude/skills/ux-architect/stack-adapters/htmx-alpine-tailwind.md`.

Update the row's `impl` field to `DONE`.

### Step 4: QA

Two-phase verification against the row's `canonical` example plus one rotating sample from `applies`:

**Phase A — HTTP contracts (fast):**

```bash
cd examples/<canonical> && dazzle ux verify --contracts
```

If this fails, mark `qa: FAIL`, note the failures in the row's `notes`, and skip Phase B. Go to Step 5.

**Phase B — Fitness-engine contract walk (slow, only if Phase A passes AND the contract has quality gates):**

Phase B now routes through the fitness engine. Subprocess lifecycle is owned
by `dazzle.e2e.runner.ModeRunner` (v0.54.4+); the fitness strategy takes an
`AppConnection` from the runner and runs the engine against it:

```python
from pathlib import Path
from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import run_fitness_strategy
from dazzle.e2e.modes import get_mode
from dazzle.e2e.runner import ModeRunner

dazzle_root = Path("/Volumes/SSD/Dazzle")
example_root = dazzle_root / "examples" / "<canonical>"
contract_path = Path.home() / ".claude/skills/ux-architect/components/<component>.md"

# For in-app components (data-table, detail-view, dashboard, etc.):
# pass an explicit persona list matching the DSL personas that should see
# the component. The ModeRunner auto-sets QA flags when personas is
# non-empty so the magic-link login flow (#768) works.
async with ModeRunner(
    mode_spec=get_mode("a"),
    project_root=example_root,
    personas=["admin", "agent", "customer"],
    db_policy="preserve",
) as conn:
    outcome = await run_fitness_strategy(
        conn,
        example_root=example_root,
        component_contract_path=contract_path,
        personas=["admin", "agent", "customer"],
    )

# For public/anonymous components (auth pages, landing pages):
# pass personas=None (or omit) to run a single anonymous cycle.
# async with ModeRunner(
#     mode_spec=get_mode("a"),
#     project_root=example_root,
#     personas=None,
#     db_policy="preserve",
# ) as conn:
#     outcome = await run_fitness_strategy(
#         conn,
#         example_root=example_root,
#         component_contract_path=contract_path,
#         personas=None,
#     )
```

The fitness engine's Pass 1 parses the contract and calls the
`walk_contract` mission — one ledger step per quality gate, with each
gate description recorded as EXPECT and the current DOM snapshot recorded
as OBSERVE. Findings flow through the normal engine pipeline and land in
`dev_docs/fitness-backlog.md` under the example app.

`ModeRunner` owns subprocess lifecycle: acquires PID lock at
`<example>/.dazzle/mode_a.lock` with 15-min TTL safety net, launches
`dazzle serve --local`, polls `.dazzle/runtime.json` for the deterministic
hashed ports, health-checks `/docs`, yields the `AppConnection`, and
tears down cleanly on exit (or on exception, with log tail printed to
stderr). The strategy no longer owns any of this — its only job is
running the engine against whatever URL the runner hands over.

Multi-persona fan-out runs one cycle per persona inside a single
subprocess lifetime. The Playwright browser is launched once, and each
persona gets a fresh `browser.new_context()` for cookie isolation.
Per-persona failures (login rejected, engine crashed, anchor navigation
failed) produce BLOCKED outcomes but do not abort the loop — remaining
personas still run. The aggregated `StrategyOutcome` sums per-persona
findings and surfaces the max independence score across all personas.

**Precondition:** the example app needs `DATABASE_URL` + `REDIS_URL`
reachable (set in `examples/<canonical>/.env` or exported in the shell).
See `docs/reference/e2e-environment.md` for details.

The row's `qa` field becomes:
- `PASS` if `outcome.degraded is False` (the contract walker completed
  without walker errors or infrastructure failures across all personas).
- `FAIL` if `outcome.degraded is True` and at least one persona ran
  (the walker erred or an infrastructure failure occurred mid-run).
- `BLOCKED` if the strategy itself raised (subprocess failed to start,
  Playwright bundle couldn't spin up, all personas failed). Note that
  per-persona failures within a multi-persona run are absorbed into
  `outcome.degraded=True` for that persona; the strategy only raises
  when there is nothing useful to return.

`outcome.findings_count` is **not** used for qa pass/fail. It reports
Pass 2a story_drift / spec_stale / lifecycle observations from the
example app's overall spec/story coherence — completely orthogonal to
whether the widget contract walked correctly. The contract walker
(`walk_contract`) emits zero findings; it only records ledger steps.
`findings_count` should be reported as informational app-health context,
not used to gate per-component qa state. This is the cycle 156 fix —
prior to that cycle, the rule incorrectly used `findings_count > 0` as
the FAIL gate, blocking every widget contract from ever reaching PASS.

### Step 5: REPORT

1. Write an entry to `dev_docs/ux-log.md` with the cycle timestamp, component, phases run, and outcome.
2. Update `dev_docs/ux-backlog.md` with the new row status, contract/impl/qa fields, and notes (include the git SHA of any commits made this cycle).
3. If QA passed, move the row to `DONE`. If it was already `DONE` and just re-verified, move it to `VERIFIED`.
4. Commit changes with message `ux: cycle {component} — {outcome}`.
5. Emit a signal:
   ```python
   from dazzle.cli.runtime_impl.ux_cycle_signals import emit
   emit(source="ux-cycle", kind="ux-component-shipped", payload={"component": "<name>", "outcome": "<status>"})
   ```
   If the row was `DONE` and regressed to `FAIL`, emit `ux-regression` instead.

### Step 6: EXPLORE / ANALYSE / INVESTIGATE (only if no actionable rows remain in Step 1)

The explore phase is the loop's entropy-reducer. Its primary job is identifying **generalisable framework-level problems** — defect classes that span multiple apps/personas and can be fixed once at the framework layer rather than N times at the app layer. Surface-level observations are the raw material; cross-cycle synthesis into framework gaps is the high-value outcome.

#### Budget

Check `.dazzle/ux-cycle-explore-count`. If count >= **100**, skip Step 6 and mark the cycle complete with "explore budget exhausted — pause for triage". 100 is a soft safety rail against runaway loops caused by bugs, not a productivity ceiling. When the cap is hit, the expected response is a **deliberate batch reset** by the operator after reviewing accumulated findings — not "more of the same".

Secondary short-circuit: if the last 5 cycles that actually reached Step 6 produced **zero** findings AND no framework gaps, skip EXPLORE and pause. Track cycles that reached Step 6 via `explored_at` timestamps in `.dazzle/ux-cycle-state.json`; housekeeping cycles (retroactive qa-rule sweeps, log-only updates, exhausted-sticky runs) are NOT counted toward the streak.

#### Strategy selection

The assistant running /ux-cycle chooses one of five strategies per cycle, using **judgment** rather than a strict rotation. The default behaviour is to rotate through `missing_contracts` and `edge_cases` for breadth, but the assistant SHOULD deviate when there's a high-leverage reason to:

1. **`missing_contracts`** — scan for recurring UX patterns that should have a ux-architect contract but don't yet. Proposal-heavy. Use when: (a) a recently-touched template family (e.g. `workspace/regions/`) may contain uncontracted components, or (b) it's been >3 cycles since the last missing_contracts run.

2. **`edge_cases`** — probe for friction, broken-state recovery, empty/error/boundary handling, dead-end navigation, affordance mismatches. Observation-heavy. Use when: (a) a persona/app axis hasn't been probed yet, or (b) a recent framework fix (closed GitHub issue) needs cross-app regression-check evidence, or (c) the current cycle's rotation dictates it.

5. **`contract_audit`** — **no browser, no subagent**. Pick a specific *known-templated-but-ungoverned* component (one whose template ships but has no ux-architect contract) and formalise it in one cycle: (a) HTTP-reproduce the current rendering via dazzle serve --local, (b) grep every call site, (c) build a contract doc at `~/.claude/skills/ux-architect/components/<name>.md` with quality gates mirroring the canonical shape, (d) fix any drift found (design-token migration, DaisyUI class removal, canonical class markers, ARIA hooks) across every call site in one commit, (e) regression tests matching each quality gate, (f) cross-app verification that the fix doesn't regress anything. Distinct from `missing_contracts` — that strategy proposes WHICH components to contract; `contract_audit` executes the contract + fix + migration for a specific already-chosen target. Promoted to a named strategy in cycle 241 after three successful iterations (cycles 238 status-badge, 239 metrics-region, 240 empty-state + EX-046 grammar extension). Use when: (a) the cycle 237 component menagerie roadmap has a prioritised target ready, (b) an existing template has cross-cutting drift that will snowball if not consolidated, or (c) a contract already exists but has silently drifted since it was written.

3. **`framework_gap_analysis`** — **no browser, no subagent**. Instead: read accumulated observations (EX-XXX rows) since the last analysis cycle, group by defect-class, identify cross-cycle themes where 2+ observations point at the same underlying framework gap, and write a **gap analysis document** to `dev_docs/framework-gaps/<YYYY-MM-DD>-<theme-slug>.md`. Each gap doc must include:
   - **Problem statement** — the generalisable defect class, phrased framework-first not app-first
   - **Evidence** — list of EX-XXX rows (and any GitHub issues) contributing to the theme, each with a one-line summary
   - **Root cause hypothesis** — where in the framework code the gap likely lives, with specific file paths if identifiable
   - **Fix sketch** — a concrete proposal, ideally a single change that addresses all contributing observations
   - **Blast radius** — which apps/personas are likely affected and which are already confirmed
   - **Open questions** — what needs verification before a fix is safe

   Use when: (a) 3+ cross-cycle observations point at the same theme, (b) you want to consolidate evidence before escalating to a GitHub issue, or (c) it's been >7 cycles since the last analysis — synthesis debt accumulates. This strategy produces NO browser activity and NO subagent dispatch; it is a pure reasoning cycle. It DOES count against the explore budget.

4. **`finding_investigation`** — **no browser subagent, but you may use your own tools to reproduce and root-cause a specific finding**. Pick one OPEN EX-XXX row (prefer severity=concerning, prefer cross-cycle reinforcement) and:
   - Reproduce the defect locally (boot the relevant example app, verify the finding is real, isolate conditions)
   - Trace it to the framework code that causes it
   - Either file a GitHub issue with direct code-level evidence OR propose a fix directly if small enough
   - Update the EX row's status from `OPEN` to `FILED→#NNN` (issue filed), `FIXED_LOCALLY` (patch pending), or `VERIFIED_FALSE_POSITIVE` (cannot reproduce)

   Use when: (a) a concerning observation has accumulated enough cross-cycle evidence to investigate, (b) a gap_analysis cycle surfaced a promising root-cause hypothesis that needs verification, or (c) the backlog has >5 OPEN concerning rows — conversion pressure.

#### Choosing for this cycle

When Step 6 is entered, the assistant:

1. **Scans recent cycle outcomes** in `dev_docs/ux-log.md` (last 5 cycles) and the OPEN EX row counts by severity.
2. **Lists candidate strategies** it considered, with a one-line reason each.
3. **Picks one** and records the choice in the log entry for this cycle.
4. **Proceeds** with that strategy's playbook (see below for `missing_contracts` / `edge_cases`; `framework_gap_analysis` and `finding_investigation` have their own structures documented in Appendix A at the bottom of this skill).

The assistant should **prefer diverse cycles over mechanical rotation**. Three edge_cases runs in a row is fine if the cross-cycle signal keeps converging on interesting framework themes; conversely, two back-to-back framework_gap_analysis cycles is fine if the first one surfaced a promising theme that the second can dig deeper into.

### Appendix A — `framework_gap_analysis` and `finding_investigation` playbooks

**`framework_gap_analysis` workflow:**

1. Read `dev_docs/ux-log.md` for the last ~10 cycles and the current `dev_docs/ux-backlog.md` EX table.
2. Group OPEN (and recently-filed) observations by suspected common cause. Look for:
   - Identical or near-identical defect patterns across 2+ apps
   - Observations that point at the same template family or framework subsystem
   - Observations that recur *after* a framework fix was shipped for a related issue
   - Observations that reinforce a hypothesis from a prior finding
3. For each theme with 2+ observations, write a gap doc at `dev_docs/framework-gaps/<YYYY-MM-DD>-<theme-slug>.md` using the structure in Step 6 above.
4. Commit with message `ux: gap analysis cycle {N} — {K} themes synthesised`.
5. The cycle counts against the explore budget (increment the counter).
6. Emit signal `ux-gap-analysis` with payload `{cycle, themes_count, theme_slugs}`.

**`finding_investigation` workflow:**

1. Pick an OPEN EX row (see selection heuristics in Step 6).
2. Reproduce locally (typically `dazzle serve --local` against the row's canonical example, drive via curl/httpx/direct SQL, extract the minimum repro).
3. Trace to framework code using Grep/Read, starting from the symptom's most-likely call site.
4. Write findings to the EX row's `notes` column (include line-number refs to the responsible code).
5. One of:
   - File a GitHub issue (via `gh issue create`) if the fix scope is material and unclear. Update the row's status to `FILED→#NNN`.
   - Land a fix directly (edit code, run `/ship`) if the fix is small and the mechanism is certain. Update the row's status to a closure note and cite the commit SHA.
   - Mark as `VERIFIED_FALSE_POSITIVE` if the observation cannot be reproduced, with notes explaining the reproduction attempt and the likely false-positive cause.
6. Commit with message `ux: investigation cycle {N} — {EX-id} {outcome}`.
7. The cycle counts against the explore budget.
8. Emit signal `ux-investigation-complete` with payload `{cycle, ex_id, outcome}`.

### Durable heuristics (from cycles 225-234)

These rules are load-bearing for every future investigation and synthesis cycle. Internalise them.

**Heuristic 1 — "Try the real thing" before committing to a framework hypothesis. (MANDATORY)**

*Surfaced in cycle 228, proved critical in cycle 229, repeatedly validated in cycles 232/233/234.*

**This rule is non-negotiable.** Before you write a line of fix code OR commit to a gap doc's proposed framework infrastructure, **reproduce the defect end-to-end at the lowest layer that can exhibit it**. For a "silent form submit" observation: fire a raw curl with `HX-Request: true` at the backend endpoint and check the response. For a "bulk-action bar shown to wrong persona" observation: attempt the actual DELETE and see whether the runtime accepts or denies it. For a "workspace nav leak" observation: compare the sidebar hrefs for each persona against what `workspace_allowed_personas` returns directly. For a "widget missing on form" observation: curl the form HTML and grep for the widget marker.

**Track record — 4 of the last 6 investigations had the hypothesised framework fix turn out to be unnecessary or wrong:**

- **Cycle 229** — Gap doc #1's "silent form submit" framework gap was a substrate artifact (`action_type` values evaporated across subprocess boundaries). Framework 422 handling already existed and worked. Heuristic 1 saved a major unnecessary build.
- **Cycle 232 ref-half** — EX-009's widget-selection observation turned out to be two separate gaps with asymmetric scope. Date half was a 1-line default; ref half was structural template work. The initial hypothesis (single dispatch-table fix) would have been wrong for the ref case.
- **Cycle 233** — EX-041's "cascade `inject_current_user_refs` to User-subtypes" fix had no code to apply because Tester isn't a User-subtype at all. The real gap is a deeper DSL question (persona-to-entity binding, filed as EX-045).
- **Cycle 234** — EX-011/030/037's "empty-state CTAs invite unauthorised actions" turned out to be DSL copy quality, not a framework affordance bug. The framework already correctly withholds the Create-first CTA button via `empty_state.html:7-9`. Fix is at the DSL copy layer (EX-046), not the framework rendering layer.

Without Heuristic 1, each of these cycles would have shipped framework code that didn't solve the observed problem. The discipline prevents wrong work, and its hit rate is durable enough to promote from "strongly recommended" to **mandatory**.

**Why subagent observations are unreliable:** Multiple layers separate the subagent's `visible_text` from actual framework behaviour — the substrate's statelessness (form state evaporates between calls), the browser's JS event loop timing, HTMX swap scheduling, observe-time re-navigation that destroys in-place DOM changes, DSL copy that looks like an affordance but isn't. Any of these can fake a framework defect.

**Catalog of observed substrate-intel failure modes** (cycles 229 → 331, consolidated cycle 332):

| # | Mode | Surfaced | Telltale | Mitigation |
|---|---|---|---|---|
| 1 | Substrate statelessness | 229 | Form values evaporate between subagent tool calls — looks like "server lost the data" but is actually subprocess-boundary artifact | Raw curl / httpx repro with explicit payload; never trust form-state persistence claims from subagents |
| 2 | DSL copy misread as affordance | 234 | Empty-state text says "Add your first item!" → observer reports "CTA invites unauthorised action" — but framework correctly withholds the Create button; only the COPY suggested otherwise | Grep the DSL `empty:` block for the string; check the template's `{% if create_url %}` gate |
| 3 | Pre-open DOM of dynamic elements | 330 | `<a hidden>` element with no `href` read before JS populates it → observer reports "dead affordance"; actual element is client-side-populated at interaction time | Check for `hidden` attribute + absent `href`/`src`. If dynamic, element is populated by an event handler — raw-read is insufficient |
| 4 | Pre-hydration DOM textContent | 331 | `<span x-text="count">0</span> items` with `x-cloak`/`x-show` wrapper → observer extracts text content (not blocked by `display:none`) before Alpine hydrates → reports "empty placeholder" or pre-substitution text | Check for Alpine directives (`x-text`, `x-show`, `x-cloak`) or HTMX `hx-*` on the element or an ancestor. Raw-read snapshots are taken BEFORE JS runtime finishes |
| 5 | Detection-tool AST blindspot | 371 | Module appears orphan in `make audit-internals` but is used by sibling code via `from .submod import X`. The audit's `_imports_in_file` ignored `ImportFrom.level > 0` (relative imports), so sibling imports never registered as graph edges. Suspected "fitness parser never wired" turned out to be an audit-tool bug. Cut 150 → 65 orphans when fixed. | Before filing a #834-shape issue for a module orphan, run `grep -rn "from \.\w* import\\|from \.\.\w* import" --include="*.py" <dir>` as a raw-layer sanity check. The audit tool is heuristic — verify its claim against a direct grep before assuming the module is dead |

Add to this catalog whenever a `finding_investigation` cycle pivots from "framework bug" → "observer artifact" (or "detection-tool artifact", per mode 5). The catalog is durable knowledge for future cycles — reading it before filing a framework issue can prevent unnecessary work.

**The rule (mandatory — not optional):**

In any `finding_investigation` cycle OR any implementation cycle triggered by a gap doc, the FIRST step is a raw-layer reproduction. If the raw layer shows the framework behaving correctly, the defect is in the observer, the DSL, or the substrate — pivot the cycle to that layer instead. Do not write framework code until the raw layer confirms framework behaviour is incorrect.

**Heuristic 2 — Helper-audit cycles for single-source-of-truth propagation.**

*Surfaced in cycles 226 + 228.*

When the framework introduces a helper function intended to be a single source of truth for some decision (e.g. `workspace_allowed_personas` for workspace visibility, `_user_can_mutate` for entity-level permissions), the refactor that introduces the helper often migrates ONE call site but misses others with superficially similar but subtly divergent logic. Cycle 226 found the v0.55.34 #775 fix had migrated `template_compiler.py`'s nav builder but missed `page_routes.py:1115`'s separate nav builder. Cycle 228 found that `_user_can_mutate` was correctly called for the Create button but not for the bulk-action bar, even though both are role-gated UI affordances.

**Rule**: when a `finding_investigation` cycle identifies a helper-audit class defect (two code paths that should consult the same helper but one of them doesn't), **before writing the fix, grep-scan for other call sites** where the helper should also be consulted. Two is evidence of a pattern; there's often a third call site that would have surfaced as a future observation. Fix all of them in one commit when feasible.

Worth considering as a dedicated cycle type: `helper_audit` — pick a single-source-of-truth helper and walk every spot in the codebase where a role/persona/access decision is made, checking whether the helper is called. The audit surfaces pre-observation drift before it becomes cross-cycle evidence.

**Heuristic 3 — Cross-app verification before committing a framework fix.**

*Surfaced in cycle 227.*

Before running `/ship` on a framework-layer fix, run the change against **all 5 example apps** and verify the target behaviour. Cycle 227's first attempted fix reused `compute_persona_default_routes` which honours `persona.default_route` values — a shape simple_task's DSL declares but does not register as real routes. The naïve fix would have redirected simple_task admins to a 404. Cross-app verification caught it immediately.

**Rule**: any `finding_investigation` fix that touches framework code (not test scaffolding or docs) must include an explicit "verified on all 5 example apps" step before commit, even if the fix was motivated by a single app. The 5 apps function as a fidelity oracle for latent DSL shapes you might not have anticipated.

**Heuristic 4 — Defaults propagation audit.**

*Surfaced in cycle 232.*

When the framework introduces a canonical intent declaration (a central lookup table or resolver function that says "this type of thing should use that default"), grep for every call site that *reads* the intent and verify it actually propagates into the context objects templates/consumers actually look at. The intent and the consumer can both exist while the bridge between them is silently incomplete.

**The cycle 232 case**: `src/dazzle/core/ir/triples.py` has a `FIELD_TYPE_TO_WIDGET` map that says `DATE → DATE_PICKER`, `REF → SEARCH_SELECT`. Its resolver `resolve_widget(field_spec)` is called by `template_compiler._field_type_to_form_type()` which derives a `form_type` string. But the form_type string alone isn't enough — the form-field Jinja macro branches on a separate `field.widget` field that was only ever populated from explicit DSL overrides. The intent was declared (triples.py), the resolver was correct, the template consumer existed — but the **bridge** from resolver to context object was missing a default. Date fields correctly rendered as `type="date"` (via the form_type fallback) but never reached the Flatpickr widget branch.

**The pattern**: intent declaration + correct resolver + working consumer ≠ end-to-end correctness. The compiler needs to propagate the intent *into the context object the template actually reads*. This is neither a helper-audit nor a try-the-real-thing issue — it's a subtle data-flow gap that only shows up when you trace from the declaration down to the rendered DOM.

**Rule**: when a framework introduces a canonical intent declaration (like `FIELD_TYPE_TO_WIDGET` or `workspace_allowed_personas` or `PermissionKind`), grep for every call site that reads the intent and verify it propagates all the way to the consumer. Missing propagation is a defect class in its own right — distinct from "helper not called" (Heuristic 2) because the helper IS called, it just produces a value that isn't plumbed through to where it's needed.

Worth considering as a dedicated cycle type: `defaults_propagation_audit` — pick a canonical intent declaration and trace every downstream data-flow path to its rendering consumer. This is a stricter audit than `helper_audit` and catches a different class of drift.

### Substrate (cycle 198+, v0.55.5)

EXPLORE runs as a Claude Code Task-tool subagent, NOT as a `DazzleAgent` on the direct Anthropic SDK. Cognitive work is billed to the Claude Code host subscription; browser work happens via a stateless Playwright helper subprocess. **The assistant running `/ux-cycle` composes this sequence directly — there is no async orchestrator function.**

**Prerequisites:**
- Claude Code host running this very session (the `Task` tool must be reachable).
- `examples/<canonical>/.env` with `DATABASE_URL` + `REDIS_URL`.
- Postgres + Redis reachable on the local dev box.
- No `ANTHROPIC_API_KEY` needed — cognition runs through the subscription.

### Playbook (numbered steps the assistant walks through)

**1. Initialise the per-run state directory.** Run via Bash:

```bash
python -c "
from pathlib import Path
from dazzle.cli.runtime_impl.ux_cycle_impl.subagent_explore import init_explore_run
import json
ctx = init_explore_run(
    example_root=Path('/Volumes/SSD/Dazzle/examples/<canonical>'),
    persona_id='<persona_id>',
)
print(json.dumps(ctx.to_dict(), indent=2))
"
```

This creates `dev_docs/ux_cycle_runs/<example>_<persona>_<run_id>/` with an empty `findings.json` + a generated `runner.py`. Capture the printed context dict — every subsequent step uses paths from it.

**2. Boot the example app via the generated runner script.** Run via Bash `run_in_background=true`:

```bash
python <runner_script_path>
```

The runner loads the example's `.env`, boots `ModeRunner`, writes `conn.json` inside the state dir, then blocks on SIGTERM. **Do not wait on this call** — it runs for the lifetime of the cycle.

**3. Poll for readiness.** Run via Bash (foreground, ~5s timeout):

```bash
for i in $(seq 1 20); do
  test -f <conn_path> && break
  sleep 0.5
done
cat <conn_path>
```

Grab `site_url` + `api_url` from the JSON.

**4. Log in as the persona.** Run via Bash:

```bash
python -m dazzle.agent.playwright_helper \
  --state-dir <state_dir> \
  login <api_url> <persona_id>
```

Verify the output JSON has `"status": "logged_in"`. If it has `"error"`, abort the cycle and jump to Step 7 (kill the runner, log the failure).

**5. Build the subagent mission prompt.** Run via Bash:

```bash
python -c "
from dazzle.agent.missions.ux_explore_subagent import build_subagent_prompt
from dazzle.core.appspec_loader import load_project_appspec
from pathlib import Path
import os

example_root = Path('<example_root>')
app_spec = load_project_appspec(example_root)
persona = next(p for p in app_spec.personas if p.id == '<persona_id>')

# List existing-contracted components so the subagent doesn't re-propose them
components_dir = Path(os.path.expanduser('~/.claude/skills/ux-architect/components'))
existing = sorted(p.stem for p in components_dir.glob('*.md')) if components_dir.exists() else []

prompt = build_subagent_prompt(
    strategy='missing_contracts',
    example_name='<example_name>',
    persona_id='<persona_id>',
    persona_label=persona.label,
    site_url='<site_url>',
    helper_command='python -m dazzle.agent.playwright_helper',
    state_dir='<state_dir>',
    findings_path='<findings_path>',
    existing_components=existing,
    start_route=persona.default_route or '/app',
    budget_calls=20,
    min_findings=3,
)
print(prompt)
"
```

Capture the printed prompt.

**6. Invoke the Task tool with the prompt.** Call the `Agent` / `Task` tool with:
- `subagent_type`: `general-purpose`
- `model`: `sonnet`
- `description`: `Cycle N /ux-cycle explore: <example> <persona>`
- `prompt`: the string from step 5

Wait for the subagent to complete. Its final message is the report; the findings file is the durable artifact.

**7. Read the findings.** Run via Bash:

```bash
python -c "
from pathlib import Path
from dazzle.cli.runtime_impl.ux_cycle_impl.subagent_explore import (
    ExploreRunContext, read_findings,
)
# Reconstruct context from the state_dir paths captured in step 1
ctx = ExploreRunContext(
    example_root=Path('<example_root>'),
    example_name='<example_name>',
    persona_id='<persona_id>',
    run_id='<run_id>',
    state_dir=Path('<state_dir>'),
    findings_path=Path('<findings_path>'),
    conn_path=Path('<conn_path>'),
    runner_script_path=Path('<runner_script_path>'),
)
findings = read_findings(ctx)
print(f'proposals: {len(findings.proposals)}, observations: {len(findings.observations)}')
import json
print(json.dumps(findings.to_dict(), indent=2))
"
```

**8. Tear down the runner.** Run via Bash:

```bash
pkill -TERM -f <runner_script_path> || true
```

The runner has a 20-minute safety cap anyway, but explicit teardown is cleaner. Verify `.dazzle/mode_a.lock` is released against the example.

**9. Record results.** Run via Bash — the `ingest_findings` helper handles
ID allocation, dedup, table insertion, and row formatting:

```bash
python -c "
from pathlib import Path
from dazzle.cli.runtime_impl.ux_cycle_impl.subagent_explore import (
    ExploreRunContext, read_findings,
)
from dazzle.cli.runtime_impl.ux_cycle_impl.subagent_ingest import (
    PersonaRun, ingest_findings,
)

ctxs = [  # one per persona-run in this cycle
    ExploreRunContext(
        example_root=Path('<example_root>'),
        example_name='<example_name>',
        persona_id='<persona_id>',
        run_id='<run_id>',
        state_dir=Path('<state_dir>'),
        findings_path=Path('<findings_path>'),
        conn_path=Path('<conn_path>'),
        runner_script_path=Path('<runner_script_path>'),
    ),
]
runs = [
    PersonaRun(
        persona_id=ctx.persona_id,
        run_id=ctx.run_id,
        example_name=ctx.example_name,
        findings=read_findings(ctx),
    )
    for ctx in ctxs
]
result = ingest_findings(
    backlog_path=Path('/Volumes/SSD/Dazzle/dev_docs/ux-backlog.md'),
    cycle_number=<N>,
    runs=runs,
)
print('added:', result.prop_rows_added, 'proposals,', result.ex_rows_added, 'observations')
if result.proposals_skipped_as_duplicates:
    print('dedup-skipped:', result.proposals_skipped_as_duplicates)
if result.warnings:
    print('warnings:', result.warnings)
"
```

The helper dedups proposals against existing `PROP-NNN` rows by
`component_name`, allocates fresh IDs starting from the next free
number in each table, and appends the new rows after the last existing
data row in "Proposed Components" and "Exploration Findings".

The findings in `dev_docs/ux_cycle_runs/<run>/findings.json` are
local-only (gitignored); only the backlog row updates get committed.
The log entry (`dev_docs/ux-log.md`) is still written by hand — it's
interpretive prose and doesn't benefit from automation.

**10. Commit.** Message: `ux: explore cycle {N} — {proposals} proposals, {observations} observations`. Include the run_id in the body so future diagnosticians can find the raw findings file locally if it still exists.

### Step 7: Complete

1. Delete `.dazzle/ux-cycle.lock`.
2. Call `mark_run(source="ux-cycle")` to update the signal bus.
3. Report the cycle result (component touched, outcome, next row).

## Hard rules

- **One component per cycle.** Don't chain components even if the current one completes quickly.
- **Per-phase stagnation check.** If any phase (SPECIFY / REFACTOR / QA) makes no progress for 3 minutes, abort and mark the row `BLOCKED`.
- **Lock is mandatory.** Never run a cycle without creating the lock file.
- **Commit every cycle.** Even failures commit the `notes` update and signal emission.
- **Never modify rows in the DONE/VERIFIED state directly — let the cycle move them naturally via QA.**

## Usage

```bash
# One-off cycle
/ux-cycle

# Recurring (every 30 min interval between cycles)
/loop 30m /ux-cycle

# Self-paced (model decides cadence)
/loop /ux-cycle
```
