Cross-project quality scan across Dazzle and its sibling projects. Dispatches one subagent per project in parallel, then synthesizes findings.

**This command uses parallel subagents** — one per sibling project — for concurrent analysis.

ARGUMENTS: $ARGUMENTS

## 1. Discover sibling projects

Scan the parent directory of the Dazzle project for sibling projects with `dazzle.toml`:

```bash
ls /Volumes/SSD/*/dazzle.toml 2>/dev/null
```

This typically finds: Dazzle (framework), AegisMark, CyFuture, and any others.

If `$ARGUMENTS` is provided, filter to only that project name. If the project doesn't exist, report the error and stop.

## 2. Dispatch parallel scans

**Dispatch one background subagent per project** in a single message. Use `model: "sonnet"` — these need judgment to interpret results.

Each subagent prompt:

```
Scan the Dazzle-based project at <project_path> for quality issues.

Steps:
1. Read dazzle.toml to understand the project (name, entities, surfaces)
2. Run: cd <project_path> && dazzle validate
   - If this fails, record as CRITICAL and stop further checks
3. Run: cd <project_path> && dazzle lint
   - Record violations as WARNING
4. Call mcp__dazzle__select_project with project_name "<project_path>"
5. Call mcp__dazzle__sentinel with operation "scan"
   - Map high/critical → WARNING, medium/low → INFO
6. Call mcp__dazzle__pulse with operation "run"
   - Extract health score and per-axis scores
   - Axis below 60 → WARNING, 60-79 → INFO
7. Call mcp__dazzle__discovery with operation "coherence"
   - Record gaps as WARNING

Return your results as:
PROJECT: <name> (<path>)
ENTITIES: <count>
SURFACES: <count>
HEALTH: <score>/100 (axis1: X, axis2: Y, ...)
FINDINGS:
- [severity] [source] description
(or "FINDINGS: none" if clean)

Do NOT make any changes. Read-only analysis.
```

## 3. Compile cross-project report

Once ALL subagents complete:

### Per-project sections

```
### N. project_name (K findings)

**Scale:** X entities, Y surfaces
**Health:** score/100 (Security: X, Compliance: Y, UX: Z, ...)

| # | Severity | Source | Finding |
|---|----------|--------|---------|
| 1 | warning | lint | Description |
```

### Cross-project synthesis

```
## Cross-Project Synthesis

**Projects scanned:** N | **Total findings:** N

### Shared patterns
- (findings that appear in 2+ projects — these likely indicate framework-level issues in Dazzle itself)

### Framework impact assessment
- (issues in Dazzle core that propagate to consumer projects)
- (MCP tool reliability issues observed across projects)

### Per-project health comparison
| Project | Health | Entities | Surfaces | Findings |
|---------|--------|----------|----------|----------|
| AegisMark | 85/100 | 38 | 42 | 12 |
| CyFuture | 78/100 | 24 | 30 | 18 |

### Recommended actions
1. **Framework fixes** (affect all projects): ...
2. **Per-project fixes**: ...
```

## 4. Prompt

End with: **"Would you like me to fix any framework-level issues, or focus on a specific project?"**

Do NOT commit, create issues, or make any changes. This is a read-only analysis.
