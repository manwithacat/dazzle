# Agent-First Development Commands

> **For agentic workers:** This spec defines autonomous development commands that ship with `dazzle-dsl` and are projected into user projects for agent consumption.

**Goal:** Deploy a set of autonomous, agent-first development commands that Dazzle's frontier users can apply to their domains — and that evolve automatically as the framework adds new capabilities.

**Architecture:** MCP-canonical definitions with local file projection. Command definitions ship in the Dazzle package, are served dynamically by a new `agent_commands` MCP tool, and projected into user projects as `.claude/commands/` skill files + `AGENTS.md`.

---

## 1. Problem Statement

Dazzle has 11 autonomous development commands (`/ux-cycle`, `/issues`, `/improve`, etc.) that operate on the framework codebase itself. These leverage rich infrastructure — fitness engines, discovery runs, conformance checks, backlog-driven loops — that already works on any Dazzle user project via `dazzle` CLI and MCP tools.

But frontier users don't get the orchestration layer. Their projects ship with a passive CLAUDE.md ("here's how to use the CLI") and no autonomous workflows. An agent working on a user project today is entirely reactive — it never proactively discovers quality gaps, tests drift, or conformance failures.

### Anti-pattern: scaffolded-and-forgotten

Static command files dropped at project init go stale. As the framework adds new MCP tools, CLI commands, and quality engines, agents locked into v1 commands miss new capabilities. The design must solve for continuous evolution.

## 2. Design Principles

1. **Agents are the primary consumer.** Commands are designed for autonomous AI agents, not humans typing in terminals.
2. **MCP is the source of truth.** Command definitions live in the Dazzle package and are served dynamically. Local files are a regenerable cache.
3. **Project-aware filtering.** Commands appear only when the project meets maturity prerequisites. A one-entity project shouldn't see `/polish`.
4. **Git-tracked cognitive trail.** Backlogs, logs, and plans live in `agent/` and are committed to git. The historical record of agent cognition is valuable.
5. **Evolution over scaffolding.** Session-start version checks and signal-based notifications ensure agents discover new capabilities as the framework evolves.

## 3. Architecture

```
┌─────────────────────────────────────────────────┐
│  Canonical Definitions (ships with dazzle-dsl)  │
│  src/dazzle/cli/agent_commands/definitions/     │
│  improve.toml, qa.toml, ship.toml, ...          │
└──────────────────────┬──────────────────────────┘
                       │ served by
┌──────────────────────▼──────────────────────────┐
│  MCP Tool: agent_commands                        │
│  Operations: list, get, check_updates             │
│  Filters by: project maturity, dazzle version    │
│  Returns: command metadata + full skill content   │
└──────────────────────┬──────────────────────────┘
                       │ projected to
┌──────────────────────▼──────────────────────────┐
│  Local Files (in user's project)                 │
│  .claude/commands/*.md   — Claude Code skills    │
│  AGENTS.md               — Cross-tool convention │
│  agent/                  — Backlog + log files   │
└─────────────────────────────────────────────────┘
```

### Flow

1. **Bootstrap** (new project): `dazzle bootstrap` response includes instruction to run `dazzle agent sync`. Agent executes it, producing initial local files.
2. **Session start**: CLAUDE.md instructs agent to call `mcp__dazzle__agent_commands operation=check_updates`. If newer versions exist, agent runs `dazzle agent sync`.
3. **Framework upgrade**: When `pip install --upgrade dazzle-dsl` brings new/updated commands, first `dazzle validate` emits a `commands-updated` signal. Next agent session picks it up and syncs.
4. **Command execution**: Agent reads local `.claude/commands/{name}.md` skill file and follows the orchestration pattern, calling MCP tools + CLI commands as directed.

### Key constraint

Local files are a **cache**, not the source of truth. They can be deleted and regenerated at any time via `dazzle agent sync`. But they are the execution surface — agents read and follow them directly.

## 4. Canonical Command Definitions

Each command is a TOML file in `src/dazzle/cli/agent_commands/definitions/`. TOML is the natural fit — Dazzle already uses it for `dazzle.toml`, `core.toml` (semantics KB), and project configuration.

### Schema

