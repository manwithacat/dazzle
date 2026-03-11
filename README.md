# DAZZLE

**Human Intent → Structured DSL → Deterministic Code → Frontier AI Cognition**

<!-- Versions & Compatibility -->
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Homebrew](https://img.shields.io/badge/homebrew-manwithacat%2Ftap-orange)](https://github.com/manwithacat/homebrew-tap)

<!-- Build & Quality -->
[![CI](https://github.com/manwithacat/dazzle/workflows/CI/badge.svg)](https://github.com/manwithacat/dazzle/actions)
[![codecov](https://codecov.io/gh/manwithacat/dazzle/graph/badge.svg)](https://codecov.io/gh/manwithacat/dazzle)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-checked-blue.svg)](https://mypy-lang.org/)

<!-- Meta -->
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://manwithacat.github.io/dazzle/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/manwithacat/dazzle.svg?style=social)](https://github.com/manwithacat/dazzle)

DAZZLE is a **declarative application framework**. You describe *what* your application is — its data, its screens, its workflows, its users — and Dazzle figures out *how* to build it. You write `.dsl` files; Dazzle gives you a working web application with a database, API, rendered UI, authentication, and CRUD operations. No code generation step, no build toolchain, no scaffold to maintain.

```bash
cd examples/simple_task && dazzle serve
# UI:  http://localhost:3000
# API: http://localhost:8000/docs
```

---

## Table of Contents

- [The Core Idea](#the-core-idea)
- [Quick Start](#quick-start)
- [DSL Feature Highlights](#dsl-feature-highlights)
- [The Pipeline](#the-pipeline-determinism-and-cognition)
- [The MCP Tooling Pipeline](#the-mcp-tooling-pipeline)
- [Agent Framework](#agent-framework)
- [Three-Tier Testing](#three-tier-testing)
- [API Packs](#api-packs)
- [Fidelity Scoring](#fidelity-scoring)
- [Why HTMX, Not React](#why-htmx-not-react)
- [Install](#install)
- [IDE Support](#ide-support)
- [Examples](#examples)
- [Project Structure](#project-structure)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## The Core Idea

Dazzle is built on one principle: **the DSL is the application**. There is no code generation step that produces source files you then maintain. The DSL is parsed into a semantic intermediate representation (the AppSpec IR), and the runtime executes that IR directly.

```
DSL Files  →  Parser + Linker  →  AppSpec (IR)  →  Runtime (live app)
                                                 →  OpenAPI / AsyncAPI specs
                                                 →  Test generation
                                                 →  Fidelity scoring
```

This means:

- **Change the DSL, refresh the browser.** The runtime re-reads the IR on every request in dev mode.
- **No generated code to keep in sync.** The DSL is the single source of truth.
- **Every artifact is derivable.** API specs, test suites, demo data, and documentation are all computed from the same IR.
- **The DSL is analyzable.** Because it is deliberately anti-Turing (no arbitrary computation), Dazzle can validate, lint, measure fidelity, and reason about your application statically.

"Declarative" does not mean "limited." Dazzle has a layered architecture that lets you start simple and add complexity only where your business genuinely needs it. A todo app is 20 lines of DSL. A 39-entity accountancy SaaS with state machines, double-entry ledgers, multi-step onboarding wizards, and role-based dashboards is the same language — just more of it.

## Quick Start

```bash
# Install
brew install manwithacat/tap/dazzle   # macOS/Linux (auto-registers MCP server)
# or: pip install dazzle-dsl

# Run the example
cd examples/simple_task
dazzle serve

# Open http://localhost:3000 for the UI
# Open http://localhost:8000/docs for the API
```

That's it. No code generation, no build step — your DSL runs directly.

### First DSL File

```dsl
module my_app

app todo "Todo Application"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  completed: bool=false
  created_at: datetime auto_add

surface task_list "Tasks":
  uses entity Task
  mode: list

  section main:
    field title "Title"
    field completed "Done"
```

Save this as `app.dsl`, run `dazzle serve`, and you have a working application with:
- A database table with correct column types and constraints
- CRUD API endpoints with pagination, filtering, and sorting
- A rendered list UI with sortable columns and a create form
- OpenAPI documentation at `/docs`

---

## DSL Feature Highlights

<!-- BEGIN FEATURE TABLE -->
| Feature | Description |
|---------|-------------|
| [Entities](docs/reference/entities.md) | Entities are the core data models in DAZZLE. |
| [Access Control](docs/reference/access-control.md) | DAZZLE uses Cedar-style access rules with three layers: entity-level permit/forbid blocks, surface-level access restrictions, and workspace-level persona allow/deny lists. |
| [Surfaces](docs/reference/surfaces.md) | Surfaces define the UI and API interfaces for interacting with entities. |
| [Workspaces](docs/reference/workspaces.md) | Workspaces compose multiple data views into cohesive dashboards or information hubs. |
| [UX Semantic Layer](docs/reference/ux.md) | The UX semantic layer expresses WHY interfaces exist and WHAT matters to users, without prescribing HOW to implement it. |
| [Experiences](docs/reference/experiences.md) | Experiences define multi-step user flows such as onboarding wizards, checkout processes, and approval workflows. |
| [Services](docs/reference/services.md) | Services declare custom business logic in DSL with implementation in Python or TypeScript stubs. |
| [Integrations](docs/reference/integrations.md) | Integrations connect DAZZLE apps to external systems via declarative API bindings with triggers, field mappings, and error handling. |
| [Processes](docs/reference/processes.md) | Processes orchestrate durable, multi-step workflows across entities and services. |
| [Stories](docs/reference/stories.md) | Stories capture expected user-visible outcomes in a structured format tied to personas and entities. |
| [Rhythms](docs/guides/rhythms.md) | Rhythms capture longitudinal persona journeys organized into temporal phases containing scenes — evaluable actions on specific surfaces. Use `rhythm propose` to generate from natural language. |
| [Ledgers & Transactions](docs/reference/ledgers.md) | Ledgers and transactions provide TigerBeetle-backed double-entry accounting. |
| [LLM Models & Intents](docs/reference/llm.md) | DAZZLE supports declarative LLM job definitions for AI-powered tasks such as classification, extraction, and generation. |
| [Testing](docs/reference/testing.md) | DAZZLE provides a comprehensive testing toolkit including E2E testing with Playwright, FlowSpec test generation, semantic DOM conventions, capability discovery, CRUD completeness analysis, workflow coherence checks, and RBAC validation. |
| [Frontend & Templates](docs/reference/frontend.md) | The Dazzle frontend uses server-rendered Jinja2 templates with HTMX for declarative HTTP interactions. |
| [Messaging & Events](docs/reference/messaging.md) | Messaging and events enable asynchronous communication between components and users. |
| [Governance](docs/reference/governance.md) | Governance constructs enforce organisational policies, approval workflows, and service-level agreements. |
| [Patterns](docs/reference/patterns.md) | Patterns are reusable DSL recipes that combine multiple constructs into proven solutions. |
<!-- END FEATURE TABLE -->

For a complete walkthrough of each layer, see the [DSL Reference](docs/reference/index.md).

---

## The Pipeline: Determinism and Cognition

DAZZLE separates work into two distinct phases: a **deterministic foundation** that requires zero LLM involvement (parsing, linking, validation, runtime execution), and a **cognitive layer** where LLM creativity adds value (story generation, test proposals, gap analysis). The deterministic phase handles all the mechanical work that LLMs do poorly; the cognitive phase leverages what LLMs do well — understanding intent, proposing test scenarios, and identifying gaps. Every cognitive artifact (stories, test designs, processes) is saved as reviewable YAML, never executed blindly.

See [Architecture Overview](docs/architecture/overview.md) for the full pipeline diagram.

---

## The MCP Tooling Pipeline

Dazzle is not just a runtime — it is also an AI-assisted development environment accessed through MCP (Model Context Protocol) tools. When you use Claude Code with a Dazzle project, you get access to **26 tools with 170+ operations** spanning every stage from natural-language spec to visual regression testing.

### 1. Spec to DSL

Turn a plain-English idea into validated DSL. `bootstrap` is the entry point for "build me an app" requests; `spec_analyze` breaks a narrative into entities, lifecycles, personas, and business rules; `dsl` validates and inspects the result; `api_pack` wires in external APIs.

| Tool | Operations | Purpose |
|------|-----------|---------|
| `bootstrap` | (single operation) | Entry point — scans for spec files, runs cognition pass, returns a mission briefing |
| `spec_analyze` | discover_entities, identify_lifecycles, extract_personas, surface_rules, generate_questions, refine_spec | Analyze natural-language specs before DSL generation |
| `dsl` | validate, lint, inspect_entity, inspect_surface, analyze, list_modules, get_spec, fidelity, list_fragments, export_frontend_spec | Parse, validate, inspect, and score DSL files |
| `api_pack` | list, search, get, generate_dsl, env_vars, infrastructure | External API integration packs with infra manifests |

### 2. Test and Verify

Generate stories, design tests, execute them at three tiers, and seed realistic demo data — all from the DSL.

| Tool | Operations | Purpose |
|------|-----------|---------|
| `story` | propose, save, get, generate_tests, coverage | Generate and manage user stories; `get` with `view=wall` shows a founder-friendly board grouped by implementation status |
| `test_design` | propose_persona, gaps, save, get, coverage_actions, runtime_gaps, save_runtime, auto_populate, improve_coverage | Persona-centric test design with autonomous gap-filling |
| `dsl_test` | generate, run, run_all, coverage, list, create_sessions, diff_personas, verify_story | API tests — including `verify_story` (check story implementations) and `diff_personas` (compare route behavior across roles) |
| `e2e_test` | check_infra, run, run_agent, coverage, list_flows, tier_guidance, run_viewport, list_viewport_specs, save_viewport_specs | Browser E2E with Playwright — viewport testing, screenshot capture, visual regression baselines, and `tier_guidance` for test strategy |
| `demo_data` | propose, save, get, generate | Generate realistic seed data per persona/tenant |
| `rhythm` | propose, evaluate, coverage, get, list | Longitudinal persona journey maps — propose rhythms from natural language, evaluate surface/entity coverage, find persona gaps |

### 3. Analyze and Audit

Deterministic quality checks, agent-powered gap discovery, visual composition analysis, semantic extraction, and RBAC policy verification.

| Tool | Operations | Purpose |
|------|-----------|---------|
| `pipeline` | run | Full quality audit in one call — chains validate, lint, fidelity, composition audit, test/story/process coverage, test design gaps, and semantics. Adaptive detail levels (`metrics`/`issues`/`full`) |
| `nightly` | run | Same quality steps as pipeline but fans out independent steps in parallel for ~50% wall-clock speedup. Uses dependency graph to run validate first, then lint/fidelity/composition/coverage concurrently |
| `discovery` | run, report, compile, emit, status, verify_all_stories, coherence | Agent-powered capability discovery in 4 modes: `persona`, `entity_completeness`, `workflow_coherence`, `headless` (pure DSL/KG analysis without a running app). Includes authenticated UX coherence scoring |
| `sentinel` | scan, findings, suppress, status, history | Static failure-mode detection — scans DSL for anti-patterns across dependency integrity, accessibility, mapping track, and boundary layer agents |
| `composition` | audit, capture, analyze, report, bootstrap, inspect_styles | Visual hierarchy audit (5-factor attention model), Playwright screenshot capture, Claude vision evaluation, CSS `getComputedStyle()` inspection |
| `semantics` | extract, validate_events, tenancy, compliance, analytics, extract_guards | Semantic analysis — tenancy isolation, compliance/PII detection, event validation, guard extraction |
| `policy` | analyze, conflicts, coverage, simulate | RBAC policy analysis — find unprotected entities, detect contradictory rules, generate permission matrices, trace rule evaluation |

### 4. Site and Brand

Manage the public-facing site structure, copy, theme, and imagery — all from spec files.

| Tool | Operations | Purpose |
|------|-----------|---------|
| `sitespec` | get, validate, scaffold, coherence, review, get_copy, scaffold_copy, review_copy, get_theme, scaffold_theme, validate_theme, generate_tokens, generate_imagery_prompts | Site structure + copy + theme. `coherence` checks if the site feels like a real website; `generate_tokens` produces design tokens; `generate_imagery_prompts` creates image generation prompts |

### 5. Stakeholder and Ops

Founder-facing health reports, investor pitch decks, user/session management, and workflow orchestration.

| Tool | Operations | Purpose |
|------|-----------|---------|
| `pulse` | run, radar, persona, timeline, decisions | Founder-ready health report with Launch Readiness score, 6-axis radar, blocker list, and decisions needing input. `persona` shows the app through a specific user's eyes |
| `pitch` | scaffold, generate, validate, get, review, update, enrich, init_assets | Investor pitch deck generation from `pitchspec.yaml` + DSL data. Outputs PPTX and narrative formats |
| `user_management` | list, create, get, update, reset_password, deactivate, list_sessions, revoke_session, config | Auth user and session management in SQLite or PostgreSQL |
| `process` | propose, save, list, inspect, list_runs, get_run, diagram, coverage | Workflow orchestration with saga patterns — Mermaid diagrams, run tracking, coverage analysis |

### 6. Knowledge and Meta

Framework knowledge, codebase graph, community contributions, adaptive user profiling, and server diagnostics.

| Tool | Operations | Purpose |
|------|-----------|---------|
| `graph` | query, dependencies, dependents, neighbourhood, paths, stats, populate, concept, inference, related, export, import | Unified knowledge graph — codebase structure, framework concepts, inference patterns, import/export for portability |
| `knowledge` | concept, examples, cli_help, workflow, inference, get_spec | DSL knowledge base and pattern lookup |
| `contribution` | templates, create, validate, examples | Package API packs, UI patterns, bug fixes, DSL patterns, and feature requests for sharing |
| `user_profile` | observe, observe_message, get, reset | Adaptive persona inference — analyzes tool usage and message vocabulary to tailor response detail |
| `status` | mcp, logs, active_project, telemetry | Server diagnostics — module status, log tailing, telemetry with per-tool stats |

### Autonomous Quality Pipeline

`pipeline run` chains 11 deterministic steps (validate, lint, fidelity, composition audit, test/story/process coverage, test design gaps, semantics) with adaptive output — returning compact metrics for clean steps and full detail only where problems exist. Feed the results into `discovery run` to explore as each persona and find gaps the static checks miss. Then `composition report` adds visual analysis: DOM-level hierarchy audit plus Claude vision evaluation of captured screenshots. An agent can audit structure, logic, access control, and visual rendering without human intervention.

### Agent-Friendly Responses

MCP responses are designed for LLM agents to make cost-aware decisions. The `pipeline` tool supports three detail levels (`metrics` at ~1KB, `issues` at ~5-20KB, `full` at ~200KB+) so agents can start cheap and drill down only where needed. Responses include `_meta` blocks with wall time, token usage, and LLM call counts. Expensive operations like `discovery run` and `composition analyze` perform pre-flight health checks before committing resources.

### Claude Code Integration

```bash
# Homebrew: MCP server auto-registered during installation
brew install manwithacat/tap/dazzle

# PyPI: Register manually
pip install dazzle-dsl
dazzle mcp-setup

# Verify
dazzle mcp-check
```

When using Claude Code with a DAZZLE project, ask: "What DAZZLE tools do you have access to?"

See [MCP Server Guide](docs/architecture/mcp-server.md) for details.

---

## Agent Framework

Dazzle includes a mission-driven agent framework that autonomously explores, tests, and analyzes running applications using an **observe -> decide -> act -> record** loop. It supports four discovery modes: **persona** (explore as a specific user role), **entity completeness** (CRUD coverage analysis), **workflow coherence** (process/story integrity), and **headless** (pure DSL/KG analysis without a running app). The agent produces structured observations that feed into a **narrative compiler** (grouping by severity and entity) and a **DSL emitter** (converting proposals into validated DSL code with auto-fix retry).

See [Testing Reference](docs/reference/testing.md) for the full discovery workflow.

---

## Three-Tier Testing

Dazzle generates tests from the DSL at three tiers: **Tier 1 (DSL tests)** — fast HTTP-level API contract tests covering CRUD, state machines, and access control; **Tier 2 (Playwright)** — browser automation for UI rendering, form submission, and visual regression with viewport screenshot baselines; **Tier 3 (Agent)** — LLM-guided end-to-end user journeys that validate behavior against stories. The test design system tracks coverage across entities, personas, and processes, and proposes new tests to fill gaps.

See [Testing Reference](docs/reference/testing.md) for details on all three tiers.

---

## API Packs

Dazzle ships with pre-built integration packs for Stripe, HMRC (6 packs), Xero, Companies House, DocuSeal, SumSub, and Ordnance Survey. Each pack includes authentication configuration, operation definitions, foreign model schemas, and DSL generation templates. Use `api_pack search` to find packs, `api_pack generate_dsl` to generate service and foreign model DSL blocks, and `mock` to test integrations with auto-started mock servers.

See [Integrations Reference](docs/reference/integrations.md) for the full API pack workflow.

---

## Fidelity Scoring

DAZZLE includes a built-in fidelity scorer that measures how accurately rendered HTML reflects the DSL specification. It evaluates four dimensions — structural (35%, field/section/action presence), semantic (30%, input types and required attributes), story (20%, action affordances for user stories), and interaction (15%, search widgets, loading states, empty states). Each gap is categorised by severity and returned with a concrete recommendation.

```bash
dazzle fidelity                  # Score all surfaces
dazzle fidelity --surface orders # Score a single surface
```

---

## Why HTMX, Not React

DAZZLE's frontend is server-rendered HTML using HTMX. This is a deliberate architectural choice, not a limitation.

**React's strengths are for humans.** React's component model is designed around how human developers think: compositional UI building blocks, a rich ecosystem of community packages, and a mental model (declarative state -> view) that maps well to how people reason about interfaces.

**React's weaknesses are for LLM agents.** When the primary author is an LLM coding agent, React's strengths become liabilities:

| Concern | React | HTMX + server templates |
|---------|-------|------------------------|
| **Token cost** | JSX, hooks, state management, bundler config, type definitions — large surface area per feature | HTML fragments returned by the server; minimal client-side code |
| **Build toolchain** | Node, npm/yarn/pnpm, Vite/webpack, TypeScript compiler — each a failure surface the agent must diagnose | Zero build step; three CDN script tags |
| **Implicit context** | Closure scoping, hook ordering rules, render cycle timing — hard for an LLM to hold in context reliably | Explicit: every interaction is an HTTP request with a visible URL and swap target |
| **Ecosystem churn** | Package versions, peer dependency conflicts, breaking changes across React 18/19 — a moving target | HTML is stable; HTMX has had one major version |
| **Debugging** | Stack traces span client bundler, React internals, and async state — requires mental model of the runtime | Server logs show the request; `hx-target` shows where the response goes |
| **Determinism** | Same prompt can produce subtly different hook patterns, each with different edge-case bugs | Server returns HTML; there is one way to render a list |

The server-rendered approach also means the entire UI is visible in the AppSpec IR — DAZZLE can validate, lint, and generate the frontend without executing JavaScript or maintaining a shadow DOM model.

### UI Components

The runtime ships with 10 composable HTMX fragments:

| Fragment | Purpose |
|----------|---------|
| `search_select` | Debounced search with dropdown selection and autofill |
| `search_results` | Result items from search endpoints |
| `search_input` | Search with loading indicator and clear button |
| `table_rows` | Table body with typed cell rendering and row actions |
| `table_pagination` | Page navigation for tables |
| `inline_edit` | Click-to-edit field with Alpine.js + HTMX save |
| `bulk_actions` | Toolbar for bulk update/delete on selected rows |
| `status_badge` | Colored status badge with automatic formatting |
| `form_errors` | Validation error alert |
| `filter_bar` | Dynamic filter controls based on entity schema |

---

## Install

```bash
# Homebrew (macOS/Linux) - MCP server auto-registered
brew install manwithacat/tap/dazzle

# PyPI (import name remains `dazzle`)
pip install dazzle-dsl

```

**Downloads**: [Homebrew Formula](https://github.com/manwithacat/homebrew-tap)

### CLI Commands

```bash
# Run
dazzle serve                     # Start the app (Docker or --local)
dazzle serve --local             # Start without Docker

# Validate
dazzle validate                  # Parse + link + validate
dazzle lint                      # Extended checks

# Build
dazzle build                     # Full build (UI + API + schema)
dazzle build-ui                  # Build UI only
dazzle build-api                 # Build API only

# Specs
dazzle specs openapi             # Generate OpenAPI 3.1 spec
dazzle specs asyncapi            # Generate AsyncAPI 3.0 spec

# Test
dazzle test dsl-run              # Tier 1: API tests
dazzle test playwright           # Tier 2: UI tests
dazzle test agent                # Tier 3: LLM-powered tests

# Info
dazzle info                      # Project information
dazzle status                    # Service status

# Monitor
dazzle workshop                  # Live MCP activity display (progress, timing, errors)
```

---

## IDE Support

Full Language Server Protocol (LSP) implementation with:
- Real-time validation and diagnostics
- Hover documentation
- Go-to-definition
- Auto-completion
- Document symbols

### Quick Start

```bash
# Start the LSP server (editors pipe to this via stdio)
dazzle lsp run

# Verify LSP dependencies are installed
dazzle lsp check

# Get the path to the bundled TextMate grammar (for syntax highlighting)
dazzle lsp grammar-path
```

### Editor Setup

**VS Code** — Add to `.vscode/settings.json`:
```json
{
  "dazzle.lsp.serverCommand": "dazzle lsp run"
}
```
Or use any generic LSP client extension pointing to `dazzle lsp run`.

**Neovim** (nvim-lspconfig):
```lua
require('lspconfig').dazzle.setup {
  cmd = { "dazzle", "lsp", "run" },
  filetypes = { "dsl", "dazzle" },
}
```

**Emacs** (eglot):
```elisp
(add-to-list 'eglot-server-programs '(dazzle-mode . ("dazzle" "lsp" "run")))
```

Works with any editor that supports LSP.

---

## Examples

All examples are in the `examples/` directory:

| Example | Complexity | What it demonstrates |
|---------|-----------|---------------------|
| `simple_task` | Beginner | 3 entities, state machine, personas, workspaces, access control |
| `contact_manager` | Beginner | CRM with relationships and list/detail surfaces |
| `support_tickets` | Intermediate | Ticket lifecycle with state machines and assignments |
| `ops_dashboard` | Intermediate | Workspace stages and aggregate metrics |
| `fieldtest_hub` | Advanced | Full-featured demo with integrations |
| `pra` | Advanced | Performance reference app — 15 DSL files covering every construct: relationships, state machines, invariants, computed fields, processes, messaging, ledgers, streams, services, access control, LLM features |

---

## Project Structure

```
my_project/
├── dazzle.toml              # Project manifest
├── dsl/
│   ├── app.dsl              # App declaration, entities, surfaces
│   ├── workspaces.dsl       # Dashboards and regions
│   ├── services.dsl         # External and domain services
│   ├── processes.dsl        # Multi-step workflows
│   ├── messaging.dsl        # Channels and templates
│   └── ...
├── stubs/                   # Service stub implementations (Python)
├── sitespec.yaml            # Public site structure
├── copy.md                  # Public site content
├── .dazzle/
│   ├── data.db              # SQLite database
│   ├── stories/             # Generated stories
│   ├── processes/           # Generated processes
│   ├── tests/               # Generated test suites
│   └── demo_data/           # Generated seed data
└── build/                   # Generated artifacts (OpenAPI, AsyncAPI)
```

### Codebase Structure (for contributors)

```
src/
├── dazzle/
│   ├── core/                # Parser, IR types, linker, validation
│   │   ├── ir/              # ~45 modules, ~150+ Pydantic IR types
│   │   └── dsl_parser_impl/ # Parser mixins for each construct
│   ├── mcp/                 # MCP server with 24 tool handlers
│   │   ├── server/handlers/ # One handler per tool
│   │   └── knowledge_graph/ # Unified per-project knowledge graph
│   ├── agent/               # Mission-driven agent framework
│   │   ├── missions/        # Persona discovery, entity completeness, workflow coherence, headless
│   │   ├── compiler.py      # Observations → proposals (narrative compiler)
│   │   └── emitter.py       # Proposals → valid DSL (with retry + auto-fix)
│   ├── testing/             # Three-tier test generation and execution
│   ├── specs/               # OpenAPI and AsyncAPI generators
│   ├── api_kb/              # API pack definitions (TOML)
│   └── cli/                 # CLI entry points
├── dazzle_back/             # FastAPI runtime (CRUD, auth, migrations)
└── dazzle_ui/               # HTMX + DaisyUI frontend runtime
    ├── runtime/             # Template renderer, fragment registry
    └── templates/           # Jinja2 templates (layouts, components, fragments, workspace regions)
```

---

## Documentation

**Full documentation**: [manwithacat.github.io/dazzle](https://manwithacat.github.io/dazzle/)

- **[DSL Reference](docs/reference/index.md)** — complete guide to all DSL constructs (entities, surfaces, workspaces, services, processes, ledgers, and more)
- **[Rhythm Guide](docs/guides/rhythms.md)** — understanding longitudinal persona journey evaluation
- **[Getting Started](docs/getting-started/)** — installation, quickstart, first app tutorial
- **[Architecture](docs/architecture/)** — system design, DSL-to-AppSpec pipeline, MCP server internals
- **[Contributing](docs/contributing/)** — development setup, testing guide, adding features
- **[Examples](examples/)** — runnable example applications from beginner to advanced

---

## Contributing

All contributions require AI co-authorship. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT - see [LICENSE](LICENSE)
