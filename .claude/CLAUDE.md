# CLAUDE.md

Guidance for Claude Code when working with the DAZZLE codebase.

## Project Overview

**DAZZLE** - DSL-first toolkit for building apps from high-level specifications.

- **Primary Runtime**: DNR (Dazzle Native Runtime) - runs DSL directly as FastAPI + signals-based UI
- **Optional**: Code generation via `base` builder for custom stacks

```bash
# Quick start - run any DAZZLE project
cd examples/simple_task
dazzle dnr serve
# UI: http://localhost:3000 | API: http://localhost:8000/docs
```

## Architecture

```
DSL Files → Parser → IR (AppSpec) → DNR Runtime (live app)
                                  → Code Generation (optional)
```

**Key Directories**:
- `src/dazzle/core/` - Parser, IR, linker, validation
- `src/dazzle_dnr_back/` - FastAPI runtime
- `src/dazzle_dnr_ui/` - JavaScript UI runtime
- `src/dazzle/stacks/base/` - Base builder for custom code generation

## DSL Concepts

```dsl
module my_app

app todo "Todo App"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  completed: bool=false

surface task_list "Tasks":
  uses entity Task
  mode: list
  section main:
    field title "Title"
    field completed "Done"

workspace dashboard "Dashboard":
  purpose: "Task overview"
  task_count:
    source: Task
    aggregate:
      total: count(Task)
```

**Constructs**: `entity`, `surface`, `workspace`, `experience`, `service`, `foreign_model`, `integration`

## Essential Commands

```bash
# DNR (primary)
dazzle dnr serve              # Run the app
dazzle dnr info               # Show project info

# Validation
dazzle validate               # Parse and validate DSL
dazzle lint                   # Extended checks
dazzle layout-plan            # Visualize workspace layouts

# Code generation (optional)
dazzle build --stack base     # Generate using base builder
```

## Core Files

| File | Purpose |
|------|---------|
| `src/dazzle/core/ir.py` | IR type system (Pydantic models) |
| `src/dazzle/core/dsl_parser.py` | DSL parser |
| `src/dazzle/core/linker.py` | Module linking and validation |
| `src/dazzle_dnr_back/runtime/server.py` | FastAPI server |
| `src/dazzle_dnr_ui/` | UI component system |

## Development

```bash
# Setup (editable install)
pip install -e '.[dev]'

# Test
pytest tests/
pytest tests/ -m "not e2e"    # Skip E2E tests

# Lint
ruff check src/ tests/ --fix
ruff format src/ tests/
mypy src/dazzle
```

**Code Quality**:
- Type hints required (enforced by mypy)
- Format with ruff before committing
- Tests required for new features

## Extending

### Adding DSL Constructs

1. Update `docs/DAZZLE_DSL_REFERENCE_0_1.md` (syntax)
2. Update `docs/DAZZLE_DSL_GRAMMAR_0_1.ebnf` (grammar)
3. Add IR types in `src/dazzle/core/ir.py`
4. Implement parser in `src/dazzle/core/dsl_parser.py`
5. Add tests in `tests/unit/test_parser.py`

### Custom Code Generation

Use the base builder:

```python
from dazzle.stacks.base import BaseBackend

class MyStack(BaseBackend):
    def generate(self, spec, output_dir, artifacts=None):
        # Transform spec into your target format
        ...
```

## Examples

All in `examples/`:
- `simple_task` - Basic CRUD app (start here)
- `contact_manager` - Multiple entities with relationships
- `uptime_monitor` - FOCUS_METRIC workspace archetype
- `email_client` - MONITOR_WALL workspace archetype
- `inventory_scanner` - SCANNER_TABLE workspace archetype
- `ops_dashboard` - COMMAND_CENTER workspace archetype

## Module System

```dsl
module my_app.core
use my_app.shared    # Declare dependencies

entity Foo "Foo":
  bar: ref Bar       # References require 'use' declaration
```

- Modules declare dependencies via `use`
- Linker validates cross-references
- Cycle detection built-in

## Known Limitations

- Integration actions/syncs use placeholder parsing
- No export declarations (planned v2.0)
- Experiences support basic flows only

## Documentation

- `docs/DAZZLE_DSL_REFERENCE_0_1.md` - Full DSL reference
- `docs/DAZZLE_DSL_GRAMMAR_0_1.ebnf` - Formal grammar
- `README.md` - User-facing overview

---
**Version**: 0.3.0 | **Python**: 3.11+ | **Status**: Production Ready
