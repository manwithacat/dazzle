# DAZZLE v0.4.0 Roadmap - DNR: From Spec to Running App

**Status**: Phase 3 Week 21-22 complete (Deployment & Distribution)
**Target**: Q1 2025
**Focus**: Make DNR actually run applications from DSL
**Theme**: Vertical depth → Horizontal breadth → Meta tooling

---

## Vision

**Before (Stacks Era)**: DSL → Generate Code → User deploys code
**Now (DNR Era)**: DSL → Runtime Specs → DNR serves the app directly

DNR is not a code generator. It's a **runtime** that interprets Dazzle specs to serve real applications. Think:
- Retool/Appsmith (low-code platforms)
- Hasura (instant GraphQL from schema)
- Supabase (instant APIs from Postgres)

With one key difference: **Dazzle is DSL-first and LLM-friendly**.

---

## Architecture Refresh

### Three-Layer Model (from DNR-SeparationOfConcerns-v1)

```
┌─────────────────────────────────────────────────────────────┐
│                    DAZZLE DSL                               │
│  (entities, surfaces, workspaces, experiences, services)    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    AppSpec (IR)                             │
│      Parsed, linked, validated representation               │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   BackendSpec   │ │  BehaviourSpec  │ │     UISpec      │
│                 │ │                 │ │                 │
│ - Entities      │ │ - State atoms   │ │ - Workspaces    │
│ - Services      │ │ - Actions       │ │ - Components    │
│ - Endpoints     │ │ - Effects       │ │ - View trees    │
│ - Auth          │ │ - Transitions   │ │ - Themes        │
└─────────────────┘ └─────────────────┘ └─────────────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    DNR Runtime                              │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ FastAPI     │  │ Signals     │  │ Vite/Preact │         │
│  │ Backend     │◄─┤ State Mgmt  ├─►│ Frontend    │         │
│  │ (Python)    │  │ (JS)        │  │ (JS)        │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Separation of Concerns (Enforced)

| Layer | Owns | Cannot Reference |
|-------|------|------------------|
| **Backend** | Entities, Services, Endpoints, Auth | UI components, views, layout |
| **Behaviour** | State atoms, Actions (pure/impure), Effects | DOM, rendering, backend internals |
| **UI** | Workspaces, Components, Views, Themes | Business logic, direct backend calls |

**Key Insight**: With a native runtime target, we can be more opinionated. The DSL can enforce these boundaries at parse time.

---

## Phase 1: Vertical (Make One Thing Work End-to-End)

**Goal**: `dazzle dnr serve` runs a real app with data persistence

### Week 1-2: Backend Runtime ✅ COMPLETE

**Make `dazzle dnr serve` start a real FastAPI server**

Tasks:
- [x] SQLite database auto-creation from entities
- [x] Auto-migration on entity changes
- [x] CRUD endpoints generated from BackendSpec
- [x] JSON REST API (no auth yet)
- [x] Health check endpoint

```bash
$ dazzle dnr serve
Starting DNR...
  Backend: http://localhost:8000
  API Docs: http://localhost:8000/docs
  Database: .dazzle/data.db
```

**Deliverables**:
- [x] Working FastAPI server from `simple_task` example
- [x] Create, read, update, delete tasks via API
- [x] Data persists in SQLite

**Implementation Summary (Nov 2025)**:
- Repository pattern with SQLite persistence (`src/dazzle_dnr_back/runtime/repository.py`)
- Auto-migration system with safe schema changes (`src/dazzle_dnr_back/runtime/migrations.py`)
- Dynamic Pydantic model generation (`src/dazzle_dnr_back/runtime/model_generator.py`)
- CRUD service layer (`src/dazzle_dnr_back/runtime/service_generator.py`)
- Route generator with FastAPI integration (`src/dazzle_dnr_back/runtime/route_generator.py`)
- 8 E2E tests covering full CRUD lifecycle

### Week 3-4: Frontend Runtime ✅ COMPLETE

**Make UISpec render in browser**

Tasks:
- [x] Vite dev server integration (via combined server)
- [x] UISpec → JavaScript components (signals-based)
- [x] Archetype layouts render correctly
- [x] Connect to backend API (API proxy)
- [x] Basic forms for create/edit

```bash
$ dazzle dnr serve
============================================================
  DAZZLE NATIVE RUNTIME (DNR)
============================================================

[DNR] Backend:  http://127.0.0.1:8000
[DNR] API Docs: http://127.0.0.1:8000/docs
[DNR] Database: .dazzle/data.db

