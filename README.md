# DAZZLE

**Domain-Aware, Token-Efficient DSL for LLM-Enabled Apps**

[![CI](https://github.com/manwithacat/dazzle/workflows/CI/badge.svg)](https://github.com/manwithacat/dazzle/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

DAZZLE is a DSL-first toolkit for designing applications from high-level specifications. Define your domain model once, run it instantly with the **Dazzle Native Runtime (DNR)**.

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

See [MCP Integration](docs/MCP_INTEGRATION.md) for details.

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
dazzle dnr serve

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
dazzle dnr serve                 # Start the app
dazzle dnr build-ui              # Build static UI assets
dazzle dnr build-api             # Generate API spec
dazzle dnr info                  # Show project info
```

## Workflow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  DSL Files  │ ──▶ │   Parser    │ ──▶ │  IR/AppSpec │ ──▶ │ DNR Runtime │
│  (.dsl)     │     │   + Linker  │     │  (Semantic) │     │ (Live App)  │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

1. **Parse**: DSL files are parsed into an AST
2. **Link**: Multi-module references are resolved
3. **AppSpec**: A semantic intermediate representation (IR) captures the full application model
4. **Run**: DNR executes the AppSpec directly as a live application

```bash
dazzle validate                  # Parse + link + validate
dazzle layout-plan               # Visualize workspace layouts
dazzle dnr serve                 # Run the application
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

## Code Generation (Optional)

For custom deployments, DAZZLE provides code generation as an alternative to DNR:

| Stack | Status | Output |
|-------|--------|--------|
| `docker` | 🚧 In Progress | Docker Compose configuration for DNR apps |
| `base` | ✅ Available | Base builder for custom stack implementations |

Legacy stacks (`openapi`, `micro`, `django_api`, `express_micro`, `nextjs_semantic`, `terraform`) are deprecated in favor of DNR.

```bash
dazzle stacks               # List available stacks
dazzle build --stack docker # Generate Docker deployment
```

### Custom Stacks

Use the `base` builder to create your own code generation stack:

```python
from dazzle.stacks.base import BaseBackend

class MyStack(BaseBackend):
    def generate(self, appspec, output_dir):
        # Transform appspec into your target format
        ...
```

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

- [DSL Quick Reference](docs/DAZZLE_DSL_QUICK_REFERENCE.md) - Language specification
- [DNR CLI Reference](docs/dnr/CLI.md) - Command-line interface
- [Example Projects](docs/EXAMPLES.md) - Live demos with E2E test coverage
- [Custom Stacks](docs/CUSTOM_STACKS.md) - Creating code generation stacks
- [Contributing](CONTRIBUTING.md) - Contribution guidelines

## Contributing

All contributions require AI co-authorship. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT - see [LICENSE](LICENSE)
