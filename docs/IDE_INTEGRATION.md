# DAZZLE IDE Integration Guide

**Version**: 0.1.0
**Last Updated**: 2025-11-23

This guide covers how to integrate DAZZLE's Language Server Protocol (LSP) support with various editors and IDEs.

---

## Table of Contents

1. [Overview](#overview)
2. [VS Code](#vs-code-recommended)
3. [Neovim](#neovim)
4. [Emacs](#emacs)
5. [Sublime Text](#sublime-text)
6. [Other LSP-Compatible Editors](#other-lsp-compatible-editors)
7. [LSP Architecture](#lsp-architecture)
8. [Troubleshooting](#troubleshooting)

---

## Overview

DAZZLE provides a complete Language Server Protocol (LSP) implementation that offers:

- **Real-time diagnostics** - Errors and warnings as you type
- **Hover documentation** - Type information and descriptions
- **Go-to-definition** - Jump to entity, surface, service definitions
- **Find references** - Find all usages of a symbol
- **Document symbols** - Navigate document structure
- **Auto-completion** - Context-aware suggestions
- **Signature help** - Parameter hints

The LSP server is automatically installed when you install DAZZLE:

```bash
pip install dazzle
# or
brew install dazzle

# LSP server is now available
dazzle lsp --help
```

---

## VS Code (Recommended)

DAZZLE provides a full-featured VS Code extension for the best development experience.

### Installation

**Option 1: VS Code Marketplace** (when published)
1. Open VS Code
2. Go to Extensions (Cmd+Shift+X / Ctrl+Shift+X)
3. Search for "DAZZLE"
4. Click "Install"

**Option 2: Install from VSIX**
```bash
# If you have a .vsix file
code --install-extension dazzle-vscode-*.vsix
```

**Option 3: Build from Source**
```bash
git clone https://github.com/manwithacat/dazzle.git
cd dazzle/extensions/vscode
npm install
npm run compile
code --install-extension .
```

### Features

The VS Code extension provides:

- ✅ **Syntax Highlighting** - Custom .dsl file grammar
- ✅ **Real-time Diagnostics** - Errors and warnings in Problems panel
- ✅ **Hover Information** - Type and description tooltips
- ✅ **Go-to-Definition** (F12)
- ✅ **Find References** (Shift+F12)
- ✅ **Rename Symbol** (F2)
- ✅ **Auto-completion** (Ctrl+Space)
- ✅ **Code Actions** - Quick fixes and refactorings
- ✅ **Document Symbols** - Outline view
- ✅ **Breadcrumbs** - Navigation bar

### Configuration

**Extension Settings**:

Open VS Code settings (Cmd+, / Ctrl+,) and search for "dazzle":

```json
{
  "dazzle.lsp.enabled": true,
  "dazzle.lsp.trace": "off",  // or "messages", "verbose" for debugging
  "dazzle.validation.onType": true,
  "dazzle.validation.onSave": true,
  "dazzle.completion.enabled": true
}
```

**LSP Server Path**:

If the extension can't find the LSP server automatically:

```json
{
  "dazzle.lsp.serverPath": "/usr/local/bin/dazzle"
}
```

### Usage

1. Open a folder with `dazzle.toml` or `.dsl` files
2. Extension auto-activates
3. Start editing `.dsl` files
4. Get real-time feedback!

**Keyboard Shortcuts**:
- `F12` - Go to definition
- `Shift+F12` - Find references
- `F2` - Rename symbol
- `Ctrl+Space` - Trigger completion
- `Ctrl+Shift+Space` - Trigger signature help
- `F8` - Next error/warning
- `Shift+F8` - Previous error/warning

See [VS Code Extension User Guide](vscode_extension_user_guide.md) for complete documentation.

---

## Neovim

### Prerequisites

- Neovim 0.8+ with built-in LSP support
- `nvim-lspconfig` plugin

### Installation

1. **Install DAZZLE** (if not already installed):
```bash
pip install dazzle
```

2. **Install nvim-lspconfig**:

Using `vim-plug`:
```vim
Plug 'neovim/nvim-lspconfig'
```

Using `packer.nvim`:
```lua
use 'neovim/nvim-lspconfig'
```

3. **Configure LSP**:

Add to your `init.lua`:

```lua
local lspconfig = require('lspconfig')

-- Define DAZZLE LSP configuration
local configs = require('lspconfig.configs')

if not configs.dazzle then
  configs.dazzle = {
    default_config = {
      cmd = {'dazzle', 'lsp'},
      filetypes = {'dsl'},
      root_dir = function(fname)
        return lspconfig.util.root_pattern('dazzle.toml')(fname)
          or lspconfig.util.path.dirname(fname)
      end,
      settings = {},
    },
  }
end

-- Start LSP for .dsl files
lspconfig.dazzle.setup{}
```

Or in `init.vim`:

```vim
lua << EOF
local lspconfig = require('lspconfig')
local configs = require('lspconfig.configs')

if not configs.dazzle then
  configs.dazzle = {
    default_config = {
      cmd = {'dazzle', 'lsp'},
      filetypes = {'dsl'},
      root_dir = function(fname)
        return lspconfig.util.root_pattern('dazzle.toml')(fname)
          or lspconfig.util.path.dirname(fname)
      end,
      settings = {},
    },
  }
end

lspconfig.dazzle.setup{}
EOF
```

4. **Set up filetype detection**:

Create `~/.config/nvim/ftdetect/dsl.vim`:

```vim
au BufRead,BufNewFile *.dsl set filetype=dsl
```

### Key Bindings (Recommended)

Add to your `init.lua`:

```lua
-- LSP key bindings
vim.api.nvim_create_autocmd('LspAttach', {
  group = vim.api.nvim_create_augroup('UserLspConfig', {}),
  callback = function(ev)
    local opts = { buffer = ev.buf }
    vim.keymap.set('n', 'gD', vim.lsp.buf.declaration, opts)
    vim.keymap.set('n', 'gd', vim.lsp.buf.definition, opts)
    vim.keymap.set('n', 'K', vim.lsp.buf.hover, opts)
    vim.keymap.set('n', 'gi', vim.lsp.buf.implementation, opts)
    vim.keymap.set('n', '<space>rn', vim.lsp.buf.rename, opts)
    vim.keymap.set('n', 'gr', vim.lsp.buf.references, opts)
  end,
})
```

### Completion (Optional)

Install `nvim-cmp` for auto-completion:

```lua
use 'hrsh7th/nvim-cmp'
use 'hrsh7th/cmp-nvim-lsp'

local cmp = require('cmp')
cmp.setup({
  sources = {
    { name = 'nvim_lsp' },
  }
})

-- Add LSP capabilities to DAZZLE
lspconfig.dazzle.setup{
  capabilities = require('cmp_nvim_lsp').default_capabilities()
}
```

---

## Emacs

### Prerequisites

- Emacs 27+ with `lsp-mode`

### Installation

1. **Install DAZZLE**:
```bash
pip install dazzle
```

2. **Install lsp-mode**:

Using `use-package`:

```elisp
(use-package lsp-mode
  :ensure t
  :commands lsp
  :hook ((dsl-mode . lsp-deferred)))
```

3. **Register DAZZLE LSP client**:

Add to your `init.el`:

```elisp
(require 'lsp-mode)

;; Define .dsl file mode
(define-derived-mode dsl-mode prog-mode "DSL"
  "Major mode for editing DAZZLE DSL files."
  (setq-local comment-start "#"))

(add-to-list 'auto-mode-alist '("\\.dsl\\'" . dsl-mode))

;; Register DAZZLE LSP client
(lsp-register-client
 (make-lsp-client
  :new-connection (lsp-stdio-connection '("dazzle" "lsp"))
  :major-modes '(dsl-mode)
  :server-id 'dazzle-lsp
  :root-pattern '("dazzle.toml")))

;; Auto-start LSP for .dsl files
(add-hook 'dsl-mode-hook #'lsp-deferred)
```

4. **Configure lsp-mode (optional)**:

```elisp
(setq lsp-enable-snippet nil)  ; Disable snippets if not needed
(setq lsp-enable-symbol-highlighting t)
(setq lsp-signature-auto-activate t)
```

### Key Bindings

LSP-mode provides default bindings:

- `M-.` - Go to definition
- `M-?` - Find references
- `C-c l r r` - Rename symbol
- `C-c l a a` - Code actions
- `C-c l g g` - Find definitions
- `C-c l g r` - Find references

---

## Sublime Text

### Prerequisites

- Sublime Text 4+
- LSP package

### Installation

1. **Install DAZZLE**:
```bash
pip install dazzle
```

2. **Install LSP package**:
   - Open Command Palette (Cmd+Shift+P / Ctrl+Shift+P)
   - Run "Package Control: Install Package"
   - Search for "LSP"
   - Install "LSP"

3. **Configure DAZZLE LSP client**:

   **Preferences → Package Settings → LSP → Settings**:

```json
{
  "clients": {
    "dazzle": {
      "enabled": true,
      "command": ["dazzle", "lsp"],
      "selector": "source.dsl",
      "languageId": "dsl"
    }
  }
}
```

4. **Set up syntax highlighting**:

   Create `Packages/User/dsl.sublime-syntax`:

```yaml
%YAML 1.2
---
name: DAZZLE DSL
file_extensions:
  - dsl
scope: source.dsl

contexts:
  main:
    - match: '#.*$'
      scope: comment.line.dsl
    - match: '\b(module|use|app|entity|surface|experience|service|foreign_model|integration|test)\b'
      scope: keyword.control.dsl
    - match: '\b(str|int|bool|date|datetime|uuid|email|text|decimal|enum|ref)\b'
      scope: storage.type.dsl
    - match: '\b(required|pk|unique|auto_add|auto_update)\b'
      scope: storage.modifier.dsl
    - match: '"[^"]*"'
      scope: string.quoted.double.dsl
```

---

## Other LSP-Compatible Editors

Most modern editors support LSP. Here's the general pattern:

### Generic LSP Setup

1. **Install DAZZLE**: `pip install dazzle`

2. **Configure your editor's LSP client** with:
   - **Server command**: `dazzle lsp`
   - **File extensions**: `.dsl`
   - **Root pattern**: `dazzle.toml`

3. **Language ID**: `dsl`

### Editor-Specific Resources

- **Vim** (with vim-lsp): Similar to Neovim setup
- **Atom** (atom-languageclient): Configure LSP client
- **Eclipse** (LSP4E): Add external server
- **IntelliJ IDEA** (LSP Support plugin): Configure custom server

---

## LSP Architecture

### How It Works

```
┌─────────────┐         LSP Protocol         ┌──────────────┐
│             │◄──────────────────────────────►│              │
│   Editor    │   JSON-RPC over stdio/socket  │  DAZZLE LSP  │
│  (Client)   │                                │   Server     │
│             │◄──────────────────────────────►│              │
└─────────────┘                                └──────────────┘
                                                      │
                                                      ▼
                                               ┌──────────────┐
                                               │   DAZZLE     │
                                               │   Parser     │
                                               │   Linker     │
                                               │   Validator  │
                                               └──────────────┘
```

### LSP Capabilities

DAZZLE LSP server implements:

**Text Synchronization**:
- `textDocument/didOpen`
- `textDocument/didChange`
- `textDocument/didSave`
- `textDocument/didClose`

**Language Features**:
- `textDocument/hover`
- `textDocument/completion`
- `textDocument/definition`
- `textDocument/references`
- `textDocument/documentSymbol`
- `textDocument/signatureHelp`
- `textDocument/rename`
- `textDocument/codeAction`

**Diagnostics**:
- Parse errors
- Validation errors
- Lint warnings
- Pattern detection warnings

### Performance

The LSP server is optimized for:
- **Low latency**: Diagnostics update on-type (< 100ms typical)
- **Low memory**: Incremental parsing and caching
- **Scalability**: Handles projects with 100+ DSL files

---

## Troubleshooting

### LSP Server Not Starting

**Check if dazzle is installed**:
```bash
which dazzle
dazzle --version
```

**Verify LSP mode works**:
```bash
dazzle lsp --help
```

**Check editor LSP logs**:
- VS Code: Output panel → "DAZZLE Language Server"
- Neovim: `:LspLog`
- Emacs: `*lsp-log*` buffer

### No Diagnostics Appearing

1. **Ensure file is in a DAZZLE project**:
   - Must have `dazzle.toml` in project root
   - Or `.dsl` file must be recognized

2. **Check file is valid**:
```bash
dazzle validate your_file.dsl
```

3. **Restart LSP server**:
   - VS Code: Command Palette → "Restart Extension Host"
   - Neovim: `:LspRestart`
   - Emacs: `M-x lsp-workspace-restart`

### Slow Performance

1. **Reduce project size**: Split into modules
2. **Disable on-type validation** (save-only):
   - VS Code: Set `dazzle.validation.onType: false`
3. **Check for loops in experiences**: Pattern detection can be slow on complex flows

### Go-to-Definition Not Working

1. **Ensure symbol is defined**: Use `dazzle validate` to check
2. **Check cross-module references**: May need `use` declaration
3. **Restart LSP**: Sometimes cache gets stale

### Auto-completion Not Showing

1. **Trigger manually**: Ctrl+Space (VS Code), C-x C-o (Neovim)
2. **Check context**: Completions are context-aware
3. **Ensure LSP is attached**: Check status bar (VS Code) or `:LspInfo` (Neovim)

---

## Getting Help

- **Documentation**: [DAZZLE Docs](https://github.com/manwithacat/dazzle/tree/main/docs)
- **Issues**: [GitHub Issues](https://github.com/manwithacat/dazzle/issues)
- **Discussions**: [GitHub Discussions](https://github.com/manwithacat/dazzle/discussions)

---

## Contributing

Want to improve IDE support?

- **VS Code Extension**: `extensions/vscode/`
- **LSP Server**: `src/dazzle/lsp/`
- **Grammar Definitions**: Welcome for other editors!

See [CONTRIBUTING.md](../CONTRIBUTING.md) for details.

---

**Last Updated**: 2025-11-23
**DAZZLE Version**: 0.1.0
