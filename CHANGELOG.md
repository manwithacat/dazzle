# Changelog

All notable changes to DAZZLE will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.4.0] - 2025-12-02

### Added

**Dazzle Native Runtime (DNR) - Phase 1 Complete + Phase 2 Auth**:
- **Backend Runtime** (Week 1-2):
  - SQLite database auto-creation from entity specs
  - Auto-migration system with safe schema change detection
  - CRUD endpoints generated dynamically from BackendSpec
  - Repository pattern with SQLite persistence
  - Dynamic Pydantic model generation from EntitySpec
  - 8 E2E tests covering full CRUD lifecycle

- **Frontend Runtime** (Week 3-4):
  - Combined server architecture (backend + frontend in one process)
  - API proxy for seamless frontend-backend communication
  - Hot reload support via Server-Sent Events
  - Signals-based UI runtime (pure JavaScript)
  - Vite generator for production builds
  - 15 combined server tests

- **Behaviour Layer** (Week 5-6):
  - Enhanced signals: `batch()`, `createResource()`, cleanup on dispose
  - Pure actions: filter, sort, select, toggle, reset
  - Impure actions via `apiClient` (CRUD helpers)
  - Effects system: fetch, navigate, toast, log, custom
  - Global loading/error states with notifications
  - UI components: Loading, Error, Empty, Modal
  - Patch operations: SET, MERGE, APPEND, REMOVE, DELETE
  - 44 behaviour layer tests

- **Authentication & Authorization** (Week 7-8):
  - Session-based authentication with PBKDF2 password hashing
  - AuthStore class with SQLite persistence (users, sessions)
  - Login/logout/register/me/change-password endpoints
  - AuthMiddleware for session validation
  - User entity auto-detection from BackendSpec
  - Dependency injection for protected routes
  - Role-based access control (`require_roles` parameter)
  - Optional vs required authentication modes
  - 65 auth tests

- **Row-Level Security** (Week 7-8):
  - Owner-based access control (filter by `owner_id`, `user_id`, etc.)
  - Tenant-based access control (filter by `tenant_id`, `organization_id`)
  - AccessContext for user/tenant/role information
  - AccessPolicy with configurable rules per entity
  - AccessEnforcer for repository-level enforcement
  - Auto-detection of owner and tenant fields
  - Multi-tenant architecture design document
  - 42 RLS tests

- **File Uploads & Rich Fields** (Week 9-10):
  - New field types: FILE, IMAGE, RICHTEXT
  - Local storage backend with date-organized file paths
  - S3-compatible storage backend (AWS S3, MinIO)
  - File metadata SQLite store with entity association
  - File validation (size limits, MIME type checking)
  - Secure filename sanitization
  - Image thumbnail generation (Pillow integration)
  - Image optimization and format conversion
  - File upload REST endpoints (upload, download, delete, stream)
  - Entity-scoped file queries
  - Markdown processor with HTML rendering
  - HTML sanitization (XSS prevention via bleach)
  - Inline base64 image extraction and upload
  - Text extraction for search indexing
  - 34 file storage tests + 26 image processor tests + 36 rich text tests

- **Relationships & Queries** (Week 11-12):
  - QueryBuilder for advanced filtering and sorting
  - Filter operators: eq, ne, gt, gte, lt, lte, contains, icontains, startswith, endswith, in, not_in, isnull, between
  - Relation path filters (e.g., `owner__name__contains`)
  - Multi-field sorting with ascending/descending support
  - RelationRegistry for tracking entity relationships
  - Auto-detection of implicit relations from ref fields
  - Nested data fetching via `include` parameter
  - Batch loading to avoid N+1 queries
  - Foreign key constraint generation
  - Full-text search with SQLite FTS5
  - Auto-detection of searchable text fields
  - Sync triggers for insert/update/delete
  - Search with snippets and highlighting
  - 56 query builder tests + 24 relation tests + 28 FTS tests

