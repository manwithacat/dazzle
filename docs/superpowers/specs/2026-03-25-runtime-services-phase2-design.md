# Runtime Services Phase 2: Remaining Singletons + Annotation

**Issue:** #673 — 32 module-level mutable singletons across 18 files
**Date:** 2026-03-25
**Status:** Approved
**Scope:** Phase 2 — dazzle_back additions + dazzle MCP singletons + Phase 3 annotations

## Problem

Phase 1 (v0.48.9) eliminated 6 HIGH-risk `dazzle_back` runtime singletons. 24 `global` invocations remain across 18 files. Four are real singleton problems; the rest are acceptable patterns (lazy imports, caches, system-wide resources) that need annotation.

## Scope

**Phase 2 targets (4 real singleton problems):**

| File | Variable(s) | Risk | Pattern |
|------|-------------|------|---------|
| `dazzle_back/runtime/task_routes.py` | `_process_manager` | MEDIUM-HIGH | Add to `RuntimeServices`, use `Depends()` |
| `dazzle_back/runtime/rate_limit.py` | `limiter`, `auth_limit`, etc. | MEDIUM | Move config to `RuntimeServices`, limiter already on `app.state` |
| `dazzle/mcp/runtime_tools/state.py` | `_appspec_data`, `_ui_spec` | HIGH | Move onto `ServerState` |
| `dazzle/api_kb/loader.py` | `_pack_cache`, `_packs_loaded`, `_project_root` | MEDIUM-HIGH | Move onto `ServerState` |

**Phase 3 annotations (irreducible remainder):**

Every remaining `global` statement gets `# noqa: PLW0603  # <reason>`.

| File | Variable | Reason |
|------|----------|--------|
| `dazzle_back/pra/tigerbeetle_client.py` | `_tb_module` | Lazy import for optional dependency |
| `dazzle_back/runtime/logging.py` | `_log_dir`, `_file_handler` | System-wide, init-only, thread-safe |
| `dazzle_back/runtime/sa_schema.py` | `_sa_imported`, `_sa` | Lazy import for optional dependency |
| `dazzle_back/runtime/auth/events.py` | `_event_framework` | Clean setter from Phase 1 |
| `dazzle/rbac/audit.py` | `_current_sink` | Thread-safe, good test isolation design |
| `dazzle/mcp/server/handlers/stories.py` | `_TRIGGER_MAP` | Lazy-init, immutable once created |
| `dazzle/mcp/server/state.py` | `_state` | Well-designed centralized MCP state |
| `dazzle/mcp/cli_help.py` | `_cached_commands` | Lazy-init, immutable once created |
| `dazzle/mcp/semantics_kb/__init__.py` | `_semantic_cache` | KG fallback cache, lazy-init |
| `dazzle/cli/auth.py` | `_database_url_override` | CLI callback storage, per-invocation |
| `dazzle/cli/testing.py` | `_ASSERTION_HANDLERS` | Lazy-init handler registry, immutable |
| `dazzle/testing/browser_gate.py` | `_gate` | Process-bounded resource, thread-safe |
| `dazzle_ui/runtime/realtime_client.py` | `_REALTIME_JS_CACHED` | Static asset cache |
| `dazzle_ui/runtime/template_renderer.py` | `_env` | Single-project runtime, lazy-init |

## Design

### 1. `task_routes._process_manager` → `RuntimeServices`

Add `process_manager` to `RuntimeServices`:

```python
@dataclass
class RuntimeServices:
    # ... existing fields ...
    process_manager: ProcessManager | None = None
```

Wire from `ProcessSubsystem.startup()`:

```python
# In src/dazzle_back/runtime/subsystems/process.py
if hasattr(ctx.app.state, "services"):
    ctx.app.state.services.process_manager = self._manager
```

Task route handlers switch to `Depends(get_services)`:

```python
@router.post("/api/tasks/{task_id}/start")
async def start_task(task_id: str, services: RuntimeServices = Depends(get_services)):
    if services.process_manager is None:
        raise HTTPException(503, "Process subsystem not initialized")
    ...
```

Delete `_process_manager`, `get_process_manager()`, `set_process_manager()` from `task_routes.py`.

### 2. `rate_limit.py` → `RuntimeServices`

The limiter instance is already stored on `app.state` (lines 109, 139). The rate-limit strings are configuration that should live on a config dataclass:

```python
@dataclass
class RateLimitConfig:
    auth_limit: str = "10/minute"
    api_limit: str = "60/minute"
    upload_limit: str = "5/minute"
    twofa_limit: str = "5/minute"
```

Add to `RuntimeServices`:

```python
@dataclass
class RuntimeServices:
    # ... existing fields ...
    rate_limit_config: RateLimitConfig = field(default_factory=RateLimitConfig)
```

`apply_rate_limiting()` populates `services.rate_limit_config` from `dazzle.toml` settings instead of writing to module-level globals.

Route decorators change from `@_rl.limiter.limit(_rl.auth_limit)` to accessing `app.state.services.rate_limit_config`. Since Starlette `@limiter.limit()` decorators need a string at decoration time, the limiter strings stay as defaults in `RateLimitConfig` and are overridden during `apply_rate_limiting()`. The `Limiter` instance remains on `app.state` (already there).

Delete module-level `limiter`, `auth_limit`, `api_limit`, `upload_limit`, `twofa_limit` globals.

### 3. `runtime_tools/state.py` → `ServerState`

