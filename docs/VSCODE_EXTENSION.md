# DAZZLE VS Code Extension User Guide

**Version**: 0.5.0 (Simplified)
**Last Updated**: November 24, 2025

## Overview

The DAZZLE VS Code extension provides IDE support for DAZZLE DSL development with:
- **Syntax highlighting** for `.dsl` files
- **Real-time validation** with error display
- **LSP features** (hover, go-to-definition, autocomplete)
- **Claude Code integration** via clipboard prompts or MCP server
- **Build and lint commands**

## Installation

### Prerequisites

1. **VS Code 1.80.0+**
2. **Python 3.11+**
3. **DAZZLE CLI**:
   ```bash
   pip install dazzle
   # Verify:
   dazzle --version
   ```

### Install Extension

**From Source:**
```bash
cd /path/to/dazzle/extensions/vscode
npm install
npm run compile
npm run package
code --install-extension dazzle-dsl-*.vsix
```

## Quick Start

### 1. Create Project

```bash
# Initialize new project
dazzle init
cd my-project

# Open in VS Code
code .
```

### 2. Create DSL File

```dsl
# dsl/core.dsl
module myapp.core

app myapp "My Application"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[todo,done]=todo
  created_at: datetime auto_add
```

### 3. Validate

**Automatic**: Save file (Cmd+S / Ctrl+S)
**Manual**: Cmd+Shift+P → "DAZZLE: Validate Project"

Errors appear in Problems panel (Cmd+Shift+M / Ctrl+Shift+M)

## Core Features

### Syntax Highlighting

Color coding for DSL elements:
- **Keywords** (purple): `module`, `entity`, `surface`
- **Types** (cyan): `uuid`, `str`, `datetime`
- **Modifiers** (gold): `required`, `unique`, `pk`
- **Strings** (green): `"Task List"`
- **Comments** (gray): `# Comment`

### Real-Time Validation

- **On Save**: Automatic validation (configurable)
- **Problems Panel**: Shows errors/warnings with file:line
- **Inline Squiggles**: Red for errors, yellow for warnings
- **Click to Navigate**: Click error to jump to location

### LSP Features

#### Hover Documentation
Hover over any DSL element for documentation:
- Types (`uuid`, `str`, etc.)
- Modifiers (`required`, `unique`)
- Entity/surface names

#### Go to Definition
**Cmd+Click** (Mac) / **Ctrl+Click** (Windows) on references
- Jump to entity definitions
- Navigate across modules
- Works with `use` statements

#### Autocomplete
**Ctrl+Space** to trigger suggestions:
- Field types
- Modifiers
- Keywords
- Entity names

## Claude Integration

### Option 1: Simple Commands (Default)

The extension provides pre-crafted prompts for common workflows:

#### Commands Available

**Ask Claude to Analyze SPEC**
- Copies prompt to analyze SPEC.md and generate DSL
- Cmd+Shift+P → "DAZZLE: Ask Claude to Analyze SPEC"

**Ask Claude to Validate & Fix**
- Copies prompt to validate and fix errors
- Cmd+Shift+P → "DAZZLE: Ask Claude to Validate & Fix"

**Ask Claude to Build**
- Copies prompt to build project with selected stack
- Cmd+Shift+P → "DAZZLE: Ask Claude to Build"

**Ask Claude to Initialize**
- Copies prompt to initialize new project
- Cmd+Shift+P → "DAZZLE: Ask Claude to Initialize Project"

#### How It Works

1. Run command from palette
2. Extension copies prompt to clipboard
3. Paste in Claude Code chat
4. Claude executes DAZZLE commands using your tokens

### Option 2: MCP Server (Advanced)

For seamless integration without copy/paste:

#### Setup MCP Server

1. **Create `.mcp.json` in project root:**

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

2. **Use in Claude Code:**

```
Validate my DAZZLE project
```

Claude will directly call the `validate_dsl` tool.

#### Available MCP Tools

- `validate_dsl` - Validate project
- `list_modules` - Show modules
- `inspect_entity` - Inspect entity definition
- `build` - Build with stack
- `analyze_patterns` - Detect patterns
- `lint_project` - Extended validation

See [MCP_SERVER.md](MCP_SERVER.md) for full documentation.

## Commands

Access via Command Palette (Cmd+Shift+P / Ctrl+Shift+P):

| Command | Description | Output |
|---------|-------------|--------|
| **DAZZLE: Validate Project** | Check DSL for errors | Problems panel |
| **DAZZLE: Build Project** | Generate code | Terminal |
| **DAZZLE: Lint Project** | Extended validation | Terminal |
| **DAZZLE: Ask Claude to...** | Copy Claude prompts | Clipboard |

## Configuration

Access settings: Cmd+, / Ctrl+, → Search "dazzle"

### Key Settings

```json
{
  // Path to DAZZLE CLI
  "dazzle.cliPath": "dazzle",

  // Auto-validate on save
  "dazzle.validateOnSave": true,

  // Python for LSP (empty = auto-detect)
  "dazzle.pythonPath": "",

  // Project manifest name
  "dazzle.manifest": "dazzle.toml"
}
```

## DSL Quick Reference

### Basic Structure

```dsl
module myapp.core        # Module declaration
use myapp.other         # Import other module

app myapp "My App"      # App declaration

entity Task "Task":     # Entity with fields
  id: uuid pk
  title: str(200) required
  status: enum[todo,done]=todo
  created_at: datetime auto_add
```

### Field Types

| Type | Example |
|------|---------|
| `uuid` | `id: uuid pk` |
| `str(n)` | `name: str(100)` |
| `text` | `description: text` |
| `int` | `count: int` |
| `float` | `price: float` |
| `bool` | `active: bool` |
| `datetime` | `created_at: datetime` |
| `enum[...]` | `status: enum[a,b,c]` |
| `ref Entity` | `owner: ref User` |

