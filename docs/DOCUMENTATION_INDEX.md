# DAZZLE Documentation Index

**Last Updated**: 2025-12-01
**DAZZLE Version**: v0.2.x
**Purpose**: Complete index of all DAZZLE documentation

---

## 📖 Quick Navigation

**Start Here**: [docs/README.md](README.md) - Main documentation hub

**For New Users**:
1. [INSTALLATION.md](INSTALLATION.md) - Get DAZZLE installed
2. [DAZZLE_DSL_QUICK_REFERENCE.md](DAZZLE_DSL_QUICK_REFERENCE.md) - Learn syntax in 5 minutes
3. [v0.2/DAZZLE_DSL_REFERENCE.md](v0.2/DAZZLE_DSL_REFERENCE.md) - Complete language spec
4. [../examples/simple_task/](../examples/simple_task/) - First example project

---

## 📚 Core Documentation (`docs/`)

### Primary Entry Points

| Document | Description | Audience |
|----------|-------------|----------|
| **[README.md](README.md)** | **Main documentation hub** | **All users - START HERE** |
| [INSTALLATION.md](INSTALLATION.md) | Installation guide (Homebrew, pip, pipx) | New users |
| [DAZZLE_DSL_QUICK_REFERENCE.md](DAZZLE_DSL_QUICK_REFERENCE.md) | One-page syntax cheat sheet | All users |

### Language & Syntax (v0.2 - Current)

| Document | Description | Type |
|----------|-------------|------|
| **[v0.2/DAZZLE_DSL_REFERENCE.md](v0.2/DAZZLE_DSL_REFERENCE.md)** | **Complete v0.2 DSL specification** | Markdown |
| [v0.2/DAZZLE_DSL_GRAMMAR.ebnf](v0.2/DAZZLE_DSL_GRAMMAR.ebnf) | Formal EBNF grammar | EBNF |
| [v0.2/DAZZLE_EXAMPLES.dsl](v0.2/DAZZLE_EXAMPLES.dsl) | Annotated DSL examples | DSL |
| [v0.2/MIGRATION_GUIDE.md](v0.2/MIGRATION_GUIDE.md) | v0.1 to v0.2 upgrade guide | Markdown |

### UX Semantic Layer (v0.2 - NEW)

| Document | Description | Type |
|----------|-------------|------|
| **[v0.2/UX_SEMANTIC_LAYER_SPEC.md](v0.2/UX_SEMANTIC_LAYER_SPEC.md)** | **UX Semantic Layer specification** | Markdown |
| [v0.2/APP_LOCAL_VOCABULARY.md](v0.2/APP_LOCAL_VOCABULARY.md) | App-local vocabulary system | Markdown |

### Capabilities & Policies

| Document | Description | Type |
|----------|-------------|------|
| **[CAPABILITIES.md](CAPABILITIES.md)** | **Authoritative capability reference** | Markdown |
| [DEPRECATION_POLICY.md](DEPRECATION_POLICY.md) | Deprecation timeline and policy | Markdown |

### Tools & Integration

| Document | Description | Type |
|----------|-------------|------|
| **[TOOLING.md](TOOLING.md)** | **MCP server, IDE, developer tools** | Markdown |
| [VSCODE_EXTENSION.md](VSCODE_EXTENSION.md) | VS Code extension guide | Markdown |
| [CLI_REFERENCE.md](CLI_REFERENCE.md) | Complete CLI command reference | Markdown |

### Runtime & Features

| Document | Description | Type |
|----------|-------------|------|
| [AUTHENTICATION.md](AUTHENTICATION.md) | Built-in auth system guide | Markdown |
| [E2E_TESTING.md](E2E_TESTING.md) | E2E testing infrastructure | Markdown |
| [SEMANTIC_DOM_CONTRACT.md](SEMANTIC_DOM_CONTRACT.md) | UI attribute specification | Markdown |

---

## 📦 Version Archives

### v0.1 (Stable)

| Document | Description | Type |
|----------|-------------|------|
| [v0.1/DAZZLE_DSL_REFERENCE.md](v0.1/DAZZLE_DSL_REFERENCE.md) | v0.1 DSL specification | Markdown |
| [v0.1/DAZZLE_DSL_GRAMMAR.ebnf](v0.1/DAZZLE_DSL_GRAMMAR.ebnf) | v0.1 EBNF grammar | EBNF |
| [v0.1/DAZZLE_EXAMPLES.dsl](v0.1/DAZZLE_EXAMPLES.dsl) | v0.1 examples | DSL |
| [v0.1/DAZZLE_IR.md](v0.1/DAZZLE_IR.md) | Internal representation (IR) spec | Markdown |

---

## 🔧 Development Documentation (`dev_docs/`)

### Implementation Summaries

| Document | Description | Status |
|----------|-------------|--------|
| [mcp_v0_2_implementation_summary.md](../dev_docs/mcp_v0_2_implementation_summary.md) | MCP v0.2 enhancements summary | ✅ Complete |
| [mcp_server_implementation.md](../dev_docs/mcp_server_implementation.md) | MCP server implementation details | ✅ Complete |

