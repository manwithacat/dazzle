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

### External API Tools

| Tool | Purpose |
|------|---------|
| `list_adapters` | List external API adapter patterns |
| `get_adapter_guide` | Get adapter implementation guide |

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
│   └── stories.py       # Story generation, stubs
└── tool_registry.py     # Tool definitions and routing
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
