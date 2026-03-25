# Runtime Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate 6 HIGH-risk module-level mutable singletons in `dazzle_back` by consolidating them into a `RuntimeServices` dataclass on `app.state`.

**Architecture:** Create `RuntimeServices` dataclass holding event_bus, presence_tracker, event_framework, metrics. Attach to `app.state.services` at startup. Route handlers access via `Depends(get_services)`, middleware via `request.app.state.services`. Delete all `get_X()` / `set_X()` / `reset_X()` global functions. Tests use pytest fixtures creating fresh instances.

**Tech Stack:** FastAPI `app.state`, Python dataclasses, pytest fixtures

**Spec:** `docs/superpowers/specs/2026-03-25-runtime-services-design.md`

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `src/dazzle_back/runtime/services.py` | Create | `RuntimeServices` dataclass + `get_services()` dependency |
| `src/dazzle_back/runtime/event_bus.py` | Modify | Delete global singleton section; update `RealtimeRepositoryMixin` |
| `src/dazzle_back/runtime/presence_tracker.py` | Modify | Delete global singleton section |
| `src/dazzle_back/events/framework.py` | Modify | Delete `_framework` global, `get_framework()`, `init_framework()`, `shutdown_framework()` |
| `src/dazzle_back/events/__init__.py` | Modify | Remove framework singleton re-exports |
| `src/dazzle_back/metrics/collector.py` | Modify | Delete `_collector` global and getter/setter |
| `src/dazzle_back/metrics/system_collector.py` | Modify | Delete `_system_collector` global and getter/setter |
| `src/dazzle_back/metrics/__init__.py` | Modify | Remove singleton re-exports |
| `src/dazzle_back/runtime/metrics/emitter.py` | Modify | Delete `_emitter` global, `get_emitter()`, `emit()` |
| `src/dazzle_back/runtime/metrics/__init__.py` | Modify | Remove singleton re-exports |
| `src/dazzle_back/runtime/metrics/middleware.py` | Modify | Use `request.app.state.services.metrics_emitter` |
| `src/dazzle_back/runtime/server.py` | Modify | Create and attach `RuntimeServices` |
| `src/dazzle_back/runtime/subsystems/system_routes.py` | Modify | Use services for event_bus |
| `src/dazzle_back/runtime/subsystems/events.py` | Modify | Store framework on `app.state.services` |
| `src/dazzle_back/runtime/auth/events.py` | Modify | Replace `get_framework()` with services access |
| `src/dazzle_back/runtime/realtime_routes.py` | Modify | Use services for presence_tracker |
| `src/dazzle_back/tests/test_event_bus.py` | Modify | Fixture-based isolation, delete singleton tests |
| `src/dazzle_back/tests/test_presence_tracker.py` | Modify | Fixture-based isolation, delete singleton tests |
| `tests/unit/test_auth_events.py` | Modify | Update `get_framework` patches |
| `tests/unit/test_runtime_services.py` | Create | Tests for `RuntimeServices` |

---

### Task 1: Create `RuntimeServices` Dataclass + Tests

**Files:**
- Create: `src/dazzle_back/runtime/services.py`
- Create: `tests/unit/test_runtime_services.py`

- [ ] **Step 1: Write the tests**

Create `tests/unit/test_runtime_services.py`:

```python
"""Tests for RuntimeServices container."""

from __future__ import annotations

from unittest.mock import MagicMock

from dazzle_back.runtime.services import RuntimeServices


class TestRuntimeServices:
    def test_creates_default_event_bus(self) -> None:
        services = RuntimeServices()
        assert services.event_bus is not None

    def test_creates_default_presence_tracker(self) -> None:
        services = RuntimeServices()
        assert services.presence_tracker is not None

    def test_optional_fields_default_none(self) -> None:
        services = RuntimeServices()
        assert services.event_framework is None
        assert services.metrics_collector is None
        assert services.system_collector is None
        assert services.metrics_emitter is None

    def test_independent_instances(self) -> None:
        s1 = RuntimeServices()
        s2 = RuntimeServices()
        assert s1.event_bus is not s2.event_bus
        assert s1.presence_tracker is not s2.presence_tracker

    def test_accepts_custom_services(self) -> None:
        mock_framework = MagicMock()
        services = RuntimeServices(event_framework=mock_framework)
        assert services.event_framework is mock_framework
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_runtime_services.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dazzle_back.runtime.services'`

