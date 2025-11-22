# DAZZLE IDE Extensions

This directory contains IDE extensions and editor integrations for DAZZLE DSL.

## Available Extensions

### 📦 VSCode Extension

**Location**: [`vscode/`](vscode/)

Full-featured Visual Studio Code extension with Language Server Protocol (LSP) support.

**Features**:
- ✅ Syntax highlighting for `.dsl` files
- ✅ Real-time validation and diagnostics
- ✅ Hover documentation with rich formatting
- ✅ Go-to-definition for entities and surfaces
- ✅ Smart autocomplete for field types and modifiers
- ✅ Document symbols and outline view
- ✅ Automatic LSP server detection
- ✅ Graceful degradation when LSP unavailable

**Status**: ✅ Complete (v0.3.0)

**Installation**: See [vscode/README.md](vscode/README.md)

**Quick Start**:
```bash
# Development installation (symlink)
ln -s /path/to/dazzle/extensions/vscode ~/.vscode/extensions/dazzle-dsl-0.3.0

# Reload VSCode
# Open a .dsl file
# Enjoy full IDE features!
```

## Planned Extensions

### 🚧 JetBrains Plugin

**Target IDEs**: PyCharm, IntelliJ IDEA, WebStorm

**Planned Features**:
- Syntax highlighting
- Code completion
- Error highlighting
- Quick documentation
- Refactoring support
- Code navigation

**Status**: Planned

### 🚧 Emacs Mode

**Target**: Emacs with LSP mode

**Planned Features**:
- Major mode for `.dsl` files
- Syntax highlighting (tree-sitter)
- LSP client integration
- Company-mode completion
- Flycheck diagnostics

**Status**: Planned

### 🚧 Vim/Neovim Plugin

**Target**: Vim 8+, Neovim 0.5+

**Planned Features**:
- Syntax highlighting
- LSP integration (via coc.nvim or native LSP)
- Autocompletion
- Error highlighting

**Status**: Planned

## Extension Architecture

### Common Components

All extensions share:

1. **LSP Server**: Python-based LSP server (`src/dazzle/lsp/server.py`)
   - Provides language intelligence
   - Runs independently of editor
   - Implements LSP specification

2. **TextMate Grammar**: Syntax highlighting rules (`vscode/syntaxes/dazzle.tmLanguage.json`)
   - Can be adapted for other editors
   - Covers full DSL syntax

3. **Language Configuration**: Editor behavior (`vscode/language-configuration.json`)
   - Comment tokens
   - Brackets and quotes
   - Indentation rules

### LSP Server

The LSP server is editor-agnostic:

```bash
# Start LSP server manually
python -m dazzle.lsp

# Or via editor extension
# Extension spawns server automatically
```

**LSP Features Provided**:
- `textDocument/hover` - Rich hover documentation
- `textDocument/definition` - Go-to-definition
- `textDocument/completion` - Autocomplete
- `textDocument/documentSymbol` - Outline view
- `textDocument/didOpen/didChange/didSave` - File lifecycle

See [LSP Implementation Details](../devdocs/PHASE3_COMPLETE.md).

## Creating a New Extension

### For Your Editor

Want DAZZLE support in your favorite editor? Here's how:

1. **Check LSP Support**: Does your editor support LSP?
   - Yes: Create LSP client extension (easier)
   - No: Implement features directly (harder)

2. **Start with Syntax Highlighting**:
   - Adapt TextMate grammar or create new
   - Cover entities, surfaces, field types, comments

3. **Add LSP Client**:
   - Connect to `python -m dazzle.lsp`
   - Register `.dsl` file association
   - Handle LSP responses

4. **Test with Examples**:
   - Use `examples/` for testing
   - Verify hover, completion, diagnostics work

5. **Document**:
   - Create README with installation steps
   - Add screenshots
   - Explain features

### Extension Checklist

- [ ] Syntax highlighting for basic DSL
- [ ] File association for `.dsl` files
- [ ] LSP client integration
- [ ] Hover documentation
- [ ] Go-to-definition
- [ ] Autocomplete
- [ ] Document symbols
- [ ] Real-time diagnostics
- [ ] Installation instructions
- [ ] Screenshots/demo
- [ ] Testing with examples

## Contributing

We welcome contributions for any editor!

### VSCode Improvements

Current VSCode extension could be enhanced:

- [ ] Semantic syntax highlighting (LSP-based)
- [ ] Code snippets for common patterns
- [ ] Code actions (quick fixes)
- [ ] Refactoring support (rename)
- [ ] Code lens (show usage counts)
- [ ] Workspace symbols
- [ ] Formatting provider
- [ ] Testing integration

See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

### New Editor Support

Priority editors for community contributions:

1. **JetBrains IDEs** - Popular for Python/web development
2. **Emacs** - Strong among backend developers
3. **Vim/Neovim** - Widely used in terminal workflows
4. **Sublime Text** - Lightweight alternative
5. **Atom** - GitHub's editor (if still maintained)

### Resources

**LSP Specification**:
- [Official LSP Spec](https://microsoft.github.io/language-server-protocol/)
- [LSP Implementations](https://langserver.org/)

**Editor Plugin Development**:
- [VSCode Extension API](https://code.visualstudio.com/api)
- [JetBrains Plugin SDK](https://plugins.jetbrains.com/docs/intellij/welcome.html)
- [Emacs LSP Mode](https://emacs-lsp.github.io/lsp-mode/)
- [Neovim LSP](https://neovim.io/doc/user/lsp.html)

**TextMate Grammars**:
- [TextMate Grammar Guide](https://macromates.com/manual/en/language_grammars)
- [VSCode Syntax Highlight Guide](https://code.visualstudio.com/api/language-extensions/syntax-highlight-guide)

## Testing Extensions

### Manual Testing

1. Install extension in your editor
2. Open example project: `examples/simple_task/`
3. Test features:
   - Syntax highlighting
   - Hover over `Task` entity
   - Go to definition of entity reference
   - Trigger autocomplete in field type
   - Check diagnostics on save
   - View document outline

### Automated Testing

For VSCode:
```bash
cd vscode
npm test
```

For other editors, add appropriate test framework.

## Documentation

Each extension should include:

- **README.md**: Installation, features, screenshots
- **CHANGELOG.md**: Version history
- **License**: MIT (consistent with main project)
- **Package metadata**: Name, version, author, repo

## Support

Questions about extensions?

- **VSCode**: See [vscode/README.md](vscode/README.md)
- **LSP Server**: See [LSP docs](../devdocs/PHASE3_COMPLETE.md)
- **New Extension**: Open an [issue](https://github.com/yourusername/dazzle/issues)
- **General**: [GitHub Discussions](https://github.com/yourusername/dazzle/discussions)

## License

All extensions are licensed under MIT, same as the main project.

---

**Build great developer experiences!** 💡
