# MCP Server

Dazzle includes a built-in Model Context Protocol (MCP) server for seamless integration with Claude Code and other AI assistants.

## Setup

```bash
# Homebrew
brew install manwithacat/tap/dazzle

# PyPI
pip install 'dazzle-dsl[mcp]'

# Start a project-scoped stdio server for any MCP host
dazzle mcp run --working-dir /absolute/path/to/project

# Optional Claude Code registration
dazzle mcp setup --working-dir /absolute/path/to/project

# Verify
dazzle mcp check
```

## Consolidated Tools

The MCP server provides **18 consolidated tools**, plus the dev-mode `project` tool; `docs/reference/mcp-tools.md` is the generated inventory. Process work (process diagrams, demo data, API packs, mocks, perf traces) is CLI-only. Each tool uses an `operation` parameter to select the action, reducing token overhead while preserving discoverability.

### dsl

DSL parsing, validation, and introspection.

| Operation | Purpose |
|-----------|---------|
| `validate` | Parse and validate DSL files |
| `list_modules` | List project modules |
| `inspect_entity` | Examine entity definitions |
| `inspect_surface` | Examine surface definitions |
| `analyze` | Detect CRUD and integration patterns |
| `lint` | Extended validation with style checks |
| `get_spec` | Get DSL specification summary or details |
| `fidelity` | Check surface implementation fidelity |
| `list_fragments` | List UI fragments |
| `export_frontend_spec` | Export spec for frontend migration |

### knowledge

DSL concept lookup, examples, and workflow guides.

| Operation | Purpose |
|-----------|---------|
| `concept` | Look up DSL concepts and syntax |
| `examples` | Search example projects by features |
| `cli_help` | Get CLI command help |
| `workflow` | Get step-by-step workflow guides |
| `inference` | Find inference patterns |
| `get_spec` | Get DSL specification reference |

### story

Story-driven development and test generation.

| Operation | Purpose |
|-----------|---------|
| `propose` | Generate behavioural stories from DSL entities |
| `save` | Persist stories to project |
| `get` | Retrieve stories by status (use `view=wall` for board view) |
| `generate_tests` | Convert stories to test designs |
| `coverage` | Analyze story coverage |

### sitespec

Public website specification and theming.

| Operation | Purpose |
|-----------|---------|
| `get` | Get site configuration |
| `validate` | Validate site for semantic correctness |
| `scaffold` | Create default site structure |
| `coherence` | Check if site feels like a real website |
| `review` | Page-by-page spec vs rendering comparison |
| `get_copy` | Get site copy |
| `scaffold_copy` | Generate site copy |
| `review_copy` | Review site copy |
| `get_theme` | Get theme configuration |
| `scaffold_theme` | Generate theme from brand parameters |
| `validate_theme` | Validate theme |
| `generate_tokens` | Generate design tokens |
| `generate_imagery_prompts` | Generate image prompts from brand |

### semantics

Event-first architecture analysis.

| Operation | Purpose |
|-----------|---------|
| `extract` | Extract semantic elements from AppSpec |
| `validate_events` | Validate event naming and idempotency |
| `tenancy` | Infer multi-tenancy requirements |
| `compliance` | Infer compliance requirements (GDPR, PCI) |
| `analytics` | Infer analytics intent |
| `extract_guards` | Extract guard conditions |

### discovery

Capability discovery — explore a running app as a persona.

| Operation | Purpose |
|-----------|---------|
| `run` | Build and run a discovery mission |
| `report` | Get discovery results |
| `compile` | Convert observations to proposals |
| `emit` | Generate DSL from proposals |
| `status` | Check readiness |
| `verify_all_stories` | Batch verify stories against API tests |

### bootstrap

Entry point for "build me an app" requests.

| Operation | Purpose |
|-----------|---------|
| (default) | Scaffold a new app from a natural language description |

### spec_analyze

Analyze narrative specs before DSL generation.

| Operation | Purpose |
|-----------|---------|
| `discover_entities` | Extract entities from a narrative spec |
| `identify_lifecycles` | Find state machines and workflows |
| `extract_personas` | Identify user personas from descriptions |

### policy

