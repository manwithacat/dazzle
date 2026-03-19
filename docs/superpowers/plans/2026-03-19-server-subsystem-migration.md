# server.py Subsystem Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `server.py` from 2,214 lines / 42 methods to ~600 lines / ~12 methods by extracting 6 new subsystems.

**Architecture:** Move feature-specific methods from `DazzleBackendApp` into subsystem classes following the existing `SubsystemPlugin` protocol. Each extraction is one commit. Auth is split: deps stay on `DazzleBackendApp` (needed before routes), routes move to subsystem (runs after routes). Fix circular import with `app_factory.py`.

**Tech Stack:** Python 3.12, FastAPI, existing `SubsystemPlugin` protocol

**Spec:** `docs/superpowers/specs/2026-03-19-server-subsystem-migration-design.md`

**Approach note:** Each task says "read lines X-Y of server.py" because the source code is the truth — the methods are moved verbatim with only `self._foo` → `ctx.foo` adjustments.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/dazzle_back/runtime/subsystems/__init__.py` | **Modify** — add new `SubsystemContext` fields |
| `src/dazzle_back/runtime/subsystems/auth.py` | **Create** — auth routes (social, 2FA, JWT) |
| `src/dazzle_back/runtime/subsystems/integrations.py` | **Create** — integration + mapping executors |
| `src/dazzle_back/runtime/subsystems/workspaces.py` | **Create** — workspace route builder + routes |
| `src/dazzle_back/runtime/subsystems/fragments.py` | **Create** — fragment source routes |
| `src/dazzle_back/runtime/subsystems/transitions.py` | **Create** — state machine transition effects |
| `src/dazzle_back/runtime/subsystems/system_routes.py` | **Create** — health, debug, audit, file, system routes |
| `src/dazzle_back/runtime/server.py` | **Reduce** — delete extracted methods, update `build()` |

---

## Task 1: SubsystemContext Additions

**Files:**
- Modify: `src/dazzle_back/runtime/subsystems/__init__.py`

- [ ] **Step 1: Add new fields to SubsystemContext**

Read the existing `SubsystemContext` dataclass. Add these fields after the existing ones:

```python
    # Auth — set by _setup_auth_deps before subsystems run
    auth_store: Any | None = None
    auth_dep: Any | None = None          # FastAPI Depends for required auth
    optional_auth_dep: Any | None = None  # FastAPI Depends for optional auth
    auth_config: Any | None = None       # AuthConfig from manifest
    database_url: str = ""               # for subsystems needing DB access

    # Integration — set by integrations subsystem
    integration_mgr: Any | None = None

    # Workspace — set by workspace subsystem
    workspace_builder: Any | None = None

    # Audit — set by _setup_routes, read by system_routes
    audit_logger: Any | None = None

    # Config forwarded from ServerConfig
    security_profile: str = "basic"
    project_root: Any | None = None
```

- [ ] **Step 2: Update `_build_subsystem_context` in server.py**

Read `_build_subsystem_context` (lines ~894-911). Add the new fields:

```python
        auth_store=self._auth_store,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        auth_config=self._auth_config,
        database_url=self._database_url or "",
        audit_logger=self._audit_logger,
        security_profile=self._security_profile,
        project_root=self._project_root,
```

This requires `_build_subsystem_context` to accept `auth_dep` and `optional_auth_dep` as parameters (since they're produced by `_setup_auth`).

- [ ] **Step 3: Update `build()` to pass auth deps through**

In `build()` (line ~2076), change the sequence so `_build_subsystem_context` receives auth deps:

```python
    def build(self) -> FastAPI:
        self._create_app()
        self._setup_models()
        self._setup_database()
        self._setup_services()
        auth_dep, optional_auth_dep = self._setup_auth()
        self._setup_routes(auth_dep, optional_auth_dep)
        # Build subsystem context with auth deps
        self._subsystem_ctx = self._build_subsystem_context(auth_dep, optional_auth_dep)
        self._run_subsystems()
        self._setup_system_routes()  # stays for now, extracted in Task 6
        # Validate routes
        from dazzle_back.runtime.route_validator import validate_routes
        assert self._app is not None
        validate_routes(self._app)
        return self._app
