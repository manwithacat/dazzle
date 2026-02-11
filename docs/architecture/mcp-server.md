# MCP Server

Dazzle includes a built-in Model Context Protocol (MCP) server for seamless integration with Claude Code and other AI assistants.

## Setup

```bash
# Homebrew (auto-registered on install)
brew install manwithacat/tap/dazzle

# PyPI (manual registration)
pip install dazzle-dsl
dazzle mcp setup

# Verify
dazzle mcp check
```

## Consolidated Tools

The MCP server provides **18 consolidated tools** (down from 66 original tools). Each tool uses an `operation` parameter to select the action, reducing token overhead while preserving discoverability.

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

### process

Workflow process inspection and visualization.

| Operation | Purpose |
|-----------|---------|
| `propose` | Generate process definitions from stories |
| `save` | Save process definitions |
| `list` | List all defined processes |
| `inspect` | Inspect process structure and steps |
| `list_runs` | List process execution runs |
| `get_run` | Get details of a specific run |
| `diagram` | Generate Mermaid diagrams (flowchart or state) |
| `coverage` | Process coverage analysis |

### test_design

UX test coverage and test design management.

| Operation | Purpose |
|-----------|---------|
| `propose_persona` | Generate tests from persona goals |
| `gaps` | Identify untested areas |
| `save` | Persist test designs |
| `get` | Retrieve test designs by status |
| `coverage_actions` | Get prioritized actions to increase coverage |
| `runtime_gaps` | Analyze runtime coverage report |
| `save_runtime` | Save runtime coverage report |
| `auto_populate` | Auto-populate stories and test designs |
| `improve_coverage` | Suggest coverage improvements |

### demo_data

Generate demo and seed data from DSL.

| Operation | Purpose |
|-----------|---------|
| `propose` | Generate demo data blueprint from DSL |
| `save` | Save blueprint to project |
| `get` | Retrieve current blueprint |
| `generate` | Generate CSV/JSONL demo data files |

### api_pack

External API integrations.

| Operation | Purpose |
|-----------|---------|
| `list` | List available API packs |
| `search` | Search integrations by category or provider |
| `get` | Get full API pack details |
| `generate_dsl` | Generate DSL from API pack |
| `env_vars` | Get `.env.example` content for packs |

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
| `analytics` | Infer analytics intent and data products |
| `extract_guards` | Extract guard conditions |

### graph

Knowledge graph for codebase understanding.

| Operation | Purpose |
|-----------|---------|
| `query` | Search entities by text |
| `dependencies` | What does X depend on? |
| `dependents` | What depends on X? |
| `neighbourhood` | Entities within N hops |
| `paths` | Find paths between entities |
| `stats` | Graph statistics |
| `populate` | Refresh graph from source |
| `concept` | Look up a framework concept |
| `inference` | Find inference patterns |
| `related` | Get related concepts for an entity |

### dsl_test

API-level test generation and execution.

| Operation | Purpose |
|-----------|---------|
| `generate` | Generate tests from DSL definitions |
| `run` | Run a specific test |
| `run_all` | Run all tests against a server |
| `coverage` | Show test coverage |
| `list` | List available tests |
| `create_sessions` | Create authenticated sessions for personas |
| `diff_personas` | Compare responses across personas |
| `verify_story` | Verify a story against API tests |

### e2e_test

End-to-end testing with Playwright.

| Operation | Purpose |
|-----------|---------|
| `check_infra` | Check Playwright infrastructure |
| `run` | Run E2E tests |
| `run_agent` | Run LLM-agent-powered E2E tests |
| `coverage` | E2E coverage analysis |
| `list_flows` | List test flows |
| `tier_guidance` | Get testing tier guidance for a scenario |
| `run_viewport` | Run viewport/responsive tests |

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

### pipeline

Full deterministic quality audit in a single call.

| Operation | Purpose |
|-----------|---------|
| `run` | Chain: validate, lint, fidelity, tests, coverage, semantics |

### pulse

Founder-ready project health report.

| Operation | Purpose |
|-----------|---------|
| `run` | Full report with narrative and launch readiness score |
| `radar` | Compact 6-axis readiness chart |
| `persona` | View app through a specific persona's eyes |
| `timeline` | Project timeline view |
| `decisions` | Decisions needing founder input |

### composition

Visual composition analysis.

| Operation | Purpose |
|-----------|---------|
| `audit` | DOM-level visual hierarchy audit |
| `capture` | Take section-level screenshots |
| `analyze` | LLM visual evaluation of screenshots |
| `report` | Combined audit + visual analysis |
| `bootstrap` | Generate reference library for evaluation |
| `inspect_styles` | Extract computed CSS styles |

### Additional Tools

| Tool | Purpose |
|------|---------|
| `bootstrap` | Entry point for "build me an app" requests |
| `spec_analyze` | Analyze narrative specs before DSL generation |
| `policy` | RBAC access control analysis |
| `user_management` | Manage auth users and sessions |
| `pitch` | Generate investor pitch decks |
| `contribution` | Package contributions for sharing |
| `user_profile` | Adaptive persona inference |

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

**Running quality audit:**

```
User: "How's the project health?"
Claude: [Uses pulse tool with operation=run]
        "Launch Readiness: 72%. Strengths: DSL coverage, API tests.
         Gaps: Missing persona tests, 2 surfaces below fidelity threshold."
```

**Visualizing a process:**

```
User: "Show me the order fulfillment workflow"
Claude: [Uses process tool with operation=diagram]
        "Here's a Mermaid flowchart showing the 5-step process..."
```

## Configuration

The MCP server is registered at `~/.claude/settings.json` (Claude Code) or `~/.config/claude/claude_desktop_config.json` (Claude Desktop):

```json
{
  "mcpServers": {
    "dazzle": {
      "command": "dazzle",
      "args": ["mcp", "run"]
    }
  }
}
```

For Homebrew installations, this is configured automatically via `dazzle mcp setup`.

## Internal Architecture

The MCP server uses consolidated handlers for maintainability:

```
src/dazzle/mcp/server/
├── __init__.py                  # Server setup and routing
├── tools_consolidated.py        # Tool definitions (18 consolidated tools)
├── handlers_consolidated.py     # Dispatch: operation → handler function
├── handlers/
│   ├── dsl.py                   # DSL parsing, entity/surface inspection
│   ├── knowledge.py             # Concept lookup, workflow guides
│   ├── stories.py               # Story generation, test conversion
│   ├── process.py               # Process inspection, diagrams
│   ├── test_design.py           # Test coverage, persona tests
│   ├── demo_data.py             # Demo data generation
│   ├── api_packs.py             # External API integrations
│   ├── sitespec.py              # Site specification and theming
│   ├── semantics.py             # Event-first architecture analysis
│   ├── discovery.py             # Capability discovery missions
│   ├── dsl_test.py              # API test generation and execution
│   ├── e2e_test.py              # E2E Playwright tests
│   ├── pipeline.py              # Quality audit pipeline
│   ├── pulse.py                 # Project health reports
│   ├── composition.py           # Visual composition analysis
│   └── ...
├── state.py                     # Project state management
└── progress.py                  # Progress reporting
```

## Troubleshooting

### Server not starting

```bash
# Check MCP status
dazzle mcp check

# View logs
dazzle mcp run --debug
```

### Tool not found

Ensure you have the latest version:

```bash
brew upgrade manwithacat/tap/dazzle
# or
pip install --upgrade dazzle-dsl
```

## See Also

- [CLI Reference](../reference/cli.md)
- [Architecture Overview](overview.md)
