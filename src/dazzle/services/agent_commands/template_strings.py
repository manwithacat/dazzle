"""Python ports of the 9 agent-command markdown templates (#1049).

Pre-#1049 (v0.67.86) these were Jinja `.j2` templates rendered via
`jinja2.Environment(loader=FileSystemLoader(...))`. The migration off
jinja2 (umbrella #1042) means each template is now a Python function
that composes the same markdown via f-strings. Loops and conditionals
that the Jinja templates expressed via `{% for %}` / `{% if %}` are
now ordinary Python control flow.

Public entry points (called from `renderer.py`):

- `render_skill(cmd, ctx)` — dispatch to the right per-command template
- `render_agents_md(commands, ctx)` — AGENTS.md project root file
- `render_claude_md_section(commands, ctx)` — section appended to CLAUDE.md
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _join_or(items: list[str] | None, fallback: str = "(none declared)") -> str:
    """Mirror Jinja `xs | join(", ") if xs else fallback`."""
    if not items:
        return fallback
    return ", ".join(items)


# ---------------------------------------------------------------------------
# Per-command skill templates
# ---------------------------------------------------------------------------


def _render_ship(cmd: Any, ctx: dict[str, Any]) -> str:
    return f"""# {cmd.title} — Validate and Ship

You are running the **{cmd.name}** command for the **{ctx["project_name"]}** project.

## Goal

Run pre-flight checks, commit all staged work, push to the remote, and verify a clean worktree.

## Workflow (One-Shot)

### 1. Pre-Flight Checks

Run each check in order. Stop on any failure.

1. `git status` — confirm no unexpected untracked files
2. `dazzle validate` — DSL must parse and link cleanly
3. `dazzle lint` — no lint errors
4. MCP `sentinel.findings` — no unresolved security findings

### 2. Run Tests (if available)

If a test suite exists:
- `pytest tests/ -m "not e2e"` — unit tests must pass

If tests fail, stop and report. Do NOT push broken code.

### 3. Commit

If there are uncommitted changes:
- Stage relevant files (avoid secrets, `.env`, large binaries)
- Commit with a descriptive message summarising the changes

### 4. Push

- `git push` to the current branch's upstream
- If no upstream is set, use `git push -u origin <branch>`

### 5. Verify Clean

After pushing:
- `git status` — worktree must be clean
- If any files remain (e.g. `dist/`), commit them and push again

Report the final commit SHA and branch name.

## Available Tools

**MCP**: {_join_or(cmd.tools.mcp)}
**CLI**: {_join_or(cmd.tools.cli)}

## Rules

- Never force-push to main/master.
- Never commit `.env`, credentials, or secrets.
- If pre-flight fails, report the issue and stop — do not push.
"""


def _render_qa(cmd: Any, ctx: dict[str, Any]) -> str:
    return f"""# {cmd.title} — Quality Assurance Cycle

You are running the **{cmd.name}** command for the **{ctx["project_name"]}** project.

## Prerequisites

A running app is required (`dazzle serve`).

## Goal

Verify stories against the running application, report failures, and fix regressions.

## Cycle: Seed → Pick → Test → Assess → Commit → Loop

### 1. Seed the Backlog

If `{cmd.loop.backlog_file}` is empty, populate it by running:
- MCP `story.coverage` — list stories lacking verification
- MCP `dsl.validate` — confirm DSL is valid before testing

Append each unverified story as a `- [ ] story:<story_id>` checkbox line.

### 2. Pick

Choose the top unchecked story from `{cmd.loop.backlog_file}`.
Prioritise stories tied to critical user journeys.

### 3. Test

Verify the story against the running app:
- Use MCP `story.get` to retrieve story steps
- Execute each step against the running app
- Record pass/fail for each step

### 4. Assess

If the story fails:
- Investigate the root cause
- Make the minimal fix
- Re-run verification to confirm

If the story passes, move to the next item.

### 5. Commit

Stage and commit any fixes with a descriptive message referencing the story ID.
Append a result line to `{cmd.loop.log_file}`:
```
[YYYY-MM-DD HH:MM] story:<id> — PASS|FAIL: <summary> (commit <sha>)
```

