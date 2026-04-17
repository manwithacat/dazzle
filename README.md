# DAZZLE

**Model your business. Ship your product. Pass your audit.**

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

Dazzle is a declarative framework for building SaaS applications. You describe your business — its data, its users, its rules, its workflows — in structured `.dsl` files. Dazzle gives you a working web application with a database, API, UI, authentication, role-based access control, and compliance evidence. No code generation, no build step, no scaffold to maintain.

```bash
cd examples/simple_task && dazzle serve
# UI:  http://localhost:3000
# API: http://localhost:8000/docs
```

---

## Why Dazzle

### Your business model IS the application

Most frameworks ask you to express your business logic across scattered files — controllers, models, migrations, middleware, templates. When requirements change, you update all of them and hope they stay in sync.

Dazzle inverts this. You write what your business *is* — entities, roles, permissions, workflows, state machines — and the runtime executes it directly. Change the DSL, refresh the browser. The DSL is the single source of truth for your application, your API spec, your test suite, and your compliance documentation.

### Built for the compliance conversation

If you're building SaaS — especially in regulated industries — you will face auditors. They will ask: *who can access what? how are changes controlled? where is sensitive data classified?*

Most teams answer these questions retroactively, combing through code to produce evidence. Dazzle answers them by construction:

- **Access control** is declared in the DSL and provably enforced. Every permission is statically verifiable.
- **State machines** model approval workflows, transitions, and four-eyes authorization.
- **Compliance evidence** is extracted automatically. Run `dazzle compliance compile --framework soc2` and get a structured audit report showing which controls your DSL satisfies.
- **Grant-based RBAC** supports delegated, time-bounded access with approval workflows — the kind of access governance auditors want to see.

Dazzle currently supports **ISO 27001** and **SOC 2 Trust Services Criteria** out of the box, with automatic evidence mapping from your DSL declarations to specific framework controls.

### From idea to running product, fast

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

Save this as `app.dsl`, run `dazzle serve`, and you have:
- A PostgreSQL-backed database with correct types and constraints
- CRUD API endpoints with pagination, filtering, and sorting
- A rendered list UI with sortable columns, search, and a create form
- OpenAPI documentation at `/docs`
- A health endpoint with deployment integrity verification

That's a todo app. But the same language scales to 39-entity accountancy platforms with double-entry ledgers, multi-step onboarding wizards, and role-based dashboards. You add complexity only where your business needs it.

---

## What You Can Model

| Capability | What it does | Why it matters |
|-----------|-------------|---------------|
| **Entities** | Data models with types, constraints, relationships | Your domain model, declared once |
| **Surfaces** | List, detail, create, review views | UI and API from the same declaration |
| **Workspaces** | Role-based dashboards with filtered regions | Each persona sees what they need |
| **State Machines** | Lifecycle transitions with guards and approval | Business processes enforced, not just documented |
| **Access Control** | Cedar-style permit/forbid rules, scope predicates | Provable RBAC — auditors can verify mechanically |
| **Grant Schemas** | Delegated, time-bounded access with approval | Four-eyes authorization, SOC 2-ready |
| **Processes** | Multi-step workflows with saga patterns | Durable business operations |
| **Experiences** | Onboarding wizards, checkout flows | Guided multi-step user journeys |
| **Ledgers** | TigerBeetle-backed double-entry accounting | Financial-grade transaction integrity |
| **Graphs** | Entity relationships with CTE traversal and algorithms | Network analysis, shortest paths, community detection |
| **Integrations** | Declarative API bindings with triggers and mappings | Connect to Stripe, HMRC, Xero, and more |
| **LLM Jobs** | Classification, extraction, generation tasks | AI capabilities without prompt engineering sprawl |
| **Compliance** | Automated evidence extraction for ISO 27001 and SOC 2 | Audit-ready from day one |

For the full DSL reference, see [docs/reference/index.md](docs/reference/index.md).

