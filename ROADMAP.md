# DAZZLE Development Roadmap

**Last Updated**: 2025-12-11
**Current Version**: v0.9.3
**Status**: DSL-first toolkit with DNR runtime + Ejection toolchain

---

## Executive Summary

DAZZLE is a **DSL-first toolkit** that bridges human specifications and production code.

### The Core Workflow

```
Human Intent ──▶ LLM ──▶ Structured DSL ──▶ Deterministic Code
                         (one-time cost)    (zero marginal cost)
```

1. **LLM translates intent to DSL** - High-value token spend, done once
2. **DSL is the compression boundary** - Validated, version-controlled spec
3. **All downstream is deterministic** - Parser, IR, code gen are mechanical

### Two Paths from DSL

| Path | Use Case | Cost |
|------|----------|------|
| **DNR Runtime** | Rapid iteration, prototyping | Zero - runs directly |
| **Ejection** | Production deployment | One-time generation |

**Philosophy**: Pay LLM tokens once to get the spec right. Everything after is cheap.

---

## Version History

### v0.1.0 - Initial Release (November 2025) ✅ COMPLETE

**Focus**: Foundation & Code Generation

**Delivered**:
- Complete DSL parser (800+ lines)
- Full Internal Representation (900+ lines, Pydantic models)
- Module system with dependency resolution
- 6 code generation stacks (Django, Express, OpenAPI, Docker, Terraform)
- LLM integration (spec analysis, DSL generation)
- LSP server with VS Code extension
- Homebrew distribution
- MCP server integration

---

### v0.1.1 - Stack Improvements (November 2025) ✅ COMPLETE

**Focus**: Express Micro enhancements, bug fixes

---

### v0.2.0 - UX Semantic Layer (November 2025) ✅ COMPLETE

**Focus**: Fundamental DSL language enhancement

**Delivered**:
- **Personas**: Role-based surface/workspace variants with scope filtering
- **Workspaces**: Composed dashboards with multiple data regions
- **Attention Signals**: Data-driven alerts (critical, warning, notice, info)
- **Information Needs**: `show`, `sort`, `filter`, `search`, `empty` directives
- **Purpose Statements**: Semantic intent documentation
- **MCP Enhancements**: Semantic concept lookup, example search

**Documentation**: DSL Reference v0.2, UX Semantic Layer Spec, Migration Guide

---

### v0.3.0 - DNR & Layout Engine ✅ COMPLETE

**Released**: November 2025

**Major Pivot**: This release introduces **Dazzle Native Runtime (DNR)** as the primary way to run DAZZLE applications, deprecating legacy code generation stacks.

#### DNR Backend (COMPLETE) ✅

- **SQLite persistence** with auto-migration
- **FastAPI server** with auto-generated CRUD endpoints
- **Authentication**: Session-based auth, PBKDF2 password hashing
- **Authorization**: Row-level security, owner/tenant-based access control
- **File uploads**: Local and S3 storage, image processing, thumbnails
- **Rich text**: Markdown rendering, HTML sanitization
- **Relationships**: Foreign keys, nested data fetching
- **Full-text search**: SQLite FTS5 integration
- **Real-time**: WebSocket support, presence indicators, optimistic updates

#### DNR Frontend (COMPLETE) ✅

- **Signals-based UI**: Reactive JavaScript without virtual DOM
- **Combined server**: Backend + Frontend with API proxy
- **Hot reload**: SSE-based live updates
- **Vite integration**: Production builds

#### UI Semantic Layout Engine (COMPLETE) ✅

- **5 Archetypes**: FOCUS_METRIC, SCANNER_TABLE, DUAL_PANE_FLOW, MONITOR_WALL, COMMAND_CENTER
- **Attention signals**: Semantic UI elements with priority weights
- **Engine variants**: Classic, Dense, Comfortable
- **Layout planning**: `dazzle layout-plan` command
- **Persona-aware**: Layout adjustments per user role

#### Phase 5: Release Preparation ✅ COMPLETE

- [x] Archetype selection improvements (`--explain` flag)
- [x] `engine_options` in IR for customization
- [x] Final testing and documentation
- [x] Version bump to 0.3.0
- [x] Release notes created

#### Example Projects

| Example | Archetype | Purpose |
|---------|-----------|---------|
| `simple_task` | SCANNER_TABLE | Basic CRUD app |
| `contact_manager` | DUAL_PANE_FLOW | List + detail pattern |
| `uptime_monitor` | FOCUS_METRIC | Single KPI dashboard |
| `email_client` | MONITOR_WALL | Multi-signal dashboard |
| `inventory_scanner` | SCANNER_TABLE | Data table focus |
| `ops_dashboard` | COMMAND_CENTER | Operations monitoring |
| `archetype_showcase` | All | Demonstrates all archetypes |

---

## Recent Releases

### v0.3.1 - Critical Bug Fixes & E2E Testing ✅ COMPLETE

**Status**: ✅ COMPLETE
**Focus**: Fix DNR runtime bugs and prevent regressions

**Background**: User testing revealed that `dazzle dnr serve` produces non-functional applications due to JavaScript generation bugs. These must be fixed immediately.

#### Bug Fixes (COMPLETE)
- [x] **Bug 1**: ES module export block conversion failure in `js_loader.py`
  - Multi-line `export { ... }` blocks were not fully stripped
  - Fix: Use regex to remove entire export blocks before line processing
- [x] **Bug 2**: HTML script tag malformation in `js_generator.py`
  - `<script src="app.js">` with inline content is invalid HTML
  - Fix: Properly close external script tags

#### E2E Testing (COMPLETE)
- [x] Add E2E tests for DNR serve in `tests/e2e/test_dnr_serve.py`
- [x] Verify JavaScript bundle generation is valid
- [x] Verify HTML generation is correct (no malformed script tags)
- [x] Verify entity conversion to BackendSpec works
- [x] Add to CI pipeline to prevent regressions

#### MCP Server Improvements (COMPLETE) ✅
- [x] Improve MCP context for Claude engagement
- [x] Add getting-started workflow guidance
- [x] Document common DSL patterns
- [x] Update semantic index to v0.5.0 with extensibility concepts
- [x] Add domain service pattern with examples

#### CI/CD E2E Testing (COMPLETE)
- [x] Remove fallback JavaScript from `js_generator.py` - single source of truth via `js_loader.py`
- [x] Add matrix-based E2E testing for example projects
- [x] P0 examples (simple_task, contact_manager) block PRs on failure
- [x] P1/P2 examples run on main branch only with warnings
- [x] Upload test artifacts on failure for debugging
- [x] Document CI strategy in `dev_docs/ci_e2e_testing_strategy.md`