### 6. Loop

Return to step 2. Stop after {cmd.loop.max_cycles} cycles or when the backlog is empty.

## Available Tools

**MCP**: {_join_or(cmd.tools.mcp)}
**CLI**: {_join_or(cmd.tools.cli)}

## Rules

- Test one story per cycle.
- Do not modify story definitions — only fix implementation code.
- If a failure requires a DSL change, log it as a separate backlog item.
"""


def _render_issues(cmd: Any, ctx: dict[str, Any]) -> str:
    return f"""# {cmd.title} — GitHub Issue Resolver

You are running the **{cmd.name}** command for the **{ctx["project_name"]}** project.

## Prerequisites

A GitHub remote must be configured.

## Goal

Triage open GitHub issues, pick one, investigate, fix, verify, ship, and repeat.

## Cycle: Triage → Pick → Investigate → Fix → Verify → Ship → Loop

### 1. Triage

Fetch open issues:
```bash
gh issue list --state open --limit 20
```

Skip issues labelled `future` or `wontfix`.
Categorise remaining issues by priority (bug > enhancement > chore).

### 2. Pick

Select the highest-priority unassigned issue.
Prefer bugs over enhancements, and quick fixes over large changes.

### 3. Investigate

- Read the issue description and any linked code
- Use MCP `dsl.validate` and `dsl.lint` to check current project state
- Reproduce the issue if possible

### 4. Fix

Implement the minimal fix:
- Follow the project's style guide
- Add or update tests if applicable
- Keep the change focused on the issue

### 5. Verify

- CLI: `dazzle validate` — DSL must pass
- CLI: `dazzle lint` — no new lint warnings
- `pytest tests/ -m "not e2e"` — unit tests pass

### 6. Ship

- Commit with a message referencing the issue: `fix: <description> (closes #<number>)`
- `git push`
- Close the issue:
  ```bash
  gh issue close <number> --comment "Fixed in <sha>"
  ```

Log the result to `{cmd.loop.backlog_file}`:
```
[YYYY-MM-DD HH:MM] #<number>: <title> — FIXED (commit <sha>)
```

### 7. Loop

Return to step 1. Stop after {cmd.loop.max_cycles} cycles or when no actionable issues remain.

## Available Tools

**MCP**: {_join_or(cmd.tools.mcp)}
**CLI**: {_join_or(cmd.tools.cli)}

## Rules

- One issue per cycle.
- Never force-push to main/master.
- If an issue requires a breaking change, flag it for human review instead of fixing.
- Skip issues labelled `future` unless explicitly instructed.
"""


def _render_spec_sync(cmd: Any, ctx: dict[str, Any]) -> str:
    return f"""# {cmd.title} — Spec / DSL Sync

You are running the **{cmd.name}** command for the **{ctx["project_name"]}** project.

## Goal

Synchronise the external specification document (SPEC.md) with the DSL definitions.
Identify drift between what the spec describes and what the DSL implements, then propose patches.

## Workflow (One-Shot)

### 1. Parse the Spec

Read `SPEC.md` from the project root. Extract:
- Entity names and their key fields
- Described user roles / personas
- Described workflows and user journeys

Use MCP `spec_analyze.discover_entities` to assist extraction.

### 2. Parse the DSL

Run MCP `dsl.validate` to confirm the DSL is valid.
Use MCP `dsl.inspect_entity` for each entity found in step 1.

### 3. Diff

Compare the two sides and categorise differences:
- **Spec-only**: described in SPEC.md but missing from DSL
- **DSL-only**: defined in DSL but not mentioned in SPEC.md
- **Diverged**: present in both but with conflicting details (fields, types, relationships)

### 4. Propose Patches

For each difference:
- If the DSL is behind the spec → propose DSL additions/changes
- If the spec is behind the DSL → propose spec text updates
- If genuinely conflicting → flag for human review

Present patches as clear diffs. Do NOT apply changes automatically.

### 5. Report

Output a summary table:
```
| Item       | Status     | Action Needed        |
|------------|------------|----------------------|
| Entity Foo | Spec-only  | Add to DSL           |
| Entity Bar | Diverged   | Review field types   |
```