### Field Modifiers

| Modifier | Description |
|----------|-------------|
| `pk` | Primary key |
| `required` | Not nullable |
| `unique` | Unique constraint |
| `default=X` | Default value |
| `auto_add` | Set on create |
| `auto_update` | Update timestamp |

### Surface Types

```dsl
# List view
surface task_list "Tasks":
  uses entity Task
  mode: list

# Detail view
surface task_detail "Task Detail":
  uses entity Task
  mode: detail

# Form
surface task_form "Task Form":
  uses entity Task
  mode: form
```

## Keyboard Shortcuts

| Action | Mac | Windows/Linux |
|--------|-----|---------------|
| Command Palette | Cmd+Shift+P | Ctrl+Shift+P |
| Go to Definition | Cmd+Click / F12 | Ctrl+Click / F12 |
| Autocomplete | Ctrl+Space | Ctrl+Space |
| Problems Panel | Cmd+Shift+M | Ctrl+Shift+M |
| Save & Validate | Cmd+S | Ctrl+S |

## Troubleshooting

### Extension Not Working

**Check Installation:**
```bash
# Verify DAZZLE CLI
dazzle --version

# Verify Python package (for LSP)
python3 -c "import dazzle.lsp.server"
```

**Check VS Code:**
- Extensions panel → DAZZLE DSL → Enabled
- Output panel → "DAZZLE" channel for errors
- Output panel → "DAZZLE LSP" for LSP logs

### Validation Not Running

1. Check `dazzle.toml` exists in workspace root
2. Settings → `dazzle.validateOnSave` → true
3. Check Output → "DAZZLE" for errors

### LSP Features Not Working

**Symptoms**: No hover, no autocomplete, no go-to-definition

**Fix:**
```bash
# Install DAZZLE Python package
pip install dazzle

# Check LSP server available
python3 -c "import dazzle.lsp.server; print('LSP OK')"
```

Check Output → "DAZZLE LSP" for error details.

### Claude Commands Not Working

**Symptoms**: Claude commands don't copy to clipboard

**Check:**
- Claude Code extension installed
- VS Code has clipboard permissions

**Alternative**: Use MCP server for direct integration (no clipboard needed).

## Common Workflows

### Create Entity with CRUD Surfaces

```dsl
# 1. Define entity
entity Product "Product":
  id: uuid pk
  name: str(200) required
  price: float required
  stock: int default=0
  created_at: datetime auto_add

# 2. Add list surface
surface product_list "Products":
  uses entity Product
  mode: list
  section main "Products":
    field name "Name"
    field price "Price"
    field stock "Stock"

# 3. Add form surface
surface product_form "Product Form":
  uses entity Product
  mode: form
  section main "Details":
    field name "Name"
    field price "Price"
    field stock "Stock"
```

### Fix Validation Errors

1. See error in Problems panel
2. Click to navigate to error
3. Fix issue (e.g., typo in entity name)
4. Save → Error clears

### Build Project

1. Validate first: Problems panel shows 0 errors
2. Cmd+Shift+P → "DAZZLE: Build Project"
3. Terminal opens → Select stack
4. Review generated code in `build/` directory

### Use Claude for SPEC → DSL

**With Clipboard:**
1. Create SPEC.md with requirements
2. Cmd+Shift+P → "DAZZLE: Ask Claude to Analyze SPEC"
3. Paste in Claude Code
4. Claude generates DSL and builds

**With MCP Server:**
1. Setup .mcp.json (see above)
2. Ask Claude: "Analyze my SPEC.md and generate DSL"
3. Claude uses tools directly

## File Structure

```
my-project/
├── dazzle.toml         # Project manifest
├── .mcp.json          # MCP server config (optional)
├── dsl/               # DSL files
│   ├── core.dsl      # Core entities
│   ├── surfaces.dsl  # UI surfaces
│   └── api.dsl       # API definitions
└── build/             # Generated code
```

## Integration Levels

Choose based on your needs:

### Level 1: Basic (Just Syntax)
- Syntax highlighting
- Manual validation
- No Claude integration

### Level 2: Standard (Recommended)
- All basic features
- LSP (hover, autocomplete)
- Claude clipboard integration
- Auto-validation

### Level 3: Advanced (Power Users)
- All standard features
- MCP server integration
- Direct Claude tool calls
- No copy/paste needed

## Tips

1. **Use Outline View**: Explorer → Outline shows file structure
2. **Multi-module**: Split large projects into modules
3. **Symbol Search**: Cmd+Shift+O to jump to entities
4. **Problems Navigation**: F8/Shift+F8 to jump between errors
5. **Check Output Channels**: For detailed error messages

## Getting Help

- **Documentation**: `/docs/` directory
- **MCP Setup**: [MCP_SERVER.md](MCP_SERVER.md)
- **DSL Reference**: `DAZZLE_DSL_REFERENCE_0_1.md`
- **GitHub Issues**: https://github.com/dazzle/dazzle/issues

Include in bug reports:
- VS Code version (Help → About)
- DAZZLE version (`dazzle --version`)
- Error messages from Output channels
- Steps to reproduce

---

## What's Changed (v0.5.0)

### Removed
- Complex LLM Q&A dialogs
- Custom webview panels
- `dazzle.analyzeSpec` command

### Added
- Simplified Claude commands (clipboard-based)
- MCP server support for direct integration
- Pre-crafted prompt templates

### Simplified
- Reduced from 700+ lines to 240 lines
- Focus on core IDE features
- User controls their Claude tokens

The extension is now simpler, more reliable, and integrates better with Claude Code while letting users control their AI spending.