**Files Changed**:
- `src/dazzle_dnr_ui/runtime/js_loader.py` - Export block regex fix
- `src/dazzle_dnr_ui/runtime/js_generator.py` - Removed fallback JS, always load from files
- `src/dazzle_dnr_ui/runtime/combined_server.py` - Script tag fix
- `src/dazzle_dnr_ui/runtime/dev_server.py` - Script tag fix
- `src/dazzle_dnr_ui/runtime/static/js/components.js` - DOM contract implementation
- `tests/e2e/test_dnr_serve.py` - New E2E tests for DNR
- `.github/workflows/ci.yml` - Matrix E2E testing for examples

---

### v0.3.2 - Semantic E2E Testing Framework ✅ COMPLETE

**Status**: ✅ All 8 phases complete
**Focus**: Stack-agnostic E2E testing generated from AppSpec
**Plan**: `dev_docs/plans/semantic_e2e_testing_implementation.md`

Tests are generated from the same AppSpec that generates the app. Tests operate on semantic identifiers (entities, fields, actions) rather than CSS selectors, making them stack-agnostic.

#### Phase 1: DOM Contract (COMPLETE)
- [x] Define `data-dazzle-*` attribute specification (`docs/SEMANTIC_DOM_CONTRACT.md`)
- [x] Update DNR UI components to emit semantic attributes
- [x] Add `withDazzleAttrs` helper in `dom.js`
- [x] Update surface converter to pass entity context
- [x] Add unit tests for attribute presence (`tests/e2e/test_semantic_dom_contract.py`)

#### Phase 2: TestSpec IR Extensions (COMPLETE)
- [x] Add FlowSpec, FlowStep, FlowAssertion to IR (`src/dazzle/core/ir.py`)
- [x] Add FixtureSpec, E2ETestSpec, UsabilityRule, A11yRule to IR
- [x] Flow step types: navigate, fill, click, wait, assert, snapshot
- [x] Semantic targets: `view:task_list`, `field:Task.title`, `action:Task.create`
- [x] Extend AppSpec with `e2e_flows` and `fixtures` fields
- [x] Unit tests for new IR types (`tests/unit/test_ir_e2e_types.py`)

#### Phase 3: Auto-Generate E2ETestSpec (COMPLETE)
- [x] Generator to produce E2ETestSpec from AppSpec (`src/dazzle/testing/testspec_generator.py`)
- [x] Auto-generate CRUD flows for each entity (create, view, update, delete)
- [x] Auto-generate validation flows from field constraints
- [x] Auto-generate navigation flows for surfaces
- [x] Generate fixtures from entity schemas
- [x] Generate usability and accessibility rules
- [x] Unit tests for generator (`tests/unit/test_testspec_generator.py`)
- [ ] CLI: `dazzle test generate` (deferred to Phase 7)

#### Phase 4: Playwright Harness (COMPLETE)
- [x] Semantic locator library (`src/dazzle_e2e/locators.py`)
- [x] Flow execution engine (`src/dazzle_e2e/harness.py`)
- [x] Domain-level assertions (`src/dazzle_e2e/assertions.py`)
- [x] Base adapter interface (`src/dazzle_e2e/adapters/base.py`)
- [x] DNR adapter implementation (`src/dazzle_e2e/adapters/dnr.py`)
- [x] Unit tests (`tests/unit/test_e2e_harness.py`)

#### Phase 5: Test Endpoints (COMPLETE)
- [x] `/__test__/seed` - Seed fixtures
- [x] `/__test__/reset` - Clear test data
- [x] `/__test__/snapshot` - Database state for assertions
- [x] `/__test__/authenticate` - Test authentication
- [x] `/__test__/entity/{name}` - Get entity data
- [x] `/__test__/entity/{name}/count` - Get entity count
- [x] Test mode configuration (`enable_test_mode` parameter)
- [x] Unit tests (`tests/unit/test_dnr_test_routes.py`)

#### Phase 6: DSL Extensions (COMPLETE)
- [x] `flow` block syntax in DSL
- [x] Parser support for flow definitions (`src/dazzle/core/dsl_parser.py`)
- [x] New keywords in lexer (`src/dazzle/core/lexer.py`)
- [x] Unit tests (`tests/unit/test_flow_parsing.py` - 22 tests)
- [ ] Grammar documentation update (deferred)

#### Phase 7: CLI & CI Integration (COMPLETE)
- [x] `dazzle test generate` command - Generate E2ETestSpec from AppSpec
- [x] `dazzle test run` command - Run E2E tests with Playwright
- [x] `dazzle test list` command - List available test flows
- [x] `dazzle dnr serve --test-mode` flag
- [x] CI workflow for semantic E2E (`semantic-e2e` job)

#### Phase 8: Usability & Accessibility (COMPLETE)
- [x] Usability rule engine (`src/dazzle_e2e/usability.py`)
  - max_steps rule for flow complexity checking
  - destructive_confirm rule for delete action safety
  - primary_action_visible rule for page usability
  - validation_placement rule for form UX
- [x] axe-core accessibility integration (`src/dazzle_e2e/accessibility.py`)
  - AccessibilityChecker class with axe-core loading
  - WCAG Level A/AA/AAA checking
  - Dazzle semantic element mapping
  - Violation filtering by A11yRule
- [x] WCAG violation mapping to AppSpec elements (`src/dazzle_e2e/wcag_mapping.py`)
  - WCAGMapper for violation-to-AppSpec mapping
  - WCAG criteria database (Level A, AA)
  - Axe rule to WCAG criterion mapping
  - Suggested fix generation
  - Violation report formatting
- [x] Unit tests (61 new tests):
  - `tests/unit/test_usability_checker.py` (17 tests)
  - `tests/unit/test_accessibility_checker.py` (21 tests)
  - `tests/unit/test_wcag_mapping.py` (23 tests)

**Success Criteria**:
- All DNR UI components emit `data-dazzle-*` attributes
- `dazzle test generate` produces valid E2ETestSpec
- High-priority flows block PRs on failure
- 100% of entities have auto-generated CRUD tests

---

### v0.3.3 - DNR Developer Experience ✅ COMPLETE

**Released**: December 2025

**Focus**: Make development delightful

**Delivered**:

#### Hot Reload & Dev Tools
- [x] DSL file watching with instant reload (`dazzle dnr serve --watch`)
- [x] Browser dev tools panel with state/action inspection
- [x] State inspector with real-time updates
- [x] Action log with state diff visualization

#### Debugging & Visualization
- [x] `dazzle dnr inspect` command for spec inspection
- [x] `dazzle dnr inspect --live` for running server inspection
- [x] `/_dnr/*` debug endpoints (health, stats, entity details)

