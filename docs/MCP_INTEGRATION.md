# DAZZLE MCP Server Integration

**Model Context Protocol (MCP) Integration for Claude Code**

DAZZLE includes a built-in MCP server that provides Claude Code with direct access to DAZZLE tooling and project context.

---

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Available Tools](#available-tools)
- [Usage Examples](#usage-examples)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)

---

## Overview

The DAZZLE MCP server enables Claude Code to:

1. **Validate DSL files** - Parse and check syntax/semantics in real-time
2. **Build applications** - Generate code from DSL specifications
3. **Inspect definitions** - Examine entities, surfaces, and modules
4. **Analyze patterns** - Detect CRUD operations and integration patterns
5. **Look up concepts** - Get help with DSL syntax and semantics
6. **Find examples** - Discover example projects demonstrating features

### How It Works

```
┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
│   Claude Code   │  ◄─MCP─► │  DAZZLE Server  │  ◄────► │  DAZZLE Project │
│  (AI Assistant) │          │  (Python)       │          │  (DSL files)    │
└─────────────────┘          └─────────────────┘          └─────────────────┘
```

Claude Code communicates with the DAZZLE MCP server using the Model Context Protocol. The server runs `dazzle` commands and returns structured results.

---

## Installation

### Homebrew (Automatic)

If you installed DAZZLE via Homebrew, the MCP server is **automatically registered**:

```bash
brew install manwithacat/tap/dazzle
```

The post-install hook runs `dazzle mcp-setup` for you.

### PyPI/pip (Manual)

After installing via pip, register the MCP server manually:

```bash
# Install DAZZLE
pip install dazzle

# Register MCP server with Claude Code
dazzle mcp-setup
```

### Verification

Check registration status:

```bash
dazzle mcp-check
```

**Expected output** (when registered):
```
DAZZLE MCP Server Status
==================================================
Status:        registered
Registered:    ✓ Yes
Config:        /Users/you/.claude/mcp_servers.json
Command:       /path/to/python -m dazzle.mcp

Available Tools (9):
  • analyze_patterns
  • build
  • find_examples
  • inspect_entity
  • inspect_surface
  • lint_project
  • list_modules
  • lookup_concept
  • validate_dsl
```

---

## Available Tools

The DAZZLE MCP server provides the following tools to Claude Code:

### Core Validation

#### `validate_dsl`
**Purpose**: Validate all DSL files in the project

**When to use**:
- After editing DSL files
- Before building
- To check syntax and semantic errors

**Example**:
```
User: "Validate my DSL files"
Claude: [Uses validate_dsl tool]
Claude: "✓ All DSL files are valid. Found 3 modules, 5 entities, 8 surfaces."
```

#### `lint_project`
**Purpose**: Run extended validation with style checks

**Parameters**:
- `extended` (bool): Enable strict validation rules

**When to use**:
- Before committing code
- To check naming conventions
- To detect unused imports or dead code

### Code Generation

#### `build`
**Purpose**: Generate code artifacts from DSL specifications

**Parameters**:
- `stacks` (list): Stack names to build (default: `["django_micro_modular"]`)

**When to use**:
- After DSL validation passes
- To generate Django, Express, OpenAPI, or other artifacts

**Example**:
```
User: "Build my application with the Django stack"
Claude: [Uses build tool with stacks=["django_micro_modular"]]
Claude: "✓ Generated Django application in build/django_micro_modular/"
```

### Inspection

#### `inspect_entity`
**Purpose**: Inspect an entity definition

**Parameters**:
- `entity_name` (str): Name of the entity to inspect

**When to use**:
- To understand entity structure
- To see fields, constraints, relationships

**Example**:
```
User: "Show me the User entity"
Claude: [Uses inspect_entity with entity_name="User"]
Claude: "The User entity has 4 fields: id (uuid), email (str), role (enum), created_at (datetime)"
```

#### `inspect_surface`
**Purpose**: Inspect a surface definition

**Parameters**:
- `surface_name` (str): Name of the surface to inspect

**When to use**:
- To understand UI structure
- To see sections, fields, actions

#### `list_modules`
**Purpose**: List all modules in the project

**When to use**:
- To understand project structure
- To see module dependencies

### Pattern Analysis

#### `analyze_patterns`
**Purpose**: Analyze project for CRUD and integration patterns

**When to use**:
- To understand what the application does
- To detect common patterns automatically
- Before suggesting improvements

**Example**:
```
User: "What patterns do you see in my project?"
Claude: [Uses analyze_patterns tool]
Claude: "I found 3 CRUD patterns: User (full CRUD), Task (list/view only), Comment (create/delete)"
```

### Learning & Discovery

#### `lookup_concept`
**Purpose**: Look up DAZZLE DSL concepts and syntax

**Parameters**:
- `term` (str): DSL concept to look up (e.g., "persona", "workspace", "entity")

**When to use**:
- To learn DSL syntax
- To understand DAZZLE features
- When writing new DSL constructs

**Example**:
```
User: "How do I define a workspace?"
Claude: [Uses lookup_concept with term="workspace"]
Claude: "A workspace is defined with the 'workspace' keyword..."
```

#### `find_examples`
**Purpose**: Find example projects demonstrating specific features

**Parameters**:
- `features` (list): Features to search for (e.g., `["persona", "workspace"]`)
- `complexity` (str): "beginner", "intermediate", or "advanced"

**When to use**:
- To learn by example
- To see how features are used together

---

## Usage Examples

### Example 1: Validating and Building

**User**: "Check if my DSL is valid and build the Django app"

**Claude's actions**:
1. Uses `validate_dsl` to check syntax
2. If valid, uses `build` with `stacks=["django_micro_modular"]`
3. Reports results

**Conversation**:
```
Claude: Let me validate your DSL first.
[Uses validate_dsl]
Claude: ✓ Validation passed. Found 2 entities: User and Task.

Now building the Django application...
[Uses build with stacks=["django_micro_modular"]]
Claude: ✓ Django app generated in build/django_micro_modular/

You can now run:
  cd build/django_micro_modular
  python manage.py migrate
  python manage.py runserver
```

### Example 2: Understanding Project Structure

**User**: "What does my project do?"

**Claude's actions**:
1. Uses `list_modules` to see structure
2. Uses `analyze_patterns` to detect functionality
3. May use `inspect_entity` on key entities

**Conversation**:
```
Claude: Let me analyze your project.
[Uses list_modules]
Claude: Your project has 2 modules: core and integrations.

[Uses analyze_patterns]
Claude: I found the following patterns:
- User management (full CRUD)
- Task tracking (list, view, create)
- GitHub integration for pulling issues

Your app appears to be a task management system with GitHub integration.
```

### Example 3: Learning DSL Syntax

**User**: "How do I add a relationship between entities?"

**Claude's actions**:
1. Uses `lookup_concept` with `term="relationships"`
2. May use `find_examples` with `features=["relationships"]`

**Conversation**:
```
Claude: [Uses lookup_concept with term="relationships"]

To add a relationship in DAZZLE DSL, use the `ref` field type:

```dsl
entity Task:
  id: uuid pk
  owner: ref User  # Relationship to User entity
```

[Uses find_examples with features=["relationships"]]
The "support_tickets" example demonstrates relationships between User, Ticket, and Comment.
```

### Example 4: Fixing Validation Errors

**User**: "My validation is failing, what's wrong?"

**Claude's actions**:
1. Uses `validate_dsl` to see specific errors
2. Uses `inspect_entity` or `lookup_concept` to understand issues
3. Suggests fixes

**Conversation**:
```
Claude: [Uses validate_dsl]

I found 2 validation errors:

1. Line 15: Unknown field type 'string' (did you mean 'str'?)
2. Line 22: Entity 'Task' references unknown entity 'Owner'

Let me fix these:

Line 15: Change `name: string(100)` to `name: str(100)`
Line 22: Did you mean `owner: ref User` instead of `Owner`?
```

---

## Configuration

### Global Configuration

The MCP server is registered in Claude Code's global config:

**Location** (one of):
- `~/.config/claude-code/mcp_servers.json` (XDG standard, Linux/Mac)
- `~/.claude/mcp_servers.json` (Legacy location)
- `~/Library/Application Support/Claude Code/mcp_servers.json` (Mac app)

**Format**:
```json
{
  "mcpServers": {
    "dazzle": {
      "command": "/usr/local/bin/python",
      "args": ["-m", "dazzle.mcp"],
      "env": {},
      "autoStart": true
    }
  }
}
```

### Project-Local Configuration

Each DAZZLE project includes `.claude/mcp.json` created by `dazzle init`:

```json
{
  "mcpServers": {
    "dazzle": {
      "command": "dazzle",
      "args": ["mcp", "--working-dir", "${projectDir}"],
      "env": {},
      "autoStart": true
    }
  }
}
```

**Note**: `${projectDir}` is substituted by Claude Code at runtime, making the config portable.

### Customizing Configuration

**Change Python executable**:
```json
{
  "mcpServers": {
    "dazzle": {
      "command": "/path/to/custom/python",
      "args": ["-m", "dazzle.mcp"],
      ...
    }
  }
}
```

**Add environment variables**:
```json
{
  "mcpServers": {
    "dazzle": {
      "command": "dazzle",
      "args": ["mcp", "--working-dir", "${projectDir}"],
      "env": {
        "ANTHROPIC_API_KEY": "your-key-here",
        "DEBUG": "true"
      },
      ...
    }
  }
}
```

---

## Troubleshooting

### MCP Tools Not Available

**Problem**: Claude Code doesn't show DAZZLE tools

**Solutions**:
1. Check registration:
   ```bash
   dazzle mcp-check
   ```

2. If not registered:
   ```bash
   dazzle mcp-setup
   ```

3. Restart Claude Code

4. Verify in Claude Code:
   ```
   Ask: "What DAZZLE tools do you have access to?"
   ```

### Wrong Python Version

**Problem**: MCP server uses wrong Python (e.g., system Python instead of virtualenv)

**Solution**: Update config to use correct Python:
```bash
# Find your Python
which python  # or: pyenv which python

# Update config manually or re-run:
dazzle mcp-setup --force
```

### Permission Errors

**Problem**: "Permission denied" when registering MCP server

**Solution**: Ensure config directory is writable:
```bash
chmod 755 ~/.claude
chmod 644 ~/.claude/mcp_servers.json
```

### Tools Return Errors

**Problem**: MCP tools work but return errors

**Checklist**:
1. Ensure you're in a DAZZLE project directory (contains `dazzle.toml`)
2. Check DSL files are in correct location (`dsl/` by default)
3. Verify project structure with `dazzle validate`

**Debug mode**:
```bash
# Run MCP server manually to see detailed errors
dazzle mcp --working-dir /path/to/project
```

### Config Not Found

**Problem**: `dazzle mcp-setup` can't find config directory

**Solution**: Manually create Claude Code config directory:
```bash
mkdir -p ~/.claude
dazzle mcp-setup
```

---

## Advanced Usage

### Running MCP Server Manually

For debugging or testing:

```bash
# Run MCP server in current directory
dazzle mcp

# Run with specific working directory
dazzle mcp --working-dir /path/to/project

# Stop with Ctrl+C
```

### Multiple DAZZLE Versions

If you have multiple DAZZLE installations (e.g., system + virtualenv):

**Global config**: Points to system or Homebrew installation
**Project-local config**: Can override with virtualenv Python

Example project-local `.claude/mcp.json`:
```json
{
  "mcpServers": {
    "dazzle": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "dazzle.mcp", "--working-dir", "${projectDir}"],
      ...
    }
  }
}
```

### Disabling MCP Server

To temporarily disable:

**Option 1**: Set `autoStart: false` in config:
```json
{
  "mcpServers": {
    "dazzle": {
      "autoStart": false,
      ...
    }
  }
}
```

**Option 2**: Remove from config entirely:
```bash
# Edit config manually, or:
# (No built-in unregister command yet)
```

### Using with Other MCP Servers

DAZZLE MCP server coexists with other MCP servers. Your `mcp_servers.json` might look like:

```json
{
  "mcpServers": {
    "dazzle": {
      "command": "dazzle",
      "args": ["mcp", "--working-dir", "${projectDir}"]
    },
    "github": {
      "command": "mcp-server-github",
      "args": []
    },
    "filesystem": {
      "command": "mcp-server-filesystem",
      "args": ["/path/to/files"]
    }
  }
}
```

Claude Code will load all servers and make their tools available.

---

## Best Practices

1. **Always validate before building**:
   Ask Claude to validate before generating code to catch errors early.

2. **Use pattern analysis for understanding**:
   When working with unfamiliar projects, ask Claude to analyze patterns first.

3. **Leverage concept lookup for learning**:
   Don't hesitate to ask Claude to look up DSL concepts—it's faster than reading docs.

4. **Verify registration on new installations**:
   After installing DAZZLE, always run `dazzle mcp-check` to ensure MCP server is ready.

5. **Update after DAZZLE upgrades**:
   After upgrading DAZZLE, run `dazzle mcp-setup --force` to ensure config is current.

---

## Support & Feedback

- **Issues**: https://github.com/manwithacat/dazzle/issues
- **Discussions**: https://github.com/manwithacat/dazzle/discussions
- **Documentation**: https://github.com/manwithacat/dazzle/tree/main/docs

---

## References

- **Model Context Protocol**: https://modelcontextprotocol.io
- **DAZZLE DSL Reference**: [DAZZLE_DSL_REFERENCE_0_1.md](DAZZLE_DSL_REFERENCE_0_1.md)
- **MCP Distribution Strategy**: [../dev_docs/mcp_distribution_strategy.md](../dev_docs/mcp_distribution_strategy.md)
- **Claude Code**: https://claude.ai/code

---

**Last Updated**: 2025-11-27
**DAZZLE Version**: 0.1.1
