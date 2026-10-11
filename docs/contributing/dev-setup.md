# Development Setup

Set up a local development environment for contributing to Dazzle.

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — single source of truth for Python and dependencies
  (same toolchain Heroku uses via the uv buildpack)
- Node.js 18+ (for JavaScript tests)
- Git
- Postgres + Redis for full app serve (optional for unit tests)

**Do not use pyenv, virtualenvwrapper, or bare `pip install -e` for this repo.**
The committed `.python-version` pins the **primary** interpreter (`3.14`) for
uv and Heroku. That file is *not* a pyenv virtualenv name; if pyenv is on your
`PATH`, prefer `make` / `uv run` (they force uv-managed Python) or
`export PYENV_VERSION=system` in this directory.

Support floor remains **Python >= 3.12** (`requires-python`); CI matrices
3.12 / 3.13 / 3.14. Local default and production deploy target is **3.14**.

## Clone and Install

```bash
# Install uv once (if needed): https://docs.astral.sh/uv/getting-started/installation/
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/manwithacat/dazzle.git
cd dazzle

# Provision the pinned interpreter + .venv from uv.lock
make dev-install
# equivalent:
#   uv python install          # reads .python-version → 3.14
#   uv sync --extra dev --extra llm --extra mcp --extra mobile \
#           --extra postgres --extra perf --extra saml --extra lsp
#   uvx pre-commit install && uvx pre-commit install --hook-type pre-push

source .venv/bin/activate   # optional; or prefix with `uv run` / use make targets

# Install Node dependencies
npm install
```

`[tool.uv] python-preference = "only-managed"` in `pyproject.toml` means uv
**never** falls back to a system or pyenv interpreter. After changing
dependencies in `pyproject.toml`, run `uv lock` and commit `uv.lock` in the
same change — CI syncs with `--frozen`.

## Verify Installation

```bash
# Check Dazzle works
uv run dazzle --version

# Fast gates (used by /improve and agent loops)
make test-ux-preflight

# Unit tests
uv run pytest tests/unit -m "not slow" -x

# JavaScript tests
npm test

# Type check
uv run mypy src/dazzle
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
│   │   ├── http/                  # FastAPI backend runtime
│   │   ├── page/                  # Server-rendered UI runtime
│   │   ├── render/                # Pure AppSpec → Fragment → HTML
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
uv run dazzle serve
```

### Making Changes

1. Create a branch:
   ```bash
   git checkout -b feature/my-feature
   ```

2. Make changes and run tests:
   ```bash
   uv run pytest tests/unit -x
   # or: make test-fast
   ```

3. Format and lint:
   ```bash
   make lint format
   # or: uv run ruff check src/ tests/ --fix && uv run ruff format src/ tests/
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
make pre-commit
# or: uvx pre-commit run --all-files
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

See [AGENTS.md](https://github.com/manwithacat/dazzle/blob/main/AGENTS.md) for detailed style guide.

## Useful Commands

```bash
# Fast tests (no subprocess)
uv run pytest tests/unit -m "not slow" -x --tb=short

# Specific test file
uv run pytest tests/unit/test_parser.py -v

# Coverage report
make coverage

# Type check
uv run mypy src/dazzle/core src/dazzle/cli

# Local CI concordance (see local-ci-concordance.md)
make ci-fast    # tier 0 — what /ship runs
make ci-core    # tier 1 — closer to GitHub CI
```

## Troubleshooting

### `pyenv: version '3.14' is not installed`

The repo `.python-version` is for **uv / Heroku**, not pyenv. Either:

```bash
# Preferred: never call bare python/pytest; use make or uv run
make test-ux-preflight
uv run pytest tests/unit -x

# Or silence pyenv for this shell
export PYENV_VERSION=system
```

Do **not** install 3.14 into pyenv “to fix” the project — use
`uv python install` (already done by `make install` / `make dev-install`).

### Import errors / missing extras

```bash
make dev-install
# or re-sync a thinner set:
uv sync --extra dev
```

A uv `.venv` has **no** `pip`. One-off tools: `uv pip install <tool>` or add an
extra and `uv lock`.

### Pre-commit failures

```bash
uvx pre-commit run --all-files -v
```

### JavaScript type errors

```bash
npx tsc --noEmit -p src/dazzle/page/runtime/static/js/
```

## See Also

- [Python 3.14 primary target](../python-3.14-primary-target.md)
- [Local CI concordance](local-ci-concordance.md)
- [Testing Guide](testing.md)
- [Adding a Feature](adding-a-feature.md)
