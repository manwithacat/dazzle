---
name: xproject
description: Run a read-only quality scan across Dazzle and sibling projects.
---

Cross-project quality scan across Dazzle and its sibling projects. Scout sibling
projects, scan each read-only, then synthesize a cross-project report.

Use independent subagents if the host supports them, or scan sequentially. The
optional host workflow at `.claude/workflows/xproject.js` batches the same work.

Use any invocation arguments to select a project name.

## 1. Scout sibling projects (main loop)

```bash
ls /Volumes/SSD/*/dazzle.toml 2>/dev/null
```

This typically finds Dazzle (framework), AegisMark, CyFuture, and any others. Take each project **root** path (the dir containing `dazzle.toml`).

If a project name was supplied, filter to that project. If it doesn't exist,
report the error and stop.

## 2. Scan each project

For each project, read `dazzle.toml`, run `dazzle validate` and `dazzle lint`,
then collect Sentinel, pulse, and discovery findings via the available MCP or
CLI operations. Record validation failure as critical and stop that project's
remaining checks. Missing optional probes are marked unavailable; do not
substitute another project's MCP state. A host with the workflow tool may run
`.claude/workflows/xproject.js` on the same list of roots.

For every MCP request, pass the project path explicitly or use a project-scoped
MCP process. Set health to `-1` if pulse is unavailable.

Return `{projects: [{project, path, entities, surfaces, health, findings:[{severity, source, description}]}]}`.

## 3. Compile the cross-project report (main loop)

### Per-project sections

```
### N. project_name (K findings)
**Scale:** X entities, Y surfaces
**Health:** score/100

| # | Severity | Source | Finding |
|---|----------|--------|---------|
```

### Cross-project synthesis

```
## Cross-Project Synthesis
**Projects scanned:** N | **Total findings:** N

### Shared patterns
- (findings in 2+ projects — likely framework-level issues in Dazzle itself)

### Framework impact assessment
- (Dazzle-core issues that propagate to consumers; MCP reliability issues seen across projects)

### Per-project health comparison
| Project | Health | Entities | Surfaces | Findings |
|---------|--------|----------|----------|----------|

### Recommended actions
1. **Framework fixes** (affect all projects): ...
2. **Per-project fixes**: ...
```

## 4. Prompt

End with: **"Would you like me to fix any framework-level issues, or focus on a specific project?"**

Do NOT commit, create issues, or make any changes. This is a read-only analysis.
