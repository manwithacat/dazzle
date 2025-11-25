# DAZZLE MCP Server Implementation (Nov 24, 2025)

## Overview

Implemented a Model Context Protocol (MCP) server for DAZZLE, enabling tight integration with Claude Code and other AI tools while keeping users in control of their AI subscription tokens.

## Motivation

Following the VS Code extension simplification, the logical next step is providing seamless AI integration through MCP. This allows developers to:
- Use Claude Code directly on DAZZLE projects
- Call DAZZLE validation, inspection, and build tools
- Access project resources without copy/paste
- Spend their own Claude subscription tokens
- Get AI assistance without manual workflows

## Implementation

### Architecture

**Protocol**: JSON-RPC 2.0 over stdio
**Transport**: stdin/stdout (line-delimited JSON)
**Entry Point**: `python -m dazzle.mcp.server`

### File Structure

```
src/dazzle/mcp/
├── __init__.py          # Module exports
├── __main__.py          # Entry point (asyncio runner)
├── server.py            # Main MCP server (400+ lines)
├── tools.py             # Tool definitions
├── resources.py         # Resource definitions
└── prompts.py           # Prompt/slash command definitions
```

### Capabilities Exposed

#### 7 Tools

1. **`validate_dsl`** - Validate DSL files, link modules
2. **`list_modules`** - Show modules and dependencies
3. **`inspect_entity`** - Inspect entity definition
4. **`inspect_surface`** - Inspect surface definition
5. **`build`** - Build artifacts for stacks
6. **`analyze_patterns`** - Detect CRUD/integration patterns
7. **`lint_project`** - Run extended validation

#### 4+ Resources

1. **`dazzle://project/manifest`** - dazzle.toml
2. **`dazzle://modules`** - Module list (JSON)
3. **`dazzle://entities`** - Entity list (JSON)
4. **`dazzle://surfaces`** - Surface list (JSON)
5. **`dazzle://dsl/{path}`** - Individual DSL files

#### 5 Prompts (Slash Commands)

1. **`/validate`** - Validate project
2. **`/review_dsl`** - Review DSL design
3. **`/code_review`** - Review generated code
4. **`/suggest_surfaces`** - Suggest CRUD surfaces
5. **`/optimize_dsl`** - Suggest optimizations

## Configuration

### Project-Level (Recommended for Teams)

Create `.mcp.json` in project root:

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

Commit to version control for team sharing.

### User-Level (Personal Setup)

Create `~/.claude/mcp.json`:

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

## Usage Examples

### Validate and Build

```
User: Validate my DAZZLE project and build with django_api stack.

Claude: [Calls validate_dsl tool]
        [Calls build tool with stacks: ["django_api"]]
        [Reports results]
```

### Inspect and Analyze

```
User: Show me the User entity and analyze patterns.

Claude: [Calls inspect_entity with entity_name="User"]
        [Calls analyze_patterns]
        [Summarizes entity structure and patterns found]
```

### Review and Optimize

```
User: /review_dsl --aspect security

Claude: [Uses review_dsl prompt]
        [Calls inspect_entity on multiple entities]
        [Analyzes for security issues]
        [Suggests improvements]
```

## Benefits

1. **Seamless Integration**: No clipboard, no copy/paste
2. **Direct Tool Access**: Claude calls DAZZLE functions directly
3. **Resource References**: `@dazzle:dazzle://modules` syntax
4. **User Tokens**: Developers pay for their own Claude usage
5. **Team Sharing**: `.mcp.json` in version control
6. **Extensible**: Easy to add new tools/resources/prompts

## Technical Details

### JSON-RPC Protocol

**Request** (stdin):
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

**Response** (stdout):
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"status\": \"valid\", \"modules\": 3}"
      }
    ]
  }
}
```

### Error Handling

Errors are returned as JSON-RPC error objects:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32603,
    "message": "Entity 'Foo' not found"
  }
}
```

### Logging

All logs go to stderr to avoid interfering with JSON-RPC on stdout:

```python
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
```

## Integration with VS Code Extension

The VS Code extension can now recommend MCP setup:

**Future Enhancement**:
```typescript
// Detect if Claude Code is installed
// Offer to create .mcp.json automatically
// Show notification: "Enable DAZZLE MCP integration?"
```

## Comparison: Clipboard vs MCP

### Before (Clipboard Pattern)

```
1. User clicks "Ask Claude to Analyze"
2. Extension copies prompt to clipboard
3. User pastes in Claude chat
4. Claude reads prompt
5. Claude runs: dazzle analyze-spec SPEC.md
6. User waits for completion
```

