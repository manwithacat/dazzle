# DAZZLE

**An agent-native, domain-first SaaS framework.**
**Model your business. Ship your product. Pass your audit.**

<!-- Versions & Compatibility -->
[![Python 3.12 to 3.14](https://img.shields.io/badge/python-3.12_to_3.14-blue)](https://www.python.org/)
[![Homebrew](https://img.shields.io/badge/homebrew-manwithacat%2Ftap-orange)](https://github.com/manwithacat/homebrew-tap)

<!-- Build & Quality -->
[![CI](https://github.com/manwithacat/dazzle/workflows/CI/badge.svg)](https://github.com/manwithacat/dazzle/actions)
[![codecov](https://codecov.io/gh/manwithacat/dazzle/branch/main/graph/badge.svg)](https://codecov.io/gh/manwithacat/dazzle)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-checked-blue.svg)](https://mypy-lang.org/)

<!-- Meta -->
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://manwithacat.github.io/dazzle/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/manwithacat/dazzle.svg?style=social)](https://github.com/manwithacat/dazzle)

Dazzle is an **agent-native SaaS framework** built around domain-first declarations, server-rendered HTML fragments, and explicit HTMX interaction contracts. You describe your business in structured `.dsl` files — entities, roles, rules, workflows, events — and the runtime executes that description directly. There is no code generation step, no scaffold to maintain, and no second source of truth.

It is optimised for applications where **correctness, inspectability, and change locality** matter more than unconstrained client-side composition: domain-heavy SaaS, workflow systems, operational tooling, and governance-heavy products. Rich client behaviour is allowed through **bounded JavaScript islands** with named lifecycle contracts — not a parallel SPA state graph.

The same repository is also a working practice of **epistemic engineering**: deliberately shaping the representations from which human and artificial collaborators reconstruct organisational judgement (see [stems](stems/README.md) below).

```bash
cd examples/simple_task && dazzle serve
# UI:  http://localhost:3000
# API: http://localhost:8000/docs
```

If you are evaluating Dazzle rather than just trying it, start with the
[skeptical evaluator's guide](EVALUATION.md) and the
[security claims inventory](SECURITY_CLAIMS.md). They show the DSL -> IR ->
runtime path, RBAC matrix, runtime verifier, and compliance evidence with
copy-pasteable commands and explicit limits.

---

## The thesis

Modern coding agents can work on many kinds of software — including large client-heavy applications. The durable claim for Dazzle is not that other stacks are incomprehensible. It is that **Dazzle reduces the amount of inference** an agent (or a human reviewer) must perform to understand, modify, and verify a SaaS application.

In a typical client-heavy codebase, behaviour is reconstructed from component trees, hooks, effects, client caches, routers, and build-time transforms. In Dazzle the target path is more direct:

```text
Domain declaration (.dsl)
  → frozen AppSpec IR
  → server-side state
  → rendered HTML fragment
  → HTMX request / response
  → DOM swap
  → CI-verifiable result
```

That path is the product advantage: **make the correct change obvious, local, inspectable, and testable.**

**Semantic compression** — putting application meaning in one inspectable, machine-readable form — is how Dazzle gets there. The DSL is not a shortcut to a generated codebase. It *is* the maintained artefact. API specs, UI surfaces, tests, and compliance evidence are projections of the same IR.

---

## Epistemic engineering and stems

Prompt engineering optimises a single interaction. **Epistemic engineering** optimises the *representational environment* from which many interactions reconstruct understanding. When artificial reasoners join the team, organisational judgement cannot rely only on hallway culture and mentorship — it has to live in **explicit representations** that a competent reasoner can rebuild from.

This repository treats a small set of those representations as first-class:

| Term | Meaning in Dazzle |
|------|-------------------|
| **Stem** | A short conceptual claim from which large bodies of judgement reconstruct (not “more docs”) |
| **Expression** | ADR, code path, test, playbook, or example that *points at* a stem |
| **Agent didactics** | How stems and instructions are sequenced so reconstruction is reliable |
| **Prior correction** | Grammar, agent guidance, and CI gates that pull against corpus defaults (next section) |

**Stems** live in a deliberate hierarchy — different artefact classes have different authority:

| Rank | Location | Role |
|------|----------|------|
| 1 | [`stems/`](stems/INDEX.md) | Framework stems — what must stay true across implementations |
| 2 | [`AGENTS.md`](AGENTS.md) | Always-on didactics and commands |
| 3 | [`docs/adr/`](docs/adr/INDEX.md) | Decision history (expressions of stems) |
| 4 | Package stems (e.g. [`packages/hatchi-maxchi/stems/`](packages/hatchi-maxchi/stems/)) | Design-system / Hyperpart judgement |
| 5 | [`examples/*/stems/`](examples/) | App **domain** stems (framework stems still win on framework questions) |
| 6 | Guides / reference | Mechanics and tutorials |

Agents (and humans onboarding): open [`stems/INDEX.md`](stems/INDEX.md) → the stem that matches the task → `AGENTS.md` commands → local code. Do not treat every Markdown file as equal weight.

Framework stems today include DSL-first, agent-first, hypermedia SSR, the four-layer stack (`http → page → render → core`), authoring boundary, clean breaks, RBAC/scope separation, and [epistemic layout](stems/epistemic-layout.md). HaTchi-MaXchi adds Hyperpart-specific stems (composition, invention ladder, three layers). New example apps scaffold a local `stems/` so domain judgement has a place to live.

Start here: **[stems/README.md](stems/README.md)** · catalogue: **[stems/INDEX.md](stems/INDEX.md)**.

---

## The substrate: three layers of prior correction

The reason the DSL is the codebase, not a generator for it, is downstream of a sharper claim: **Dazzle is a prior-correction substrate for LLM-driven software development.** Training corpora are dominated by popular-but-aging idioms (Rails ActiveRecord, React class components, jQuery-shaped vanilla JS, exception-as-control-flow, polymorphic associations, manual SQL string-building, untyped denormalisation). An LLM trained on that corpus has those shapes as its prior; running it as an agent at scale propagates the corpus mean into the codebase unless something else pulls against it.

The framework's job in the agent-driven era is to be that something. Dazzle implements three stacked layers that each catch what the others miss:

1. **Grammar restriction.** The DSL closes off bad idioms by construction. Untyped polymorphic associations — the Rails `belongs_to … polymorphic: true` shape, `ref X | Y | Z` union sugar, a hidden discriminator — don't exist; the sole exception is a *typed* `poly_ref [A, B]` with a visible discriminator and an exhaustive target list, opened only after a real use case survived a four-question interrogation and still statically scope-validated against the FK graph (ADR-0027 → ADR-0042). Field-level authorization isn't expressible (ADR-0025). Scope rules compile to a formal predicate algebra validated against the FK graph (ADR-0009). Regex in the parser is a smell (ADR-0024) and the allowlist sits at zero. Each closed-off shape is one degree of freedom the corpus prior can no longer exercise.

2. **Inference-time bias correction.** Agent instruction files (`AGENTS.md`), the ADR index (each line a "decision that prevents a wrong proposal"), and the **counter-prior catalogue** at [`docs/counter-priors/`](docs/counter-priors/INDEX.md) are versioned engineering artefacts that name specific corpus pathologies and route the agent toward the right shape. The catalogue is queryable via the MCP server (`knowledge counter_prior query=...`) and is auto-surfaced at the bootstrap step when an agent's spec text contains matching triggers.

3. **Post-hoc filtering.** Drift gates, the conformance engine, the fitness investigator, RBAC matrix verification, and the broader test sweep catch whatever slips past the first two layers. Each gate pins a specific corpus pattern: `test_no_bare_except_pass.py`, `test_no_regex_in_parser.py`, `test_shell_strict_mode.py`, the API surface drift baselines.

The catalogue is itself a deliverable. Each entry — *exceptions-as-control-flow*, *polymorphic associations*, *hand-rolled soft-delete*, *raw SQL string-building*, *shell without strict mode*, and the rest — is a small permanent inoculation against a recurring drift. As LLM-emitted code re-enters training corpora at scale, this counter-biasing grows in value over time: a framework that does this work today is investing in an asset that compounds across model generations.

The broader framing (corpus pathologies, compounding problem, generalised principle) is captured in the catalogue itself. The shortest version: **defer decisions to runtime only when the dynamism is essential to the domain, not merely convenient for the author. Make every other decision as statically as possible, and encode the static decision in the substrate so the LLM cannot accidentally undo it.**

---

## Design principles

Eleven stated positions, defended in the [ADRs](docs/adr/INDEX.md):

1. **The DSL is the source of truth.** API specs, tests, compliance evidence, and runtime behaviour are all derived from the same IR.
2. **No code generation.** The runtime executes the IR directly. No regeneration drift, no generated files to maintain.
3. **Anti-Turing by design.** The DSL has no arbitrary computation. Everything is statically inspectable, lintable, and verifiable.
4. **PostgreSQL only.** One capable relational database plus disciplined semantics beats distributed-systems sprawl for the workloads Dazzle targets.
5. **Server-rendered HTML + HTMX.** The product surface is server-owned HTML and explicit fragment swaps — not an SPA client state graph. No frontend build toolchain for the default path. Bounded **JavaScript islands** are fine when they have a named purpose and lifecycle contract (HaTchi-MaXchi Hyperparts).
6. **Fragments as the only escape hatch.** When the DSL can't express it, you reach for a *fragment* — a constrained, named, semantically-tagged piece of custom rendering. Not arbitrary frontend.
7. **Append-oriented history.** Events, decisions, and grants are logged. Auditors don't need to spelunk; the trail is part of the substrate.
8. **Provable RBAC (scoped, honestly).** Scope rules compile to a formal predicate algebra, statically validated against the FK graph; their meta-properties (least-privilege containment, deny-overrides precedence, …) are mechanically proved over the DSL by an SMT solver — `dazzle rbac prove`. The proof is of a *model* of the policy over a stated trust boundary (PostgreSQL, auth, the single query path are *trusted, not proven*); runtime conformance is *verified by test*, and grants you mint outside the declared classes fall outside the proof. The tool says which — `PROVED` / `VACUOUS` / `INFORMATIONAL` / `FAILED` — rather than a blanket green.
9. **No hidden singletons.** Dependencies are explicit (`RuntimeServices`, `ServerState`) — readable by both humans and agents.
10. **No backwards-compat shims.** Pre-1.0, clean breaks beat layered workarounds. Callers are updated in the same commit.
11. **Bump on every fix.** Every push gets a unique semantic version — deployment traceability over release ceremony.

If you disagree with one of these, you'll probably disagree with the rest. That's the point of stating them up front.

---

## Why Dazzle

### Your business model IS the application

Most frameworks ask you to express your business logic across scattered files — controllers, models, migrations, middleware, templates. When requirements change, you update all of them and hope they stay in sync.

Dazzle inverts this. You write what your business *is* — entities, roles, permissions, workflows, state machines — and the runtime executes it directly. Change the DSL, refresh the browser. The DSL is the single source of truth for your application, your API spec, your test suite, and your compliance documentation.

### Built for the compliance conversation

If you're building SaaS — especially in regulated industries — you will face auditors. They will ask: *who can access what? how are changes controlled? where is sensitive data classified?*

Most teams answer these questions retroactively, combing through code to produce evidence. Dazzle derives the answers from the DSL itself:

- **Access control** is declared in the DSL. The permission matrix is *derived* from it (not hand-maintained); its meta-properties — least-privilege containment, deny-overrides precedence, no dead-rule scopes — are *mechanically proved* over the DSL model (`dazzle rbac prove`); and runtime enforcement is *conformance-verified* against that matrix by empirical probe (`dazzle rbac verify`), **not** proved. The proof's scope, trust boundary (PostgreSQL/auth are trusted), and the out-of-scope case (grants minted outside the declared classes) are stated explicitly, the way an auditor expects.
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

That's a todo app. The same language scales to 39-entity accountancy platforms with double-entry ledgers, multi-step onboarding wizards, and role-based dashboards. You add complexity only where your business needs it.

---

## What you can model

| Capability | What it does | Why it matters |
|-----------|-------------|---------------|
| **Entities** | Data models with types, constraints, relationships | Your domain model, declared once |
| **Surfaces** | List, detail, create, review views | UI and API from the same declaration |
| **Workspaces** | Role-based dashboards with filtered regions | Each persona sees what they need |
| **State Machines** | Lifecycle transitions with guards and approval | Business processes enforced, not just documented |
| **Access Control** | Cedar-style permit/forbid rules, scope predicates | RBAC meta-properties machine-proved over the DSL (scoped); runtime verified by probe |
| **Grant Schemas** | Delegated, time-bounded access with approval | Four-eyes authorization, SOC 2-ready |
| **Processes** | Multi-step workflows with saga patterns | Durable business operations |
| **Atomic Transactions** | Multi-entity writes in one scope-guarded transaction (`atomic`) | No partial writes; every touched entity scope-checked, fail-closed (ADR-0029) |
| **Experiences** | Onboarding wizards, checkout flows | Guided multi-step user journeys |
| **Ledgers** | TigerBeetle-backed double-entry accounting | Financial-grade transaction integrity |
| **Graphs** | Entity relationships with CTE traversal and algorithms | Network analysis, shortest paths, community detection |
| **HLESS Events** | Intent/Fact/Observation/Derivation event semantics | Replay correctness, audit lineage, no "events as a vague bucket" |
| **Fragments** | Constrained custom rendering inside generated surfaces | Differentiated UX without losing semantic integrity |
| **Islands** | Self-contained interactive JS components mounted into server-rendered pages | Charts, editors, drag-and-drop without adopting an SPA framework |
| **Integrations** | Declarative API bindings with triggers and mappings | Connect to Stripe, HMRC, Xero, and more |
| **LLM Jobs** | Classification, extraction, generation tasks | AI capabilities without prompt engineering sprawl |
| **Services** | Custom business logic declared in DSL, implemented in typed Python/TS stubs | A bounded escape hatch for domain logic that keeps the declarative boundary |
| **Compliance** | Maps DSL constructs to ISO 27001 and SOC 2 controls | Control-coverage evidence, gaps flagged |

For the full DSL reference, see [docs/reference/index.md](docs/reference/index.md).

### Vocabulary glossary

A few Dazzle keywords don't map one-to-one onto industry terms. If you're skim-reading the DSL for the first time:

| Dazzle term | What other communities call this |
|-------------|----------------------------------|
| **surface** | view, page, screen — a UI/API endpoint with one entity and one mode |
| **workspace** | dashboard, role home, console |
| **experience** | wizard, flow, multi-step form |
| **rhythm** | recurring cadence, scheduled review, periodic ritual |
| **archetype** | persona pattern, role family |
| **hless** | event-stream semantics (HLESS = High-Level Event Semantics Specification — [why this name](docs/architecture/hless-deep-dive.md)) |
| **fragment** | escape-hatch component, custom partial |

---

## Compliance and security

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

Scope rules compile to a formal predicate algebra, statically validated against the FK graph at `dazzle validate` time. Each layer below carries an explicit **evidence class** — *enumeration*, *proof*, or *test* — so the word "provable" never outruns what is actually discharged:

| Layer | What it establishes | Evidence class |
|-------|---------------------|----------------|
| **Static Matrix** | Every (role, entity, operation) decision is derived from the DSL | Enumeration |
| **Meta-property proof** | Least-privilege containment, deny-overrides precedence, scope satisfiability / no-dead-rule, role-hierarchy acyclicity, separation-of-duty — discharged over the DSL by an SMT solver (Z3), with a counter-model on any violation | **Proof** |
| **Dynamic Verification** | The running app is probed as every role to confirm runtime HTTP behaviour matches the matrix | Test |
| **Decision Audit Trail** | Every access decision is logged with the matched rule and outcome | Test |

```bash
dazzle rbac matrix    # Derive the access matrix from the DSL (no server needed)
dazzle rbac prove     # Prove the meta-properties over the DSL; counter-model on violation
dazzle rbac verify    # Probe the running app per role vs the matrix (needs PostgreSQL)
dazzle rbac report    # Compliance report for auditors (--lint guards the copy)
```

The prover reports an honest verdict per obligation, not a blanket green — `PROVED` (discharged), `VACUOUS` (the construct isn't used in this app, so there's nothing to prove), `INFORMATIONAL` (proved, but partly over over-approximated nodes — see below), or `FAILED` (counter-model emitted). An app with no role hierarchy gets `VACUOUS role_hierarchy_acyclic`, not a misleading "proved".

**What is proof, and what is not — stated plainly.** The proof is *scoped*: it discharges theorems about a **model** of the policy (the scope-predicate algebra), over the static core (tenant ∧ role ∧ scope), modulo a named trust boundary — PostgreSQL's RLS engine, the connection factory, and authentication are *trusted, not proven*. Two links in the chain are deliberately **not** proof and are stated as such:

- **Model ↔ emitted SQL.** That the proved IR model faithfully matches the SQL PostgreSQL actually runs is closed by *test* (the runtime verifier today; a formal conformance oracle is on the roadmap), not by the solver.
- **Over-approximation.** `EXISTS` junctions and multi-hop FK paths are abstracted to free symbols — sound for the "who could access" (no-escalation) reading, but the prover prints exactly which obligations leaned on those abstractions so you can see the residual.

**When you mint your own grants.** The "who could access" upper-bound reading is proven only over **DSL-declared grant classes** (`grant_schema`). Grants minted by your own application code *outside* the declared classes are fully supported at runtime but are **not** covered by the proof — `dazzle rbac report` labels such an app with a residual-risk note, and its claim degrades from "proven upper bound" to "upper bound over declared classes". That boundary is stated, not buried: see the [RBAC Proof Model & Trust Boundary](docs/reference/rbac-proof-model.md), plus [RBAC Verification](docs/reference/rbac-verification.md) and [Compliance](docs/reference/compliance.md).

### Enterprise authentication & identity (opt-in)

For apps that need it, Dazzle ships native, per-organization enterprise identity — **OIDC, SAML 2.0, and SCIM provisioning** — so a customer's IdP (Okta, Microsoft Entra ID, Google, Ping) drives sign-in and user lifecycle. Connections are framework-owned runtime data (not DSL), fenced to one org, and gated by **DNS-verified domain ownership**; secret material is AES-256-GCM encrypted at rest. SAML covers IdP-metadata import, SP-signed AuthnRequests, encrypted assertions, and bidirectional Single Logout; SCIM covers user/group provisioning with group→role mapping.

It is **off by default** — a greenfield app sees none of it until you opt in (`dazzle capability enable auth.enterprise.oidc`), so the simple path stays simple. Identity is modelled as **global Identity + Organization + fenced Membership + Session**, so one person can belong to many orgs with tenant isolation enforced at the data layer, not bolted on.

See **[Enterprise SSO & Provisioning](docs/reference/enterprise-sso.md)** and [multi-tenant hosting](docs/reference/tenant-hosts.md).

---

## What Dazzle is *not* for

Stating this directly because it matters:

- **Real-time collaborative editing.** No CRDT layer, no client-state model.
- **Graphics-heavy or canvas-based interfaces.** Server-rendered HTML is not the right substrate.
- **Local-first or offline-first applications.** Authority lives on the server and in PostgreSQL.
- **General-purpose programming.** The DSL is deliberately not Turing-complete. If you need arbitrary computation, you need a different tool — or you write a fragment.
- **Replacing your existing codebase wholesale.** Dazzle is most useful for new applications where governance, workflow, and audit are first-class concerns from day one.

The framework is strongest for **enterprise SaaS, workflow systems, operational tooling, and governance-heavy applications.** That's the bet.

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

**Supported runtime:** Python **3.12 – 3.14** · PostgreSQL · macOS / Linux. The floor is **3.12**; CI runs the full suite on **3.12, 3.13, and 3.14** (all hard-required) on every change, and **3.14 is the primary deploy target** (Heroku's default; faster on the parse path via the uv tail-call interpreter — see [`docs/python-3.14-primary-target.md`](docs/python-3.14-primary-target.md)). Development and deploys use **uv** (`uv sync`; Heroku via the native uv buildpack).

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

The frontend uses server-rendered HTML with HTMX — zero default build toolchain, stable technology, and full visibility into what the runtime produces. Generated HTML is a first-class, testable artefact, not an opaque side effect of a client bundle. Every built-in display mode — lists, kanban, charts, pivots, funnels, metrics, and more — is rendered with sample data, live previews, and its source DSL in the **[UX Catalogue](https://manwithacat.github.io/dazzle/reference/ux-catalogue/)**. For UX that the generated surfaces can't express, **fragments** and bounded **islands** provide constrained escape hatches that stay connected to the entity and surface graph.

For the full architecture, see [docs/architecture/overview.md](docs/architecture/overview.md). For the event-semantics rationale, see [docs/architecture/hless-deep-dive.md](docs/architecture/hless-deep-dive.md).

---

## AI-assisted development

Dazzle ships as both a runtime and an AI development environment. The intent is not “better prompts for the same scattered architecture,” but a **smaller surface to inspect, modify, and verify**: domain model in `.dsl`, rendered HTML as a first-class artefact, HTMX contracts on the wire, stems for judgement reconstruction, and CI gates for drift.

**Before inventing structure**, agents should reconstruct from the epistemic hierarchy: [`stems/INDEX.md`](stems/INDEX.md) → matching stem → [`AGENTS.md`](AGENTS.md) → local code. Package work (e.g. HaTchi-MaXchi) also reads that package’s `stems/` and agent curriculum.

When used with Claude Code (via MCP), you get access to a growing set of tools that span the full lifecycle. The exact tool count, operations, and parameters drift with development — see the [MCP Tool Inventory](docs/reference/mcp-tools.md) for the live list, regenerated from the registry every build. As of the latest doc regen: **34 tools, 156 operations**. Broad lifecycle coverage:

| Stage | What the tools do |
|-------|------------------|
| **Spec to DSL** | Turn a natural-language idea into validated DSL — entity discovery, lifecycle identification, persona extraction |
| **Test and Verify** | Generate stories, design tests, execute at three tiers (API, browser, LLM-guided), seed demo data |
| **Analyze and Audit** | Quality pipeline, agent-powered gap discovery, visual composition analysis, RBAC policy verification |
| **Site and Brand** | Manage public site structure, copy, theme, and design tokens from spec files |
| **Stakeholder Ops** | Launch readiness scores, investor pitch generation, user/session management |

The agent framework uses an **observe-decide-act-record** loop to autonomously explore running applications, discover gaps, and propose DSL fixes. Discovery modes include persona-based exploration, CRUD completeness analysis, workflow coherence checks, and headless DSL/KG analysis.

For the live tool-by-tool inventory (operations, parameters, descriptions), see the [MCP Tool Inventory](docs/reference/mcp-tools.md) — generated from the registry every doc build. For the architectural model, see [Architecture: MCP Server](docs/architecture/mcp-server.md). For how the autonomous slash-command harness drives day-to-day development on the framework itself, see [Autonomous Harness](docs/autonomous-harness.md).

### Claude Code integration

```bash
# Homebrew: MCP server auto-registered during installation
brew install manwithacat/tap/dazzle

# PyPI: Register manually
pip install dazzle-dsl
dazzle mcp setup

# Verify
dazzle mcp check
```

---

## Examples

| Example | Complexity | What it demonstrates |
|---------|-----------|---------------------|
| `simple_task` | Beginner | 3 entities, state machine, personas, job workspaces (metrics + queues) |
| `contact_manager` | Beginner | CRM dual-pane + favourites queues, not list-only home |
| `support_tickets` | Intermediate | Ticket lifecycle; agent queue / manager ops / customer cases |
| `ops_dashboard` | Intermediate | Command-centre stages: metrics, ack queue, status_list, charts |
| `fieldtest_hub` | Advanced | Fleet metrics + triage/device attention queues; multi-entity density |
| `invoice_ops` | Advanced | Approval / pay / dispute queues + four-eyes approvals |

A curated ladder — the full set (12 apps) lives in [`examples/`](examples/). Prefer **story → persona → workspace Hyperparts** over entity CRUD lists: [`docs/guides/story-to-composition.md`](docs/guides/story-to-composition.md).

---

## IDE support

Full LSP implementation: real-time diagnostics, hover docs, go-to-definition, auto-completion, document symbols.

```bash
dazzle lsp run           # Start the LSP server
dazzle lsp check         # Verify dependencies
dazzle lsp grammar-path  # TextMate grammar for syntax highlighting
```

Works with VS Code, Neovim, Emacs, and any editor supporting LSP. See [docs/reference/index.md](docs/reference/index.md) for editor setup.

---

## Documentation

### Epistemic layout (start here if you write with agents)

- **[Framework stems](stems/README.md)** — compressed organisational judgement; catalogue in [`stems/INDEX.md`](stems/INDEX.md)
- **[AGENTS.md](AGENTS.md)** — always-on agent curriculum and commands (reconstruct stems first)
- **[HaTchi-MaXchi stems](packages/hatchi-maxchi/stems/)** — Hyperpart / design-system stems
- **[Counter-prior catalogue](docs/counter-priors/INDEX.md)** — named corpus pathologies and the preferred shape
- **[ADRs](docs/adr/INDEX.md)** — decision history (expressions of stems)

### Product and evaluation

- **[Evaluating Dazzle](EVALUATION.md)** — skeptical-evaluator walkthrough: see the claims demonstrated in ~30 min
- **[Security & Compliance Claims](SECURITY_CLAIMS.md)** — claim-by-claim inventory: status, enforcement, tests, known gaps
- **[Agent Workflow Guide](docs/guides/agent-workflow.md)** — end-to-end AI-agent spec-edit loop: spec change → DSL edit → validate → tests → human review → deploy
- **[DSL Reference](docs/reference/index.md)** — complete guide to all DSL constructs
- **[UX Catalogue](https://manwithacat.github.io/dazzle/reference/ux-catalogue/)** — every built-in display mode rendered with sample data, live previews, and source DSL
- **[HLESS deep dive](docs/architecture/hless-deep-dive.md)** — event semantics and why they're named this way
- **[Graphs](docs/reference/graphs.md)** — entity graph relationships, CTE traversal, algorithms
- **[Compliance](docs/reference/compliance.md)** — ISO 27001 + SOC 2 evidence pipeline
- **[RBAC Verification](docs/reference/rbac-verification.md)** — provable access control
- **[Enterprise SSO & Provisioning](docs/reference/enterprise-sso.md)** — per-org OIDC / SAML 2.0 / SCIM (opt-in)
- **[Autonomous Harness](docs/autonomous-harness.md)** — Claude Code slash commands + methodology
- **[Research notes](docs/research/INDEX.md)** — reproducible empirical investigations (agent-era counter-priors, predicting task context from a code graph)
- **[Architecture](docs/architecture/)** — system design, pipeline, MCP server
- **[Getting Started](docs/getting-started/)** — installation, quickstart, first app
- **[Examples](examples/)** — runnable example applications (each may carry `examples/<app>/stems/`)
- **[Fixtures](fixtures/)** — framework-validation probes (`shapes_validation` for RBAC, `asset_registry` for `subtype_of:` TPT inheritance, `pra` for full parser/construct conformance, `component_showcase` for the UX catalogue)

---

## About this project

Dazzle is an agent-native framework and a research project in how application substrates and **representational infrastructure** should look when AI collaborators are first-class readers and writers. The north star is simple: make the correct change **obvious, local, inspectable, and testable** — for humans and for agents that improve over time.

It is developed in the open, primarily by a single author, with heavy AI assistance — both in the framework itself and in the example apps built on top of it. Release cadence is high (every fix gets a unique version for deployment traceability) and pre-1.0 breaks are intentional rather than apologetic. If you're evaluating Dazzle for production use, talk to us first.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE)
