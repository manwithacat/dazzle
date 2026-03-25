# Runtime Services Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate 4 remaining singleton modules, replace rate-limit globals with a container, and annotate all irreducible `global` statements with `# noqa: PLW0603`.

**Architecture:** `task_routes._process_manager` joins `RuntimeServices` on `app.state`. MCP singletons (`runtime_tools/state.py` globals, `api_kb/loader.py` cache) move to `ServerState`. Rate-limit globals become attributes on a module-level dataclass (no `global` keyword needed). All remaining acceptable globals get `# noqa: PLW0603  # <reason>` annotations.

**Tech Stack:** FastAPI `app.state`, Python dataclasses, `ServerState` in `mcp/server/state.py`

**Spec:** `docs/superpowers/specs/2026-03-25-runtime-services-phase2-design.md`

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `src/dazzle_back/runtime/services.py` | Modify | Add `process_manager` field |
| `src/dazzle_back/runtime/task_routes.py` | Modify | Delete globals, use `Depends(get_services)` |
| `src/dazzle_back/runtime/subsystems/process.py` | Modify | Wire process_manager to services |
| `src/dazzle_back/runtime/rate_limit.py` | Modify | Replace 5 globals with `_Limits` dataclass |
| `src/dazzle_back/runtime/file_routes.py` | Modify | Update rate limit decorator references |
| `src/dazzle/mcp/server/state.py` | Modify | Add `appspec_data`, `ui_spec`, `pack_cache`, `packs_loaded` |
| `src/dazzle/mcp/runtime_tools/state.py` | Delete | Migrated to ServerState |
| `src/dazzle/mcp/runtime_tools/handlers.py` | Modify | Import from ServerState |
| `src/dazzle/api_kb/loader.py` | Modify | Delete globals, use ServerState |
| ~14 files | Modify | Add `# noqa: PLW0603` annotations |
| `tests/unit/test_runtime_services.py` | Modify | Add process_manager test |

---

### Task 1: Add `process_manager` to `RuntimeServices` + Migrate Task Routes

**Files:**
- Modify: `src/dazzle_back/runtime/services.py`
- Modify: `src/dazzle_back/runtime/task_routes.py`
- Modify: `src/dazzle_back/runtime/subsystems/process.py`
- Modify: `tests/unit/test_runtime_services.py`

- [ ] **Step 1: Add test for new field**

In `tests/unit/test_runtime_services.py`, add to `TestRuntimeServices`:

```python
    def test_process_manager_defaults_none(self) -> None:
        services = RuntimeServices()
        assert services.process_manager is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_runtime_services.py::TestRuntimeServices::test_process_manager_defaults_none -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument` or attribute error

- [ ] **Step 3: Add `process_manager` to `RuntimeServices`**

In `src/dazzle_back/runtime/services.py`, add after the `metrics_emitter` field (line 37):

```python
    process_manager: Any = None  # ProcessManager | None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_runtime_services.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Delete globals from `task_routes.py`**

In `src/dazzle_back/runtime/task_routes.py`, delete lines 115-129 (the `_process_manager` variable, `set_process_manager()`, and `get_process_manager()` functions).

- [ ] **Step 6: Add `Depends(get_services)` to task route handlers**

Add import at top of `task_routes.py`:

```python
from fastapi import Depends
from dazzle_back.runtime.services import RuntimeServices, get_services
```

Update all 5 route handlers. Each one currently has `manager = get_process_manager()` inside the function body. Replace with a `services` parameter + inline check. Example for `list_tasks` (line 253):

Before:
```python
async def list_tasks(
    status: str | None = Query(None),
    assignee: str | None = Query(None),
) -> list[dict[str, Any]]:
    manager = get_process_manager()
```

After:
```python
async def list_tasks(
    status: str | None = Query(None),
    assignee: str | None = Query(None),
    services: RuntimeServices = Depends(get_services),
) -> list[dict[str, Any]]:
    if services.process_manager is None:
        raise HTTPException(503, "Process manager not initialized")
    manager = services.process_manager
