Run a two-phase code smells analysis: regression checks against established rules, then a scan for new systemic patterns. This is a read-only analysis — do NOT make any code changes.

## Backward Compatibility Policy

**Backward compatibility is NOT a requirement at this stage.** The project has one major user who is fully engaged with the dev process. When recommending fixes:

- **Prefer clean breaks over shims.** Delete old functions, rename freely, change signatures. Do not recommend wrapper functions, re-exports, or compatibility aliases.
- **Communicate breaking changes** via CHANGELOG.md entries and GitHub issue comments. That is sufficient notice.
- **Flag duplication caused by compat shims** as a smell. Wrapper functions that exist solely for backward compatibility are themselves a code smell to be eliminated.

## Scope

Focus on `src/dazzle/`, `src/dazzle_back/`, and `src/dazzle_ui/`. Ignore `tests/`, `examples/`, and auto-generated files.

---

## Phase 1 — Regression Checks

Run each grep-able check and report **PASS** or **FAIL** with counts. These are rules established by previous smells rounds — regressions here mean a fix was undone.

### 1.1 No swallowed exceptions
```bash
grep -rn "except Exception: pass" src/ --include="*.py"
grep -rn "except Exception:$" src/ --include="*.py"  # (check next line is just pass)
```
**PASS** = 0 bare `except Exception: pass` patterns. Note: `except Exception:` followed by logging is fine.

### 1.2 No redundant except tuples
```bash
grep -rn "except (ImportError, Exception)" src/ --include="*.py"
grep -rn "except (json.JSONDecodeError, Exception)" src/ --include="*.py"
grep -rn "except (JSONDecodeError, Exception)" src/ --include="*.py"
```
**PASS** = 0 results across all three.

### 1.3 Core→MCP isolation
```bash
grep -rn "from dazzle\.mcp" src/dazzle/core/
```
**PASS** = 0 results. Core modules must not import from the MCP layer.

### 1.4 No `project_path: Any` in handlers
```bash
grep -rn "project_path: Any" src/dazzle/mcp/server/handlers/
```
**PASS** = 0 results. Handler signatures should use `Path | None`.

### 1.5 All fallback paths log at WARNING or above
Spot-check the patterns from 1.1 and 1.2. If a fallback catches a connection/runtime error, it must log at WARNING+ (not debug or silent). INFO is acceptable only for expected conditions like ImportError for optional dependencies.

### 1.5a No silent handlers in event delivery path (#365)
```bash
# Count silent except blocks (pass or bare return, no logging) in event/channel files
grep -rn "except" src/dazzle_back/events/ src/dazzle_back/channels/ --include="*.py" -A2 | grep -E "pass$|return$"
```
**PASS** = 0 silent handlers in `events/` and `channels/` directories. Event delivery failures MUST log at WARNING+.

### 1.5b getattr() with string literals (#367)
```bash
grep -rn "getattr(" src/ --include="*.py" | wc -l
```
**PASS** = count < 200. **TRACK** = report count if ≥200. Target: replace with typed attribute access on IR models.

### 1.6 Function length (aspirational)
```bash
# Count functions >150 lines in src/
```
Use AST-aware analysis or line counting between `def` statements. Report the count and list the top 5 longest functions. **Track** = report count (no pass/fail yet).

### 1.7 Class length (aspirational)
```bash
# Count classes >800 lines in src/
```
Report the count and list any offenders. **Track** = report count.

---

## Phase 2 — New Pattern Scan

Scan for **new systemic patterns** across the same categories below. Do NOT re-report issues already covered by Phase 1 regression checks.

Group findings into **patterns** (a pattern is a recurring structural issue with ≥2 instances), not individual instances. For each pattern found, provide:

| Field | Description |
|-------|-------------|
| **Pattern name** | Short descriptive name |
| **Category** | One of the categories below |
| **Instance count** | How many occurrences |
| **Root cause** | Why this pattern keeps appearing |
| **Canonical fix** | The one correct way to fix all instances |
| **Done criteria** | A grep command or check that verifies the fix |
| **Enforcement** | How to prevent recurrence (lint rule, CI check, convention) |

### Categories to scan

1. **Error handling** — silent failures, inconsistent exception strategy, missing retries on I/O
2. **Coupling** — layer violations, circular imports, inappropriate intimacy, fan-in >8
3. **Duplication** — near-duplicate blocks >10 lines, copy-paste across handlers
4. **Type safety** — `Any` where concrete types are known, `# type: ignore` masking real issues
5. **Complexity** — functions >80 lines, deeply nested conditionals (3+ levels), god classes
6. **Mutable globals** — hidden singletons, module-level mutable state, thread-unsafe patterns

### Approach

1. Use `wc -l` on source files to find the largest files (complexity hotspots).
2. Use Grep/Glob to scan systematically — don't read every file line by line.
3. Compare structurally similar files (e.g. MCP handlers, CLI commands) for duplication.
4. Focus on patterns with ≥2 instances. One-off issues are not patterns.

---

## Phase 3 — Summary Report

Produce a structured report:

```
## Code Smells Report — [date]

### Regression Check Results
| # | Check | Status | Details |
|---|-------|--------|---------|
| 1.1 | Swallowed exceptions | PASS/FAIL | count |
| 1.2 | Redundant except tuples | PASS/FAIL | count |
| 1.3 | Core→MCP isolation | PASS/FAIL | count |
| 1.4 | project_path: Any | PASS/FAIL | count |
| 1.5 | Fallback logging | PASS/FAIL | notes |
| 1.5a | Silent handlers in event path | PASS/FAIL | count |
| 1.5b | getattr() string literals | PASS/TRACK | count (target <200) |
| 1.6 | Functions >150 lines | TRACK | count, top 5 |
| 1.7 | Classes >800 lines | TRACK | count, top offenders |

### New Patterns Found
[Table of patterns from Phase 2, ordered by severity × instance count]

### Recommended Next Actions
1. [Highest priority pattern to fix]
2. [Second priority]
3. [Third priority]

### Comparison with Previous Round
- Regressions: X checks regressed
- New patterns: Y new patterns found
- Resolved since last round: [list any that are gone]
```

Save the report to `dev_docs/smells-report.md`.

Do NOT make any changes to the code. This is a read-only analysis.
