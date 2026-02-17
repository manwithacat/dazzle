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
- [How Dazzle Works: The Eight Layers](#how-dazzle-works-the-eight-layers)
  - [Layer 1: Entities](#layer-1-entities-your-data-model)
  - [Layer 2: Surfaces](#layer-2-surfaces-your-ui)
  - [Layer 3: Workspaces](#layer-3-workspaces-your-dashboards)
  - [Layer 4: Stories and Processes](#layer-4-stories-and-processes-your-business-logic)
  - [Layer 5: Services](#layer-5-services-your-custom-code)
  - [Layer 6: The Public Site](#layer-6-the-public-site)
  - [Layer 7: Experiences](#layer-7-experiences-multi-step-user-flows)
  - [Layer 8: Islands](#layer-8-islands-client-side-interactivity)
- [How the Layers Work Together](#how-the-layers-work-together)
- [The Pipeline: Determinism and Cognition](#the-pipeline-determinism-and-cognition)
- [DSL Constructs Reference](#dsl-constructs-reference)
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

## How Dazzle Works: The Eight Layers

Dazzle has eight conceptual layers, each handling a different concern. Understanding these layers — and knowing which one is responsible for what — is the key to working effectively with the system.

### Layer 1: Entities (Your Data Model)

An entity is a business concept expressed as structured data. Think of it as a database table, but described at the semantic level rather than the SQL level.

```dsl
entity Company "Company":
  id: uuid pk
  company_name: str required
  company_number: str required unique
  is_vat_registered: bool = false
  trading_status: enum[active, dormant, struck_off] = active
  vat_number: str
  created_at: datetime auto_add
  updated_at: datetime auto_update
```

What Dazzle does with this:
- Creates a database table with correct column types
- Enforces `required` and `unique` constraints
- Sets default values (e.g., `is_vat_registered = false`, `trading_status = active`)
- Generates `auto_add` timestamps on creation and `auto_update` on every save
- Builds a repository with CRUD operations (create, read, update, delete, list with pagination)

**This is critical to understand:** When your entity says `trading_status: enum[...] = active`, every new Company record gets `trading_status = active` automatically. No process needs to "set" it. No service needs to assign it. The entity layer handles it at creation time.

#### State Machines

Entities can declare allowed transitions between enum values:

```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[todo, in_progress, review, done] = todo
  assigned_to: ref User

  transitions:
    todo -> in_progress
    in_progress -> review
    review -> done
    review -> in_progress
    done -> todo: role(admin)
```

This means you cannot set `status` to `done` without going through `review` first, and you cannot reopen a `done` task unless you have the admin role. The entity layer enforces this at the API boundary — no process or service code needed.

State machines also support auto-transitions with time delays:

```dsl
  transitions:
    pending -> expired: auto after 30 days
    pending -> active: requires payment_confirmed
```

#### Relationships

Entities link to each other with typed relationships:

```dsl
entity OrderItem "Order Item":
  id: uuid pk
  order: ref Order                         # Foreign key
  product: ref Product
  quantity: int required

entity Order "Order":
  id: uuid pk
  customer: ref Customer
  items: has_many OrderItem cascade         # Delete items when order deleted
  shipping_address: embeds Address          # Embedded value object
  invoice: has_one Invoice restrict         # Prevent delete if invoice exists
```

**Relationship types:** `ref` (foreign key), `has_many` (one-to-many with ownership), `has_one` (one-to-one), `belongs_to` (inverse FK), `embeds` (embedded value type)

**Delete behaviors:** `cascade` (delete children), `restrict` (prevent delete), `nullify` (set FK to null), `readonly` (immutable relationship)

#### Invariants

Cross-field business rules that the entity layer enforces:

```dsl
entity Task "Task":
  ...
  invariants:
    urgent_needs_date: "Urgent tasks must have a due date"
      when priority = "urgent" then due_date is not null
      error_code: TASK_URGENT_NO_DATE
```

#### Archetypes

Reusable field templates that entities can inherit:

```dsl
archetype Timestamped:
  created_at: datetime auto_add
  updated_at: datetime auto_update

archetype Auditable extends Timestamped:
  created_by: ref User
  updated_by: ref User

entity Invoice "Invoice":
  extends Auditable
  ...
```

#### Sensitive Fields

Fields containing PII or credentials can be marked `sensitive` for automatic masking and compliance:

```dsl
entity Employee "Employee":
  id: uuid pk
  name: str(200) required
  bank_account: str(8) sensitive
  ni_number: str(9) required sensitive
```

This modifier:
- **Masks values in list views** — displays `****1234` (last 4 characters visible)
- **Excludes from filters** — sensitive fields cannot be used as filter criteria
- **Marks in OpenAPI** — adds `x-sensitive: true` extension to the schema
- **Flags in entity schema** — available for compliance scanning and audit tooling

#### Semantic Metadata

Entities carry metadata that helps both LLMs and Dazzle's tooling understand intent:

```dsl
entity CustomerDueDiligence "Customer Due Diligence":
  intent: "Track KYC/AML verification status for regulatory compliance"
  domain: compliance
  patterns: lifecycle, audit, searchable
  ...
```

### Layer 2: Surfaces (Your UI)

A surface defines how users see and interact with entity data. It maps fields to screens.

```dsl
surface company_list "Companies":
  uses entity Company
  mode: list

  section main:
    field company_name "Name"
    field trading_status "Status"
    field is_vat_registered "VAT Registered"

  ux:
    purpose: "Browse and manage client companies"
    sort: company_name asc
    filter: trading_status, is_vat_registered
    search: company_name, company_number
    empty: "No companies yet. Add your first client!"
```

What Dazzle does with this:
- Registers an HTTP route (`/companies`)
- Renders a DataTable with sortable column headers, filter dropdowns, debounced search, and pagination
- Generates create, edit, detail, and delete surfaces from the same entity
- All interaction is server-rendered HTML with HTMX for partial updates — no JavaScript framework required

The `ux:` block is the semantic layer. It tells Dazzle *what interactive features this table needs*, and the runtime translates that into clickable sort arrows, `<select>` filter dropdowns, and a search input with 300ms debounce.

**Surface modes:** `list` (data table), `view` (detail page), `create` (form), `edit` (form), `custom` (free-form)

#### Attention Signals

Surfaces can declare conditions that should draw user attention:

```dsl
  ux:
    attention:
      critical: status = "overdue" -> "This item is overdue"
      warning: due_date < today and status != "done" -> "Approaching deadline"
```

When rows match these conditions, the UI highlights them — red background for critical, yellow for warning — with the message shown as a tooltip. The workspace region renderer evaluates these signals against every row and picks the highest severity.

#### Persona Variants

The same surface can show different fields, scopes, or behaviors to different user roles:

```dsl
  ux:
    for admin:
      scope: all
      purpose: "Full company management"
      action_primary: company_create
    for agent:
      scope: assigned_agent = current_user
      purpose: "View assigned companies"
      read_only: true
      hide: internal_notes, margin_percentage
```

### Layer 3: Workspaces (Your Dashboards)

A workspace composes multiple data views into a single dashboard page. Where surfaces show one entity, workspaces aggregate across many.

```dsl
workspace admin_dashboard "Admin Dashboard":
  purpose: "Practice-wide operational visibility"
  stage: "command_center"

  practice_kpis:
    source: Company
    display: metrics
    aggregate:
      total_clients: count(Company)
      active_subscriptions: count(ClientSubscription where status = active)
      overdue_deadlines: count(ComplianceDeadline where due_date < today and status != completed)

  onboarding_pipeline:
    source: OnboardingFlow
    filter: completed_at = null
    sort: started_at asc
    limit: 10
    display: list
    action: onboarding_flow_detail
    empty: "No active onboardings"

  urgent_tasks:
    source: Task
    filter: priority = urgent and status != done
    sort: due_date asc
    limit: 5
    display: list
    action: task_detail
```

Each workspace has **regions** — the named blocks like `practice_kpis` and `onboarding_pipeline`. Regions can be:

- **Data regions** (`display: list`): Show filtered, sorted entity rows — like a mini surface with sortable headers, status badges, filter dropdowns, and row-click navigation
- **Aggregate regions** (`display: metrics`): Show KPI metric cards computed from `count()`, `sum()`, `avg()`, `min()`, `max()` expressions
- **Detail regions** (`display: detail`): Show a single record
- **Grid regions** (`display: grid`): Card-based grid layout

The `stage:` controls the CSS grid layout:

| Stage | Layout | Use Case |
|-------|--------|----------|
| `focus_metric` | Single column, hero stat + supporting | KPI dashboard |
| `scanner_table` | Full-width table + optional sidebar | Data browser |
| `dual_pane_flow` | 2-column master-detail | List + detail |
| `monitor_wall` | 2x2 or 2x3 grid | Status wall |
| `command_center` | 12-column grid with region spans | Operations hub |

At runtime, each region gets its own HTMX endpoint (`/api/workspaces/admin_dashboard/regions/practice_kpis`) that returns rendered HTML fragments. The workspace page loads instantly with skeleton placeholders, then each region fills in asynchronously.

Column rendering is type-aware: enum fields render as colored badges, booleans as check/cross icons, dates as relative times ("2 hours ago"), and money fields with currency symbols. Enum and boolean columns automatically get filter dropdowns. State-machine status fields are filterable by their allowed states.

### Layer 4: Stories and Processes (Your Business Logic)

This is where Dazzle's architecture gets interesting, and where the layer separation matters most.

**Stories** describe *what should happen* from a user's perspective:

```yaml
story_id: ST-161
title: "Staff completes onboarding and provisions client access"
actor: Agent
trigger: form_submitted
scope:
  - OnboardingFlow
  - OnboardingChecklist
  - Contact
  - EngagementLetter
  - ClientSubscription
happy_path_outcome:
  - "OnboardingChecklist.services_selected = true"
  - "OnboardingFlow.stage transitions to complete"
  - "OnboardingFlow.completed_at set to current timestamp"
  - "Contact.onboarding_complete = true"
  - "EngagementLetter created in draft status"
  - "ClientSubscription created for selected service package"
side_effects:
  - "Notification sent to client with portal access details"
  - "AuditLog entry records onboarding completion"
  - "Task created for agent to initiate CDD process"
```

**Processes** describe *how* the steps are orchestrated:

```yaml
name: staff_onboarding_flow
implements:
  - ST-156
  - ST-157
  - ST-158
  - ST-161
trigger:
  kind: manual
  entity_name: OnboardingFlow
steps:
  - name: check_existing_flow
    kind: service
    service: OnboardingFlow.check_unique_contact
  - name: create_flow
    kind: service
    service: OnboardingFlow.create_or_update
  - name: create_checklist
    kind: service
    service: OnboardingChecklist.create
  - name: complete_onboarding
    kind: service
    service: OnboardingFlow.complete
  - name: notify_client
    kind: service
    service: Notification.send_portal_access
  - name: create_cdd_task
    kind: service
    service: Task.create_cdd_task
  - name: log_completion
    kind: service
    service: AuditLog.create
compensations:
  - name: rollback_subscription
    service: ClientSubscription.delete
  - name: rollback_flow
    service: OnboardingFlow.delete
events:
  on_start: onboarding.staff_initiated
  on_complete: onboarding.staff_completed
```

**Here is the key insight:** The process defines *step ordering*, *failure recovery* (compensations), and *event emission*. It does NOT specify field values like "set completion_percentage to 100" — those are handled by entity defaults (Layer 1) and service implementations (Layer 5). The process orchestrates *when* things happen; the services know *what* to do.

Processes also support:
- **Human tasks** — steps that wait for user input before continuing
- **Retry policies** — automatic retry with backoff on failure
- **Timeout policies** — deadlines for step completion
- **Overlap policies** — whether multiple instances can run concurrently
- **Compensation** — rollback in reverse order when a step fails (saga pattern)

### Layer 5: Services (Your Custom Code)

Dazzle's DSL is deliberately **anti-Turing** — you cannot write arbitrary computation in it. This is a feature, not a limitation. It means the DSL is always analyzable, validatable, and safe.

When you need real business logic — VAT calculations, NINO validation, Companies House API calls — you declare a **domain service** in the DSL and implement it in a **stub**:

```dsl
service calculate_vat "Calculate VAT":
  kind: domain_logic
  input:
    invoice_id: uuid required
    country_code: str(2)
  output:
    vat_amount: decimal(10,2)
    breakdown: json
  guarantees:
    - "Must not mutate the invoice record"
  stub: python
```

Dazzle auto-generates a typed Python function signature in `stubs/calculate_vat.py`. You fill in the implementation. The DSL declares the contract (inputs, outputs, guarantees); the stub provides the computation.

**Service kinds:** `domain_logic` (pure business rules), `validation` (input checking), `integration` (external API calls), `workflow` (multi-step orchestration)

This is also how external APIs are declared. Dazzle ships with API packs for Stripe, HMRC, Xero, Companies House, DocuSeal, SumSub, and Ordnance Survey — each pack generates the service DSL and foreign model definitions for you.

### Layer 6: The Public Site

Dazzle separates your public marketing site from your application. The site is defined in two files:

- **`sitespec.yaml`** — Structure: page routes, navigation, section types, brand configuration
- **`copy.md`** — Content: headlines, feature descriptions, testimonials, calls to action

At runtime, copy is merged into sitespec sections. This separation means a copywriter can edit `copy.md` without touching the structural layout, and a designer can restructure pages in `sitespec.yaml` without rewriting content.

Pages use typed sections (`hero`, `features`, `comparison`, `card_grid`, `trust_bar`, `cta`, `markdown`) that Dazzle renders into themed HTML. Page types include `landing`, `pricing`, `legal` (terms, privacy), and custom pages.

The site layer also includes brand configuration (logo, tagline, colors), navigation structure, footer layout, and authentication page styling.

### Layer 7: Experiences (Multi-Step User Flows)

Experiences define wizard-like flows that guide users through multiple screens:

```dsl
experience client_onboarding "Client Onboarding":
  start at step welcome

  step welcome:
    kind: surface
    surface onboarding_welcome
    on continue -> step basics

  step basics:
    kind: surface
    surface onboarding_basics
    on continue -> step business_type
    on back -> step welcome

  step business_type:
    kind: surface
    surface onboarding_business_type
    on continue -> step business_details
    on back -> step basics

  step complete:
    kind: surface
    surface onboarding_complete
```

Each step references a surface, and transitions are driven by user events (`continue`, `back`, `success`, `failure`). Steps can also be `kind: process` (trigger a backend process) or `kind: integration` (call an external API).

The experience layer handles navigation state; the surfaces handle data display; the processes handle data manipulation.

### Layer 8: Islands (Client-Side Interactivity)

Dazzle's default UI is fully server-rendered with HTMX. But sometimes you need a chart, a drag-and-drop board, or a real-time widget that genuinely requires client-side JavaScript. That is what **islands** are for — self-contained interactive components embedded within server-rendered pages.

```dsl
island task_chart "Task Progress Chart":
  entity: Task
  src: "islands/task-chart/index.js"
  fallback: "Loading task chart..."

  prop chart_type: str = "bar"
  prop date_range: str = "30d"

  event chart_clicked:
    detail: [task_id, series]
```

What Dazzle does with this:
- **Renders a container** in the page with server-side fallback content shown before JS loads
- **Loads the JS entry point** from `src` (defaults to `/static/islands/{name}/index.js`)
- **Passes typed props** as `data-island-props` JSON attributes
- **Auto-generates a data endpoint** at `/api/islands/{island_name}/data` when `entity:` is declared, proxying to the entity's CRUD service with pagination

Islands are intentionally opt-in and isolated. The server-rendered HTMX approach handles 90%+ of UI needs; islands handle the remaining cases where client-side rendering adds genuine value (charts, maps, rich editors, real-time dashboards).

**Props**: Typed key-value pairs passed to the island (`str`, `int`, `bool`, `float` with optional defaults)

**Events**: CustomEvent schemas the island may emit, with typed detail fields. The server can listen for these via HTMX's `hx-on` or standard `addEventListener`.

---

## How the Layers Work Together

Here is a concrete example: a staff member onboards a new limited company client.

1. **Entity layer**: Company has `trading_status = active` as default. OnboardingFlow has `stage = started` and `flow_type = self_service` as defaults.
2. **Experience layer**: The onboarding experience defines the step sequence — welcome → basics → business type → business details → complete.
3. **Surface layer**: Each experience step renders a surface. The `company_create` surface shows a form with company_name and company_number fields. The `ux:` block adds search and validation.
4. **Process layer**: The `staff_onboarding_flow` process orchestrates the multi-entity operations — create OnboardingFlow, create OnboardingChecklist, create Company, create CompanyContact link, create EngagementLetter, create ClientSubscription. If any step fails, compensations roll back in reverse order.
5. **Service layer**: Each process step calls a service. `OnboardingFlow.complete` sets completed_at, updates completion_percentage, marks Contact.onboarding_complete. `Notification.send_portal_access` sends the welcome email.
6. **Workspace layer**: After onboarding, the admin_dashboard workspace shows updated metrics — `total_clients` count increments, the `onboarding_pipeline` region drops the completed flow.
7. **Site layer**: Meanwhile, the public site at `/pricing` shows the service packages available for new clients, driven entirely by sitespec.yaml + copy.md.
8. **Island layer**: A chart on the admin dashboard shows onboarding completion rates over time — rendered client-side with Chart.js, fed by an auto-generated data endpoint.

Each layer does one thing well and delegates everything else:

| If you need... | You write... | You DON'T write... |
|---|---|---|
| A data model with defaults | Entity DSL | Migration scripts, ORM models |
| A CRUD interface | Surface DSL | HTML templates, API routes, pagination logic |
| A dashboard | Workspace DSL | Dashboard components, data-fetching hooks |
| Business workflow | Process definition | Saga coordinators, event handlers |
| Custom logic | Service stub | Framework boilerplate, dependency injection |
| A marketing site | sitespec.yaml + copy.md | Landing page HTML, CSS, routing |
| A multi-step wizard | Experience DSL | Router configuration, step state management |
| A chart or rich widget | Island DSL + JS file | Data-fetching boilerplate, container plumbing |

---

## The Pipeline: Determinism and Cognition

DAZZLE separates work into two distinct phases: a **deterministic foundation** that requires zero LLM involvement, and a **cognitive layer** where LLM creativity adds value.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        DETERMINISTIC PHASE (no LLM)                             │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌───────────┐      ┌────────────┐      ┌───────────┐      ┌─────────────────┐  │
│  │ DSL Files │ ───▶ │   Parser   │ ───▶ │  AppSpec  │ ───▶ │ Runtime / Specs │  │
│  │  (.dsl)   │      │  + Linker  │      │   (IR)    │      │                 │  │
│  └───────────┘      └────────────┘      └───────────┘      └─────────────────┘  │
│       │                   │                   │                     │           │
│       ▼                   ▼                   ▼                     ▼           │
│   Artifacts:         Artifacts:          Artifacts:            Artifacts:       │
│   • core.dsl         • AST               • Entity graph        • OpenAPI spec   │
│   • ui.dsl           • Symbol table      • Surface defs        • AsyncAPI spec  │
│   • *.dsl            • Module graph      • Type catalog        • Running app    │
│                                          • Validation          • HTML templates │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         COGNITIVE PHASE (LLM-assisted)                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────────────┐  │
│  │  Story Proposal │    │  Test Design    │    │  Process Orchestration      │  │
│  │                 │    │                 │    │                             │  │
│  │  "User creates  │    │  Persona-based  │    │  Multi-step workflows       │  │
│  │   a task and    │    │  test coverage  │    │  with compensations         │  │
│  │   assigns it"   │    │  proposals      │    │                             │  │
│  └─────────────────┘    └─────────────────┘    └─────────────────────────────┘  │
│          │                      │                          │                    │
│          ▼                      ▼                          ▼                    │
│      Artifacts:             Artifacts:                 Artifacts:               │
│      • stories.yaml         • test_designs.yaml        • processes.yaml        │
│      • CRUD coverage        • Playwright tests         • State diagrams        │
│      • Edge cases           • E2E scenarios            • Saga definitions      │
│                                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────────────┐  │
│  │  Demo Data      │    │  Tenancy &      │    │  Fidelity & Gap Analysis    │  │
│  │                 │    │  Compliance     │    │                             │  │
│  │  Realistic      │    │  Inference      │    │  Spec vs. rendered HTML     │  │
│  │  seed data      │    │                 │    │  cross-tool issue reports   │  │
│  │  per-persona    │    │                 │    │                             │  │
│  └─────────────────┘    └─────────────────┘    └─────────────────────────────┘  │
│          │                      │                          │                    │
│          ▼                      ▼                          ▼                    │
│      Artifacts:             Artifacts:                 Artifacts:               │
│      • demo_blueprint.yaml  • Tenancy config           • Fidelity scores       │
│      • CSV/JSONL exports    • PII/GDPR hints           • Unified issues        │
│      • Tenant fixtures      • Compliance frameworks    • Coverage gaps         │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

| Phase | Characteristics | Token Cost | Error Rate |
|-------|----------------|------------|------------|
| **Deterministic** | Parsing, linking, validation, runtime execution | Zero | Near-zero (compiler-checked) |
| **Cognitive** | Story generation, test proposals, gap analysis | One-time per feature | Reviewable artifacts |

The deterministic phase handles all the mechanical work that LLMs do poorly: parsing grammars, resolving references, type checking, and generating correct code. The cognitive phase leverages what LLMs do well: understanding intent, proposing test scenarios, and identifying gaps.

---

## DSL Constructs Reference

Complete reference: [docs/reference/](docs/reference/)

### Core

| Construct | Purpose |
|-----------|---------|
| `module` | Namespace declaration for DSL files |
| `app` | Application metadata |
| `use` | Import constructs from other modules |

### Data Modeling

| Construct | Purpose |
|-----------|---------|
| `entity` | Domain models with typed fields, relationships, state machines, invariants, and access control |
| `enum` | Shared enum definitions reusable across entities (e.g., `OrderStatus` with labeled values) |
| `archetype` | Reusable field templates (e.g., `Timestamped`, `Auditable`) |
| `foreign_model` | External API data structures (read-only, event-driven, or batch-imported) |

**Field Types**: `str(N)`, `text`, `int`, `decimal(P,S)`, `bool`, `date`, `datetime`, `uuid`, `email`, `json`, `money`, `file`, `url`, `timezone`, `enum[...]`

**Relationship Types**: `ref`, `has_many`, `has_one`, `belongs_to`, `embeds`

**Field Modifiers**: `required`, `optional`, `pk`, `unique`, `unique?`, `auto_add`, `auto_update`, `sensitive`, `=default`

**Entity Blocks**: `transitions` (state machine), `invariants` (business rules), `access` (role/owner/tenant permissions), `computed` (derived fields), `examples` (fixture data), `publishes` (event declarations)

### UI Layer

| Construct | Purpose |
|-----------|---------|
| `surface` | UI screens and forms (list, view, create, edit, custom modes) |
| `workspace` | Dashboards with regions, filters, aggregates, and layout stages |
| `experience` | Multi-step wizards and user flows |
| `island` | Client-side interactive components (charts, maps, rich editors) with typed props, events, and optional entity data binding |
| `view` | Read-only projections with grouping and aggregates (`sum`, `count`, `avg`) for dashboards and reports |

**Surface Elements**: `section`, `field`, `action`, `outcome`

**Workspace Elements**: `source`, `filter`, `sort`, `limit`, `display`, `aggregate`, `group_by`, `action`

**Workspace Stages**: `focus_metric`, `scanner_table`, `dual_pane_flow`, `monitor_wall`, `command_center`

**Experience Steps**: `kind: surface`, `kind: process`, `kind: integration` with event-driven transitions

### UX Semantic Layer

| Construct | Purpose |
|-----------|---------|
| `ux` | UI hints block within surfaces |
| `attention` | Conditional alerts (critical, warning, notice, info) |
| `for` | Persona-specific view customization (scope, show/hide, read_only, defaults) |

**UX Properties**: `purpose`, `show`, `hide`, `sort`, `filter`, `search`, `empty`

### Services and Integrations

| Construct | Purpose |
|-----------|---------|
| `service` | External APIs (with OpenAPI spec) or domain services (with typed input/output/guarantees) |
| `integration` | Orchestrates data flow between app and external services |

**Service Kinds**: `domain_logic`, `validation`, `integration`, `workflow`

**Integration Elements**: `action` (request-response), `sync` (scheduled or event-driven data synchronization)

### Messaging

| Construct | Purpose |
|-----------|---------|
| `message` | Typed message schemas |
| `channel` | Communication pathways (email, queue, stream) |
| `template` | Reusable message templates with attachments |

**Send Triggers**: Entity events, status transitions, field changes, service events, schedules

### Ledgers and Transactions

| Construct | Purpose |
|-----------|---------|
| `ledger` | TigerBeetle account templates for double-entry accounting |
| `transaction` | Multi-leg financial transactions with atomic guarantees |

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

**Account Types**: `asset`, `liability`, `equity`, `revenue`, `expense`

### Governance and Automation

| Construct | Purpose |
|-----------|---------|
| `webhook` | Outbound HTTP notifications on entity events with HMAC/bearer/basic auth and retry policies |
| `approval` | Approval gates with quorum, threshold conditions, time-based escalation, and auto-approve rules |
| `sla` | Service level agreements with deadline tiers, business hours, pause conditions, and breach actions |

### Personas and Scenarios

| Construct | Purpose |
|-----------|---------|
| `persona` | User archetypes with goals, proficiency levels, default workspaces |
| `scenario` | Named application states for development and demos |

```dsl
persona admin "Administrator":
  description: "Full system access for practice management"
  goals: manage_clients, monitor_compliance, configure_system
  proficiency: expert
  default_workspace: admin_dashboard

scenario busy_sprint "Busy Sprint":
  seed_script: fixtures/busy_sprint.json
  for admin:
    description: "20 active tasks, 3 overdue, 2 in review"
  for member:
    description: "5 assigned tasks, 1 overdue"
```

### Events and Streams

| Construct | Purpose |
|-----------|---------|
| `publishes` | Event declarations on entities (lifecycle, field changes) |
| `subscribe` | Event handlers and projections |
| `stream` | HLESS (High-Level Event Semantics) with INTENT/FACT/OBSERVATION/DERIVATION records |

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

Dazzle includes a mission-driven agent framework that can autonomously explore, test, and analyze running applications.

The agent follows an **observe → decide → act → record** loop and supports four mission types:

| Mission | Purpose |
|---------|---------|
| **Persona Discovery** | Explore a running app as a specific persona, comparing what exists against the DSL spec. Identifies missing CRUD operations, workflow gaps, navigation issues, and UX problems. |
| **Entity Completeness** | Static CRUD coverage analysis plus targeted verification of missing operations per entity. |
| **Workflow Coherence** | Validates process/story integrity — checks that step transitions, guards, and compensations are correctly wired. |
| **Headless** | Pure DSL/KG persona journey analysis without a running app — traces what each persona should be able to do based on the spec alone. |

The agent produces structured observations that feed into two further stages:

1. **Narrative Compiler** — Groups observations by category and entity, prioritizes by severity x frequency, generates human-readable "As [persona], I expected... but found..." narratives, and validates adjacency against the knowledge graph.

2. **DSL Emitter** — Converts compiler proposals into valid DSL code. Template-based generation for missing surfaces, workflow gaps, and navigation gaps, with automatic validation and retry (up to 3 attempts with auto-fix for common errors).

The full discovery flow via MCP:
```
discovery run → discovery report → discovery compile → discovery emit
                                                    ↘ discovery coherence (UX scoring)
                                                    ↘ discovery verify_all_stories (batch verification)
```

---

## Three-Tier Testing

Dazzle supports three tiers of testing, each with increasing power and cost:

| Tier | Tool | What It Tests | Speed |
|------|------|--------------|-------|
| **Tier 1: DSL Tests** | `dsl_test generate` + `dsl_test run` | API contracts against the running server — CRUD operations, validation rules, state machine transitions, access control. `verify_story` checks story implementations; `diff_personas` compares route behavior across roles | Fast (HTTP calls) |
| **Tier 2: Playwright** | `e2e_test run` + `e2e_test run_viewport` | UI rendering and interaction — form submission, navigation, DataTable behavior, fragment rendering. Viewport testing with screenshot capture and visual regression baselines across mobile/desktop | Medium (browser automation) |
| **Tier 3: Agent** | `e2e_test run_agent` | End-to-end user journeys — an LLM agent navigates the app as a persona and validates behavior against stories. `tier_guidance` recommends the right tier for a given scenario | Slow (LLM-guided exploration) |

Tests are generated from the DSL, not written by hand. The test design system tracks coverage across entities, state machines, personas, workspaces, events, and processes, and proposes new tests to fill gaps.

```bash
dazzle test dsl-run              # Tier 1: API tests
dazzle test playwright           # Tier 2: UI tests
dazzle test viewport             # Tier 2: Visual regression
dazzle test agent                # Tier 3: LLM-powered tests
```

---

## API Packs

Dazzle ships with pre-built integration packs for common external APIs. Each pack includes authentication configuration, operation definitions, foreign model schemas, and DSL generation templates.

| Provider | Packs | Category |
|----------|-------|----------|
| **Stripe** | `stripe:payments` | Payment processing |
| **HMRC** | `hmrc:mtd_vat`, `hmrc:itsa`, `hmrc:cis`, `hmrc:obligations`, `hmrc:income_sources`, `hmrc:vat_lookup` | UK tax authority |
| **Xero** | `xero:accounting` | Accounting software |
| **Companies House** | `companies_house:company_data` | UK company registry |
| **DocuSeal** | `docuseal:signatures` | Digital signatures |
| **SumSub** | `sumsub:kyc` | KYC/AML verification |
| **Ordnance Survey** | `ordnance_survey:maps` | UK mapping |

Usage via MCP:
```
api_pack search query="payments"     # Find packs
api_pack get pack_name="stripe:payments"  # Full details
api_pack generate_dsl pack_name="stripe:payments"  # Generate DSL
api_pack env_vars pack_names=["stripe:payments"]    # Generate .env.example
```

---

## Fidelity Scoring

DAZZLE includes a built-in fidelity scorer that measures how accurately rendered HTML reflects the DSL specification. This closes the loop between "what you declared" and "what the user sees."

The scorer evaluates four dimensions:

| Dimension | Weight | What it checks |
|-----------|--------|----------------|
| **Structural** | 35% | Every declared field, section, and action is present in the HTML |
| **Semantic** | 30% | Input types match field types, required attributes are set, display names are humanised |
| **Story** | 20% | User stories have corresponding action affordances (buttons, links) |
| **Interaction** | 15% | Search/select widgets, loading indicators, debounce, empty states, error handling |

Each gap found is categorised by severity (`critical`, `major`, `minor`) and returned with a concrete recommendation. The interaction dimension is spec-aware: if a surface element declares `source=` (indicating a relationship lookup), the scorer verifies that a `search_select` widget was actually rendered.

```bash
dazzle fidelity                  # Score all surfaces
dazzle fidelity --surface orders # Score a single surface
```

---

## Why HTMX, Not React

DAZZLE's frontend is server-rendered HTML using HTMX. This is a deliberate architectural choice, not a limitation.

**React's strengths are for humans.** React's component model is designed around how human developers think: compositional UI building blocks, a rich ecosystem of community packages, and a mental model (declarative state → view) that maps well to how people reason about interfaces.

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

### Getting Started
- [Installation](docs/getting-started/installation.md)
- [Quickstart](docs/getting-started/quickstart.md)
- [First App Tutorial](docs/getting-started/first-app.md)

### DSL Reference
- [Modules](docs/reference/modules.md) · [Entities](docs/reference/entities.md) · [Surfaces](docs/reference/surfaces.md) · [Workspaces](docs/reference/workspaces.md) · [Services](docs/reference/services.md) · [Integrations](docs/reference/integrations.md) · [Ledgers](docs/reference/ledgers.md) · [Messaging](docs/reference/messaging.md) · [UX Layer](docs/reference/ux.md) · [Scenarios](docs/reference/scenarios.md) · [Experiences](docs/reference/experiences.md) · [CLI Reference](docs/reference/cli.md) · [DSL Grammar](docs/reference/grammar.md)

### Architecture
- [Architecture Overview](docs/architecture/overview.md) · [DSL to AppSpec](docs/architecture/dsl-to-appspec.md) · [MCP Server](docs/architecture/mcp-server.md)

### Examples
- [Simple Task](docs/examples/simple-task.md) · [Contact Manager](docs/examples/contact-manager.md) · [Ops Dashboard](docs/examples/ops-dashboard.md) · [Support Tickets](docs/examples/support-tickets.md) · [FieldTest Hub](docs/examples/fieldtest-hub.md)

### Contributing
- [Development Setup](docs/contributing/dev-setup.md) · [Testing Guide](docs/contributing/testing.md) · [Adding Features](docs/contributing/adding-a-feature.md)

---

## Contributing

All contributions require AI co-authorship. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT - see [LICENSE](LICENSE)
