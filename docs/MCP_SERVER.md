# DAZZLE MCP Server

Model Context Protocol (MCP) server for DAZZLE integration with Claude Code and other AI tools.

## Overview

The DAZZLE MCP server exposes DAZZLE functionality as:
- **Tools**: Functions Claude can call (validate, build, inspect, etc.)
- **Resources**: Data Claude can reference (modules, entities, DSL files)
- **Prompts**: Reusable slash commands for common workflows

This enables tight integration with Claude Code while keeping users in control of their AI subscription tokens.

## Quick Start

### 1. Install DAZZLE

```bash
# If not already installed
pip install dazzle

# Or for development
cd /path/to/dazzle
pip install -e .
```

### 2. Configure Claude Code

Create `.mcp.json` in your DAZZLE project root:

```json
{
  "mcpServers": {
    "dazzle": {
      "command": "python",
      "args": ["-m", "dazzle.mcp.server"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

**Or** configure globally in `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "dazzle-global": {
      "command": "python",
      "args": ["-m", "dazzle.mcp.server"]
    }
  }
}
```

### 3. Verify Connection

In Claude Code, the DAZZLE tools should now be available. Try:

```
Use the validate_dsl tool to check my project.
```

## Available Tools

### `validate_dsl`

Validate DSL files in the current project.

**Example:**
```
Validate my DAZZLE project.
```

**Returns:**
```json
{
  "status": "valid",
  "modules": 3,
  "entities": 12,
  "surfaces": 24,
  "services": 2
}
```

### `list_modules`

List all modules with their dependencies.

**Example:**
```
Show me all modules in this project.
```

**Returns:**
```json
{
  "core": {
    "file": "dsl/core.dsl",
    "dependencies": []
  },
  "auth": {
    "file": "dsl/auth.dsl",
    "dependencies": ["core"]
  }
}
```

### `inspect_entity`

Inspect a specific entity definition.

**Parameters:**
- `entity_name` (string, required): Name of the entity

**Example:**
```
Use inspect_entity to show me the User entity.
```

**Returns:**
```json
{
  "name": "User",
  "description": "Application user",
  "fields": [
    {
      "name": "email",
      "type": "EMAIL",
      "required": true,
      "modifiers": ["unique"]
    }
  ]
}
```

### `inspect_surface`

Inspect a surface definition.

**Parameters:**
- `surface_name` (string, required): Name of the surface

**Example:**
```
Inspect the UserList surface.
```

### `build`

Build artifacts for specified stacks.

**Parameters:**
- `stacks` (array of strings, optional): Stacks to build
  - Default: `["django_micro_modular"]`
  - Options: `django_micro_modular`, `django_api`, `express_micro`, `openapi`, `docker`, `terraform`

**Example:**
```
Build the project with django_api and openapi stacks.
```

### `analyze_patterns`

Analyze the project for CRUD patterns and integrations.

**Example:**
```
Analyze patterns in my project.
```

**Returns:**
```json
{
  "crud_patterns": [
    {
      "entity": "User",
      "surfaces": ["list", "create", "edit", "view"]
    }
  ],
  "integration_patterns": [
    {
      "entity": "User",
      "service": "auth_service",
      "foreign_model": "AuthUser"
    }
  ]
}
```

### `lint_project`

Run extended validation with linting rules.

**Parameters:**
- `strict` (boolean, optional): Treat warnings as errors (default: false)

**Example:**
```
Lint the project in strict mode.
```

## Available Resources

Resources can be referenced using `@server:uri` syntax in Claude Code.

### `dazzle://project/manifest`

The `dazzle.toml` project manifest.

**Example:**
```
Show me @dazzle:dazzle://project/manifest
```

### `dazzle://modules`

List of all modules and dependencies (JSON).

**Example:**
```
What modules are in @dazzle:dazzle://modules?
```

### `dazzle://entities`

All entity definitions (JSON).

### `dazzle://surfaces`

All surface definitions (JSON).

### `dazzle://dsl/{file_path}`

Individual DSL files.

**Example:**
```
Show me @dazzle:dazzle://dsl/dsl/core.dsl
```

## Available Prompts (Slash Commands)

Prompts are reusable workflows that can be invoked as slash commands.

### `/validate`

Validate the DAZZLE project and report errors.

**Usage:**
```
/validate
```

### `/review_dsl`

Review DSL design and suggest improvements.

**Arguments:**
- `aspect` (optional): What to review - `design`, `performance`, `security`, or `all`

**Usage:**
```
/review_dsl --aspect security
```

### `/code_review`

Review generated code artifacts.

**Arguments:**
- `stack` (required): Stack to review

**Usage:**
```
/code_review --stack django_micro_modular
```

### `/suggest_surfaces`

Suggest surface definitions for an entity based on CRUD patterns.