- [ ] **Step 3: Create `services.py`**

Create `src/dazzle_back/runtime/services.py`:

```python
"""Runtime service container — replaces module-level singletons.

Attached to app.state.services at startup.  Each app instance gets its own
services, enabling multi-tenant isolation and clean test fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fastapi import Request

from dazzle_back.runtime.event_bus import EntityEventBus
from dazzle_back.runtime.presence_tracker import PresenceTracker

if TYPE_CHECKING:
    from dazzle_back.events.framework import EventFramework
    from dazzle_back.metrics.collector import MetricsCollector
    from dazzle_back.metrics.system_collector import SystemMetricsCollector
    from dazzle_back.runtime.metrics.emitter import MetricsEmitter


@dataclass
class RuntimeServices:
    """Container for runtime service instances.

    Required services (event_bus, presence_tracker) are created by default.
    Optional services (metrics, event framework) are attached during their
    respective async init phases.
    """

    event_bus: EntityEventBus = field(default_factory=EntityEventBus)
    presence_tracker: PresenceTracker = field(default_factory=PresenceTracker)
    event_framework: Any = None  # EventFramework | NullEventFramework | None
    metrics_collector: MetricsCollector | None = None
    system_collector: SystemMetricsCollector | None = None
    metrics_emitter: MetricsEmitter | None = None


def get_services(request: Request) -> RuntimeServices:
    """FastAPI dependency — typed access to runtime services."""
    return request.app.state.services
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_runtime_services.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/services.py tests/unit/test_runtime_services.py
git commit -m "feat(runtime): create RuntimeServices container (#673)"
```

---

### Task 2: Delete Event Bus Global Singleton + Update `RealtimeRepositoryMixin`

**Files:**
- Modify: `src/dazzle_back/runtime/event_bus.py`

- [ ] **Step 1: Delete the global singleton section**

In `src/dazzle_back/runtime/event_bus.py`, delete lines 367-393 (the entire `# Global Event Bus` section including `_global_event_bus`, `get_event_bus()`, `set_event_bus()`, `reset_event_bus()`).

- [ ] **Step 2: Update `RealtimeRepositoryMixin.get_event_bus()`**

The method at line 416-418 currently falls back to `get_event_bus()`:
```python
    def get_event_bus(self) -> EntityEventBus:
        """Get the event bus, using global if not set."""
        return self._event_bus or get_event_bus()
```

Change to raise if not set:
```python
    def get_event_bus(self) -> EntityEventBus:
        """Get the event bus for this repository."""
        if self._event_bus is None:
            raise RuntimeError(
                f"{type(self).__name__} has no event bus — "
                "call set_event_bus() during service initialization"
            )
        return self._event_bus
```

- [ ] **Step 3: Remove the `get_event_bus` import from any remaining imports in the file**

Check the file's import block and remove any self-referencing import of `get_event_bus`.

- [ ] **Step 4: Verify the file is syntactically valid**