## Available Tools

**MCP**: {_join_or(cmd.tools.mcp)}
**CLI**: {_join_or(cmd.tools.cli)}

## Rules

- Do NOT modify files without explicit user approval.
- Prefer DSL as source of truth for implementation details.
- Prefer SPEC.md as source of truth for business intent.
"""


def _render_explore(cmd: Any, ctx: dict[str, Any]) -> str:
    return f"""# {cmd.title} — Subagent-Driven UX Exploration Loop

You are running the **{cmd.name}** command for the **{ctx["project_name"]}** project.

## Goal

Autonomously explore the running app as each persona, discover UX issues
that no one has filed, and record findings to the exploration backlog.

This command is the downstream port of the framework's `/ux-cycle` step 6
(exploration substrate). It drives a stateless Playwright helper through
a Claude Code subagent — the cognitive work is billed to the outer
assistant's host subscription, not the metered SDK path.

## Cycle: Boot → Prepare → Dispatch → Ingest → Loop

### 1. Boot the app

Start the app so the subagent has a target:

```
dazzle serve &
# or
dazzle serve &
```

Wait until `http://localhost:3000` responds. The subagent will authenticate
via the framework's QA magic-link flow, so no pre-login is needed.

### 2. Prepare run contexts

Use the CLI to create the per-persona run directory, findings file, and
ModeRunner background script:

```
dazzle ux explore --all-personas --strategy edge_cases --json
```

Parse the JSON output to get, for each persona, the absolute path to
`findings.json` and the runner script. The strategies are:

- `edge_cases` — probe friction, broken states, dead-ends (default)
- `missing_contracts` — scan for uncontracted UX component patterns
- `persona_journey` — walk the persona's DSL goals end-to-end
- `cross_persona_consistency` — check visibility/scope rules match the DSL
- `regression_hunt` — sweep all workspace regions after an upgrade
- `create_flow_audit` — stress every entity's create surface

Pick the strategy most appropriate to the current pass. When in doubt
default to `edge_cases` first, then `persona_journey` for the same
persona set on the next cycle.

### 3. Dispatch subagents

For each prepared run:

1. Run the generated `runner.py` via `Bash(run_in_background=true)` so the
   ModeRunner boots and writes `conn.json`.
2. Poll for `conn.json` to exist + `ready: true`.
3. Dispatch a `Task` subagent using
   `dazzle.agent.missions.ux_explore_subagent.build_subagent_prompt` with
   the run's persona, findings path, and strategy.
4. When the subagent completes, SIGTERM the background runner.

### 4. Ingest findings

For each completed run:

1. Read `findings.json` via `read_findings(ctx)`.
2. Append new proposals and observations to `{cmd.loop.backlog_file}`
   using the standard `PROP-NNN` / `EX-NNN` row format.
3. Mark any pattern observed 3+ times as a candidate for a
   framework-level fix and note it in `{cmd.loop.log_file}`.

### 5. Loop

Return to step 2 with a different strategy (or the next persona subset).
Stop after {cmd.loop.max_cycles} cycles or when two consecutive
cycles produce fewer than 2 new findings each.

## Available Tools

**CLI**: {_join_or(cmd.tools.cli)}

## Rules

- One strategy per cycle — don't mix modes in the same subagent run.
- Subagents must write findings to the file as they go, not at the end.
- Never edit a finding after ingestion; file a new one if the situation
  has changed.
- If two cycles in a row hit the call budget without producing findings,
  stop — the reachable surface is exhausted for that strategy.
"""


def _render_polish(cmd: Any, ctx: dict[str, Any]) -> str:
    # Conditional preamble + signal blocks (Jinja `{% if cmd.signals_consume %}`).
    if cmd.signals_consume:
        signals_consume_kinds = "\n".join(
            f"- `{kind}` — if seen, re-audit any row referencing the\n"
            f"  affected surface/entity; a fix may have already resolved the issue"
            for kind in cmd.signals_consume
        )
        consume_block = f"""
### 0. Consume signals first