---

### v0.4.0 - DNR Production Ready ✅ COMPLETE

**Released**: December 2025

**Focus**: Production deployment and testing

**Delivered**:

#### Testing & Validation
- [x] `dazzle dnr test` command for API contract testing
- [x] `--benchmark` option for performance testing
- [x] `--a11y` option for WCAG accessibility testing
- [x] Playwright harness integration

#### Deployment & Distribution
- [x] `dazzle dnr build` for production bundles
- [x] Multi-stage Dockerfile generation
- [x] docker-compose.yml for local deployment
- [x] Environment configuration (.env.example templates)
- [x] `dazzle dnr migrate` for database migrations
- [x] Kubernetes-style health probes (`/_dnr/live`, `/_dnr/ready`)

---

### v0.5.0 - Advanced DSL Features ✅ COMPLETE

**Released**: December 2025

**Focus**: DSL language enhancements for complex apps

**Delivered**:

#### Inline Access Rules (COMPLETE) ✅
```dsl
entity Task:
  access:
    read: owner = current_user or shared = true
    write: owner = current_user
```
- Parser support for `access:` block with `read:` and `write:` rules
- `read:` maps to VisibilityRule for authenticated users
- `write:` maps to CREATE, UPDATE, DELETE PermissionRules
- ACCESS, READ, WRITE tokens added to lexer
- Keywords can still be used as enum values (backward compatible)
- 8 unit tests in `test_access_rules.py`

#### Component Roles (COMPLETE) ✅
```dsl
component TaskCard:
  role: presentational  # or container
```
- ComponentRole enum: PRESENTATIONAL, CONTAINER
- `role` field on ComponentSpec with auto-inference
- `is_presentational` property: True if no state and no impure actions
- `is_container` property: True if has state or impure actions
- Explicit role overrides inference
- 13 unit tests in `test_component_roles.py`

#### Action Purity (COMPLETE) ✅
```dsl
actions:
  toggleFilter: pure
  saveTask: impure
```
- ActionPurity enum: PURE, IMPURE
- `purity` field on ActionSpec with auto-inference
- `is_pure` property: True if no effect
- `is_impure` property: True if has effect (fetch, navigate, etc.)
- Explicit purity overrides inference
- 14 unit tests in `test_action_purity.py`

#### Anti-Turing Extensibility Model (COMPLETE) ✅
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
- **Three-Layer Architecture**: DSL Layer (declarative) → Kernel Layer (DNR) → Stub Layer (Turing-complete)
- **Domain Service DSL**: `service` declarations with `kind`, `input`, `output`, `guarantees`, `stub`
- **Service Kinds**: domain_logic, validation, integration, workflow
- **Stub Generation**: `dazzle stubs generate` creates typed Python/TypeScript stubs
- **ServiceLoader**: Runtime discovery and invocation of stub implementations
- **EBNF Grammar Update**: Restricted function calls to aggregate functions only
- IR types: DomainServiceKind, StubLanguage, ServiceFieldSpec, DomainServiceSpec
- 14 unit tests in `test_domain_service_parsing.py`
- 17 unit tests in `test_service_loader.py`
- Documentation: `docs/EXTENSIBILITY.md`

**Test Results**: 601 tests pass (71+ new tests, no regressions)

---

## Recent Releases (Continued)

### v0.6.0 - GraphQL BFF Layer ✅ COMPLETE

**Released**: December 2025

**Focus**: API aggregation and external service facade

**Spec Document**: `dev_docs/DNR-Back-GraphQL-Spec-v1.md`

#### Core Components (COMPLETE) ✅
- [x] **GraphQLContext**: Multi-tenant context with role-based access control
  - `tenant_id`, `user_id`, `roles`, `request_id`, `ip_address`, `session`
  - `require_tenant()`, `require_authenticated()`, `has_role()`, `has_any_role()`
  - Factory functions: `create_context_from_request()`, `create_anonymous_context()`, `create_system_context()`
- [x] **SchemaGenerator**: Generate Strawberry types from BackendSpec
  - Entity types, input types (create/update), enum types
  - Scalar type mapping (str, int, bool, date, datetime, uuid, etc.)
  - SDL generation for documentation
- [x] **ResolverGenerator**: Generate CRUD resolvers with tenant isolation
  - Get by ID, list with pagination
  - Create, update, delete mutations
  - Tenant filtering from context (never from args)
  - Service and repository delegation
- [x] **FastAPI Integration**: Mount GraphQL on existing app
  - `create_graphql_app()`: Standalone GraphQL FastAPI app
  - `mount_graphql()`: Add GraphQL to existing app
  - `create_schema()`: Generate Strawberry schema from BackendSpec

#### CLI Integration (COMPLETE) ✅
```bash
dazzle dnr serve --graphql    # Enable GraphQL endpoint at /graphql
```

#### Unit Tests (COMPLETE) ✅
- [x] 12 context tests (creation, permissions, roles, immutability)
- [x] 14 Strawberry-dependent tests (skipped when not installed)
- [x] All 582 unit tests passing

#### CLI Inspection (COMPLETE) ✅
- [x] `dazzle dnr inspect --schema` command - Generate GraphQL SDL from BackendSpec

#### External API Adapters (COMPLETE) ✅
- [x] **BaseExternalAdapter**: Abstract base class for wrapping external REST APIs
  - Retry logic with exponential backoff
  - Rate limiting
  - Support for httpx, aiohttp, and urllib fallback
- [x] **Error Normalization**: Unified error model across external APIs
  - `NormalizedError` with category, severity, user/developer messages
  - `normalize_error()` for consistent error handling
  - HMRC-specific error mapping
- [x] **53 unit tests** for adapter interface and error normalization

#### Integration Tests (COMPLETE) ✅
- [x] GraphQL integration tests with real queries (`tests/integration/test_graphql_integration.py`)
  - Health check verification
  - List queries with empty results
  - GraphQL introspection (Task, Query, Mutation types)
  - Query type field verification (task, tasks)
  - Mutation type field verification (createTask, updateTask, deleteTask)
  - Error handling for invalid syntax and unknown fields

**Use Case**: Aggregate HMRC, banking APIs, and internal services into clean graph for frontend consumption.

---

### v0.7.0 - Business Logic Extraction ✅ COMPLETE

**Released**: December 2025

**Focus**: DSL as compression boundary for semantic reasoning

**Design Document**: `docs/design/BUSINESS_LOGIC_EXTRACTION.md`

