# DAZZLE Core – Test Infrastructure Specification

This document outlines the recommended test architecture for the DAZZLE Core project.
It assumes the reader is a Python developer familiar with pytest, mypy, hypothesis, and modern tooling.

---

## 1. Core Python Test Stack

DAZZLE Core should use a conventional but robust Python toolchain:

- **pytest** – primary test runner
- **hypothesis** – property-based testing for the IR and grammar
- **coverage.py** – coverage measurement
- **mypy** or **pyright** – static type checking (IR, parser, linker)
- **ruff** – linting, formatting, import sorting
- **pre-commit** – enforce style and run fast checks before commit

Directory structure:

```
dazzle_core/
    __init__.py

    dsl/
        parser.py
        lexer.py
        grammar.ebnf

    ir/
        models.py
        validate.py

    project/
        manifest.py      # dazzle.toml handling
        modules.py       # module/use resolution

    backends/
        __init__.py
        openapi.py
        ...

tests/
    unit/
    integration/
    fixtures/
pyproject.toml
```

---

## 2. Unit Tests for the Language Kernel

### a) Parser and Grammar Tests

Test that the DSL parser produces the correct AST/IR fragments.

Use **fixture DSL files** under `tests/fixtures/dsl/` such as:

- `ticket_minimal.dsl`
- `ticket_with_integrations.dsl`

Typical test:

```python
def test_parses_simple_entity(simple_entity_dsl):
    ir = parse_to_ir(simple_entity_dsl)
    assert len(ir.domain.entities) == 1
    entity = ir.domain.entities[0]
    assert entity.name == "Ticket"
    assert {f.name for f in entity.fields} == {"id", "title", "status"}
```

This validates that the DSL is parsed consistently and the IR structure is correct.

### b) IR Validation Tests

Construct IR objects directly and test the validator:

- Valid IR → should pass
- Invalid IR → should produce meaningful and friendly errors

Examples:

- Unknown entity referenced from a surface
- Duplicate entity names
- Cycles in experiences
- Missing services/foreign models in integrations

---

## 3. Golden-Master (“Snapshot”) Tests for DSL → IR

These tests ensure that DSL changes don’t accidentally break IR output.

Under `tests/fixtures/apps/`:

```
support_tickets.dsl
support_tickets.ir.json
```

The test:

1. Parse DSL → produce IR
2. Normalise IR (sorting lists, stripping timestamps/metadata)
3. Compare to the stored `support_tickets.ir.json`

You can use:

- `pytest-regressions`
- `syrupy`
- or a custom JSON comparator

This creates a stable interface between DSL and tooling.

---

## 4. Property-Based Testing with Hypothesis

Hypothesis is excellent for stress-testing the IR and parser.

Recommended strategies:

### 1. IR Generators

Generate small random `EntitySpec`, `SurfaceSpec`, `ExperienceSpec`, and check:

- `validate_ir()` accepts valid structures
- invalid structures yield predictable, safe errors
- validation never raises raw exceptions

### 2. Round-Trip Tests

Once DAZZLE supports IR → DSL pretty-printing:

- Generate random IRs
- Render to DSL
- Parse DSL back to IR
- Assert structural equivalence (“equivalent enough”)

Even if limited to entities/fields initially, it greatly increases confidence.

---

## 5. Module/Project Resolution Tests

Since DAZZLE now supports:

- `module <name>`
- `use <module_name>`
- `dazzle.toml` manifests

We need explicit tests of module composition and linking.

Fixture layout:

```
tests/fixtures/projects/support/
    dazzle.toml
    core.dsl                 # module support.core
    ui.dsl                   # module support.ui; use support.core
    integrations.dsl         # module support.integrations; use support.core
```

Test cases:

- Successful merge:
  - load all modules
  - resolve `use` dependencies
  - verify cross-module entity/surface/service references
- Negative cases:
  - missing module referenced in `use`
  - duplicate entity names across modules
  - unresolved symbols in surfaces/experiences/integrations

---

## 6. Backend Contract Tests

Even if early backends are stubbed, you can test the **backend interface**:

1. Define a small fake backend that implements `generate(appspec, out_dir)`
2. Run it with:
   - Parsed IR from a known DSL example
   - Assert expected output structure (snapshot)

Once real backends (Django/FastAPI/OpenAPI) arrive:

- Validate generated Python via `compileall`
- Validate generated OpenAPI via a schema validator

---

## 7. CLI Tests

Use pytest with `capsys` or Click’s `CliRunner`:

- `dazzle validate`
- `dazzle lint`
- `dazzle build`

Tests should assert:

- Exit codes
- Friendly errors for invalid DSL
- Correct output paths for builds
- Stable output text for summaries

---

## 8. Continuous Integration (CI)

A minimal GitHub Actions workflow:

```yaml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install .[dev]
      - run: pytest --maxfail=1 --disable-warnings -q
      - run: mypy dazzle_core
      - run: ruff check .
```

This ensures every PR preserves DSL consistency and IR validity.

---

## Summary

The DAZZLE test infrastructure should emphasise:

- **Separation of concerns**: parser vs IR vs linker vs backend
- **Predictability**: snapshot tests for DSL → IR
- **Robustness**: property-based tests for IR and parser
- **Extensibility**: module-aware linting + backend contract tests
- **Tooling discipline**: mypy, ruff, pre-commit, CI

This provides a durable foundation for DAZZLE’s evolution into a real, multi-module DSL ecosystem.