Before reading the backlog, check `.dazzle/signals/` for events emitted
by other loops since our last run:

```
dazzle agent signals --source {cmd.name} --consume
```

Kinds this command subscribes to:
{signals_consume_kinds}
"""
    else:
        consume_block = ""

    if cmd.signals_emit:
        signals_emit_kinds = "\n".join(f"- `{kind}`" for kind in cmd.signals_emit)
        emit_block = f"""

### 7. Emit signals

When a cycle closes the last actionable row in the backlog, emit:

```
dazzle agent signals --source {cmd.name} --emit polish-complete \\
    --payload '{{"cycle": <N>, "closed": <row_count>}}'
```

Kinds this command emits:
{signals_emit_kinds}

Downstream loops use this to know when it's safe to re-seed.
"""
    else:
        emit_block = ""

    return f"""# {cmd.title} — UX Polish Cycle

You are running the **{cmd.name}** command for the **{ctx["project_name"]}** project.

## Prerequisites

- A running app is required (`dazzle serve`).
- The project must have 3+ surfaces defined.

## Goal

Improve the UX quality of surfaces by auditing, investigating, fixing,
and verifying. One surface per cycle — quality beats throughput.

## Cycle: Audit → Triage → Pick → Investigate → Fix → Verify → Loop
{consume_block}
### 1. Audit

Assess current UX quality against the running app:

- MCP `composition.audit` — surface-level composition health
- MCP `dsl.validate` — confirm DSL integrity
- CLI: `dazzle validate`

Rank surfaces by severity.

### 2. Triage — filter out known issues

**Do NOT mark a gap actionable before checking it against known issues
and the sentinel log.** Silent false positives are the #1 wasted-cycle
source for polish.

For each new audit finding:

1. **GitHub issues** — run:
   ```
   gh issue list --state open --search "<surface-name> in:title,body" --limit 5
   ```
   If an open issue already describes the finding, mark the backlog row
   `BLOCKED` with `tracked: #NNN` in Notes. Skip to the next finding.

2. **Sentinel findings** — run:
   ```
   mcp__dazzle__sentinel operation=findings
   ```
   If the finding correlates with an existing sentinel entry (same
   surface + same category), mark the backlog row `BLOCKED` with
   `sentinel: <finding-id>`. Don't attempt a fix — the framework-side
   investigation owns it.

3. **Recently-shipped fix-committed signal** — if step 0 surfaced a
   `fix-committed` signal for this surface, re-run the audit with
   `dazzle validate --verbose` to confirm the finding is still real.
   If not, mark DONE.

Findings that survive triage become new PENDING rows in
`{cmd.loop.backlog_file}`.

### 3. Pick

Select the surface with the worst post-triage audit score from
`{cmd.loop.backlog_file}`. Mark IN_PROGRESS.

### 4. Investigate

For the selected surface:
- MCP `dsl.inspect_surface` to review its definition
- Observe the surface in the running app (click in, fill forms, watch
  for silent failures)
- Note layout issues, missing fields, confusing labels, broken
  interactions

### 5. Fix

Make targeted improvements:
- Fix layout and field ordering in the DSL
- Improve labels and descriptions
- Correct component type mismatches

**Scope rule:** if the fix requires framework changes (template macros,
widget renderers, scope resolver), DO NOT attempt them here. File a
GitHub issue, mark the backlog row BLOCKED with the issue number, and
move on. Polish operates on project-level DSL only.

### 6. Verify

After fixing:
- CLI: `dazzle validate` — DSL still valid
- CLI: `dazzle ux verify` — UX contracts pass
- Visually reconfirm the surface in the running app

Commit the fix:

```
git commit -am "polish({{surface}}): <summary>"
```

Append to `{cmd.loop.log_file}`:
```
[YYYY-MM-DD HH:MM] Polished: <surface_name> — <summary> (commit <sha>)
```
{emit_block}
### 8. Loop

Return to step 0 (consume signals). Stop after {cmd.loop.max_cycles}
cycles or when all surfaces pass audit (in which case emit
`polish-complete` and exit).

## Available Tools

