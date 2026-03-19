# server.py Subsystem Migration Design

> **For agentic workers:** Use superpowers:writing-plans to create an implementation plan from this spec.

**Goal:** Reduce `server.py` from 2,214 lines / 42 methods to ~600 lines / ~12 methods by extracting 6 new subsystems using the existing `SubsystemPlugin` protocol. Fix the `server.py` ↔ `app_factory.py` circular import.

**Motivation:** `DazzleBackendApp` is a god class with fan-in of 54 internal imports. Every new feature adds more code to it. 9 subsystems were already successfully extracted — this completes the migration.

---

## What stays on `DazzleBackendApp`

Core lifecycle orchestration only — methods that set up the app skeleton and delegate to subsystems:

| Method | Purpose | Stays because |
|--------|---------|---------------|
| `__init__` | Accept config, convert specs | Entry point |
| `_create_app` | Create FastAPI, apply middleware (security, CSRF, rate limit, gzip, metrics, tenant) | Must run before anything else |
| `_setup_models` | Generate Pydantic models from entity specs | Needed by all downstream steps |
| `_setup_database` | Init PostgresBackend, run migrations, open pool | Needed by services + subsystems |
| `_setup_services` | Create repositories and CRUD services (including `_wire_service_hooks`) | Needed by route generation + subsystems |
| `_setup_auth_deps` | Create AuthStore + AuthMiddleware, produce `auth_dep`/`optional_auth_dep` | Must run before `_setup_routes`; too early for subsystem loop |
| `_setup_routes` | Generate entity CRUD routes using auth deps | Core routing; depends on models + services + auth deps |
| `_build_default_subsystems` | Register subsystem instances in order | Orchestration |
| `_build_subsystem_context` | Build `SubsystemContext` from instance state | Orchestration |
| `_run_subsystems` | Call `startup()` on each subsystem | Orchestration |
| `build` | Call the above in order, return FastAPI app | Public API |

**Target:** ~600 lines, ~12 methods.

### `build()` call sequence

```
_create_app()
_setup_models()
_setup_database()
_setup_services()          # includes _wire_service_hooks
_setup_auth_deps()         # creates AuthStore, produces auth deps — NOT a subsystem
_setup_routes(auth_dep, optional_auth_dep)   # entity CRUD only
_run_subsystems()          # auth routes + all other subsystems run here
```

**Key design decision:** Auth is split into two phases:
1. `_setup_auth_deps()` stays on `DazzleBackendApp` — creates `AuthStore`, `AuthMiddleware`, and produces `auth_dep`/`optional_auth_dep`. Called before `_setup_routes` because entity CRUD routes need auth deps.
2. `AuthSubsystem.startup()` — registers auth routes, social auth, 2FA routes. Runs in the subsystem loop after `_setup_routes`.

This avoids restructuring the `build()` call sequence while still extracting 250+ lines of auth route code into a subsystem.

---

## New subsystems to extract

### 1. `auth.py` — Authentication Routes Subsystem

**Absorbs from `server.py`:**
- `_init_social_auth()` — OAuth2 social login setup
- `_build_social_auth_config()` — OAuth provider config builder
- Auth route creation (currently inside `_setup_routes`: `create_auth_routes`, `create_2fa_routes`, `create_jwt_auth_routes`)

**Does NOT absorb:** `AuthStore` creation and `auth_dep` production — those stay in `_setup_auth_deps()` on `DazzleBackendApp`.

**Writes to `SubsystemContext`:**
- `ctx.auth_middleware` (already exists on context) — set by `_setup_auth_deps`, but auth subsystem may update it for social auth

**Reads from `SubsystemContext`:** `ctx.app`, `ctx.config`, `ctx.auth_store`, `ctx.auth_dep`, `ctx.optional_auth_dep`, `ctx.database_url`

### 2. `integrations.py` — Integration Subsystem

**Absorbs from `server.py`:**
- `_init_integration_executor()` — creates IntegrationExecutor
- `_init_mapping_executor()` — creates MappingExecutor, registers trigger routes
- `_register_manual_trigger_routes()` — adds per-entity manual trigger endpoints
- `_wire_entity_events_to_bus()` — connects entity CRUD events to the event bus for integration dispatch