```

Apply the same pattern to all 5 handlers:
- `list_tasks` (line 253)
- `get_task` (line 290)
- `complete_task` (line 334)
- `reassign_task` (line 383)
- `get_task_surface_url` (line 414)

- [ ] **Step 7: Wire process_manager from subsystem**

In `src/dazzle_back/runtime/subsystems/process.py`, replace the `set_process_manager` call (line 62):

Before:
```python
from dazzle_back.runtime.task_routes import set_process_manager
...
set_process_manager(self._manager)
```

After:
```python
# Store on RuntimeServices for dependency injection
if hasattr(ctx.app.state, "services"):
    ctx.app.state.services.process_manager = self._manager
```

Remove the `set_process_manager` import.

- [ ] **Step 8: Verify import and run affected tests**

Run: `python -c "from dazzle_back.runtime.task_routes import router; print('OK')"`
Run: `pytest tests/unit/test_runtime_services.py -v`
Expected: Both pass

- [ ] **Step 9: Commit**

```bash
git add src/dazzle_back/runtime/services.py src/dazzle_back/runtime/task_routes.py src/dazzle_back/runtime/subsystems/process.py tests/unit/test_runtime_services.py
git commit -m "refactor(runtime): migrate process_manager to RuntimeServices (#673)"
```

---

### Task 2: Replace Rate Limit Globals with Dataclass Container

**Files:**
- Modify: `src/dazzle_back/runtime/rate_limit.py`
- Modify: `src/dazzle_back/runtime/file_routes.py`

- [ ] **Step 1: Replace 5 module-level globals with a `_Limits` dataclass**

In `src/dazzle_back/runtime/rate_limit.py`, replace lines 37-48:

Before:
```python
limiter: Any = _NoOpLimiter()
...
auth_limit: str = "10/minute"
api_limit: str = "60/minute"
upload_limit: str = "10/minute"
twofa_limit: str = "5/minute"
```

After:
```python
@dataclass
class _Limits:
    """Mutable container for rate-limit state.

    Attributes are set once by apply_rate_limiting() at startup.
    Using a dataclass avoids the ``global`` keyword — attribute
    assignment on an existing instance needs no global declaration.
    """

    limiter: Any = field(default_factory=_NoOpLimiter)
    auth_limit: str = "10/minute"
    api_limit: str = "60/minute"
    upload_limit: str = "10/minute"
    twofa_limit: str = "5/minute"


limits = _Limits()
```

Add `from dataclasses import dataclass, field` to imports.

- [ ] **Step 2: Update `apply_rate_limiting()` to write to `limits` container**

Replace the `global` statement and attribute writes in `apply_rate_limiting()` (line 106 onward):

Before:
```python
    global limiter, auth_limit, api_limit, upload_limit, twofa_limit
    ...
    if config.auth_limit:
        auth_limit = config.auth_limit
    ...
    limiter = _NoOpLimiter()
    ...
    limiter = Limiter(key_func=get_remote_address)
```

After:
```python
    config = configure_rate_limits_for_profile(profile)
    app.state.rate_limit_config = config

    if config.auth_limit:
        limits.auth_limit = config.auth_limit
    if config.api_limit:
        limits.api_limit = config.api_limit
    if config.upload_limit:
        limits.upload_limit = config.upload_limit
    if config.twofa_limit:
        limits.twofa_limit = config.twofa_limit

    if profile == "basic":
        limits.limiter = _NoOpLimiter()
        return
    ...
    limits.limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limits.limiter
```

- [ ] **Step 3: Update `file_routes.py` decorator references**

In `src/dazzle_back/runtime/file_routes.py`, update the decorator (line 406):

Before:
```python
@_rl.limiter.limit(_rl.upload_limit)  # type: ignore[misc,untyped-decorator,unused-ignore]
```

After:
```python
@_rl.limits.limiter.limit(_rl.limits.upload_limit)  # type: ignore[misc,untyped-decorator,unused-ignore]
```

Search the file for any other `_rl.limiter` or `_rl.auth_limit` etc. references and update them similarly.

- [ ] **Step 4: Verify import**

Run: `python -c "from dazzle_back.runtime.rate_limit import limits; print(limits.auth_limit)"`
Expected: `10/minute`

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/rate_limit.py src/dazzle_back/runtime/file_routes.py
git commit -m "refactor(runtime): replace rate limit globals with dataclass container (#673)"
```

