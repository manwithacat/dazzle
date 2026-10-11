# Quality Pipeline — Knowledge Patterns + Scaffolded Agent Commands

> **For agentic workers:** Use superpowers:writing-plans to create an implementation plan from this spec.

**Goal:** Encode the 4-stage quality pipeline (nightly, actions, ux-actions, full) as MCP knowledge patterns and provide `dazzle quality init` to scaffold project-specific `.claude/commands/` files from the DSL.

**Motivation:** AegisMark developed a domain-agnostic quality pipeline as Claude Code skills. The patterns benefit all Dazzle users. The MCP knowledge base is the source of truth; scaffolded command files are the per-project instantiation.

---

## Architecture

MCP knowledge (source of truth) defines the workflows and concepts. `dazzle quality init` reads the project's DSL to extract personas, workspaces, entities, and site URL, then interpolates template command files and writes them to `.claude/commands/`.

The scaffolded files are starting points — agents customize them to the domain. The knowledge patterns remain as the canonical reference.

---

## MCP Knowledge Additions

### 4 Workflow Definitions (in `cli_help.py`)

Add to the `workflows` dict in `get_workflow_guide()`:

#### `quality_nightly`
- Compare deployed Dazzle version against latest
- Run `dazzle validate` pipeline
- Launch parallel agents: pipeline validator, DSL API tester, site health checker
- Write report to `dev_docs/nightly-YYYY-MM-DD.md`
- References: `dsl(validate)`, `sentinel(scan)`, `status(mcp)`

#### `quality_actions`
- Parse nightly report for action items
- Run `sentinel(scan)`, `semantics(compliance, extract_guards, analytics)`
- Implement DSL fixes (classify, indexes, scope rules)
- Validate pipeline after each fix
- Write report to `dev_docs/actions-YYYY-MM-DD.md`
- References: `sentinel(findings)`, `semantics(compliance)`, `dsl(lint)`

#### `quality_ux`
- Phase 1a: curl-based UX evaluation against 7-point rubric (per workspace, per persona)
- Phase 1b: sequential Playwright persona journey testing
- Phase 2: implement findings by impact priority (BLOCKING > CONFUSING > NOISY > POLISH)
- Write dual-audience report to `dev_docs/ux-actions-YYYY-MM-DD.md`
- References: `test_design(gaps)`, `discovery(coherence)`

#### `quality_full`
- Run nightly → actions → ux sequentially
- Combined report, alert on critical failures only

### 2 Concept Definitions (in `semantics_kb/patterns.toml`)

#### `quality_ux_rubric`
The 7-point UX evaluation rubric:
1. **UUID visibility** — are raw UUIDs shown to users?
2. **Information density** — is the data useful at a glance?
3. **Actionability** — can users take next steps from this view?
4. **Column relevance** — are displayed fields meaningful?
5. **Data freshness** — are timestamps/dates current?
6. **Dead-end detection** — are there views with no navigation out?
7. **Sidebar coherence** — does navigation match the persona's role?

#### `quality_impact_scale`
The 4-level impact prioritization:
- **BLOCKING** — user cannot complete their task
- **CONFUSING** — user can complete but is misled or uncertain
- **NOISY** — unnecessary information or visual clutter
- **POLISH** — cosmetic improvement, no functional impact

---

## Command Templates

4 markdown files in `src/dazzle/cli/quality_templates/`:

### `nightly.md`
```markdown
# Nightly Quality Check

Run the nightly quality check for this project.

## Steps

1. Check if a newer version of dazzle-dsl is available
2. Run `dazzle validate` to verify DSL pipeline
3. Run `dazzle lint` for extended checks
4. Run `dazzle sentinel scan` for static analysis
5. Check site health: curl {site_url}/health (if configured)
6. Write report to `dev_docs/nightly-{date}.md`

## Project Context

- **Personas**: {persona_list}
- **Entities**: {entity_count} entities
- **Workspaces**: {workspace_list}
```

### `actions.md`
```markdown
# Action Items — Discover & Fix

Parse the latest nightly report and implement fixes.

## Steps

1. Read the latest `dev_docs/nightly-*.md` report
2. Run MCP tools to discover additional issues:
   - `sentinel(findings)` — static analysis findings
   - `semantics(compliance)` — compliance gaps
   - `semantics(extract_guards)` — missing guards
   - `semantics(analytics)` — analytics gaps
3. Merge and deduplicate findings
4. Prioritize by impact: BLOCKING > CONFUSING > NOISY > POLISH
5. Implement DSL fixes for each finding
6. Run `dazzle validate` after each fix to verify
7. Write report to `dev_docs/actions-{date}.md`

## Project Context

- **Entities**: {entity_list}
- **Personas**: {persona_list}
```

