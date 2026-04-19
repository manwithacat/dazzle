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

## Project Layout Convention

When creating custom Python code in a Dazzle project (not the framework itself), follow the recommended layout. Production code goes in `app/<category>/` (e.g., `app/sync/`, `app/render/`, `app/db/`). One-shot scripts go in `scripts/`. Don't create flat dumping-ground directories. See `docs/reference/project-layout.md` for the full convention.

## Style Guide

- **Type hints required** on all public functions (enforced by mypy)
- **Pydantic models** for data crossing module boundaries
- **Explicit dependencies** — no hidden globals or singletons (ADR-0005)
- **No backward compat shims** — clean breaks, update all callers in same commit (ADR-0003)
- Prefer explicit over magic; keep functions small and single-purpose
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

**Constructs**: `entity`, `surface`, `workspace`, `experience`, `island`, `service`, `foreign_model`, `integration`, `ledger`, `transaction`, `process`, `schedule`, `story`, `archetype`, `persona`, `scenario`, `enum`, `webhook`, `approval`, `sla`, `rhythm`, `feedback_widget`

*(This is the user-facing subset. The parser also dispatches on `app`, `test`, `flow`, `rule`, `message`, `channel`, `asset`, `document`, `template`, `demo`, `event_model`, `subscribe`, `project`, `stream`, `hless`, `policies`, `tenancy`, `interfaces`, `data_products`, `llm_model`, `llm_config`, `llm_intent`, `notification`, `grant_schema`, `param`, `question`. The drift test in `tests/unit/test_docs_drift.py` asserts every name listed above actually exists in the parser.)*

**Scope rules** compile to a formal predicate algebra and are statically validated against the FK graph at `dazzle validate` time. Supported forms:
- Direct: `school_id = current_user.school` — column equality check
- FK path (depth-N): `manuscript.assessment_event.school_id = current_user.school` — nested subquery
- EXISTS: `via JunctionEntity(field = current_user.attr, field = id)` — junction table check
- NOT EXISTS: `not via BlockList(user = current_user, resource = id)` — negated junction check
- Negation: `not (status = archived)` — parenthesised negation
- Boolean: `realm = current_user.realm or creator = current_user` — AND/OR compile to SQL

Use `revoked_at = null` for literal null filters, `!=` for not-equals. Each `scope:` rule needs a matching `permit:` rule and a `for:` clause naming the personas.

## UX Improvement Loop

Dazzle has an autonomous UX improvement loop at `/ux-cycle`. It iterates over the backlog in `dev_docs/ux-backlog.md`, applies ux-architect contracts to components that lack them, refactors code to match, and validates via agent-driven Playwright QA against example apps. See `docs/superpowers/specs/2026-04-12-ux-cycle-design.md` for the full design.

**Common invocations:**
- `/ux-cycle` — one cycle
- `/loop 30m /ux-cycle` — recurring with 30-min intervals
- `/loop /ux-cycle` — self-paced

## Qualitative Trial Loop

Sibling to `/ux-cycle` — where ux-cycle checks *shape* (contracts, DOM, card safety) deterministically, `/trial-cycle` checks *substance* (did the user achieve the task, was the RBAC sensible, did the error page help) qualitatively. Each cycle picks an `(example_app, trial.toml scenario)` pair, runs `dazzle qa trial --fresh-db`, and triages findings into `dev_docs/trial-backlog.md` or GitHub issues. ~5 min/cycle; burns tokens — prefer `/loop 60m /trial-cycle` or manual.

Downstream Dazzle users can author their own `trial.toml` via the `qa-trial` skill (`.claude/skills/qa-trial/SKILL.md`). Each user domain stress-tests a different surface of the framework — aligns with the convergence hypothesis in ROADMAP.md.

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