**Reads from `SubsystemContext`:** `ctx.app`, `ctx.appspec`, `ctx.services`, `ctx.db_manager`, `ctx.event_framework`

### 3. `workspaces.py` — Workspace Subsystem

**Absorbs from `server.py`:**
- `_init_workspace_routes()` — top-level workspace routing
- `_init_workspace_entity_routes()` — per-workspace entity routing
- The `WorkspaceRouteBuilder` class (currently inlined in `server.py` ~lines 312-660)

**Reads from `SubsystemContext`:** `ctx.app`, `ctx.appspec`, `ctx.services`, `ctx.repositories`, `ctx.auth_dep`, `ctx.optional_auth_dep`, `ctx.auth_middleware`, `ctx.db_manager`

**Note:** `WorkspaceRouteBuilder` is itself ~350 lines. It moves to `subsystems/workspaces.py` intact. Its constructor currently takes `auth_middleware` — this reads from `ctx.auth_middleware` (already on context).

### 4. `fragments.py` — Fragment Routes Subsystem

**Absorbs from `server.py`:**
- `_init_fragment_routes()` — registers fragment source routes for DSL `source=` annotations

**Reads from `SubsystemContext`:** `ctx.app`, `ctx.appspec`, `ctx.config.fragment_sources`, `ctx.optional_auth_dep`

**Note:** The method also reads `ctx.appspec.integrations` to merge integration base URLs into fragment sources — not just `ctx.config.fragment_sources`.

### 5. `transitions.py` — Transition Effects Subsystem

**Absorbs from `server.py`:**
- `_init_transition_effects()` — wires state machine transition side effects (notifications, field assignments, process triggers)

**Reads from `SubsystemContext`:** `ctx.app`, `ctx.appspec`, `ctx.services`, `ctx.repositories`, `ctx.db_manager`

### 6. `system_routes.py` — System Routes Subsystem

**Absorbs from `server.py`:**
- `_setup_system_routes()` — health endpoint, debug info, startup time, migration status
- Audit logger creation (currently at top of `_setup_routes`) and audit query routes
- Metadata store creation and file service wiring

**Reads from `SubsystemContext`:** `ctx.app`, `ctx.appspec`, `ctx.config`, `ctx.db_manager`, `ctx.services`, `ctx.audit_logger`

**Note:** The `AuditLogger` is created in `_setup_routes` and passed to entity CRUD route generation. After migration, `_setup_routes` creates it, stores it on `self._audit_logger`, and `SubsystemContext` exposes it as `ctx.audit_logger` for `system_routes.py` to use for audit query routes. The CRUD routes still receive it directly from `_setup_routes`.

**Must run last:** provides health/debug routes that report on other subsystems' state.

---

## `SubsystemContext` additions

Add these fields to `SubsystemContext` in `subsystems/__init__.py`:

```python
# Auth — set by _setup_auth_deps on DazzleBackendApp, read by auth subsystem + others
auth_store: Any | None = None
auth_dep: Any | None = None          # FastAPI Depends for required auth
optional_auth_dep: Any | None = None  # FastAPI Depends for optional auth
database_url: str = ""                # for subsystems that need DB access

# Integration — set by integrations subsystem
integration_mgr: Any | None = None

# Workspace — set by workspace subsystem
workspace_builder: Any | None = None

# Audit — set by _setup_routes on DazzleBackendApp, read by system_routes
audit_logger: Any | None = None

# Misc config forwarded from ServerConfig
security_profile: str = "basic"
cors_origins: list[str] | None = None
```

**Note:** `auth_middleware` is already on `SubsystemContext` (line 51). It will be written by `_setup_auth_deps` and read by the workspaces subsystem.

---

## Subsystem ordering

`_build_default_subsystems()` returns subsystems in dependency order:

```python
def _build_default_subsystems(self) -> list[Any]:
    return [
        # Phase 1: Auth routes (deps already set by _setup_auth_deps)
        AuthSubsystem(),
        # Phase 2: Infrastructure (existing — unchanged)
        ConsoleSubsystem(),
        ChannelsSubsystem(),
        EventsSubsystem(),
        ProcessSubsystem(),
        SeedSubsystem(),
        SLASubsystem(),
        LLMQueueSubsystem(),
        GraphQLSubsystem(),
        WebSocketSubsystem(),
        # Phase 3: Feature subsystems (use auth deps + services)
        IntegrationsSubsystem(),
        TransitionsSubsystem(),
        FragmentsSubsystem(),
        WorkspacesSubsystem(),
        # Phase 4: System routes (last — reports on everything)
        SystemRoutesSubsystem(),
    ]
```

