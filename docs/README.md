# DAZZLE Documentation

**Current Version**: v0.2.0 (Beta)
**Last Updated**: 2025-11-25

DAZZLE is a declarative specification language for building full-stack applications. Write your domain model and UI semantics once, generate production-ready code for multiple platforms.

## 🚀 Quick Start

**New to DAZZLE? Start here:**

1. **[Installation Guide](INSTALLATION.md)** - Install via Homebrew, pip, or pipx
2. **[Quick Reference](DAZZLE_DSL_QUICK_REFERENCE.md)** - DSL syntax in 5 minutes
3. **[DSL Reference v0.2](v0.2/DAZZLE_DSL_REFERENCE.md)** - Complete language specification
4. **[Examples](../examples/)** - Working example projects

## 📚 Documentation Structure

### Core Documentation

#### Language & Syntax (v0.2)
- **[DSL Reference v0.2](v0.2/DAZZLE_DSL_REFERENCE.md)** - Complete v0.2 specification with UX Semantic Layer
- **[Quick Reference](DAZZLE_DSL_QUICK_REFERENCE.md)** - One-page syntax cheat sheet
- **[DSL Grammar v0.2](v0.2/DAZZLE_DSL_GRAMMAR.ebnf)** - Formal EBNF grammar
- **[Migration Guide](v0.2/MIGRATION_GUIDE.md)** - Upgrade from v0.1 to v0.2
- **[Examples](v0.2/DAZZLE_EXAMPLES.dsl)** - Annotated DSL examples

#### UX Semantic Layer (NEW in v0.2)
- **[UX Semantic Layer Spec](v0.2/UX_SEMANTIC_LAYER_SPEC.md)** - Design philosophy and specification
- **[App-Local Vocabulary](v0.2/APP_LOCAL_VOCABULARY.md)** - Context-specific terminology system
- **[Capabilities Matrix](v0.2/CAPABILITIES_MATRIX.md)** - Feature support across stacks

#### Tools & Integration
- **[MCP Server](MCP_SERVER.md)** - Model Context Protocol server for Claude Code
- **[MCP v0.2 Enhancements](MCP_V0_2_ENHANCEMENTS.md)** - Semantic lookup and example search
- **[IDE Integration](IDE_INTEGRATION.md)** - Editor support overview
- **[VS Code Extension](VSCODE_EXTENSION.md)** - VS Code-specific features

#### Installation & Setup
- **[Installation](INSTALLATION.md)** - Installation methods and troubleshooting
- **[Feature Compatibility](FEATURE_COMPATIBILITY_MATRIX.md)** - Stack feature support

### Version Archives

#### v0.1 (Stable)
- **[DSL Reference v0.1](v0.1/DAZZLE_DSL_REFERENCE.md)** - Original specification
- **[DSL Grammar v0.1](v0.1/DAZZLE_DSL_GRAMMAR.ebnf)** - v0.1 grammar
- **[Examples](v0.1/DAZZLE_EXAMPLES.dsl)** - v0.1 examples
- **[Internal Representation](v0.1/DAZZLE_IR.md)** - IR structure and type system

## 🎯 Learning Paths

### Beginner Path
1. Install DAZZLE → [INSTALLATION.md](INSTALLATION.md)
2. Learn syntax basics → [DAZZLE_DSL_QUICK_REFERENCE.md](DAZZLE_DSL_QUICK_REFERENCE.md)
3. Study simple example → [../examples/simple_task/](../examples/simple_task/)
4. Build your first app → [v0.2/DAZZLE_DSL_REFERENCE.md](v0.2/DAZZLE_DSL_REFERENCE.md)

### Intermediate Path (v0.2 Features)
1. Understand v0.2 concepts → [v0.2/DAZZLE_DSL_REFERENCE.md](v0.2/DAZZLE_DSL_REFERENCE.md)
2. Learn UX Semantic Layer → [v0.2/UX_SEMANTIC_LAYER_SPEC.md](v0.2/UX_SEMANTIC_LAYER_SPEC.md)
3. Study personas & workspaces → [../examples/support_tickets/](../examples/support_tickets/)
4. Master attention signals → [v0.2/DAZZLE_EXAMPLES.dsl](v0.2/DAZZLE_EXAMPLES.dsl)

### Advanced Path
1. Review capabilities matrix → [v0.2/CAPABILITIES_MATRIX.md](v0.2/CAPABILITIES_MATRIX.md)
2. Study IR representation → [v0.1/DAZZLE_IR.md](v0.1/DAZZLE_IR.md)
3. Explore app-local vocabulary → [v0.2/APP_LOCAL_VOCABULARY.md](v0.2/APP_LOCAL_VOCABULARY.md)
4. Set up IDE integration → [IDE_INTEGRATION.md](IDE_INTEGRATION.md)

### Migration Path (v0.1 → v0.2)
1. Review what's new → [v0.2/DAZZLE_DSL_REFERENCE.md#whats-new-in-v02](v0.2/DAZZLE_DSL_REFERENCE.md)
2. Follow migration guide → [v0.2/MIGRATION_GUIDE.md](v0.2/MIGRATION_GUIDE.md)
3. Update your DSL files → Add `ux:` blocks incrementally
4. Test and validate → `dazzle validate`

## 🔍 Find What You Need

### I want to...