---

### Task 3: Move `runtime_tools/state.py` Globals to `ServerState`

**Files:**
- Modify: `src/dazzle/mcp/server/state.py`
- Delete: `src/dazzle/mcp/runtime_tools/state.py`
- Modify: `src/dazzle/mcp/runtime_tools/handlers.py`

- [ ] **Step 1: Add `appspec_data` and `ui_spec` to `ServerState.__init__()`**

In `src/dazzle/mcp/server/state.py`, add to `ServerState.__init__()` after the existing fields:

```python
        self.appspec_data: dict[str, Any] | None = None
        self.ui_spec: dict[str, Any] | None = None
```

Also add to `ServerState.reset()`:

```python
        self.appspec_data = None
        self.ui_spec = None
```

Add `Any` to the typing imports if not already present.

- [ ] **Step 2: Add `get_or_create_ui_spec()` method to `ServerState`**

Add a method on `ServerState`:

```python
    def get_or_create_ui_spec(self) -> dict[str, Any]:
        """Get the UI spec, creating a default if none exists."""
        if self.ui_spec is None:
            self.ui_spec = {"name": "unnamed", "components": [], "workspaces": [], "themes": []}
        return self.ui_spec
```

- [ ] **Step 3: Update `runtime_tools/handlers.py` imports**

In `src/dazzle/mcp/runtime_tools/handlers.py`, replace the import (line 21):

Before:
```python
from .state import get_appspec_data, get_or_create_ui_spec, get_ui_spec
```

After:
```python
from dazzle.mcp.server.state import get_state
```

Then update all usages in the file. Each `get_appspec_data()` becomes `get_state().appspec_data`. Each `get_ui_spec()` becomes `get_state().ui_spec`. Each `get_or_create_ui_spec()` becomes `get_state().get_or_create_ui_spec()`. Each `set_appspec_data(spec)` becomes `get_state().appspec_data = spec`.

Specifically (these are approximate line numbers — read the file for exact locations):
- Line 46: `spec = get_state().appspec_data`
- Line 84: `spec = get_state().appspec_data`
- Line 107: `spec = get_state().appspec_data`
- Line 150: `spec = get_state().appspec_data`
- Line 185: `ui_spec = get_state().ui_spec`
- Line 229: `ui_spec = get_state().ui_spec`
- Line 302: `ui_spec = get_state().get_or_create_ui_spec()`
- Line 325: `ui_spec = get_state().ui_spec`
- Line 419: `ui_spec = get_state().get_or_create_ui_spec()`

Also find any `set_appspec_data(data)` calls and replace with `get_state().appspec_data = data`. Same for `set_ui_spec(data)` → `get_state().ui_spec = data`.

- [ ] **Step 4: Search for any other importers of `runtime_tools.state`**

Run: `grep -rn "from.*runtime_tools.state import\|from.*runtime_tools import state" src/ --include="*.py"`

Update any additional importers found with the same pattern.

- [ ] **Step 5: Delete `runtime_tools/state.py`**

```bash
git rm src/dazzle/mcp/runtime_tools/state.py
```

- [ ] **Step 6: Verify**

Run: `python -c "from dazzle.mcp.runtime_tools.handlers import handle_runtime_tools; print('OK')"`
Expected: No error

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/mcp/server/state.py src/dazzle/mcp/runtime_tools/handlers.py
git commit -m "refactor(mcp): move runtime_tools state to ServerState (#673)"
```

---

### Task 4: Move `api_kb/loader.py` Cache Globals to `ServerState`

**Files:**
- Modify: `src/dazzle/mcp/server/state.py`
- Modify: `src/dazzle/api_kb/loader.py`

- [ ] **Step 1: Add pack cache fields to `ServerState`**

In `src/dazzle/mcp/server/state.py`, add to `ServerState.__init__()`:

```python
        self.pack_cache: dict[str, Any] = {}
        self.packs_loaded: bool = False