The DSL serves as a **compression boundary** (chokepoint) between high-value LLM reasoning and low-cost mechanical transformation. Apply LLM tokens where they're most valuable—understanding founder intent—while using deterministic code generation for everything derivable mechanically.

#### Core Concept
```
Founder's Vision (natural language)
        │ LLM: semantic extraction (HIGH VALUE)
        ▼
    DSL Specification (structured, validated)
        │ Deterministic: parser + compiler (ZERO COST)
        ▼
    Generated Code (stubs, routes, schemas)
```

#### Rule Layers (in implementation order)

**Layer 1: State Machines** (Phase 1)
```dsl
entity Ticket:
  status: enum(open, assigned, resolved, closed)

  transitions:
    open -> assigned: requires assignee
    assigned -> resolved: requires resolution_note
    resolved -> closed: auto after 7 days OR manual
```
- Grammar extension for `transitions:` block
- IR types for state machine representation
- Guard code generation in service stubs

**Layer 2: Computed Fields** (Phase 2)
```dsl
entity Order:
  line_items: [LineItem]
  subtotal: computed sum(line_items.amount)
  tax: computed subtotal * 0.08
```
- Expression evaluation at parse time
- Lazy vs eager computation strategies
- Cache invalidation rules

**Layer 3: Entity Invariants** (Phase 3)
```dsl
entity Booking:
  start_date: datetime
  end_date: datetime

  invariant: end_date > start_date
  invariant: duration <= 14 days
```
- Cross-field validation rules
- Pre/post condition checking

**Layer 4: Access Rules Enhancement** (Phase 4)
```dsl
entity Document:
  access:
    read: owner OR owner.team OR role(admin)
    write: owner OR role(admin)
    delete: role(admin) AND status != "published"
```
- Complex boolean expressions
- Role and relationship-based access
- Middleware/decorator generation

#### Stub Expansion
Generated stubs include:
- Type-safe method signatures from DSL
- Validation guards from constraints/invariants
- Transition checks from state machines
- TODO markers for custom logic escape hatches
- Docstrings explaining expected behavior

#### Design Principles
- **Declarative over imperative**: Rules describe "what" not "how"
- **Bounded expressiveness**: DSL is intentionally not Turing-complete
- **Composable primitives**: Complex rules from simple building blocks
- **Explicit escape hatches**: Custom code clearly marked, typed stubs generated

#### Success Criteria
- 80% of business logic expressible in DSL without escape hatches
- Generated code readable without DSL knowledge
- Property-based tests auto-generated from rule definitions
- Token cost front-loaded: pay once for spec, free transformation thereafter

**Estimate**: 8-10 weeks

---

### v0.7.1 - LLM Cognition & DSL Generation Enhancement ✅ COMPLETE

**Released**: December 2025

**Focus**: DSL features that improve LLM comprehension and generation quality

**Design Document**: `docs/design/LLM_COGNITION_DSL_v0.7.1.md`

The core insight: LLMs reason better from **purpose → implementation** than from structure alone. These features make semantic intent explicit at every level of the DSL.

#### P0 Features (High Impact, Low Effort)

**Intent Declarations**
```dsl
entity Order "Order":
  intent: "Track customer purchases through fulfillment lifecycle"
  # LLM validates fields against stated purpose
```

**Example Data**
```dsl
entity Priority "Priority":
  level: enum[low,medium,high,critical]

  examples:
    - {level: low, label: "Nice to have", color: "#22c55e"}
    - {level: critical, label: "Production down", color: "#ef4444"}
```

**Validation Messages**
```dsl
invariant: end_date > start_date
  message: "Check-out must be after check-in"
  code: INVALID_DATE_RANGE
```

#### P1 Features (Medium Effort)

**Domain Hints / Semantic Tags**
```dsl
entity Invoice "Invoice":
  domain: financial
  patterns: audit_trail, lifecycle, soft_delete
```

**Archetypes (Template Inheritance)**
```dsl
archetype Auditable:
  created_at: datetime auto_add
  updated_at: datetime auto_update
  created_by: ref User

entity Invoice "Invoice":
  extends: Auditable
```

**Relationship Semantics**
```dsl
entity Order "Order":
  customer: ref Customer required          # Reference
  items: has_many OrderItem cascade        # Owned, delete together
  shipping_address: embeds Address         # Embedded value
```

#### P2 Features (Higher Effort)

**Negative Constraints (Anti-patterns)**
```dsl
entity User "User":
  manager: ref User

  deny:
    - self_reference(manager)     # user.manager != user
    - circular_ref(manager, 3)    # No deep circular chains
```

**Scenario Definitions**
```dsl
scenarios:
  happy_path:
    given: {status: open, assignee: null}
    when: assign(user_1)
    then: {status: assigned, assignee: user_1}

  blocked_transition:
    given: {status: open}
    when: resolve()
    then: error(REQUIRES_ASSIGNEE)
```

**Derivation Chains**
```dsl
deadline: computed created_at + hours(sla_hours)
is_overdue: computed now() > deadline and status != closed
urgency: computed case(is_overdue -> "p1", default -> priority)
```

#### P3 Features (Future)

**Cross-Entity Rules**
```dsl
rule OrderFulfillment:
  when: Order.status changes to shipped
  then:
    - Inventory.quantity -= Order.items.quantity
    - Notification.create(recipient: Order.customer, message: "Shipped!")
```

#### Delivered (All P0/P1)
- [x] Intent declarations on entities
- [x] Domain and patterns semantic tags
- [x] Archetypes with extends inheritance
- [x] Example data blocks
- [x] Invariant messages and codes
- [x] Relationship semantics (has_many, has_one, embeds, belongs_to)
- [x] Delete behaviors (cascade, restrict, nullify, readonly)
- [x] MCP semantic index with all v0.7.1 concepts
- [x] 5 example projects updated

---

### v0.7.2 - Ejection Toolchain ✅ COMPLETE

**Released**: December 2025

**Focus**: Generate standalone code from DNR applications

**Design Document**: `docs/design/EJECTION_TOOLCHAIN_v0.7.2.md`

The Ejection Toolchain provides a path from DNR runtime to standalone generated code when projects outgrow the native runtime or have deployment constraints requiring traditional application structure.

#### Core Concept
```
DNR Runtime (default)     →     Ejected Code (optional)
─────────────────────────────────────────────────────────
Fast iteration                  Full customization
Zero config                     Framework-specific
Live from DSL                   Traditional deployment
```

#### When to Eject
- Deploying to infrastructure that can't run Docker/DNR
- Needing deep integration with framework-specific features
- Performance profiling reveals DNR overhead is unacceptable
- Compliance requires auditable, version-controlled application code

