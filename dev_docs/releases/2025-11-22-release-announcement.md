# DAZZLE v0.1.0 Release Announcement

## 🎉 DAZZLE v0.1.0 is now available!

DAZZLE (Domain-Aware, Token-Efficient DSL for LLM-Enabled Apps) is a machine-first software design experiment where humans describe business intent in natural language, LLMs translate it into a compact DSL, and tooling generates production-ready applications.

### Installation

**Homebrew (macOS):**
```bash
brew tap manwithacat/tap
brew install dazzle
```

**Fast alternatives:**
```bash
# pipx (30 seconds)
brew install pipx
pipx install dazzle

# uv (10 seconds - fastest!)
brew install uv
uv tool install dazzle

# pip (30 seconds)
pip install dazzle
```

**Note**: Homebrew installation takes ~15 minutes on first install (builds from source with Rust). Bottles coming in v0.1.1 for instant installation.

### Quick Start

```bash
# Create a new project
dazzle init my-app
cd my-app

# Write your DSL
cat > dsl/app.dsl << 'EOF'
module myapp.core
app myapp "My Application"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  status: enum[todo,in_progress,done] = todo
  created_at: datetime auto_add
EOF

# Validate
dazzle validate

# Build Django application
dazzle build
```

### What's in v0.1.0

**Core Features:**
- ✅ DSL parser for domain models, surfaces, experiences
- ✅ Module system with dependency resolution
- ✅ Django micro-modular backend
- ✅ CLI with init, validate, lint, build commands
- ✅ Homebrew distribution
- ✅ Comprehensive documentation

**CLI Commands:**
- `dazzle init` - Initialize new project
- `dazzle validate` - Validate DSL specifications
- `dazzle lint` - Run extended validation rules
- `dazzle build` - Generate Django application
- `dazzle backends` - List available backends

**What Works:**
- Domain model definition
- Basic surface (UI) specs
- Experience (flow) definitions
- Service integrations
- Foreign model declarations
- Django code generation
- Project scaffolding

**Known Limitations:**
- Some backend features incomplete
- Limited error messages in some cases
- No `--version` flag yet (use `--help`)
- First-time Homebrew install is slow (~15 min)

### Distribution

**Homebrew Tap:**
- Repository: https://github.com/manwithacat/homebrew-tap
- Formula tested on macOS 14 (Apple Silicon & Intel)
- Includes all dependencies (no manual setup required)

**PyPI Package:**
- Available via pip, pipx, uv
- Faster installation than Homebrew
- Works on macOS, Linux, Windows

**VS Code Extension:**
- Syntax highlighting for `.dsl` files
- LSP integration (hover, diagnostics)
- Coming soon to VS Code Marketplace

### Documentation

- **Main Repository**: https://github.com/manwithacat/dazzle
- **DSL Reference**: https://github.com/manwithacat/dazzle/blob/main/docs/DAZZLE_DSL_REFERENCE_0_1.md
- **Grammar**: https://github.com/manwithacat/dazzle/blob/main/docs/DAZZLE_DSL_GRAMMAR_0_1.ebnf
- **Examples**: https://github.com/manwithacat/dazzle/tree/main/docs/examples
- **Distribution**: https://github.com/manwithacat/dazzle/blob/main/DISTRIBUTION.md

### What's Next

**v0.1.1 (Next Patch):**
- 🔜 Homebrew bottles for instant installation
- 🔜 `--version` flag implementation
- 🔜 Improved error messages
- 🔜 Bug fixes from user feedback

**v0.2.0 (Future):**
- 🔮 Additional backends (FastAPI, Next.js)
- 🔮 Enhanced LLM integration
- 🔮 More DSL features
- 🔮 Production deployment tooling

### Community

- **Issues**: https://github.com/manwithacat/dazzle/issues
- **Discussions**: https://github.com/manwithacat/dazzle/discussions
- **Contributing**: https://github.com/manwithacat/dazzle/blob/main/CONTRIBUTING.md

### Acknowledgments

This is an experimental v0.1 release focusing on proving the core loop is viable and token-efficient. Feedback, issues, and contributions welcome!

---

**Install now:**
```bash
brew tap manwithacat/tap && brew install dazzle
# or
pipx install dazzle
```

**Get started:**
```bash
dazzle init my-project && cd my-project && dazzle build
```

🚀 Start building apps with LLM-assisted development!