```

Add to `ServerState.reset()`:

```python
        self.pack_cache.clear()
        self.packs_loaded = False
```

- [ ] **Step 2: Update `set_project_root()` in `state.py` to clear pack cache**

Find where `set_project_root()` in `state.py` calls `api_kb.loader.set_project_root()`. Add pack cache clearing:

```python
def set_project_root(path: Path) -> None:
    _state.project_root = path
    _state.pack_cache.clear()
    _state.packs_loaded = False
    # Remove the old api_kb.loader.set_project_root() call
```

- [ ] **Step 3: Update `loader.py` to use `ServerState`**

In `src/dazzle/api_kb/loader.py`, delete the module-level globals (lines 348-352):

```python
# DELETE these:
_pack_cache: dict[str, ApiPack] = {}
_packs_loaded = False
_project_root: Path | None = None
_packs_lock = threading.Lock()
```

Also delete the `set_project_root()` function (lines 355-365).

Update `_discover_packs()` to use state:

```python
def _discover_packs() -> None:
    """Discover all available packs (project-local first, then built-in)."""
    from dazzle.mcp.server.state import get_state

    state = get_state()
    if state.packs_loaded:
        return

    new_cache: dict[str, ApiPack] = {}

    # Project-local packs take priority
    project_packs_dir = state.project_root / ".dazzle" / "api_packs"
    _collect_packs_from_dir(project_packs_dir, new_cache)

    # Built-in packs (won't overwrite project-local ones with same name)
    _collect_packs_from_dir(_get_packs_dir(), new_cache)

    state.pack_cache = new_cache
    state.packs_loaded = True
```

Update `load_pack()`:

```python
def load_pack(pack_name: str) -> ApiPack | None:
    """Load a specific API pack by name."""
    from dazzle.mcp.server.state import get_state

    _discover_packs()
    return get_state().pack_cache.get(pack_name)
```

Update `list_packs()`:

```python
def list_packs() -> list[ApiPack]:
    """List all available API packs."""
    from dazzle.mcp.server.state import get_state

    _discover_packs()
    return list(get_state().pack_cache.values())
```

Note: imports are deferred (inside functions) to avoid circular imports since `loader.py` is in `dazzle.api_kb` and `state.py` is in `dazzle.mcp.server`.

Remove `import threading` if no longer needed. Remove the `_packs_lock` usage from `_discover_packs()` — `ServerState` is accessed from a single event loop thread (MCP server), so the lock is unnecessary. If thread safety is needed, it can be added back on `ServerState`.

- [ ] **Step 4: Search for remaining callers of `loader.set_project_root()`**

Run: `grep -rn "loader.set_project_root\|from.*loader import.*set_project_root" src/ --include="*.py"`

Update or remove any remaining callers (they should now go through `state.set_project_root()`).

- [ ] **Step 5: Verify**

Run: `python -c "from dazzle.api_kb.loader import load_pack, list_packs; print('OK')"`
Expected: No error

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/mcp/server/state.py src/dazzle/api_kb/loader.py
git commit -m "refactor(mcp): move api_kb pack cache to ServerState (#673)"
```

---

### Task 5: Annotate All Remaining `global` Statements

**Files:** ~14 files with remaining `global` statements

- [ ] **Step 1: Annotate each remaining `global` statement**

Add `  # noqa: PLW0603  # <reason>` to each line. The exact edits:

**`src/dazzle_back/pra/tigerbeetle_client.py:32`:**
```python
    global _tb_module  # noqa: PLW0603  # lazy import for optional dependency
```

**`src/dazzle_back/runtime/logging.py:187`:**
```python
    global _log_dir, _file_handler  # noqa: PLW0603  # system-wide logging, init-only
```

**`src/dazzle_back/runtime/sa_schema.py:36`:**
```python
    global _sa_imported, _sa  # noqa: PLW0603  # lazy import for optional sqlalchemy
```