[DNR] Frontend: http://127.0.0.1:3000
```

**Deliverables**:
- [x] Browser opens with working UI
- [x] Task list displays real data
- [x] Create new task via form
- [x] Changes persist to database

**Implementation Summary (Nov 2025)**:
- Combined server architecture (`src/dazzle_dnr_ui/runtime/combined_server.py`)
  - Backend: FastAPI on port 8000 with SQLite persistence
  - Frontend: Dev server on port 3000 with API proxy
  - Hot reload support via SSE
- JS Generator for signals-based UI (`src/dazzle_dnr_ui/runtime/js_generator.py`)
- Vite generator for production builds (`src/dazzle_dnr_ui/runtime/vite_generator.py`)
- CLI integration: `dazzle dnr serve` command
- 15 combined server tests + 8 E2E tests

### Week 5-6: Behaviour Layer ✅ COMPLETE

**Wire up state management and actions**

Tasks:
- [x] Signals-based state (custom signals implementation)
- [x] Pure actions (filter, select, sort, toggle, reset)
- [x] Impure actions (fetch, save, delete via apiClient)
- [x] Effects system (API calls, navigation, toasts, log, custom)
- [x] Loading/error states (globalLoading, globalError, notifications)

**Deliverables**:
- [x] Full CRUD workflow in browser
- [x] State updates reactively
- [x] Error handling with toasts
- [x] Navigation between workspaces

**Implementation Summary (Nov 2025)**:
- Enhanced signals system with `batch()`, `createResource()`, cleanup on effect dispose
- API client with CRUD helpers (`apiClient.list()`, `.create()`, `.update()`, `.remove()`)
- Toast notification system with variants (success, error, warning, info)
- Patch operations (SET, MERGE, APPEND, REMOVE, DELETE)
- Built-in actions: filter, sort, select, toggle, reset
- UI components: Loading, Error, Empty, Modal
- 44 behaviour layer tests covering all functionality

### Vertical Phase Success Criteria ✅ COMPLETE

- [x] `simple_task` example runs end-to-end ✅ (Week 1-4)
- [x] Create, read, update, delete tasks ✅ (Week 1-2)
- [x] Data persists across restarts ✅ (Week 1-2)
- [x] Multiple workspaces navigate correctly ✅ (Week 5-6)
- [x] < 3 second cold start ✅ (Verified)

**Phase 1 Complete!** 🎉 All vertical milestones achieved.

---

## Phase 2: Horizontal (Add Capabilities)

**Goal**: Production-ready features

### Week 7-8: Authentication & Authorization ✅ COMPLETE

Tasks:
- [x] User entity auto-detection
- [x] Session-based auth (cookies)
- [x] Login/logout flows
- [x] Auth middleware / dependency injection
- [x] Row-level security (owner-based)
- [ ] DSL syntax for auth rules (deferred to future)

**Implementation Summary (Nov 2025)**:
- Session-based authentication with PBKDF2 password hashing (`src/dazzle_dnr_back/runtime/auth.py`)
- AuthStore class with SQLite persistence for users and sessions
- AuthMiddleware for session validation
- Login/logout/register/me/change-password endpoints
- User entity auto-detection (`src/dazzle_dnr_back/runtime/auth_detection.py`)
- Dependency injection for protected routes (`create_auth_dependency`, `create_optional_auth_dependency`)
- Role-based access control via `require_roles` parameter
- 65 auth tests covering all functionality

**Row-Level Security** (`src/dazzle_dnr_back/runtime/access_control.py`):
- `AccessContext`: User/tenant context for access decisions
- `AccessPolicy`: Configurable policies per entity (public, authenticated, owner, tenant, role)
- `AccessEnforcer`: Wraps repository to enforce policies
- Auto-detection of owner fields (`owner_id`, `user_id`, `created_by`)
- Auto-detection of tenant fields (`tenant_id`, `organization_id`)
- 42 access control tests

**Multi-tenant Architecture Design** (`dev_docs/Dazzle_Native_Runtime/multi_tenant_architecture.md`):
- Row-level security (SQLite) - implemented ✅
- PostgreSQL with native RLS - planned for Week 9-10
- Schema isolation - planned for enterprise tier

```dsl
entity Task:
  ...
  owner: ref User required

  access:
    read: owner = current_user or role = "admin"
    write: owner = current_user
    delete: owner = current_user