**MCP**: {_join_or(cmd.tools.mcp)}
**CLI**: {_join_or(cmd.tools.cli)}

## Rules

- One surface per cycle — do not batch multiple surfaces.
- Do not change entity definitions unless required by the surface fix.
- Preserve existing field ordering unless there is a clear UX reason to
  change it.
- Triage (step 2) is non-optional. A finding that duplicates an open
  GitHub issue or sentinel entry is NOT actionable in this loop.
"""


def _render_improve(cmd: Any, ctx: dict[str, Any]) -> str:
    # Two conditional blocks: signals_consume (preamble in step 1) and
    # signals_emit (insertion in step 5). plus batch_compatible toggle in
    # step 1 + Rules section.
    if cmd.signals_consume:
        kinds = "\n".join(f"- `{kind}`" for kind in cmd.signals_consume)
        consume_block = f"""
**Consume signals first.** Check `.dazzle/signals/` for signals emitted
since our last run and act on them before touching the backlog:

```
dazzle agent signals --source {cmd.name} --consume
```

This command prints signals this command subscribes to:
{kinds}

A `ux-component-shipped` signal (for example) means the /ux-cycle loop
has just shipped a new contract — our backlog may now have gaps that
reference components we can now satisfy. Re-seed affected rows before
picking the next gap.
"""
    else:
        consume_block = ""

    if cmd.batch_compatible:
        pick_block = """5. **Pick a batch.** Group all PENDING gaps that share the same
   (gap_type, target_file, category) tuple — e.g. every lint warning
   about missing `search_fields` on a list surface. Treat the whole
   group as one work unit for this cycle. If there's only one
   matching gap, that's fine — the group is size 1.
6. Mark every gap in the batch as IN_PROGRESS with the same batch_id
   so later runs can correlate the findings."""
        batch_rule = """- One **batch** per cycle. A batch may contain multiple gaps when they
  share gap_type + target_file + category. Do not mix unrelated gap
  types in the same cycle."""
    else:
        pick_block = """5. Pick the next PENDING gap (priority: critical > warning > info,
   then by target file for locality)
6. Mark it IN_PROGRESS"""
        batch_rule = "- One fix per cycle. Do not batch unrelated changes."

    if cmd.signals_emit:
        kinds = "\n".join(f"   - `{kind}`" for kind in cmd.signals_emit)
        emit_block = f"""4. **Emit signals** so other loops notice this work:

   ```
   dazzle agent signals --source {cmd.name} --emit {cmd.signals_emit[0]} \\
       --payload '{{"gap": "<description>", "commit": "<sha>"}}'
   ```

   Kinds this command emits:
{kinds}
"""
    else:
        emit_block = ""

    return f"""# {cmd.title} — Autonomous Improvement Loop

You are running the **{cmd.name}** command for the **{ctx["project_name"]}** project.

## Overview

```
OBSERVE → ENHANCE → BUILD → VERIFY → REPORT
    ↑                         │
    │  ┌── green ─────────────┤
    │  │                      │
    │  │    red (≤3): fix → retry from BUILD
    │  │    red (>3) → DIAGNOSE → file issue → next gap
    └──┘──────────────────────┘
```

One cycle per invocation (~15 minutes). Run with `/loop 15m /{cmd.name}` for
continuous improvement.

## State Files

| File | Purpose |
|------|---------|
| `{cmd.loop.backlog_file}` | Gap status: PENDING / IN_PROGRESS / DONE / BLOCKED |
| `{cmd.loop.log_file}` | Append-only cycle log |

## Step 0: INIT (first run only)

If `{cmd.loop.backlog_file}` does not exist or has no rows, seed it:

```
dazzle agent seed {cmd.name}
```

This one-shot runs the full seeding pipeline (lint, conformance, fidelity,
story coverage, visual quality) and writes the backlog file. No manual
JSON parsing required. If `dazzle agent seed` isn't available, fall back
to running each tool manually:

- `dazzle validate` — record any validation errors
- `dazzle lint` — record lint violations
- MCP `conformance` with `operation=summary` — record conformance gaps
- MCP `dsl` with `operation=fidelity` — record fidelity gaps
- (optional, needs LLM) the `/improve` example-apps `visual_tier2_subagent` strategy — capture + CC-subagent evaluation

