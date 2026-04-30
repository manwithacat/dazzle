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

**Constructs**: `entity`, `surface`, `workspace`, `experience`, `island`, `service`, `foreign_model`, `integration`, `ledger`, `transaction`, `process`, `schedule`, `story`, `archetype`, `persona`, `scenario`, `enum`, `webhook`, `approval`, `sla`, `rhythm`, `feedback_widget`, `subprocessor`, `analytics`

*(This is the user-facing subset. The parser also dispatches on `app`, `test`, `flow`, `rule`, `message`, `channel`, `asset`, `document`, `template`, `demo`, `event_model`, `subscribe`, `project`, `stream`, `hless`, `policies`, `tenancy`, `interfaces`, `data_products`, `llm_model`, `llm_config`, `llm_intent`, `notification`, `grant_schema`, `param`, `question`. The drift test in `tests/unit/test_docs_drift.py` asserts every name listed above actually exists in the parser.)*

**Scope rules** compile to a formal predicate algebra and are statically validated against the FK graph at `dazzle validate` time. Supported forms:
- Direct: `school_id = current_user.school` — column equality check
- FK path (depth-N): `manuscript.assessment_event.school_id = current_user.school` — nested subquery
- EXISTS: `via JunctionEntity(field = current_user.attr, field = id)` — junction table check
- NOT EXISTS: `not via BlockList(user = current_user, resource = id)` — negated junction check
- Negation: `not (status = archived)` — parenthesised negation
- Boolean: `realm = current_user.realm or creator = current_user` — AND/OR compile to SQL

Use `revoked_at = null` for literal null filters, `!=` for not-equals. Each `scope:` rule needs a matching `permit:` rule and a `for:` clause naming the personas.

## Autonomous Improvement Loop

Dazzle has a single agent-first entrypoint for autonomous investigation, improvement, refactoring, and remediation: `/improve`. The driver picks the highest-leverage **lane** each cycle based on actionable rows and signals, then hands off to that lane's playbook:

| Lane | Targets |
|------|---------|
| `framework-ux` | Dazzle's UI layer (templates, contracts, fitness walks). ux-architect-driven; was `/ux-cycle` |
| `example-apps` | Example app DSL gaps (lint, scope, fidelity, conformance). Tiered gap discovery |
| `trials` | Qualitative persona scenarios via `dazzle qa trial`. ~5 min/cycle, burns tokens — was `/trial-cycle` |
| `ux-converge` | Example apps with nonzero contract failures; runs converge-to-zero per app — was `/ux-converge` |

**State:**
- `dev_docs/improve-backlog.md` — unified backlog with one `## Lane:` section per lane
- `dev_docs/improve-log.md` — append-only cycle log across all lanes
- `.dazzle/improve.lock`, `.dazzle/improve-explore-count` — driver state (cap 100, shared across lanes)
- `.dazzle/signals/` — cross-loop signal bus (`ux_cycle_signals`); lanes emit `ux-component-shipped`, `trial-friction`, `convergence-clean` etc.

**Common invocations:**
- `/improve` — driver picks the lane
- `/improve framework-ux` — force a specific lane
- `/improve framework-ux contract_audit` — force lane + sub-strategy
- `/improve --status` — read-only status across all lanes
- `/loop 30m /improve` — recurring; lane-pickup auto each fire

**Files:** driver at `.claude/commands/improve.md`; lanes at `.claude/commands/improve/lanes/*.md`; sub-strategies at `.claude/commands/improve/strategies/*.md`. Design doc at `dev_docs/2026-04-25-improve-consolidation-design.md`.

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

### API surface snapshots (#961)

Five committed baselines under `docs/api-surface/` pin the framework's public API:

```bash
dazzle inspect-api dsl-constructs        # parser → IR class mapping
dazzle inspect-api ir-types              # 485 entries from dazzle.core.ir.__all__
dazzle inspect-api mcp-tools             # 32 MCP tool schemas
dazzle inspect-api public-helpers        # top-level __init__ exports
dazzle inspect-api runtime-urls          # AST walk of *_routes.py
```

Drift gate: `tests/unit/test_api_surface_drift.py` (21 tests). Adding `--write` regenerates the baseline; `--diff` prints unified-diff vs baseline. Any drift requires a CHANGELOG entry under Added/Changed/Removed. The improve loop's `framework-ux` lane has an `api_surface_audit` sub-strategy that walks one baseline per cycle asking "is this what we'd design today?" — the recurring 1.0-prep walkthrough.

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

## Reports & Charts

When writing any chart / report region (bar_chart, pivot_table, heatmap, funnel_chart, metrics), read `docs/reference/reports.md` first. It's the canonical entry point covering:

- Which `display:` mode matches which cardinality (0-dim KPI through N-dim pivot)
- Single-dim (`group_by: status`) vs multi-dim (`group_by: [system, severity]`)
- Fast vs slow path — prefer `count(<source>)` over `count(<other> where field = current_bucket)`
- FK auto-join behaviour and the display-field probe order
- Scope-safety contract (always pre-aggregation, no RBAC leaks)
- `dazzle db explain-aggregate` for debugging wrong/empty charts

Every chart region compiles to one `Repository.aggregate` call which runs one scope-aware `GROUP BY` SQL query. No N+1, no enumeration phase, no divergence between the bucket list and the counts (the bug class #847–#851 chased).

Example: `examples/ops_dashboard` has working `bar_chart` (FK `group_by: system`) and `pivot_table` (`group_by: [system, severity]`) regions.

## Gotchas

- **MCP test isolation**: Tests that mock `mcp.*` modules pollute `sys.modules`. The `tests/unit/conftest.py` 3-phase fixture handles this — don't bypass it.
- **PersonaSpec identity**: Use `.id`, not `.name` — `getattr(p, "name", None) or getattr(p, "id", "unknown")`.
- **State machine states**: Plain strings, not objects — use `s if isinstance(s, str) else s.name`.
- **KG re-seeding**: `ensure_seeded()` checks a version key; bump it in `seed.py` when TOML data changes.

---
**Version**: 0.63.11 | **Python**: 3.12+ | **Status**: Production Ready
