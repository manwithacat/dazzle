# DAZZLE Tests

Comprehensive test suite for the DAZZLE DSL toolkit.

## Test Structure

```
tests/
├── build_validation/    # Example build validation
│   ├── validate_examples.py
│   └── README.md
├── unit/               # Unit tests (if present)
├── integration/        # Integration tests (if present)
└── fixtures/           # Test data and fixtures
```

## Running Tests

### Quick Start

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/dazzle --cov-report=html

# Run specific test file
pytest tests/test_parser.py

# Run tests matching pattern
pytest -k "test_entity"

# Verbose output
pytest -v
```

### Build Validation

Test all example projects:

```bash
# Validate all examples
python tests/build_validation/validate_examples.py

# Validate specific example
python tests/build_validation/validate_examples.py --example support_tickets

# Generate JSON report for CI
python tests/build_validation/validate_examples.py --report-format json
```

See [build_validation/README.md](build_validation/README.md) for details.

## Test Categories

### Parser Tests

Test DSL syntax parsing:
- Entity definitions
- Surface specifications
- Module imports
- Field types and modifiers
- Syntax error handling

### Semantic Tests

Test validation rules:
- Type checking
- Reference resolution
- Constraint validation
- Circular dependency detection

### Backend Tests

Test code generation:
- OpenAPI schema generation
- Backend plugin system
- Stack coordination

### LSP Tests

Test Language Server Protocol:
- Hover provider
- Completion provider
- Definition provider
- Document symbols

### Integration Tests

Test full workflows:
- Parse → Validate → Build pipeline
- Multi-module projects
- Error recovery
- CLI commands

## Writing Tests

### Test Structure

```python
import pytest
from dazzle.core.parser import parse_module

def test_entity_with_required_fields():
    """Test that required field modifier is parsed correctly."""
    dsl = '''
    module test

    entity User:
      email: str required
    '''

    module = parse_module(dsl, "test.dsl")

    assert len(module.entities) == 1
    entity = module.entities[0]
    assert entity.name == "User"
    assert "required" in entity.fields[0].modifiers
```

### Best Practices

- **One assertion per test**: Keep tests focused
- **Clear names**: Test name should describe what's being tested
- **Arrange-Act-Assert**: Structure tests clearly
- **Use fixtures**: Share common setup with pytest fixtures
- **Test edge cases**: Empty inputs, invalid data, boundary conditions
- **Mock external dependencies**: Use unittest.mock for external services

### Fixtures

Create reusable test data:

```python
@pytest.fixture
def simple_entity_dsl():
    return '''
    module test

    entity Task:
      id: uuid pk
      title: str(200)
    '''

def test_parse_entity(simple_entity_dsl):
    module = parse_module(simple_entity_dsl, "test.dsl")
    assert module.entities[0].name == "Task"
```

## Coverage

We aim for >90% test coverage:

```bash
# Generate coverage report
pytest --cov=src/dazzle --cov-report=html

# View in browser
open htmlcov/index.html
```

Current coverage areas:
- ✅ Parser: >95%
- ✅ Semantic validation: >90%
- ✅ OpenAPI backend: >85%
- 🚧 LSP server: ~70% (expanding)
- 🚧 CLI: ~60% (expanding)

## Continuous Integration

Tests run automatically on:
- Every push to main/develop
- Pull requests
- Nightly builds

See `.github/workflows/` for CI configuration.

## Performance Testing

Benchmark critical paths:

```bash
# Profile test execution
pytest --profile

# Profile specific operation
python -m cProfile -o profile.stats scripts/benchmark_parser.py
```

## Test Data

### Fixtures Directory

Contains:
- Sample DSL files
- Expected output files
- Test configuration
- Mock service responses

### Examples Directory

Real DAZZLE projects used for validation:
- `examples/simple_task/` - Basic CRUD app
- `examples/support_tickets/` - Multi-module project

## Debugging Tests

```bash
# Drop into debugger on failure
pytest --pdb

# Show local variables on failure
pytest -l

# Stop after first failure
pytest -x

# Run last failed tests only
pytest --lf
```

## Adding New Tests

1. **Create test file**: `tests/test_<feature>.py`
2. **Write test functions**: Start with `test_`
3. **Add fixtures**: If needed
4. **Run tests**: `pytest tests/test_<feature>.py`
5. **Check coverage**: Ensure new code is tested
6. **Update validation**: Add to example validation if applicable

## Test Dependencies

Tests use:
- **pytest**: Test runner and fixtures
- **pytest-cov**: Coverage reporting
- **pytest-mock**: Mocking utilities
- **hypothesis**: Property-based testing (future)

Install with:
```bash
pip install -e ".[dev]"
```

## Known Issues

- LSP tests require running server instance (working on better mocking)
- Some integration tests are slow (consider marking with `@pytest.mark.slow`)
- Windows path handling in some tests (contributions welcome!)

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines on:
- Writing tests
- Running test suite
- Coverage requirements
- CI integration

---

**Questions?** Open an issue or check [GitHub Discussions](https://github.com/yourusername/dazzle/discussions)