**Backlog format:**

```markdown
| # | Gap Type | Description | Status | Attempts | Notes |
|---|----------|-------------|--------|----------|-------|
| 1 | lint | Missing search_fields on task_list | PENDING | 0 | |
```

## Step 1: OBSERVE
{consume_block}
1. Read `{cmd.loop.backlog_file}`
2. If a gap is IN_PROGRESS with attempts < 3: resume it
3. If IN_PROGRESS with attempts ≥ 3: mark BLOCKED, file issue if
   framework-related, pick next PENDING
4. If all gaps are DONE or BLOCKED: re-seed with `dazzle agent seed
   {cmd.name}` and continue. If still empty, fall through to TRIAGE
   (Step 6).
{pick_block}

## Step 2: ENHANCE

Diagnose and repair based on gap type:

| Gap Type | Repair Location |
|----------|-----------------|
| Lint violation | Fix DSL in `dsl/*.dsl` |
| Validation error | Fix DSL syntax/structure |
| Conformance gap | Add missing `scope:` / `permit:` blocks |
| Fidelity gap | Add missing surface fields, entity fields, or ux blocks |
| Missing surface | Add a new surface definition |
| Visual quality | UI template fix (app or framework — see below) |

**Framework-level fixes** — if the repair requires changes inside the
Dazzle framework (not the project's DSL), file a GitHub issue and mark
the gap BLOCKED. Do NOT attempt framework changes from within this
loop.

**Gate:** `dazzle validate` must pass with zero new errors beyond the
known baseline.

## Step 3: BUILD

For most gaps ENHANCE is sufficient. For gaps that require code:

1. Update any affected test fixtures
2. Update template expectations if surface structure changed
3. Run `ruff check src/ tests/ --fix && ruff format src/ tests/`

**Gate:** `python -m pytest tests/ -m "not e2e" -x -q --timeout=60` —
must pass. Scope tests to the changed module; run the full suite in
VERIFY.

## Step 4: VERIFY

Run verification appropriate to the gap type:

| Gap Type | Verification |
|----------|-------------|
| Lint | `dazzle lint` — violation gone |
| Validation | `dazzle validate` — passes |
| Conformance | MCP `conformance operation=summary` — count increases |
| Fidelity | MCP `dsl operation=fidelity` — gap resolved |
| Surface | MCP `dsl operation=inspect_surface` — surface exists |
| Visual quality | re-run `/improve example-apps visual_tier2_subagent` — finding gone |

If verification fails: increment attempts, log the failure, retry
from ENHANCE (≤ 3 attempts).

## Step 5: REPORT

1. Update `{cmd.loop.backlog_file}` — mark DONE (or increment attempts)
2. Append to `{cmd.loop.log_file}`:
   ```
   ## Cycle {{N}} — {{timestamp}}
   **Gap:** {{description}}
   **Action:** {{what was done}}
   **Result:** PASS / FAIL ({{details}})
   ```
3. If verified green:
   - Stage the touched files (DSL + any test/src changes)
   - Commit with message `fix: {{description}}` — do NOT push; accumulate
     commits for human review
{emit_block}
5. **Check for new issues:** `gh issue list --state open --limit 5`. If new
   labelled-as-bug issues appeared during this cycle, pause the loop
   and hand off to `/issues` before the next OBSERVE.
6. Move to the next gap (return to OBSERVE).

## Step 6: TRIAGE (when backlog is clean)

When all gaps are DONE/BLOCKED and re-seed finds nothing:

1. `gh issue list --state open --limit 20 --json number,title,labels,author`
2. If open issues exist, delegate to `/issues` for the triage loop.
3. After `/issues` completes — or if nothing to triage — wait for the
   next scheduled run.

## Failure Policy

| Condition | Action |
|-----------|--------|
| `dazzle validate` fails | Fix DSL, retry from ENHANCE |
| Tests fail on changed code | Fix code, retry from BUILD |
| Verification still shows gap | Check if the gap definition is stale; if not, retry |
| Same failure 3 times | DIAGNOSE. If framework bug → file issue. Mark BLOCKED |
| All gaps done, no issues | "all clear" — wait for next loop cycle |

## Available Tools

**MCP**: {_join_or(cmd.tools.mcp)}
**CLI**: {_join_or(cmd.tools.cli)}

## Rules
{batch_rule}
- If a fix introduces new warnings, fix them before moving on.
- If you cannot resolve an item after two attempts, escalate — either
  mark BLOCKED with a framework-issue reference or mark `[~]` skipped.
"""


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def _render_ux_maturity(cmd: Any, ctx: dict[str, Any]) -> str:
    return f"""# {cmd.title} — Framework UX-maturity scorecard

You are running the **{cmd.name}** command for the **{ctx["project_name"]}** project.

## What this scores

This judges the **Dazzle framework** your app is built on — *does Dazzle make the
data-right UI the DEFAULT?* — not whether one screen is good. The rubric, ladder
(0 absent → 4 adaptive), the 13 criteria, and the output schema live in the
framework docs: **`docs/reference/ux-maturity.md`** (in the Dazzle repo). Two
evidence kinds that must agree: a static **capability** pass (the framework's
primitives + zero-effort defaults) and a **rendered** pass (your live UI).

## Workflow (one-shot)

### 1. Capability pass (static, deterministic)

```bash
dazzle ux maturity --json > .dazzle/ux-maturity.json
dazzle ux maturity            # human-readable table + framework backlog
```

This is boot-free and version-pinned: it scores each criterion from the installed
Dazzle's grammar/renderer. The `framework_backlog` (red/amber criteria,
leverage-ordered) is your candidate list of framework primitives worth building.

