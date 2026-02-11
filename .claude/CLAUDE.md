# CLAUDE.md

Guidance for Claude Code when working with the DAZZLE codebase.

## Project Overview

**DAZZLE** - DSL-first toolkit for building apps from high-level specifications.

```bash
cd examples/simple_task && dazzle serve
# UI: http://localhost:3000 | API: http://localhost:8000/docs
```

## Architecture

```
DSL Files → Parser → IR (AppSpec) → Dazzle Runtime (live app)
                                  → Code Generation (optional)
```

| Directory | Purpose |
|-----------|---------|
| `src/dazzle/core/` | Parser, IR, linker, validation |
| `src/dazzle_back/` | FastAPI runtime |
| `src/dazzle_ui/` | JavaScript UI runtime |
| `src/dazzle/specs/` | OpenAPI and AsyncAPI specification generators |

## LLM-First Style Guide

This is an LLM-first codebase. Optimize for clarity and predictability over cleverness.

### Python
- **Type hints required** on all public functions (enforced by mypy)
- **Pydantic models** for data crossing module boundaries
- **Explicit dependencies** - no hidden globals or singletons
- Avoid metaprogramming, monkey-patching, runtime code generation

### JavaScript (Dazzle UI)
- **Vanilla JS with JSDoc and `@ts-check`** - TypeScript checker without build step
- **All exported functions must have JSDoc** param/return types
- UI runtime is server-rendered via Python templates in `src/dazzle_ui/runtime/`

### General
- Prefer explicit over magic
- Keep functions small and single-purpose
- Data shapes in dedicated files (models.py, types at top of JS files)
- Never edit auto-generated files (marked with `# AUTO-GENERATED`)

## Commands

```bash
# Run app
dazzle serve              # Docker (default)
dazzle serve --local      # Without Docker

# Validate
dazzle validate               # Parse and validate DSL
dazzle lint                   # Extended checks

# Test
pytest tests/ -m "not e2e"    # Unit tests
pytest tests/ -m e2e          # E2E tests

# Lint
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle
```

## DSL Quick Reference

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
```

**Constructs**: `entity`, `surface`, `workspace`, `experience`, `service`, `foreign_model`, `integration`, `ledger`, `transaction`, `process`, `schedule`, `story`, `archetype`, `persona`, `scenario`

### TigerBeetle Ledgers (v0.24)

```dsl
ledger CustomerWallet "Customer Wallet":
  account_code: 1001
  ledger_id: 1
  account_type: asset
  currency: GBP
  flags: debits_must_not_exceed_credits
  sync_to: Customer.balance_cache

transaction RecordPayment "Record Payment":
  execution: async
  priority: high

  transfer revenue:
    debit: CustomerWallet
    credit: Revenue
    amount: payment.amount
    code: 1
    flags: linked

  idempotency_key: payment.id
```

**Account types**: `asset`, `liability`, `equity`, `revenue`, `expense`

## Extending

### Adding DSL Constructs
1. Update grammar in `docs/reference/grammar.md`
2. Add IR types in `src/dazzle/core/ir/`
3. Implement parser mixin in `src/dazzle/core/dsl_parser_impl/`
4. Add tests in `tests/unit/test_parser.py`

### API Specifications
```bash
# Generate OpenAPI spec
dazzle specs openapi

# Generate AsyncAPI spec
dazzle specs asyncapi
```

## Examples

All in `examples/`: `simple_task`, `contact_manager`, `ops_dashboard`, `pra`, `fieldtest_hub`, `llm_ticket_classifier`, `support_tickets`

## LSP Server

- LSP server: `dazzle lsp run` (diagnostics, hover, completion, go-to-definition)
- Check deps: `dazzle lsp check`
- Grammar path: `dazzle lsp grammar-path`

## MCP Server

The DAZZLE MCP server (`dazzle mcp`) provides context-aware tools:
- `dsl` (validate, inspect_entity, inspect_surface, lint, analyze)
- `knowledge` (concept, examples, workflow, inference)
- `story`, `process`, `demo_data`, `test_design`
- `sitespec`, `semantics`, `graph`, `bootstrap`, `spec_analyze`

Use MCP tools for DSL semantics; this file for codebase conventions.

## Known Limitations

- Integration actions/syncs use placeholder parsing
- No export declarations (planned v2.0)
- Experiences support basic flows only

---
**Version**: 0.22.0 | **Python**: 3.11+ | **Status**: Production Ready