```

Note: `_setup_optional_features` is replaced by `_run_subsystems` — the subsystem loop replaces the old optional features method.

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -m "not e2e" -x --timeout=120 -q`
Expected: All pass (no behavior change yet)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/subsystems/__init__.py src/dazzle_back/runtime/server.py
git commit -m "refactor(server): add SubsystemContext fields for migration (#535)"
```

---

## Task 2: Extract Auth Routes Subsystem

**Files:**
- Create: `src/dazzle_back/runtime/subsystems/auth.py`
- Modify: `src/dazzle_back/runtime/server.py`

- [ ] **Step 1: Read auth methods in server.py**

Read these methods:
- `_init_social_auth()` (lines ~935-1019)
- `_build_social_auth_config()` (lines ~1021-1078)
- Auth route creation in `_setup_routes` — find `create_auth_routes`, `create_2fa_routes`, `create_jwt_auth_routes` calls

- [ ] **Step 2: Create `subsystems/auth.py`**

Create `src/dazzle_back/runtime/subsystems/auth.py` following the pattern in `channels.py`:

```python
"""Auth routes subsystem.

Registers authentication routes (login/register/logout), social auth (OAuth2),
2FA routes, and JWT routes. Auth deps (AuthStore, AuthMiddleware, auth_dep,
optional_auth_dep) are already set on SubsystemContext by DazzleBackendApp._setup_auth().
"""

from __future__ import annotations

import logging
from typing import Any

from dazzle_back.runtime.subsystems import SubsystemContext

logger = logging.getLogger("dazzle.server")


class AuthSubsystem:
    name = "auth_routes"

    def startup(self, ctx: SubsystemContext) -> None:
        if not ctx.enable_auth or not ctx.auth_store:
            return

        self._register_auth_routes(ctx)
        self._init_social_auth(ctx)

    def _register_auth_routes(self, ctx: SubsystemContext) -> None:
        # Move create_auth_routes, create_2fa_routes, create_jwt_auth_routes
        # calls from _setup_routes in server.py
        ...

    def _init_social_auth(self, ctx: SubsystemContext) -> None:
        # Move _init_social_auth from server.py verbatim
        # Replace self._auth_config → ctx.auth_config
        # Replace self._app → ctx.app
        # Replace self._auth_store → ctx.auth_store
        # Replace self._database_url → ctx.database_url
        ...

    def _build_social_auth_config(self, oauth_providers: list[Any]) -> Any | None:
        # Move _build_social_auth_config from server.py verbatim
        ...

    def shutdown(self) -> None:
        pass
```

Fill in each method by copying the code from `server.py` and replacing `self._` references with `ctx.` references.

- [ ] **Step 3: Remove extracted methods from server.py**

Delete `_init_social_auth` and `_build_social_auth_config` from `DazzleBackendApp`.

- [ ] **Step 4: Extract auth route creation from `_setup_routes`**

In `_setup_routes`, find the section that calls `create_auth_routes`, `create_2fa_routes`, `create_jwt_auth_routes` and move those to `AuthSubsystem._register_auth_routes`. Keep `_setup_routes` focused on entity CRUD routes only.

- [ ] **Step 5: Register AuthSubsystem in `_build_default_subsystems`**

Add `AuthSubsystem()` as the first entry (before existing subsystems).

- [ ] **Step 6: Run tests**

Run: `pytest tests/ -m "not e2e" -x --timeout=120 -q`
Expected: All pass

- [ ] **Step 7: Lint and commit**

```bash
ruff check src/dazzle_back/runtime/subsystems/auth.py src/dazzle_back/runtime/server.py --fix
ruff format src/dazzle_back/runtime/subsystems/auth.py src/dazzle_back/runtime/server.py
git add src/dazzle_back/runtime/subsystems/auth.py src/dazzle_back/runtime/server.py
git commit -m "refactor(server): extract auth routes to AuthSubsystem (#535)"
```

---

## Task 3: Extract System Routes Subsystem

**Files:**
- Create: `src/dazzle_back/runtime/subsystems/system_routes.py`
- Modify: `src/dazzle_back/runtime/server.py`

- [ ] **Step 1: Read system route methods in server.py**

Read:
- `_setup_system_routes()` (line ~1929 to ~2070)
- `_setup_optional_features()` (line ~1844 to ~1928) — audit logger, metadata store, file service

- [ ] **Step 2: Create `subsystems/system_routes.py`**

```python
"""System routes subsystem.

Registers health, debug, system info, audit query, and static file routes.
Also initializes optional features: audit logger, metadata store, file service.
"""