Run: `python -c "import dazzle_back.runtime.event_bus"`
Expected: No error

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/event_bus.py
git commit -m "refactor(runtime): delete event bus global singleton (#673)"
```

---

### Task 3: Delete Presence Tracker Global Singleton

**Files:**
- Modify: `src/dazzle_back/runtime/presence_tracker.py`

- [ ] **Step 1: Delete the global singleton section**

Delete lines 452-470 (`_global_presence_tracker`, `get_presence_tracker()`, `set_presence_tracker()`, `reset_presence_tracker()`).

Keep `create_presence_tracker()` — it's a factory function used by `realtime_routes.py`.

- [ ] **Step 2: Verify**

Run: `python -c "import dazzle_back.runtime.presence_tracker"`
Expected: No error

- [ ] **Step 3: Commit**

```bash
git add src/dazzle_back/runtime/presence_tracker.py
git commit -m "refactor(runtime): delete presence tracker global singleton (#673)"
```

---

### Task 4: Delete Event Framework Global Singleton + Update Re-exports

**Files:**
- Modify: `src/dazzle_back/events/framework.py`
- Modify: `src/dazzle_back/events/__init__.py`

- [ ] **Step 1: Delete framework globals from `framework.py`**

Delete the `_framework` module-level variable and these functions: `get_framework()`, `init_framework()`, `shutdown_framework()`. These are near the end of the file (around lines 515-560).

Keep the `EventFramework` class and `EventFrameworkConfig` — only the singleton management goes.

- [ ] **Step 2: Update `events/__init__.py` re-exports**

In `src/dazzle_back/events/__init__.py`, remove `get_framework`, `init_framework`, `shutdown_framework` from both the import block (lines 50-52) and `__all__` list (lines 179-181).

- [ ] **Step 3: Verify**

Run: `python -c "from dazzle_back.events import EventFramework"`
Expected: No error

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_back/events/framework.py src/dazzle_back/events/__init__.py
git commit -m "refactor(events): delete event framework global singleton (#673)"
```

---

### Task 5: Delete Metrics Globals + Update Re-exports

**Files:**
- Modify: `src/dazzle_back/metrics/collector.py`
- Modify: `src/dazzle_back/metrics/system_collector.py`
- Modify: `src/dazzle_back/metrics/__init__.py`
- Modify: `src/dazzle_back/runtime/metrics/emitter.py`
- Modify: `src/dazzle_back/runtime/metrics/__init__.py`

- [ ] **Step 1: Delete collector globals from `collector.py`**

Delete `_collector` variable, `get_collector()`, `reset_collector()` (around lines 279-300).

- [ ] **Step 2: Delete system_collector globals from `system_collector.py`**

Delete `_system_collector` variable, `get_system_collector()`, `reset_system_collector()` (around lines 605-620).

- [ ] **Step 3: Update `metrics/__init__.py`**

Remove `get_system_collector` and `reset_system_collector` from both the import block and `__all__`.

- [ ] **Step 4: Delete emitter globals from `emitter.py`**

Delete `_emitter` variable, `get_emitter()`, `emit()` convenience function (lines 219-237). Also delete the `import atexit` and `import os` if no longer needed. Note: the `atexit.register(_emitter.shutdown)` call goes away — emitter shutdown will be handled by FastAPI lifecycle in Task 7.

- [ ] **Step 5: Update `runtime/metrics/__init__.py`**

Remove `get_emitter` and `emit` from both the import and `__all__`:

```python
from .emitter import MetricsEmitter
from .middleware import MetricsMiddleware, add_metrics_middleware

__all__ = [
    "MetricsEmitter",
    "MetricsMiddleware",
    "add_metrics_middleware",
]
```

- [ ] **Step 6: Verify**

Run: `python -c "from dazzle_back.metrics import MetricsCollector, SystemMetricsCollector; from dazzle_back.runtime.metrics import MetricsEmitter"`
Expected: No error

- [ ] **Step 7: Commit**

```bash
git add src/dazzle_back/metrics/collector.py src/dazzle_back/metrics/system_collector.py src/dazzle_back/metrics/__init__.py src/dazzle_back/runtime/metrics/emitter.py src/dazzle_back/runtime/metrics/__init__.py
git commit -m "refactor(metrics): delete metrics global singletons (#673)"
```

---

### Task 6: Wire `RuntimeServices` into App Startup

**Files:**
- Modify: `src/dazzle_back/runtime/server.py`
- Modify: `src/dazzle_back/runtime/subsystems/events.py`

- [ ] **Step 1: Read `server.py` to find where the app is assembled**

Read `src/dazzle_back/runtime/server.py` to find the function that creates the FastAPI app and where `get_event_bus()` is called at line 933.

- [ ] **Step 2: Create and attach `RuntimeServices` at app creation**

Add near the top of the app assembly function:

```python
from dazzle_back.runtime.services import RuntimeServices

services = RuntimeServices()
app.state.services = services
```

- [ ] **Step 3: Replace `get_event_bus()` call at line 933**

