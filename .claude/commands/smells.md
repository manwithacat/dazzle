Run a two-phase code smells analysis: regression checks against established rules, then a scan for new systemic patterns. This is a read-only analysis — do NOT make any code changes.

**This command runs as a Workflow** (`.claude/workflows/smells.js`): the regression checks and the three pattern-category finders fan out as parallel agents, each returning schema-validated findings. This main loop then writes the report + log from the validated result and presents the summary. (Replaced the hand-rolled "dispatch 4 background subagents" prose — the Workflow gives deterministic fan-out + structured output.)

## Backward Compatibility Policy

**Backward compatibility is NOT a requirement at this stage.** The project has one major user who is fully engaged with the dev process. When recommending fixes:

- **Prefer clean breaks over shims.** Delete old functions, rename freely, change signatures. Do not recommend wrapper functions, re-exports, or compatibility aliases.
- **Communicate breaking changes** via CHANGELOG.md entries and GitHub issue comments. That is sufficient notice.
- **Flag duplication caused by compat shims** as a smell. Wrapper functions that exist solely for backward compatibility are themselves a code smell to be eliminated.

(The workflow's finder prompts already encode this policy + the scope below.)

## Scope

Focus on `src/dazzle/` — the merged tree (`back/`, `ui/`, `render/` all live under it since #1056). Ignore `tests/`, `examples/`, and auto-generated files.

## 1. Run the workflow

Invoke the **Workflow** tool with `name: "smells"`. It returns:

```
{
  regressions: [{id, check, status: PASS|FAIL|TRACK, details}],
  patterns:    [{pattern, category, instances, root_cause, canonical_fix, done_criteria, enforcement}],
  regressed:   <count of FAIL regressions>
}
```

The finders inherit the session model (no `model` override) per the Subagent Model Policy in CLAUDE.md — pattern recognition is judgment work.

## 2. Write the report

From the returned data, write `agent/smells-report.md`:

```
## Code Smells Report — [date]

### Regression Check Results
| # | Check | Status | Details |
|---|-------|--------|---------|
(one row per `regressions` entry)

### New Patterns Found
| Pattern | Category | Instances | Root Cause | Fix |
|---------|----------|-----------|------------|-----|
(one row per `patterns` entry, ordered by severity × instance count)

### Recommended Next Actions
1. [highest-priority pattern]
2. [second]
3. [third]

### Comparison with Previous Round
- Regressions: X checks regressed
- New patterns: Y found
- Resolved since last round: [diff against the previous agent/smells-report.md if present]
```

## 3. Append to the log

Append a timestamped summary to `agent/smells-log.md` (create if missing):

```
## Smells Run — [date]
- Regressions: X/Y checks passed
- New patterns: Z found
- Top concern: [highest priority pattern]
- Commit: [current HEAD sha]
```

## 4. Report to the user

Present the regression table and the top patterns. **Surface any FAIL regressions first** — those are the ones that broke an established rule. Do NOT make any code changes; this is read-only analysis.
