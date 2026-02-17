# Changelog

All notable changes to DAZZLE will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

## [0.30.0] - 2026-02-17

### Added
- Typed expression language: tokenizer, recursive descent parser, tree-walking evaluator, and type checker for pure-function expressions over entity fields (`src/dazzle/core/expression_lang/`) ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Expression AST types: `Literal`, `FieldRef`, `DurationLiteral`, `BinaryExpr`, `UnaryExpr`, `FuncCall`, `InExpr`, `IfExpr` with full operator precedence ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Field expression defaults: `total: int = subtotal + tax` — computed default values using typed expressions on entity fields ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Cross-entity predicate guards on state transitions with FK arrow path syntax: `guard: self->signatory->aml_status == "completed"` ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Guard message support: `message: "Signatory must pass AML checks"` sub-clause on transition guards ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Block-mode transition parsing: transitions now support indented sub-blocks alongside existing inline syntax ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Process-aware task inbox with step context enrichment showing position in workflows ([#274](https://github.com/manwithacat/dazzle/issues/274))
- Built-in expression functions: `today()`, `now()`, `days_until()`, `days_since()`, `concat()`, `coalesce()`, `abs()`, `min()`, `max()`, `round()`, `len()` ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Invariant expressions consolidated to unified Expr type with `InvariantSpec.invariant_expr` field ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Computed fields consolidated to unified Expr type with `ComputedFieldSpec.computed_expr` field ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Surface field `when:` clause for conditional visibility: `field notes "Notes" when: status == "pending"` ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Duration word-form mapping in expression parser: `14 days` → `14d`, `2 hours` → `2h` ([#275](https://github.com/manwithacat/dazzle/issues/275))

## [0.29.0] - 2026-02-17

### Added
- `sensitive` field modifier for PII masking — auto-masks values in list views, excludes from filters, adds `x-sensitive: true` to OpenAPI schemas ([#263](https://github.com/manwithacat/dazzle/issues/263))
- UI Islands (`island` DSL construct) — self-contained client-side interactive components with typed props, events, entity data binding, and auto-generated API endpoints
- `nightly` MCP tool — parallel quality pipeline with dependency-aware fan-out for faster CI runs
- `sentinel` MCP tool — static failure-mode detection across dependency integrity, accessibility, mapping track, and boundary layer
- `story(scope_fidelity)` operation — verifies implementing processes exercise all entities in story scope, integrated into quality pipeline ([#266](https://github.com/manwithacat/dazzle/issues/266))
- htmx SPA-like UX enhancements: View Transitions API, preload extension, response-targets, loading-states, SSE real-time updates, infinite scroll pagination, optimistic UI feedback, skeleton loading placeholders
- htmx fragment targeting for app navigation — `hx-target="#main-content"` replaces full-body swap for smoother transitions ([#265](https://github.com/manwithacat/dazzle/issues/265))

### Fixed
- Test runner cross-run unique collisions — replaced timestamp-based suffixes with UUID4, regenerate unique fields after design-time overrides ([#262](https://github.com/manwithacat/dazzle/issues/262))
- Persona discovery agent stuck in click loop — extract href from CSS selectors, include element attributes in prompt, start at `/app` not public homepage ([#261](https://github.com/manwithacat/dazzle/issues/261))
- `/_site/nav` authenticated routes returning 404 — fixed double-prefixed page routes and singular slug mismatch ([#260](https://github.com/manwithacat/dazzle/issues/260))
- Entity surface links added to workspace sidebar navigation ([#259](https://github.com/manwithacat/dazzle/issues/259))
- Sitespec review false positives for card_grid, pricing, value_highlight sections ([#258](https://github.com/manwithacat/dazzle/issues/258))
- Visual evaluator false positives from preprocessed images and budget exhaustion ([#257](https://github.com/manwithacat/dazzle/issues/257))
- Sentinel suppress writing invalid status that crashes next scan ([#256](https://github.com/manwithacat/dazzle/issues/256))

## [0.28.2] - 2026-02-16

### Changed
- Split god classes: DazzleBackendApp, KnowledgeGraphHandlers, LiteProcessAdapter into focused sub-classes
- Split large modules: discovery.py and KG handlers.py into packages with focused sub-modules
- Extract BaseEventBus from postgres/redis/sqlite event bus implementations
- Handler factory pattern for consolidated MCP handlers reducing boilerplate
- Centralized path constants in paths.py replacing hardcoded strings
- LSP completion refactored into per-context dispatch for maintainability

### Removed
- Dead tools.py (1623 lines) replaced by tools_consolidated.py

### Fixed
- Error handling in queue/stream adapters for JSON decode and subprocess timeouts
- Type safety: concrete DB return types, TypedDict for structured returns
- ARIA accessibility improvements for generated app interfaces

## [0.28.1] - 2026-02-15

### Fixed
- Composition `analyze` returning false 100/100 when LLM evaluation fails — now returns `visual_score: null` with actual error messages ([#239](https://github.com/manwithacat/dazzle/issues/239))
- Sentinel PR-05 false positives on list surfaces with view-based projections — now counts view fields instead of entity fields ([#238](https://github.com/manwithacat/dazzle/issues/238))
- Sentinel PR-01 false positives for N+1 risk on entities with ref fields — ref fields excluded since runtime auto-eager-loads them ([#238](https://github.com/manwithacat/dazzle/issues/238))

## [0.28.0] - 2026-02-15

### Added
- Agent swarm infrastructure with parallel execution and background tasks ([#224](https://github.com/manwithacat/dazzle/issues/224))
- `--base-url` flag for `dsl-run` to test against remote servers ([#226](https://github.com/manwithacat/dazzle/issues/226))
- File-based MCP activity log for Claude Code progress visibility ([#206](https://github.com/manwithacat/dazzle/issues/206))
- Infrastructure manifest for auto-provisioning services from DSL declarations ([#200](https://github.com/manwithacat/dazzle/issues/200))
- Authenticated UX coherence check for post-login experience validation ([#197](https://github.com/manwithacat/dazzle/issues/197))
- Business priority and revenue-criticality signals on DSL constructs ([#196](https://github.com/manwithacat/dazzle/issues/196))
- Persona-scoped navigation audit to detect admin content shown to all users ([#195](https://github.com/manwithacat/dazzle/issues/195))
- Project-level custom CSS override via `static/css/custom.css` ([#187](https://github.com/manwithacat/dazzle/issues/187))
- CSS computed style inspection for agent-driven layout diagnosis ([#186](https://github.com/manwithacat/dazzle/issues/186))
- Layout geometry extraction via Playwright bounding boxes in composition ([#183](https://github.com/manwithacat/dazzle/issues/183))
- Composition analysis MCP tool with dual-layer DOM audit and visual evaluation ([#180](https://github.com/manwithacat/dazzle/issues/180))
- Pulse tool with story wall, readiness radar, and decision queue for founders ([#178](https://github.com/manwithacat/dazzle/issues/178))
- Summary mode for pipeline and fidelity output for LLM-friendly compact results ([#173](https://github.com/manwithacat/dazzle/issues/173))
- Declarative `themespec.yaml` for deterministic design generation ([#167](https://github.com/manwithacat/dazzle/issues/167))
- Batch MCP operations to reduce round-trips for agent loops ([#165](https://github.com/manwithacat/dazzle/issues/165))
- Responsive testing strategy with structural, viewport, and visual tiers ([#153](https://github.com/manwithacat/dazzle/issues/153))
- MCP entrypoint for agent-driven smoke test authoring and execution ([#148](https://github.com/manwithacat/dazzle/issues/148))
- HX-Trigger response headers for server→client event coordination ([#142](https://github.com/manwithacat/dazzle/issues/142))
- Auto-generated curl smoke test suite from DSL specification ([#138](https://github.com/manwithacat/dazzle/issues/138))
- Per-persona authenticated sessions for testing and ACL verification ([#137](https://github.com/manwithacat/dazzle/issues/137))

### Changed
- Expanded LSP hover and go-to-definition to all DSL construct types ([#235](https://github.com/manwithacat/dazzle/issues/235))
- Context-aware completion suggestions in LSP ([#234](https://github.com/manwithacat/dazzle/issues/234))
- Missing construct keywords added to TextMate grammar for syntax highlighting ([#236](https://github.com/manwithacat/dazzle/issues/236))
- Parser diagnostics published to editor for real-time error feedback ([#232](https://github.com/manwithacat/dazzle/issues/232))
- Auto-eager-load ref fields on list surfaces to prevent N+1 queries ([#231](https://github.com/manwithacat/dazzle/issues/231))
- View projections on list surfaces to reduce column fetch ([#230](https://github.com/manwithacat/dazzle/issues/230))
- Per-test progress and result annotations in Workshop for `dsl_test.run_all` ([#227](https://github.com/manwithacat/dazzle/issues/227))
- CLI command activity written to shared store for Workshop visibility ([#225](https://github.com/manwithacat/dazzle/issues/225))
- UK government identifier detection (NINO, UTR) added to compliance scanner ([#221](https://github.com/manwithacat/dazzle/issues/221))
- Discovery agent now uses MCP sampling instead of direct Anthropic API calls ([#220](https://github.com/manwithacat/dazzle/issues/220))
- Progress feedback, token visibility, and streaming added to MCP tools ([#201](https://github.com/manwithacat/dazzle/issues/201))
- Explicit password option in `create-user` and `reset-password` CLI commands ([#199](https://github.com/manwithacat/dazzle/issues/199))
- Production-grade Docker setup with Postgres, Redis, and Celery ([#198](https://github.com/manwithacat/dazzle/issues/198))
- Orphan experience detection for experiences with no workspace entry point ([#194](https://github.com/manwithacat/dazzle/issues/194))
- Composition audit step added to pipeline for visual hierarchy validation ([#192](https://github.com/manwithacat/dazzle/issues/192))
- Pipeline semantics step returns counts and summaries instead of full schemas ([#190](https://github.com/manwithacat/dazzle/issues/190))
- Perfect-score surfaces omitted from fidelity output to reduce pipeline size ([#189](https://github.com/manwithacat/dazzle/issues/189))
- Hero-balance severity escalated when media is declared but not side-by-side ([#188](https://github.com/manwithacat/dazzle/issues/188))
- Sitespec media declarations cross-checked against rendered layout in audit ([#185](https://github.com/manwithacat/dazzle/issues/185))
- Money field widget with major/minor unit conversion in forms ([#172](https://github.com/manwithacat/dazzle/issues/172))
- Runtime standardised on PostgreSQL-only backend; SQLite removed ([#158](https://github.com/manwithacat/dazzle/issues/158))
- Migrated from psycopg2 + asyncpg to unified psycopg v3 driver ([#155](https://github.com/manwithacat/dazzle/issues/155))
- PostgreSQL-first runtime with SQLite-isms eliminated ([#154](https://github.com/manwithacat/dazzle/issues/154))
- Postgres constraint violations return 422 with helpful messages ([#146](https://github.com/manwithacat/dazzle/issues/146))
- htmx upgraded from 2.0.3 to 2.0.8 ([#144](https://github.com/manwithacat/dazzle/issues/144))
- Idiomorph swap for table performance to preserve DOM state ([#143](https://github.com/manwithacat/dazzle/issues/143))
- Alpine.js replaced with lightweight `dz.js` micro-runtime (~3 KB) ([#141](https://github.com/manwithacat/dazzle/issues/141))

### Deprecated
- Dazzle Bar dev toolbar feature removed ([#164](https://github.com/manwithacat/dazzle/issues/164))

### Fixed
- Recursive FK dependency chains in DSL test generator ([#237](https://github.com/manwithacat/dazzle/issues/237))
- Document symbol positions so outline navigation works correctly ([#233](https://github.com/manwithacat/dazzle/issues/233))
- Auth propagation to TestRunner and test generator quality issues ([#229](https://github.com/manwithacat/dazzle/issues/229))
- Authentication before CRUD tests when using `--base-url` ([#228](https://github.com/manwithacat/dazzle/issues/228))
- JSONL file writer connected to SQLite activity store for Workshop visibility ([#223](https://github.com/manwithacat/dazzle/issues/223))
- v0.25.0 constructs silently dropped by pre-v0.25.0 dispatchers ([#222](https://github.com/manwithacat/dazzle/issues/222))
- DSL with reserved keyword conflicts now rejected during MCP validation ([#219](https://github.com/manwithacat/dazzle/issues/219))
- Remaining ForwardRef modules causing `/openapi.json` 500 ([#218](https://github.com/manwithacat/dazzle/issues/218))
- Pydantic ForwardRef errors causing `/openapi.json` 500 ([#217](https://github.com/manwithacat/dazzle/issues/217))
- `asyncio.run()` conflict in `create_sessions` under MCP event loop ([#216](https://github.com/manwithacat/dazzle/issues/216))
- `InFailedSqlTransaction` recovery in publisher loop instead of cascading ([#215](https://github.com/manwithacat/dazzle/issues/215))
- Pluralization in surface converter to match test infrastructure ([#214](https://github.com/manwithacat/dazzle/issues/214))
- `from __future__ import annotations` removed from remaining route modules ([#213](https://github.com/manwithacat/dazzle/issues/213))
- `/openapi.json` returning 500 Internal Server Error ([#211](https://github.com/manwithacat/dazzle/issues/211))
- `asyncio.run()` conflict in `dsl_test` `create_sessions` ([#210](https://github.com/manwithacat/dazzle/issues/210))
- Workspace routes returning 404 despite nav links pointing to them ([#209](https://github.com/manwithacat/dazzle/issues/209))
- Entity route names using proper English pluralization ([#208](https://github.com/manwithacat/dazzle/issues/208))
- `dsl_test` route pattern matching actual runtime API routes ([#207](https://github.com/manwithacat/dazzle/issues/207))
- Partial stories always appear in pipeline coverage regardless of pagination ([#193](https://github.com/manwithacat/dazzle/issues/193))
- False positives in compliance signal detection for non-PII fields ([#191](https://github.com/manwithacat/dazzle/issues/191))
- LLM vision path not executing in `composition(analyze)` ([#184](https://github.com/manwithacat/dazzle/issues/184))
- Sitespec rendering for `split_content` source.path and pricing layout ([#182](https://github.com/manwithacat/dazzle/issues/182))
- Playwright async API in composition capture to fix asyncio conflict ([#181](https://github.com/manwithacat/dazzle/issues/181))
- Hero section media image not rendering despite correct sitespec ([#179](https://github.com/manwithacat/dazzle/issues/179))
- Sitespec rendering for `card_grid`, `split_content`, `trust_bar`, and more ([#177](https://github.com/manwithacat/dazzle/issues/177))
- `role()` conditions evaluated in policy simulate instead of always allowing ([#176](https://github.com/manwithacat/dazzle/issues/176))
- False HIGH severity gaps suppressed for system entities lacking create/edit ([#175](https://github.com/manwithacat/dazzle/issues/175))
- Standalone entity routes recognised in sitespec validator ([#174](https://github.com/manwithacat/dazzle/issues/174))
- Money field expansion accounted for in fidelity checker to prevent false positives ([#171](https://github.com/manwithacat/dazzle/issues/171))
- CSS/HTML class name mismatches breaking site styling ([#166](https://github.com/manwithacat/dazzle/issues/166))
- SQLAlchemy included as base dependency to prevent fresh deploy crashes ([#163](https://github.com/manwithacat/dazzle/issues/163))
- Tables topologically sorted by FK dependencies during PostgreSQL migration ([#162](https://github.com/manwithacat/dazzle/issues/162))
- `DATABASE_URL` honoured in `dazzle migrate` CLI command ([#161](https://github.com/manwithacat/dazzle/issues/161))
- Extra `dazzle` argument removed from subprocess command in `dazzle check` ([#160](https://github.com/manwithacat/dazzle/issues/160))
- Entity list routes 500 from psycopg v3 `dict_row` incompatibility ([#157](https://github.com/manwithacat/dazzle/issues/157))
- PostgresBus table creation crash from `.format()` vs JSONB DEFAULT conflict ([#156](https://github.com/manwithacat/dazzle/issues/156))
- SQL placeholder for FK pre-validation on PostgreSQL ([#152](https://github.com/manwithacat/dazzle/issues/152))
- psycopg2 `IntegrityError` subclasses handled in repository exception check ([#151](https://github.com/manwithacat/dazzle/issues/151))
- DaisyUI drawer hamburger toggle not appearing on tablet viewports ([#150](https://github.com/manwithacat/dazzle/issues/150))
- Project-level static images served after unified server change ([#149](https://github.com/manwithacat/dazzle/issues/149))
- `dz.js` and `dz.css` returning 404 after Alpine.js migration ([#147](https://github.com/manwithacat/dazzle/issues/147))
- Authentication enforced on workspace dashboard routes ([#145](https://github.com/manwithacat/dazzle/issues/145))
- Enum validation error handler crash from non-serializable `ValueError` ([#140](https://github.com/manwithacat/dazzle/issues/140))
- Orphaned column removed after money field expansion to fix NOT NULL violation ([#139](https://github.com/manwithacat/dazzle/issues/139))
- Entity route names using proper English pluralization ([#136](https://github.com/manwithacat/dazzle/issues/136))
- HTML sanitized in string/text fields to prevent stored XSS ([#135](https://github.com/manwithacat/dazzle/issues/135))
- Unique constraint violations return 422 instead of 500 ([#134](https://github.com/manwithacat/dazzle/issues/134))
- Foreign key constraint violations return 422 instead of 500 ([#133](https://github.com/manwithacat/dazzle/issues/133))
- `auto_add` and `auto_update` timestamp fields populated on insert and update ([#132](https://github.com/manwithacat/dazzle/issues/132))
- `money(GBP)` type expanded to `_minor`/`_currency` column pair instead of string ([#131](https://github.com/manwithacat/dazzle/issues/131))
- Enum field values validated against DSL-defined options on CRUD endpoints ([#130](https://github.com/manwithacat/dazzle/issues/130))

## [0.16.0] - 2025-12-16

### Added
- **MkDocs Material Documentation Site** ([manwithacat.github.io/dazzle](https://manwithacat.github.io/dazzle))
  - Complete DSL reference with 10 sections (modules, entities, surfaces, workspaces, services, integrations, messaging, ux, scenarios, experiences)
  - Architecture guides (overview, event semantics, DSL to AppSpec, MCP server)
  - 5 example walkthroughs (simple_task, contact_manager, support_tickets, ops_dashboard, fieldtest_hub)
  - Getting started guides (installation, quickstart, first app)
  - Contributing guides (dev setup, testing, adding features)
  - Auto-generated API reference from source code analysis (315 files)
  - GitHub Pages deployment via GitHub Actions

- **Event-First Architecture** (Issue #25) - Events as invisible substrate
  - EventBus interface (Kafka-shaped) with DevBrokerSQLite (zero-Docker development)
  - Transactional outbox for at-least-once delivery (no dual writes)
  - Idempotent inbox for consumer deduplication
  - DSL extensions: `event_model`, `topic`, `event`, `publish when`, `subscribe`, `project`
  - Replay capability for projection rebuild
  - Developer Observability Pack:
    - CLI commands: `dazzle events status|tail|replay`, `dazzle dlq list|replay|clear`, `dazzle outbox status|drain`
    - Event Explorer API at `/_dnr/events/`
    - AsyncAPI 3.0 generation from AppSpec
  - Email as events: raw stream, normalized stream, outbound events
  - Data products module: field classification, curated topics, policy transforms
  - 12 Stability Rules (Constitution) for event-first systems
  - KafkaBus adapter for production
  - Multi-tenancy strategies and topology drift detection

- **SiteSpec: Public Site Shell** (Issue #24)
  - YAML-based `sitespec.yaml` for public pages (home, about, pricing, terms, privacy)
  - 10 section types: hero, features, feature_grid, cta, faq, testimonials, stats, steps, logo_cloud, pricing
  - Template variable substitution (`{{product_name}}`, `{{year}}`, etc.)
  - Legal page templates (terms.md, privacy.md with full boilerplate)
  - Generated auth pages (login, signup) with working forms
  - Theme presets (`saas-default`, `minimal`)
  - MCP tools: `get_sitespec`, `validate_sitespec`, `scaffold_site`

- **Performance & Reliability Analysis (PRA)**
  - Load generator with configurable event profiles
  - Throughput and latency metrics collection
  - CI integration with stress test scenarios
  - Pre-commit hook for PRA unit tests

- **HLESS (High-Level Event Semantics Specification)**
  - RecordKind enum: INTENT, FACT, OBSERVATION, DERIVATION
  - StreamSpec model with IDL fields
  - HLESSValidator enforcing semantic rules
  - Cross-stream reference validation

- **Playwright E2E Tests**
  - Smoke tests for P0 examples (simple_task, contact_manager)
  - Screenshot tests for fieldtest_hub (16 screenshots)
  - Semantic DOM contract validation

- **Messaging Channels** (Issue #20) - Complete email workflow
  - DSL parser for `message`, `channel`, `asset`, `document`, `template`
  - IR types: MessageSpec, ChannelSpec, SendOperationSpec, ThrottleSpec
  - Outbox pattern: transactional persistence, status tracking, retry logic, dead letter handling
  - Background dispatcher: `ChannelManager.start_processor()` processes outbox every 5s
  - Email adapters: MailpitAdapter (SMTP), FileEmailAdapter (disk fallback)
  - Provider detection framework for email, queue, stream providers
  - Template engine with variable substitution and conditionals
  - Server integration: API routes at `/_dnr/channels/*`
  - MCP tools: `list_channels`, `get_channel_status`, `list_messages`, `get_outbox_status`
  - 95 unit tests

### Changed
- Examples reorganized: removed obsolete examples, added support_tickets and fieldtest_hub
- Consolidated `tools/` into `scripts/` directory
- API reference generator now excludes `__init__.py` files and detects events/invariants

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
