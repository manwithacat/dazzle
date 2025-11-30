# DAZZLE Tooling Guide

> MCP Server, IDE Integration, and Developer Tools

DAZZLE provides first-class tooling for AI-assisted development and traditional IDE workflows.

## MCP Server (Claude Code Integration)

DAZZLE includes a built-in Model Context Protocol (MCP) server for seamless integration with Claude Code.

### Setup

```bash
# Homebrew (auto-registered)
brew install manwithacat/tap/dazzle

# PyPI (manual registration)
pip install dazzle
dazzle mcp-setup

# Verify
dazzle mcp-check
```

### Available MCP Tools

| Tool | Purpose |
|------|---------|
| `validate_dsl` | Parse and validate DSL files |
| `build` | Generate code from DSL |
| `inspect_entity` | Examine entity definitions |
| `inspect_surface` | Examine surface definitions |
| `list_modules` | List project modules |
| `analyze_patterns` | Detect CRUD and integration patterns |
| `lint_project` | Extended validation with style checks |
| `lookup_concept` | Look up DSL concepts and syntax |
| `find_examples` | Search example projects by features |

### Usage Examples

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

### MCP Configuration

**Global** (`~/.claude/mcp_servers.json`):
```json
{
  "mcpServers": {
    "dazzle": {
      "command": "dazzle",
      "args": ["mcp"],
      "autoStart": true
    }
  }
}
```

**Project-local** (`.claude/mcp.json`):
```json
{
  "mcpServers": {
    "dazzle": {
      "command": "dazzle",
      "args": ["mcp", "--working-dir", "${projectDir}"]
    }
  }
}
```

---

## IDE Integration (LSP)

DAZZLE provides a Language Server Protocol (LSP) implementation for IDE support.

### Features

- Real-time diagnostics
- Hover documentation
- Go-to-definition
- Find references
- Auto-completion
- Document symbols

### VS Code (Recommended)

```bash
# Install extension
code --install-extension manwithacat.dazzle-vscode
```

**Settings:**
```json
{
  "dazzle.lsp.enabled": true,
  "dazzle.validation.onType": true,
  "dazzle.completion.enabled": true
}
```

### Neovim

```lua
local lspconfig = require('lspconfig')
local configs = require('lspconfig.configs')

if not configs.dazzle then
  configs.dazzle = {
    default_config = {
      cmd = {'dazzle', 'lsp'},
      filetypes = {'dsl'},
      root_dir = lspconfig.util.root_pattern('dazzle.toml'),
    },
  }
end

lspconfig.dazzle.setup{}
```

### Emacs

```elisp
(define-derived-mode dsl-mode prog-mode "DSL"
  "Major mode for DAZZLE DSL files.")

(add-to-list 'auto-mode-alist '("\\.dsl\\'" . dsl-mode))

(lsp-register-client
 (make-lsp-client
  :new-connection (lsp-stdio-connection '("dazzle" "lsp"))
  :major-modes '(dsl-mode)
  :server-id 'dazzle-lsp))

(add-hook 'dsl-mode-hook #'lsp-deferred)
```

### Other Editors

Configure your LSP client with:
- **Command**: `dazzle lsp`
- **File extensions**: `.dsl`
- **Root pattern**: `dazzle.toml`

---

## CLI Commands

### Validation & Analysis

```bash
dazzle validate              # Parse and validate DSL
dazzle lint                  # Extended checks
dazzle layout-plan           # Visualize workspace layouts
```

### DNR (Dazzle Native Runtime)

```bash
dazzle dnr serve             # Run the application
dazzle dnr info              # Show project info
dazzle dnr build-ui          # Build static UI assets
dazzle dnr build-api         # Generate API spec
```

### Project Management

```bash
dazzle init <name>           # Create new project
dazzle stacks                # List available stacks
dazzle build --stack <name>  # Generate code (optional)
```

### Testing

```bash
dazzle test generate         # Generate test specification
dazzle test run              # Run E2E tests
dazzle test list             # List test flows
```

---

## Troubleshooting

### MCP Not Working

```bash
# Check registration
dazzle mcp-check

# Re-register
dazzle mcp-setup --force

# Restart Claude Code
```

### LSP Not Starting

```bash
# Verify installation
dazzle lsp --help

# Check logs (VS Code)
# Output panel → "DAZZLE Language Server"

# Check logs (Neovim)
:LspLog
```

### Validation Errors

```bash
# Run validation manually
dazzle validate

# Check specific file
dazzle validate path/to/file.dsl
```

---

## Resources

- [DSL Quick Reference](DAZZLE_DSL_QUICK_REFERENCE.md)
- [DNR Architecture](dnr/ARCHITECTURE.md)
- [CLI Reference](dnr/CLI.md)
- [Example Projects](EXAMPLES.md)
