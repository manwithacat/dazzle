# DAZZLE Test Infrastructure

Comprehensive guide to testing in the DAZZLE codebase.

## Overview

DAZZLE has a multi-layered test infrastructure with **1,300+ test functions** across **68+ test files**. Tests are organized by scope (unit, integration, E2E) and execution context (local, pre-commit, CI).

```
┌─────────────────────────────────────────────────────────────────┐
│                        Test Pyramid                              │
├─────────────────────────────────────────────────────────────────┤
│                     E2E Tests (Playwright)                       │
│              ┌───────────────────────────────────┐              │
│              │  Browser automation, full stack   │              │
│              └───────────────────────────────────┘              │
│                                                                  │
│                   Integration Tests                              │
│         ┌─────────────────────────────────────────────┐         │
│         │  Multi-component, DNR pipeline, GraphQL     │         │
│         └─────────────────────────────────────────────┘         │
│                                                                  │
│                        Unit Tests                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Parser, IR, Linker, Validator, CLI, Code Generation      │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Quick Reference

| What | Command | When |
|------|---------|------|
| Fast local tests | `pytest tests/unit -m "not slow" -x` | During development |
| All unit tests | `pytest tests/unit/` | Before committing |
| Integration tests | `pytest tests/integration/` | Before PR |
| JavaScript tests | `npm test` | For UI changes |
| Pre-commit checks | `pre-commit run --all-files` | Auto on commit |
| Full CI simulation | `pytest -m "not e2e" --cov` | Manual verification |

---

## Test Categories

### 1. Unit Tests

**Location:** `tests/unit/`
**Framework:** pytest + pytest-asyncio
**Execution:** Local, Pre-commit (fast), CI

Core functionality tests covering:

| Area | Files | Description |
|------|-------|-------------|
| Parser | `test_parser.py` | DSL parsing, syntax |
| IR | `test_ir.py`, `test_ir_e2e_types.py` | Intermediate representation |
| Linker | `test_linker.py` | Module linking, resolution |
| Validator | `test_validator.py` | Semantic validation |
| State Machines | `test_state_machine_parsing.py` | State/transition parsing |
| Access Control | `test_access_rules.py`, `test_access_evaluator.py` | Permissions |
| CLI | `test_cli.py`, `test_cli_bridge.py` | Command-line interface |
| Code Generation | `test_adapters.py`, `test_ejection.py` | Ejection adapters |
| Layout | `test_layout_engine.py`, `test_layout_ir.py` | UI layout system |
| Accessibility | `test_accessibility_checker.py`, `test_wcag_mapping.py` | WCAG compliance |

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run fast tests only (excludes subprocess spawning)
pytest tests/unit/ -m "not slow" -v

# Run with coverage
pytest tests/unit/ --cov=src/dazzle --cov-report=html

# Run specific test file
pytest tests/unit/test_parser.py -v

# Run tests matching pattern
pytest tests/unit/ -k "test_entity" -v
```

### 2. Integration Tests

**Location:** `tests/integration/`
**Framework:** pytest
**Execution:** CI (after unit tests pass)

Multi-component tests:

| File | Description |
|------|-------------|
| `test_dnr_pipeline.py` | AppSpec → BackendSpec/UISpec conversion |
| `test_dnr_e2e.py` | Full DNR pipeline |
| `test_end_to_end.py` | Complete workflows |
| `test_archetype_examples.py` | Archetype expansion |
| `test_golden_master.py` | Snapshot/golden master testing |
| `test_graphql_integration.py` | GraphQL schema generation |
| `test_ux_semantic_layer.py` | UX semantic layer |

```bash
# Run all integration tests
pytest tests/integration/ -v

# Run with early exit on failure
pytest tests/integration/ -v --maxfail=1
```

### 3. E2E Tests

#### 3.1 Docker-Based E2E (`tests/e2e/docker/`)