### Fitness investigator
```bash
dazzle fitness investigate --top 1          # investigate highest-priority cluster
dazzle fitness investigate --cluster CL-... --dry-run
```
Proposals land at `.dazzle/fitness-proposals/`. See `docs/reference/fitness-investigator.md`.

## Examples

Working Dazzle apps in `examples/`: `simple_task`, `contact_manager`, `support_tickets`, `ops_dashboard`, `fieldtest_hub`

Internal fixtures in `fixtures/`: `shapes_validation`, `rbac_validation`, `pra`, `component_showcase`, `design_studio`, `project_tracker`, `llm_ticket_classifier`

## LSP Server

- LSP server: `dazzle lsp run` (diagnostics, hover, completion, go-to-definition)
- Check deps: `dazzle lsp check`
- Grammar path: `dazzle lsp grammar-path`

## MCP / CLI Boundary

MCP = stateless reads, CLI = process/writes (ADR-0002). Use `dazzle search <keyword>` to find commands.

### MCP Tools

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
dazzle db status|verify|reset|cleanup|stamp
dazzle tenant create|list|status|suspend|activate

# Data & integration
dazzle demo propose|save|generate
dazzle api-pack generate-dsl|env-vars|infrastructure|scaffold
dazzle mock scenarios|fire-webhook|inject-error|scaffold-scenario
dazzle contribution templates|create|validate|examples
```

## PyPI Package

- **Package name**: `dazzle-dsl` (the name `dazzle` is taken on PyPI)
- **Import name**: `dazzle` (unchanged — PEP 503 normalises the package name)
- `pip install dazzle-dsl` provides the `dazzle` console command

## Architectural Decisions

See `docs/adr/INDEX.md` for the full index. Key constraints:
- **No new singletons** — use `RuntimeServices` or `ServerState` (ADR-0005)
- **No SQLite** — PostgreSQL only (ADR-0008)
- **No SPA frameworks** — server-side Jinja2 + HTMX (ADR-0011)
- **No field conditions in `permit:`** — use `scope:` with `for:` (ADR-0010)
- **No `from __future__ import annotations`** in FastAPI route files (ADR-0014)
- **All schema changes via Alembic** — including framework entities (FeedbackReport, AIJob, admin entities). No raw ALTER TABLE. Use `dazzle db revision -m "description"` then `dazzle db upgrade` (ADR-0017)

## Ship Discipline

- **Clean worktree**: Every push must leave `git status` clean. After shipping, check for untracked or modified files (especially `dist/`) and commit them before moving on.
- **Bump on every fix**: Run `/bump patch` after bug fixes before pushing. Every push gets a unique version for deployment traceability.
- **Agent Guidance in CHANGELOG**: When a release introduces new patterns, conventions, ADRs, or breaking changes that affect how agents should work, add a `### Agent Guidance` section to that version's changelog entry. Keep entries concise — one bullet per topic, stating the rule and where to look.

## UI Invariants

- **Card safety**: any new region template, dashboard layout change, or fragment primitive must satisfy the 8 invariants in `docs/reference/card-safety-invariants.md`. The scanners in `src/dazzle/testing/ux/contract_checker.py` enforce them and `tests/unit/test_card_safety_invariants.py` pins each invariant to a named test. Regions emit zero chrome + zero title; the dashboard slot owns both. Tests run on the composite DOM, not isolated templates.

## Gotchas

- **MCP test isolation**: Tests that mock `mcp.*` modules pollute `sys.modules`. The `tests/unit/conftest.py` 3-phase fixture handles this — don't bypass it.
- **PersonaSpec identity**: Use `.id`, not `.name` — `getattr(p, "name", None) or getattr(p, "id", "unknown")`.
- **State machine states**: Plain strings, not objects — use `s if isinstance(s, str) else s.name`.
- **KG re-seeding**: `ensure_seeded()` checks a version key; bump it in `seed.py` when TOML data changes.

---
**Version**: 0.57.95 | **Python**: 3.12+ | **Status**: Production Ready