- **Real-time & Collaboration** (Week 13-14):
  - WebSocket manager for connection lifecycle management
  - Channel-based pub/sub subscriptions
  - Entity event bus (CREATED, UPDATED, DELETED)
  - Live updates broadcast to subscribers
  - Presence tracking (who's viewing what)
  - Heartbeat-based activity detection
  - Optimistic UI updates for instant feedback
  - RealtimeClient JavaScript class with reconnection
  - PresenceManager for collaboration awareness
  - EntitySync for auto-updating signals
  - 76 real-time tests (26 WebSocket + 22 event bus + 28 presence)

**New CLI Commands**:
- `dazzle dnr serve`: Run complete DNR app with backend and frontend
  - `--port`: Frontend port (default: 3000)
  - `--api-port`: Backend API port (default: 8000)
  - `--db`: SQLite database path (default: .dazzle/data.db)
  - `--ui-only`: Serve static UI only (no backend)
- `dazzle dnr build-ui`: Generate UI artifacts from AppSpec
- `dazzle dnr build-api`: Generate API spec from AppSpec
- `dazzle dnr info`: Show DNR installation status

**New Packages**:
- `dazzle_dnr_back`: Backend runtime (FastAPI + SQLite)
  - `runtime/server.py`: DNRBackendApp builder
  - `runtime/repository.py`: Repository pattern implementation
  - `runtime/migrations.py`: Auto-migration system
  - `runtime/model_generator.py`: Dynamic Pydantic models
  - `runtime/service_generator.py`: CRUD service layer
  - `runtime/route_generator.py`: FastAPI route generation
- `dazzle_dnr_ui`: Frontend runtime (signals-based JS)
  - `runtime/js_generator.py`: JavaScript code generation
  - `runtime/vite_generator.py`: Vite project generation
  - `runtime/combined_server.py`: Unified dev server
  - `runtime/dev_server.py`: Standalone dev server
  - `runtime/file_storage.py`: File storage backends (local, S3)
  - `runtime/file_routes.py`: File upload REST endpoints
  - `runtime/image_processor.py`: Image processing utilities
  - `runtime/richtext_processor.py`: Rich text/markdown processing
  - `runtime/websocket_manager.py`: WebSocket connection manager
  - `runtime/event_bus.py`: Entity change event bus
  - `runtime/presence_tracker.py`: User presence tracking
  - `runtime/realtime_routes.py`: WebSocket endpoint setup
  - `runtime/realtime_client.py`: Frontend realtime JavaScript

### Changed
- Legacy stack deprecation began - DNR is now the recommended approach
- Updated examples to use DNR workflow

### Improved
- **JavaScript Restructuring**: Refactored monolithic inline JavaScript into modular files
  - Created `static/js/` directory with 13 separate JS modules
  - Modules: signals, state, api-client, toast, dom, binding, components, renderer, actions, theme, app, index, realtime
  - New `js_loader.py` handles module loading and bundle generation
  - Supports both IIFE (browser-compatible) and ESM (modern) output formats
  - Backward compatible - existing imports continue to work
  - 17 new tests for the JS loader

### Status
- **Phase 1 (Vertical)**: Complete ✅ (All 6 weeks)
- **Phase 2 Week 7-8**: Complete ✅ (Authentication & Row-Level Security)
- **Phase 2 Week 9-10**: Complete ✅ (File Uploads & Rich Fields)
- **Phase 2 Week 11-12**: Complete ✅ (Relationships & Queries)
- **Phase 2 Week 13-14**: Complete ✅ (Real-time & Collaboration)
- **Next**: Phase 3 - Hot Reload & Dev Tools (Week 15-16)
- See `dev_docs/roadmap_v0_4_0_dnr.md` for full roadmap

---

## [0.1.1] - 2025-11-23

### Fixed

**express_micro stack**:
- **CRITICAL**: Added graceful fallback for AdminJS on incompatible Node.js versions (v25+)
- **CRITICAL**: Added Node.js version constraints to package.json (`>=18.0.0 <25.0.0`)
- **HIGH**: Fixed missing `title` variable in all route handlers (detail, form, delete views)
- **HIGH**: Fixed admin interface not being mounted in server.js
- **HIGH**: Improved error handling with contextual logging in all routes
- **MEDIUM**: Removed deprecated `--backend` flag from generated README.md

### Added

**express_micro stack**:
- Environment variable support with dotenv
- Generated `.env.example` file with all configuration options
- Contextual error messages for better debugging
- Error logging with `console.error()` in all catch blocks

### Changed

**express_micro stack**:
- Server now loads `.env` file automatically on startup
- Admin interface only shows URL in console if successfully loaded
- Error messages now more user-friendly ("Please try again later")
- README regeneration instructions simplified

---

## [0.3.0] - Planned

### Planned Features

**Pattern Support** (Phase 1):
- Add `@pattern` annotation syntax to DSL for explicit architectural pattern modeling
- Support 5 core patterns: repository, service, ports_and_adapters, cqrs, observer
- Implement pattern-aware code generation in django_micro_modular and express_micro stacks
- Pattern annotations are optional - apps work without them
- Documentation: Pattern usage guide and examples

**Design Pattern DSL Evaluation**:
- Comprehensive evaluation of proposed Design Pattern DSL (DP-DSL) layer completed
- Full implementation roadmap defined across v0.3.0 - v0.5.0
- Phased approach: Pattern Annotations (v0.3.0) → DP-DSL Prototype (v0.4.0) → Full DP-DSL (v0.5.0)
- See `dev_docs/architecture/dp_dsl_evaluation_and_roadmap.md` for complete analysis and roadmap

**Additional Planned**:
- Enhanced pattern detection and architectural linting
- Stack compatibility matrix for pattern support
- Pattern-based example projects
- Design spike: ports-and-adapters implementation for UserRegistration use case

**Status**: Under evaluation for Q1 2026 release

---

## [0.2.0] - Planned

### Planned Features

**Testing Infrastructure** (Priority 1):
- Generate Jest/pytest test structure for all CRUD operations
- Model tests with fixtures and validation
- Route/endpoint tests with supertest/pytest-django
- Test coverage reporting

**Database Migrations** (Priority 2):
- Replace `sync({force: true})` with proper migration system
- Sequelize CLI integration for express_micro
- Django migrations already supported in django stacks
- Migration history and rollback support

**Production Features** (Priority 3-7):
- Health check endpoint with database connectivity checks
- Security headers (helmet/django-csp)
- Pagination support for list views
- Auto-generated database indexes on foreign keys
- Logging framework (winston/python logging)

**Timeline**: 7-8 weeks estimated
**Status**: See `dev_docs/roadmap_v0_2_0.md` for detailed specifications

---

## [0.1.0] - 2025-11-22

### Added

**Core Features**:
- Complete DSL parser supporting entities, surfaces, experiences, services, integrations, tests
- Internal Representation (IR) with full Pydantic type system (900+ lines)
- Module system with dependency resolution, cycle detection, topological sorting
- Linker with symbol table building and cross-reference validation
- Comprehensive validation and linting system
- Pattern detection (CRUD, integrations, experience flows)

**Stacks** (6 production-ready):
- `django_micro_modular`: Django apps with admin, forms, views, templates
- `django_api`: Django REST Framework with OpenAPI integration
- `express_micro`: Node.js/Express with Sequelize ORM and AdminJS
- `openapi`: OpenAPI 3.0 specification generation
- `docker`: Docker Compose multi-service orchestration
- `terraform`: AWS infrastructure (ECS, RDS, VPC, ALB)

**CLI Commands**:
- `init`: Initialize new project
- `validate`: Parse, link, and validate DSL
- `lint`: Extended validation with naming conventions
- `build`: Generate code from AppSpec
- `inspect`: Show module interfaces and patterns
- `analyze-spec`: Parse natural language specifications with LLM
- `clone`: Clone example projects
- `demo`: Create demo project
- `example`: Build in-place examples

**LLM Integration**:
- Spec analysis (natural language → structured requirements)
- DSL generation (requirements → .dsl files)
- Interactive Q&A for clarifications
- Cost estimation and safety checks
- Support for Anthropic Claude and OpenAI GPT

**IDE & Tooling**:
- LSP server with real-time diagnostics, hover, completions, go-to-definition
- VS Code extension with syntax highlighting and validation
- Test suite with 59+ tests (unit, integration, LLM)

**Examples**:
- `simple_task`: Minimal starter project (1 entity, 4 surfaces)
- `support_tickets`: Production-like complexity (3 entities, relationships, workflows)

### Documentation
- Complete DSL reference (`docs/DAZZLE_DSL_REFERENCE_0_1.md`)
- EBNF grammar (`docs/DAZZLE_DSL_GRAMMAR_0_1.ebnf`)
- IR documentation (`docs/DAZZLE_IR_0_1.md`)
- VS Code extension user guide
- Stack development guides

---
