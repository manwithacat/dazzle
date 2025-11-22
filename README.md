# DAZZLE

**Domain-Aware, Token-Efficient DSL for LLM-Enabled Apps**

A DSL-first toolkit for designing and generating applications from high-level specifications. DAZZLE enables you to define your application's domain model, UI surfaces, and integrations in a concise, machine-first language, then generate concrete artifacts like OpenAPI specs, database schemas, and application code.

[![CI](https://github.com/yourusername/dazzle/workflows/CI/badge.svg)](https://github.com/yourusername/dazzle/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- **🎯 Machine-First DSL**: Optimized for LLM consumption and generation
- **🔗 Multi-Module Support**: Organize large projects across multiple files
- **✨ Semantic Validation**: Catch errors early with comprehensive validation
- **🔌 Plugin System**: Extensible backend architecture with stacks
- **📊 OpenAPI Generation**: Built-in OpenAPI 3.0 backend
- **💡 IDE Support**: Full Language Server Protocol (LSP) with VSCode extension
- **🔍 Real-time Diagnostics**: Live validation and error reporting in your editor
- **🧪 Production-Ready**: Full test suite with CI/CD and build validation

## Quick Start

### Installation

```bash
# Install from PyPI (when published)
pip install dazzle

# Or install in editable mode for development
git clone https://github.com/manwithacat/dazzle.git
cd dazzle
pip install -e .
```

### Your First DAZZLE Project

Create `my_app.dsl`:

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

Create `dazzle.toml`:

```toml
[project]
name = "todo"
version = "0.1.0"
root = "my_app"

[modules]
paths = ["./"]
```

Generate OpenAPI spec:

```bash
dazzle validate                        # Validate DSL
dazzle build --backend openapi --out ./build
```

View the generated `build/openapi.yaml` in Swagger UI!

## Testing with AI Assistants

DAZZLE is designed to be **LLM-friendly** - AI assistants should be able to understand and build DAZZLE projects with minimal guidance. Test this yourself!

### Recommended Test Prompt

Try this with a fresh AI assistant (ChatGPT, Claude, etc.):

```
You're exploring a new codebase. This folder contains a DSL-based application project.

Your task:
  1. Investigate: Figure out what framework/tool this uses and what it does
  2. Validate: Ensure the configuration is correct
  3. Build: Generate the application artifacts
  4. Verify: Confirm the build was successful

Work step-by-step. Explain your reasoning as you go. If you encounter issues,
troubleshoot and document your fixes.

Success criteria:
  - You understand what the project does
  - All validation passes
  - Artifacts are generated
  - You can explain what was built
```

### Evaluating Success

A successful LLM interaction should:

✅ **Discover the manifest** - Find and read `dazzle.toml`
✅ **Identify DAZZLE** - Recognize this as a DAZZLE DSL project
✅ **Locate DSL files** - Find files in the configured module paths
✅ **Run validation** - Execute `dazzle validate` before building
✅ **Choose appropriate command** - Use `dazzle build` or `dazzle demo`
✅ **Handle errors gracefully** - Diagnose and fix issues (like template variables)
✅ **Generate artifacts** - Successfully create output in `build/` directory
✅ **Explain output** - Describe what was generated and why

### Hints for Making Progress

If the LLM gets stuck, try these progressive hints:

**Hint 1 - Tool Discovery**:
```
"Look for configuration files that might indicate what tool this uses."
```

**Hint 2 - Command Help**:
```
"Try running 'dazzle --help' to see available commands."
```

**Hint 3 - Common Pattern**:
```
"Most DSL tools follow a validate → build workflow."
```

**Hint 4 - Direct Guidance**:
```
"Run: dazzle validate && dazzle build"
```

### Why This Matters

DAZZLE's **machine-first design** means:
- **Token-efficient syntax** - Minimal tokens for maximum meaning
- **Clear semantics** - Unambiguous constructs that LLMs can reason about
- **Discoverable structure** - Standard patterns (manifest → modules → entities)
- **Rich context** - Projects include `LLM_CONTEXT.md` and `.llm/` directories
- **Helpful errors** - Clear validation messages with actionable fixes

This makes DAZZLE ideal for **LLM-assisted development** where AI helps you design, build, and iterate on applications.

### Quick Start for Testing

Generate a demo project to test with:

```bash
dazzle demo                    # Creates micro-demo/ with simple_task example
cd micro-demo
# Now test the prompt above with your AI assistant
```

The demo includes:
- Valid DAZZLE DSL
- Configuration files
- LLM context documentation
- Example entities and surfaces

Perfect for testing LLM comprehension!

## Core Concepts

### Entities

Define your domain models:

```dsl
entity User "User":
  id: uuid pk
  email: email unique required
  name: str(200) required
  role: enum[admin,user]=user
  created_at: datetime auto_add
  
  index email
```

### Surfaces

Define UI entry points:

```dsl
surface user_list "Users":
  uses entity User
  mode: list                    # list, view, create, edit
  
  section main "User List":
    field email "Email"
    field name "Name"
    field role "Role"
```

### Experiences

Define multi-step workflows:

```dsl
experience user_onboarding "User Onboarding":
  start at step signup
  
  step signup:
    kind: surface
    surface user_create
    on success -> step welcome
  
  step welcome:
    kind: surface
    surface welcome_screen
```

### Services & Integrations

Integrate external APIs:

```dsl
service github "GitHub API":
  spec: url "https://api.github.com/openapi.yaml"
  auth_profile: oauth2_pkce scopes="read:user"

integration github_sync "GitHub Sync":
  uses service github
  
  action fetch_repos:
    call github.list_repos
```

## CLI Commands

```bash
# Validate DSL syntax and semantics
dazzle validate

# Run linter with extended checks
dazzle lint --strict

# Generate artifacts
dazzle build --backend openapi --out ./build

# List available backends
dazzle backends
```

## Available Backends

- **openapi**: Generate OpenAPI 3.0 specifications (YAML/JSON)
- More backends coming soon: Django, FastAPI, Prisma, React...

## IDE Support

### VSCode Extension

DAZZLE includes a full-featured VSCode extension with:

- **Syntax Highlighting**: TextMate grammar for `.dsl` files
- **Language Server Protocol (LSP)**: Powered by Python-based LSP server
- **Go-to-Definition**: Navigate to entity and surface declarations
- **Hover Documentation**: View detailed entity/surface information
- **Autocomplete**: Smart suggestions for field types and modifiers
- **Real-time Validation**: Live error detection and diagnostics
- **Document Symbols**: Hierarchical outline view

**Installation**:
```bash
# Development installation (symlink)
ln -s /path/to/dazzle/extensions/vscode ~/.vscode/extensions/dazzle-dsl-0.3.0

# Or package and install
cd extensions/vscode
npm install
npm run compile
```

See [extensions/vscode/README.md](extensions/vscode/README.md) for details.

## Project Structure

```
my_project/
  dazzle.toml          # Project manifest
  dsl/
    core.dsl           # Core domain models
    ui.dsl             # UI surfaces
    integrations.dsl   # External integrations
  build/               # Generated artifacts
    openapi.yaml
```

## Multi-Module Projects

Organize large projects across multiple modules:

```dsl
# auth.dsl
module my_app.auth

entity AuthToken:
  id: uuid pk
  token: str(500) unique
```

```dsl
# core.dsl
module my_app.core

use my_app.auth

entity User:
  id: uuid pk
  current_token: ref AuthToken optional
```

DAZZLE automatically resolves dependencies and validates cross-module references.

## Examples

See the [`examples/`](examples/) directory for:
- **Simple Task Manager**: Basic CRUD application
- **Support Ticket System**: Multi-module project with integrations

## Documentation

### User Documentation
- [DSL Reference](docs/DSL_REFERENCE.md) - Complete language reference
- [CLI Commands](docs/CLI_REFERENCE.md) - Command-line interface guide
- [VSCode Extension](extensions/vscode/README.md) - IDE setup and features

### Developer Documentation
- [Developer Docs Index](devdocs/README.md) - Development documentation hub
- [Backend Development](docs/BACKEND_GUIDE.md) - Creating custom backends
- [Architecture](docs/ARCHITECTURE.md) - System design
- [Build Validation](tests/build_validation/README.md) - Testing infrastructure
- [Contributing](CONTRIBUTING.md) - How to contribute

## Development

```bash
# Clone repository
git clone https://github.com/yourusername/dazzle.git
cd dazzle

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check src/ tests/

# Type check
mypy src/dazzle
```

## Testing

DAZZLE has comprehensive test coverage:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/dazzle --cov-report=html

# Run specific test suite
pytest tests/unit/
pytest tests/integration/
```

## Philosophy

DAZZLE is designed for **machine-first** specification:

- **Token Efficiency**: Minimal syntax, maximum meaning
- **Semantic Clarity**: Clear separation of concerns (domain, UI, integration)
- **LLM-Friendly**: Optimized for LLM understanding and generation
- **Progressive Enhancement**: Start simple, add complexity as needed

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Roadmap

### Completed ✓
- [x] DSL Parser with comprehensive error handling
- [x] Multi-module support with dependency resolution
- [x] Semantic validation and linting
- [x] OpenAPI 3.0 backend
- [x] Stack system for coordinated backend generation
- [x] Language Server Protocol (LSP) implementation
- [x] VSCode extension with full IDE features
- [x] Build validation and testing infrastructure

### In Progress 🚧
- [ ] Django backend with model generation
- [ ] Infrastructure backend (Docker, Terraform)
- [ ] Service integration profiles

### Planned 📋
- [ ] FastAPI backend
- [ ] Prisma backend
- [ ] React UI generation
- [ ] GraphQL backend
- [ ] Additional IDE support (JetBrains, Emacs, Vim)
- [ ] Web-based playground/IDE

## Citation

If you use DAZZLE in research, please cite:

```bibtex
@software{dazzle2025,
  author = {Your Name},
  title = {DAZZLE: Domain-Aware, Token-Efficient DSL for LLM-Enabled Apps},
  year = {2025},
  url = {https://github.com/manwithacat/dazzle}
}
```

---

Built with ❤️ for LLM-driven development