**Framework:** Playwright (Python) in Docker
**Execution:** CI (ux-coverage workflow), Manual

Full browser automation with Docker Compose:

```bash
# Run E2E tests (requires Docker)
./tests/e2e/docker/run_tests.sh

# With rebuild
./tests/e2e/docker/run_tests.sh --build

# Interactive mode for debugging
./tests/e2e/docker/run_tests.sh --interactive

# Cleanup containers
./tests/e2e/docker/run_tests.sh --cleanup
```

#### 3.2 Semantic DOM Contract Tests

**Location:** `tests/e2e/test_semantic_dom_contract.py`
**Execution:** CI (semantic-e2e job)

Tests semantic HTML contracts and `data-dazzle-*` attributes:

```bash
pytest tests/e2e/test_semantic_dom_contract.py -v --timeout=60
```

#### 3.3 DNR Serve Tests

**Location:** `tests/e2e/test_dnr_serve.py`
**Execution:** CI (dnr-e2e job)

Tests `dazzle dnr serve` command functionality:

```bash
pytest tests/e2e/test_dnr_serve.py -v --timeout=120
```

### 4. DNR Runtime Tests

#### Backend Tests (`src/dazzle_dnr_back/tests/`)

| File | Description |
|------|-------------|
| `test_runtime.py` | FastAPI initialization, routing |
| `test_repository.py` | Data access layer |
| `test_query_builder.py` | Query construction |
| `test_access_control.py` | Authorization |
| `test_state_machine.py` | State transitions |
| `test_computed_evaluator.py` | Computed fields |
| `test_invariant_evaluator.py` | Invariant checking |
| `test_websocket_manager.py` | WebSocket connectivity |
| `test_file_storage.py` | File uploads |
| `test_fts.py` | Full-text search |

#### UI Tests (`src/dazzle_dnr_ui/tests/`)

| File | Description |
|------|-------------|
| `test_runtime.py` | UI runtime |
| `test_ui_spec.py` | UI spec generation |
| `test_behaviour_layer.py` | Behavioral components |
| `test_js_loader.py` | JavaScript loading |

### 5. JavaScript Tests

**Location:** `src/dazzle_dnr_ui/runtime/static/js/*.test.js`
**Framework:** Vitest (jsdom environment)
**Execution:** Pre-commit, CI (js-test job)

```bash
# Run JavaScript tests
npm test

# Watch mode for development
npm run test:watch
```

### 6. LLM Tests

**Location:** `tests/llm/`
**Execution:** Manual (requires API keys)

Tests for AI-assisted features:

| File | Description |
|------|-------------|
| `test_models.py` | LLM model integration |
| `test_dsl_generator.py` | DSL generation from natural language |
| `test_fixtures.py` | LLM fixture generation |

---

## Example-Specific Tests

### Simple Task (`examples/simple_task/tests/e2e/`)

**File:** `test_simple_task_generated.py`
**Execution:** CI (example-e2e job)

Auto-generated E2E tests with 12 test cases:

```bash
cd examples/simple_task
pytest tests/e2e/test_simple_task_generated.py -v
```

### FieldTest Hub (`examples/fieldtest_hub/tests/e2e/`)

**NEW** - Comprehensive E2E test suite for demo evaluation.

| File | Tests | Description |
|------|-------|-------------|
| `test_stories.py` | 18 | User story tests (ST-001 to ST-018) |
| `test_access_control.py` | 23 | Persona permission tests |
| `test_state_machines.py` | 20 | State transition tests |
| `test_invariants.py` | 18 | Business rule validation |
| `test_dazzle_bar.py` | 17 | Developer toolbar tests |
| `test_computed_fields.py` | 11 | Computed field tests |

**Not in CI** - Manual execution for demo evaluation.