**Arguments:**
- `entity_name` (required): Entity to suggest surfaces for

**Usage:**
```
/suggest_surfaces --entity_name User
```

### `/optimize_dsl`

Suggest optimizations for DSL based on patterns and best practices.

**Usage:**
```
/optimize_dsl
```

## Configuration Options

### Project-Specific Configuration

Create `.mcp.json` in your project root for project-specific setup:

```json
{
  "mcpServers": {
    "dazzle": {
      "command": "python",
      "args": ["-m", "dazzle.mcp.server"],
      "cwd": "${workspaceFolder}",
      "env": {
        "DAZZLE_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

Commit this file to version control so your team gets the same setup.

### User-Global Configuration

Create `~/.claude/mcp.json` for personal setup across all projects:

```json
{
  "mcpServers": {
    "dazzle": {
      "command": "python",
      "args": ["-m", "dazzle.mcp.server"]
    }
  }
}
```

### Using a Specific Python Environment

If you have DAZZLE installed in a specific virtualenv:

```json
{
  "mcpServers": {
    "dazzle": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "dazzle.mcp.server"]
    }
  }
}
```

## Example Workflows

### Analyze and Build

```
1. Validate my DAZZLE project
2. Analyze patterns
3. Build with django_micro_modular and openapi stacks
4. Show me the generated files
```

Claude will:
1. Call `validate_dsl` tool
2. Call `analyze_patterns` tool
3. Call `build` tool with specified stacks
4. List files in `build/` directory

### Review and Improve DSL

```
1. Review my DSL for security issues
2. Suggest improvements
3. Inspect the User entity
4. Suggest surfaces for the User entity
```

Claude will:
1. Use `/review_dsl --aspect security`
2. Analyze code and suggest improvements
3. Call `inspect_entity` with entity_name="User"
4. Use `/suggest_surfaces --entity_name User`

### Generate from SPEC

```
I have a SPEC.md file. Please:
1. Analyze the spec
2. Generate DSL (you'll need to write DSL files based on the spec)
3. Validate the DSL
4. Build the project
```

Claude will:
1. Read SPEC.md
2. Write DSL files based on requirements
3. Call `validate_dsl` tool
4. Call `build` tool

## Troubleshooting

### MCP Server Not Found

If Claude Code can't find the MCP server:

1. **Verify DAZZLE is installed:**
   ```bash
   python -m dazzle.mcp.server --help
   ```

2. **Check Python path:**
   ```bash
   which python
   ```

3. **Use absolute path in config:**
   ```json
   {
     "command": "/usr/local/bin/python3",
     "args": ["-m", "dazzle.mcp.server"]
   }
   ```

### Server Crashes or Errors

Check the Claude Code output panel for MCP server logs:

1. Open Command Palette (Cmd/Ctrl+Shift+P)
2. Select "Claude Code: Show MCP Output"
3. Look for `[DAZZLE MCP]` log entries

### Validation Errors

If `validate_dsl` reports errors, fix the DSL files and validate again:

```
My validation failed. Please:
1. Show me the validation errors
2. Help me fix them
3. Validate again
```

## Advanced Usage

### Custom MCP Server Wrapper

You can create a wrapper script for custom configuration:

**`~/.local/bin/dazzle-mcp`:**
```bash
#!/bin/bash
export DAZZLE_LOG_LEVEL=DEBUG
exec python -m dazzle.mcp.server "$@"
```

**`.mcp.json`:**
```json
{
  "mcpServers": {
    "dazzle": {
      "command": "/Users/you/.local/bin/dazzle-mcp"
    }
  }
}
```

### Multiple DAZZLE Versions

Use different servers for different DAZZLE versions:

```json
{
  "mcpServers": {
    "dazzle-stable": {
      "command": "/path/to/stable/venv/bin/python",
      "args": ["-m", "dazzle.mcp.server"]
    },
    "dazzle-dev": {
      "command": "/path/to/dev/venv/bin/python",
      "args": ["-m", "dazzle.mcp.server"]
    }
  }
}
```

## Architecture

The DAZZLE MCP server uses:

- **Protocol**: JSON-RPC 2.0 over stdio
- **Transport**: stdin/stdout
- **Format**: Line-delimited JSON

**Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "validate_dsl",
    "arguments": {}
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"status\": \"valid\", ...}"
      }
    ]
  }
}
```

## Contributing

To add new tools, resources, or prompts:

1. **Tools**: Add to `src/dazzle/mcp/tools.py`
2. **Resources**: Add to `src/dazzle/mcp/resources.py`
3. **Prompts**: Add to `src/dazzle/mcp/prompts.py`
4. **Implementation**: Add handler in `src/dazzle/mcp/server.py`

See the source code for examples.

## See Also

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Claude Code MCP Integration](https://code.claude.com/docs/en/mcp.md)
- [DAZZLE Documentation](../README.md)
