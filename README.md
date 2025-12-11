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
| **v0.9.x** (Current) | Messaging channels, UX layer, personas | Active development |
| v0.8.x | Bun CLI + DNR + Ejection | Stable |
| v0.1.x-v0.7.x | Legacy versions | Deprecated |

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

## DSL Constructs

Complete reference: [docs/reference/](docs/reference/)

### Core Constructs

| Construct | Purpose |
|-----------|---------|
| `module` | Namespace declaration for DSL files |
| `app` | Application metadata |
| `use` | Import constructs from other modules |

### Data Modeling

| Construct | Purpose |
|-----------|---------|
| `entity` | Domain models with typed fields and relationships |
| `archetype` | Reusable field templates (e.g., `Timestamped`, `Auditable`) |
| `foreign_model` | External API data structures |

**Entity Field Types**: `str(N)`, `text`, `int`, `decimal(P,S)`, `bool`, `date`, `datetime`, `uuid`, `email`, `enum[...]`

**Relationship Types**: `ref`, `has_many`, `has_one`, `belongs_to`, `embeds`

**Field Modifiers**: `required`, `optional`, `pk`, `unique`, `unique?`, `auto_add`, `auto_update`, `=default`

**Entity Metadata** (LLM cognition hints):
- `intent:` - Semantic purpose description
- `domain:` - Business domain tag (e.g., `crm`, `support`, `identity`)
- `patterns:` - Behavioral patterns (e.g., `lifecycle`, `audit`, `searchable`)

### UI Layer

| Construct | Purpose |
|-----------|---------|
| `surface` | UI screens and forms (list, view, create, edit modes) |
| `workspace` | Dashboard views with regions, filters, and aggregates |
| `experience` | Multi-step wizards and user flows |

**Surface Elements**: `section`, `field`, `action`

**Workspace Elements**: `source`, `filter`, `sort`, `limit`, `display`, `aggregate`, `group_by`

**Workspace Stages**: `stage: "..."` selects a layout archetype:
- `focus_metric` - Single KPI with supporting context
- `scanner_table` - Filterable data table with bulk actions
- `dual_pane_flow` - Master-detail split view
- `monitor_wall` - Grid of status cards
- `command_center` - Multi-region operational dashboard

### Services & Integrations

| Construct | Purpose |
|-----------|---------|
| `service` | External APIs (OpenAPI) or domain services |
| `integration` | Orchestrates data flow between app and external services |

**Service Types**: External API (with `spec`, `auth_profile`) or Domain Service (with `kind`, `input`, `output`, `guarantees`)

**Integration Elements**: `action` (request-response), `sync` (scheduled/event-driven)

### Messaging (v0.9)

| Construct | Purpose |
|-----------|---------|
| `message` | Typed message schemas |
| `channel` | Communication pathways (email, queue, stream) |
| `template` | Reusable message templates |
| `asset` | Static file attachments |
| `document` | Dynamic document generators |

**Channel Operations**: `send` (outbound with triggers), `receive` (inbound with routing)

**Send Triggers**: Entity events, status transitions, field changes, service events, schedules

### UX Semantic Layer

| Construct | Purpose |
|-----------|---------|
| `ux` | UI hints block within surfaces/workspaces |
| `attention` | Conditional alerts (critical, warning, notice, info) |
| `for` | Persona-specific view customization |

**UX Properties**: `purpose`, `show`, `hide`, `sort`, `filter`, `search`, `empty`

**Persona Properties**: `scope`, `show_aggregate`, `action_primary`, `read_only`, `defaults`, `focus`

### Personas & Scenarios

| Construct | Purpose |
|-----------|---------|
| `persona` | User archetypes with goals and proficiency |
| `scenario` | Test data states for development and demos |
| `demo` | Inline fixture data |

**Persona Properties**: `description`, `goals`, `proficiency`, `default_workspace`, `default_route`

**Scenario Properties**: `seed_script`, `for persona` (per-persona config)

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

### DSL Reference
- [DSL Reference Guide](docs/reference/) - Complete DSL documentation
  - [Modules](docs/reference/01-modules.md) - Module and app declarations
  - [Entities](docs/reference/02-entities.md) - Data modeling
  - [Surfaces](docs/reference/03-surfaces.md) - UI screens
  - [Workspaces](docs/reference/04-workspaces.md) - Dashboards
  - [Services](docs/reference/05-services.md) - External and domain services
  - [Integrations](docs/reference/06-integrations.md) - API orchestration
  - [Messaging](docs/reference/07-messaging.md) - Channels and templates
  - [UX Layer](docs/reference/08-ux.md) - Attention signals and personas
  - [Scenarios](docs/reference/09-scenarios.md) - Test data and personas
  - [Experiences](docs/reference/10-experiences.md) - Multi-step flows

### Technical
- [DSL Grammar](docs/v0.9/DAZZLE_DSL_GRAMMAR.ebnf) - Formal EBNF grammar
- [Example Projects](docs/examples/) - Live demos

### Tooling
- [Tooling Guide](docs/TOOLING.md) - MCP server, IDE integration
- [Contributing](CONTRIBUTING.md) - Contribution guidelines

## Contributing

All contributions require AI co-authorship. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT - see [LICENSE](LICENSE)
