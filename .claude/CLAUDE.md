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
| `src/dazzle/agent/` | Generic mission-driven agent framework |
| `src/dazzle/mcp/` | MCP server, knowledge graph, semantics KB |
| `src/dazzle/cli/` | CLI commands (`dazzle serve`, `dazzle mcp`, etc.) |
| `src/dazzle/lsp/` | LSP server (diagnostics, hover, completion) |
| `src/dazzle/specs/` | OpenAPI and AsyncAPI specification generators |
| `src/dazzle/testing/` | Test infrastructure (agent E2E wrapper, browser gate) |
| `src/dazzle_back/` | FastAPI runtime (API, auth, channels, events) |
| `src/dazzle_ui/` | UI runtime — Python/Jinja2 templates rendered server-side, static JS/CSS assets |

## LLM-First Style Guide

This is an LLM-first codebase. Optimize for clarity and predictability over cleverness.

### Python
- **Type hints required** on all public functions (enforced by mypy)
- **Pydantic models** for data crossing module boundaries
- **Explicit dependencies** - no hidden globals or singletons
- Avoid metaprogramming, monkey-patching, runtime code generation

### General
- Prefer explicit over magic
- Keep functions small and single-purpose
- Data shapes in dedicated files (`models.py`)
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

**Constructs**: `entity`, `surface`, `workspace`, `experience`, `service`, `foreign_model`, `integration`, `ledger`, `transaction`, `process`, `schedule`, `story`, `archetype`, `persona`, `scenario`, `enum`, `view`, `webhook`, `approval`, `sla`

### TigerBeetle Ledgers

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

All in `examples/`: `simple_task`, `contact_manager`, `ops_dashboard`, `pra`, `fieldtest_hub`, `llm_ticket_classifier`, `support_tickets`, `rbac_validation`

## LSP Server

- LSP server: `dazzle lsp run` (diagnostics, hover, completion, go-to-definition)
- Check deps: `dazzle lsp check`
- Grammar path: `dazzle lsp grammar-path`

## MCP Server

The DAZZLE MCP server (`dazzle mcp`) provides 23 consolidated tools:

| Tool | Operations |
|------|-----------|
| `dsl` | validate, inspect_entity, inspect_surface, lint, analyze, fidelity, export_frontend_spec |
| `story` | propose, save, get, generate_tests, coverage |
| `process` | propose, save, list, inspect, diagram, coverage |
| `test_design` | propose_persona, gaps, save, get, auto_populate, improve_coverage |
| `dsl_test` | generate, run, run_all, coverage, verify_story, diff_personas |
| `e2e_test` | check_infra, run, run_agent, coverage, run_viewport |
| `discovery` | run, report, compile, emit, status, verify_all_stories, coherence |
| `pipeline` | run (full deterministic quality audit in one call) |
| `graph` | query, dependencies, neighbourhood, concept, inference, export, import |
| `status` | mcp, logs, telemetry, activity |
| `knowledge` | concept, examples, workflow, inference |
| `sitespec` | get, validate, scaffold, coherence, review, themes |
| `semantics` | extract, validate_events, tenancy, compliance, analytics |
| `composition` | audit, capture, analyze, report, inspect_styles |
| `policy` | analyze, conflicts, coverage, simulate |
| `pulse` | run, radar, persona, timeline, decisions |
| `pitch` | scaffold, generate, validate, review, enrich |
| `bootstrap` | entry point for "build me an app" requests |
| `spec_analyze` | discover_entities, identify_lifecycles, extract_personas |
| `demo_data` | propose, save, get, generate |
| `api_pack` | list, search, get, generate_dsl |
| `contribution` | templates, create, validate, examples |
| `user_management` | list, create, get, update, deactivate |

Use MCP tools for DSL semantics; this file for codebase conventions.

## Workshop

Run `dazzle workshop` in your project directory to watch MCP activity in a live terminal display. It shows active tools with progress bars, completed calls with timing, and a running tally of errors and warnings. Open it in a second terminal while Claude Code works on your app.

```bash
dazzle workshop                    # watch current directory
dazzle workshop --bell             # ring terminal bell on errors
dazzle workshop --tail 50          # show more history
dazzle workshop --info             # print log path (for scripting)
```

The log location defaults to `.dazzle/mcp-activity.log` and can be overridden in `dazzle.toml`:

```toml
[workshop]
log = ".dazzle/mcp-activity.log"   # default
```

The `status activity` MCP operation provides the same data for programmatic polling.

## PyPI Package

- **Package name**: `dazzle-dsl` (the name `dazzle` is taken on PyPI)
- **Import name**: `dazzle` (unchanged — PEP 503 normalises the package name)
- `pip install dazzle-dsl` provides the `dazzle` console command

---
**Version**: 0.27.0 | **Python**: 3.12+ | **Status**: Production Ready