```toml
[command]
name = "improve"
version = "1.0.0"
title = "Autonomous Improvement Loop"
description = "Discovers quality gaps in the project and fixes one per cycle."
pattern = "loop"  # loop | one-shot

[maturity]
min_entities = 1
requires_running_app = false
requires = ["validate"]  # dazzle validate must pass

[loop]
backlog_file = "agent/improve-backlog.md"
log_file = "agent/improve-log.md"
lock_file = ".dazzle/improve.lock"
max_cycles = 50
stale_lock_minutes = 30

[tools]
mcp = ["dsl.lint", "dsl.validate", "conformance.gaps", "test_intelligence.coverage", "story.coverage"]
cli = ["dazzle validate", "dazzle lint", "dazzle test run"]

[skill_template]
file = "improve.md.j2"
```

### Command Inventory

| Definition | Pattern | Maturity Gate |
|------------|---------|---------------|
| `improve.toml` | loop | 1+ entities, validate passes |
| `qa.toml` | loop | 1+ stories, app can serve |
| `spec-sync.toml` | one-shot | SPEC.md exists |
| `ship.toml` | one-shot | validate passes |
| `polish.toml` | loop | 3+ surfaces, app can serve |
| `issues.toml` | loop | GitHub remote configured |

## 5. MCP `agent_commands` Tool

New handler at `src/dazzle/mcp/server/handlers/agent_commands.py` with three read-only operations. File writing is handled by `dazzle agent sync` (CLI), respecting ADR-0002 (MCP = reads, CLI = writes).

### `list`

Returns all commands with availability status for the current project.

```json
{
  "commands": [
    {
      "name": "improve",
      "version": "1.0.0",
      "title": "Autonomous Improvement Loop",
      "pattern": "loop",
      "description": "Discovers quality gaps...",
      "available": true,
      "reason": null
    },
    {
      "name": "polish",
      "version": "1.0.0",
      "title": "UX Polish Cycle",
      "pattern": "loop",
      "available": false,
      "reason": "Requires 3+ surfaces (project has 1)"
    }
  ],
  "dazzle_version": "0.56.0",
  "commands_version": "1.0.0"
}
```

Unavailable commands are listed with a reason — agents can see what project milestones unlock new capabilities.

### `get`

Returns the full rendered skill content for a single command. The Jinja2 template is rendered with current AppSpec context (entity names, personas, surfaces). Output is what gets written to `.claude/commands/{name}.md`.

### `check_updates`

Lightweight version comparison. Agent passes its local `commands_version` from `.manifest.json`. MCP responds with `up_to_date: true/false` and a changelog of what changed. Designed for session-start checks — fast, minimal payload.

### File writing (CLI only)

The `dazzle agent sync` CLI command handles all file writes. It calls the renderer module directly (no MCP server dependency) to evaluate maturity gates, render templates, and write `.claude/commands/`, `AGENTS.md`, and `agent/` backlog files. The MCP `agent_commands` tool is read-only — it tells agents what's available but never writes to disk.

## 6. The Six Commands

### `/improve` (loop)

The flagship command. Discovers one quality gap per cycle, fixes it, verifies the fix, commits.

**Cycle:**
1. **Seed** (first run only) — calls `dsl.lint`, `conformance.gaps`, `story.coverage`, `test_intelligence.coverage` to populate `agent/improve-backlog.md`
2. **Pick** — highest priority gap from backlog (bugs > coverage gaps > lint warnings > enhancements)
3. **Fix** — edit DSL, templates, or app code to address the gap
4. **Verify** — re-run the tool that found the gap, confirm it's resolved
5. **Commit** — descriptive message referencing the gap ID
6. **Log** — append cycle result to `agent/improve-log.md`
7. **Loop** — return to step 2

### `/qa` (loop)

Quality verification against the running app. Requires `dazzle serve`.

**Cycle:**
1. **Seed** — story coverage + conformance checks populate `agent/qa-backlog.md`
2. **Pick** — untested story or failing conformance case
3. **Test** — generate test via `dazzle test generate`, run it, observe result
4. **Fix** (if failure is a real bug) — fix the DSL/code, re-test
5. **Report** (if failure is a test design issue) — note in backlog, move on
6. **Commit + Log**

### `/spec-sync` (one-shot)

Detects drift between SPEC.md and the DSL, proposes patches to either.

**Steps:**
1. Parse SPEC.md for stated entities, personas, workflows
2. Parse DSL via `dsl.validate` for actual entities, personas, surfaces
3. Diff — what's in spec but not DSL? What's in DSL but not spec?
4. For spec-ahead items: propose DSL additions
5. For DSL-ahead items: propose SPEC.md updates
6. Present the diff, apply approved patches, commit