**`src/dazzle_back/runtime/auth/events.py:39`:**
```python
    global _event_framework  # noqa: PLW0603  # clean setter called once at startup
```

**`src/dazzle_back/runtime/task_routes.py`:** (if any `global` remains after Task 1 — should be none)

**`src/dazzle/rbac/audit.py:92`:**
```python
    global _current_sink  # noqa: PLW0603  # thread-safe audit sink swap for testing
```

**`src/dazzle/mcp/server/handlers/stories.py:51`:**
```python
    global _TRIGGER_MAP  # noqa: PLW0603  # lazy-init, immutable once created
```

**`src/dazzle/mcp/server/state.py:82`:**
```python
    global _state  # noqa: PLW0603  # centralized MCP state, reset for test isolation
```

**`src/dazzle/mcp/cli_help.py:301`:**
```python
    global _cached_commands  # noqa: PLW0603  # lazy-init command cache, immutable once created
```

**`src/dazzle/mcp/semantics_kb/__init__.py:290`:**
```python
    global _semantic_cache  # noqa: PLW0603  # KG fallback cache, lazy-init
```

**`src/dazzle/mcp/semantics_kb/__init__.py:482`:**
```python
    global _semantic_cache  # noqa: PLW0603  # KG fallback cache reset for re-seeding
```

**`src/dazzle/cli/auth.py:43`:**
```python
    global _database_url_override  # noqa: PLW0603  # CLI callback storage, per-invocation
```

**`src/dazzle/cli/testing.py:963`:**
```python
    global _ASSERTION_HANDLERS  # noqa: PLW0603  # lazy-init handler registry, immutable
```

**`src/dazzle/testing/browser_gate.py:160`:**
```python
    global _gate  # noqa: PLW0603  # process-bounded browser resource, thread-safe
```

**`src/dazzle/testing/browser_gate.py:173`:**
```python
    global _gate  # noqa: PLW0603  # browser gate reconfiguration at startup
```

**`src/dazzle_ui/runtime/realtime_client.py:911`:**
```python
    global _REALTIME_JS_CACHED  # noqa: PLW0603  # static asset cache, immutable once loaded
```

**`src/dazzle_ui/runtime/template_renderer.py:318`:**
```python
    global _env  # noqa: PLW0603  # single-project Jinja2 env, lazy-init
```

**`src/dazzle_ui/runtime/template_renderer.py:330`:**
```python
    global _env  # noqa: PLW0603  # project template override at startup
```

- [ ] **Step 2: Verify no unannotated globals remain**

Run: `grep -rn "^    global " src/ --include="*.py" | grep -v examples | grep -v "noqa: PLW0603" | wc -l`
Expected: 0

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "chore: annotate irreducible globals with noqa PLW0603 (#673)"
```

---

### Task 6: Full Test Suite + Quality Checks

- [ ] **Step 1: Run all unit tests**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: ALL PASS

- [ ] **Step 2: Verify global counts**

Run: `grep -rn "^    global " src/ --include="*.py" | grep -v examples | wc -l`
Expected: ≤ 18 (all annotated)

Run: `grep -rn "^    global " src/ --include="*.py" | grep -v examples | grep -v "noqa: PLW0603" | wc -l`
Expected: 0 (none unannotated)

- [ ] **Step 3: Verify deleted functions don't remain as imports**

Run: `grep -rn "get_process_manager\|set_process_manager" src/dazzle_back/ --include="*.py" | grep -v "test_\|\.pyc"`
Expected: 0 matches

Run: `grep -rn "from.*runtime_tools.state import\|from.*runtime_tools import state" src/ --include="*.py"`
Expected: 0 matches

- [ ] **Step 4: Lint**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`
Expected: Clean

- [ ] **Step 5: Type check**

Run: `mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp --ignore-missing-imports --exclude 'eject' && mypy src/dazzle_back/ --ignore-missing-imports`
Expected: Clean

- [ ] **Step 6: Final commit if lint/format changes**

```bash
git add -u
git commit -m "chore: lint + format fixes for Phase 2 (#673)"
```

- [ ] **Step 7: Version bump**

Run `/bump patch` to increment the version.
