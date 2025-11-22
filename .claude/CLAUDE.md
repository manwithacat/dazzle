# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DAZZLE (Domain-Aware, Token-Efficient DSL for LLM-Enabled Apps) is a machine-first software design experiment where:
- Humans describe business intent in natural language
- LLMs translate intent into a compact DSL
- Tooling converts the DSL into an internal representation (IR)
- Stacks generate concrete artifacts (APIs, UIs, infrastructure)

This is version 0.1, focusing on proving the core loop is viable and token-efficient.

## Core Architecture

### Three-Layer Model

1. **DSL Layer** (`.dsl` files)
   - Token-efficient, human-readable specifications
   - Defines domain models, surfaces (UI), experiences (flows), services, foreign models, integrations
   - Located in `dsl/` directory (or paths specified in `dazzle.toml`)

2. **IR Layer** (Internal Representation)
   - Structured, typed model built from DSL
   - Implemented with Pydantic schemas in `src/dazzle/core/`
   - Source of truth for all code generation
   - Lives in `ir.py` (to be implemented)

3. **Stack Layer** (Code Generation)
   - Plugins that consume IR to produce artifacts
   - Each stack (django_micro_modular, openapi, docker, terraform, etc.) is independent
   - Located in `src/dazzle/stacks/`

### Module System

- DSL files declare `module <name>` at the top (e.g., `module vat_tools.core`)
- Modules can depend on others via `use <module_name>` directives
- Project manifest (`dazzle.toml`) defines root module and DSL paths
- The linker (`src/dazzle/core/linker.py`) merges all modules into a single `AppSpec`

### Core Components

- **`src/dazzle/cli.py`**: CLI entry point using Typer (commands: validate, lint, build)
- **`src/dazzle/core/manifest.py`**: Loads `dazzle.toml` project configuration
- **`src/dazzle/core/fileset.py`**: Discovers DSL files based on manifest paths
- **`src/dazzle/core/parser.py`**: Parses DSL files into `ModuleIR` fragments
- **`src/dazzle/core/linker.py`**: Merges modules into unified `AppSpec`
- **`src/dazzle/core/lint.py`**: Validates `AppSpec` for consistency
- **`src/dazzle/core/errors.py`**: Error types (to be implemented)
- **`src/dazzle/core/ir.py`**: IR type definitions (to be implemented)

## DSL Concepts

The DSL vocabulary is intentionally small to keep tokens low:

- **app**: Root declaration with name and title
- **entity**: Internal domain models (with fields, constraints, indexes)
- **surface**: User-facing screens/forms (with sections, fields, actions)
- **experience**: Orchestrated flows with steps and transitions
- **service**: External third-party systems (with auth profiles)
- **foreign_model**: External data shapes from services
- **integration**: Connections between entities, foreign models, and services (actions and syncs)

See `docs/DAZZLE_DSL_REFERENCE_0_1.md` for full syntax reference and `docs/DAZZLE_DSL_GRAMMAR_0_1.ebnf` for formal grammar.

## Common Development Commands

### Validation and Linting

```bash
# Validate DSL specs (parse, link, validate merged AppSpec)
python -m dazzle.cli validate

# Validate with custom manifest path
python -m dazzle.cli validate --manifest path/to/dazzle.toml

# Run extended lint checks (naming, dead modules, unused imports)
python -m dazzle.cli lint

# Treat warnings as errors
python -m dazzle.cli lint --strict
```

### Building

```bash
# Generate artifacts using a stack
python -m dazzle.cli build --stack openapi --out ./build

# Build with multiple stacks
python -m dazzle.cli build --stack django_micro_modular,docker --out ./build

# Build with custom manifest
python -m dazzle.cli build --manifest path/to/dazzle.toml --stack openapi
```

### Working with DSL Files

DSL files are discovered automatically by scanning paths in `dazzle.toml`:

