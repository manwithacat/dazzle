# Runtime Services: Eliminate HIGH-Risk Mutable Singletons (Phase 1)

**Issue:** #673 — 32 module-level mutable singletons across 18 files
**Date:** 2026-03-25
**Status:** Approved
**Scope:** Phase 1 — `dazzle_back` runtime singletons only

## Problem

Six HIGH-risk module-level singletons in `dazzle_back` use the `global` keyword to mutate shared state. In multi-tenant deployments (one process, multiple tenants), these create:

- **Cross-tenant data leakage** — event bus broadcasts to all WebSocket clients regardless of tenant
- **Cross-test pollution** — tests mutate global state without reliable teardown
- **Implicit coupling** — callers use `get_event_bus()` with no indication of where the bus came from

The pattern:
```python
_global_event_bus: EntityEventBus | None = None

def get_event_bus() -> EntityEventBus:
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EntityEventBus()
    return _global_event_bus
```

## Scope

**In scope (Phase 1 — 6 HIGH-risk singletons in `dazzle_back`):**

| File | Variable | Risk |
|------|----------|------|
| `runtime/event_bus.py` | `_global_event_bus` | Cross-tenant event broadcasting |
| `runtime/presence_tracker.py` | `_global_presence_tracker` | User presence leakage |
| `events/framework.py` | `_framework` | Single framework for all requests |
| `metrics/collector.py` | `_collector` | Cross-request metric pollution |
| `metrics/system_collector.py` | `_system_collector` | Cross-request state |
| `runtime/metrics/emitter.py` | `_emitter` | Shared Redis connection |

**Out of scope (Phase 2+):**

- MEDIUM-risk: `rate_limit`, `logging`, `template_renderer`, `api_kb` cache
- LOW-risk: lazy imports, read-only caches (6 singletons)
- `dazzle` package singletons: `rbac/audit.py`, `mcp/server/state.py`, `runtime_tools/state.py`, `core/process/eventbus_adapter.py` (no FastAPI access — need different pattern)

## Decision

**Approach A: FastAPI `app.state` Container.**

Consolidate the 6 singletons into a `RuntimeServices` dataclass attached to `app.state.services`. Access via `Depends(get_services)` in routes, `request.app.state.services` in middleware.

## Design

### `RuntimeServices` Dataclass

New file: `src/dazzle_back/runtime/services.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dazzle_back.runtime.event_bus import EntityEventBus
from dazzle_back.runtime.presence_tracker import PresenceTracker

if TYPE_CHECKING:
    from dazzle_back.events.framework import EventFramework
    from dazzle_back.metrics.collector import MetricsCollector
    from dazzle_back.metrics.system_collector import SystemMetricsCollector
    from dazzle_back.runtime.metrics.emitter import MetricsEmitter

from fastapi import Request


@dataclass
class RuntimeServices:
    """Runtime service container — replaces module-level singletons.

    Attached to app.state.services at startup. Each app instance
    gets its own services, enabling multi-tenant isolation and
    clean test fixtures.
    """

    event_bus: EntityEventBus = field(default_factory=EntityEventBus)
    presence_tracker: PresenceTracker = field(default_factory=PresenceTracker)
    event_framework: EventFramework | None = None
    metrics_collector: MetricsCollector | None = None
    system_collector: SystemMetricsCollector | None = None
    metrics_emitter: MetricsEmitter | None = None


def get_services(request: Request) -> RuntimeServices:
    """FastAPI dependency — typed access to runtime services."""
    return request.app.state.services
```

### Startup Wiring

In app startup (wherever the FastAPI app is assembled), create and attach:

```python
from dazzle_back.runtime.services import RuntimeServices

services = RuntimeServices()
app.state.services = services
```

Event framework, metrics, and emitter are attached later during their async init phases:

```python
# In events subsystem startup:
app.state.services.event_framework = framework

# In metrics startup:
app.state.services.metrics_collector = collector
app.state.services.system_collector = system_collector
app.state.services.metrics_emitter = emitter
```

### Caller Migration

All callers replace `get_X()` calls with `services.X` access. The access pattern depends on context:

