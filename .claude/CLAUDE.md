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
| `src/dazzle/compliance/` | Compliance pipeline — ISO 27001 + SOC 2 evidence extraction, taxonomy, compiler |
| `src/dazzle/rbac/` | Provable RBAC — static matrix, dynamic verification, audit trail, compliance report |
| `src/dazzle/testing/` | Test infrastructure (agent E2E wrapper, browser gate) |
| `src/dazzle_back/` | FastAPI runtime (API, auth, channels, events, grants) |
| `src/dazzle_ui/` | UI runtime — Python/Jinja2 templates rendered server-side, static JS/CSS assets |

## Backward Compatibility Policy

**Backward compatibility is not a requirement.** This project has one major user who is fully engaged with the dev process. When making changes:

- **Prefer clean breaks over shims.** Delete old functions, rename freely, change signatures. Never create wrapper functions, re-exports, or compatibility aliases.
- **Update all callers** in the same commit rather than preserving old APIs.
- **Communicate breaking changes** via CHANGELOG.md (`### Changed` / `### Removed`) and GitHub issue comments. That is sufficient notice.

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

### Dev Setup
```bash
pip install -e ".[dev,llm,mcp]"    # Editable install with all extras
```

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

**Constructs**: `entity`, `surface`, `workspace`, `experience`, `island`, `service`, `foreign_model`, `integration`, `ledger`, `transaction`, `process`, `schedule`, `story`, `archetype`, `persona`, `scenario`, `enum`, `view`, `webhook`, `approval`, `sla`, `rhythm`, `feedback_widget`

**Scope rules** compile to a formal predicate algebra and are statically validated against the FK graph at `dazzle validate` time. Supported forms:
- Direct: `school_id = current_user.school` — column equality check
- FK path (depth-N): `manuscript.assessment_event.school_id = current_user.school` — nested subquery
- EXISTS: `via JunctionEntity(field = current_user.attr, field = id)` — junction table check
- NOT EXISTS: `not via BlockList(user = current_user, resource = id)` — negated junction check
- Negation: `not (status = archived)` — parenthesised negation
- Boolean: `realm = current_user.realm or creator = current_user` — AND/OR compile to SQL

Use `revoked_at = null` for literal null filters, `!=` for not-equals. Each `scope:` rule needs a matching `permit:` rule and a `for:` clause naming the personas.

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

## MCP / CLI Boundary

**MCP tools** = stateless reads returning data (fast, no side effects). Claude can continue thinking while these run.

**CLI commands** = anything that does work (generates, runs, writes, calls LLMs). Use `dazzle <group> <command>`.

### MCP Tools (24 knowledge/query tools)

| Tool | Operations |
|------|-----------|
| `dsl` | validate, inspect_entity, inspect_surface, lint, analyze, fidelity, export_frontend_spec |
| `story` | get, coverage, scope_fidelity |
| `rhythm` | get, list, coverage |
| `process` | list, inspect, list_runs, get_run, coverage |
| `test_design` | get, gaps |
| `discovery` | coherence |
| `graph` | query, dependencies, neighbourhood, concept, inference, export, import |
| `knowledge` | concept, examples, workflow, inference |
| `semantics` | extract, validate_events, tenancy, compliance, analytics |
| `sitespec` | get, validate, scaffold, coherence, review, advise, get_copy, scaffold_copy, review_copy, get_theme, scaffold_theme, validate_theme, generate_tokens, generate_imagery_prompts |
| `composition` | audit, capture, analyze, report, inspect_styles |
| `policy` | analyze, conflicts, coverage, simulate |
| `sentinel` | findings, status, history |
| `test_intelligence` | summary, failures, regression, coverage, context |
| `api_pack` | list, search, get |
| `mock` | status, request_log |
| `db` | status, verify |
| `demo_data` | get |
| `pitch` | get |
| `status` | mcp, logs, telemetry, activity |
| `bootstrap` | entry point for "build me an app" requests |
| `spec_analyze` | discover_entities, identify_lifecycles, extract_personas |
| `user_management` | list, create, get, update, deactivate |
| `user_profile` | observe, observe_message, get, reset |
| `llm` | ask |

### CLI Commands (process operations)

```bash
# Discovery & pipeline
dazzle discovery run|report|compile|emit|status|verify-all-stories
dazzle e2e check-infra|coverage|list-flows|tier-guidance|run-viewport|list-viewport-specs|save-viewport-specs

# Story & rhythm workflow
dazzle story propose|list|generate-tests|scope-fidelity
dazzle rhythm propose|evaluate|gaps|fidelity|lifecycle
dazzle process propose|save|diagram
dazzle test-design propose-persona|save|coverage-actions|runtime-gaps|save-runtime|improve-coverage

# Testing
dazzle test verify-story|generate|run|run-all|coverage|diff-personas

# Quality
dazzle pulse run|radar|persona|timeline|decisions|wfs
dazzle pitch review|update|enrich|init-assets
dazzle sentinel scan|suppress

# Database operations
dazzle db status|verify|reset|cleanup
dazzle tenant create|list|status|suspend|activate

# Data & integration
dazzle demo propose|save|generate
dazzle api-pack generate-dsl|env-vars|infrastructure|scaffold
dazzle mock scenarios|fire-webhook|inject-error|scaffold-scenario
dazzle contribution templates|create|validate|examples
```

## Vendor Integration Workflow

When integrating a third-party API:
1. `dazzle api-pack search` (MCP) — check for existing pack
2. `dazzle api-pack scaffold` (CLI) — create pack TOML (from OpenAPI or blank)
   - Save to `.dazzle/api_packs/<vendor>/<name>.toml`
3. `dazzle api-pack generate-dsl` (CLI) — generate service + foreign_model DSL blocks
4. Write integration + mapping DSL blocks
5. `dazzle serve --local` — mocks auto-start for all pack references
6. `dazzle mock fire-webhook` (CLI) — test webhook handling
7. `mock request_log` (MCP) — verify integration calls
8. `dazzle mock scenarios` (CLI) — test edge cases

### Project-Local Packs
Place custom packs in `.dazzle/api_packs/<vendor>/<name>.toml`.
Project-local packs override built-in packs with the same name.

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

## Gotchas

- **MCP test isolation**: Tests that mock `mcp.*` modules pollute `sys.modules`. The `tests/unit/conftest.py` 3-phase fixture handles this — don't bypass it.
- **PersonaSpec identity**: Use `.id`, not `.name` — `getattr(p, "name", None) or getattr(p, "id", "unknown")`.
- **State machine states**: Plain strings, not objects — use `s if isinstance(s, str) else s.name`.
- **KG re-seeding**: `ensure_seeded()` checks a version key; bump it in `seed.py` when TOML data changes.

---
**Version**: 0.48.5 | **Python**: 3.12+ | **Status**: Production Ready