RBAC access control analysis.

| Operation | Purpose |
|-----------|---------|
| `analyze` | Analyze access rules across surfaces |
| `conflicts` | Detect conflicting permissions |
| `coverage` | Measure RBAC coverage gaps |
| `simulate` | Simulate access for a persona/route |

## Usage Examples

**Validating a project:**

```
User: "Validate my DAZZLE project"
Claude: [Uses dsl tool with operation=validate]
        "Found 3 modules, 5 entities, 8 surfaces. All valid."
```

**Inspecting an entity:**

```
User: "What fields does the Task entity have?"
Claude: [Uses dsl tool with operation=inspect_entity, name=Task]
        "Task has 6 fields: id (uuid pk), title (str required), ..."
```

**Generating stories:**

```
User: "Propose user stories for my app"
Claude: [Uses story tool with operation=propose]
        "Generated 12 stories covering Task CRUD and status transitions..."
```
## Configuration

`dazzle mcp setup` writes to the first available Claude Code MCP config path
(`~/.config/claude-code/mcp_servers.json`, `~/.claude/mcp_servers.json`, or
`~/Library/Application Support/Claude Code/mcp_servers.json`). For example:

```json
{
  "mcpServers": {
    "dazzle": {
      "command": "/path/to/python",
      "args": ["-m", "dazzle.mcp"]
    }
  }
}
```

MCP registration is explicit for every host. `dazzle mcp setup` writes a
Claude Code entry; other hosts can launch `dazzle mcp run --working-dir` using
their own MCP configuration format.

### Per-project vs. global configuration

**Prefer a project-scoped MCP entry over a single global, framework-rooted one.**

