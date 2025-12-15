# Changelog

All notable changes to DAZZLE will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.15.0] - 2025-12-15

### Added
- **Interactive CLI Commands**: New user-friendly interactive modes
  - `dazzle init`: Interactive project wizard with guided setup
  - `dazzle doctor`: Environment diagnostics with automatic fixes
  - `dazzle explore`: Interactive DSL explorer with syntax examples
  - `dazzle kb`: Knowledgebase browser for DSL concepts and patterns

### Changed
- CLI version bumped to 0.15.0

---

## [0.14.0] - 2025-12-14

### Added
- **MCP Commands Restored**: Full MCP server functionality in Bun CLI
  - `dazzle mcp`: Run MCP server for Claude Code integration
  - `dazzle mcp-setup`: Register MCP server with Claude Code
  - `dazzle mcp-check`: Check MCP server status
- **Deterministic Port Allocation**: DNR serve now uses deterministic ports based on project path
- **Semantic E2E Attributes**: Added `data-dazzle-*` attributes for E2E testability

---

## [0.9.3] - 2025-12-11

### Added
- **Documentation Overhaul**
  - Complete DSL reference guide in `docs/reference/` (11 files)
  - Comprehensive README with DSL constructs overview
  - Renamed docs/v0.7 to docs/v0.9

---

## [0.8.0] - 2025-12-09

### Added
- **Bun CLI Framework**: Complete CLI rewrite for 50x faster startup
  - Bun-compiled binary (57MB, single file)
  - 20ms startup vs 1000ms+ Python CLI
  - JSON-first output for LLM integration
  - `__agent_hint` fields in errors for AI remediation

### Changed
- **Command Mappings**:
  | Old Command | New Command |
  |-------------|-------------|
  | `dazzle init` | `dazzle new` |
  | `dazzle dnr serve` | `dazzle dev` |
  | `dazzle validate` | `dazzle check` |
  | `dazzle inspect` | `dazzle show` |
  | `dazzle dnr test` | `dazzle test` |
  | `dazzle eject run` | `dazzle eject` |
  | `dazzle dnr migrate` | `dazzle db` |

### Distribution
- GitHub Releases with 4 platform binaries (darwin-arm64, darwin-x64, linux-arm64, linux-x64)
- Homebrew tap updated (`brew install manwithacat/tap/dazzle`)
- VS Code extension v0.8.0 with new command mappings

---

## [0.7.2] - 2025-12-10

### Added
- **Ejection Toolchain**: Generate standalone code from DNR applications
  - Ejection config parser for `dazzle.toml` `[ejection]` section
  - Adapter registry with pluggable generators
  - FastAPI backend adapter (models, schemas, routes, guards, validators, access)
  - React frontend adapter (TypeScript types, Zod schemas, TanStack Query hooks)
  - Testing adapters (Schemathesis contract tests, Pytest unit tests)
  - CI adapters (GitHub Actions, GitLab CI)
  - OpenAPI 3.1 generation from AppSpec
  - Post-ejection verification (no Dazzle imports, no template markers)
  - `.ejection.json` metadata file for audit trail
  - CLI: `eject run`, `eject status`, `eject adapters`, `eject openapi`, `eject verify`
  - 35 unit tests

---

## [0.7.1] - 2025-12-10

### Added
- **LLM Cognition & DSL Generation Enhancement**
  - Intent declarations on entities (`intent: "..."`)
  - Domain and patterns semantic tags (`domain: billing`, `patterns: lifecycle, audit`)
  - Archetypes with extends inheritance (`archetype Timestamped`, `extends: Timestamped`)
  - Example data blocks (`examples: [{...}]`)
  - Invariant messages and codes (`message: "...", code: ERROR_CODE`)
  - Relationship semantics (`has_many`, `has_one`, `embeds`, `belongs_to`)
  - Delete behaviors (`cascade`, `restrict`, `nullify`, `readonly`)
  - Updated MCP semantic index with all v0.7.1 concepts
  - 5 example projects updated

---

## [0.7.0] - 2025-12-10

### Added
- **Business Logic Extraction**: DSL as compression boundary for semantic reasoning
  - State machines for entity lifecycle (`transitions:` block)
  - Computed fields for derived values (`computed` keyword)
  - Invariants for data integrity (`invariant:` rules)
  - Access rules for visibility/permissions
  - All 5 example projects upgraded with v0.7 features
  - 756 tests passing

---

## [0.6.0] - 2025-12-09

### Added
- **GraphQL BFF Layer**: API aggregation and external service facade
  - GraphQLContext: Multi-tenant context with role-based access control
  - SchemaGenerator: Generate Strawberry types from BackendSpec
  - ResolverGenerator: Generate CRUD resolvers with tenant isolation
  - FastAPI Integration: `mount_graphql()`, `create_graphql_app()`
  - CLI: `--graphql` flag for `dazzle dnr serve`
  - `dazzle dnr inspect --schema` command
  - External API Adapters with retry logic and rate limiting
  - Error normalization with unified error model
  - 53 unit tests for adapter interface
  - 7 GraphQL integration tests

---

## [0.5.0] - 2025-12-02

### Added
- **Anti-Turing Extensibility Model**
  - Domain Service DSL: `service` with `kind`, `input`, `output`, `guarantees`, `stub`
  - Service Kinds: domain_logic, validation, integration, workflow
  - ServiceLoader: Runtime discovery of Python stubs
  - Stub Generation: `dazzle stubs generate` command
  - EBNF Grammar: Restricted to aggregate functions only
  - Documentation: `docs/EXTENSIBILITY.md`
  - 31 new tests (14 domain service + 17 service loader)

