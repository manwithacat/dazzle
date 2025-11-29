# DAZZLE Development Roadmap

**Last Updated**: 2025-11-28
**Current Version**: v0.3.0 (in development)
**Status**: DNR is primary runtime, legacy stacks deprecated

---

## Executive Summary

DAZZLE has undergone a **strategic transformation** from a code generation toolkit to a **native runtime platform**. The Dazzle Native Runtime (DNR) now runs applications directly from DSL specifications, eliminating the generate-then-deploy workflow.

**Key Shift**: DSL → Generated Code → Deploy **became** DSL → DNR Runtime → Live App

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

### v0.3.0 - DNR & Layout Engine (Current) 🔄 IN PROGRESS

**Status**: Phase 2 Horizontal COMPLETE, Phase 5 in progress
**Target Release**: December 2025

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

## Upcoming Releases

### v0.3.1 - Critical Bug Fixes & E2E Testing (PRIORITY)

**Status**: 🔴 CRITICAL - Required before any other work
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

#### MCP Server Improvements (TODO)
- [ ] Improve MCP context for Claude engagement
- [ ] Add getting-started workflow guidance
- [ ] Document common DSL patterns

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

### v0.3.3 - DNR Developer Experience (February 2026)

**Focus**: Make development delightful

**Planned Features**:

#### Hot Reload & Dev Tools
- DSL file watching with instant reload
- Browser dev tools panel
- State inspector
- Network request viewer

#### Debugging & Visualization
- `dazzle dnr inspect` command
- Action log viewer
- State diff visualization
- Layout plan visualizer in browser

**Estimate**: 4-6 weeks

---

### v0.4.0 - DNR Production Ready (March 2026)

**Focus**: Production deployment and testing

**Planned Features**:

#### Testing & Validation
- DSL `test` blocks with spec-based testing
- Playwright integration for UI tests
- API contract testing
- Performance benchmarks
- Accessibility checks

#### Deployment & Distribution
- `dazzle dnr build` for production bundles
- Docker image generation
- Environment configuration
- Database migrations for production
- Health monitoring endpoints

**Estimate**: 6-8 weeks

---

### v0.5.0 - Advanced DSL Features (Q2 2026)

**Focus**: DSL language enhancements for complex apps

**Planned Features**:

#### Component Roles
```dsl
component TaskCard:
  role: presentational
  props:
    task: Task
    onEdit: action
```

#### Action Purity (Explicit)
```dsl
actions:
  toggleFilter: pure
    filter = not filter

  saveTask: impure
    effect: fetch POST /tasks body=currentTask
```

#### Access Rules (Inline)
```dsl
entity Task:
  access:
    read: owner = current_user or shared = true
    write: owner = current_user
```

**Estimate**: 8-10 weeks

---

### v0.6.0 - Multi-Platform (Q3 2026)

**Focus**: Beyond web applications

**Planned Features**:
- React Native runtime (mobile)
- Desktop app packaging (Electron/Tauri)
- Offline-first patterns
- Cross-platform sync

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

---

## Success Metrics

### v0.3.0 Success Criteria

- [x] `dazzle dnr serve` starts a real app with persistence
- [x] CRUD operations work end-to-end
- [x] Authentication and authorization functional
- [x] File uploads and rich text work
- [x] Real-time updates in browser
- [x] 5 layout archetypes implemented
- [x] All example projects demonstrate archetypes
- [ ] Version bump to 0.3.0
- [ ] Release announcement

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
**Last Review**: 2025-11-28
**Next Review**: December 2025 (post v0.3.0 release)

---

## Changelog

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