### `ux-actions.md`
```markdown
# UX Actions — Test & Improve User Experience

Evaluate and improve the user experience for each persona.

## Phase 1a: Workspace UX Audit (curl-based, parallelizable)

For each persona workspace, evaluate against the 7-point rubric:
1. UUID visibility — are raw UUIDs shown?
2. Information density — is data useful at a glance?
3. Actionability — can users take next steps?
4. Column relevance — are displayed fields meaningful?
5. Data freshness — are timestamps current?
6. Dead-end detection — are there views with no way out?
7. Sidebar coherence — does nav match the persona's role?

### Persona Workspaces to Evaluate

{persona_workspace_table}

## Phase 1b: Persona Journey Testing (sequential, Playwright)

For each persona, test the narrative journey:
- Login as persona → land on default workspace → drill into detail → navigate back
- Verify visual coherence across the journey

## Phase 2: Implement Findings

Group by persona story, prioritize by impact:
- **BLOCKING** — user cannot complete their task
- **CONFUSING** — user can complete but is misled
- **NOISY** — unnecessary clutter
- **POLISH** — cosmetic improvement

Write dual-audience report to `dev_docs/ux-actions-{date}.md`:
- Persona narratives for human stakeholders
- Action tables for agents
```

### `quality.md`
```markdown
# Full Quality Pipeline

Run the complete quality pipeline unattended.

## Stages

1. **Nightly** — `/nightly` (upgrade check + validate + health)
2. **Actions** — `/actions` (discover issues + implement fixes)
3. **UX** — `/ux-actions` (evaluate + improve user experience)

Run sequentially. Stop on critical failures (site down, deploy failed, pipeline broken).

Write combined report to `dev_docs/quality-{date}.md`.
```

---

## `dazzle quality init` CLI Command

### What it does

1. Parse the project's DSL to extract:
   - Persona names and descriptions
   - Workspace names and their persona assignments
   - Entity names (count + list)
   - Site URL from `dazzle.toml` (if configured)
2. Read the 4 template `.md` files from the package
3. Interpolate placeholders:
   - `{persona_list}` → bullet list of persona names
   - `{workspace_list}` → bullet list of workspace names
   - `{entity_list}` → bullet list of entity names
   - `{entity_count}` → count
   - `{persona_workspace_table}` → markdown table of persona → workspace mapping
   - `{site_url}` → from sitespec or dazzle.toml, default `http://localhost:3000`
   - `{date}` → left as literal `{date}` for runtime substitution by the agent
4. Write to `.claude/commands/nightly.md`, `actions.md`, `ux-actions.md`, `quality.md`
5. Print summary

### What it does NOT do

- No execution — it scaffolds, the agent runs
- No Playwright setup — that's the agent's responsibility
- No `dazzle quality run` CLI command — agents use `/quality` in Claude Code

---

## Relationship to Existing Tools

| Existing Tool | Role in Quality Pipeline |
|---------------|-------------------------|
| `dazzle validate` | Stage 1: pipeline validation |
| `dazzle lint` | Stage 1: extended checks |
| `dazzle sentinel scan` | Stage 2: static analysis |
| `semantics(compliance)` | Stage 2: compliance gaps |
| `semantics(extract_guards)` | Stage 2: missing guards |
| `semantics(analytics)` | Stage 2: analytics gaps |
| `dazzle pulse run` | Stage 1: health check |
| `test_design(gaps)` | Stage 3: test coverage gaps |
| `discovery(coherence)` | Stage 3: UX coherence |

No new MCP tools needed. The pipeline orchestrates existing tools.

---

## Files to Create/Modify

| File | Change |
|------|--------|
| `src/dazzle/cli/quality.py` | **Create** — `quality_app` with `init` command |
| `src/dazzle/cli/__init__.py` | **Modify** — register `quality_app` |
| `src/dazzle/cli/quality_templates/nightly.md` | **Create** — nightly template |
| `src/dazzle/cli/quality_templates/actions.md` | **Create** — actions template |
| `src/dazzle/cli/quality_templates/ux-actions.md` | **Create** — ux-actions template |
| `src/dazzle/cli/quality_templates/quality.md` | **Create** — full pipeline template |
| `src/dazzle/mcp/cli_help.py` | **Modify** — add 4 workflow definitions |
| `src/dazzle/mcp/semantics_kb/patterns.toml` | **Modify** — add ux_rubric + impact_scale concepts |
| `tests/unit/test_quality_init.py` | **Create** — test scaffolding + interpolation |