```toml
[project]
name = "vat_tools"
version = "0.1.0"
root = "vat_tools.core"

[modules]
paths = ["./dsl"]
```

## Development Guidelines

### When Adding New Features

1. **Updating the DSL**: Changes to syntax must be reflected in:
   - `docs/DAZZLE_DSL_REFERENCE_0_1.md` (reference documentation)
   - `docs/DAZZLE_DSL_GRAMMAR_0_1.ebnf` (formal grammar)
   - `src/dazzle/core/parser.py` (parser implementation)

2. **Extending the IR**: New IR types go in `src/dazzle/core/ir.py` (to be implemented):
   - Use Pydantic dataclasses for type safety
   - Keep the IR framework-neutral

3. **Adding Backends**: Each backend is a plugin in `src/dazzle/backends/`:
   - Must implement a standard interface (to be defined)
   - Consumes `AppSpec` from IR, produces framework-specific artifacts
   - Registered in `src/dazzle/backends/__init__.py`

### Parser Implementation Notes

- The parser in `parser.py` currently does minimal parsing (just extracts `module` and `use` declarations)
- Full DSL parsing needs to be implemented to build rich `ModuleIR` fragments containing entities, surfaces, etc.
- The parser should handle indentation-based blocks (Python-style)
- Comments start with `#` and extend to end of line

### Linker Implementation Notes

- `linker.py` currently returns a stub `AppSpec`
- Needs to:
  - Resolve `use` dependencies between modules
  - Detect cycles and missing modules
  - Merge fragments from all modules
  - Check for duplicate definitions and missing references

### Linter Implementation Notes

- `lint.py` has placeholder validation logic
- Should check:
  - Unresolved references (entities, surfaces, services, foreign models)
  - Duplicate names within same scope
  - Unreachable steps in experiences
  - Invalid field types and constraints
  - Naming conventions (in extended mode)

## Python Environment

- Python 3.12+ (project uses `tomllib` which is Python 3.11+)
- Dependencies: Typer (CLI), Pydantic (IR models)
- No `pyproject.toml` yet; add one when packaging

## Design Philosophy

- **Token efficiency over verbosity**: The DSL is compact to minimize LLM token costs
- **Machine-first, human-executive**: LLMs generate and mutate specs; humans guide intent
- **Framework-agnostic core**: The IR and DSL are deliberately not tied to any framework
- **Deterministic generation**: Only DSL generation uses LLMs; IR and codegen are deterministic
- **Intent-based**: DSL expresses "what" and "why", not "how" (implementation is in backends)

## Examples

See `examples/support_ticket_system.dsl` for a complete working example of a support ticket system with:
- Domain models (User, Ticket, Comment)
- Surfaces (ticket_board, ticket_create, ticket_detail)
- Experiences (ticket_lifecycle)
- Services and integrations (agent_directory, comments_service)

## Documentation

- `README.md`: High-level philosophy and concepts
- `docs/DAZZLE_DSL_REFERENCE_0_1.md`: Complete DSL syntax reference
- `docs/DAZZLE_DSL_GRAMMAR_0_1.ebnf`: Formal EBNF grammar
- `docs/DAZZLE_IR_0_1.md`: IR structure and types (to be implemented)
- `docs/DAZZLE_EXAMPLES_0_1.dsl`: Additional DSL examples

## Current State (v0.1)

This is an early-stage implementation. Core components exist but are incomplete:

- ✅ CLI skeleton with validate, lint, build commands
- ✅ Project manifest loading
- ✅ DSL file discovery
- ✅ Basic module parsing (module/use declarations only)
- ⏳ Full DSL parser (needs implementation)
- ⏳ IR type definitions (needs implementation)
- ⏳ Module linker (needs full implementation)
- ⏳ Validation rules (needs implementation)
- ⏳ Backend plugins (none implemented yet)

When implementing missing pieces, stay true to the token-efficiency and simplicity goals. Avoid feature creep.
