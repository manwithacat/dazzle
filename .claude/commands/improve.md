Proactively discover bugs and quality issues across Dazzle's example apps by orchestrating existing analysis tools. Read-only — no commits, no issues filed.

**This command uses parallel subagents** — one per app — for ~Nx faster scanning.

ARGUMENTS: $ARGUMENTS

## 1. Discover apps

Find all example apps that have a `dazzle.toml`:

```bash
ls examples/*/dazzle.toml
```

If `$ARGUMENTS` is provided, filter to only that app name (e.g. `support_tickets`). If the app doesn't exist or lacks `dazzle.toml`, report the error and stop.

## 2. Scan apps in parallel

For each app, **dispatch a background subagent** using the Agent tool with `run_in_background: true`. Each subagent scans one app independently.

**Dispatch ALL app subagents in a single message** (multiple Agent tool calls) so they run concurrently. Use `model: "haiku"` for each subagent to keep cost low — these are mechanical checks, not judgment calls.

Each subagent prompt should be:

```
Scan Dazzle example app "<app_name>" for quality issues. Return findings as a JSON object.

Steps (run sequentially within this app):

1. **Validate**: Run `cd examples/<app_name> && dazzle validate`. If this fails, return: {"app": "<app_name>", "critical": true, "findings": [{"severity": "critical", "source": "validate", "detail": "<error>"}]}

2. **Lint**: Run `cd examples/<app_name> && dazzle lint`. Record any violations as severity "warning", source "lint".

3. **Fidelity**: Call mcp__dazzle__select_project with project_name "examples/<app_name>", then call mcp__dazzle__dsl with operation "fidelity". Record gaps as severity "warning", source "fidelity". On error, record as severity "info".

4. **Sentinel**: Call mcp__dazzle__sentinel with operation "scan". Map high/critical → "warning", medium/low → "info", source "sentinel". On error, record as severity "info".

5. **Pulse**: Call mcp__dazzle__pulse with operation "run". Extract health score and per-axis scores. Axis below 60 → "warning". Axis 60-79 → "info". Source "pulse". Record the overall health score. On error, record as severity "info".

6. **Coherence**: Call mcp__dazzle__discovery with operation "coherence". Record gaps as severity "warning", source "coherence". On error, record as severity "info".

Return your results as a structured summary in this exact format:
APP: <app_name>
HEALTH: <score>/100 (axis1: X, axis2: Y, ...)
FINDINGS:
- [severity] [source] description
- [severity] [source] description
(or "FINDINGS: none" if clean)

Do NOT make any changes. Read-only analysis.
```

**While waiting** for subagents, print: `Dispatched N parallel scans...`

## 3. Collect and report

As each subagent completes, collect its findings. Once ALL are done, compile the report.

### Per-app sections

For each app (ordered by finding count, descending):

```
### N. app_name (K findings)

**Health:** score/100 (Security: X, Compliance: Y, UX: Z, ...)

| # | Severity | Source | Finding |
|---|----------|--------|---------|
| 1 | warning | lint | Description of issue |
| 2 | info | sentinel | Description of issue |
```

If an app has 0 findings, show: `Clean.`

### Cross-app summary

```
## Cross-App Summary

**Apps scanned:** N | **Total findings:** N | **Critical:** N | **Warning:** N | **Info:** N

**Systemic patterns:**
- (any finding that appears in 2+ apps — these likely indicate framework-level issues)

**Recommended next steps:**
1. (prioritized action items based on severity and frequency)
```

### Severity definitions

| Level | Criteria |
|-------|----------|
| **critical** | Parse/validate failures (app won't boot) |
| **warning** | Lint violations, sentinel findings (high/critical), coherence gaps, pulse axis below 60 |
| **info** | Pulse axis below 80, sentinel findings (medium/low), tool errors |

## 4. Prompt

End with: **"Would you like me to fix any of these findings?"**

Do NOT commit, create issues, or make any changes. This is a read-only analysis.
