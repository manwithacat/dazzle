# DAZZLE

**Domain-Aware, Token-Efficient DSL for LLM-Enabled Apps**

[![CI](https://github.com/manwithacat/dazzle/workflows/CI/badge.svg)](https://github.com/manwithacat/dazzle/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

DAZZLE is a DSL-first toolkit for designing applications from high-level specifications. Define your domain model once, generate concrete artifacts for any stack.

## Install

```bash
# Homebrew (macOS/Linux)
brew install manwithacat/tap/dazzle

# PyPI
pip install dazzle

# VS Code Extension
code --install-extension manwithacat.dazzle-vscode
```

**Downloads**: [VS Code Extension](https://marketplace.visualstudio.com/items?itemName=manwithacat.dazzle-vscode) · [Homebrew Formula](https://github.com/manwithacat/homebrew-tap)

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

## Workflow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  DSL Files  │ ──▶ │   Parser    │ ──▶ │  IR/AppSpec │ ──▶ │  Artifacts  │
│  (.dsl)     │     │   + Linker  │     │  (Semantic) │     │  (Code)     │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

1. **Parse**: DSL files are parsed into an AST
2. **Link**: Multi-module references are resolved
3. **AppSpec**: A semantic intermediate representation (IR) captures the full application model
4. **Generate**: Stack backends transform the AppSpec into concrete artifacts

```bash
dazzle validate              # Parse + link + validate
dazzle build --stack openapi # Generate artifacts
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

## Stacks

Stacks transform the AppSpec into technology-specific artifacts.

| Stack | Status | Output |
|-------|--------|--------|
| `openapi` | ✅ Stable | OpenAPI 3.0 spec |
| `micro` | ✅ Stable | Django micro app |
| `django_next` | 🚧 In Progress | Django + Next.js + Docker |
| `fastapi` | 📋 Planned | FastAPI + SQLAlchemy |
| `prisma` | 📋 Planned | Prisma schema |
| `graphql` | 📋 Planned | GraphQL schema + resolvers |

```bash
dazzle stacks               # List available stacks
dazzle build --stack micro  # Generate Django app
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

- [DSL Reference](docs/DSL_REFERENCE.md) - Language specification
- [CLI Reference](docs/CLI_REFERENCE.md) - Command-line interface
- [Stack Guide](docs/STACK_GUIDE.md) - Creating custom stacks
- [Contributing](CONTRIBUTING.md) - Contribution guidelines

## Contributing

All contributions require AI co-authorship. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT - see [LICENSE](LICENSE)
