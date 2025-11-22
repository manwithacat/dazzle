# DAZZLE Documentation

Welcome to the DAZZLE documentation! This directory contains user-facing documentation for using DAZZLE.

## 📚 Documentation Index

### Getting Started

- **[Main README](../README.md)** - Project overview and quick start
- **[Installation Guide](#installation)** - Setting up DAZZLE
- **[Your First Project](#first-project)** - Step-by-step tutorial

### Language Reference

- **[DSL Reference](DSL_REFERENCE.md)** - Complete DAZZLE DSL syntax guide
- **[DSL Grammar](DAZZLE_DSL_GRAMMAR_0_1.ebnf)** - Formal grammar specification
- **[IR Specification](DAZZLE_IR_0_1.md)** - Intermediate Representation details

### Command-Line Interface

- **[CLI Reference](CLI_REFERENCE.md)** - All DAZZLE commands and options
  - `dazzle init` - Create new projects
  - `dazzle validate` - Validate DSL files
  - `dazzle build` - Generate artifacts
  - `dazzle lint` - Run semantic checks
  - `dazzle backends` - List available backends

### IDE & Editor Support

- **[VSCode Extension](../extensions/vscode/README.md)** - Full IDE features
  - Installation and setup
  - Language Server Protocol (LSP) features
  - Hover documentation
  - Go-to-definition
  - Autocomplete
  - Real-time validation

### Backends

- **[Backend Guide](BACKEND_GUIDE.md)** - Using and creating backends
- **[Stack System](STACKS.md)** - Coordinated multi-backend builds
- **[OpenAPI Backend](openapi/README.md)** - OpenAPI 3.0 generation

### Examples

- **[Examples Directory](../examples/)** - Complete example projects
  - [Simple Task Manager](../examples/simple_task/) - Basic CRUD
  - [Support Ticket System](../examples/support_tickets/) - Multi-module project

## Installation

### From PyPI (when published)

```bash
pip install dazzle
```

### From Source

```bash
git clone https://github.com/yourusername/dazzle.git
cd dazzle
pip install -e .
```

### Verify Installation

```bash
dazzle --help
dazzle backends
```

## First Project

### 1. Create Project Structure

```bash
mkdir my_app
cd my_app
```

### 2. Create `dazzle.toml`

```toml
[project]
name = "my_app"
version = "0.1.0"
root = "my_app.core"

[modules]
paths = ["./dsl"]
```

### 3. Create DSL File

Create `dsl/app.dsl`:

```dsl
module my_app.core

app my_app "My Application"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  description: text
  completed: bool=false
  created_at: datetime auto_add

surface task_list "Task List":
  uses entity Task
  mode: list
  
  section main "Tasks":
    field title "Title"
    field completed "Done"
    field created_at "Created"
```

### 4. Validate and Build

```bash
# Validate DSL
dazzle validate

# Build OpenAPI spec
dazzle build --backend openapi --out ./build

# View generated spec
cat build/openapi.yaml
```

### 5. Next Steps

- Add more entities and relationships
- Create edit/create surfaces
- Add integrations
- Generate different backends

## Core Concepts

### Entities

Define your domain model:

```dsl
entity User "User":
  id: uuid pk
  email: str(255) unique required
  name: str(200) required
  role: enum[admin,user]=user
  created_at: datetime auto_add
  
  index email
```

**Key Features**:
- Field types: `uuid`, `str`, `int`, `bool`, `datetime`, `text`, `enum`, `ref`
- Modifiers: `pk`, `required`, `unique`, `auto_add`, `auto_update`
- Indexes for performance
- Default values

### Surfaces

Define UI entry points:

```dsl
surface user_list "Users":
  uses entity User
  mode: list
  
  section main "User List":
    field email "Email"
    field name "Name"
    field role "Role"
```

**Surface Modes**:
- `list` - Display multiple records
- `view` - View single record
- `create` - Create new record
- `edit` - Modify existing record

### Relationships

Connect entities:

```dsl
entity Ticket:
  id: uuid pk
  title: str(200)
  assigned_to: ref User optional  # Foreign key to User
  created_by: ref User required
```

### Multi-Module Projects

Organize large projects:

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

## CLI Usage

### Validate Project

```bash
# Basic validation
dazzle validate

# Validate specific manifest
dazzle validate --manifest dazzle.toml

# Machine-readable format (for IDE/CI)
dazzle validate --format vscode
```

### Build Artifacts

```bash
# Build with single backend
dazzle build --backend openapi --out ./build

# Build with multiple backends
dazzle build --backends django,openapi --out ./build

# Build with stack preset
dazzle build --stack django_api --out ./build

# Incremental build
dazzle build --incremental

# Preview changes without building
dazzle build --diff
```

### Lint Project

```bash
# Run all lint checks
dazzle lint

# Strict mode (warnings as errors)
dazzle lint --strict

# Fix auto-fixable issues
dazzle lint --fix
```

### List Backends

```bash
# Show available backends
dazzle backends

# Show backend details
dazzle backends --verbose
```

## IDE Features

### VSCode

Install the DAZZLE extension for full IDE support:

- **Syntax highlighting** for `.dsl` files
- **Real-time validation** with diagnostics
- **Hover documentation** on entities and fields
- **Go-to-definition** for references
- **Autocomplete** for field types and modifiers
- **Document symbols** for navigation

See [VSCode Extension Guide](../extensions/vscode/README.md).

### Other Editors

LSP support planned for:
- JetBrains IDEs
- Emacs
- Vim/Neovim

## Backend System

### Available Backends

- **openapi** - OpenAPI 3.0 specifications
- **django** (planned) - Django models and admin
- **fastapi** (planned) - FastAPI endpoints
- **prisma** (planned) - Prisma schema
- **react** (planned) - React UI components

### Using Backends

```bash
# Single backend
dazzle build --backend openapi

# Multiple backends
dazzle build --backends django,openapi

# Stack preset
dazzle build --stack django_api
```

### Creating Custom Backends

See [Backend Development Guide](BACKEND_GUIDE.md).

## Best Practices

### Project Structure

```
my_project/
  dazzle.toml           # Project manifest
  dsl/                  # DSL files
    core.dsl            # Core entities
    ui.dsl              # Surfaces
    integrations.dsl    # Services
  build/                # Generated artifacts
  README.md             # Project documentation
```

### Naming Conventions

- **Entities**: PascalCase (`User`, `TaskItem`)
- **Fields**: snake_case (`email`, `created_at`)
- **Surfaces**: snake_case (`user_list`, `task_create`)
- **Modules**: snake_case with dots (`my_app.core`, `my_app.auth`)

### Version Control

Add to `.gitignore`:
```
build/
*.pyc
__pycache__/
.pytest_cache/
htmlcov/
```

## Troubleshooting

### Common Issues

**"Module not found" errors**:
- Check `dazzle.toml` module paths
- Ensure DSL files are in configured directories
- Verify module declarations match file paths

**"Reference not found" errors**:
- Add `use` statements for cross-module references
- Check entity/surface names for typos
- Verify reference types are entities

**Validation warnings**:
- Review lint output with `dazzle lint`
- Use `--strict` to treat warnings as errors
- Fix auto-fixable issues with `--fix`

### Getting Help

- **Documentation**: Check this docs directory
- **Examples**: See `examples/` for working projects
- **Issues**: [GitHub Issues](https://github.com/yourusername/dazzle/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/dazzle/discussions)

## Contributing to Docs

Found an issue or want to improve documentation?

1. Edit the relevant `.md` file
2. Test examples for correctness
3. Submit a pull request

See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

## Additional Resources

- **[Architecture Docs](../devdocs/ARCHITECTURE.md)** - System design
- **[Developer Docs](../devdocs/README.md)** - Implementation details
- **[Test Documentation](../tests/README.md)** - Testing guide
- **[Contributing Guide](../CONTRIBUTING.md)** - How to contribute

---

**Questions?** Open an issue or start a discussion on GitHub!
