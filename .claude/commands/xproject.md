Cross-project quality scan across Dazzle and its sibling projects. Scouts sibling projects, fans out one read-only scan agent per project via a Workflow, then synthesizes a cross-project report.

**This command runs as a Workflow** (`.claude/workflows/xproject.js`) — one agent per project, in parallel. This main loop scouts the project list, passes it in, and writes the synthesis from the schema-validated results.

ARGUMENTS: $ARGUMENTS

## 1. Scout sibling projects (main loop)

```bash
ls /Volumes/SSD/*/dazzle.toml 2>/dev/null
```

This typically finds Dazzle (framework), AegisMark, CyFuture, and any others. Take each project **root** path (the dir containing `dazzle.toml`).

If `$ARGUMENTS` is provided, filter to only that project name. If it doesn't exist, report the error and stop.

## 2. Run the workflow

Invoke the **Workflow** tool with `name: "xproject"` and `args:` set to the JSON array of project root paths from step 1 (actual array, not a stringified one). Each per-project agent runs `dazzle validate` / `dazzle lint` + the dazzle MCP `sentinel` / `pulse` / `discovery` ops, read-only, and inherits the session model (judgment to interpret results — model-tiering, AGENTS.md Capability Mapping).

> Requires the **dazzle MCP** to be connected in this session (the agents call `mcp__dazzle__*`). If it isn't, run `/xproject` from a session where it is.

It returns `{projects: [{project, path, entities, surfaces, health, findings:[{severity, source, description}]}]}`.

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
