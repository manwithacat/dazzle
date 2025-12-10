# DAZZLE Source Code

Core implementation of the DAZZLE DSL toolkit.

## Directory Structure

```
src/dazzle/
├── core/               # Core language implementation
│   ├── grammar.lark    # DSL grammar definition (Lark)
│   ├── parser.py       # Parser implementation
│   ├── ast.py          # Abstract Syntax Tree models
│   ├── ir.py           # Intermediate Representation (IR)
│   ├── linker.py       # Module linking and resolution
│   ├── lint.py         # Semantic validation and linting
│   ├── manifest.py     # Project manifest (dazzle.toml) handling
│   ├── fileset.py      # DSL file discovery
│   └── errors.py       # Error types and handling
├── backends/           # Code generation backends
│   ├── base.py         # Backend interface and registry
│   ├── openapi/        # OpenAPI 3.0 backend
│   └── stacks.py       # Stack coordination
├── lsp/                # Language Server Protocol
│   ├── server.py       # LSP server implementation (pygls)
│   └── features.py     # LSP features (hover, completion, etc.)
├── cli/                # Command-line interface
│   ├── main.py         # CLI entry point (Click-based)
│   ├── commands/       # CLI command implementations
│   └── output.py       # CLI output formatting
├── templates/          # Project templates
│   └── blank/          # Blank project template
└── __init__.py         # Package initialization
```

## Core Components

### Parser (`core/parser.py`)

Converts DSL text into Abstract Syntax Tree (AST):

```python
from dazzle.core.parser import parse_module

# Parse a DSL file
module_ast = parse_module(dsl_text, filename="app.dsl")

# AST contains raw parsed structure
print(module_ast.entities)  # List of entity AST nodes
```

**Key Functions**:
- `parse_module(text, filename)` - Parse single DSL file
- `parse_modules(files)` - Parse multiple DSL files

### Intermediate Representation (`core/ir.py`)

Type-safe Pydantic models representing validated DAZZLE spec:

```python
from dazzle.core.ir import AppSpec, Entity, Field

# IR models are fully validated and type-safe
appspec: AppSpec = ...
for entity in appspec.domain.entities:
    print(f"Entity: {entity.name}")
    for field in entity.fields:
        print(f"  {field.name}: {field.type.kind}")
```

**Key Models**:
- `AppSpec` - Complete application specification
- `DomainSpec` - Domain model (entities)
- `Entity` - Entity definition
- `Field` - Field specification
- `SurfaceSpec` - UI surface definition

### Linker (`core/linker.py`)

Resolves references and builds complete AppSpec:

```python
from dazzle.core.linker import build_appspec

# Links modules and resolves references
appspec = build_appspec(modules, project_root="my_app")

# Now all entity references are resolved
ticket_entity = appspec.domain.get_entity("Ticket")
assigned_to_field = ticket_entity.get_field("assigned_to")
# assigned_to_field.type.ref_entity is now resolved
```

**Responsibilities**:
- Resolve cross-module references
- Build complete domain model
- Validate entity relationships
- Detect circular dependencies

### Validator (`core/lint.py`)

Semantic validation and linting:

```python
from dazzle.core.lint import lint_appspec

# Run semantic checks
issues = lint_appspec(appspec)

for issue in issues:
    print(f"{issue.severity}: {issue.message}")
    print(f"  at {issue.location}")
```

**Checks**:
- Naming conventions
- Unused entities/fields
- Missing indexes on foreign keys
- Invalid enum values
- Orphaned surfaces

## Backend System

### Backend Interface (`backends/base.py`)

All backends implement `Backend` protocol:

```python
from dazzle.backends.base import Backend, BackendContext

class MyBackend(Backend):
    """Custom backend implementation."""

    @property
    def name(self) -> str:
        return "mybackend"

    def generate(self, ctx: BackendContext) -> None:
        """Generate artifacts from AppSpec."""
        appspec = ctx.appspec
        output_dir = ctx.output_dir

        # Generate files
        for entity in appspec.domain.entities:
            self._generate_entity(entity, output_dir)
```

**Backend Registry**:
```python
from dazzle.backends.base import register_backend, get_backend

# Register backend
register_backend(MyBackend())

# Get backend instance
backend = get_backend("mybackend")
```

### OpenAPI Backend (`backends/openapi/`)

Reference implementation generating OpenAPI 3.0 specs:

```
backends/openapi/
├── __init__.py         # Backend registration
├── generator.py        # Main generator
├── schema.py           # Schema generation
└── paths.py            # Path/endpoint generation
```

