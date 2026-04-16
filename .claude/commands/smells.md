Run a two-phase code smells analysis: regression checks against established rules, then a scan for new systemic patterns. This is a read-only analysis — do NOT make any code changes.

**This command uses parallel subagents** — Phase 1 regression checks and Phase 2 pattern scans run concurrently across categories.

## Backward Compatibility Policy

**Backward compatibility is NOT a requirement at this stage.** The project has one major user who is fully engaged with the dev process. When recommending fixes:

- **Prefer clean breaks over shims.** Delete old functions, rename freely, change signatures. Do not recommend wrapper functions, re-exports, or compatibility aliases.
- **Communicate breaking changes** via CHANGELOG.md entries and GitHub issue comments. That is sufficient notice.
- **Flag duplication caused by compat shims** as a smell. Wrapper functions that exist solely for backward compatibility are themselves a code smell to be eliminated.

## Scope

Focus on `src/dazzle/`, `src/dazzle_back/`, and `src/dazzle_ui/`. Ignore `tests/`, `examples/`, and auto-generated files.

---

## Dispatch parallel analysis

**Dispatch ALL of these subagents in a single message** using `run_in_background: true`. Use `model: "sonnet"` — these need judgment for pattern recognition.

### Subagent 1: Regression checks (Phase 1)

```
Run regression checks on the Dazzle codebase at /Volumes/SSD/Dazzle. Report PASS or FAIL for each:

1.1 No swallowed exceptions:
  grep -rn "except Exception: pass" src/ --include="*.py"
  grep -rn "except Exception:$" src/ --include="*.py" (check next line is just pass)
  PASS = 0 bare except-pass patterns. Note: except Exception followed by logging is fine.

1.2 No redundant except tuples:
  grep -rn "except (ImportError, Exception)" src/ --include="*.py"
  grep -rn "except (json.JSONDecodeError, Exception)" src/ --include="*.py"
  grep -rn "except (JSONDecodeError, Exception)" src/ --include="*.py"
  PASS = 0 results across all three.

1.3 Core→MCP isolation:
  grep -rn "from dazzle\.mcp" src/dazzle/core/
  PASS = 0 results.

1.4 No project_path: Any in handlers:
  grep -rn "project_path: Any" src/dazzle/mcp/server/handlers/
  PASS = 0 results.

1.5 All fallback paths log at WARNING or above:
  Spot-check patterns from 1.1 and 1.2.

1.5a No silent handlers in event delivery path:
  grep -rn "except" src/dazzle_back/events/ src/dazzle_back/channels/ --include="*.py" -A2 | grep -E "pass$|return$"
  PASS = 0 silent handlers.

1.5b getattr() with string literals:
  grep -rn "getattr(" src/ --include="*.py" | wc -l
  PASS = count < 200. TRACK = report count if >=200.

1.6 Function length (aspirational):
  Count functions >150 lines in src/. Report count and top 5 longest.

1.7 Class length (aspirational):
  Count classes >800 lines in src/. Report count and any offenders.

Return results as:
REGRESSION_RESULTS:
| # | Check | Status | Details |
(one row per check)
```

### Subagent 2: Error handling & coupling patterns

```
Scan the Dazzle codebase at /Volumes/SSD/Dazzle for code smell patterns in these categories. Focus on src/dazzle/, src/dazzle_back/, src/dazzle_ui/. Ignore tests/, examples/, auto-generated files.

Categories:
1. Error handling — silent failures, inconsistent exception strategy, missing retries on I/O
2. Coupling — layer violations, circular imports, inappropriate intimacy, fan-in >8

For each pattern found (must have >=2 instances), report:
PATTERN: <name>
CATEGORY: error_handling|coupling
INSTANCES: <count>
ROOT_CAUSE: <why this keeps appearing>
CANONICAL_FIX: <the one correct way to fix>
DONE_CRITERIA: <a grep command to verify the fix>
ENFORCEMENT: <how to prevent recurrence>
```

### Subagent 3: Duplication & type safety patterns

```
Scan the Dazzle codebase at /Volumes/SSD/Dazzle for code smell patterns in these categories. Focus on src/dazzle/, src/dazzle_back/, src/dazzle_ui/. Ignore tests/, examples/, auto-generated files.

Categories:
1. Duplication — near-duplicate blocks >10 lines, copy-paste across handlers
2. Type safety — Any where concrete types are known, # type: ignore masking real issues

Approach:
- Compare structurally similar files (e.g. MCP handlers, CLI commands) for duplication
- Use Grep to find `Any` annotations and `# type: ignore` comments
- Focus on patterns with >=2 instances

For each pattern found, report:
PATTERN: <name>
CATEGORY: duplication|type_safety
INSTANCES: <count>
ROOT_CAUSE: <why>
CANONICAL_FIX: <fix>
DONE_CRITERIA: <verification command>
ENFORCEMENT: <prevention>
```

### Subagent 4: Complexity & mutable globals

```
Scan the Dazzle codebase at /Volumes/SSD/Dazzle for code smell patterns in these categories. Focus on src/dazzle/, src/dazzle_back/, src/dazzle_ui/. Ignore tests/, examples/, auto-generated files.

Categories:
1. Complexity — functions >80 lines, deeply nested conditionals (3+ levels), god classes
2. Mutable globals — hidden singletons, module-level mutable state, thread-unsafe patterns

Approach:
- Use wc -l on source files to find the largest files (complexity hotspots)
- Look for deeply nested if/for/while blocks
- Search for module-level mutable dicts/lists/sets

For each pattern found (>=2 instances), report:
PATTERN: <name>
CATEGORY: complexity|mutable_globals
INSTANCES: <count>
ROOT_CAUSE: <why>
CANONICAL_FIX: <fix>
DONE_CRITERIA: <verification command>
ENFORCEMENT: <prevention>
```

---

## Collect and compile report

Once ALL subagents complete, compile the results into:

```
## Code Smells Report — [date]

### Regression Check Results
| # | Check | Status | Details |
|---|-------|--------|---------|
(from Subagent 1)

### New Patterns Found
| Pattern | Category | Instances | Root Cause | Fix |
|---------|----------|-----------|------------|-----|
(merged from Subagents 2-4, ordered by severity × instance count)

### Recommended Next Actions
1. [Highest priority pattern to fix]
2. [Second priority]
3. [Third priority]

### Comparison with Previous Round
- Regressions: X checks regressed
- New patterns: Y new patterns found
- Resolved since last round: [list any that are gone]
```

Save the report to `agent/smells-report.md`.

Then append a timestamped summary to `agent/smells-log.md` (create if it doesn't exist):

```
## Smells Run — [date]
- Regressions: X/Y checks passed
- New patterns: Z found
- Top concern: [highest priority pattern]
- Commit: [current HEAD sha]
```

Do NOT make any changes to the code. This is a read-only analysis.
