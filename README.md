# DAZZLE

**Human Intent → Structured DSL → Deterministic Code**

[![CI](https://github.com/manwithacat/dazzle/workflows/CI/badge.svg)](https://github.com/manwithacat/dazzle/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

DAZZLE is a DSL-first toolkit that bridges human specifications and production code. An LLM translates your intent into a structured DSL; from there, all code generation is deterministic and token-efficient.

**The workflow:**
1. **Describe** what you want in natural language
2. **Generate** a precise DSL specification (LLM-assisted, one-time cost)
3. **Iterate** instantly with the Dazzle Native Runtime (DNR)
4. **Eject** to standalone FastAPI + React when ready for production

## Install

```bash
# Homebrew (macOS/Linux) - MCP server auto-registered
brew install manwithacat/tap/dazzle

# PyPI
pip install dazzle

# VS Code Extension
code --install-extension manwithacat.dazzle-vscode
```

**Downloads**: [VS Code Extension](https://marketplace.visualstudio.com/items?itemName=manwithacat.dazzle-vscode) · [Homebrew Formula](https://github.com/manwithacat/homebrew-tap)

### Claude Code Integration (MCP Server)

DAZZLE includes MCP server support for enhanced tooling in Claude Code.

**Homebrew**: MCP server is automatically registered during installation.

**PyPI/pip**: Register the MCP server manually after installation:
```bash
dazzle mcp-setup
```

Verify registration:
```bash
dazzle mcp-check
```

When using Claude Code with a DAZZLE project, you'll have access to tools like:
- `validate_dsl` - Validate all DSL files
- `build` - Generate code from DSL specifications
- `inspect_entity` - Inspect entity definitions
- `analyze_patterns` - Detect CRUD and integration patterns
- And more! Ask Claude: "What DAZZLE tools do you have access to?"

See [Tooling Guide](docs/TOOLING.md) for details.

## Version Status

| Version | Features | Status |
|---------|----------|--------|
| **v0.8.x** (Current) | New Bun CLI + DNR + Ejection | Active development |
| v0.7.x | LLM Cognition Layer + State Machines | Stable |
| v0.1.x-v0.6.x | Legacy versions | Deprecated |

- **DNR** is for rapid iteration - run your DSL directly without code generation
- **Ejection** generates standalone FastAPI + React when you need production deployment

## The DSL

DAZZLE uses a machine-first DSL optimized for LLM consumption and generation.

```dsl
module my_app

app todo "Todo Application"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  completed: bool=false
  created_at: datetime auto_add

surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title "Title"
    field completed "Done"
```

## Quick Start

```bash
# Navigate to any DAZZLE project
cd examples/simple_task

# Start the app
dazzle dev

# Open http://localhost:3000 for the UI
# Open http://localhost:8000/docs for the API
```

That's it. No code generation, no build step—your DSL runs directly.

## Dazzle Native Runtime (DNR)

DNR is the primary way to run DAZZLE applications:

- **FastAPI Backend**: Auto-generated CRUD endpoints with SQLite persistence
- **Signals-based UI**: Reactive JavaScript frontend with no virtual DOM
- **Hot Reload**: Changes to DSL files reflect immediately
- **OpenAPI Docs**: Automatic Swagger UI at `/docs`

```bash
dazzle dev                       # Start the app
dazzle check                     # Validate DSL files
dazzle show                      # Show project info
dazzle build                     # Build for production
```

## Workflow

```
                                                    ┌─────────────┐
                                               ┌──▶ │ DNR Runtime │ (rapid iteration)
┌─────────────┐     ┌─────────────┐     ┌──────┴──┐ └─────────────┘
│  DSL Files  │ ──▶ │   Parser    │ ──▶ │ AppSpec │
│  (.dsl)     │     │   + Linker  │     │  (IR)   │ ┌─────────────┐
└─────────────┘     └─────────────┘     └──────┬──┘ │  Ejection   │ (production code)
                                               └──▶ │  Toolchain  │
                                                    └─────────────┘
```

1. **Parse**: DSL files are parsed into an AST
2. **Link**: Multi-module references are resolved
3. **AppSpec**: A semantic intermediate representation (IR) captures the full application model
4. **Run or Eject**:
   - **DNR**: Execute directly for instant iteration
   - **Eject**: Generate standalone code for production

```bash
dazzle check                     # Parse + link + validate
dazzle dev                       # Run instantly with DNR
dazzle eject                     # Generate standalone code
```

## Semantic Concepts

### Entities
Domain models with typed fields, constraints, and relationships.

```dsl
entity User "User":
  id: uuid pk
  email: email unique required
  role: enum[admin,user]=user
  profile: ref Profile optional
```

### Surfaces
UI entry points that present entity data in specific modes.

```dsl
surface user_list "Users":
  uses entity User
  mode: list              # list | view | create | edit

  section main:
    field email "Email"
    field role "Role"
```

### Workspaces
Composition of related data views for user-centric interfaces. Workspaces automatically convert to semantic layouts with intelligent signal inference and attention budget management.

```dsl
workspace dashboard "Dashboard":
  purpose: "Overview of key metrics"

  # Aggregate regions become KPI signals
  task_count:
    source: Task
    aggregate:
      total: count(Task)

  # Limited regions become curated lists
  urgent_tasks:
    source: Task
    limit: 5

  # Unlimited regions become browsable tables
  all_tasks:
    source: Task
```

Visualize layouts with `dazzle layout-plan`:
- Automatic archetype selection (FOCUS_METRIC, MONITOR_WALL, etc.)
- Surface allocation and signal assignment
- Attention budget analysis

### Experiences
Multi-step workflows connecting surfaces into user journeys.

```dsl
experience onboarding "User Onboarding":
  start at step signup

  step signup:
    kind: surface
    surface user_create
    on success -> step welcome
```

### Services & Integrations
External API connections with auth profiles.

```dsl
service github "GitHub API":
  spec: url "https://api.github.com/openapi.yaml"
  auth_profile: oauth2_pkce scopes="read:user"
```

## Ejection: From Prototype to Production

When your MVP is ready for production, **eject** to standalone code:

```bash
dazzle eject                        # Generate full application
dazzle eject --backend-only         # Backend only
dazzle eject --dry-run              # Preview what will be generated
```

### What Gets Generated

| Component | Output |
|-----------|--------|
| **Backend** | FastAPI + SQLAlchemy + Pydantic |
| **Frontend** | React + TypeScript + TanStack Query + Zod |
| **Testing** | Schemathesis (contract) + Pytest (unit) |
| **CI/CD** | GitHub Actions or GitLab CI |
| **Infrastructure** | Docker Compose (dev + prod) |

### Configuration

Add to your `dazzle.toml`:

```toml
[ejection]
enabled = true

[ejection.backend]
framework = "fastapi"

[ejection.frontend]
framework = "react"

[ejection.output]
directory = "generated"
```

### Verification

Ejected code is verified to be completely independent from DAZZLE:

```bash
dazzle eject verify ./generated     # Verify independence
```

The verification ensures:
- No Dazzle imports in generated code
- No runtime DSL/AppSpec loaders
- No template merge markers
- Fully standalone, deployable without DAZZLE installed

### When to Eject

| Use Case | Recommendation |
|----------|----------------|
| Rapid prototyping | Stay with DNR |
| Frequent DSL changes | Stay with DNR |
| Production deployment | Eject |
| Custom infrastructure | Eject |
| Code review/audit requirements | Eject |

## IDE Support

Full Language Server Protocol (LSP) implementation with:
- Real-time validation and diagnostics
- Hover documentation
- Go-to-definition
- Auto-completion
- Document symbols

Works with VS Code, Neovim, Emacs, and any LSP-compatible editor.

## Project Structure

```
my_project/
├── dazzle.toml        # Project manifest
├── core.dsl           # Domain models
├── ui.dsl             # Surfaces
└── build/             # Generated artifacts
```

## Documentation

### Getting Started
- [Philosophy](docs/PHILOSOPHY.md) - How DAZZLE's features work together
- [Example Projects](docs/EXAMPLES.md) - Live demos with E2E test coverage
- [Installation](docs/INSTALLATION.md) - Setup instructions

### Reference
- [DSL Quick Reference](docs/DAZZLE_DSL_QUICK_REFERENCE.md) - Language specification
- [DNR CLI Reference](docs/dnr/CLI.md) - Command-line interface
- [DNR Architecture](docs/dnr/ARCHITECTURE.md) - Runtime internals

### Ejection
- [Ejection Toolchain](docs/design/EJECTION_TOOLCHAIN_v0.7.2.md) - Design specification
- [LLM Cognition Layer](docs/design/LLM_COGNITION_DSL_v0.7.1.md) - Intent, archetypes, examples

### Tooling
- [Tooling Guide](docs/TOOLING.md) - MCP server, IDE integration, developer tools
- [VS Code Extension](docs/VSCODE_EXTENSION.md) - Editor support

### Advanced
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Common issues and solutions
- [Contributing](CONTRIBUTING.md) - Contribution guidelines

## Contributing

All contributions require AI co-authorship. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT - see [LICENSE](LICENSE)
