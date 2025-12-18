# MCP Server

Dazzle includes a built-in Model Context Protocol (MCP) server for seamless integration with Claude Code and other AI assistants.

## Setup

```bash
# Homebrew (auto-registered)
brew install manwithacat/tap/dazzle

# PyPI (manual registration)
pip install dazzle
dazzle mcp-setup

# Verify
dazzle mcp-check
```

## Available MCP Tools

### Core Tools

| Tool | Purpose |
|------|---------|
| `validate_dsl` | Parse and validate DSL files |
| `list_modules` | List project modules |
| `inspect_entity` | Examine entity definitions |
| `inspect_surface` | Examine surface definitions |
| `analyze_patterns` | Detect CRUD and integration patterns |
| `lint_project` | Extended validation with style checks |
| `lookup_concept` | Look up DSL concepts and syntax |
| `find_examples` | Search example projects by features |
| `get_workflow_guide` | Get step-by-step workflow guides |
| `get_cli_help` | Get CLI command help and examples |

### Behaviour Layer Tools

Tools for working with stories, test designs, and process workflows.

| Tool | Purpose |
|------|---------|
| `get_dsl_spec` | Get complete DSL specification for story analysis |
| `propose_stories_from_dsl` | Generate behavioural stories from DSL entities |
| `save_stories` | Persist stories to project |
| `get_stories` | Retrieve stories by status |
| `generate_story_stubs` | Generate Python handler stubs from stories |
| `generate_tests_from_stories` | Convert stories to test designs |

### Process Tools

Tools for inspecting and visualizing workflow processes.

| Tool | Purpose |
|------|---------|
| `stories_coverage` | Analyze story coverage by processes |
| `propose_processes_from_stories` | Generate process definitions from stories |
| `list_processes` | List all defined processes |
| `inspect_process` | Inspect process structure and steps |
| `list_process_runs` | List process execution runs |
| `get_process_run` | Get details of a specific run |
| `get_process_diagram` | Generate Mermaid diagrams for processes |

### Test Design Tools

Tools for managing UX test coverage and test designs.

| Tool | Purpose |
|------|---------|
| `propose_persona_tests` | Generate tests from persona goals |
| `get_test_gaps` | Identify untested areas |
| `save_test_designs` | Persist test designs |
| `get_test_designs` | Retrieve test designs by status |
| `get_coverage_actions` | Get prioritized actions to increase coverage |
| `get_runtime_coverage_gaps` | Analyze runtime coverage report |
| `save_runtime_coverage` | Save runtime coverage report |

### Demo Data Tools

Tools for generating demo/seed data from DSL.

| Tool | Purpose |
|------|---------|
| `propose_demo_blueprint` | Generate demo data blueprint from DSL |
| `save_demo_blueprint` | Save blueprint to project |
| `get_demo_blueprint` | Retrieve current blueprint |
| `generate_demo_data` | Generate CSV/JSONL demo data files |

### DNR Backend Tools

| Tool | Purpose |
|------|---------|
| `list_dnr_entities` | List entities in BackendSpec |
| `get_dnr_entity` | Get detailed EntitySpec |
| `list_backend_services` | List available backend services |
| `get_backend_service_spec` | Get full ServiceSpec JSON |

### DNR UI Tools

| Tool | Purpose |
|------|---------|
| `list_dnr_components` | List UI components (primitives/patterns) |
| `get_dnr_component_spec` | Get ComponentSpec details |
| `list_workspace_layouts` | List available layout types |
| `create_uispec_component` | Create new ComponentSpec |
| `patch_uispec_component` | Modify existing ComponentSpec |
| `compose_workspace` | Wire components into workspace layout |

### GraphQL Tools

| Tool | Purpose |
|------|---------|
| `get_graphql_schema` | Get generated GraphQL SDL |
| `list_graphql_types` | List GraphQL types from BackendSpec |

### Messaging Tools