```

### Week 9-10: File Uploads & Rich Fields ✅ COMPLETE

Tasks:
- [x] File upload field type (FILE, IMAGE, RICHTEXT in ScalarType)
- [x] Image preview/thumbnail (ImageProcessor with Pillow)
- [x] S3-compatible storage (LocalStorageBackend + S3StorageBackend)
- [x] Rich text field (MarkdownProcessor with bleach sanitization)
- [ ] Date/time pickers (deferred)

**Implementation Summary (Nov 2025)**:
- File storage system (`src/dazzle_dnr_back/runtime/file_storage.py`):
  - StorageBackend protocol with local and S3 implementations
  - FileMetadataStore with SQLite persistence
  - FileValidator for size/type checking
  - FileService combining storage, metadata, and validation
  - Secure filename sanitization
- Image processing (`src/dazzle_dnr_back/runtime/image_processor.py`):
  - Thumbnail generation with aspect ratio preservation
  - Image optimization for web delivery
  - Format conversion (PNG, JPEG, WEBP)
  - Square cropping for avatars
- Rich text (`src/dazzle_dnr_back/runtime/richtext_processor.py`):
  - Markdown to HTML rendering
  - HTML sanitization (XSS prevention)
  - Inline base64 image processing
  - Text extraction for search indexing
- REST endpoints (`src/dazzle_dnr_back/runtime/file_routes.py`):
  - POST /api/files/upload
  - GET /api/files/{id}/download
  - GET /api/files/{id}/thumbnail
  - DELETE /api/files/{id}
  - GET /api/files/entity/{entity}/{id}
- 96 new tests (34 file storage + 26 image + 36 rich text)

### Week 11-12: Relationships & Queries ✅ COMPLETE

Tasks:
- [x] Foreign key relationships
- [x] Nested data fetching
- [x] List filtering from DSL
- [x] Sorting and pagination
- [x] Search (full-text)

**Implementation Summary (Nov 2025)**:
- **Query Builder** (`src/dazzle_dnr_back/runtime/query_builder.py`):
  - Advanced filter operators: eq, ne, gt, gte, lt, lte, contains, icontains, startswith, endswith, in, not_in, isnull, between
  - Relation path filters (e.g., `owner__name__contains`)
  - Multi-field sorting with ascending/descending support
  - SQL generation with parameter binding
  - 56 query builder tests

- **Relation Loader** (`src/dazzle_dnr_back/runtime/relation_loader.py`):
  - RelationRegistry for tracking entity relationships
  - Auto-detection of implicit relations from ref fields
  - To-one relation loading (many-to-one, one-to-one)
  - To-many relation loading (one-to-many, many-to-many)
  - Batch loading to avoid N+1 queries
  - Foreign key constraint generation
  - 24 relation tests

- **Full-Text Search** (`src/dazzle_dnr_back/runtime/fts_manager.py`):
  - SQLite FTS5 virtual table integration
  - Auto-detection of searchable text fields
  - Sync triggers for insert/update/delete
  - Search with snippets and highlighting
  - Query escaping for safety
  - Index rebuild functionality
  - 28 FTS tests

- **Repository Enhancements**:
  - Extended `list()` with sort, include, and search parameters
  - Extended `read()` with include parameter
  - Support for nested data in responses

```dsl
workspace task_board "Task Board":
  my_tasks:
    source: Task
    filter: owner = current_user and status != "done"
    sort: priority desc, due_date asc
    include: owner, project
    limit: 50