#### Configuration (extends dazzle.toml)
```toml
[ejection]
enabled = true

[ejection.backend]
framework = "fastapi"
models = "pydantic-v2"

[ejection.frontend]
framework = "react"
api_client = "zod-fetch"

[ejection.testing]
contract = "schemathesis"
```

#### CLI Commands
```bash
dazzle eject              # Generate standalone code
dazzle eject --backend    # Backend only
dazzle eject --frontend   # Frontend only
dazzle eject --dry-run    # Preview without writing
```

#### Key Features
- **AppSpec as Source**: Generate directly from AppSpec, not OpenAPI intermediate
- **Business Logic Included**: State machines, invariants, access rules all generated
- **DNR Component Reuse**: Optional import of DNR components for consistency
- **Framework Adapters**: FastAPI (initial), Django/Flask/Vue/Next.js (future)
- **Test Generation**: Schemathesis contract tests, state machine tests, invariant tests

#### Delivered
- [x] Ejection config parser (`dazzle.toml` `[ejection]` section)
- [x] Adapter registry with pluggable generators
- [x] FastAPI backend adapter (models, schemas, routes, guards, validators, access)
- [x] React frontend adapter (TypeScript types, Zod schemas, TanStack Query hooks)
- [x] Testing adapters (Schemathesis contract tests, Pytest unit tests)
- [x] CI adapters (GitHub Actions, GitLab CI)
- [x] OpenAPI 3.1 generation from AppSpec
- [x] EjectionRunner orchestration
- [x] Post-ejection verification (no Dazzle imports, no template markers)
- [x] `.ejection.json` metadata file
- [x] CLI: `eject run`, `eject status`, `eject adapters`, `eject openapi`, `eject verify`
- [x] 35 unit tests

---

### v0.8.0 - Bun CLI Framework ✅ COMPLETE

**Released**: December 2025

**Focus**: Complete CLI rewrite using Bun for 50x faster startup

#### Delivered

**New CLI Architecture**:
- Bun-compiled binary (57MB, single file)
- 20ms startup (vs 1000ms+ Python CLI)
- JSON-first output for LLM integration
- `__agent_hint` fields in errors for AI remediation

**New Commands**:
| Old Command | New Command |
|-------------|-------------|
| `dazzle init` | `dazzle new` |
| `dazzle dnr serve` | `dazzle dev` |
| `dazzle validate` | `dazzle check` |
| `dazzle inspect` | `dazzle show` |
| `dazzle dnr test` | `dazzle test` |
| `dazzle eject run` | `dazzle eject` |
| `dazzle dnr migrate` | `dazzle db` |

**Distribution**:
- GitHub Releases with 4 platform binaries (darwin-arm64, darwin-x64, linux-arm64, linux-x64)
- Homebrew tap updated (`brew install manwithacat/tap/dazzle`)
- VS Code extension v0.8.0 with new command mappings

**Technical Details**:
- TypeScript CLI compiled with `bun build --compile`
- Python bridge for DSL parsing via subprocess
- `python -m dazzle` invocation for CI compatibility
- Cross-compilation from ARM to x64 in GitHub Actions

#### Compatibility
- Python backend unchanged (FastAPI/SQLite)
- DSL parser remains Python (no rewrite)
- All Python tests continue to pass

---

### v0.9.0 - Messaging Channels

**Status**: In Progress
**Focus**: Unified messaging abstraction for email, queues, and event streams

**Design Documents**:
- `dev_docs/RFC-001-messaging-channels.md` - Main architecture
- `dev_docs/RFC-001-messaging-grammar.ebnf` - Grammar extensions
- `dev_docs/RFC-001-provider-detection.md` - Auto-detection system
- `dev_docs/RFC-001-mcp-prompting-strategy.md` - LLM guidance
- `dev_docs/RFC-001-llm-email-interaction.md` - MCP tools for email testing
- `dev_docs/RFC-001-design-decisions.md` - Architectural stances

#### Core Concepts

**Message Schemas** (first-class DSL construct):
```dsl
message OrderConfirmation "Order Confirmation Email":
  to: email required
  order_number: str required
  items: list[OrderItem] required
  total: money required
```

**Channels** (unified send/receive):
```dsl
channel notifications:
  kind: email           # email | queue | stream
  provider: auto        # mailpit locally, sendgrid in prod

  send order_confirmation:
    message: OrderConfirmation
    when: entity Order status -> confirmed
    delivery_mode: outbox  # transactional guarantee
    mapping:
      to -> Order.customer.email
      order_number -> Order.order_number

  receive support_ticket:
    message: InboundEmail
    match:
      to: "support@{{app.domain}}"
    action: create SupportTicket
    mapping:
      from -> requester_email
      subject -> title
```

#### Channel Kinds

| Kind | Dev Provider | Prod Providers | Use Case |
|------|--------------|----------------|----------|
| `email` | Mailpit, FileProvider | SendGrid, SES, SMTP | User notifications, transactional email |
| `queue` | In-memory | RabbitMQ, SQS | Async processing, reliable delivery |
| `stream` | In-memory | Kafka, Redis Streams | Event sourcing, audit logs, real-time |

#### Key Design Decisions

1. **No Schema Evolution**: Messages carry `_dazzle.build_id` for observability. Migration handled post-eject.

2. **Transactional Outbox**: Default `delivery_mode: outbox` writes to outbox table in same transaction. Background worker dispatches. `delivery_mode: direct` for fire-and-forget.

3. **DSL-Native Templates**: Restricted Jinja-ish syntax (`{{ user.name }}`, simple `{% if %}`). No loops, filters, or math. Compiles to target engine.

4. **Resource-Based Attachments**: `asset` for static files, `document` for entity-bound generated files. No storage paths in DSL.

5. **Two-Layer Rate Limiting**: Provider limits in `provider_config` (operational). Business throttles (`per_recipient`, `per_entity`) first-class in DSL.

#### Implementation Phases

**Phase 1: Core Infrastructure**
- [ ] DSL parser extensions for `message` and `channel` constructs
- [ ] IR types: `MessageSpec`, `ChannelSpec`, `ChannelOperationSpec`
- [ ] Provider detection framework with auto-discovery

**Phase 2: Email Channel (Mailpit First)**
- [ ] Mailpit provider (SMTP send, HTTP API read)
- [ ] FileEmailProvider fallback (`.dazzle/mail/`)
- [ ] Dazzle Bar integration with Mailpit panel
- [ ] CLI: `dazzle channel list`, `dazzle channel send`, `dazzle channel inbox`