**Note:** `ConsoleSubsystem` is an existing subsystem included here for completeness. `GraphQLSubsystem` and `WebSocketSubsystem` are existing files in `subsystems/` that are already registered.

---

## Circular import fix

**Remove** lines ~2190-2213 at the bottom of `server.py` that re-export from `app_factory`:

```python
# DELETE these:
from dazzle_back.runtime.app_factory import create_app, run_app, ...
```

**Update callers:** `grep -rn "from dazzle_back.runtime.server import create_app\|run_app"` and change imports to `from dazzle_back.runtime.app_factory import ...`.

---

## `_setup_routes` simplification

After extracting auth routes, workspace routes, system routes, and fragment routes into subsystems, `_setup_routes` shrinks to:

1. Create `AuditLogger` (store on `self._audit_logger` for subsystem context)
2. Generate entity CRUD routes with auth deps and audit logger
3. Register them on the app

No more auth route creation, no more workspace route creation, no more system route creation. Those are all subsystem responsibilities now.

The auth deps (`auth_dep`, `optional_auth_dep`) are passed as parameters from `build()`, which gets them from `_setup_auth_deps()`.

---

## `_wire_service_hooks` stays on `DazzleBackendApp`

`_wire_service_hooks()` runs at the end of `_setup_services()`, before subsystems. It wires project-level hook files to CRUD service callbacks. This stays on `DazzleBackendApp` because:

1. It runs during `_setup_services()`, before subsystem context exists
2. The file upload callbacks it sets up (`_upload_callbacks`) are consumed later by `_setup_routes` when creating file routes
3. Moving it to a subsystem would require splitting `_setup_services` and adding complex ordering

The `_upload_callbacks` plumbing stays on `DazzleBackendApp` — file route creation in `_setup_routes` reads it directly.

---

## Files to modify

| File | Change |
|------|--------|
| `src/dazzle_back/runtime/subsystems/__init__.py` | Add new `SubsystemContext` fields |
| `src/dazzle_back/runtime/subsystems/auth.py` | **Create** — auth routes subsystem |
| `src/dazzle_back/runtime/subsystems/integrations.py` | **Create** — integration subsystem |
| `src/dazzle_back/runtime/subsystems/workspaces.py` | **Create** — workspace subsystem |
| `src/dazzle_back/runtime/subsystems/fragments.py` | **Create** — fragment routes subsystem |
| `src/dazzle_back/runtime/subsystems/transitions.py` | **Create** — transition effects subsystem |
| `src/dazzle_back/runtime/subsystems/system_routes.py` | **Create** — system routes subsystem |
| `src/dazzle_back/runtime/server.py` | **Reduce** — extract methods, rename `_setup_auth` → `_setup_auth_deps`, simplify `_setup_routes`, remove re-exports |
| Callers of `server.py` re-exports | **Update** — import from `app_factory` instead |

## Implementation approach

Extract one subsystem at a time in this order (each is a commit):

1. **SubsystemContext additions** — add new fields
2. **Auth split** — rename `_setup_auth` → `_setup_auth_deps`, extract auth route code to `AuthSubsystem`
3. **System routes** — extract `_setup_system_routes` + audit routes
4. **Workspaces** — extract `WorkspaceRouteBuilder` + workspace route methods
5. **Integrations** — extract integration/mapping executor + event bus wiring
6. **Transitions** — extract transition effects
7. **Fragments** — extract fragment routes
8. **Circular import fix** — remove re-exports, update callers
9. **Final cleanup** — remove dead code from `_setup_routes`

After each extraction, run full test suite to verify no breakage.

## What this does NOT change

- No changes to the `SubsystemPlugin` protocol
- No changes to existing 9 subsystems
- No changes to entity CRUD route generation logic
- No changes to middleware application order
- No changes to the subsystem startup/shutdown lifecycle
- `_wire_service_hooks` stays on `DazzleBackendApp` (called in `_setup_services`)