```bash
# Prerequisites
cd examples/fieldtest_hub
dazzle dnr serve --local  # Start the app

# Install test dependencies
pip install playwright pytest httpx
playwright install chromium

# Run all FieldTest Hub E2E tests
pytest tests/e2e/ -v

# Run by category
pytest tests/e2e/ -m story           # User stories
pytest tests/e2e/ -m access_control  # Permissions
pytest tests/e2e/ -m state_machine   # State transitions
pytest tests/e2e/ -m invariant       # Business rules
pytest tests/e2e/ -m dazzle_bar      # Dazzle Bar
pytest tests/e2e/ -m computed        # Computed fields
```

---

## Execution Contexts

### Local Development

Fast feedback loop during development:

```bash
# Fastest - unit tests, skip slow
pytest tests/unit -m "not slow" -x --tb=short

# JavaScript tests
npm test

# Type checking
mypy src/dazzle/core src/dazzle/cli
npm run typecheck
```

### Pre-Commit Hooks

Automatically runs on `git commit`:

| Hook | Description |
|------|-------------|
| `ruff` | Python linting + formatting |
| `mypy` | Python type checking (src/ only) |
| `bandit` | Security checks |
| `eslint` | JavaScript linting |
| `tsc` | JavaScript type checking |
| `vitest` | JavaScript tests |
| `dsl-validate` | DSL validation |
| `pytest-fast` | Fast unit tests |

```bash
# Manual pre-commit run
pre-commit run --all-files

# Skip hooks (emergency only)
git commit --no-verify
```

### CI/GitHub Actions

Runs on push to main/develop and pull requests:

| Job | Runs | Description |
|-----|------|-------------|
| `python-tests` | All PRs | Unit tests (Python 3.11, 3.12) |
| `lint` | All PRs | Ruff, Bandit, DSL validation |
| `js-lint` | All PRs | ESLint |
| `js-test` | All PRs | Vitest |
| `js-typecheck` | All PRs | TypeScript checker |
| `type-check` | All PRs | mypy on core modules |
| `integration` | After lint | Integration tests |
| `dnr-e2e` | After lint | DNR serve tests |
| `semantic-e2e` | After lint | Semantic DOM tests |
| `example-e2e` | After lint | P0 examples (simple_task, contact_manager) |
| `example-e2e-extended` | main only | P1/P2 examples (warnings only) |
| `homebrew-validation` | All PRs | Formula validation (macOS) |
| `ux-coverage` | Separate workflow | UX coverage tracking |

---

## Test Markers

### Standard Markers (pyproject.toml)

```python
@pytest.mark.unit          # Unit tests
@pytest.mark.integration   # Integration tests
@pytest.mark.slow          # Slow tests (subprocess, full validation)
@pytest.mark.e2e           # End-to-end tests
```

### Priority Markers (E2E tests)

```python
@pytest.mark.high_priority    # P0 - blocks PRs
@pytest.mark.medium_priority  # P1 - informational
@pytest.mark.low_priority     # P2 - experimental
```

### Feature Markers (FieldTest Hub)

```python
@pytest.mark.story         # User story tests
@pytest.mark.access_control # Permission tests
@pytest.mark.state_machine  # State transition tests
@pytest.mark.invariant      # Business rule tests
@pytest.mark.dazzle_bar     # Dazzle Bar tests
@pytest.mark.computed       # Computed field tests
```

---

## Coverage

### Configuration (pyproject.toml)

```toml
[tool.coverage.run]
source = ["src/dazzle"]
omit = ["*/tests/*", "*/__pycache__/*"]
```

### Generate Coverage Report

```bash
# Terminal report
pytest --cov=src/dazzle --cov-report=term-missing

# HTML report (opens in browser)
pytest --cov=src/dazzle --cov-report=html
open htmlcov/index.html

# XML for CI upload
pytest --cov=src/dazzle --cov-report=xml
```

---

## Test Dependencies

### Python (install with `pip install -e ".[dev]"`)