### Release Information

| Document | Description | Version |
|----------|-------------|---------|
| [release_v0_1_1_summary.md](../dev_docs/release_v0_1_1_summary.md) | v0.1.1 release summary | v0.1.1 |
| [releases/2025-11-22-v0.1.0-release-summary.md](../dev_docs/releases/2025-11-22-v0.1.0-release-summary.md) | v0.1.0 official release | v0.1.0 |
| [releases/2025-11-22-release-announcement.md](../dev_docs/releases/2025-11-22-release-announcement.md) | v0.1.0 announcement | v0.1.0 |
| [releases/2025-11-22-stack-consolidation.md](../dev_docs/releases/2025-11-22-stack-consolidation.md) | Stack terminology refactor | v0.1.0 |

### Roadmaps & Planning

| Document | Description | Status |
|----------|-------------|--------|
| [roadmap_v0_2_0.md](../dev_docs/roadmap_v0_2_0.md) | v0.2.0 roadmap | 🔬 In Progress |
| [architecture/dp_dsl_evaluation_and_roadmap.md](../dev_docs/architecture/dp_dsl_evaluation_and_roadmap.md) | Design Pattern DSL eval | 📋 Planned |
| [NEXT_STAGES_SPEC.md](../dev_docs/NEXT_STAGES_SPEC.md) | Future development stages | 📋 Planning |
| [gap_analysis_2025_11_23.md](../dev_docs/gap_analysis_2025_11_23.md) | Gap analysis | 📊 Analysis |

### Bug Fixes & Issues

| Document | Description | Status |
|----------|-------------|--------|
| **[BUG_FIXES_CONSOLIDATED_SUMMARY.md](../dev_docs/BUG_FIXES_CONSOLIDATED_SUMMARY.md)** | **All bug fixes consolidated** | ✅ Complete |
| [BUG_003_DECIMAL_FIELDS_FIXED.md](../dev_docs/BUG_003_DECIMAL_FIELDS_FIXED.md) | Decimal field fix (Django) | ✅ Fixed |
| [CRITICAL_BUGS_FIXED_SUMMARY.md](../dev_docs/CRITICAL_BUGS_FIXED_SUMMARY.md) | URLs and view naming (Django) | ✅ Fixed |
| [express_micro_comprehensive_improvements.md](../dev_docs/express_micro_comprehensive_improvements.md) | Express improvements | ✅ Fixed |
| [express_micro_fixes_summary.md](../dev_docs/express_micro_fixes_summary.md) | Express fixes summary | ✅ Fixed |

### Architecture & Features

| Document | Description | Category |
|----------|-------------|----------|
| [features/MICRO_STACK_SPEC.md](../dev_docs/features/MICRO_STACK_SPEC.md) | Micro stack specification | Architecture |
| [architecture/dazzle_architecture_diagram.md](../dev_docs/architecture/dazzle_architecture_diagram.md) | System architecture | Architecture |

---

## 🎯 Documentation by Use Case

### "I want to learn DAZZLE"
1. [INSTALLATION.md](INSTALLATION.md) - Install DAZZLE
2. [DAZZLE_DSL_QUICK_REFERENCE.md](DAZZLE_DSL_QUICK_REFERENCE.md) - Learn syntax
3. [v0.2/DAZZLE_DSL_REFERENCE.md](v0.2/DAZZLE_DSL_REFERENCE.md) - Deep dive
4. [../examples/simple_task/](../examples/simple_task/) - Build first app

### "I want to use v0.2 features"
1. [v0.2/DAZZLE_DSL_REFERENCE.md](v0.2/DAZZLE_DSL_REFERENCE.md) - v0.2 overview
2. [v0.2/UX_SEMANTIC_LAYER_SPEC.md](v0.2/UX_SEMANTIC_LAYER_SPEC.md) - UX layer details
3. [../examples/support_tickets/](../examples/support_tickets/) - Full showcase
4. [v0.2/DAZZLE_EXAMPLES.dsl](v0.2/DAZZLE_EXAMPLES.dsl) - Syntax examples