### Ejection System (`eject/`)

For production deployment, the ejection toolchain generates standalone code:

```python
from dazzle.eject import EjectionRunner, EjectionConfig

# Run ejection with configured adapters
config = EjectionConfig.from_toml("dazzle.toml")
runner = EjectionRunner(config, appspec)
result = runner.run()
```

## LSP Server

### Server (`lsp/server.py`)

Language Server Protocol implementation using pygls:

```python
from pygls.server import LanguageServer
from dazzle.lsp.server import server

# Server provides:
# - Hover documentation
# - Go-to-definition
# - Autocomplete
# - Document symbols
# - Real-time validation
```

**LSP Features**:
- `textDocument/hover` - Show entity/surface details
- `textDocument/definition` - Jump to declaration
- `textDocument/completion` - Smart suggestions
- `textDocument/documentSymbol` - Outline view

Started by VSCode extension or other LSP clients.

## CLI

### Main Entry Point (`cli/main.py`)

Click-based command-line interface:

```python
import click
from dazzle.cli import cli

@cli.command()
@click.option("--format", type=click.Choice(["yaml", "json"]))
def build(format):
    """Build project."""
    # Implementation
```

**Commands**:
- `dazzle init` - Create new project
- `dazzle validate` - Validate DSL
- `dazzle build` - Generate artifacts
- `dazzle lint` - Run linter
- `dazzle backends` - List backends

## Development Workflow

### Adding a New Feature

1. **Grammar**: Update `core/grammar.lark` if new syntax
2. **Parser**: Modify `core/parser.py` to handle new AST nodes
3. **IR**: Add models to `core/ir.py` if needed
4. **Validation**: Add checks to `core/lint.py`
5. **Backend**: Update backends to support new feature
6. **LSP**: Add LSP support for new syntax
7. **Tests**: Add comprehensive tests
8. **Docs**: Update documentation

### Adding a New Backend

1. **Create Backend**:
   ```python
   # src/dazzle/backends/mybackend/__init__.py
   from dazzle.backends.base import Backend, register_backend

   class MyBackend(Backend):
       @property
       def name(self) -> str:
           return "mybackend"

       def generate(self, ctx: BackendContext) -> None:
           # Generate code
           pass

   # Register on import
   register_backend(MyBackend())
   ```

2. **Add Tests**: `tests/backends/test_mybackend.py`

3. **Document**: Update `docs/BACKEND_GUIDE.md`

### Code Style

- **Type Hints**: Use everywhere
- **Pydantic**: For data models (IR)
- **Dataclasses**: For simple data structures
- **Error Handling**: Raise specific error types from `core/errors.py`

## Key Concepts

### AST vs IR

- **AST** (Abstract Syntax Tree): Raw parsed structure, minimal validation
- **IR** (Intermediate Representation): Validated, type-safe, fully linked

AST → Linker → IR → Backends → Generated Code

### Module Resolution

1. **Parse**: Each `.dsl` file becomes a Module AST
2. **Discover**: Find all modules via `dazzle.toml`
3. **Link**: Resolve cross-module references
4. **Validate**: Check semantic rules
5. **Build**: Create AppSpec IR

### Error Handling

```python
from dazzle.core.errors import ParseError, ValidationError

try:
    appspec = build_appspec(modules, project_root)
except ParseError as e:
    # Syntax error
    print(f"Parse error at {e.location}: {e.message}")
except ValidationError as e:
    # Semantic error
    print(f"Validation error: {e.message}")
```

## Performance Considerations

- **Caching**: Parser caches grammar compilation
- **Lazy Loading**: Backends loaded on-demand
- **Incremental**: LSP supports incremental updates
- **Memory**: Large projects may need streaming

## Dependencies

Core dependencies:
- **lark**: Parser generator
- **pydantic**: Data validation and models
- **click**: CLI framework
- **pygls**: Language Server Protocol
- **toml**: Configuration parsing

See `pyproject.toml` for complete list.

## Testing

See [../../tests/README.md](../../tests/README.md) for testing guidelines.

## Documentation

- [Developer Docs](../../devdocs/README.md) - Implementation details
- [User Docs](../../docs/README.md) - End-user documentation
- [API Reference](../../docs/API.md) - Python API documentation

## Contributing

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for contribution guidelines.

---

**Architecture Questions?** Check [devdocs/ARCHITECTURE.md](../../devdocs/ARCHITECTURE.md) or open an issue.