**Route handlers** — via `Depends()`:
```python
from dazzle_back.runtime.services import RuntimeServices, get_services

@router.post("/api/things")
async def create_thing(services: RuntimeServices = Depends(get_services)):
    services.event_bus.publish(...)
```

**Middleware** — via `request.app.state.services`:
```python
async def dispatch(self, request, call_next):
    services = request.app.state.services
    emitter = services.metrics_emitter
    ...
```

**WebSocket handlers** — via `websocket.app.state.services`:
```python
async def ws_handler(websocket: WebSocket):
    services = websocket.app.state.services
    services.presence_tracker.track(...)
```

**Background tasks** — receive `services` as a parameter from the route that launched them:
```python
background_tasks.add_task(process_event, services=services, event=event)
```

**`RealtimeRepositoryMixin`** (in `event_bus.py`) — takes `event_bus` as constructor arg instead of calling `get_event_bus()`:
```python
class RealtimeRepositoryMixin:
    def __init__(self, ..., event_bus: EntityEventBus | None = None):
        self._event_bus = event_bus
```

### Deletions

The following global functions are deleted (clean break, no compatibility shims):

| File | Deleted functions |
|------|-------------------|
| `runtime/event_bus.py` | `get_event_bus()`, `set_event_bus()`, `reset_event_bus()` |
| `runtime/presence_tracker.py` | `get_presence_tracker()`, `set_presence_tracker()`, `reset_presence_tracker()` |
| `events/framework.py` | `_framework` global, `get_framework()`, `init_framework()`, `shutdown_framework()` |
| `metrics/collector.py` | `_collector` global, `get_collector()`, `reset_collector()` |
| `metrics/system_collector.py` | `_system_collector` global, `get_system_collector()`, `reset_system_collector()` |
| `runtime/metrics/emitter.py` | `_emitter` global, `get_emitter()`, `emit()` convenience function |

### Test Isolation

Tests create fresh `RuntimeServices` per test via pytest fixture:

```python
@pytest.fixture
def services():
    return RuntimeServices()

@pytest.fixture
def event_bus(services):
    return services.event_bus
```

Existing test files (`test_event_bus.py`, `test_presence_tracker.py`) replace:
- `reset_event_bus()` / `reset_presence_tracker()` → fixture creates fresh instance
- `get_event_bus()` → `event_bus` fixture parameter
- `set_event_bus(custom)` → direct constructor or fixture override

The global singleton tests (`test_set_event_bus`, `test_reset_event_bus`, `test_get_event_bus_returns_singleton`) are deleted — they tested the singleton pattern which no longer exists.

### `service_mixin.py` Change

`EventServiceMixin.set_event_framework()` currently stores the framework on the service instance. This stays — but the caller in `events.py:61` passes `services.event_framework` instead of using a global getter.

## Production Callers Inventory

| File | Current call | New access |
|------|-------------|-----------|
| `runtime/server.py:933` | `get_event_bus()` | `app.state.services.event_bus` |
| `runtime/subsystems/system_routes.py:172` | `get_event_bus()` | `services.event_bus` via Depends |
| `runtime/subsystems/events.py:61` | `self._framework` (already avoids global) | store on `services.event_framework` instead of `SubsystemContext` |
| `events/service_mixin.py:67` | `set_event_framework()` on self | unchanged (instance method) |
| `runtime/metrics/middleware.py:60` | `get_emitter()` | `request.app.state.services.metrics_emitter` |
| `runtime/metrics/emitter.py:235` | `emit()` calls `get_emitter()` | delete `emit()`, callers use `services.metrics_emitter.emit()` directly |
| `metrics/collector.py:282` | `get_collector()` definition | deleted |
| `metrics/system_collector.py:606` | `get_system_collector()` definition | deleted |
| `runtime/event_bus.py:418` | `get_event_bus()` fallback in `RealtimeRepositoryMixin` | `self._event_bus` (required param) |
| `runtime/auth/events.py:115` | `get_framework()` | `services.event_framework` (via app.state or passed as param) |
| `runtime/realtime_routes.py:44` | `create_presence_tracker()` fallback | `services.presence_tracker` from app.state |

### Cross-Package Caller: `eventbus_adapter.py`