```

### Week 13-14: Real-time & Collaboration ✅ COMPLETE

Tasks:
- [x] WebSocket support
- [x] Live updates (other users' changes)
- [x] Optimistic UI updates
- [x] Presence indicators (who's viewing)

**Implementation Summary (Nov 2025)**:
- **WebSocket Manager** (`src/dazzle_dnr_back/runtime/websocket_manager.py`):
  - Connection lifecycle management (connect, disconnect, heartbeat)
  - Channel-based pub/sub subscriptions
  - Message routing to handlers
  - Broadcast to all or filtered connections
  - User tracking across connections
  - Stale connection cleanup
  - 26 WebSocket manager tests

- **Event Bus** (`src/dazzle_dnr_back/runtime/event_bus.py`):
  - Entity event types: CREATED, UPDATED, DELETED
  - Async and sync event handlers
  - WebSocket broadcast integration
  - Repository mixin for automatic event emission
  - 22 event bus tests

- **Presence Tracker** (`src/dazzle_dnr_back/runtime/presence_tracker.py`):
  - Join/leave tracking for resources
  - Heartbeat-based activity detection
  - Automatic cleanup of stale entries
  - Presence sync for new connections
  - Connection cleanup on disconnect
  - 28 presence tracker tests

- **Realtime Routes** (`src/dazzle_dnr_back/runtime/realtime_routes.py`):
  - WebSocket endpoint with auth support
  - Presence message handlers
  - Stats endpoint for monitoring
  - Integration with FastAPI

- **Frontend Client** (`src/dazzle_dnr_ui/runtime/realtime_client.py`):
  - RealtimeClient class with reconnection
  - Channel subscriptions
  - OptimisticManager for instant UI updates
  - PresenceManager for collaboration awareness
  - EntitySync for auto-updating signals

### Horizontal Phase Success Criteria

- [x] Multi-user app with authentication ✅
- [x] File uploads work ✅
- [x] Complex queries execute correctly ✅
- [x] Real-time updates in browser ✅

---

## Phase 3: Meta (Developer Experience)

**Goal**: Make development delightful

### Week 15-16: Hot Reload & Dev Tools ✅ COMPLETE

Tasks:
- [x] DSL file watching
- [x] Hot reload on changes (no restart)
- [x] Dev tools panel in browser
- [x] State inspector
- [x] Network request viewer

**Implementation Summary (Dec 2025)**:
- **Hot Reload** (`src/dazzle_dnr_ui/runtime/hot_reload.py`):
  - FileWatcher with polling-based change detection
  - HotReloadManager orchestrating file watching and SSE broadcast
  - Debounced reload (300ms) to batch rapid changes
  - DSL re-parsing and spec regeneration on change
  - SSE endpoint for browser notification
  - 313 lines of hot reload infrastructure

- **DevTools Panel** (`src/dazzle_dnr_ui/runtime/static/js/devtools.js`):
  - Draggable floating panel (Ctrl+Shift+D toggle)
  - State tab: hierarchical view of all registered state
  - Network tab: API request/response logging
  - Actions tab: action dispatch history with timestamps
  - Auto-initialization in development mode
  - 528 lines of devtools UI

### Week 17-18: Debugging & Visualization ✅ COMPLETE

Tasks:
- [x] `dazzle dnr inspect --live` - show running state from server
- [x] Action log (what happened) with expandable details
- [x] State diff viewer (integrated into action log)
- [ ] Layout plan visualizer (deferred)
- [ ] Component tree explorer (deferred)

**Implementation Summary (Dec 2025)**:
- **Debug Routes** (`src/dazzle_dnr_back/runtime/debug_routes.py`):
  - `/_dnr/health` - System health check with database status
  - `/_dnr/stats` - Runtime statistics (uptime, entity counts, total records)
  - `/_dnr/spec` - Loaded specification info
  - `/_dnr/entity/{name}` - Entity schema and sample data
  - `/_dnr/tables` - Database table listing
- **CLI Live Inspection** (`src/dazzle/cli/dnr.py`):
  - `dazzle dnr inspect --live` - Query running server
  - Tree view with status, uptime, entity record counts
  - JSON/summary output formats
  - Entity-specific inspection with sample data
- **Enhanced DevTools Actions Tab** (`src/dazzle_dnr_ui/runtime/static/js/devtools.js`):
  - Rich action entries with timestamp, name, payload preview
  - Click to expand/collapse with state diff details
  - Before→after visualization for each state change
  - Change count badges per action
  - Full payload inspection in expanded view

### Week 19-20: Testing & Validation ✅ COMPLETE

Tasks:
- [x] Spec-based testing (`test` blocks in DSL)
- [x] Automated UI tests (Playwright integration)
- [x] API contract testing
- [x] Performance benchmarks
- [x] Accessibility checks

**Implementation Summary (Dec 2025)**:
- **`dazzle dnr test` Command** (`src/dazzle/cli/dnr.py`):
  - Unified testing command for DNR applications
  - `--api-only` for API contract tests only
  - `--e2e` for Playwright-based UI tests
  - `--benchmark` for performance metrics
  - `--a11y` for WCAG accessibility checks
  - Auto-starts server in test mode
  - JSON output with `-o results.json`

- **API Contract Testing**:
  - Tests health, spec, and CRUD endpoints
  - Validates against BackendSpec definitions
  - Dynamic test data generation per field type
  - Checks available endpoints before testing

- **Performance Benchmarks**:
  - Cold start time measurement
  - Latency percentiles (p50, p95, p99)
  - Sequential throughput (100 requests)
  - Concurrent throughput (50 requests, 10 workers)

- **WCAG Accessibility Testing**:
  - Integrates axe-core via Playwright
  - Configurable level (A, AA, AAA)
  - Maps violations to Dazzle entities/views
  - Checks multiple pages from workspace routes

### Week 21-22: Deployment & Distribution ✅ COMPLETE

Tasks:
- [x] `dazzle dnr build` - production bundle
- [x] Docker image generation
- [x] Environment configuration
- [x] Database migrations for prod
- [x] Health monitoring

**Implementation Summary**:
- `dazzle dnr build` command creates complete production bundles:
  - Backend spec and static files
  - Optional Vite frontend project
  - Production `main.py` entry point with argparse, logging
  - `requirements.txt` for dependencies
  - Multi-stage `Dockerfile` with health checks
  - `docker-compose.yml` for local deployment
  - `.env.example` template for configuration
- `dazzle dnr migrate` command for explicit database migrations:
  - `--dry-run` to preview planned migrations
  - `--db` to specify production database path
  - Detection of safe vs destructive changes
  - Migration history recording
- Kubernetes-style health probes:
  - `/_dnr/live` - liveness probe (process alive)
  - `/_dnr/ready` - readiness probe (database connected)
  - `/_dnr/health` - comprehensive health status
  - `/_dnr/stats` - runtime statistics (uptime, entity counts)

### Meta Phase Success Criteria

- [ ] Edit DSL, see changes instantly
- [ ] Debug running app visually
- [ ] Tests run from DSL definitions
- [ ] One-command deployment

---

## DSL Enhancements (Opinionated)

With DNR as the target, we can make the DSL more opinionated:

### Component Roles (New)

```dsl
component TaskCard:
  role: presentational  # view-only, props in/events out
  props:
    task: Task
    onEdit: action

  view:
    Card:
      Text: task.title
      Badge: task.status
      Button "Edit" -> onEdit

