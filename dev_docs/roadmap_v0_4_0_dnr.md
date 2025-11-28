# DAZZLE v0.4.0 Roadmap - DNR: From Spec to Running App

**Status**: Planning
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

### Week 1-2: Backend Runtime

**Make `dazzle dnr serve` start a real FastAPI server**

Tasks:
- [ ] SQLite database auto-creation from entities
- [ ] Auto-migration on entity changes
- [ ] CRUD endpoints generated from BackendSpec
- [ ] JSON REST API (no auth yet)
- [ ] Health check endpoint

```bash
$ dazzle dnr serve
Starting DNR...
  Backend: http://localhost:8000
  API Docs: http://localhost:8000/docs
  Database: .dazzle/data.db
```

**Deliverables**:
- Working FastAPI server from `simple_task` example
- Create, read, update, delete tasks via API
- Data persists in SQLite

### Week 3-4: Frontend Runtime

**Make UISpec render in browser**

Tasks:
- [ ] Vite dev server integration
- [ ] UISpec → Preact components (signals-based)
- [ ] Archetype layouts render correctly
- [ ] Connect to backend API (fetch data)
- [ ] Basic forms for create/edit

```bash
$ dazzle dnr serve
Starting DNR...
  Backend: http://localhost:8000
  Frontend: http://localhost:5173
  Opening browser...
```

**Deliverables**:
- Browser opens with working UI
- Task list displays real data
- Create new task via form
- Changes persist to database

### Week 5-6: Behaviour Layer

**Wire up state management and actions**

Tasks:
- [ ] Signals-based state (Preact signals)
- [ ] Pure actions (filter, select, sort)
- [ ] Impure actions (fetch, save, delete)
- [ ] Effects system (API calls, navigation, toasts)
- [ ] Loading/error states

**Deliverables**:
- Full CRUD workflow in browser
- State updates reactively
- Error handling with toasts
- Navigation between workspaces

### Vertical Phase Success Criteria

- [ ] `simple_task` example runs end-to-end
- [ ] Create, read, update, delete tasks
- [ ] Data persists across restarts
- [ ] Multiple workspaces navigate correctly
- [ ] < 3 second cold start

---

## Phase 2: Horizontal (Add Capabilities)

**Goal**: Production-ready features

### Week 7-8: Authentication & Authorization

Tasks:
- [ ] User entity auto-detection
- [ ] Session-based auth (cookies)
- [ ] Login/logout flows
- [ ] Row-level security (owner-based)
- [ ] DSL syntax for auth rules

```dsl
entity Task:
  ...
  owner: ref User required

  access:
    read: owner = current_user or role = "admin"
    write: owner = current_user
    delete: owner = current_user
```

### Week 9-10: File Uploads & Rich Fields

Tasks:
- [ ] File upload field type
- [ ] Image preview/thumbnail
- [ ] S3-compatible storage (local or cloud)
- [ ] Rich text field (markdown)
- [ ] Date/time pickers

### Week 11-12: Relationships & Queries

Tasks:
- [ ] Foreign key relationships
- [ ] Nested data fetching
- [ ] List filtering from DSL
- [ ] Sorting and pagination
- [ ] Search (full-text)

```dsl
workspace task_board "Task Board":
  my_tasks:
    source: Task
    filter: owner = current_user and status != "done"
    sort: priority desc, due_date asc
    limit: 50
```

### Week 13-14: Real-time & Collaboration

Tasks:
- [ ] WebSocket support
- [ ] Live updates (other users' changes)
- [ ] Optimistic UI updates
- [ ] Presence indicators (who's viewing)

### Horizontal Phase Success Criteria

- [ ] Multi-user app with authentication
- [ ] File uploads work
- [ ] Complex queries execute correctly
- [ ] Real-time updates in browser

---

## Phase 3: Meta (Developer Experience)

**Goal**: Make development delightful

### Week 15-16: Hot Reload & Dev Tools

Tasks:
- [ ] DSL file watching
- [ ] Hot reload on changes (no restart)
- [ ] Dev tools panel in browser
- [ ] State inspector
- [ ] Network request viewer

### Week 17-18: Debugging & Visualization

Tasks:
- [ ] `dazzle dnr inspect` - show running state
- [ ] Action log (what happened)
- [ ] State diff viewer
- [ ] Layout plan visualizer
- [ ] Component tree explorer

### Week 19-20: Testing & Validation

Tasks:
- [ ] Spec-based testing (`test` blocks in DSL)
- [ ] Automated UI tests (Playwright integration)
- [ ] API contract testing
- [ ] Performance benchmarks
- [ ] Accessibility checks

### Week 21-22: Deployment & Distribution

Tasks:
- [ ] `dazzle dnr build` - production bundle
- [ ] Docker image generation
- [ ] Environment configuration
- [ ] Database migrations for prod
- [ ] Health monitoring

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