### 2. Rendered pass (drive the real app — attribution only)

Boot the app and drive it as a real user (reuse the `/ux-pass` / `dazzle ux
verify` walk — **rendered affordances only**, never type `/app/<entity>/<id>`).
Per screen, record clumsiness flags: `raw_data`, `empty_on_path`, `hunt`,
`nav_only`, `long_chain`, `deadend`, `ambiguous`. Map a *pattern* of a flag to its
criterion (see the rubric's flag→criterion table — e.g. repeated `raw_data` → 1d;
`empty_on_path` → 3d).

### 3. Attribution (the rigorous step)

For each failing criterion, decide per the rubric's **attribution rule**:
- **Authoring gap** — the right-by-default primitive existed and the author didn't
  use it. Fix in *this app's* DSL.
- **Framework gap** — it fails *despite* the author (missing primitive, only via
  `mode: custom`/custom renderer, or wrong default). **Promote to the framework
  backlog only on repetition under effort** (many screens, several via custom
  renderers). One screen is authoring; a pattern is the framework.

### 4. Roll up + report

Merge the static capability scores with the rendered evidence into the scorecard
schema (overall index, per-principle levels, `framework_backlog` keyed to the
`framework_version` from step 1). Write it to `.dazzle/ux-maturity.json`.

- **App-side findings** → fix in DSL here (or file in this app's tracker).
- **Framework-side findings** → file/upstream against Dazzle, citing the criterion
  id, the repetition evidence, and `framework_version`. Prefer requesting a native
  primitive over a bespoke `mode: custom` surface (that's the maturity signal).

## Rules
- The static `dazzle ux maturity` index is the **canonical, CI-able number**; the
  rendered pass annotates and attributes it — it does not replace it.
- Never promote a single screen to the framework backlog. Patterns only.
- Stay declarative: a missing capability is a framework RFC, not app-side custom HTML.
"""


_SKILL_RENDERERS: dict[str, Callable[[Any, dict[str, Any]], str]] = {
    "ship.md.j2": _render_ship,
    "qa.md.j2": _render_qa,
    "issues.md.j2": _render_issues,
    "spec_sync.md.j2": _render_spec_sync,
    "explore.md.j2": _render_explore,
    "polish.md.j2": _render_polish,
    "improve.md.j2": _render_improve,
    "ux_maturity.md.j2": _render_ux_maturity,
}


def render_skill(cmd: Any, ctx: dict[str, Any]) -> str:
    """Render a command's per-skill template.

    `cmd.template_file` is the canonical key (the original .j2 filename
    is kept as the lookup key for backward compatibility with the
    `loader.py` CommandDefinition shape).
    """
    renderer = _SKILL_RENDERERS.get(cmd.template_file)
    if renderer is None:
        raise KeyError(
            f"No skill renderer registered for template_file={cmd.template_file!r}. "
            f"Available: {sorted(_SKILL_RENDERERS)}"
        )
    return renderer(cmd, ctx)


# ---------------------------------------------------------------------------
# Aggregate templates — AGENTS.md and CLAUDE.md section
# ---------------------------------------------------------------------------


def render_agents_md(
    commands: list[tuple[Any, bool, str | None]],
    ctx: dict[str, Any],
) -> str:
    """Render AGENTS.md from all commands."""
    available_blocks: list[str] = []
    for cmd, available, _reason in commands:
        if not available:
            continue
        loop_block = ""
        if cmd.loop:
            loop_block = (
                f"- **Backlog**: `{cmd.loop.backlog_file}`\n"
                f"- **Log**: `{cmd.loop.log_file}`\n"
                f"- **Max cycles**: {cmd.loop.max_cycles}\n"
            )
        available_blocks.append(
            f"### /{cmd.name} — {cmd.title}\n\n"
            f"{cmd.description}\n\n"
            f"- **Pattern**: {cmd.pattern}\n"
            f"{loop_block}"
            f"- **MCP tools**: {_join_or(cmd.tools.mcp, fallback='none')}\n"
            f"- **CLI tools**: {_join_or(cmd.tools.cli, fallback='none')}\n"
        )

    upcoming_lines = [
        f"- **{cmd.name}**: {reason}" for cmd, available, reason in commands if not available
    ]
    if upcoming_lines:
        upcoming = "\n".join(upcoming_lines)
    else:
        upcoming = "All commands are available."

    available_section = "\n".join(available_blocks) if available_blocks else "(none)"

    return f"""# Agent Commands

Autonomous development commands available for this project.
Generated by `dazzle agent sync` — do not edit manually.

## Available Commands

{available_section}

## Upcoming Commands

The following commands are not yet available for this project:

{upcoming}

## Agent Tool Convention

- **MCP tools** are for stateless reads and queries (knowledge, validation, inspection).
- **CLI tools** are for process operations and writes (validate, lint, test, commit).
- Always run `dazzle validate` before committing changes.
- State files live in the `agent/` directory — backlogs, logs, and lock files.
- Loop commands use file-based locking to prevent concurrent execution.
"""


def render_claude_md_section(
    commands: list[tuple[Any, bool, str | None]],
    ctx: dict[str, Any],
) -> str:
    """Render the section to append to .claude/CLAUDE.md."""
    available_lines = [
        f"- `/{cmd.name}` — {cmd.description}" for cmd, available, _reason in commands if available
    ]
    loop_lines = [
        f"- `/{cmd.name}`: backlog at `{cmd.loop.backlog_file}`, log at `{cmd.loop.log_file}`"
        for cmd, available, _reason in commands
        if available and cmd.loop
    ]

    available_block = "\n".join(available_lines)
    loop_block = "\n".join(loop_lines)

    return f"""## Autonomous Development Commands

This project has agent commands synced by Dazzle. Run `dazzle agent sync` to update.

### Available Commands

{available_block}

### Running Loop Commands

Loop commands maintain state in the `agent/` directory:
{loop_block}

### State Files

- **Backlogs** (`agent/*-backlog.md`): Pending work items seeded by MCP tools.
- **Logs** (`agent/*-log.md`): Completed work with timestamps and commit SHAs.
- **Lock files** (`agent/*.lock`): Prevent concurrent loop execution.

### Agent Tool Convention

- MCP tools for reads: `dsl.validate`, `dsl.lint`, `story.coverage`, `composition.audit`
- CLI tools for writes: `dazzle validate`, `dazzle lint`, `pytest`, `git commit`
- Always validate before committing. One change per cycle for loop commands.
"""