**Phase 3: Outbox & Templates**
- [ ] `_dazzle_message_outbox` table generation
- [ ] Background outbox dispatcher worker
- [ ] Template parser with restricted syntax
- [ ] Template compilation to Jinja2

**Phase 4: Queue & Stream Channels**
- [ ] In-memory queue/stream providers
- [ ] RabbitMQ provider
- [ ] Redis Streams provider

**Phase 5: MCP & LLM Integration**
- [ ] `suggest_channels` tool with pattern detection
- [ ] `get_channel_status` tool
- [ ] `send_test_email`, `get_mailpit_messages`, `simulate_inbound_email` tools
- [ ] Inference hints for channel-related keywords

**Phase 6: Throttling & Assets**
- [ ] Business throttle enforcement (`per_recipient`, `per_entity`)
- [ ] `asset` and `document` declarations
- [ ] Attachment handling in email sends

---

### v0.10.0 - API Knowledgebase & Integration Assistant

**Status**: Planned
**Focus**: Curated API definitions and LLM-assisted integration setup

**Design Document**: `dev_docs/api_definition_chair_keyboard_interface.md`

#### Core Concept

The API Knowledgebase provides pre-baked, tested configurations for common external APIs. Instead of an LLM hallucinating endpoints or parsing OpenAPI specs at runtime, we maintain curated "packs" for popular services.

```
Founder Intent (natural language)
        │ LLM: extract api_intent (HIGH VALUE)
        ▼
    API Knowledgebase (curated packs)
        │ Deterministic: load pre-tested config (ZERO COST)
        ▼
    DSL service/integration blocks
```

#### API Knowledgebase Structure

```
src/dazzle/api_kb/
  __init__.py
  loader.py           # Load and query packs
  stripe/
    payments.toml     # Stripe payments pack
    billing.toml      # Stripe billing pack
  hmrc/
    mtd_vat.toml      # HMRC MTD VAT pack
  companies_house/
    lookup.toml       # Companies House lookup
  xero/
    accounting.toml   # Xero accounting pack
```

Each pack contains:
- Pre-validated `service_ir` fragment
- DSL template for `service` block
- Required environment variables
- Common `foreign_model` definitions
- Test fixtures for integration testing

#### Key Features

**1. Curated API Packs**
```toml
# api_kb/stripe/payments.toml
[pack]
name = "stripe_payments"
provider = "Stripe"
category = "payments"
version = "2024-01-01"

[auth]
type = "api_key"
header = "Authorization"
prefix = "Bearer"
env_var = "STRIPE_SECRET_KEY"

[operations]
create_payment_intent = { method = "POST", path = "/v1/payment_intents" }
confirm_payment = { method = "POST", path = "/v1/payment_intents/{id}/confirm" }
list_payments = { method = "GET", path = "/v1/charges" }

[env_vars]
STRIPE_SECRET_KEY = { required = true, description = "Stripe secret key (sk_...)" }
STRIPE_WEBHOOK_SECRET = { required = false, description = "Webhook signing secret" }
```

**2. .env.example Generation**
When services are added to a project, automatically generate `.env.example`:
```bash
# Stripe (stripe_payments pack)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# HMRC (hmrc_mtd_vat pack)
HMRC_CLIENT_ID=
HMRC_CLIENT_SECRET=
```

**3. MCP Tools for Integration**
```
lookup_api_pack      - Query available packs by category or provider
suggest_integration  - Analyze intent and recommend packs
get_pack_config      - Get full pack configuration
validate_env_vars    - Check required environment variables are set
```

**4. DSL Generation from Packs**
```dsl
# Auto-generated from stripe_payments pack
service stripe "Stripe Payments":
  pack: stripe_payments
  auth_profile: api_key header="Authorization" key_env="STRIPE_SECRET_KEY"

foreign_model PaymentIntent from stripe "Payment Intent":
  key: id
  constraint cache ttl="60"

  id: str(50) required pk
  amount: int required
  currency: str(3) required
  status: enum[requires_payment_method,requires_confirmation,succeeded,canceled]
```

#### Implementation Phases

**Phase 1: Core Infrastructure**
- [ ] Create `api_kb/` package structure
- [ ] Pack loader with TOML parsing
- [ ] Environment variable registry
- [ ] `.env.example` generator in `dazzle new`

**Phase 2: Initial Packs (UK Focus)**
- [ ] Stripe payments pack
- [ ] HMRC MTD VAT pack
- [ ] Companies House lookup pack
- [ ] Xero accounting pack (basic)

**Phase 3: MCP Integration**
- [ ] `lookup_api_pack` tool
- [ ] `suggest_integration` tool with intent matching
- [ ] `get_pack_config` tool
- [ ] `validate_env_vars` tool

**Phase 4: DSL Generation**
- [ ] Generate `service` blocks from packs
- [ ] Generate `foreign_model` blocks from pack schemas
- [ ] Generate `integration` actions from pack operations

**Phase 5: Testing & Documentation**
- [ ] Mock server fixtures per pack
- [ ] Integration test templates
- [ ] Pack contribution guide

#### Success Criteria

- 5+ curated packs for common UK business APIs
- `dazzle new` generates `.env.example` with all service env vars
- MCP tools enable LLM to recommend and configure integrations
- Zero hallucinated endpoints - all from curated packs

---

### v1.0.0 - Dazzle Orchestrator Control Plane

**Focus**: Hosted control plane for production app management

**Spec Document**: `dev_docs/orchestrator-control-plane-spec-v1.md`

This is a **major version** representing the shift from CLI tool to hosted platform.

#### Architecture
```
┌─────────────────────────────────────────┐
│            CONTROL PLANE                │
│  Dazzle Server + Dazzle-DB + Worker     │
└───────────────────┬─────────────────────┘
                    │ manages
┌───────────────────▼─────────────────────┐
│              DATA PLANE                 │
│       App (FastAPI) + App DB            │
└─────────────────────────────────────────┘
```

#### Core Domain Models
- **SpecVersion**: Immutable DSL/AppSpec snapshots
- **AppSpecDiff**: Semantic differences between versions
- **MigrationPlan**: Proposed execution plan (DB + code + deploy)
- **MigrationRun**: Execution instance with logs/status
- **Deployment**: Current/historical deployment state per environment

#### Founder Web UI
- Dashboard with environment status
- Spec Editor (structured + raw DSL)
- Diff & Plan View with risk assessment
- Deployment View with rollback capability
- Chat/Companion Pane for LLM-assisted changes

#### Safe Migration Patterns
- Backwards-compatible-first principle
- Blue/green deployments
- Snapshot-based recovery for destructive migrations
- Pre/post health checks

#### LLM Integration
- Natural language → DSL changes (with validation)
- Migration plan explanation
- Strict safety rails on LLM output

