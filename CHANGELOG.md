# Changelog

All notable changes to DAZZLE will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

## [0.49.8] - 2026-03-27

### Added
- DSL parser fuzzer — three-layer hybrid fuzzer (LLM generation, grammar-aware mutation, token-level mutation) with classification oracle detecting hangs, crashes, and poor error messages (#732)
- `dazzle sentinel fuzz` CLI command — run fuzz campaigns against the parser with configurable layers, sample counts, and timeout
- MCP `sentinel` tool: new `fuzz_summary` operation for on-demand parser fuzz reports
- Hypothesis-powered parser fuzz test suite — 7 property-based tests covering arbitrary input, DSL-like text, and 5 mutation strategies

### Fixed
- `parse_duration()` in process parser now raises `ParseError` instead of `ValueError` on invalid duration strings — found by the fuzzer (#732)

### Agent Guidance
- **Parser fuzzing**: Run `dazzle sentinel fuzz --layer mutate --samples 100` to check parser robustness. The fuzzer found a `ValueError` bug and a parser hang (#733) during initial development — use it after parser changes.

## [0.49.7] - 2026-03-27

### Fixed
- DSL parser: infinite loop on unsupported syntax in surface section blocks — now raises a clear `ParseError` (#731)
- DSL parser: bare `owner` in `permit:` now gives actionable guidance pointing to the correct `scope:` block pattern (#729)
- Added `ownership_pattern` concept to semantics KB for MCP knowledge tool discoverability (#729)

### Agent Guidance
- **Ownership pattern**: Row-level ownership uses `scope:` blocks, not `permit:`. Write `scope: read: user_id = current_user for: reader` — there is no standalone `owner` keyword. See KB concept `ownership_pattern`.

## [0.49.6] - 2026-03-27

### Added
- `dazzle db stamp` CLI command — marks a revision as applied without running migrations, wraps `alembic.command.stamp()` (#728)

### Fixed
- `grammar_gen.write_grammar()`, `docs_gen.write_reference_docs()`, and `docs_gen.inject_readme_feature_table()` now write to project directory (CWD) instead of package directory (ADR-0018, #725)
- `tenant/provisioner.py` locates alembic dir via `import dazzle_back` for pip install compatibility (#725)

## [0.49.5] - 2026-03-27

### Fixed
- Alembic `env.py` now normalizes Heroku's `postgres://` scheme to `postgresql://` before adding the psycopg driver — fixes `Can't load plugin: sqlalchemy.dialects:postgres` on Heroku (#727)
- `_get_url()` now prefers `sqlalchemy.url` (already normalized by `db.py`) over raw `DATABASE_URL` env var

## [0.49.4] - 2026-03-27

### Added
- PythonAuditAgent (PA) sentinel agent — detects obsolete Python patterns in user project code (#726)
- Three detection layers: ruff profile (UP/PTH/ASYNC/C4/SIM), semgrep ruleset (8 rules for deprecated stdlib), and 6 `@heuristic` AST-based methods for LLM training-bias patterns
- Semgrep ruleset at `src/dazzle/sentinel/rules/python_audit.yml` covering distutils, pkg_resources, cgi, imp, asyncio.get_event_loop, nose, toml PyPI package, and datetime.timezone.utc
- LLM-bias heuristics: requests-in-async (PA-LLM-01), manual dunders (PA-LLM-03), unittest-in-pytest (PA-LLM-04), setup.py alongside pyproject.toml (PA-LLM-05), pip-when-uv-available (PA-LLM-06)
- Python version filtering — findings with min_version above project target are excluded
- Orchestrator now passes `project_path` through to agents that need it

### Agent Guidance
- **PA agent**: Results appear via existing `sentinel findings`/`status`/`history` MCP tools — no new MCP operations. PA scans user project code (app/, scripts/, root .py files), never framework code.

## [0.49.3] - 2026-03-27

### Fixed
- `dazzle db revision` now writes migration files to project directory (`.dazzle/migrations/versions/`) instead of the framework's package directory (#724)
- Alembic config uses `version_locations` to chain framework + project migrations — upgrade/downgrade discovers both
- Framework alembic directory located via `dazzle_back` package path (works with pip installs, not just editable dev mode)

### Agent Guidance
- **Migration output path**: `dazzle db revision` writes to `.dazzle/migrations/versions/` in the project directory. Framework migrations and project migrations are chained via Alembic's `version_locations`. Never write to the Python package directory.

## [0.49.2] - 2026-03-26

### Added
- Environment profiles: `[environments.<name>]` sections in `dazzle.toml` for per-environment database configuration (#718)
- Global `--env` CLI flag and `DAZZLE_ENV` environment variable to select active profile (#718)
- `EnvironmentProfile` dataclass with `database_url`, `database_url_env`, and `heroku_app` fields (#718)
- `environment_profiles` concept in semantics KB with resolution priority documentation (#718)
- Commented-out `[environments.*]` example in blank project template (#718)

### Changed
- `resolve_database_url()` now accepts `env_name` parameter — inserted at priority #2 between explicit URL and DATABASE_URL env var (#718)
- All database-touching CLI commands (db, dbshell, tenant, serve --local, backup) thread `env_name` through to URL resolution (#718)

### Agent Guidance
- **Environment profiles**: Use `[environments.<name>]` in `dazzle.toml` to declare per-environment database connections. Select via `--env <name>` or `DAZZLE_ENV`. Profile names are freeform (development, staging, production, blue, green, demo, etc.).
- **Resolution priority**: `--database-url` > `--env` profile > `DATABASE_URL` env var > `[database].url` > default. Document this in comments when using profiles.
- **CI/CD**: Set `DAZZLE_ENV=production` in deployment config instead of passing `--env` to every command.

## [0.49.1] - 2026-03-26

### Changed
- All tutorial examples now declare `security_profile: basic` and an `admin` persona — aligns with auth-universal philosophy (#704)
- `llm_ticket_classifier` example: added `[auth]` section to `dazzle.toml` (#704)
- `contact_manager` stories: fixed actor references to match declared persona IDs (#704)

### Agent Guidance
- **Examples are auth-universal**: All tutorial examples now have auth enabled, an `admin` persona, and `security_profile: basic`. When scaffolding new apps from examples, this is the expected baseline.

## [0.49.0] - 2026-03-26

### Added
- MCP `knowledge` tool: `changelog` operation — returns `### Agent Guidance` entries from recent releases, with optional `since` version filter (#716)
- MCP `knowledge` tool: `version_info` block in concept lookup responses — includes `since` version and `changes` history when annotated in TOML (#716)
- Semantics KB: `since_version` and `changed_in` fields on TOML concepts — 5 concepts annotated (feedback_widget, scope, static_assets, predicate_compilation, surface_access) (#716)
- KG seeder: changelog guidance entries stored as `changelog:vX.Y.Z` entities during startup (#716)

### Agent Guidance
- **Version-aware concepts**: Some concept lookups now include a `version_info` block with `since` (introduction version) and `changes` (version history). Use this to understand when features appeared and what changed.
- **Changelog operation**: Use `knowledge(operation='changelog')` to get agent guidance from recent releases. Use `since` parameter to filter (e.g., `knowledge(operation='changelog', since='0.48.0')`). Default: last 5 releases with guidance.

## [0.48.16] - 2026-03-26

### Added
- Admin workspace: `DIAGRAM` display mode — entity relationship diagrams rendered via Mermaid JS (#700)
- Admin workspace: app map region showing entity FK graph in Operations nav group (#700)
- Admin workspace: deploy trigger actions — "Trigger Deploy" header button and per-row "Rollback" on deploys region (#701)
- Admin workspace: `_REGION_ACTIONS` / `_ROW_ACTIONS` action button system for admin regions (#701)
- Admin API: `POST /_admin/api/deploys/trigger` and `POST /_admin/api/deploys/{id}/rollback` endpoints (super_admin only) (#701)

## [0.48.15] - 2026-03-26

### Added
- Admin workspace: `LogEntry` virtual entity and `_admin_logs` region — log viewer backed by `get_recent_logs()` with level filtering (#699)
- Admin workspace: `EventTrace` virtual entity and `_admin_events` region — event explorer backed by event bus replay API (#702)
- Feedback widget: resolved-report notification — toast on page load when reports are resolved, `notification_sent` tracking field (#721)

## [0.48.14] - 2026-03-26

### Removed
- Removed unnecessary `from __future__ import annotations` from 547 files — ban-by-default policy, retained with `# required:` justification in ~145 files with genuine forward references (#717)

### Fixed
- Feedback widget PUT endpoint: added test coverage verifying surface converter generates PUT endpoint and UPDATE service for FeedbackReport (#720)

## [0.48.13] - 2026-03-26

### Fixed
- Feedback widget: all buttons now have `type="button"` — prevents Safari scroll glitch on first click inside `hx-boost` bodies (#722)
- Feedback widget: removed `textarea.focus()` on panel open — eliminates iPad Safari white bar from virtual keyboard reservation (#723)
- Feedback widget: panel height changed from `100vh` to `100dvh` — tracks dynamic viewport excluding virtual keyboard on mobile Safari (#723)

## [0.48.12] - 2026-03-26

### Added
- Universal admin workspace: linker auto-generates `_platform_admin` (and `_tenant_admin` for multi-tenant apps) with profile-gated regions for health, metrics, deploys, processes, sessions, users, and feedback (#686)
- Five synthetic platform entities: `SystemHealth`, `SystemMetric`, `DeployHistory`, `ProcessRun`, `SessionInfo` — backed by existing observability stores (#686)
- `SystemEntityStore` adapter: routes reads for virtual entities to health aggregator, metrics store, and process monitor instead of PostgreSQL (#686)
- Collision detection: `LinkError` raised if user-declared entities/workspaces conflict with synthetic admin names (#686)
- Admin LIST surfaces for all synthetic entities with admin-persona access control (#686)
- Content-hash cache busting: `static_url` Jinja2 filter rewrites asset paths with SHA-256 fingerprints — no build step (#711)
- Project layout convention: recommended `app/` directory structure for custom Python code; `dazzle init --with-app` scaffold (#715)
- Security profile reference: `docs/reference/security-profiles.md` with profile comparison and admin region tables (#705)
- Template override docs: `dz://` prefix, declaration headers, available blocks (#710)

### Fixed
- Feedback widget retry toast no longer shown on page load — silent mode for background retries (#708)
- CSS sidebar hidden on desktop — moved `dz.css` out of `@layer(framework)` so overrides beat DaisyUI (#709)

### Changed
- All schema changes (including framework entities) now go through Alembic — removed raw ALTER TABLE startup path (ADR-0017, #713)
- Virtual entities (SystemHealth, SystemMetric, ProcessRun) excluded from SA metadata — no phantom PostgreSQL tables (#713)

### Deprecated
- Founder console routes (`/_ops/`, `/_console/`) — `X-Dazzle-Deprecated` header added, will be removed in a future release (#686)

### Agent Guidance
- **Admin workspace entities**: The linker now generates synthetic entities with `domain="platform"`. Tests and tools that count entities should filter these out (e.g., `[e for e in entities if e.domain != "platform"]`).
- **Entity naming**: Don't declare entities named `SystemHealth`, `SystemMetric`, `DeployHistory`, `ProcessRun`, or `SessionInfo` — these are reserved by the admin workspace and will cause a `LinkError`.
- **Schema migrations**: Use `dazzle db revision -m "description"` then `dazzle db upgrade` for ALL schema changes, including framework entities. No raw ALTER TABLE (ADR-0017).
- **Static assets in templates**: Use `{{ 'css/file.css' | static_url }}` instead of bare `/static/css/file.css` paths. The filter adds content-hash fingerprints for cache busting.
- **Project layout**: Custom Python code goes in `app/<category>/` (db, sync, render, qa, demo). One-shot scripts go in `scripts/`. Don't create flat `pipeline/` directories.
- **Security profiles**: All three profiles (basic/standard/strict) now include auth and an admin workspace. See `docs/reference/security-profiles.md` for which regions each profile gets.

## [0.48.11] - 2026-03-25

### Fixed
- Feedback widget POST 422: `reported_by` now populated from session email, field made optional (#687)
- Feedback widget CSS: converted `oklch()` to `hsl()` to match design system variable format (#690)
- Missing favicon `<link>` in app `base.html` — 404 console error on all app pages (#691)
- `/__test__/reset` now reads `.dazzle/test_credentials.json` for user creation instead of generic emails (#688)
- Dead-construct lint false positives: surfaces reachable via `nav_group` entity items no longer flagged (#689)

### Agent Guidance
- **FeedbackReport idempotency**: The `idempotency_key` field (str(36), unique) was added to FeedbackReport in #693. Existing deployments need `dazzle db upgrade` to add the column.

## [0.48.10] - 2026-03-25

### Changed
- `process_manager` added to `RuntimeServices`, task route handlers use `Depends(get_services)` (#673)
- Rate-limit globals replaced with `_Limits` dataclass container — eliminates `global` keyword (#673)
- `runtime_tools/state.py` globals (`_appspec_data`, `_ui_spec`) moved to `ServerState` (#673)
- `api_kb/loader.py` cache globals (`_pack_cache`, `_packs_loaded`, `_project_root`) moved to `ServerState` (#673)
- All 17 remaining `global` statements annotated with `# noqa: PLW0603` and mandatory reason (#673)

### Removed
- `src/dazzle/mcp/runtime_tools/state.py` — module deleted, state migrated to `ServerState` (#673)
- `get_process_manager()`, `set_process_manager()` global singleton functions (#673)
- `api_kb.loader.set_project_root()` — cache clearing handled by `ServerState.set_project_root()` (#673)

### Agent Guidance
- **No new singletons** (ADR-0005): Access runtime services via `Depends(get_services)` in route handlers or `request.app.state.services` in middleware. Do not create module-level mutable state.

## [0.48.9] - 2026-03-25

### Changed
- 6 HIGH-risk module-level mutable singletons in `dazzle_back` consolidated into `RuntimeServices` dataclass on `app.state.services` (#673)
- Route handlers access services via `Depends(get_services)`, middleware via `request.app.state.services` (#673)
- Tests use pytest fixtures creating fresh instances instead of global reset functions (#673)

### Removed
- `get_event_bus()`, `set_event_bus()`, `reset_event_bus()` global singleton functions (#673)
- `get_presence_tracker()`, `set_presence_tracker()`, `reset_presence_tracker()` global singleton functions (#673)
- `get_framework()`, `init_framework()`, `shutdown_framework()` global singleton functions (#673)
- `get_collector()`, `reset_collector()`, `get_system_collector()`, `reset_system_collector()` global singleton functions (#673)
- `get_emitter()`, `emit()` global singleton functions (#673)

## [0.48.8] - 2026-03-25

### Changed
- CSS delivery default flipped to local-first (`_use_cdn = False`); CDN opt-in via `[ui] cdn = true` in `dazzle.toml` (#671)
- CSS Cascade Layers (`@layer base, framework, app, overrides`) added to `base.html` and `site_base.html` for explicit cascade ordering (#671)
- New `dazzle-framework.css` entry point replaces standalone `dz.css` loading in local mode (#671)
- `css_loader.py` updated with canonical CSS order, `@layer framework` wrappers, and inline source map (#671)
- `build_dist.py` produces layer-aware `dazzle.min.css` with `@layer framework` wrappers (#671)
- CI publish workflow rebuilds `dist/` at release time for CDN freshness (#671)

### Agent Guidance
- **CSS is local-first**: Static CSS/JS are served from the app, not CDN. The CDN path is opt-in via `[ui] cdn = true` in `dazzle.toml`.
- **Cascade layers**: CSS uses `@layer base, framework, app, overrides`. Framework styles go in `layer(framework)`. Exception: `dz.css` is unlayered so its sidebar overrides beat DaisyUI's unlayered drawer styles.

## [0.48.7] - 2026-03-25

### Fixed
- Workspace regions returning 0 rows: UUID FK attrs from psycopg3 silently dropped in session preferences (#684)
- Feedback widget POST 403 on deployed sites: route now uses direct SQL insert instead of nonexistent repository
- Feedback widget CSS missing from CDN bundle — added to `build_dist.py`

### Added
- Positive auth resolution tests: verify UUID FK attrs resolve through full auth chain, not just deny paths (#684)

### Changed
- PostgreSQL CI job runs only `pytest.mark.postgres` tests (127 tests) instead of full suite (9,143) — ~3 min saved per run

## [0.48.6] - 2026-03-25

### Changed
- `eval_comparison_op` extracted to `dazzle.core.comparison` — eliminates 60-line duplication between `_comparison.py` and `condition_eval.py` (#675)
- `appspec: Any` replaced with `appspec: AppSpec` via `TYPE_CHECKING` across 5 agent mission files (#676)
- `EventFramework.get_bus()` public method replaces all direct `framework._bus` access (#678)
- `AuthStore` public API: `count_users`, `count_active_sessions`, `list_distinct_roles`, `list_sessions`, `store_totp_secret_pending` — eliminates 7 external `_execute` calls (#672)
- `_fastapi_compat.py` TYPE_CHECKING imports — mypy sees real FastAPI types, removes type: ignore cascade (#677)
- `route_generator.py` public handler signatures typed with `BaseService`, `EntityAccessSpec`, `AuditLogger` (#680)

## [0.48.5] - 2026-03-25

### Fixed
- `has_grant()` state machine guard: properly enter `db.connection()` context for GrantStore — was passing context manager generator instead of connection (#669)
- `has_grant()` diagnostic logging: WARNING on missing store/IDs/UUID failures, DEBUG on query results (#669)
- UUID objects passed through without re-casting in `has_grant()` (#669)
- Feedback widget POST route registered at `/feedbackreports` when `feedback_widget.enabled` — was returning 403/404 (#670)

### Changed
- 7 `# type: ignore[no-any-return]` on `json.loads()` replaced with explicit variable annotations (#682)

## [0.48.4] - 2026-03-24

### Added
- SOC 2 Trust Services Criteria taxonomy — 63 controls across 5 categories with DSL evidence mappings (#657)
- Reference documentation for graph features (CTE neighborhood, NetworkX algorithms, domain-scoped graphs) (#656)
- Reference documentation for compliance framework (ISO 27001 + SOC 2 pipeline, CLI, evidence mapping) (#656)
- Grant-based RBAC section in access-control reference (grant_schema, has_grant, four-eyes approval) (#656)
- System endpoints (/health, /_diagnostics) and feedback widget in runtime-capabilities reference (#656)

## [0.48.3] - 2026-03-24

### Fixed
- Connection pool auto-rollback on failed transactions — prevents cascading 500s from poisoned connections (#664)
- `RedisBus.start_consumer_loop()` accepts `poll_interval` kwarg to match base class signature (#662)
- FK fields on detail pages now resolve to `display_field` values instead of showing raw UUIDs (#663)
- ParamRef resolved to its default value before use as field default in `_build_column` (#641)
- GrantStore supports PostgreSQL `%s` placeholders (#640)

### Changed
- Pool `open_pool()` passes a `reset` callback to rollback aborted transactions on connection return
- Detail view template checks `{relation_name}_display` key for ref fields, matching list surface behaviour
- Nav group route dedup prevents entity items appearing in both flat nav and grouped accordion (#661)
- Feedback widget CSS uses oklch fallback values for opaque backgrounds (#660)

## [0.48.2] - 2026-03-24

### Changed
- Event system is now PostgreSQL-only — removed all aiosqlite/SQLite code paths from outbox, inbox, consumer, publisher, and framework (#644)
- `OutboxPublisher`, `IdempotentConsumer`, `idempotent()`: `db_path` parameter removed — use `connect=` instead
- `EventFrameworkConfig`: `db_path` field removed — use `database_url` instead
- `EventOutbox`: `use_postgres` parameter removed — always PostgreSQL
- `EventInbox`: `placeholder`/`backend_type` parameters removed — always PostgreSQL
- Canary dependency probe changed from `aiosqlite` to `psycopg` in `null.py`

### Agent Guidance
- **PostgreSQL only** (ADR-0008): No SQLite code paths remain. All database operations use PostgreSQL via psycopg. Don't propose SQLite as a fallback or dev convenience.

### Fixed
- Feedback widget Jinja global set after `configure_project_templates()` to survive env replacement (#649)
- Workspace grid uses CSS columns for masonry-style card layout — eliminates whitespace gaps (#648)
- `/health` endpoint now reports `version`, `dsl_hash`, and `uptime_seconds` (#651)
- Queue display uses `_display` sibling key for FK ref columns instead of raw dict repr (#654)
- `_eval_func` implements `has_grant()` for state machine transition guards (#653)
- `grant_routes`: `_check_granted_by` reads from `GrantRelationSpec`, not `GrantSchemaSpec` (#650)

### Added
- `/_diagnostics` endpoint (admin-only) returning entity/surface/workspace counts and feature flags (#651)
- Lint warning for FK-target entities missing `display_field` (#652)
- `_extract_roles` helper for compound `ConditionExpr` trees in grant routes (#650)

### Removed
- `aiosqlite` dependency from `events` and `dev` extras in pyproject.toml (#644)
- SQLite DDL constants from outbox.py and inbox.py (#644)
- All `db_path` deprecation shims from event system (#644)

## [0.48.1] - 2026-03-24

### Fixed
- `grant_routes`: `_check_granted_by` now reads `granted_by` and `approval` from `GrantRelationSpec` instead of `GrantSchemaSpec` — fixes 500 error on all grant creation (#650)

### Added
- `_extract_roles` helper to walk `ConditionExpr` trees for compound role expressions (e.g. `role(admin) or role(manager)`)
- `_get_relation_spec` helper for relation-level lookups within grant schemas
- Unit tests for grant routes (`test_grant_routes.py`)

## [0.48.0] - 2026-03-24

### Agent Guidance
- **Grant-based RBAC**: GrantStore is now PostgreSQL-only with atomic state transitions. Use `has_grant()` in state machine guards. See `src/dazzle_back/runtime/grant_routes.py` for the HTTP API.
- **Template overrides**: Use `{% extends "dz://base.html" %}` to extend framework templates from project overrides. Plain `{% extends "base.html" %}` causes infinite recursion.

### Changed
- GrantStore rewritten as PostgreSQL-only — removed all SQLite code paths, `_sql()` helper, and `placeholder` parameter
- Grant tables now use native PostgreSQL types: UUID columns, TIMESTAMPTZ timestamps, JSONB metadata
- State transitions use atomic `UPDATE WHERE status + rowcount` pattern — eliminates TOCTOU race conditions
- `list_grants` uses dynamic WHERE clause construction instead of `IS NULL OR` anti-pattern
- `expire_stale_grants` uses `RETURNING id` for single-pass batch expiry
- `grant_routes.py` docstring and constructor updated for psycopg (was sqlite3)

### Added
- `cancel_grant` transition: `pending_approval → cancelled` (by the granter)
- CHECK constraints on `_grants.status` and `_grant_events.event_type` columns
- Partial index `idx_grants_expiry` for active grants with expiry dates
- FK index `idx_grant_events_grant_id` on grant events table
- Cancel endpoint: `POST /api/grants/{id}/cancel`
- UUID validation at HTTP boundary in grant routes (`_parse_uuid` helper)
- Concurrency tests proving one-winner property for competing state transitions
- PostgreSQL integration tests via `TEST_DATABASE_URL` (skip when not set)

### Removed
- SQLite support in GrantStore — PostgreSQL is the sole supported backend
- `_sql()` placeholder rewriting helper
- `placeholder` parameter on GrantStore constructor

## [0.47.2] - 2026-03-23

### Fixed
- Rebuilt `dist/dazzle.min.js` CDN bundle — stale `dzWorkspaceEditor` signature caused Alpine init failure (#638)
- Context selector `scope_field` now reads domain attributes from `auth_ctx.preferences` instead of `user_obj` (#639)
- Data island `layout_json` uses `| safe` filter to prevent Jinja2 entity-encoding inside `<script>` tags (#635 follow-up)

## [0.47.1] - 2026-03-23

### Fixed
- Workspace layout JSON now embedded as `<script type="application/json">` data island instead of inlined in `x-data` HTML attribute — eliminates JSON/HTML escaping conflict (#632, #635)
- Nav: workspace home link now renders above collapsible nav_groups (#630)
- Heatmap region click-through uses FK target entity ID instead of source item ID (#633)
- Tailwind safelist for `col-span-{4,6,8,12}` at responsive breakpoints — workspace card width customisation now takes effect (#631)
- Context selector: `scope_field` wired into options route + `htmx.ajax()` for unconditional region refresh (#634)
- Event framework startup hang with remote Postgres: added `connect_timeout=10` + lazy pool open + REDIS_URL forwarding (#636)

### Added
- Grant management API: `POST/GET/DELETE /api/grants/*` endpoints wrapping existing `GrantStore` — unblocks `has_grant()` transition guards (#629)
- `dazzle serve --local-assets/--cdn-assets` flag — serve JS/CSS from local installation instead of CDN; defaults local in dev, CDN in production (#637)

## [0.47.0] - 2026-03-23

### Added
- `feedback_widget` DSL keyword with parser mixin, IR model (`FeedbackWidgetSpec`), and auto-entity generation
- Auto-generated `FeedbackReport` entity with lifecycle state machine (new → triaged → in_progress → resolved → verified) when `feedback_widget: enabled` is declared
- Client-side feedback widget (JS/CSS) injected into authenticated pages — safe DOM construction, idempotency keys, rate limiting, offline retry
- Apps can override auto-entity by declaring their own `FeedbackReport` entity

### Changed
- Database migrations now use Alembic instead of hand-rolled `MigrationPlanner`
- `dazzle db migrate` generates and applies migrations in one step
- `dazzle db rollback` reverts migrations with optional revision target
- Type changes detected automatically via `compare_type=True`
- `dazzle serve --production` refuses to start with pending migrations
- Linker `_parse_field_type` now supports `ref <Entity>` and `float` types

### Added
- Compliance documentation compiler: maps DSL metadata to framework controls
- `dazzle compliance compile` / `evidence` / `gaps` CLI commands
- MCP `compliance` tool with 5 operations (compile, evidence, gaps, summary, review)
- ISO 27001:2022 taxonomy (93 controls, 4 themes)
- Pydantic models for Taxonomy, EvidenceMap, AuditSpec IR
- `[compliance]` optional extra in pyproject.toml
- Safe cast registry: text→uuid, text→date, text→timestamptz, text→jsonb applied automatically with USING clauses
- `dazzle db migrate --check` dry-run to preview schema changes
- `dazzle db migrate --tenant <slug>` for per-tenant schema migration

### Removed
- `MigrationPlanner`, `MigrationExecutor`, `MigrationHistory` classes (~400 lines)
- `auto_migrate()` / `plan_migrations()` functions — replaced by Alembic

## [0.46.5] - 2026-03-23

### Fixed
- 77 mypy type errors across `dazzle_back` and `dazzle.core` (Redis async unions, bare `dict` params, missing `column` arg in `make_parse_error`, missing `_build_graph_filter_sql`)
- Gitignore `.claude/projects/` local session data

## [0.46.4] - 2026-03-22

### Fixed
- Suppress misleading "permit without scope" linter warning on framework-generated entities (e.g. AIJob from `llm_intent` blocks)

## [0.46.3] - 2026-03-22

### Added
- `--production` flag on `dazzle serve` — binds 0.0.0.0, reads PORT env var, requires DATABASE_URL, structured JSON logging, disables dev features
- `dazzle deploy dockerfile` — generates production Dockerfile + requirements.txt
- `dazzle deploy heroku` — generates Procfile, runtime.txt, requirements.txt
- `dazzle deploy compose` — generates production docker-compose.yml

### Removed
- Container runtime (`dazzle_ui.runtime.container`) — replaced by `dazzle serve --production`
- `DockerRunner` and Docker template generation — replaced by `dazzle deploy`
- `dazzle rebuild` command — prints migration message directing to `dazzle deploy dockerfile`

### Fixed
- `float` type missing from frontend spec export `FIELD_TYPE_MAP`
- `target:` keyword not recognized in integration transform block parser
- Stale test snapshots for graph semantics and streamspec error types
- Content negotiation test mocks returning truthy MagicMock for `query_params.get()`

## [0.46.2] - 2026-03-22

### Fixed
- Legacy scope condition path (via clauses) now catches exceptions instead of 500 (#617)
- Graph materialization SQL uses `quote_identifier` for defense-in-depth

## [0.46.1] - 2026-03-22

### Added
- `float` field type — IEEE 754 double precision for sensors, weights, and scores (#620)

### Fixed
- Float type included in tagged release (v0.46.0 tag predated the float commit)

## [0.46.0] - 2026-03-22

### Added
- **Graph Semantics** — full directed property multigraph support in the DSL (#619)
  - Phase 1: `graph_edge:` and `graph_node:` blocks on entities with validation and lint hints
  - Phase 2: `?format=cytoscape|d3` on edge entity list endpoints via `GraphSerializer`
  - Phase 3: `GET /{entity}/{id}/graph?depth=N` neighborhood traversal via PostgreSQL recursive CTE
  - Phase 4: Shortest path and connected components via optional NetworkX integration
- Domain-scoped graph algorithms (per-work graph partitioning via filter params)
- `networkx>=3.0` as optional `[graph]` extra

## [0.45.5] - 2026-03-22

### Added
- Graph algorithms: shortest path + connected components endpoints (#619 Phase 4)
- `GraphMaterializer` — on-demand DB → NetworkX graph materialization
- Domain-scoped algorithms via filter params (`?work_id=uuid`) for partitioned graphs
- NetworkX as optional dependency (`pip install dazzle-dsl[graph]`)

## [0.45.4] - 2026-03-22

### Added
- Neighborhood endpoint: `GET /{entity}/{id}/graph?depth=N&format=cytoscape|d3` (#619 Phase 3)
- `NeighborhoodQueryBuilder` — PostgreSQL recursive CTE for graph traversal
- Directed and undirected traversal with automatic cycle prevention via UNION
- Scope predicate injection into CTE WHERE clauses
- Configurable depth bound (1–3 hops)

## [0.45.3] - 2026-03-22

### Added
- Graph serializer: `?format=cytoscape|d3` on edge entity list endpoints (#619 Phase 2)
- `GraphSerializer` class for Cytoscape.js and D3 force-graph JSON output
- Heterogeneous graph support (bipartite graphs with different node entity types)
- Node batch-fetch with scope/permit enforcement

## [0.45.2] - 2026-03-22

### Added
- `graph_edge:` and `graph_node:` blocks on entities — formal graph semantics declarations (#619)
- Graph validation: field references, type checks, cross-entity consistency
- Lint hints: suggest `graph_edge:` for entities with 2+ refs to same entity, suggest `graph_node:` for targeted entities
- Grammar reference updated with graph semantics BNF

## [0.45.1] - 2026-03-22

### Fixed
- CDN bundle at v0.45.0 tag missing Alpine + workspace editor — rebuilt with all components (#615, #618)
- CSRF middleware rewritten as pure ASGI to fix body consumption (#606)
- Scope predicate resolution: most-permissive-wins for dual-role users (#604), pass-through for no-scope entities (#607), Tautology detection (#604)
- Graceful handling of null FK in EXISTS scope bindings (#617)
- MCP db handlers converted to async (#609), topology/triggers import path fixed
- `/create` guard routes registered before `/{id}` routes (#598)
- Circular FK references demoted to warning (#608), decimal parse error improved (#610)
- EntitySpec.relations and FieldSpec.unique API mismatches in migrate (#616)
- Workspace action URL interpolation with cross-entity FK fields (#614)
- Lucide sourcemap 404 in Safari stripped
- Security test updated for CSRF middleware class rename
- `/check` and `/ship` mypy targets aligned with CI (src/dazzle_back/)

### Added
- 15 runtime contract KB entries (display_field, scope, CSRF, request lifecycle, etc.)
- Purpose-annotated `implemented_by` on KB concepts
- `graph topology` operation — derive project structure from DSL
- Knowledge effectiveness metrics in telemetry
- `/improve` autonomous improvement loop (BDD pattern)
- Alpine.js `$persist` plugin for localStorage state
- Example app DSL quality improvements across 6 apps (scope blocks, workspace wiring, ux blocks)

### Changed
- dz.js fully retired — all UI state managed by Alpine.js components in dz-alpine.js

## [0.45.0] - 2026-03-21

### Added
- **Conformance Role 2**: HTTP execution engine — boots FastAPI in-process, seeds fixtures via `/__test__/seed`, runs all derived cases as HTTP assertions (#601)
- **Stage invariant verification**: three-stage verifier for predicate compilation chain (ConditionExpr → ScopePredicate → SQL → resolved params) (#603)
- **Runtime contract monitoring**: `ConformanceMonitor` captures access decisions during scenario execution and compares against expected conformance cases (#602)
- `dazzle conformance execute` CLI command for running HTTP conformance against PostgreSQL
- `monitor_status` MCP operation on conformance tool
- `?q=` alias for `?search=` on all API list endpoints (#596)
- Bare `?field=value` query params accepted when field is in DSL `ux: filter:` list (#596)
- `build_entity_filter_fields()` extracts filter allowlist from surface UX declarations
- Alpine.js `$persist` plugin (835B) for localStorage state management
- `dz-alpine.js` — Alpine.data() components replacing dz.js: dzToast, dzConfirm, dzTable, dzMoney, dzFileUpload, dzWizard (#600)
- `param` DSL construct for runtime-configurable parameters with tenant-scoped cascade (#572)
- `param("key")` reference syntax in workspace region constructs (heatmap thresholds)
- `_dazzle_params` table for storing per-scope parameter overrides
- `param list/get/validate` MCP operations and CLI commands
- Startup validation of stored param overrides against DSL declarations
- `dazzle e2e journey` — persona-driven E2E testing against live deployments (#557)
- Two-phase execution: deterministic workspace exploration + LLM story verification
- Cross-persona pattern analysis with structured HTML reports
- `test_intelligence journey` MCP operation (read-only)
- `.dazzle/test_personas.toml` credential file for journey testing
- `dazzle demo propose` now generates test persona credentials
- `not via` syntax for NOT EXISTS scope rules
- `not (...)` parenthesised negation in scope rules
- depth-N FK path traversal in scope rules (previously depth-1 only)
- Static validation of scope rule FK paths at `dazzle validate` time
- Runtime startup assertion verifies all scope predicates compile

### Changed
- Scope rules compile to formal ScopePredicate algebra with FK graph validation
- OR conditions in scope rules now compile to SQL OR (previously post-fetch filtered)
- Template strings replaced with contextual variables (`app_name`, `entity_name`) across 10 templates (#593)
- Console routes derive `app_name` from AppSpec instead of hardcoding "Dazzle Console"
- All UI state management migrated from dz.js to Alpine.js (#600)

### Removed
- `dz.js` micro-runtime (1102 lines) — replaced by Alpine.js components in `dz-alpine.js`
- Post-fetch OR filtering for scope rules (replaced by SQL OR)

### Fixed
- CSRF middleware now exempts `/__test__/` and `/dazzle/dev/` paths (internal-only endpoints)

## [0.44.0] - 2026-03-19

### Added
- **Schema-per-tenant isolation** — `TenantMiddleware` with subdomain/header/session resolvers, registry cache, `pg_backend` context-var routing, `--tenant` flag on `dazzle db` commands (#531)
- **Domain user attribute resolution** — auth session validation merges DSL User entity fields into `auth_context.preferences` so scope rules like `current_user.school` resolve correctly (#532)
- **Via clause entity ID resolution** — bare `current_user` in via clauses now resolves to DSL User entity PK via `preferences["entity_id"]` (#534)
- **DSL anti-pattern guidance** — 5 modeling anti-patterns (polymorphic keys, god entities, soft-delete booleans, stringly-typed refs, duplicated fields) surfaced via inference KB, lint warnings, and `_guidance` string
- **External action links** — new `OutcomeKind.EXTERNAL` and `external` keyword for URL-based action links on surfaces (#542)
- **Docker dev infrastructure** — `dazzle serve` (Docker mode) now starts Postgres+Redis via Docker Compose while running the app locally (#540, #541)

### Fixed
- Scope rules using `current_user.school` resolve to null — auth users lacked domain attributes (#532)
- Via clause `current_user` resolved to auth user ID instead of DSL entity ID (#534)
- Test generator didn't populate nullable FKs required by 3-way OR invariants (#533)
- 4 pre-existing CI failures (type-check, security tests, PostgreSQL tests, E2E smoke) all resolved
- 6 bare `except Exception: pass` sites given proper logging
- `_pack_cache` thread-safety gap fixed via atomic snapshot replacement
- HTTP retry coverage gap — 4 unretried outbound call sites retrofitted
- Docker container runtime SQLite → PostgreSQL default (#541)

### Changed
- **`server.py` subsystem migration** — reduced from 2,214 to 936 lines; `IntegrationManager` and `WorkspaceRouteBuilder` moved to standalone modules; circular import with `app_factory.py` eliminated (#535)
- **Route factory extraction** — all 13 route factory mega-functions (300-784L each) refactored: handlers extracted to module level with `_XxxDeps` dataclasses, factories shrunk to route registration (#536)
- **Parser nesting depth** — top 4 offenders flattened: `execute_step` (depth 24→dispatch), `_parse_single_step` (22→field parsers), `parse_type_spec` (20→sub-parsers), `handle_runtime_tool` (18→dispatch table) (#537)
- **`dazzle_back` public API** — `__init__.py` exports 11 symbols via lazy loaders; CLI/MCP no longer reach into `dazzle_back.runtime.*` internals (#539)
- Duplicated `error_response`/`unknown_op_response` in `handlers_consolidated.py` removed
- 8 `Any` annotations replaced with concrete `TYPE_CHECKING` types
- `ViaBinding` and `ViaCondition` added to `ir.__init__.__all__`
- Shapes validation DSL fixed: `or` syntax in permit blocks, missing PKs and persona

## [0.43.0] - 2026-03-18

### Added
- **RBAC Verification Framework** — three-layer provable access control: static access matrix (Layer 1), dynamic verification (Layer 2), decision audit trail (Layer 3)
- `dazzle rbac matrix` CLI command — generate (role, entity, operation) → permit/deny matrix from DSL
- `dazzle rbac verify` CLI command (stub) — dynamic verification pipeline
- `dazzle rbac report` CLI command — compliance report from verification results
- `policy access_matrix` and `policy verify_status` MCP operations
- `src/dazzle/rbac/` package: `matrix.py`, `audit.py`, `verifier.py`, `report.py`
- `AccessDecisionRecord` audit trail with pluggable sinks (Null, InMemory, JsonFile)
- `evaluate_permission()` instrumented to emit audit records on every decision
- `examples/shapes_validation/` — abstract RBAC validation domain (7 personas, 4 entities) exercising RBAC0/RBAC2/ABAC/multi-tenancy patterns
- CI security gate: Shapes RBAC matrix validated on every push (fails if any entity is PERMIT_UNPROTECTED)
- Two-tier access control evaluation model documented in `docs/reference/access-control.md`
- RBAC verification deep-dive with academic references in `docs/reference/rbac-verification.md`
- README "Provable RBAC" section

### Fixed
- **Critical: LIST gate silently disabled for all role-based access rules** (#520) — `_is_field_condition()` now correctly classifies role_check conditions as gate-evaluable
- Sidebar navigation not filtered by role — restricted workspaces now hidden from unauthorized users (#521)
- Workspace region filters fall back to unfiltered when result is empty (#522)
- HTMX workspace region loading no longer causes unintended page navigation (#523)
- URL scheme validation in `_sync_fetch` prevents file:// SSRF (#519)
- SQL table name validation in control_plane `_delete_all_rows()` (#519)

### Changed
- 14 code smells fixed from systematic analysis (#504–#518): `_sessions` race condition locked, `__self_service__` monkey-patch removed, comparison logic deduplicated across 3 evaluators, 6 `_generate_field_value` implementations consolidated, FastAPI import guards centralized, HTTP error responses standardized, mutable globals protected with locks, core→backend layer boundary restored, dazzle_ui→dazzle_back dependency made one-directional, subsystem plugin infrastructure created, deep nesting reduced in parser/tokenizer/test runner
- `DazzleBackendApp` partially decomposed into subsystem plugins (9 modules, 6 dead `_init_*` methods removed)

### Removed
- `__self_service__` dynamic attribute pattern in route_generator.py
- 17 duplicate FastAPI import guard blocks (replaced by `_fastapi_compat.py`)
- `hx-push-url="true"` from workspace region templates (redundant with drawer JS)

## [0.42.0] - 2026-03-14

### Added
- **Surface field visibility by role** (`visible:` condition on sections and fields) — role-based RBAC for hiding sensitive fields/sections without duplicating surfaces (#487)
- `visible:` supports `role()`, `has_grant()`, compound `and`/`or` via existing ConditionExpr system
- `visible:` and `when:` can coexist on the same field (role-based vs data-driven visibility)
- **Grant schema infrastructure** — `grant_schema` DSL construct with `relation` sub-blocks, `has_grant()` condition function, `GrantStore` runtime with SQLite-backed CRUD and audit events
- Grant pre-fetching in workspace rendering for synchronous condition evaluation

### Fixed
- Pulse compliance scoring now reads DSL `classify` directives (confidence=1.0) before pattern matching (#488)
- Pulse security scoring counts default-deny as deliberate secure posture instead of penalising it (#488)
- `when_expr` silently dropped in multi-section (wizard) surface forms — now correctly propagated
- Auto-generate READ endpoints for entities with LIST surfaces (#482)
- Resolve `current_user` in workspace filters in test mode (#483)
- Cross-entity navigation resolved by shared workspace nav_groups (#477)
- Infer experience reachability from access spec (#476)

## [0.41.1] - 2026-03-12

### Changed
- `dazzle workshop` rewritten from Rich to Textual TUI with keyboard-driven drill-down
  - DashboardScreen: live active tools + recent completed history
  - SessionScreen: all calls grouped by tool, collapsible groups
  - CallDetailScreen: full progress timeline for a single call
  - Navigation: Enter to drill in, Esc to go back, j/k for movement
- Workshop now requires `textual>=1.0.0` via optional `workshop` extra

### Added
- Handler progress instrumentation: 15 handlers now emit structured progress events
  - pipeline, story.coverage, dsl_test, sentinel, composition, e2e_test,
    dsl.validate, dsl.fidelity, discovery, process.coverage, nightly
- `context_json` on tool completion events for structured summaries in workshop

## [0.41.0] - 2026-03-12

### Added
- **Convergent BDD:** `rule` DSL construct — domain-level business invariants with `kind` (constraint/precondition/authorization/derivation), `origin` (top_down/bottom_up), and `invariant` fields
- **Convergent BDD:** `question` DSL construct — typed specification gaps that block artifacts until resolved, with `blocks`, `raised_by`, and `status` fields
- `exercises:` field on stories — links stories to rules they exercise for convergence tracking
- Rule and question parser mixins (`RuleParserMixin`, `QuestionParserMixin`)
- Rule and question emitters (`emit_rule_dsl`, `emit_question_dsl`, `append_rules_to_dsl`, `append_questions_to_dsl`)
- Linker validation: rule scope, story exercises, question blocks, open-question-blocks-accepted-artifact error
- MCP operations: `rule_propose`, `rule_get`, `rule_coverage`, `question_get`, `question_resolve` (story tool); `converge`, `question_raise` (discovery tool)
- `rule(coverage)` and `rule(converge)` pipeline quality steps
- Convergence handler: structural analysis of rule-story alignment, gap detection, coverage scoring
- Semantics KB: `rule`, `question`, `convergence` concepts with aliases and relations

### Changed
- **Breaking:** Stories now use DSL-only persistence (`dsl/stories.dsl`) — removed JSON persistence layer (`stories.json`, `StoriesContainer`, `_inject_json_stories`)
- **Breaking:** `unless` keyword on stories raises parse error — use `rule` construct with boundary stories instead
- Story IR uses Gherkin fields (`given`, `when`, `then`) — removed legacy fields (`preconditions`, `happy_path_outcome`, `side_effects`, `constraints`, `variants`, `created_at`, `accepted_at`)
- `rbac_validation` example migrated from `unless` to rule + boundary story pattern

### Removed
- `StoryException` class and `unless` field from `StorySpec`
- `unless` handling from fidelity scorer, process proposals, process coverage, serializers
- `unless_block` from grammar
- `src/dazzle/core/stories_persistence.py` — JSON read/write layer
- `StoriesContainer` class and `with_status()` / `effective_given` / `effective_then` helpers
- `_inject_json_stories()` from appspec loader

## [0.40.0] - 2026-03-11

### Added
- Rhythm fidelity metric: `fidelity` operation measures how well surfaces serve scene intent by comparing `expects:` keywords against surface field names (#450)
- Surface reuse detection: `evaluate` handler flags surfaces used in multiple scenes with divergent `expects:` values as specialization signals (#448)
- Standardized action vocabulary: 7 action verbs mapped to 3 archetypes (observe, act, decide) with `classify_action()` API and advisory warnings for non-standard verbs (#449)
- Phase-level `depends_on:` field for declaring phase ordering constraints with circular dependency detection (#451)
- Phase kind `gate` for mandatory completion phases (#451)
- Phase-level `cadence:` field for temporal frequency hints (#447)
- Persona-scoped coverage metric respecting surface ACL `allow_personas`/`deny_personas` (#446)
- Scenes can target workspaces via `on:` field, tracked separately in coverage (#445)

### Fixed
- Rhythm `story:` field now accepts quoted strings for hyphenated IDs like `"ST-020"` (#452)

## [0.39.0] - 2026-03-11

### Added
- Rhythm DSL construct: `rhythm`, `phase`, `scene` keywords for longitudinal persona journey evaluation (#444)
- Rhythm MCP tool with 5 operations: `propose`, `evaluate`, `coverage`, `get`, `list`
- Static rhythm evaluation: surface existence, entity coverage, navigation coherence checks
- Rhythm conceptual guide (`docs/guides/rhythms.md`) and reference page (`docs/reference/rhythms.md`)

## [0.38.1] - 2026-03-10

### Added
- Declarative transition side effects: `on_transition:` blocks fire `create`/`update` actions on entity state changes (#435)
- Configurable per-field max upload size: `file(200MB)` DSL syntax overrides global security profile limit (#436)
- Post-upload event hook: `FILE_UPLOADED` event emitted to event bus after file upload with entity context; `entity.post_upload` hook point for Python hooks (#437)

## [0.38.0] - 2026-03-09

### Fixed
- Nav group `items` key collision with Python `dict.items()` in Jinja2 — renamed to `children` to fix TypeError/500 on workspace pages with nav_groups (#421)

### Added
- Documentation infrastructure: `dazzle docs generate` renders TOML knowledge base into human-readable reference docs; `dazzle docs check` validates coverage
- 17 auto-generated reference doc pages covering all DSL constructs (entities, access control, surfaces, workspaces, LLM, processes, ledgers, governance, etc.)
- 13 new knowledge base concepts for previously undocumented features (nav_group, approval, SLA, webhook, LLM triggers, visibility rules, etc.)
- README.md overhauled — slimmed from 1247 to 509 lines with auto-generated feature table linking to reference docs
- Deterministic demo data loading: `dazzle demo load` loads seed CSV/JSONL files into a running instance via REST API with FK-aware topological ordering (#420)
- `dazzle demo validate` validates seed files against DSL (FK integrity, enum values, field coverage)
- `dazzle demo reset` clears and reloads demo data (deletes in reverse dependency order, then reloads)
- MCP `demo_data` tool: new `load` and `validate_seeds` operations complete the propose → save → generate → load lifecycle
- LLM intent execution: `/_dazzle/llm/execute/{intent_name}` triggers intents at runtime, records AIJob for cost tracking
- MCP `llm` tool: `list_intents`, `list_models`, `inspect_intent`, `get_config` operations
- Collapsible navigation groups with Lucide icon support in workspace DSL (`nav_group` keyword) and app shell sidebar (#418)
- LLM async event queue: background job queue with token-bucket rate limiting and per-model semaphore concurrency (#417)
- LLM entity triggers: `trigger:` clause on `llm_intent` fires intents on entity created/updated/deleted events with input mapping, write-back, and conditional execution
- `llm_config` gains `concurrency:` block for per-model max concurrent request limits
- Process `llm_intent` step kind: processes can now execute LLM intents as steps with `input_map` context resolution
- Linear checkpointed process executor: sequential step execution with checkpoint-based resume on restart
- Async job execution: `POST /_dazzle/llm/execute/{intent_name}?async_mode=true` queues jobs and returns `job_id`; poll with `GET /_dazzle/llm/jobs/{job_id}`
- MCP `graph` tool: new `triggers` operation shows cross-references (what fires when entity X event Y occurs)
- Workspace context selector: multi-scope users get a dropdown to filter all workspace regions by a scope entity (e.g., School) with preference persistence (#425)
- DSL-driven reference data seeding: entities with `seed:` blocks auto-generate rolling-window rows (academic years, fiscal years) at server startup with idempotent upsert (#428)
- FK traversal support in workspace region filter validation (#419)

## [0.37.0] - 2026-03-07

### Added
- AST-level test verifying all server startup paths pass `app_prefix` to `create_page_routes` — prevents #408-style regressions
- AST-level test ensuring auth routes returning `Response` use `include_in_schema=False` — prevents #411-style regressions

### Changed
- Unified server startup paths: `run_unified_server()` and `create_app_factory()` now share `build_server_config()` and `assemble_post_build_routes()`
- `dazzle serve --local` gains experience routes, entity list projections, search fields, auto-includes, schedule sync
- `create_app_factory()` gains route validation
- `run_backend_only()` gains entity projections and search fields

### Fixed
- `dsl-run --cleanup` now cascade-deletes child records before parents, preventing orphaned rows from FK references (#407)
- Sidebar nav links missing `/app` prefix in `dazzle serve` mode — `combined_server.py` now passes `app_prefix="/app"` to `create_page_routes` (#408)
- `ref_display` chain now recognises `forename`/`surname` fields — FK columns for UK naming conventions show names instead of UUIDs (#409)
- `dsl-run --cleanup` no longer queries API for child records — uses topological sort of tracked entities, avoiding RBAC 403 errors (#410)
- `/openapi.json` no longer crashes with `PydanticUserError` — auth and email tracking routes returning `Response` excluded from schema (#411)

## [0.36.0] - 2026-03-07

### Added
- `events` extras group (`pip install dazzle-dsl[events]`) for optional event system dependency (aiosqlite)
- `NullBus` and `NullEventFramework` no-op implementations in `dazzle_back.events.null` — always importable regardless of extras
- `dazzle_back.events.api` public API boundary module for alternative event bus implementations
- Wire `EventEmittingMixin.set_event_framework()` at server startup (fixes dead code bug)
- Event system imports gated behind `EVENTS_AVAILABLE` flag — apps without event extras stay lean

### Fixed
- Workspace redirect missing `/app` prefix — `_workspace_root_route()` now returns `/app/workspaces/{name}` (#406)
- Login form ignoring persona-specific redirect URL — now uses `redirect_url` from server response (#406)
- Role prefix mismatch preventing persona-based routing — `role_` prefix now stripped when matching user roles against persona IDs in auth redirect, RBAC checks, nav filtering, and workspace access (#406)

## [0.35.0] - 2026-03-06

### Added
- **Team section type** (`type: team`) — dedicated cards for team/people pages with circular avatar (image or auto-generated initials), name, role, bio, and social links (linkedin, email, twitter, github) (#394)
- **Section backgrounds** — `background: alt | primary | dark` on any section for visual rhythm; `layout.section_backgrounds: auto-alternate` for automatic alternating backgrounds (#395)
- **Media rendering** in `card_grid` and `features` sections — `section_media()` macro in `_helpers.html` for reusable section-level images (#396)
- **Validation warning** when `media` is set on section types that don't render it (#396)
- **`sitespec advise` MCP operation** — proactive layout suggestions: missing hero sections, background variation, team section recommendations, long markdown splitting (#397)
- **Media.src path validation** — `sitespec validate` warns on non-`/static/` paths and missing files; imagery prompts include `save_to` and `sitespec_src` fields (#391)
- jsDelivr CDN distribution — framework CSS/JS served from `cdn.jsdelivr.net` for faster loading and cache sharing across Dazzle-powered sites
- `dist/dazzle.min.css` (43 KB) — micro-runtime + design system + site sections CSS bundle
- `dist/dazzle.min.js` (131 KB) — HTMX + extensions + micro-runtime JS bundle
- `dist/dazzle-icons.min.js` (350 KB) — Lucide icons bundle (site pages only)
- `scripts/build_dist.py` — concatenates and minifies framework assets into `dist/`
- `scripts/update_vendors.py` — checks/downloads latest vendor JS versions (htmx, idiomorph, lucide)
- `.github/workflows/update-vendors.yml` — weekly automated vendor update PR
- `[ui] cdn = false` in `dazzle.toml` — disables CDN for air-gapped deployments
- `_dazzle_version` and `_use_cdn` Jinja2 globals in template renderer

### Changed
- `base.html` and `site_base.html` now load framework assets from jsDelivr CDN by default, with local vendored fallback when CDN is disabled

### Fixed
- **Legal page CSS** — constrained width (45rem) and left-aligned headings for terms/privacy pages (#393)
- **Markdown `<hr>` styling** — horizontal rules render as subtle centered gradient lines instead of crude browser default (#398)
- **Infrastructure banner** no longer shows stale `.dazzle/data.db` or "Lite (in-process)" when PostgreSQL is configured (#390)
- **Circular FK migration** — `Department ↔ User` foreign keys no longer fail migration (#389)
- **Heroku deployment** — `[serve]` extra installs runtime dependencies (`uvicorn`, `gunicorn`, etc.) (#388)

### Removed
- `LiteProcessAdapter` and `DevBrokerSQLite` — deprecated SQLite-based process/event backends fully removed; PostgreSQL is now required for event bus
- `SQLITE` tier from `EventBusTier` enum

## [0.34.0] - 2026-02-23

### Added
- `ApiResponseCache` — async Redis cache for external API responses with scoped keys, dedup locking, and lazy connection (`dazzle_back.runtime.api_cache`)
- `cache:` keyword in integration mapping blocks — per-mapping TTL (e.g. `cache: "24h"`) parsed via `parse_duration()`
- Fragment route caching — search (5 min TTL) and select (1 hour TTL) endpoints use shared `ApiResponseCache`
- `cache_ttl` values for all API pack foreign models — data-volatility-appropriate defaults across all 10 packs
- `format_duration()` helper — converts seconds to compact duration strings (86400 → "1d", 300 → "5m")
- `ApiPack.generate_integration_template()` — generates DSL integration blocks with `cache:` directives from pack metadata
- `generate_service_dsl` MCP handler now returns `integration_template` field with recommended cache settings
- Pack TTL fallback in `MappingExecutor` — when no `mapping.cache_ttl` is set, looks up the pack's foreign model `cache_ttl` before falling back to the default
- Built-in entity CRUD operations for process service steps — `Entity.create`, `Entity.read`, `Entity.update`, `Entity.delete`, `Entity.transition` now execute directly against PostgreSQL without requiring custom Python service modules (#345)
- Entity metadata (fields, status_field) stored in Redis at startup by `ProcessManager` for Celery worker access
- `query` step kind — queries entities matching Django-style filters (e.g. `{"due_date__lt": "today", "status__not_in": ["completed"]}`) with date literal resolution (#346)
- `foreach` step kind — iterates over query results and executes sub-steps for each item, enabling batch operations like escalation workflows (#346)
- AI cost tracking gateway — `budget_alert_usd`, `default_provider` on `llm_config`; `vision`, `description` on `llm_intent`; auto-generated `AIJob` entity for cost/token audit trail (#376)
- Integration data transformation — `transform:` block on integration mappings with `jmespath`, `template`, and `rename` expressions (#383)
- Workflow Field Specification (WFS) — `wfs_fields:` block on process steps for field-level read/write/required declarations with runtime enforcement (#375)

### Changed
- `MappingExecutor` now accepts `cache: ApiResponseCache | None` instead of auto-creating sync Redis. All cache operations are async
- Cache keys scoped to `api_cache:{scope}:{url_hash}` preventing collisions across integrations
- Cache TTL priority chain: DSL `cache:` directive > pack TOML `cache_ttl` > default 86400
- Replaced `getattr()` string literals with typed attribute access across agent missions, persona journey, workspace/UI files (#367)
- Eliminated `BackendSpec` from main code path — runtime uses `AppSpec` directly (#369)
- Wired `EventBusProcessAdapter` into app startup, simplified Procfile (#368)
- Eliminated Celery dependency for event bus — native async process adapter (#368)
- Fixed silent exception handlers in event delivery path (#365)

### Improved
- Eliminated 8 swallowed exceptions (`except Exception: pass`) — all now log at appropriate levels (debug/info/warning)
- Extracted Cedar/audit helpers in `route_generator.py` — `_build_access_context()`, `_record_to_dict()`, `_log_audit_decision()` replace ~140 lines of duplicated code across 7 handler closures
- Canonicalized AppSpec loading in `tool_handlers.py` — 7 inline manifest→discover→parse→build patterns replaced with single `load_project_appspec()` calls

### Fixed
- `ProcessStateStore` UUID serialization error — `json.dumps()` now uses a custom encoder that handles `uuid.UUID`, `datetime`, `date`, and `Decimal` objects from psycopg v3 / SQLAlchemy (#344)
- `create_app_factory()` now loads persisted processes from `.dazzle/processes/processes.json` — previously only DSL-parsed processes were used, leaving ProcessManager empty when processes were composed via MCP (#343)
- Sync Redis in async context — replaced `import redis` with `redis.asyncio` in cache layer
- `cache=False/None` still created cache — disabled state now respected via `enabled` flag
- Dedup lock never released — `release_lock()` called in `finally` block after HTTP response
- Lock key collisions across integrations — keys now include `{integration}:{mapping}` scope
- `force_refresh=True` blocked by dedup lock — lock check skipped when force-refreshing
- Blocking `redis.ping()` in constructor — connection is now lazy (first `get()`/`put()`)
- Hardcoded `ssl.CERT_NONE` — removed, uses redis-py defaults (validates certs)
- CI test `test_crud_service_with_repository` — fixture missing surface, service name convention mismatch

### Removed
- `IntegrationCache` class from `mapping_executor.py` — replaced by `ApiResponseCache`

## [0.33.0] - 2026-02-19

### Added
- Canonical AppSpec loader (`dazzle.core.appspec_loader`) — single implementation of manifest → discover → parse → build pipeline, replacing 6 duplicate copies (#329)
- `error_response()` and `unknown_op_response()` factory functions in MCP handler common module, replacing ~100 inline `json.dumps({"error": ...})` calls (#329)
- Experience flow entity orchestration — `context:`, `prefill:`, `saves_to:`, `when:` blocks for multi-entity experience steps (#326)
- Process step side-effect actions for cross-entity automation (#323)
- Multi-source workspace regions with tabbed display (#322)
- Guided review surface mode with queue navigation and approve/return actions (#325)
- Experience flow resume with durable file-based progress persistence (#324)
- Polymorphic FK detection for related entity tabs (#321)

### Changed
- HTMX utilities (`HtmxDetails`, `htmx_error_response`) moved from `dazzle_back` to `dazzle_ui.runtime.htmx` — correct layer ownership (#329)
- Backward compatibility policy: clean breaks preferred over shims; breaking changes communicated via CHANGELOG (#329)

### Removed
- Backward-compat shims: `get_project_path()` alias, pipeline/nightly aliases, archetype→stage aliases, `paths.py` re-export module, `handlers/utils.py` re-export module, `site_renderer.py` shim functions, `DNRDevServer`/`DNRDevHandler` aliases, `docker_runner.py` re-export module (#329)
- Deprecated `db_path` parameters from 6 constructor signatures (`TokenStore`, `AuthStore`, `FileMetadataStore`, `OpsDatabase`, `DeviceRegistry`, `create_local_file_service`, `create_s3_file_service`) (#329)
- CLI utils backward-compat aliases (`_print_human_diagnostics`, etc.) (#329)

### Fixed
- Last 2 swallowed exceptions in `workspace_rendering.py` now log at WARNING level (#329)
- Expression evaluator duplication eliminated — shared `dazzle_ui.utils.expression_eval` module (#327)
- Reduced MCP handler inner catches from 71 to 38 (#327)

## [0.32.0] - 2026-02-17

### Added
- Dead construct detection lint pass — warns on unreachable surfaces, entities with no surfaces, orphaned views, and undefined service references (#279)
- Source locations on IR nodes — parser attaches file/line/column to all major constructs for source-mapped diagnostics (#280)
- Query pre-planning at startup — projection pushdown from surface section fields, not just view-backed surfaces (#281)
- Template constant folding — pre-compute workspace column metadata at startup instead of per-request (#282)
- Workspace query batching — concurrent aggregate metric queries via asyncio.gather (#283)
- `dazzle build --target` codegen pipeline — SQL DDL, OpenAPI, and AsyncAPI code generation targets with `--check` validation-only mode (#284)

## [0.31.0] - 2026-02-17

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
- Declarative integration mappings: `base_url`, `auth`, `mapping` blocks with HTTP requests, lifecycle triggers, response field mapping, and error strategies ([#275](https://github.com/manwithacat/dazzle/issues/275))

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