Change:
```python
from dazzle_back.runtime.event_bus import get_event_bus
_upload_bus = get_event_bus()
```
to:
```python
_upload_bus = app.state.services.event_bus
```

- [ ] **Step 4: Update `EventsSubsystem` to store framework on services**

In `src/dazzle_back/runtime/subsystems/events.py`, after the framework is created and assigned to `ctx.event_framework` (line 45), also store it on services:

```python
        ctx.event_framework = self._framework

        # Store on RuntimeServices for dependency injection
        if hasattr(ctx.app.state, "services"):
            ctx.app.state.services.event_framework = self._framework
```

- [ ] **Step 5: Verify server still starts**

Run: `python -c "from dazzle_back.runtime.server import create_app; print('OK')"`
Expected: No import error (actual server start requires config)

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_back/runtime/server.py src/dazzle_back/runtime/subsystems/events.py
git commit -m "feat(runtime): wire RuntimeServices into app startup (#673)"
```

---

### Task 7: Migrate Remaining Production Callers

**Files:**
- Modify: `src/dazzle_back/runtime/subsystems/system_routes.py`
- Modify: `src/dazzle_back/runtime/metrics/middleware.py`
- Modify: `src/dazzle_back/runtime/auth/events.py`
- Modify: `src/dazzle_back/runtime/realtime_routes.py`

- [ ] **Step 1: Update `system_routes.py`**

Read the file. At line 170-173, replace:
```python
from dazzle_back.runtime.event_bus import get_event_bus
event_bus = get_event_bus()
```
with:
```python
event_bus = ctx.app.state.services.event_bus
```

(Check that `ctx` has access to `app` — it's a `SubsystemContext` which holds the FastAPI app.)

- [ ] **Step 2: Update `metrics/middleware.py`**

At line 60, replace:
```python
emitter = get_emitter()
```
with:
```python
services = getattr(request.app.state, "services", None)
emitter = services.metrics_emitter if services else None
```

Remove the `get_emitter` import.

- [ ] **Step 3: Update `auth/events.py`**

At lines 115-118, the `_publish()` function calls `get_framework()`. This function doesn't have access to `request` or `app`. Replace:

```python
    try:
        from dazzle_back.events.framework import get_framework

        framework = get_framework()
        bus = framework.get_bus() if framework else None
```

with a new approach — pass `app` or `services` to `_publish()`. Read the file to understand how `_publish()` is called. If it's called from route handlers, thread `services` through. If it's called from auth middleware, use a module-level reference set during startup:

```python
_event_framework: Any = None

def configure_auth_events(framework: Any) -> None:
    """Set the event framework for auth event publishing."""
    global _event_framework
    _event_framework = framework

async def _publish(envelope: EventEnvelope) -> None:
    try:
        framework = _event_framework
        bus = framework.get_bus() if framework else None
```

Note: this keeps one `global` keyword, but it's a clean setter called once at startup — not a lazy-init singleton. Wire `configure_auth_events()` from `EventsSubsystem.startup()`.

- [ ] **Step 4: Update `realtime_routes.py`**

At lines 36-44, `RealtimeContext.__init__()` uses `create_presence_tracker()` as a fallback. Read the file to understand how `RealtimeContext` is constructed. If it's constructed in a route handler, pass `services` values. If it's a standalone creation, update the constructor to accept `services`:

```python
    def __init__(
        self,
        ws_manager: WebSocketManager | None = None,
        event_bus: EntityEventBus | None = None,
        presence_tracker: PresenceTracker | None = None,
    ):
        self.ws_manager = ws_manager or create_websocket_manager()
        self.event_bus = event_bus or EntityEventBus()
        self.presence_tracker = presence_tracker or PresenceTracker()
```

The key change: replace `create_event_bus()` with `EntityEventBus()` and `create_presence_tracker()` with `PresenceTracker()` as defaults. Callers that have access to `services` should pass `services.event_bus` and `services.presence_tracker` explicitly.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/subsystems/system_routes.py src/dazzle_back/runtime/metrics/middleware.py src/dazzle_back/runtime/auth/events.py src/dazzle_back/runtime/realtime_routes.py
git commit -m "refactor(runtime): migrate callers to RuntimeServices (#673)"
```

