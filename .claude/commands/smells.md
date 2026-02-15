Analyse the codebase for code smells, anti-patterns, and structural problems. Produce a prioritised report with concrete recommendations.

## Scope

Focus on `src/dazzle/` and `src/dazzle_back/` and `src/dazzle_ui/`. Ignore `tests/`, `examples/`, and auto-generated files.

## Analysis categories

Work through each category systematically. For each finding, note the file path, line range, severity (high/medium/low), and a one-sentence fix suggestion.

### 1. Complexity smells

- Functions longer than ~80 lines
- Deeply nested conditionals (3+ levels)
- Functions with more than 5 parameters
- God classes (classes with 10+ methods or 500+ lines)
- Cyclomatic complexity hotspots

### 2. Coupling and cohesion

- Circular imports or tightly coupled modules
- Classes/modules that import from too many siblings (fan-in > 8)
- Feature envy — functions that use another module's internals more than their own
- Inappropriate intimacy between modules (reaching into private attributes)

### 3. Duplication

- Near-duplicate functions or blocks (>10 lines substantially similar)
- Copy-paste patterns across handler files
- Repeated boilerplate that should be extracted to a helper

### 4. Naming and clarity

- Misleading names (function does more/less than the name suggests)
- Inconsistent naming conventions within a module
- Single-letter variables outside of comprehensions/lambdas
- Overly generic names (`data`, `result`, `info`, `item`, `obj`) in non-trivial scopes

### 5. Error handling

- Bare `except:` or `except Exception:` that swallows errors silently
- Missing error handling on I/O operations (file, network, subprocess)
- Inconsistent error propagation patterns

### 6. Architecture smells

- Layers violated (e.g. CLI importing directly from runtime internals)
- Business logic in CLI commands or route handlers instead of service layer
- Mutable global state or hidden singletons
- Configuration scattered across modules instead of centralised

### 7. Dead code

- Unused imports (beyond what ruff catches)
- Unreachable branches
- Functions/classes defined but never called
- Commented-out code blocks

### 8. Type safety

- `Any` used where a concrete type is known
- `# type: ignore` comments that mask real issues
- Missing return type annotations on public functions

## Approach

1. Use Grep and Glob to scan systematically — don't try to read every file line by line.
2. Start with the largest files (likely complexity hotspots): `wc -l src/dazzle/**/*.py | sort -rn | head -30`.
3. For duplication, compare structurally similar files (e.g. MCP handlers, CLI commands).
4. Prioritise findings by impact: things that actively cause bugs or block development rank higher than style nits.

## Output

Produce a structured report in this format:

```
## Code Smell Report

### Critical (fix soon)
| # | Category | File | Lines | Description | Suggestion |
|---|----------|------|-------|-------------|------------|
| 1 | complexity | path | L100-180 | 80-line function with 4 nested ifs | Extract into smaller helpers |

### Moderate (fix when touching)
...

### Minor (nice to have)
...

### Summary
- X critical, Y moderate, Z minor findings
- Top 3 areas needing attention: ...
- Estimated effort: ...
```

Do NOT make any changes to the code. This is a read-only analysis.
