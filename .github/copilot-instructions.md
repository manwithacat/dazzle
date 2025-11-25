# Copilot Instructions for DAZZLE

These instructions guide GitHub Copilot when working on issues and pull requests in this repository.

## Project Overview

DAZZLE is a DSL-first application framework that transforms declarative specifications into full-stack applications. The codebase includes:

- **Core DSL Parser**: Lark-based grammar in `src/dazzle/core/`
- **Intermediate Representation**: Pydantic models in `src/dazzle/core/ir.py`
- **Backend Generators**: Code generators in `src/dazzle/stacks/`
- **Language Server**: LSP implementation in `src/dazzle/lsp/`
- **CLI**: Command-line interface in `src/dazzle/cli/`
- **VS Code Extension**: TypeScript extension in `extensions/vscode/`

## Code Style Requirements

### Python
- Use type hints for all function parameters and return values
- Follow PEP 8 style (enforced by `ruff`)
- Use Google-style docstrings for public APIs
- Prefer `pathlib.Path` over `os.path`
- Use dataclasses or Pydantic models for structured data

### TypeScript (VS Code Extension)
- Use strict TypeScript settings
- Prefer async/await over callbacks
- Document public APIs with JSDoc

## Testing Requirements

Before submitting changes:

1. **Run linting**: `ruff check src/ tests/`
2. **Run formatting**: `ruff format src/ tests/`
3. **Run type checking**: `mypy src/dazzle`
4. **Run tests**: `pytest tests/ -x`
5. **Validate examples**: `python tests/build_validation/validate_examples.py`

Or use the Makefile: `make ci`

## Architecture Guidelines

### Adding New Field Types
1. Update grammar in `src/dazzle/core/grammar.lark`
2. Add IR model in `src/dazzle/core/ir.py`
3. Update parser in `src/dazzle/core/dsl_parser.py`
4. Add validation in `src/dazzle/core/lint.py`
5. Update backends in `src/dazzle/stacks/*/`
6. Add tests in `tests/`

### Adding New Backends
1. Create directory in `src/dazzle/stacks/<backend_name>/`
2. Implement `Generator` class extending `BaseGenerator`
3. Register in `src/dazzle/stacks/__init__.py`
4. Add integration tests
5. Create example in `examples/`

## Common Patterns

### Error Handling
```python
from dazzle.core.errors import DazzleError, ValidationError

def validate_something(value: str) -> None:
    if not value:
        raise ValidationError("Value cannot be empty", location=loc)
```

### Working with IR
```python
from dazzle.core.ir import EntitySpec, FieldSpec

# Access entity fields
for field in entity.fields:
    if field.is_required:
        # handle required field
```

### File Generation
```python
from pathlib import Path

def generate_file(output_dir: Path, content: str) -> Path:
    output_path = output_dir / "generated.py"
    output_path.write_text(content)
    return output_path
```

## Issue Investigation Checklist

When assigned an issue, follow this investigation process:

### For Bugs
1. [ ] Reproduce the issue with a minimal test case
2. [ ] Identify the root cause in the codebase
3. [ ] Check for related issues or edge cases
4. [ ] Propose a fix with test coverage
5. [ ] Consider backwards compatibility

### For Features
1. [ ] Understand the use case and requirements
2. [ ] Check existing patterns in the codebase
3. [ ] Design the solution following project conventions
4. [ ] Implement with comprehensive tests
5. [ ] Update documentation if needed

## Pull Request Guidelines

- Keep PRs focused on a single issue
- Include tests for all changes
- Update relevant documentation
- Reference the issue number in commits
- Ensure all CI checks pass

## Virtual Environment

When running commands, use:
- Python virtual environment: `.venv/`
- Node modules: `extensions/vscode/node_modules/`

## Security Considerations

- Never commit secrets or API keys
- Validate all user input in CLI and LSP
- Use parameterized queries for any database operations
- Follow OWASP guidelines for generated code