from __future__ import annotations

import logging
from typing import Any

from dazzle_back.runtime.subsystems import SubsystemContext

logger = logging.getLogger("dazzle.server")


class SystemRoutesSubsystem:
    name = "system_routes"

    def startup(self, ctx: SubsystemContext) -> None:
        self._setup_optional_features(ctx)
        self._setup_system_routes(ctx)

    def _setup_optional_features(self, ctx: SubsystemContext) -> None:
        # Move _setup_optional_features from server.py
        # Replace self._ → ctx. references
        ...

    def _setup_system_routes(self, ctx: SubsystemContext) -> None:
        # Move _setup_system_routes from server.py
        # Replace self._ → ctx. references
        ...

    def shutdown(self) -> None:
        pass
```

- [ ] **Step 3: Remove extracted methods from server.py, update build()**

Delete `_setup_system_routes` and `_setup_optional_features` from `DazzleBackendApp`. Remove the `self._setup_system_routes()` call from `build()` — the subsystem handles it now.

- [ ] **Step 4: Register SystemRoutesSubsystem as the last subsystem**

Add `SystemRoutesSubsystem()` at the end of `_build_default_subsystems`.

- [ ] **Step 5: Run tests, lint, commit**

```bash
pytest tests/ -m "not e2e" -x --timeout=120 -q
ruff check src/dazzle_back/runtime/subsystems/system_routes.py src/dazzle_back/runtime/server.py --fix
ruff format src/dazzle_back/runtime/subsystems/system_routes.py src/dazzle_back/runtime/server.py
git add src/dazzle_back/runtime/subsystems/system_routes.py src/dazzle_back/runtime/server.py
git commit -m "refactor(server): extract system routes to SystemRoutesSubsystem (#535)"
```

---

## Task 4: Extract Workspace Subsystem

**Files:**
- Create: `src/dazzle_back/runtime/subsystems/workspaces.py`
- Modify: `src/dazzle_back/runtime/server.py`

- [ ] **Step 1: Read workspace code in server.py**

Read:
- The `WorkspaceRouteBuilder` class (lines ~137-660)
- `_init_workspace_routes()` (line ~1313)
- `_init_workspace_entity_routes()` (line ~1318)

- [ ] **Step 2: Create `subsystems/workspaces.py`**

Move the entire `WorkspaceRouteBuilder` class and the two init methods. The subsystem `startup()` calls them using `ctx` references.

- [ ] **Step 3: Remove from server.py**

Delete `WorkspaceRouteBuilder`, `_init_workspace_routes`, `_init_workspace_entity_routes`. Remove calls to these from `_setup_optional_features` (already moved to system_routes in Task 3) or wherever they're called.

- [ ] **Step 4: Register, test, lint, commit**

```bash
pytest tests/ -m "not e2e" -x --timeout=120 -q
git add src/dazzle_back/runtime/subsystems/workspaces.py src/dazzle_back/runtime/server.py
git commit -m "refactor(server): extract WorkspaceRouteBuilder to WorkspacesSubsystem (#535)"
```

---

## Task 5: Extract Integrations Subsystem

**Files:**
- Create: `src/dazzle_back/runtime/subsystems/integrations.py`
- Modify: `src/dazzle_back/runtime/server.py`

- [ ] **Step 1: Read integration methods in server.py**

Read:
- `_init_integration_executor()` (line ~1110)
- `_init_mapping_executor()` (line ~1115)
- `_register_manual_trigger_routes()` (line ~1173)
- `_wire_entity_events_to_bus()` (line ~1257)

- [ ] **Step 2: Create `subsystems/integrations.py`**

Move all four methods. The subsystem `startup()` calls them in order.

- [ ] **Step 3: Remove from server.py, register, test, lint, commit**

```bash
pytest tests/ -m "not e2e" -x --timeout=120 -q
git add src/dazzle_back/runtime/subsystems/integrations.py src/dazzle_back/runtime/server.py
git commit -m "refactor(server): extract integration executor to IntegrationsSubsystem (#535)"
```

---

## Task 6: Extract Transitions Subsystem

**Files:**
- Create: `src/dazzle_back/runtime/subsystems/transitions.py`
- Modify: `src/dazzle_back/runtime/server.py`

- [ ] **Step 1: Read `_init_transition_effects()` in server.py** (line ~1323)

- [ ] **Step 2: Create `subsystems/transitions.py`**

Move `_init_transition_effects` verbatim.

- [ ] **Step 3: Remove from server.py, register, test, lint, commit**

```bash
pytest tests/ -m "not e2e" -x --timeout=120 -q
git add src/dazzle_back/runtime/subsystems/transitions.py src/dazzle_back/runtime/server.py
git commit -m "refactor(server): extract transition effects to TransitionsSubsystem (#535)"
```

---

## Task 7: Extract Fragments Subsystem

**Files:**
- Create: `src/dazzle_back/runtime/subsystems/fragments.py`
- Modify: `src/dazzle_back/runtime/server.py`

- [ ] **Step 1: Read `_init_fragment_routes()` in server.py** (line ~1079)

Note: this method reads from `self._appspec.integrations` for base URLs as well as `self._config.fragment_sources`.

- [ ] **Step 2: Create `subsystems/fragments.py`**

Move `_init_fragment_routes` verbatim. Use `ctx.appspec.integrations` and `ctx.config.fragment_sources`.

- [ ] **Step 3: Remove from server.py, register, test, lint, commit**

```bash
pytest tests/ -m "not e2e" -x --timeout=120 -q
git add src/dazzle_back/runtime/subsystems/fragments.py src/dazzle_back/runtime/server.py
git commit -m "refactor(server): extract fragment routes to FragmentsSubsystem (#535)"
```

---

## Task 8: Fix Circular Import

**Files:**
- Modify: `src/dazzle_back/runtime/server.py`
- Modify: callers that import re-exports from server.py

- [ ] **Step 1: Find all callers of re-exported symbols**

```bash
grep -rn "from dazzle_back.runtime.server import create_app\|from dazzle_back.runtime.server import run_app\|from dazzle_back.runtime.server import build_server_config\|from dazzle_back.runtime.server import create_app_factory\|from dazzle_back.runtime.server import assemble_post_build_routes\|from dazzle_back.runtime.server import build_entity" src/ tests/ --include="*.py"
```

- [ ] **Step 2: Update each caller**

Change imports from `dazzle_back.runtime.server` to `dazzle_back.runtime.app_factory` for: `create_app`, `run_app`, `build_server_config`, `create_app_factory`, `assemble_post_build_routes`, `build_entity_list_projections`, `build_entity_search_fields`.

- [ ] **Step 3: Remove re-exports from server.py**

Delete lines ~2190-2214 (the `from dazzle_back.runtime.app_factory import ...` block and the `__all__` list that includes those names).

Update `__all__` to only export `DazzleBackendApp` and `ServerConfig`.

- [ ] **Step 4: Run tests, lint, commit**

```bash
pytest tests/ -m "not e2e" -x --timeout=120 -q
git add -A
git commit -m "refactor(server): remove re-exports, fix circular import with app_factory (#535)"
```

---

## Task 9: Final Cleanup + Verification

**Files:**
- Modify: `src/dazzle_back/runtime/server.py` (final cleanup)

- [ ] **Step 1: Count lines and methods**

```bash
wc -l src/dazzle_back/runtime/server.py
grep -c "def " src/dazzle_back/runtime/server.py
```

Target: ~600 lines, ~12 methods.

- [ ] **Step 2: Verify no remaining `_init_` methods that should be subsystems**

```bash
grep "def _init_" src/dazzle_back/runtime/server.py
```

Should return empty (all `_init_*` methods moved to subsystems).

- [ ] **Step 3: Full test suite**

```bash
pytest tests/ -m "not e2e" -x --timeout=120 -q
```

- [ ] **Step 4: Type check**

```bash
mypy src/dazzle_back/runtime/server.py src/dazzle_back/runtime/subsystems/ --ignore-missing-imports
```

- [ ] **Step 5: Push**

```bash
git push
```

- [ ] **Step 6: Close issue**

```bash
gh issue comment 535 --body "Completed. server.py reduced from 2,214 to ~600 lines. 6 new subsystems extracted: auth, system_routes, workspaces, integrations, transitions, fragments. Circular import with app_factory fixed."
gh issue close 535
gh issue edit 535 --remove-label "needs-triage"
```