**Estimate**: 12-16 weeks

---

### v1.1.0 - Multi-Platform (Q2 2027)

**Focus**: Beyond web applications

**Planned Features**:
- React Native runtime (mobile)
- Desktop app packaging (Electron/Tauri)
- Offline-first patterns
- Cross-platform sync

**Rationale**: Multi-platform support is deferred until after the Control Plane is established, as the orchestration layer will provide the deployment and management infrastructure needed for mobile and desktop apps.

**Estimate**: 10-12 weeks

---

## Deprecated Features

The following are **deprecated** as of v0.3.0 in favor of DNR:

| Stack | Status | Recommendation |
|-------|--------|----------------|
| `django_micro` | Deprecated | Use DNR |
| `django_micro_modular` | Deprecated | Use DNR |
| `django_api` | Deprecated | Use DNR |
| `express_micro` | Deprecated | Use DNR |
| `nextjs_onebox` | Deprecated | Use DNR |
| `nextjs_semantic` | Deprecated | Use DNR |
| `openapi` | Available | For API spec export only |
| `terraform` | Available | For infrastructure |
| `docker` | In Progress | For DNR deployment |

**Migration Path**: Existing projects using legacy stacks should migrate to DNR. The DSL syntax is fully compatible—only the runtime changes.

---

## Development Roadmap Files

For detailed phase planning, see:

| File | Purpose |
|------|---------|
| `dev_docs/roadmap_v0_3_0.md` | v0.3.0 UI Layout Engine phases |
| `dev_docs/roadmap_v0_3_0_phase5.md` | Phase 5 advanced archetypes |
| `dev_docs/roadmap_v0_4_0_dnr.md` | DNR runtime architecture |
| `dev_docs/DNR-Back-GraphQL-Spec-v1.md` | GraphQL BFF specification (v0.6.0) |
| `docs/design/BUSINESS_LOGIC_EXTRACTION.md` | Business logic extraction design (v0.7.0) |
| `dev_docs/orchestrator-control-plane-spec-v1.md` | Control plane specification (v1.0.0) |
| `docs/design/LLM_COGNITION_DSL_v0.7.1.md` | LLM Cognition DSL features (v0.7.1) |
| `docs/design/EJECTION_TOOLCHAIN_v0.7.2.md` | Ejection Toolchain specification (v0.7.2) |
| `dev_docs/future_features_analysis.md` | Analysis and context for future features |

---

## Success Metrics

### v0.5.0 Success Criteria ✅ ALL MET

- [x] Inline access rules in entity definitions
- [x] `access:` block parsing with `read:` and `write:` rules
- [x] Component roles (presentational/container) with inference
- [x] Action purity (pure/impure) with inference
- [x] All features backward compatible
- [x] 35 new unit tests, 530 total passing
- [x] No regressions from v0.4.0

### v0.4.0 Success Criteria ✅ ALL MET

- [x] `dazzle dnr serve` starts a real app with persistence
- [x] CRUD operations work end-to-end
- [x] Authentication and authorization functional
- [x] File uploads and rich text work
- [x] Real-time updates in browser
- [x] 5 layout archetypes implemented
- [x] Hot reload with `--watch` flag
- [x] Dev tools panel in browser
- [x] `dazzle dnr test` with contract/benchmark/a11y testing
- [x] `dazzle dnr build` produces Docker-ready bundles
- [x] `dazzle dnr migrate` for production database updates
- [x] Kubernetes health probes (`/_dnr/live`, `/_dnr/ready`)

### Overall Health Metrics

- Test coverage: >85%
- Cold start time: <3 seconds
- Build time: <10 seconds for typical project
- Zero configuration required for basic apps

---

## Contributing

**Current Opportunities**:

1. **DNR Testing**: Run your projects with DNR, report issues
2. **Example Projects**: Create domain-specific examples
3. **Documentation**: Improve guides and tutorials
4. **Custom Stacks**: Build on `base` builder for specific frameworks

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Resources

- **Repository**: https://github.com/manwithacat/dazzle
- **Documentation**: `docs/` directory
- **Examples**: `examples/` directory
- **Issues**: GitHub Issues

---

**Document Owner**: Claude + James
**Last Review**: 2025-12-11
**Next Review**: Q1 2026 (v0.9.0 completion)

---

## Changelog

### 2025-12-11 (v0.10.0 Planned - API Knowledgebase)
- **v0.10.0 PLANNED**: API Knowledgebase & Integration Assistant
  - Curated API packs for common external services (Stripe, HMRC, Xero, etc.)
  - Pre-validated service configurations to avoid LLM hallucination
  - `.env.example` generation from service env var requirements
  - MCP tools: `lookup_api_pack`, `suggest_integration`, `validate_env_vars`
  - DSL generation from packs (`service` and `foreign_model` blocks)
  - Design document: `dev_docs/api_definition_chair_keyboard_interface.md`
- **v0.9.3 Released**: Documentation overhaul
  - Complete DSL reference guide in `docs/reference/` (11 files)
  - README updated with comprehensive DSL constructs overview
  - Renamed docs/v0.7 to docs/v0.9

### 2025-12-11 (v0.9.0 Started - Messaging Channels)
- **v0.9.0 IN PROGRESS**: Messaging Channels
  - Unified messaging abstraction for email, queues, and event streams
  - `message` construct for typed, reusable message schemas
  - `channel` construct with `kind: email | queue | stream`
  - Provider auto-detection (Mailpit locally, SendGrid/SQS/Kafka in prod)
  - Transactional outbox pattern as default (`delivery_mode: outbox | direct`)
  - DSL-native template language (restricted Jinja-ish syntax)
  - Resource-based attachments (`asset`, `document`)
  - Two-layer rate limiting (provider config vs business throttles)
  - MCP tools for LLM-driven email testing
  - Dazzle Bar integration with Mailpit panel
- Design documents created in `dev_docs/RFC-001-*`

### 2025-12-10 (v0.7.1 + v0.7.2 Complete)
- **v0.7.1 COMPLETE**: LLM Cognition & DSL Generation Enhancement
  - Intent declarations on entities (`intent: "..."`)
  - Domain and patterns semantic tags (`domain: billing`, `patterns: lifecycle, audit`)
  - Archetypes with extends inheritance (`archetype Timestamped`, `extends: Timestamped`)
  - Example data blocks (`examples: [{...}]`)
  - Invariant messages and codes (`message: "...", code: ERROR_CODE`)
  - Relationship semantics (`has_many`, `has_one`, `embeds`, `belongs_to`)
  - Delete behaviors (`cascade`, `restrict`, `nullify`, `readonly`)
  - Updated MCP semantic index with all v0.7.1 concepts
  - Updated glossary with LLM Cognition section