`src/dazzle/core/process/eventbus_adapter.py:390` calls `get_framework()` via a lazy import. This lives in the `dazzle` package (no FastAPI access). However, the global `_framework` is never populated by the current `EventsSubsystem` (which stores the framework on `SubsystemContext.event_framework` instead). The `get_framework()` call already raises `RuntimeError` at runtime, and `eventbus_adapter.py` has a try/except guard that swallows it. **Deleting `get_framework()` does not change behavior** — the caller's fallback path already handles the missing framework. This will be properly addressed in Phase 2 when `dazzle` package singletons are migrated.

## Files Changed

| File | Change |
|------|--------|
| `src/dazzle_back/runtime/services.py` | **New** — `RuntimeServices` dataclass + `get_services()` |
| `src/dazzle_back/runtime/event_bus.py` | Delete global singleton functions; `RealtimeRepositoryMixin` takes `event_bus` as constructor arg |
| `src/dazzle_back/runtime/presence_tracker.py` | Delete global singleton functions; keep `PresenceTracker` class and `create_presence_tracker()` |
| `src/dazzle_back/events/framework.py` | Delete `_framework` global, `get_framework()`, `init_framework()`, `shutdown_framework()` |
| `src/dazzle_back/events/__init__.py` | Remove re-exports of `get_framework`, `init_framework`, `shutdown_framework` |
| `src/dazzle_back/metrics/collector.py` | Delete `_collector` global and getter/setter |
| `src/dazzle_back/metrics/system_collector.py` | Delete `_system_collector` global and getter/setter |
| `src/dazzle_back/metrics/__init__.py` | Remove re-exports of `get_system_collector`, `reset_system_collector` |
| `src/dazzle_back/runtime/metrics/emitter.py` | Delete `_emitter` global, `get_emitter()`, `emit()`; move `atexit` shutdown to FastAPI lifecycle |
| `src/dazzle_back/runtime/metrics/__init__.py` | Remove re-exports of `get_emitter`, `emit` |
| `src/dazzle_back/runtime/metrics/middleware.py` | Access emitter via `request.app.state.services` |
| `src/dazzle_back/runtime/server.py` | Create `RuntimeServices`, attach to `app.state`; replace `get_event_bus()` |
| `src/dazzle_back/runtime/subsystems/system_routes.py` | Replace `get_event_bus()` with services access |
| `src/dazzle_back/runtime/subsystems/events.py` | Store framework on `services.event_framework` |
| `src/dazzle_back/runtime/auth/events.py` | Replace `get_framework()` with services access |
| `src/dazzle_back/runtime/realtime_routes.py` | Replace `create_presence_tracker()` fallback with `services.presence_tracker` |
| `src/dazzle_back/tests/test_event_bus.py` | Replace global get/set/reset with fixture-based instances |
| `src/dazzle_back/tests/test_presence_tracker.py` | Replace global get/set/reset with fixture-based instances |
| `tests/unit/test_auth_events.py` | Update 11 `get_framework` patches to use services |
| `tests/unit/test_runtime_services.py` | **New** — tests for `RuntimeServices` dataclass |

## Testing

### Automated
- Test `RuntimeServices` creates independent instances (no shared state)
- Test `get_services()` dependency returns `app.state.services`
- Test event bus fixture isolation (two tests don't share bus state)
- Test presence tracker fixture isolation
- Verify `global` keyword count in `src/dazzle_back/` drops from ~20 to ≤4

### Manual
- `dazzle serve --local` — verify event bus, presence tracker, metrics all function
- Run existing E2E tests — verify no regression

## Success Criteria

- `grep -rn "^    global " src/dazzle_back/ --include="*.py" | wc -l` ≤ 4 (down from ~20)
- No `get_event_bus()`, `get_presence_tracker()`, or similar global getters remain
- All runtime services accessed via `RuntimeServices` container
- Tests use fixtures, not global reset functions

## Future Work (Phase 2+)

- Thread `RuntimeServices` through `dazzle` package singletons (`rbac/audit.py`, `mcp/server/state.py`)
- Consolidate MEDIUM-risk singletons (`rate_limit`, `logging`, `template_renderer`)
- Add `# noqa: PLW0603` requirement for remaining `global` usage with mandatory comments
