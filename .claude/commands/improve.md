Proactively discover bugs and quality issues across Dazzle's example apps by orchestrating existing analysis tools. Read-only — no commits, no issues filed.

ARGUMENTS: $ARGUMENTS

## 1. Discover apps

Find all example apps that have a `dazzle.toml`:

```bash
ls examples/*/dazzle.toml
```

If `$ARGUMENTS` is provided, filter to only that app name (e.g. `support_tickets`). If the app doesn't exist or lacks `dazzle.toml`, report the error and stop.

## 2. Scan each app

For each app, print a progress line: `Scanning <app_name>... (N/M)`

Run these 6 steps **sequentially**. Collect findings from each step.

### Step 1: Parse & Validate

Run from the app directory:

```bash
cd examples/<app_name> && dazzle validate
```

If this fails → record a **critical** finding and **skip remaining steps** for this app.

### Step 2: Lint

Run from the app directory:

```bash
cd examples/<app_name> && dazzle lint
```

Collect any violations as **warning** findings. Continue regardless.

### Step 3: Fidelity

Call MCP tool `mcp__dazzle__select_project` with `project_name` set to the app directory path. Then call `mcp__dazzle__dsl` with `operation: "fidelity"`.

Collect any gaps or issues as **warning** findings. If the tool returns an error, log it as an **info** finding and continue.

### Step 4: Sentinel

Call `mcp__dazzle__sentinel` with `operation: "scan"`.

Collect findings. Map sentinel severity to report severity:
- sentinel high/critical → **warning**
- sentinel medium/low → **info**

If the tool returns an error, log it as an **info** finding and continue.

### Step 5: Pulse

Call `mcp__dazzle__pulse` with `operation: "run"`.

Extract the health score and per-axis scores. Map to findings:
- Any axis below 60 → **warning** finding
- Any axis below 80 (but ≥ 60) → **info** finding

If the tool returns an error, log it as an **info** finding and continue.

### Step 6: Coherence

Call `mcp__dazzle__discovery` with `operation: "coherence"`.

Collect any coherence gaps as **warning** findings. If the tool returns an error, log it as an **info** finding and continue.

## 3. Report

After scanning all apps, present results in this format:

### Per-app sections

For each app:

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