Move `_appspec_data` and `_ui_spec` onto `ServerState` as attributes:

```python
# In mcp/server/state.py ServerState class
@dataclass
class ServerState:
    # ... existing fields ...
    appspec_data: dict[str, Any] | None = None
    ui_spec: dict[str, Any] | None = None
```

Replace module-level functions in `runtime_tools/state.py` with `ServerState` methods or direct attribute access:

```python
# Before (runtime_tools/state.py)
def get_appspec_data() -> dict[str, Any] | None:
    return _appspec_data

# After (callers use)
from dazzle.mcp.server.state import get_state
state = get_state()
state.appspec_data
```

Delete the entire `runtime_tools/state.py` module — its only purpose was holding these two globals. Update imports in `runtime_tools/handlers.py` and `runtime_tools/tool_handlers.py`.

### 4. `api_kb/loader.py` → `ServerState`

Move `_pack_cache`, `_packs_loaded`, `_project_root` onto `ServerState`:

```python
@dataclass
class ServerState:
    # ... existing fields ...
    pack_cache: dict[str, ApiPack] = field(default_factory=dict)
    packs_loaded: bool = False
```

`project_root` is already on `ServerState`. The `set_project_root()` in `state.py` already calls `api_kb.loader.set_project_root()` — reverse that flow: `ServerState.set_project_root()` clears `pack_cache` and resets `packs_loaded` directly.

`load_pack()`, `list_packs()`, `search_packs()` accept an optional `state` parameter (defaulting to `get_state()`). The thread lock moves to `ServerState` or is replaced by the existing `_state` access pattern.

Delete module-level `_pack_cache`, `_packs_loaded`, `_project_root`, `_packs_lock` from `loader.py`. Keep `set_project_root()` as a thin wrapper calling `state.set_project_root()` for backward compatibility during transition, then delete in the same commit.

## Files Changed

| File | Change |
|------|--------|
| `src/dazzle_back/runtime/services.py` | Add `process_manager`, `rate_limit_config` fields |
| `src/dazzle_back/runtime/task_routes.py` | Delete globals, use `Depends(get_services)` |
| `src/dazzle_back/runtime/subsystems/process.py` | Wire process_manager to services |
| `src/dazzle_back/runtime/rate_limit.py` | Delete globals, populate services config |
| `src/dazzle_back/runtime/file_routes.py` | Update rate limit decorator references |
| `src/dazzle/mcp/server/state.py` | Add `appspec_data`, `ui_spec`, `pack_cache`, `packs_loaded` to `ServerState` |
| `src/dazzle/mcp/runtime_tools/state.py` | **Delete** — migrate to ServerState |
| `src/dazzle/mcp/runtime_tools/handlers.py` | Update imports to ServerState |
| `src/dazzle/mcp/runtime_tools/tool_handlers.py` | Update imports to ServerState |
| `src/dazzle/api_kb/loader.py` | Delete globals, accept state parameter |
| ~14 files | Add `# noqa: PLW0603` annotations |
| Test files | Update patches and fixtures |

## Production Callers Inventory

### task_routes._process_manager

| File | Current call | New access |
|------|-------------|-----------|
| `runtime/task_routes.py:253,290,334,383,414` | `get_process_manager()` | `services.process_manager` via Depends |
| `runtime/subsystems/process.py:62` | `set_process_manager(manager)` | `app.state.services.process_manager = manager` |
| `tests/unit/test_eventbus_adapter.py` | patches `get_process_manager` | patches `services.process_manager` |
| `tests/unit/test_human_tasks.py` | patches `get_process_manager` | patches `services.process_manager` |

### rate_limit globals

| File | Current call | New access |
|------|-------------|-----------|
| `runtime/file_routes.py` | `@_rl.limiter.limit(_rl.auth_limit)` | `@app.state.limiter.limit(...)` with config from services |
| `runtime/server.py` | `apply_rate_limiting(app, config)` | Same, but writes to services |

### runtime_tools/state.py

| File | Current call | New access |
|------|-------------|-----------|
| `mcp/runtime_tools/handlers.py` | `get_appspec_data()`, `set_appspec_data()` | `state.appspec_data` |
| `mcp/runtime_tools/tool_handlers.py` | `get_ui_spec()`, `get_or_create_ui_spec()` | `state.ui_spec` |

### api_kb/loader.py globals

| File | Current call | New access |
|------|-------------|-----------|
| `mcp/server/state.py` | `api_kb.loader.set_project_root()` | Direct `state.pack_cache.clear()` |
| 20+ handler files | `load_pack()`, `list_packs()` | Same API, state passed internally |

## Testing

### Automated
- `RuntimeServices` tests extended for new fields
- Task route tests use fixture-based `services` instead of `set_process_manager()`
- Rate limit tests verify config propagation
- MCP handler tests verify appspec_data/ui_spec on ServerState
- Verify `global` count ≤ 15, all annotated

### Verification
```bash
# Count unannotated globals (should be 0)
grep -rn "^    global " src/ --include="*.py" | grep -v examples | grep -v "noqa: PLW0603" | wc -l

# Count all globals (should be ≤ 15)
grep -rn "^    global " src/ --include="*.py" | grep -v examples | wc -l
```

## Success Criteria

- All Phase 2 singletons eliminated (4 modules)
- All remaining `global` statements annotated with `# noqa: PLW0603  # <reason>`
- 0 unannotated `global` statements
- All tests pass
- `ruff check` and `mypy` clean