---

## Compliance and Security

Dazzle treats compliance as a first-class concern, not an afterthought.

### Automated evidence extraction

Every DSL construct that relates to security — access rules, data classification, state machine transitions, process workflows — is automatically mapped to compliance framework controls. Run:

```bash
dazzle compliance compile --framework iso27001   # ISO 27001 audit
dazzle compliance compile --framework soc2       # SOC 2 TSC audit
dazzle compliance gaps --framework soc2          # Show unmet controls
```

The output is a structured `AuditSpec` showing which controls are **evidenced** (your DSL satisfies them), which are **gaps** (your DSL should cover them but doesn't), and which are **excluded** (physical security, HR — outside DSL scope).

### Provable access control

Scope rules compile to a formal predicate algebra, statically validated against the FK graph at `dazzle validate` time. The verification framework has three layers:

| Layer | What it proves |
|-------|---------------|
| **Static Matrix** | Every (role, entity, operation) combination is computed from the DSL |
| **Dynamic Verification** | The running app is probed as every role to confirm runtime matches the matrix |
| **Decision Audit Trail** | Every access decision is logged with the matched rule and outcome |

```bash
dazzle rbac matrix    # Generate the access matrix (no server needed)
dazzle rbac verify    # Verify runtime matches the matrix (CI gate)
dazzle rbac report    # Compliance report for auditors
```

See [RBAC Verification](docs/reference/rbac-verification.md) and [Compliance](docs/reference/compliance.md) for details.

---

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

---

## AI-Assisted Development

Dazzle ships as both a runtime and an AI development environment. When used with Claude Code (via MCP), you get access to **26 tools with 170+ operations** that span the full lifecycle:

| Stage | What the tools do |
|-------|------------------|
| **Spec to DSL** | Turn a natural-language idea into validated DSL — entity discovery, lifecycle identification, persona extraction |
| **Test and Verify** | Generate stories, design tests, execute at three tiers (API, browser, LLM-guided), seed demo data |
| **Analyze and Audit** | Quality pipeline, agent-powered gap discovery, visual composition analysis, RBAC policy verification |
| **Site and Brand** | Manage public site structure, copy, theme, and design tokens from spec files |
| **Stakeholder Ops** | Launch readiness scores, investor pitch generation, user/session management |

The agent framework uses an **observe-decide-act-record** loop to autonomously explore running applications, discover gaps, and propose DSL fixes. Discovery modes include persona-based exploration, CRUD completeness analysis, workflow coherence checks, and headless DSL/KG analysis.

For the full MCP tool reference, see [Architecture: MCP Server](docs/architecture/mcp-server.md).

### Claude Code Integration

```bash
# Homebrew: MCP server auto-registered during installation
brew install manwithacat/tap/dazzle

# PyPI: Register manually
pip install dazzle-dsl
dazzle mcp setup

# Verify
dazzle mcp check
```

### Autonomous development harness

Dazzle ships a set of Claude Code slash commands that, together, form an
autonomous harness: point Claude Code at the repo, invoke a command
(often inside a `/loop`), and it iterates until there's nothing left to
do. Most cycles take ~15 minutes; a weekend-long run produces a tree of
small, reviewable commits rather than one giant patch.

The common entry points:

| Command | What it does | Typical invocation |
|---------|-------------|--------------------|
| `/improve` | Fix the next lint/validate/fidelity/conformance gap in an example app. Falls through to `/issues` when the backlog is clean. | `/loop 15m /improve` |
| `/issues` | Triage, investigate, implement, ship, and close open GitHub issues. Parallel subagents per issue. | `/issues` |
| `/ux-cycle` | One UX component per cycle through ux-architect governance + agent QA. | `/loop 30m /ux-cycle` |
| `/ux-converge` | Drive DSL-driven UX contract failures to zero against a running app. | `/ux-converge` |
| `/check` | Parallel lint + mypy + tests on modified files. Read-only quality gate. | `/check` |
| `/smells` | Parallel code-smell analysis across four categories. Writes `agent/smells-report.md`. | `/smells` |
| `/xproject` | Cross-project quality scan across every sibling app that uses Dazzle. | `/xproject` |
| `/cimonitor` | CI badge watchdog. Fetches logs for failed jobs and categorises the failure. | `/cimonitor` |
| `/bump [major/minor/patch]` | Semantic version bump, CHANGELOG roll, no tag yet. | `/bump patch` |
| `/ship` | Commit + push gate: ruff, mypy, tag-if-version-bumped, push. | `/ship` |
| `/docs-update [since]` | Scan recently-closed issues and propose doc edits. | `/docs-update v0.57.0` |

Productive loops persist state in `dev_docs/` (gitignored). `/improve` and
`/ux-cycle` commit every green cycle but never push — pushes are always
explicit via `/ship` or `/issues`, which keeps long autonomous runs
recoverable with a single `git reset`.

For the methodology, termination conditions, and state-file conventions
behind these commands, see [**docs/autonomous-harness.md**](docs/autonomous-harness.md).

---

## Architecture

```
DSL Files  →  Parser + Linker  →  AppSpec (IR)  →  Runtime (live app)
                                                 →  OpenAPI / AsyncAPI specs
                                                 →  Test generation
                                                 →  Compliance evidence
                                                 →  Fidelity scoring
```

The DSL is parsed into a typed intermediate representation (AppSpec IR). The runtime executes the IR directly — no code generation step. Every artifact (API specs, tests, compliance reports, demo data) is computed from the same IR.

This architecture is deliberately **anti-Turing**: the DSL has no arbitrary computation, which means Dazzle can statically validate, lint, measure fidelity, and reason about your application. What you declare is what runs.

The frontend uses server-rendered HTML with HTMX — zero build toolchain, stable technology, and full visibility into what the runtime produces.

For the full architecture, see [docs/architecture/overview.md](docs/architecture/overview.md).

---

## Examples

| Example | Complexity | What it demonstrates |
|---------|-----------|---------------------|
| `simple_task` | Beginner | 3 entities, state machine, personas, workspaces, access control |
| `contact_manager` | Beginner | CRM with relationships and list/detail surfaces |
| `support_tickets` | Intermediate | Ticket lifecycle with state machines and assignments |
| `ops_dashboard` | Intermediate | Workspace stages and aggregate metrics |
| `fieldtest_hub` | Advanced | Full-featured demo with integrations |
| `pra` | Advanced | 15 DSL files covering every construct: ledgers, processes, LLM, services |

---

## IDE Support

Full LSP implementation: real-time diagnostics, hover docs, go-to-definition, auto-completion, document symbols.

```bash
dazzle lsp run           # Start the LSP server
dazzle lsp check         # Verify dependencies
dazzle lsp grammar-path  # TextMate grammar for syntax highlighting
```

Works with VS Code, Neovim, Emacs, and any editor supporting LSP. See [docs/reference/index.md](docs/reference/index.md) for editor setup.

---

## Documentation

- **[DSL Reference](docs/reference/index.md)** — complete guide to all DSL constructs
- **[Graphs](docs/reference/graphs.md)** — entity graph relationships, CTE traversal, algorithms
- **[Compliance](docs/reference/compliance.md)** — ISO 27001 + SOC 2 evidence pipeline
- **[RBAC Verification](docs/reference/rbac-verification.md)** — provable access control
- **[Autonomous Harness](docs/autonomous-harness.md)** — Claude Code slash commands + methodology
- **[Architecture](docs/architecture/)** — system design, pipeline, MCP server
- **[Getting Started](docs/getting-started/)** — installation, quickstart, first app
- **[Examples](examples/)** — runnable example applications

---

## Contributing

All contributions require AI co-authorship. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT - see [LICENSE](LICENSE)
