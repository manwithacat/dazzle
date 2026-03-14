# `/improve` Command — Autonomous Bug Discovery

> **For agentic workers:** This is a Claude Code command file (`.claude/commands/improve.md`), not a Python feature. Implementation is writing the command prompt template and verifying it works against example apps.

**Goal:** Proactively discover bugs and quality issues across Dazzle's example apps by orchestrating existing analysis tools, without waiting for user reports.

**Status:** v1 — read-only analysis, report-first

---

## 1. Command Overview

**Name:** `/improve [app_name]`

**Behavior:**
- No args: scans all example apps in `examples/` that have a `dazzle.toml`
- With arg: scans only the named app (e.g. `/improve support_tickets`)
- Output: structured findings report grouped by app, with cross-app summary
- Read-only: no commits, no issues filed — user decides what to action
- Ends with: "Would you like me to fix any of these findings?"

**Not in v1:** feature discovery, example app generation, auto-fixing, scheduling, E2E/runtime testing.

## 2. Analysis Pipeline

For each example app, run these 6 steps sequentially:

| Step | Tool | What it catches | On failure |
|------|------|-----------------|------------|
| 1. Parse & Validate | `dazzle validate` (CLI, from app dir) | Syntax errors, undefined refs, type mismatches | **Hard fail** — record critical finding, skip remaining steps for this app |
| 2. Lint | `dazzle lint` (CLI, from app dir) | Style violations, naming issues, reserved keywords | Soft — collect findings, continue |
| 3. Fidelity | `dsl fidelity` (MCP) | IR round-trip integrity, missing constructs | Soft — collect findings, continue |
| 4. Sentinel | `sentinel scan` (MCP) | Failure modes: DI gaps, auth bypass, multi-tenancy leaks, business logic holes | Soft — collect findings, continue |
| 5. Pulse | `pulse run` (MCP) | 6-axis health score (architecture, security, compliance, UX, testing, data integrity) | Soft — collect score + flag any axis below threshold |
| 6. Coherence | `discovery coherence` (MCP) | Cross-construct consistency: orphan surfaces, unreachable workspaces, story/entity mismatches | Soft — collect findings, continue |

### Execution details

- **Sequential per app:** Steps run in order within each app. Apps are scanned sequentially (v1 simplicity).
- **MCP project context:** Before steps 3-6, call `select_project` MCP tool pointing to the app's directory.
- **Progress reporting:** Print a status line as each app starts: `Scanning support_tickets... (3/8)`
- **Error handling:** If an MCP tool returns an error, log it as an info-level finding ("Could not run pulse for fieldtest_hub: [error]") and continue to the next step.

## 3. Report Format

### Per-app section

```
### N. app_name (K findings)

**Health:** score/100 (Security: X, Compliance: Y, UX: Z, ...)

| # | Severity | Source | Finding |
|---|----------|--------|---------|
| 1 | warning | lint | Reserved keyword `question` used as enum value |
| 2 | warning | coherence | Surface `comment_edit` unreachable — no workspace links |
| 3 | info | sentinel | No explicit access control on Comment create |
```

Apps with 0 findings show: `Clean.`

### Cross-app summary

```
## Cross-App Summary

**Apps scanned:** N | **Total findings:** N | **Critical:** N | **Warning:** N | **Info:** N

**Systemic patterns:**
- (findings appearing in 2+ apps — likely framework-level issues)

**Recommended next steps:**
1. (prioritized action items)
```

### Severity mapping

| Level | Criteria |
|-------|----------|
| **critical** | Parse/validate failures (app won't boot) |
| **warning** | Lint violations, sentinel findings, coherence gaps, any pulse health axis below 60 |
| **info** | Pulse health axis below 80, minor coherence notes |

### Cross-app pattern detection

After all per-app reports, identify findings that appear in 2+ apps. These are likely framework-level issues rather than app-specific mistakes, and should be prioritized as they indicate systematic gaps.

## 4. Implementation

This is a single file: `.claude/commands/improve.md` — a Claude Code command prompt template.

No Python code changes. No new CLI commands. No new MCP tools. The command composes existing infrastructure:
- CLI: `dazzle validate`, `dazzle lint`
- MCP: `select_project`, `dsl fidelity`, `sentinel scan`, `pulse run`, `discovery coherence`

### File location

`.claude/commands/improve.md`

### Command template structure

```
ARGUMENTS: app_name (optional — name of a single example app to scan)

Steps:
1. Discover apps in examples/ with dazzle.toml
2. Filter to app_name if provided
3. For each app: validate → lint → fidelity → sentinel → pulse → coherence
4. Present per-app findings report
5. Compute cross-app summary (systemic patterns in 2+ apps)
6. Ask user what to action
```

## 5. Future Versions

**v2 candidates** (not in scope, listed for context):
- E2E smoke testing (boot app, hit endpoints)
- Story/process coverage analysis (steps 7-8 from pipeline)
- Feature discovery via cross-app pattern analysis
- Example app expansion (generate new apps covering untested domains)
- Auto-fix for low-risk findings (lint, missing surfaces)
- Scheduled execution via `/loop`
- Persistent findings between runs (diff against previous scan)