### `/ship` (one-shot)

Project-level commit + validate + push discipline.

**Steps:**
1. `dazzle validate` — must pass
2. `dazzle lint` — fix any warnings
3. Run project tests if they exist
4. Stage, commit with descriptive message
5. Push to remote

### `/polish` (loop)

UX improvement cycle. Requires a running app and 3+ surfaces.

**Cycle:**
1. **Audit** — call `composition.audit` + `discovery.coherence` to find UX gaps
2. **Pick** — worst-scoring surface or persona experience
3. **Investigate** — load the surface, check responsiveness, empty states, error handling, persona-specific rendering
4. **Fix** — DSL adjustments, template overrides, sitespec tweaks
5. **Verify** — re-run the audit, confirm improvement
6. **Commit + Log**

### `/issues` (loop)

GitHub issue triage and resolution.

**Cycle:**
1. **Triage** — `gh issue list`, check for already-resolved issues, close stale ones
2. **Pick** — highest priority open issue
3. **Investigate** — read issue, search codebase, identify root cause
4. **Fix** — implement the fix
5. **Verify** — run tests, validate
6. **Ship** — commit referencing issue number, push, close issue

## 7. Sync Mechanism

### `dazzle agent sync` CLI command

```
dazzle agent sync
  ├── Parse AppSpec (dsl/*.dsl + dazzle.toml)
  ├── Evaluate maturity gates for each command
  ├── For each available command:
  │   ├── Render skill template with project context
  │   ├── Write .claude/commands/{name}.md
  │   └── Write version header: <!-- dazzle-agent-command:{name}:v{version} -->
  ├── Generate AGENTS.md from all available commands
  ├── Seed empty backlog files in agent/ (if not already present)
  ├── Append "Autonomous Development Commands" section to .claude/CLAUDE.md
  └── Write .claude/commands/.manifest.json
```

### `.manifest.json`

```json
{
  "dazzle_version": "0.56.0",
  "commands_version": "1.0.0",
  "synced_at": "2026-04-16T14:30:00Z",
  "commands": {
    "improve": {"version": "1.0.0", "available": true},
    "qa": {"version": "1.0.0", "available": true},
    "polish": {"version": "1.0.0", "available": false, "reason": "Requires 3+ surfaces"}
  }
}
```

### Session-start discovery

The generated CLAUDE.md instructs agents:

> At the start of each session, call `mcp__dazzle__agent_commands operation=check_updates` with the current `commands_version` from `.claude/commands/.manifest.json`. If updates are available, run `dazzle agent sync` before proceeding.

### Signal-based notification

When a new Dazzle release adds or updates command definitions, the first `dazzle validate` (or any CLI command) on the upgraded version emits a `commands-updated` signal. The next agent session that checks signals picks it up and syncs.

### AGENTS.md generation

A single file at project root, generated from the same command definitions:

```markdown
# Agent Commands

This project uses Dazzle autonomous development commands.
Run `dazzle agent sync` to update.

## Available Commands

### /improve
Discovers quality gaps and fixes one per cycle.
Tools: dazzle validate, dazzle lint, mcp dsl.lint, mcp conformance.gaps
Backlog: agent/improve-backlog.md
Pattern: loop

### /qa
...
```

This gives Copilot, Cursor, Windsurf, and Codex agents enough context to understand what's available, even though the full orchestration skill files are Claude Code-specific.

## 8. Bootstrap Integration

The existing `bootstrap` MCP tool is extended to detect missing agent commands:

```python
if not (project_root / ".claude" / "commands" / ".manifest.json").exists():
    agent_instructions["setup_agent_commands"] = {
        "action": "Run `dazzle agent sync` to install autonomous development commands",
        "priority": "before_first_commit"
    }
```

This is a nudge, not magic — the agent reads the instruction and runs the sync. Keeps bootstrap stateless (MCP boundary respected).

### What bootstrap does NOT do

- Does not auto-run sync (the agent decides when)
- Does not modify `.gitignore` (the `agent/` directory is tracked by design)
- Does not write command files directly (always goes through `dazzle agent sync`)

## 9. File Layout

### In the Dazzle package (`src/dazzle/`)