---

### Task 8: Migrate Test Files

**Files:**
- Modify: `src/dazzle_back/tests/test_event_bus.py`
- Modify: `src/dazzle_back/tests/test_presence_tracker.py`
- Modify: `tests/unit/test_auth_events.py`

- [ ] **Step 1: Update `test_event_bus.py` fixtures**

Replace the `reset_global_bus` autouse fixture (lines 30-35):
```python
@pytest.fixture(autouse=True)
def reset_global_bus() -> Any:
    reset_event_bus()
    yield
    reset_event_bus()
```
with:
```python
# No autouse fixture needed — each test gets fresh instances via fixtures.
```

Update the `event_bus` fixture (lines 38-41):
```python
@pytest.fixture
def event_bus() -> Any:
    return create_event_bus()
```
(This already creates a fresh bus per test — keep as-is, just remove the `reset_event_bus` import.)

Remove imports of `get_event_bus`, `set_event_bus`, `reset_event_bus` from the import block.

- [ ] **Step 2: Delete `TestGlobalEventBus` class**

Delete the entire `TestGlobalEventBus` class (lines 289-340) — these tests tested the singleton pattern which no longer exists.

- [ ] **Step 3: Update any remaining tests that use `set_event_bus()`**

Line 340 has a test using `set_event_bus(bus)`. Read the context — if it's setting up state for an integration test, replace with passing the bus directly to the constructor.

- [ ] **Step 4: Update `test_presence_tracker.py` fixtures**

Same pattern: remove `reset_presence_tracker` autouse fixture, remove imports of `get_presence_tracker`, `set_presence_tracker`, `reset_presence_tracker`, delete `TestGlobalPresenceTracker` class (lines 412-442).

- [ ] **Step 5: Update `test_auth_events.py` patches**

There are ~11 patches of `dazzle_back.events.framework.get_framework`. These need to change to patch the new module-level variable. If Task 7 introduced `configure_auth_events()` with a `_event_framework` module-level var in `auth/events.py`, the patches change to:

```python
with patch("dazzle_back.runtime.auth.events._event_framework", mock_framework):
    await emit_user_registered(user, session_id="sess_abc")
```

- [ ] **Step 6: Run all affected tests**

```bash
pytest src/dazzle_back/tests/test_event_bus.py src/dazzle_back/tests/test_presence_tracker.py tests/unit/test_auth_events.py -v
```
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/dazzle_back/tests/test_event_bus.py src/dazzle_back/tests/test_presence_tracker.py tests/unit/test_auth_events.py
git commit -m "test(runtime): migrate tests to fixture-based isolation (#673)"
```

---

### Task 9: Run Full Test Suite + Quality Checks

- [ ] **Step 1: Run all unit tests**

Run: `pytest tests/ -m "not e2e" -x -q`
Expected: ALL PASS

- [ ] **Step 2: Check global keyword count**

Run: `grep -rn "^    global " src/dazzle_back/ --include="*.py" | grep -v examples | wc -l`
Expected: ≤ 4 (down from ~20)

- [ ] **Step 3: Verify no deleted functions remain as imports**

Run: `grep -rn "get_event_bus\|set_event_bus\|reset_event_bus\|get_presence_tracker\|set_presence_tracker\|reset_presence_tracker\|get_framework\|get_collector\|reset_collector\|get_system_collector\|reset_system_collector\|get_emitter" src/dazzle_back/ --include="*.py" | grep -v "test_\|\.pyc\|def get_event_bus\|def get_services"'`
Expected: 0 matches (or only in comments/docstrings)

- [ ] **Step 4: Lint**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`
Expected: Clean

- [ ] **Step 5: Type check**

Run: `mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp --ignore-missing-imports --exclude 'eject' && mypy src/dazzle_back/ --ignore-missing-imports`
Expected: Clean or no new errors

- [ ] **Step 6: Final commit if lint/format changes**

```bash
git add -u
git commit -m "chore: lint + format fixes for runtime services (#673)"
```

- [ ] **Step 7: Version bump**

Run `/bump patch` to increment the version.