- **v0.7.2 COMPLETE**: Ejection Toolchain
  - Ejection config parser for `dazzle.toml` `[ejection]` section
  - Adapter registry with pluggable generators
  - FastAPI backend adapter (models, schemas, routes, guards, validators, access)
  - React frontend adapter (TypeScript types, Zod schemas, TanStack Query hooks)
  - Testing adapters (Schemathesis contract tests, Pytest unit tests)
  - CI adapters (GitHub Actions, GitLab CI)
  - OpenAPI 3.1 generation from AppSpec
  - Post-ejection verification (no Dazzle imports, no template markers)
  - `.ejection.json` metadata file for audit trail
  - CLI commands: `eject run`, `eject status`, `eject adapters`, `eject openapi`, `eject verify`
  - 35 unit tests for ejection module
- **README Updated**: New vision statement reflecting DSL as compression boundary
- **Roadmap Simplified**: Two paths from DSL (DNR for iteration, Ejection for production)

### 2025-12-10 (v0.7.0 Complete + v0.7.1 Planned)
- **v0.7.0 COMPLETE**: Business Logic Extraction features delivered
  - State machines for entity lifecycle
  - Computed fields for derived values
  - Invariants for data integrity
  - Access rules for visibility/permissions
  - All 5 example projects upgraded with v0.7 features
  - 756 tests passing
- **v0.7.1 PLANNED**: LLM Cognition & DSL Generation Enhancement
  - Design document: `docs/design/LLM_COGNITION_DSL_v0.7.1.md`
  - P0: Intent declarations, example data, validation messages
  - P1: Domain tags, archetypes, relationship semantics
  - P2: Anti-patterns, scenarios, derivation chains
  - P3: Cross-entity rules
  - Focus: Make semantic intent explicit for better LLM generation
- Updated current version to v0.7.0

### 2025-12-09 (v0.6.0 Complete - GraphQL BFF Layer)
- **v0.6.0 COMPLETE**: All GraphQL BFF Layer features delivered
- Fixed Strawberry type generation for dynamic Query/Mutation fields
- Created typed resolver factory functions with proper `__annotations__`
- GraphQL integration tests with 7 real query tests
- All CI passing (687 unit tests + 7 integration tests)
- Updated current version to v0.6.0

### 2025-12-09 (Roadmap Update - v0.7.0 & v0.8.0 Defined)
- **v0.7.0 Redefined**: Business Logic Extraction (was "Full GraphQL Builder")
  - DSL as compression boundary for semantic reasoning
  - State machines, computed fields, invariants, access rules
  - Design document: `docs/design/BUSINESS_LOGIC_EXTRACTION.md`
- **v0.8.0 Added**: Bun CLI Framework
  - Refactor CLI tooling to use Bun runtime
  - TypeScript-first CLI with faster startup
  - Phased migration maintaining Python backend

### 2025-12-03 (GraphQL BFF Layer - v0.6.0 Started)
- **v0.6.0 IN PROGRESS**: GraphQL BFF Layer implementation begun
- GraphQL module structure: `src/dazzle_dnr_back/graphql/`
- GraphQLContext: Multi-tenant context with role-based access control
- SchemaGenerator: Generate Strawberry types from BackendSpec
- ResolverGenerator: Generate CRUD resolvers with tenant isolation
- FastAPI Integration: `mount_graphql()`, `create_graphql_app()`
- CLI: `--graphql` flag for `dazzle dnr serve`
- Unit tests: 12 context tests, 14 Strawberry-dependent tests (skipped when not installed)
- All 582 unit tests passing

### 2025-12-03 (Anti-Turing Extensibility)
- **Anti-Turing Extensibility Model**: Three-layer architecture complete
- Domain Service DSL: `service` with `kind`, `input`, `output`, `guarantees`, `stub`
- Service Kinds: domain_logic, validation, integration, workflow
- ServiceLoader: Runtime discovery of Python stubs
- Stub Generation: `dazzle stubs generate` command
- EBNF Grammar: Restricted to aggregate functions only
- 71+ new tests (14 domain service + 17 service loader + others)
- 601 total tests passing
- Documentation: `docs/EXTENSIBILITY.md`

### 2025-12-02 (v0.5.0 Release)
- **v0.5.0 COMPLETE**: All Advanced DSL Features delivered
- Inline Access Rules: `access:` block with `read:`/`write:` rules
- Component Roles: presentational/container with auto-inference
- Action Purity: pure/impure with auto-inference
- 35 new tests (8 access rules + 13 component roles + 14 action purity)
- 530 total tests passing, no regressions
- Updated current version to v0.5.0
- **Roadmap restructure**: Multi-Platform moved to v1.1.0 (after Control Plane)
  - v0.6.0: GraphQL BFF Layer (was v0.7.0)
  - v0.7.0: Full GraphQL Builder (was v0.8.0)
  - v1.0.0: Control Plane (unchanged)
  - v1.1.0: Multi-Platform (was v0.6.0)

### 2025-12-02 (Evening)
- Added future roadmap items v0.7.0, v0.8.0, v1.0.0
- **v0.7.0**: GraphQL BFF Layer (Q4 2026) - API aggregation/facade pattern
- **v0.8.0**: Full GraphQL Builder (Q1 2027) - Schema generation from BackendSpec
- **v1.0.0**: Dazzle Orchestrator Control Plane (Q2 2027) - Hosted platform
- Created `dev_docs/future_features_analysis.md` with implementation context
- Updated roadmap files table with spec documents

### 2025-12-02
- **v0.4.0 COMPLETE**: All DNR Production Ready features delivered
- Marked v0.3.3 (Developer Experience) as complete
- Marked v0.4.0 (Production Ready) as complete
- Updated current version to v0.4.0
- New features: `dazzle dnr build`, `dazzle dnr migrate`, `dazzle dnr test`
- Health probes: `/_dnr/live`, `/_dnr/ready`
- Updated success criteria for v0.4.0

### 2025-11-28
- **MAJOR REWRITE**: Aligned roadmap with actual development reality
- Consolidated v0.2.0 (UX Semantic Layer) as complete
- Positioned v0.3.0 as DNR + Layout Engine release (current)
- Deprecated legacy code generation stacks
- Updated future versions (v0.3.1, v0.4.0, v0.5.0, v0.6.0)
- Removed obsolete v0.2.1, v0.2.2 plans (superseded by DNR)
- Added deprecation table for legacy stacks

### 2025-11-25
- Previous version with stack-based roadmap