```
cli/
  agent_commands/
    __init__.py              # CLI entry point for `dazzle agent sync`
    definitions/
      improve.toml
      qa.toml
      spec_sync.toml
      ship.toml
      polish.toml
      issues.toml
    templates/
      improve.md.j2
      qa.md.j2
      spec_sync.md.j2
      ship.md.j2
      polish.md.j2
      issues.md.j2
      agents_md.j2           # AGENTS.md template
      claude_md_section.j2   # Section appended to CLAUDE.md
    renderer.py              # Template rendering + maturity gate evaluation
    models.py                # CommandDefinition, MaturityGate, SyncManifest
mcp/
  server/
    handlers/
      agent_commands.py      # MCP handler for agent_commands tool
```

### In a user project (after `dazzle agent sync`)

```
project_root/
  AGENTS.md                          # Cross-tool agent instructions
  agent/
    improve-backlog.md               # Gap tracking (git-tracked)
    improve-log.md                   # Cycle history (git-tracked)
    qa-backlog.md
    qa-log.md
    polish-backlog.md
    polish-log.md
    issues-log.md
  .claude/
    CLAUDE.md                        # Augmented with agent commands section
    commands/
      .manifest.json                 # Sync state
      improve.md                     # Claude Code skill
      qa.md
      spec-sync.md
      ship.md
      polish.md
      issues.md
  .dazzle/
    improve.lock                     # Runtime locks (gitignored)
    qa.lock
    polish.lock
    issues.lock
```

## 10. Testing Strategy

### Unit tests — command definitions (`tests/unit/test_agent_commands.py`)

- All TOML definitions parse without error
- Maturity gates evaluate correctly for various mock AppSpecs
- Templates render valid markdown with minimal AppSpec context
- Version fields are valid semver strings

### Unit tests — MCP handler (`tests/unit/test_agent_commands_handler.py`)

- `list` filters by maturity, returns correct structure
- `get` renders skill content for specific commands
- `check_updates` detects stale vs current versions
- `sync` produces expected file tree

### Integration tests — sync CLI (`tests/unit/test_agent_sync.py`)

- Sync creates `.claude/commands/*.md` for each available command
- Sync creates `.manifest.json` with correct versions
- Sync creates `AGENTS.md` at project root
- Sync seeds empty `agent/*.md` backlog files for loop commands
- Sync is idempotent (running twice produces identical output)
- Sync preserves existing backlog content (does not overwrite)
- Sync appends to CLAUDE.md without duplicating the section

### Not tested

Command orchestration logic (the cycle patterns themselves) is not tested as code — it's markdown instructions executed by agents. The individual MCP tools and CLI commands that commands reference are already tested independently.

## 11. Agent Tool Convention

The backlog + log pattern used by the six shipped commands is a general-purpose convention for any agent-developed tooling in a Dazzle project. The generated CLAUDE.md includes a convention section that establishes this norm:

```markdown
### Agent Tool Convention

When developing new autonomous workflows for this project, follow the
established pattern:

- **Backlog**: `agent/{tool-name}-backlog.md` — markdown table tracking
  items to process. Columns vary by tool, but always include an ID,
  status (PENDING/IN_PROGRESS/DONE/BLOCKED), and notes.
- **Log**: `agent/{tool-name}-log.md` — append-only cycle history.
  Each entry records timestamp, what was attempted, and outcome.
- Both files are git-tracked. The historical record of agent cognition
  and decision-making is valuable for project understanding.
```

This is descriptive, not prescriptive. The six shipped commands demonstrate the pattern concretely; the convention section names it explicitly so agents developing new tools default to it. Column schemas, cycle structures, and status progressions vary by tool — the invariant is: named markdown files in `agent/`, tabulated state, append-only history, committed to git.

The `claude_md_section.j2` template includes this convention alongside the command listing.

## 12. Scope and Non-Goals

### In scope

- Command definition format (TOML + Jinja2 templates)
- MCP `agent_commands` handler (4 operations)
- `dazzle agent sync` CLI command
- Six command skill templates
- AGENTS.md generation
- CLAUDE.md augmentation
- Bootstrap integration (nudge)
- Session-start version check pattern
- Signal-based update notification
- Backlog/log file seeding in `agent/`
- Tests for all of the above

### Out of scope

- Migrating framework-level `dev_docs/` to `agent/` (separate effort)
- Custom user-defined commands (future — user adds their own TOML definitions)
- Command composition (chaining `/improve` → `/ship` automatically)
- Metrics/telemetry on command usage
- GUI for command status (the backlog files serve this purpose)