### "I want to migrate from v0.1"
1. [v0.2/MIGRATION_GUIDE.md](v0.2/MIGRATION_GUIDE.md) - Step-by-step guide
2. [v0.2/DAZZLE_DSL_REFERENCE.md#migration-from-v01](v0.2/DAZZLE_DSL_REFERENCE.md) - What's changed
3. [v0.2/DAZZLE_EXAMPLES.dsl](v0.2/DAZZLE_EXAMPLES.dsl) - v0.2 examples

### "I want to integrate with tools"
1. **Claude Code**: [TOOLING.md](TOOLING.md) (MCP Server section)
2. **VS Code**: [VSCODE_EXTENSION.md](VSCODE_EXTENSION.md)
3. **Other IDEs**: [TOOLING.md](TOOLING.md) (IDE Integration section)

### "I want to know what features are supported"
1. [CAPABILITIES.md](CAPABILITIES.md) - Current capabilities (authoritative)
2. [DEPRECATION_POLICY.md](DEPRECATION_POLICY.md) - What's deprecated

### "I want to contribute"
1. [../CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution guidelines
2. [../dev_docs/](../dev_docs/) - Architecture docs
3. [v0.1/DAZZLE_IR.md](v0.1/DAZZLE_IR.md) - Internal representation

---

## 📂 Directory Structure

```
docs/
├── README.md                           # Main documentation hub ⭐
├── DOCUMENTATION_INDEX.md              # This file
├── INSTALLATION.md                     # Installation guide
├── DAZZLE_DSL_QUICK_REFERENCE.md      # Quick syntax reference
│
├── v0.2/                               # Current version (v0.2) 🎯
│   ├── DAZZLE_DSL_REFERENCE.md        # Complete v0.2 spec
│   ├── DAZZLE_DSL_GRAMMAR.ebnf        # v0.2 grammar
│   ├── DAZZLE_EXAMPLES.dsl            # v0.2 examples
│   ├── MIGRATION_GUIDE.md             # v0.1 → v0.2 guide
│   ├── UX_SEMANTIC_LAYER_SPEC.md      # UX layer spec (NEW)
│   ├── APP_LOCAL_VOCABULARY.md        # Vocabulary system
│   └── CAPABILITIES_MATRIX.md         # Stack features
│
├── v0.1/                               # Previous version (v0.1)
│   ├── DAZZLE_DSL_REFERENCE.md        # v0.1 spec
│   ├── DAZZLE_DSL_GRAMMAR.ebnf        # v0.1 grammar
│   ├── DAZZLE_EXAMPLES.dsl            # v0.1 examples
│   └── DAZZLE_IR.md                   # IR specification
│
├── TOOLING.md                          # MCP, IDE, developer tools
├── VSCODE_EXTENSION.md                 # VS Code guide
├── CAPABILITIES.md                     # Current capabilities
└── DEPRECATION_POLICY.md               # Deprecation timeline

dev_docs/                               # Development documentation
├── mcp_v0_2_implementation_summary.md
├── mcp_server_implementation.md
├── BUG_FIXES_CONSOLIDATED_SUMMARY.md
├── roadmap_v0_2_0.md
├── releases/
├── architecture/
└── features/

examples/                               # Example projects
├── simple_task/                        # Beginner (v0.2)
├── support_tickets/                    # Intermediate (v0.2)
└── fieldtest_hub/                      # Intermediate (v0.2)
```

---

## 🔑 Key Document Relationships

```
Start Here
    └── README.md
         ├── Language Learning
         │    ├── DAZZLE_DSL_QUICK_REFERENCE.md
         │    ├── v0.2/DAZZLE_DSL_REFERENCE.md
         │    └── v0.2/DAZZLE_EXAMPLES.dsl
         │
         ├── v0.2 Features
         │    ├── v0.2/UX_SEMANTIC_LAYER_SPEC.md
         │    ├── v0.2/MIGRATION_GUIDE.md
         │    └── examples/support_tickets/
         │
         ├── Tool Integration
         │    ├── TOOLING.md (MCP + IDE)
         │    └── VSCODE_EXTENSION.md
         │
         └── Installation
              └── INSTALLATION.md
```

---

## 📊 Documentation Statistics

- **Total Documentation Files**: 20
  - Core docs: 12
  - v0.2 specific: 6
  - v0.1 archives: 4
  - Tool integration: 4
  - Development: 30+ (in dev_docs/)

- **Current Version**: v0.2.0 (Beta)
- **Stable Version**: v0.1.1

---

## 🎯 Version Focus

**Current Development**: v0.2.0
- UX Semantic Layer
- Personas and Workspaces
- Attention Signals
- Enhanced MCP server

**Production Stable**: v0.1.1
- Core DSL features
- Basic CRUD patterns
- Multi-stack support

---

## 📝 Documentation Conventions

Throughout DAZZLE documentation:

- ✨ **NEW** - Features added in v0.2
- ✅ **Stable** - Production-ready
- 🔬 **Beta** - Under development
- 📦 **Deprecated** - Being phased out
- ⭐ **Recommended** - Best starting point
- 🎯 **Current** - Active version

---

## 🔄 Document Update Frequency

| Document Type | Update Frequency |
|---------------|------------------|
| DSL Reference | Major versions |
| Quick Reference | Minor updates as needed |
| Examples | With new features |
| MCP Docs | With MCP changes |
| IDE Integration | With tool updates |
| Installation | With new methods |

---

## 🆘 Finding Help

1. **Syntax questions** → [DAZZLE_DSL_QUICK_REFERENCE.md](DAZZLE_DSL_QUICK_REFERENCE.md)
2. **Detailed reference** → [v0.2/DAZZLE_DSL_REFERENCE.md](v0.2/DAZZLE_DSL_REFERENCE.md)
3. **Examples** → [../examples/](../examples/)
4. **Tool setup** → [MCP_SERVER.md](MCP_SERVER.md) or [VSCODE_EXTENSION.md](VSCODE_EXTENSION.md)
5. **Contributing** → [../CONTRIBUTING.md](../CONTRIBUTING.md)

---

**Last Updated**: 2025-12-01
**Version**: v0.2.x