### After (MCP Integration)

```
1. User: "Validate my project"
2. Claude calls validate_dsl tool directly
3. Results returned instantly
4. Claude summarizes results
```

**Improvement**: 6 steps → 4 steps, no manual copy/paste

## Testing

### Manual Test

```bash
# Start server
python -m dazzle.mcp.server /path/to/project

# Send request (stdin)
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}

# Receive response (stdout)
{"jsonrpc":"2.0","id":1,"result":{"tools":[...]}}
```

### With Claude Code

```bash
# Configure in ~/.claude/mcp.json
claude mcp list  # Should show "dazzle"

# In Claude Code chat:
"Use the validate_dsl tool on my project"
```

## Future Enhancements

1. **More Tools**:
   - `generate_dsl_from_spec` - Generate DSL from markdown spec
   - `refactor_entity` - Rename/restructure entities
   - `add_field` - Add field to entity
   - `create_surface` - Generate surface definition

2. **More Resources**:
   - `dazzle://schema/{entity}` - JSON Schema for entities
   - `dazzle://openapi` - Generated OpenAPI spec
   - `dazzle://build/{stack}/files` - List of generated files

3. **More Prompts**:
   - `/migrate_spec` - Convert SPEC.md to DSL
   - `/deploy` - Deploy generated application
   - `/test` - Run tests on generated code

4. **Authentication** (for remote MCP):
   - OAuth 2.0 for cloud-hosted servers
   - API key management
   - Team/workspace access control

5. **VS Code Integration**:
   - Auto-create `.mcp.json` on project init
   - Status bar showing MCP connection
   - Quick actions in command palette

## Documentation

Created comprehensive user documentation:
- **`docs/MCP_SERVER.md`** - Full setup and usage guide
- **`dev_docs/mcp_server_implementation.md`** - This document

## Files Added

```
src/dazzle/mcp/__init__.py         # 9 lines
src/dazzle/mcp/__main__.py         # 40 lines
src/dazzle/mcp/server.py           # 400+ lines
src/dazzle/mcp/tools.py            # 95 lines
src/dazzle/mcp/resources.py        # 60 lines
src/dazzle/mcp/prompts.py          # 70 lines
docs/MCP_SERVER.md                 # 400+ lines
dev_docs/mcp_server_implementation.md  # This file

Total: ~1,075 lines of implementation + documentation
```

## Dependencies

**None!** The MCP server uses:
- Standard library (json, asyncio, sys, pathlib, logging)
- Existing DAZZLE imports (core modules)
- No external MCP packages required

This makes it:
- Easy to install (no extra deps)
- Portable (works anywhere Python works)
- Maintainable (no external API changes)

## Outcome

DAZZLE now provides **three levels of Claude integration**:

1. **Level 1: Documentation** - `.claude/CLAUDE.md` provides context
2. **Level 2: VS Code Extension** - Clipboard prompts for quick workflows
3. **Level 3: MCP Server** - Direct tool calls for seamless integration

Users can choose their level based on needs:
- **Casual users**: Just use Claude Code with CLAUDE.md
- **Regular users**: VS Code extension for quick prompts
- **Power users**: MCP server for full integration

## Impact

This implementation achieves the original vision:

> "Ultimately I want the founders to have their conversations with their AI, and deliver the markdown spec, with their AI writing the DSL based on our grammar. I want them to pay for their own tokens."

Now possible:
```
Founder: "Here's my SPEC.md for a task management app. Build it."

Claude Code:
1. Reads SPEC.md
2. Writes DSL files using DAZZLE grammar
3. Calls validate_dsl to check syntax
4. Calls build to generate code
5. Shows founder the working application

Tokens: Paid by founder's Claude subscription ✅
```

## Next Steps

1. **Test with real users** - Get feedback on MCP workflows
2. **Add more tools** - Based on user needs
3. **VS Code auto-setup** - Detect Claude Code, offer MCP config
4. **Examples repo** - Show MCP workflows for common tasks
5. **Remote MCP** - Cloud-hosted server for teams (later)

## Conclusion

The DAZZLE MCP server provides seamless Claude Code integration with:
- ✅ 7 tools for validation, inspection, building
- ✅ 4+ resources for project data
- ✅ 5 prompts for common workflows
- ✅ Zero external dependencies
- ✅ Simple configuration (`.mcp.json`)
- ✅ Users control their tokens

Ready for initial users to test and provide feedback.