- **Inline Access Rules**
  - New `access:` block syntax in entity definitions
  - `read:` rule for visibility/view access control
  - `write:` rule for create/update/delete permissions
  - 8 unit tests

- **Component Roles** (UISpec)
  - `ComponentRole` enum: PRESENTATIONAL, CONTAINER
  - Auto-inference based on state and actions
  - 13 unit tests

- **Action Purity** (UISpec)
  - `ActionPurity` enum: PURE, IMPURE
  - Auto-inference based on effects
  - 14 unit tests

### Status
- 601 tests passing

---

## [0.4.0] - 2025-12-02

### Added
- **DNR Production Ready**
  - `dazzle dnr test` command for API contract testing
  - `--benchmark` option for performance testing
  - `--a11y` option for WCAG accessibility testing
  - `dazzle dnr build` for production bundles
  - Multi-stage Dockerfile generation
  - docker-compose.yml for local deployment
  - `dazzle dnr migrate` for database migrations
  - Kubernetes health probes (`/_dnr/live`, `/_dnr/ready`)

---

## [0.3.3] - 2025-12

### Added
- **DNR Developer Experience**
  - DSL file watching with instant reload (`dazzle dnr serve --watch`)
  - Browser dev tools panel with state/action inspection
  - State inspector with real-time updates
  - Action log with state diff visualization
  - `dazzle dnr inspect` command for spec inspection
  - `dazzle dnr inspect --live` for running server inspection
  - `/_dnr/*` debug endpoints (health, stats, entity details)

---

## [0.3.2] - 2025-12

### Added
- **Semantic E2E Testing Framework** (8 phases complete)
  - DOM Contract: `data-dazzle-*` attributes for semantic locators
  - TestSpec IR: FlowSpec, FlowStep, FlowAssertion, FixtureSpec, E2ETestSpec
  - Auto-Generate E2ETestSpec from AppSpec (CRUD, validation, navigation flows)
  - Playwright Harness: semantic locators, flow execution, domain assertions
  - Test Endpoints: `/__test__/seed`, `/__test__/reset`, `/__test__/snapshot`
  - DSL Extensions: `flow` block syntax with parser support
  - CLI: `dazzle test generate`, `dazzle test run`, `dazzle test list`
  - Usability & Accessibility: axe-core integration, WCAG mapping
  - 61 new tests

---

## [0.3.1] - 2025-12

### Fixed
- **Critical Bug Fixes**
  - ES module export block conversion failure in `js_loader.py`
  - HTML script tag malformation in `js_generator.py`

### Added
- **E2E Testing**
  - E2E tests for DNR serve in `tests/e2e/test_dnr_serve.py`
  - Matrix-based E2E testing for example projects in CI
  - P0 examples (simple_task, contact_manager) block PRs on failure

- **MCP Server Improvements**
  - Getting-started workflow guidance
  - Common DSL patterns documentation
  - Semantic index v0.5.0 with extensibility concepts

---

## [0.3.0] - 2025-11

### Added
- **Dazzle Native Runtime (DNR)**: Major pivot to runtime-first approach

  **DNR Backend**:
  - SQLite persistence with auto-migration
  - FastAPI server with auto-generated CRUD endpoints
  - Session-based auth, PBKDF2 password hashing
  - Row-level security, owner/tenant-based access control
  - File uploads: Local and S3 storage, image processing, thumbnails
  - Rich text: Markdown rendering, HTML sanitization
  - Relationships: Foreign keys, nested data fetching
  - Full-text search: SQLite FTS5 integration
  - Real-time: WebSocket support, presence indicators, optimistic updates

  **DNR Frontend**:
  - Signals-based UI: Reactive JavaScript without virtual DOM
  - Combined server: Backend + Frontend with API proxy
  - Hot reload: SSE-based live updates
  - Vite integration: Production builds

  **UI Semantic Layout Engine**:
  - 5 Archetypes: FOCUS_METRIC, SCANNER_TABLE, DUAL_PANE_FLOW, MONITOR_WALL, COMMAND_CENTER
  - Attention signals with priority weights
  - Engine variants: Classic, Dense, Comfortable
  - `dazzle layout-plan` command
  - Persona-aware layout adjustments

### Changed
- Legacy code generation stacks deprecated in favor of DNR

---

## [0.2.0] - 2025-11

### Added
- **UX Semantic Layer**: Fundamental DSL language enhancement
  - Personas: Role-based surface/workspace variants with scope filtering
  - Workspaces: Composed dashboards with multiple data regions
  - Attention Signals: Data-driven alerts (critical, warning, notice, info)
  - Information Needs: `show`, `sort`, `filter`, `search`, `empty` directives
  - Purpose Statements: Semantic intent documentation
  - MCP Enhancements: Semantic concept lookup, example search

---

## [0.1.1] - 2025-11-23

### Fixed
- **express_micro stack**:
  - Graceful fallback for AdminJS on incompatible Node.js versions (v25+)
  - Node.js version constraints to package.json (`>=18.0.0 <25.0.0`)
  - Missing `title` variable in route handlers
  - Admin interface mounting in server.js
  - Error handling with contextual logging

### Added
- Environment variable support with dotenv
- Generated `.env.example` file

---

## [0.1.0] - 2025-11-22

### Added
- **Initial Release**
  - Complete DSL parser (800+ lines)
  - Full Internal Representation (900+ lines, Pydantic models)
  - Module system with dependency resolution
  - 6 code generation stacks (Django, Express, OpenAPI, Docker, Terraform)
  - LLM integration (spec analysis, DSL generation)
  - LSP server with VS Code extension
  - Homebrew distribution
  - MCP server integration

---

## Deprecated Features

The following are deprecated as of v0.3.0 in favor of DNR:

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
| `docker` | Available | For DNR deployment |