component TaskList:
  role: controller  # owns state, composes presentational
  state:
    filter: enum[all,active,done] = all
    selected: Task?

  actions:
    setFilter(f): filter = f  # pure
    selectTask(t): selected = t  # pure
    loadTasks: fetch tasks -> setTasks  # impure

  view:
    Column:
      FilterBar filter=filter onFilter=setFilter
      for task in tasks:
        TaskCard task=task onEdit=selectTask
```

### Action Purity (Explicit)

```dsl
workspace dashboard:
  actions:
    # Pure - state only, no side effects
    toggleFilter: pure
      filter = not filter

    # Impure - has effects (API, navigation)
    saveTask: impure
      effect: fetch POST /tasks body=currentTask
      onSuccess: showToast "Saved!"
      onError: showToast "Failed"

    # Impure - navigation
    goToDetail: impure
      effect: navigate /tasks/{id}
```

### Access Rules (Inline)

```dsl
entity Task:
  id: uuid pk
  title: str(200) required
  owner: ref User required

  access:
    create: authenticated
    read: owner = current_user or shared = true
    update: owner = current_user
    delete: owner = current_user and status = "draft"
```

### Effect Boundaries (Enforced)

```dsl
# Views cannot call backend directly
surface task_list:
  # ❌ Invalid - view calling backend
  # on_load: fetch /tasks

  # ✅ Valid - dispatch action that has effect
  on_load: dispatch loadTasks
```

---

## Migration from v0.3

### Deprecated
- All legacy stacks (already removed)
- `dazzle build` with framework stacks
- Direct code generation model

### New Commands
- `dazzle dnr serve` - Run app locally
- `dazzle dnr build` - Production bundle
- `dazzle dnr inspect` - Debug running app
- `dazzle dnr test` - Run spec tests

### Breaking Changes
- Examples default to DNR stack
- `[stack] name = "dnr"` is now default
- Framework-specific stacks removed

---

## Success Metrics

### Phase 1 (Vertical)
- Time from `dazzle init` to running app: < 30 seconds
- Cold start time: < 3 seconds
- Zero configuration required

### Phase 2 (Horizontal)
- Support 80% of typical CRUD app needs
- Auth flow working in < 5 minutes
- File uploads "just work"

### Phase 3 (Meta)
- Hot reload latency: < 500ms
- Dev tools useful for debugging
- Test coverage from DSL specs

---

## Open Questions

1. **State Persistence**: Local-first (SQLite) vs cloud-first (Postgres)?
2. **Deployment Target**: Docker-only or also serverless?
3. **Mobile**: React Native runtime or PWA-first?
4. **Offline**: Support offline-first patterns?
5. **Extensibility**: How do users add custom components?

---

## Timeline Summary

| Phase | Focus | Duration | Target |
|-------|-------|----------|--------|
| 1 | Vertical (end-to-end) | 6 weeks | Make it work |
| 2 | Horizontal (features) | 8 weeks | Make it useful |
| 3 | Meta (DX) | 8 weeks | Make it delightful |

**Total**: ~22 weeks (~5-6 months)

---

**Next Action**: Start Phase 1, Week 1 - Backend Runtime
