# Development Setup

Set up a local development environment for contributing to Dazzle.

## Prerequisites

- Python 3.12+
- Node.js 18+ (for JavaScript tests)
- Git

## Clone and Install

```bash
# Clone the repository
git clone https://github.com/manwithacat/dazzle.git
cd dazzle

# Create the venv + editable install from uv.lock (uv is the canonical toolchain)
uv sync --extra dev
source .venv/bin/activate  # Windows: .venv\Scripts\activate
# (pip alternative: python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]")

# Install Node dependencies
npm install

# Install pre-commit hooks
pre-commit install
```

## Verify Installation

```bash
# Check Dazzle works
dazzle --version

# Run tests
pytest tests/unit -m "not slow" -x

# Run JavaScript tests
npm test

# Type check
mypy src/dazzle
npx tsc --noEmit -p src/dazzle/page/runtime/static/js/
```

## Project Structure

```
dazzle/
├── src/
│   ├── dazzle/                    # Core package
│   │   ├── cli/                   # CLI commands
│   │   ├── core/                  # Parser, IR, validator
│   │   │   ├── ir/                # Internal representation types
│   │   │   ├── dsl_parser_impl/   # Parser implementation modules
│   │   │   └── lexer.py           # Tokenizer (KEYWORDS auto-generated)
│   │   ├── mcp/                   # MCP server
│   │   │   └── server/
│   │   │       └── handlers/      # Tool handlers by domain
│   │   │           ├── project.py   # Project management
│   │   │           ├── dsl.py       # DSL validation/inspection
│   │   │           ├── knowledge.py # Concept lookup
│   │   │           ├── status.py    # MCP + runtime status
│   │   │           ├── api_packs.py # External API packs
│   │   │           └── stories.py   # Story generation
│   │   ├── back/                  # FastAPI backend runtime
│   │   │   ├── runtime/           # Server and API generation
│   │   │   └── converters/        # AppSpec → BackendSpec
│   │   ├── ui/                    # Server-rendered UI runtime
│   │   │   ├── runtime/
│   │   │   │   ├── combined_server.py  # HTTP server
│   │   │   │   ├── site_renderer.py    # Site/auth page HTML
│   │   │   │   └── static/             # JS/CSS assets
│   │   │   └── converters/        # AppSpec → typed Fragment trees
│   │   └── eject/                 # Code generation adapters
├── tests/
│   ├── unit/                      # Unit tests
│   ├── integration/               # Integration tests
│   ├── e2e/                       # End-to-end tests
│   └── parser_corpus/             # DSL parser test cases
├── examples/                      # Example projects
└── docs/                          # Documentation
```

## Development Workflow

### Running Examples

```bash
cd examples/simple_task
dazzle serve
```

### Making Changes

1. Create a branch:
   ```bash
   git checkout -b feature/my-feature
   ```

2. Make changes and run tests:
   ```bash
   pytest tests/unit -x
   ```

3. Format and lint:
   ```bash
   ruff check src/ tests/ --fix
   ruff format src/ tests/
   ```

4. Commit (pre-commit hooks run automatically):
   ```bash
   git add .
   git commit -m "feat: add my feature"
   ```

### Pre-commit Hooks

These run automatically on commit:

| Hook | Purpose |
|------|---------|
| `ruff` | Python linting + formatting |
| `mypy` | Python type checking |
| `bandit` | Security checks |
| `eslint` | JavaScript linting |
| `tsc` | JavaScript type checking |
| `vitest` | JavaScript tests |
| `dsl-validate` | DSL validation |
| `pytest-fast` | Fast unit tests |

To run manually:

```bash
pre-commit run --all-files
```

## Code Style

### Python

- Type hints on all public functions
- Pydantic models for data structures
- Single-purpose functions
- No magic or metaprogramming

### JavaScript

- Vanilla JS with JSDoc + `@ts-check`
- Shared types in `types.js`
- ES modules (bundled to IIFE for runtime)

See [CLAUDE.md](https://github.com/manwithacat/dazzle/blob/main/.claude/CLAUDE.md) for detailed style guide.

## Useful Commands

```bash
# Fast tests (no subprocess)
pytest tests/unit -m "not slow" -x --tb=short

# Specific test file
pytest tests/unit/test_parser.py -v

# Tests matching pattern
pytest -k "test_entity" -v

# Coverage report
pytest --cov=src/dazzle --cov-report=html
open htmlcov/index.html

# Type check
mypy src/dazzle/core src/dazzle/cli
```

## Troubleshooting

### Import errors

```bash
pip install -e ".[dev]" --force-reinstall
```

### Pre-commit failures

```bash
pre-commit run --all-files -v
```

### JavaScript type errors

```bash
npx tsc --noEmit -p src/dazzle/page/runtime/static/js/
```

## See Also

- [Testing Guide](testing.md)
- [Adding a Feature](adding-a-feature.md)