When the server's working directory is a *framework checkout* (a clone of Dazzle
itself — no `dazzle.toml`, but `src/dazzle/` + `examples/` present), it runs in
**dev mode**: it only discovers the example apps under `examples/` and never
auto-selects one. That is correct for working *on the framework*, but if you
point one global MCP entry at the framework checkout and then open an unrelated
project, two silent traps follow (#1374):

- **Concurrent sessions no longer share one exclusive process** (#1628).
  By default each MCP process isolates state under
  `<root>/.dazzle/mcp-sessions/<session_id>/` (knowledge graph + activity log)
  and does **not** take a machine-wide exclusive lock. Agent hosts (Grok,
  Claude Code) always spawn a new stdio child per session; process uniqueness
  was the wrong isolation primitive. Optional `DAZZLE_MCP_SHARED=1` restores
  the legacy shared `.dazzle/knowledge_graph.db` + exclusive
  `.dazzle/mcp.lock` for operators who want one shared graph.
- **Other projects are mis-rooted.** A project living outside `examples/` is
  invisible to a framework-rooted server. Project tools either error ("No
  project selected…") or operate on the framework-dev install — the wrong
  knowledge graph and an unexpectedly-old `dazzle` version, so e.g. `dsl
  validate` may reject newer grammar your project legitimately uses.

Give **each project its own MCP entry** pointed at that project. Run the setup
command from that project's Python environment:

```bash
uv run dazzle mcp setup --working-dir /absolute/path/to/MyProject
```

The generated entry uses the current Python interpreter, appends a short path
hash to the project name to avoid collisions, and pins `--working-dir`:

```json
{
  "mcpServers": {
    "dazzle-MyProject-xxxxxxxx": {
      "command": "/path/to/MyProject/.venv/bin/python",
      "args": ["-m", "dazzle.mcp", "--working-dir", "/path/to/MyProject"]
    }
  }
}
```

To replace an existing global `dazzle` entry with a pinned one, run
`dazzle mcp setup --working-dir /absolute/path/to/project --name dazzle --force`
from the desired environment. Restart the MCP host afterward.

Each project-scoped entry gets its own session state (or shared lock when
`DAZZLE_MCP_SHARED=1`), its own knowledge graph, and the `dazzle` version
pinned in that project's environment. Reserve a framework-rooted entry
(`--working-dir <dazzle-checkout>`) for working *in* the framework repo, and
use `select_project` to choose among its example apps.

### Multi-session hosts and locks (#1628)

| Mode | Env | State paths | Exclusive lock |
|------|-----|-------------|----------------|
| **Default (multi-session)** | unset | `.dazzle/mcp-sessions/<id>/knowledge_graph.db` | No |
| **Shared** | `DAZZLE_MCP_SHARED=1` | `.dazzle/knowledge_graph.db` | Yes (`.dazzle/mcp.lock`) |
| **Test bypass** | `DAZZLE_MCP_SKIP_LOCK=1` | per mode | No |

- Pin a stable session directory with `DAZZLE_MCP_SESSION_ID=<name>`.
- Diagnose holders: `dazzle mcp check [--working-dir <root>] [--clear-stale]`.
  Live shared-mode contention exits **2** with `LOCK_HELD_BY_PID=<n> age=…`.
  Stale locks (dead PID) clear on next shared-mode acquire and via `--clear-stale`.
- **Avoid dual registration:** if `dazzle` is listed in both Grok
  (`~/.grok/config.toml`) and Claude (`~/.claude.json` / mcp_servers.json),
  hosts that import Claude sources may double-spawn. Prefer one registration
  per host. `dazzle mcp check` warns when both are present.

## Internal Architecture

The MCP server uses consolidated handlers for maintainability:

```
src/dazzle/mcp/server/
├── __init__.py                  # Server setup and routing
├── tools_consolidated.py        # Tool definitions (18 consolidated + 1 dev-mode)
├── handlers_consolidated.py     # Dispatch: operation → handler function
├── handlers/
│   ├── dsl.py                   # DSL parsing, entity/surface inspection
│   ├── knowledge.py             # Concept lookup, workflow guides
│   ├── stories.py               # Story generation, test conversion
│   ├── process/                # Story coverage, process proposals (CLI)
│   ├── test_design.py           # Test coverage, persona tests
│   ├── demo_data.py             # Demo data generation (CLI)
│   ├── api_packs.py             # External API integrations (CLI)
│   ├── sitespec.py              # Site specification and theming
│   ├── semantics.py             # Event-first architecture analysis
│   ├── discovery.py             # Capability discovery missions
│   ├── dsl_test.py              # API test generation and execution
│   ├── pipeline.py              # Quality audit pipeline
│   ├── policy.py                # RBAC access control analysis
│   ├── status.py                # MCP + runtime status and activity
│   └── ...
├── state.py                     # Project state management
├── progress.py                  # Progress reporting
└── activity_log.py              # Activity logging (JSONL + SQLite)
```

## Troubleshooting

### Server not starting

```bash
# Check registration + lock / multi-session diagnosis
dazzle mcp check
dazzle mcp check --working-dir /path/to/project --clear-stale

# View logs
dazzle mcp run --debug
```

If the host reports only `handshake failed: connection closed` and
`dazzle mcp check` shows `LOCK_HELD_BY_PID=…` with a live PID, either
`kill <pid>` or unset `DAZZLE_MCP_SHARED` (default multi-session does not
need an exclusive process). Exit code **2** means lock contention for agents.

### Tool not found

Ensure you have the latest version:

```bash
brew upgrade manwithacat/tap/dazzle
# or
pip install --upgrade dazzle-dsl
```

### "Another DAZZLE MCP server is already running"

A second Claude Code session can't start the MCP because the per-root lock is
already held. This usually means a **single global MCP entry rooted at a
framework checkout** is shared by every session — see
[Per-project vs. global configuration](#per-project-vs-global-configuration).
Give each project its own `--working-dir <project>` entry so it gets its own
lock. (To release a genuinely stale lock, the failure message prints the holder
PID and a `kill` command.)

### Project tools return "No project selected" or operate on the wrong version

The MCP is in **dev mode** (rooted at a framework checkout) and your project
lives outside `examples/`, so it isn't discovered. Either `select_project`
(for example apps), pass `project_path` explicitly, or — for a real project —
configure a project-scoped MCP entry as above. A framework-rooted server runs
the framework-dev `dazzle`, not your project's pinned wheel, which is why
`dsl validate` can reject grammar your project legitimately uses.

## See Also

- [CLI Reference](../reference/cli.md)
- [Architecture Overview](overview.md)