- pytest >= 7.4
- pytest-asyncio >= 0.23
- pytest-cov >= 4.1
- pytest-xdist >= 3.3 (parallel execution)
- pytest-timeout >= 2.2
- hypothesis >= 6.82 (property-based testing)
- syrupy >= 4.0 (snapshot testing)
- playwright (E2E tests)
- httpx (API testing)

### JavaScript (install with `npm install`)

- vitest ^2.0.0
- jsdom ^25.0.0
- typescript ^5.0.0
- eslint ^9.0.0

### System (for Docker E2E)

- Docker + Docker Compose
- Playwright browsers (`playwright install chromium`)

---

## Troubleshooting

### Tests timing out

```bash
# Increase timeout
pytest tests/e2e/ -v --timeout=300

# Run with verbose output
pytest -vv -l
```

### Flaky E2E tests

```bash
# Re-run failed tests
pytest --lf

# Run specific test in isolation
pytest tests/e2e/test_file.py::test_specific -v
```

### Pre-commit failures

```bash
# See what failed
pre-commit run --all-files -v

# Fix ruff issues
ruff check src/ --fix
ruff format src/

# Skip specific hook (debug only)
SKIP=pytest-fast git commit -m "message"
```

### Docker E2E issues

```bash
# Cleanup and rebuild
./tests/e2e/docker/run_tests.sh --cleanup
./tests/e2e/docker/run_tests.sh --build

# Check container logs
docker-compose -f tests/e2e/docker/docker-compose.yml logs
```

---

## Adding New Tests

### Unit Test

```python
# tests/unit/test_new_feature.py
import pytest
from dazzle.core.new_feature import NewFeature

class TestNewFeature:
    def test_basic_functionality(self):
        """Test basic feature works."""
        feature = NewFeature()
        assert feature.do_something() == expected

    @pytest.mark.slow
    def test_expensive_operation(self):
        """Test that spawns subprocess."""
        ...

    @pytest.mark.asyncio
    async def test_async_operation(self):
        """Test async functionality."""
        result = await feature.async_method()
        assert result is not None
```

### E2E Test (Playwright)

```python
# examples/my_example/tests/e2e/test_my_example.py
import pytest
from playwright.sync_api import Page

@pytest.mark.e2e
class TestMyExample:
    def test_page_loads(self, page: Page, ui_url: str):
        """Test main page loads."""
        page.goto(ui_url)
        assert page.title() == "My Example"

    def test_create_entity(self, page: Page, ui_url: str):
        """Test entity creation."""
        page.goto(f"{ui_url}/entity/create")
        page.fill('[data-dazzle-field="name"]', "Test")
        page.click('[data-dazzle-action="save"]')
        # Assert success
```

---

## Summary

| Layer | Location | Local | Pre-commit | CI |
|-------|----------|:-----:|:----------:|:--:|
| Unit | `tests/unit/` | ✅ | ✅ (fast) | ✅ |
| Integration | `tests/integration/` | ✅ | ❌ | ✅ |
| E2E (Docker) | `tests/e2e/docker/` | ✅ | ❌ | ✅ |
| E2E (Semantic) | `tests/e2e/test_semantic_dom_contract.py` | ✅ | ❌ | ✅ |
| DNR Backend | `src/dazzle_dnr_back/tests/` | ✅ | ❌ | ✅ |
| DNR UI | `src/dazzle_dnr_ui/tests/` | ✅ | ❌ | ✅ |
| JavaScript | `*.test.js` | ✅ | ✅ | ✅ |
| Example E2E (P0) | `examples/*/tests/e2e/` | ✅ | ❌ | ✅ |
| Example E2E (P1/P2) | `examples/*/tests/e2e/` | ✅ | ❌ | ⚠️ (main only) |
| FieldTest Hub | `examples/fieldtest_hub/tests/e2e/` | ✅ | ❌ | ❌ (manual) |
| LLM | `tests/llm/` | ✅ | ❌ | ❌ (manual) |

---

*Last updated: December 2024*