**Learn the syntax**
- Quick overview → [DAZZLE_DSL_QUICK_REFERENCE.md](DAZZLE_DSL_QUICK_REFERENCE.md)
- Complete reference → [v0.2/DAZZLE_DSL_REFERENCE.md](v0.2/DAZZLE_DSL_REFERENCE.md)
- See examples → [v0.2/DAZZLE_EXAMPLES.dsl](v0.2/DAZZLE_EXAMPLES.dsl)

**Use v0.2 features**
- Personas → [v0.2/DAZZLE_DSL_REFERENCE.md#persona-variants](v0.2/DAZZLE_DSL_REFERENCE.md)
- Workspaces → [v0.2/DAZZLE_DSL_REFERENCE.md#workspace-construct-new-in-v02](v0.2/DAZZLE_DSL_REFERENCE.md)
- Attention signals → [v0.2/DAZZLE_DSL_REFERENCE.md#attention-signals](v0.2/DAZZLE_DSL_REFERENCE.md)
- UX blocks → [v0.2/UX_SEMANTIC_LAYER_SPEC.md](v0.2/UX_SEMANTIC_LAYER_SPEC.md)

**Integrate with tools**
- Claude Code (MCP) → [MCP_SERVER.md](MCP_SERVER.md) + [MCP_V0_2_ENHANCEMENTS.md](MCP_V0_2_ENHANCEMENTS.md)
- VS Code → [VSCODE_EXTENSION.md](VSCODE_EXTENSION.md)
- Other IDEs → [IDE_INTEGRATION.md](IDE_INTEGRATION.md)

**Check stack support**
- What can each stack do? → [v0.2/CAPABILITIES_MATRIX.md](v0.2/CAPABILITIES_MATRIX.md)
- Feature compatibility → [FEATURE_COMPATIBILITY_MATRIX.md](FEATURE_COMPATIBILITY_MATRIX.md)

**Migrate from v0.1**
- Migration guide → [v0.2/MIGRATION_GUIDE.md](v0.2/MIGRATION_GUIDE.md)
- What's changed → [v0.2/DAZZLE_DSL_REFERENCE.md#migration-from-v01](v0.2/DAZZLE_DSL_REFERENCE.md)

## 📖 Key Concepts (v0.2)

### Core Constructs
- **Entity** - Domain models (User, Task, Device, etc.)
- **Surface** - UI/API interfaces (list, view, create, edit)
- **Workspace** ✨ NEW - Composed dashboards and information hubs
- **Module** - Namespace for organizing DSL across files

### UX Semantic Layer ✨ NEW
- **Purpose** - Why a surface/workspace exists
- **Information Needs** - What data matters (show, sort, filter, search)
- **Attention Signals** - Data-driven alerts (critical, warning, notice)
- **Persona Variants** - Role-based adaptations (admin, manager, member)
- **Scope** - Data filtering per persona

### Expression System
- **Conditions** - Boolean expressions for filters and signals
- **Aggregates** - Computed metrics (count, sum, avg, min, max)
- **Functions** - Built-in helpers (days_since, round, etc.)

## 🎨 Design Philosophy

DAZZLE v0.2 embraces **semantic specification over visual prescription**:

✅ **Express WHAT and WHY** - Define user needs and business intent
❌ **Not HOW** - Don't prescribe colors, layouts, or visual styles

Example:
```dsl
ux:
  purpose: "Monitor critical system alerts"  # WHY

  attention critical:
    when: status = failed                    # WHAT matters
    message: "System failure detected"       # User impact

  for engineer:
    scope: team = current_user.team          # WHO sees it
```

Stack generators interpret this semantic intent into platform-appropriate implementations.

## 🛠️ Development Documentation

For contributors and advanced users, see:
- **[../dev_docs/](../dev_docs/)** - Architecture, roadmaps, bug fixes
- **[../CONTRIBUTING.md](../CONTRIBUTING.md)** - Contribution guidelines
- **[Full Documentation Index](DOCUMENTATION_INDEX.md)** - Complete file listing

## 📦 Example Projects

Located in `../examples/`:

| Project | Complexity | v0.2 Features |
|---------|------------|---------------|
| **simple_task** | Beginner | ✅ ux blocks, personas, workspaces |
| **support_tickets** | Intermediate | ✅ Full UX Semantic Layer showcase |
| **fieldtest_hub** | Intermediate | ✅ Workspaces, personas |

## 🔗 External Resources

- **GitHub**: [anthropics/dazzle](https://github.com/anthropics/dazzle) *(placeholder)*
- **Homebrew**: `brew install dazzle`
- **PyPI**: `pip install dazzle`
- **Documentation**: This repository

## 📝 Documentation Conventions

- ✨ **NEW** - Features added in v0.2
- ✅ **Stable** - Production-ready features
- 🔬 **Beta** - Features under development
- 📦 **Deprecated** - Features being phased out

## 🆘 Getting Help

1. Check the [Quick Reference](DAZZLE_DSL_QUICK_REFERENCE.md)
2. Search the [DSL Reference](v0.2/DAZZLE_DSL_REFERENCE.md)
3. Review [Example Projects](../examples/)
4. File an issue on GitHub *(coming soon)*

---

**Version**: DAZZLE v0.2.0 (Beta)
**License**: See [../LICENSE](../LICENSE)
**Maintained by**: Anthropic *(placeholder)*