| Tool | Purpose |
|------|---------|
| `list_channels` | List messaging channels with resolution status |
| `get_channel_status` | Get detailed channel health status |
| `list_messages` | List message schemas and validation rules |
| `get_outbox_status` | Get outbox statistics |

### External API Tools

| Tool | Purpose |
|------|---------|
| `list_api_packs` | List available API packs |
| `search_api_packs` | Search for integrations by category |
| `get_api_pack` | Get full API pack details |
| `generate_service_dsl` | Generate DSL from API pack |
| `get_env_vars_for_packs` | Get .env.example content |
| `list_adapters` | List external API adapter patterns |
| `get_adapter_guide` | Get adapter implementation guide |

### Event-First Architecture Tools

| Tool | Purpose |
|------|---------|
| `extract_semantics` | Extract semantic elements from AppSpec |
| `validate_events` | Validate event naming and idempotency |
| `infer_tenancy` | Infer multi-tenancy requirements |
| `infer_compliance` | Infer compliance requirements (GDPR, PCI) |
| `infer_analytics` | Infer analytics intent and data products |

### Site Tools

| Tool | Purpose |
|------|---------|
| `get_sitespec` | Get public site configuration |
| `validate_sitespec` | Validate site for semantic correctness |
| `scaffold_site` | Create default site structure |

## Usage Examples

**Validating a project:**

```
User: "Validate my DAZZLE project"
Claude: [Uses validate_dsl tool]
        "Found 3 modules, 5 entities, 8 surfaces. All valid."
```

**Understanding structure:**

```
User: "What patterns do you see?"
Claude: [Uses analyze_patterns tool]
        "User management (full CRUD), Task tracking (list/view only)"
```

**Learning DSL:**

```
User: "How do I define a workspace?"
Claude: [Uses lookup_concept with term="workspace"]
        "A workspace composes regions for user-centric views..."
```

**Generating stories from DSL:**

```
User: "Propose user stories for my app"
Claude: [Uses propose_stories_from_dsl tool]
        "Generated 12 stories covering Task CRUD operations and status transitions..."
```

**Converting stories to test designs:**

```
User: "Generate tests from my accepted stories"
Claude: [Uses generate_tests_from_stories tool]
        "Created 8 test designs from accepted stories. Each includes login step,
        action steps, and expected outcomes derived from story acceptance criteria."
```

**Visualizing a process:**

```
User: "Show me the order fulfillment workflow"
Claude: [Uses get_process_diagram tool]
        "Here's a Mermaid flowchart showing the 5-step process with human approval
        step and error handling branches..."
```

## Internal Architecture

The MCP server is organized into domain-specific handler modules for maintainability:

```
src/dazzle/mcp/server/
├── handlers/
│   ├── __init__.py      # Re-exports all handlers
│   ├── project.py       # Project selection, validation
│   ├── dsl.py           # DSL parsing, entity/surface inspection
│   ├── knowledge.py     # Concept lookup, workflow guides
│   ├── status.py        # MCP status, DNR logs
│   ├── api_packs.py     # External API integrations
│   ├── stories.py       # Story generation, test conversion, stubs
│   └── process.py       # Process inspection, diagrams, coverage
├── tools.py             # Tool definitions
└── __init__.py          # Server setup and routing
```

Each handler module contains related tool implementations, making it easier to extend and maintain.

## Configuration

The MCP server configuration is stored at `~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dazzle": {
      "command": "dazzle",
      "args": ["mcp"]
    }
  }
}
```

For Homebrew installations, this is configured automatically.

## Troubleshooting

### Server not starting

```bash
# Check MCP status
dazzle mcp-check

# View logs
dazzle mcp --debug
```

### Tool not found

Ensure you have the latest version:

```bash
brew upgrade manwithacat/tap/dazzle
# or
pip install --upgrade dazzle
```

## See Also

- [CLI Reference](../reference/cli.md)
- [Architecture Overview](overview.md)
