Autonomous improvement loop for Dazzle example apps. Each cycle: find a gap, fix it, verify, commit, move on.

Adapted from the BDD improvement loop pattern (Penny Dreadful, 2026-03-22).

ARGUMENTS: $ARGUMENTS

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

One cycle per invocation (~15 minutes). Run with `/loop 15m /improve` for continuous improvement.

## State Files

| File | Purpose |
|------|---------|
| `dev_docs/improve-backlog.md` | Gap status: PENDING / IN_PROGRESS / DONE / BLOCKED |
| `dev_docs/improve-log.md` | Append-only cycle log |

Both in `dev_docs/` (gitignored).

## Step 0: INIT (first run only)

If `dev_docs/improve-backlog.md` does not exist:

1. Create `dev_docs/` directory if needed
2. Discover all example apps: `ls examples/*/dazzle.toml`
3. For each app, run gap analysis to seed the backlog:
   - `cd examples/{app} && dazzle validate 2>&1` — record any validation errors
   - `cd examples/{app} && dazzle lint 2>&1` — record lint violations
   - Use `mcp__dazzle__conformance` with `operation=summary` — record conformance gaps
   - Use `mcp__dazzle__dsl` with `operation=fidelity` — record fidelity gaps
4. Write `dev_docs/improve-backlog.md` with all discovered gaps as PENDING items
5. Write `dev_docs/improve-log.md` with header
6. Continue to OBSERVE

**Backlog format:**

```markdown
| # | App | Gap Type | Description | Status | Attempts | Notes |
|---|-----|----------|-------------|--------|----------|-------|
| 1 | simple_task | lint | Missing search_fields on task_list | PENDING | 0 | |
```

If `$ARGUMENTS` is provided, filter to only that app name.

## Step 1: OBSERVE

1. Read `dev_docs/improve-backlog.md`
2. If a gap is IN_PROGRESS with attempts < 3: resume it
3. If a gap is IN_PROGRESS with attempts >= 3: mark BLOCKED, file issue if framework-related, pick next PENDING
4. If all gaps DONE or BLOCKED: re-scan for new gaps (DSL may have changed), update backlog, report completion
5. Pick next PENDING gap (priority: critical > warning > info, then by app alphabetical)
6. Mark IN_PROGRESS

## Step 2: ENHANCE

Based on gap type:

**Lint violation** → Fix the DSL in `examples/{app}/dsl/*.dsl`
**Validation error** → Fix the DSL syntax/structure
**Conformance gap** → Add missing `scope:` or `permit:` blocks
**Fidelity gap** → Add missing surface fields, entity fields, or UX blocks
**Missing surface** → Add a new surface definition

**Gate:** Run `cd examples/{app} && dazzle validate 2>&1`. Must pass with zero new errors/warnings beyond the known baseline.

## Step 3: BUILD

For most gaps, ENHANCE is sufficient — the DSL change IS the fix. But for gaps that require code changes:

1. Update test fixtures if DSL changes affect conformance cases
2. Update template expectations if surface structure changed
3. Run `ruff check src/ tests/ --fix && ruff format src/ tests/`

**Gate:** `python -m pytest tests/unit/ -m "not e2e" -x -q --timeout=60` — must pass. Only run tests relevant to the changed app/code, not the full suite (speed matters in the loop).

## Step 4: VERIFY

Run verification appropriate to the gap type:

| Gap Type | Verification |
|----------|-------------|
| Lint | `cd examples/{app} && dazzle lint 2>&1` — violation should be gone |
| Validation | `cd examples/{app} && dazzle validate 2>&1` — must pass |
| Conformance | `mcp__dazzle__conformance operation=summary` — case count should increase or gap should close |
| Fidelity | `mcp__dazzle__dsl operation=fidelity` — gap should be resolved |
| Surface | `mcp__dazzle__dsl operation=inspect_surface entity_name={entity}` — surface should exist |

If verification fails: increment attempts, log the failure, retry from ENHANCE (if < 3 attempts).

## Step 5: REPORT

1. Update `dev_docs/improve-backlog.md` — mark DONE or increment attempts
2. Append to `dev_docs/improve-log.md`:
   ```
   ## Cycle {N} — {timestamp}
   **App:** {app_name}
   **Gap:** {description}
   **Action:** {what was done}
   **Result:** PASS / FAIL ({details})
   ```
3. If verified green:
   - `git add examples/{app}/` (and any changed src/ files)
   - Commit: `fix({app}): {description} — auto-verified`
   - Do NOT push — accumulate commits for human review
4. **Check for new issues:**
   - Run `gh issue list --state open --limit 5 --json number,title,labels --jq '.[] | "#\(.number) \(.title)"'`
   - If new issues exist that weren't there at cycle start:
     - Log them in `dev_docs/improve-log.md` under a `### New Issues Detected` section
     - If any are labelled `needs-triage` or look like bugs from the three teams (CyFuture, AegisMark, Penny Dreadful), **interrupt the backlog** and switch to `/issues` mode: investigate, implement, ship, close — then resume the improvement backlog
     - If they're feature requests or discussion issues, note them and continue the backlog
5. Move to next gap (return to OBSERVE)

## Failure Policy

| Condition | Action |
|-----------|--------|
| `dazzle validate` fails | Fix DSL, retry from ENHANCE |
| Tests fail on changed code | Fix code, retry from BUILD |
| Verification still shows gap | Check if gap definition is stale, retry |
| Same failure 3 times | DIAGNOSE: root-cause analysis. If framework bug → file at manwithacat/dazzle. Mark BLOCKED. |
| All gaps done | Re-scan for new gaps. If clean → report completion. |

## Scope

**What this command improves:**
- DSL quality in example apps (lint, validation, fidelity)
- RBAC completeness (conformance gaps — missing scope/permit blocks)
- Surface coverage (entities without surfaces)
- UX completeness (missing search/filter/sort/empty directives)

**What it does NOT do:**
- Modify framework source code (src/dazzle/, src/dazzle_back/, src/dazzle_ui/)
- Create new example apps
- Make changes that require human judgment (architecture decisions, new features)

## Success Criteria

After a full `/loop` run:
- At least 5-10 gaps resolved per hour
- All example apps pass `dazzle validate`
- Conformance coverage increases
- `dev_docs/improve-log.md` has a clear audit trail of every change
