# DAZZLE

**Human Intent → Structured DSL → Deterministic Code**

<!-- Versions & Compatibility -->
[![PyPI version](https://img.shields.io/pypi/v/dazzle.svg)](https://pypi.org/project/dazzle/)
[![Python 3.11+](https://img.shields.io/pypi/pyversions/dazzle.svg)](https://pypi.org/project/dazzle/)
[![Homebrew](https://img.shields.io/badge/homebrew-manwithacat%2Ftap-orange)](https://github.com/manwithacat/homebrew-tap)

<!-- Build & Quality -->
[![CI](https://github.com/manwithacat/dazzle/workflows/CI/badge.svg)](https://github.com/manwithacat/dazzle/actions)
[![codecov](https://codecov.io/gh/manwithacat/dazzle/graph/badge.svg)](https://codecov.io/gh/manwithacat/dazzle)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-checked-blue.svg)](https://mypy-lang.org/)

<!-- Downloads & Stats -->
[![PyPI Downloads](https://img.shields.io/pypi/dm/dazzle.svg)](https://pypi.org/project/dazzle/)
[![VS Code Extension](https://img.shields.io/visual-studio-marketplace/i/manwithacat.dazzle-vscode?label=VS%20Code%20installs)](https://marketplace.visualstudio.com/items?itemName=manwithacat.dazzle-vscode)

<!-- Meta -->
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://manwithacat.github.io/dazzle/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/manwithacat/dazzle.svg?style=social)](https://github.com/manwithacat/dazzle)

DAZZLE is a DSL-first toolkit that bridges human specifications and production code. An LLM translates your intent into a structured DSL; from there, all code generation is deterministic and token-efficient.

**The workflow:**
1. **Describe** what you want in natural language
2. **Generate** a precise DSL specification (LLM-assisted, one-time cost)
3. **Iterate** instantly with the Dazzle Native Runtime (DNR)
4. **Deploy** directly — DNR is the runtime, not a scaffold

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

See [MCP Server Guide](docs/architecture/mcp-server.md) for details.

## Current State (v0.19)

The DNR frontend has migrated from a custom signals-based JS runtime to **server-rendered HTMX templates** with Alpine.js for ephemeral client state. This gives us a zero-build-step UI with declarative interactions and no node_modules.

Recent additions:
- **HTMX + DaisyUI frontend** — server-rendered pages, HTMX partial swaps
- **Alpine.js interaction patterns** — inline editing, bulk actions, slide-over panels, debounced search
- **Template fragment system** — composable HTML partials for HTMX swap targets
- **TigerBeetle ledgers** — double-entry accounting with typed transactions
- **Messaging channels** — email, queue, and stream integrations
- **MCP server** — Claude Code integration with 17 consolidated tools

### Roadmap

Frontend UX is the dominant focus area. Next up:
- `search_select` fragment for relationship field lookups
- `FragmentContext` base model to standardize fragment rendering inputs
- Richer workspace layout patterns (dual-pane, monitor wall)

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

## Dazzle Native Runtime (DNR)

DNR is the primary way to run DAZZLE applications:

- **FastAPI backend**: Auto-generated CRUD endpoints with SQLite persistence
- **HTMX + DaisyUI frontend**: Server-rendered pages with declarative interactions
- **Alpine.js interactions**: Client-side state for toggles, selections, and transitions
- **Zero build toolchain**: Three CDN script tags, no node_modules
- **Hot reload**: Changes to DSL files reflect immediately
- **OpenAPI docs**: Automatic Swagger UI at `/docs`

```bash
dazzle dev                       # Start the app
dazzle check                     # Validate DSL files
dazzle show                      # Show project info
dazzle build                     # Build for production
```

## Workflow

```
                                                    ┌─────────────┐
                                               ┌──▶ │ DNR Runtime │ (run directly)
┌─────────────┐     ┌─────────────┐     ┌──────┴──┐ └─────────────┘
│  DSL Files  │ ──▶ │   Parser    │ ──▶ │ AppSpec │
│  (.dsl)     │     │   + Linker  │     │  (IR)   │ ┌─────────────┐
└─────────────┘     └─────────────┘     └──────┬──┘ │    Specs     │ (OpenAPI/AsyncAPI)
                                               └──▶ │  Generator  │
                                                    └─────────────┘
```

1. **Parse**: DSL files are parsed into an AST
2. **Link**: Multi-module references are resolved
3. **AppSpec**: A semantic intermediate representation (IR) captures the full application model
4. **Run**: DNR executes your spec directly — no code generation step

```bash
dazzle check                     # Parse + link + validate
dazzle dev                       # Run instantly with DNR
dazzle specs openapi             # Generate OpenAPI 3.1 spec
dazzle specs asyncapi            # Generate AsyncAPI 3.0 spec
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

### Messaging

| Construct | Purpose |
|-----------|---------|
| `message` | Typed message schemas |
| `channel` | Communication pathways (email, queue, stream) |
| `template` | Reusable message templates |
| `asset` | Static file attachments |
| `document` | Dynamic document generators |

**Channel Operations**: `send` (outbound with triggers), `receive` (inbound with routing)

**Send Triggers**: Entity events, status transitions, field changes, service events, schedules

### Ledgers & Transactions

| Construct | Purpose |
|-----------|---------|
| `ledger` | TigerBeetle account templates for double-entry accounting |
| `transaction` | Multi-leg financial transactions with atomic guarantees |

**Account Types**: `asset`, `liability`, `equity`, `revenue`, `expense`

**Account Flags**: `debits_must_not_exceed_credits`, `credits_must_not_exceed_debits`, `linked`, `history`

**Transaction Features**: `transfer` blocks, `idempotency_key`, `validation` rules, `async`/`sync` execution

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

## Why HTMX, Not React

DAZZLE's frontend is server-rendered HTML with HTMX and Alpine.js. This is a
deliberate architectural choice, not a limitation.

### React's strengths are for humans

React's component model is designed around how human developers think:
compositional UI building blocks, a rich ecosystem of community packages, and
a mental model (declarative state -> view) that maps well to how people reason
about interfaces. For teams of human engineers iterating on bespoke UIs, React
is a strong choice.

### React's weaknesses are for LLM agents

When the primary author is an LLM coding agent, React's strengths become
liabilities:

| Concern | React | HTMX + server templates |
|---------|-------|------------------------|
| **Token cost** | JSX, hooks, state management, bundler config, type definitions — large surface area per feature | HTML fragments returned by the server; minimal client-side code |
| **Build toolchain** | Node, npm/yarn/pnpm, Vite/webpack, TypeScript compiler — each a failure surface the agent must diagnose | Zero build step; three CDN script tags |
| **Implicit context** | Closure scoping, hook ordering rules, render cycle timing — hard for an LLM to hold in context reliably | Explicit: every interaction is an HTTP request with a visible URL and swap target |
| **Ecosystem churn** | Package versions, peer dependency conflicts, breaking changes across React 18/19 — a moving target | HTML is stable; HTMX has had one major version |
| **Debugging** | Stack traces span client bundler, React internals, and async state — requires mental model of the runtime | Server logs show the request; `hx-target` shows where the response goes |
| **Determinism** | Same prompt can produce subtly different hook patterns, each with different edge-case bugs | Server returns HTML; there is one way to render a list |

In short: React optimises for **human ergonomics** (component reuse,
ecosystem leverage, IDE tooling). DAZZLE optimises for **agent ergonomics**
(minimal token cost, zero ambiguity, no build step, deterministic output).

The server-rendered approach also means the entire UI is visible in the
AppSpec IR — DAZZLE can validate, lint, and generate the frontend without
executing JavaScript or maintaining a shadow DOM model.

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

**Full documentation**: [manwithacat.github.io/dazzle](https://manwithacat.github.io/dazzle/)

### Getting Started
- [Installation](docs/getting-started/installation.md) - Install DAZZLE
- [Quickstart](docs/getting-started/quickstart.md) - First steps
- [First App Tutorial](docs/getting-started/first-app.md) - Build your first app

### DSL Reference
- [DSL Reference Guide](docs/reference/) - Complete DSL documentation
  - [Modules](docs/reference/modules.md) - Module and app declarations
  - [Entities](docs/reference/entities.md) - Data modeling
  - [Surfaces](docs/reference/surfaces.md) - UI screens
  - [Workspaces](docs/reference/workspaces.md) - Dashboards
  - [Services](docs/reference/services.md) - External and domain services
  - [Integrations](docs/reference/integrations.md) - API orchestration
  - [Ledgers](docs/reference/ledgers.md) - TigerBeetle double-entry accounting
  - [Messaging](docs/reference/messaging.md) - Channels and templates
  - [UX Layer](docs/reference/ux.md) - Attention signals and personas
  - [Scenarios](docs/reference/scenarios.md) - Test data and personas
  - [Experiences](docs/reference/experiences.md) - Multi-step flows
  - [CLI Reference](docs/reference/cli.md) - Command-line interface
  - [DSL Grammar](docs/reference/grammar.md) - Formal EBNF grammar

### Architecture
- [Architecture Overview](docs/architecture/overview.md) - System design
- [DSL to AppSpec](docs/architecture/dsl-to-appspec.md) - Compilation pipeline
- [MCP Server](docs/architecture/mcp-server.md) - Claude Code integration

### Examples
- [Simple Task](docs/examples/simple-task.md) - Basic todo app
- [Contact Manager](docs/examples/contact-manager.md) - CRM example
- [Ops Dashboard](docs/examples/ops-dashboard.md) - Monitoring dashboard
- [Support Tickets](docs/examples/support-tickets.md) - Ticket system
- [FieldTest Hub](docs/examples/fieldtest-hub.md) - Full-featured demo

### Contributing
- [Development Setup](docs/contributing/dev-setup.md) - Local development
- [Testing Guide](docs/contributing/testing.md) - Running tests
- [Adding Features](docs/contributing/adding-a-feature.md) - Extending DAZZLE

## Contributing

All contributions require AI co-authorship. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT - see [LICENSE](LICENSE)
