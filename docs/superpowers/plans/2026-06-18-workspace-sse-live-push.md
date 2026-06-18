# Workspace SSE Live Push Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A workspace declaring `live: on` pushes "an entity changed" nudges over SSE so its cards refresh instantly on mutations, with the `refresh: every Ns` poll retained as a fallback heartbeat.

**Architecture:** Connect three existing-but-disconnected pieces of infra. The HLESS framework `EventBus` is already wired and started by `EventsSubsystem`. We (1) make `CRUDService` lifecycle callbacks publish a nudge envelope to the canonical `entity.{created,updated,deleted}` bus topics, (2) mount the already-built `SSEStreamManager` + `/_ops/sse/events` route against that bus, independent of the ops dashboard, and (3) populate `WorkspaceContext.sse_url` when `live`, which activates the already-wired client `sse-connect` + `sse:entity.*` triggers. Nudge-only: events carry no row data; the card re-fetches via its existing scope-gated endpoint.

**Tech Stack:** Python 3.12+, FastAPI/Starlette `StreamingResponse`, psycopg3, Pydantic, HLESS event framework (`dazzle.back.events`), pytest.

## Global Constraints

- **No new singletons** — use `RuntimeServices` / `ServerState` (ADR-0005). The bus is reached via `app.state.services.event_framework`.
- **PostgreSQL-only runtime** (ADR-0008). The framework bus resolves to the postgres tier because `database_url` is always set.
- **No `from __future__ import annotations`** in FastAPI route files (ADR-0014). `sse_stream.py` / route files must not add it.
- **Nudge-only:** SSE events carry entity name + id + tenant header — never row field data.
- **Type hints required** on all public functions (mypy `mypy src/dazzle`).
- **Lint/format:** `ruff check src/ tests/ --fix && ruff format src/ tests/`.
- **Pre-ship test scope:** `pytest tests/ -m "not e2e"`; add `DATABASE_URL=… pytest -m postgres` for the runtime-path test.
- **API-surface drift:** adding an IR field requires regenerating the `ir-types` baseline (`dazzle inspect api ir-types --write`) and a CHANGELOG entry (drift gate `tests/unit/test_api_surface_drift.py`).
- **Bump on every fix** then `/ship` (clean worktree after push).

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `src/dazzle/core/ir/workspaces.py` | `WorkspaceSpec.live` IR field | Modify |
| `src/dazzle/core/dsl_parser_impl/workspace.py` | `live: on` keyword parse | Modify |
| `src/dazzle/back/runtime/sse_wiring.py` | Build + register nudge-publishing lifecycle callbacks | **Create** |
| `src/dazzle/back/runtime/server.py` | Call sse-wiring; mount SSE manager + routes when any workspace is live | Modify |
| `src/dazzle/back/runtime/sse_stream.py` | `/events` derives tenant from request (hardening) | Modify |
| `src/dazzle/ui/runtime/workspace_renderer.py` | Populate `WorkspaceContext.sse_url` when `live` | Modify |
| `examples/ops_dashboard/dsl/*.dsl` | Exercise `live: on` (coverage) | Modify |
| `docs/reference/grammar.md`, `CHANGELOG.md` | Docs + drift | Modify |
| `tests/unit/test_workspace_live_push_1399.py` | Unit tests for parser/IR/wiring/renderer | **Create** |
| `tests/integration/test_sse_live_push_pg.py` | Runtime-path postgres test | **Create** |

---

### Task 1: IR field `WorkspaceSpec.live`

**Files:**
- Modify: `src/dazzle/core/ir/workspaces.py` (WorkspaceSpec model, ~line 1270-1313)
- Test: `tests/unit/test_workspace_live_push_1399.py` (create)

**Interfaces:**
- Produces: `WorkspaceSpec.live: bool` (default `False`), a frozen-model field readable by the parser and renderer.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_workspace_live_push_1399.py
"""#1399 slice 1 — workspace SSE live push (IR + parser + wiring + renderer)."""
from dazzle.core.ir.workspaces import WorkspaceSpec


class TestWorkspaceLiveIR:
    def test_live_defaults_false(self) -> None:
        ws = WorkspaceSpec(name="ops")
        assert ws.live is False

    def test_live_can_be_set(self) -> None:
        ws = WorkspaceSpec(name="ops", live=True)
        assert ws.live is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_workspace_live_push_1399.py::TestWorkspaceLiveIR -v`
Expected: FAIL — `WorkspaceSpec` has no `live` field (`ValidationError: unexpected keyword`/`AttributeError`).

- [ ] **Step 3: Add the field**

In `src/dazzle/core/ir/workspaces.py`, in the `WorkspaceSpec` field block (next to `nav_ref: str | None = None`), add:

```python
    live: bool = False  # #1399 slice 1 — SSE live push (poll retained as fallback)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_workspace_live_push_1399.py::TestWorkspaceLiveIR -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Regenerate the ir-types baseline**

Run: `dazzle inspect api ir-types --write`
Then confirm the drift gate is green:
Run: `pytest tests/unit/test_api_surface_drift.py -q`
Expected: PASS. (The CHANGELOG entry lands in Task 7.)

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/ir/workspaces.py tests/unit/test_workspace_live_push_1399.py docs/api-surface/
git commit -m "feat(ir): add WorkspaceSpec.live for SSE live push (#1399)"
```

---

### Task 2: Parser — `live: on` keyword

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/workspace.py` (workspace-body keyword dispatch + `WorkspaceSpec(...)` construction)
- Modify: `docs/reference/grammar.md` (workspace keyword list)
- Test: `tests/unit/test_workspace_live_push_1399.py`

**Interfaces:**
- Consumes: `WorkspaceSpec.live` (Task 1).
- Produces: DSL `live: on` / `live: off` → `WorkspaceSpec.live`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/unit/test_workspace_live_push_1399.py
from dazzle.core.dsl_parser import parse_dsl  # adjust to the project's parse entrypoint


_LIVE_DSL = """
module demo
app demo "Demo"

entity Job "Job":
  id: uuid pk
  status: str(20) = "queued"

workspace ops "Ops":
  live: on
  region jobs:
    source: Job
    refresh: every 10s
"""

_NOLIVE_DSL = _LIVE_DSL.replace("  live: on\n", "")


class TestWorkspaceLiveParse:
    def test_live_on_sets_flag(self) -> None:
        spec = parse_dsl(_LIVE_DSL)
        ws = next(w for w in spec.workspaces if w.name == "ops")
        assert ws.live is True

    def test_absent_live_defaults_false(self) -> None:
        spec = parse_dsl(_NOLIVE_DSL)
        ws = next(w for w in spec.workspaces if w.name == "ops")
        assert ws.live is False
```

> Implementer note: confirm the real parse entrypoint with
> `grep -rn "def parse_dsl\|def parse(" src/dazzle/core/dsl_parser*.py` and match the
> existing workspace tests' import (`tests/unit/test_workspace_live_refresh_1391.py`
> shows the canonical helper). Use that helper, not a guessed name.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_workspace_live_push_1399.py::TestWorkspaceLiveParse -v`
Expected: FAIL — `live` keyword unrecognized, `ws.live` stays `False` for the `on` case (assert fails).

- [ ] **Step 3: Parse the keyword**

In `src/dazzle/core/dsl_parser_impl/workspace.py`, locate the workspace-body keyword dispatch chain (the `elif key == ...` ladder that handles `nav_ref`, `context_selector`, etc.) and the `WorkspaceSpec(...)` construction. Add a boolean accumulator and keyword branch mirroring existing boolean handling:

```python
# near where other workspace-body flags are initialised
live = False
...
# in the elif ladder
            elif key == "live":
                # #1399 slice 1 — `live: on` enables SSE push; on/true/yes accepted
                live = str(value).strip().lower() in ("on", "true", "yes", "1")
```

Then thread it into the `WorkspaceSpec(...)` constructor call:

```python
        return WorkspaceSpec(
            name=...,
            # ... existing kwargs ...
            live=live,
        )
```

> Implementer note: `value` shape depends on the tokenizer. Match how an adjacent
> boolean/simple keyword in this same function reads its value (grep the function for
> `elif key ==` and copy the value-extraction idiom).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_workspace_live_push_1399.py::TestWorkspaceLiveParse -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Update grammar reference**

In `docs/reference/grammar.md`, add `live: on` to the workspace-body keyword documentation alongside `refresh`. Then run the docs-drift gate:
Run: `pytest tests/unit/test_docs_drift.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/dsl_parser_impl/workspace.py docs/reference/grammar.md tests/unit/test_workspace_live_push_1399.py
git commit -m "feat(parser): live: on workspace keyword (#1399)"
```

---

### Task 3: SSE nudge-publishing callbacks (`sse_wiring.py`)

**Files:**
- Create: `src/dazzle/back/runtime/sse_wiring.py`
- Test: `tests/unit/test_workspace_live_push_1399.py`

**Interfaces:**
- Consumes: the framework `EventBus` (`dazzle.back.events.bus.EventBus`) with `async publish(topic, envelope)`; `EventEnvelope.create(event_type, key, payload, *, headers, producer)`; `CRUDService.on_created/on_updated/on_deleted(cb)` where `cb(entity_name: str, entity_id: str, entity_data: dict, old_data: dict | None)`.
- Produces: `register_sse_callbacks(services: dict[str, Any], bus: EventBus) -> int` — registers nudge publishers on every `CRUDService`, returns the count wired. Publishes to topics `entity.created` / `entity.updated` / `entity.deleted` with `event_type` matching the topic (so `SSEStreamManager.STREAM_TOPICS` routes it and the SSE `event:` field equals the client trigger name `entity.<action>`).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/unit/test_workspace_live_push_1399.py
import asyncio
from types import SimpleNamespace


class _RecordingBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, object]] = []

    async def publish(self, topic, envelope, *, transactional: bool = False) -> None:
        self.published.append((topic, envelope))


class _FakeCRUDService:
    """Mimics the on_created/on_updated/on_deleted registration surface."""
    def __init__(self, entity_name: str) -> None:
        self.entity_name = entity_name
        self._created: list = []
        self._updated: list = []
        self._deleted: list = []

    def on_created(self, cb) -> None: self._created.append(cb)
    def on_updated(self, cb) -> None: self._updated.append(cb)
    def on_deleted(self, cb) -> None: self._deleted.append(cb)


class TestSseWiring:
    def test_created_callback_publishes_nudge(self) -> None:
        from dazzle.back.runtime.sse_wiring import register_sse_callbacks

        bus = _RecordingBus()
        svc = _FakeCRUDService("Job")
        # register_sse_callbacks must treat any object with on_created/on_updated/
        # on_deleted + entity_name as a target (it filters on CRUDService in prod
        # via isinstance; the unit test injects a duck-typed double through the
        # `_is_target` seam — see Step 3).
        n = register_sse_callbacks({"Job": svc}, bus, _is_target=lambda s: True)
        assert n == 1

        cb = svc._created[0]
        asyncio.run(cb("Job", "abc-123", {"id": "abc-123", "tenant_id": "t1"}, None))

        assert len(bus.published) == 1
        topic, env = bus.published[0]
        assert topic == "entity.created"
        assert env.event_type == "entity.created"
        assert env.key == "abc-123"
        assert env.headers.get("tenant_id") == "t1"
        # Nudge-only: no row field data beyond identity.
        assert set(env.payload) <= {"entity", "id"}
        assert env.payload["entity"] == "Job"

    def test_no_bus_wires_nothing(self) -> None:
        from dazzle.back.runtime.sse_wiring import register_sse_callbacks
        svc = _FakeCRUDService("Job")
        assert register_sse_callbacks({"Job": svc}, None, _is_target=lambda s: True) == 0
        assert svc._created == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_workspace_live_push_1399.py::TestSseWiring -v`
Expected: FAIL — `sse_wiring` module does not exist (ImportError).

- [ ] **Step 3: Implement `sse_wiring.py`**

```python
# src/dazzle/back/runtime/sse_wiring.py
"""#1399 slice 1 — SSE live-push nudge wiring.

Registers entity-lifecycle callbacks on every CRUDService that publish a
*nudge* (entity name + id + tenant, no row data) to the framework EventBus on
the canonical ``entity.{created,updated,deleted}`` topics. The already-built
SSEStreamManager subscribes to those topics and forwards them to connected
browsers, whose cards re-fetch via their existing scope-gated endpoints.

Mirrors the audit/notification/job wiring pattern (``audit_wiring.py``).
"""

import logging
from collections.abc import Callable
from typing import Any

from dazzle.back.events.envelope import EventEnvelope

logger = logging.getLogger("dazzle.server")

# action -> canonical topic / event_type. Matches SSEStreamManager.STREAM_TOPICS
# (StreamType.EVENTS) AND the client `sse:entity.<action>` trigger names.
_TOPICS = {
    "created": "entity.created",
    "updated": "entity.updated",
    "deleted": "entity.deleted",
}


def _default_is_target(service: Any) -> bool:
    from dazzle.back.runtime.service_generator import CRUDService

    return isinstance(service, CRUDService)


def _make_nudge_callback(bus: Any, action: str) -> Callable[..., Any]:
    topic = _TOPICS[action]

    async def _publish_nudge(
        entity_name: str,
        entity_id: str,
        entity_data: dict[str, Any],
        old_data: dict[str, Any] | None,
    ) -> None:
        tenant_id = (entity_data or {}).get("tenant_id")
        headers = {"tenant_id": str(tenant_id)} if tenant_id else {}
        envelope = EventEnvelope.create(
            event_type=topic,
            key=str(entity_id),
            payload={"entity": entity_name, "id": str(entity_id)},
            headers=headers,
            producer="dazzle.ui.live",
        )
        try:
            await bus.publish(topic, envelope)
        except Exception as exc:  # nudge delivery must never break a mutation
            logger.warning("SSE nudge publish failed for %s.%s: %s", entity_name, action, exc)

    return _publish_nudge


def register_sse_callbacks(
    services: dict[str, Any],
    bus: Any | None,
    *,
    _is_target: Callable[[Any], bool] = _default_is_target,
) -> int:
    """Register nudge publishers on every CRUD service. Returns count wired."""
    if bus is None:
        return 0
    wired = 0
    for service in services.values():
        if not _is_target(service):
            continue
        service.on_created(_make_nudge_callback(bus, "created"))
        service.on_updated(_make_nudge_callback(bus, "updated"))
        service.on_deleted(_make_nudge_callback(bus, "deleted"))
        wired += 1
    if wired:
        logger.info("SSE live push: wired nudge callbacks on %d services", wired)
    return wired
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_workspace_live_push_1399.py::TestSseWiring -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Lint + type**

Run: `ruff check src/dazzle/back/runtime/sse_wiring.py --fix && mypy src/dazzle/back/runtime/sse_wiring.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/back/runtime/sse_wiring.py tests/unit/test_workspace_live_push_1399.py
git commit -m "feat(runtime): SSE nudge-publish lifecycle callbacks (#1399)"
```

---

### Task 4: Wire callbacks + mount SSE routes in `server.py`

**Files:**
- Modify: `src/dazzle/back/runtime/server.py` (the `CRUDService` wiring loop ~line 1232-1255; the router-mount region ~line 1540)
- Modify: `src/dazzle/back/runtime/sse_stream.py` (`/events` endpoint: prefer request-resolved tenant)
- Test: `tests/unit/test_workspace_live_push_1399.py`

**Interfaces:**
- Consumes: `register_sse_callbacks` (Task 3); `WorkspaceSpec.live` (Task 1); `SSEStreamManager`, `create_sse_routes` (`sse_stream.py`); `app.state.services.event_framework` (set by `EventsSubsystem`).
- Produces: when `any(ws.live for ws in appspec.workspaces)` and a bus exists — nudge callbacks registered, an `SSEStreamManager` started via lifespan, and the `/_ops/sse/events` router mounted.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/unit/test_workspace_live_push_1399.py
class TestSseMountGate:
    def test_any_live_predicate(self) -> None:
        from dazzle.back.runtime.server import _any_workspace_live  # helper added in Step 3

        live = [SimpleNamespace(live=True), SimpleNamespace(live=False)]
        none = [SimpleNamespace(live=False)]
        assert _any_workspace_live(live) is True
        assert _any_workspace_live(none) is False
        assert _any_workspace_live([]) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_workspace_live_push_1399.py::TestSseMountGate -v`
Expected: FAIL — `_any_workspace_live` not defined (ImportError).

- [ ] **Step 3: Add the predicate + wiring + mount**

In `src/dazzle/back/runtime/server.py`, add the module-level helper:

```python
def _any_workspace_live(workspaces: list[Any]) -> bool:
    """#1399 — True if any workspace opted into SSE live push."""
    return any(getattr(ws, "live", False) for ws in workspaces)
```

After the audit/job/notification wiring block (right after `register_audit_callbacks(...)`, ~line 1255), register the SSE nudge callbacks:

```python
        # #1399 slice 1 — SSE live push. Wire nudge publishers only when a
        # workspace opted in and a framework bus exists.
        if _any_workspace_live(list(self._appspec.workspaces)):
            services_state = getattr(self._app.state, "services", None)
            framework = getattr(services_state, "event_framework", None)
            bus = framework.get_bus() if framework is not None else None
            if bus is not None:
                from dazzle.back.runtime.sse_wiring import register_sse_callbacks

                register_sse_callbacks(self._services, bus)
                self._sse_bus = bus  # stash for the mount step below
            else:
                logger.warning("Workspace declares live: on but no event bus is available")
```

In the router-mount region (near the existing `self._app.include_router(...)` calls, ~line 1540), mount the SSE manager + routes against the stashed bus:

```python
        # #1399 slice 1 — mount the SSE stream platform (independent of the ops
        # dashboard) when a workspace is live and a bus was wired above.
        sse_bus = getattr(self, "_sse_bus", None)
        if sse_bus is not None:
            from dazzle.back.runtime.lifespan_hooks import register_lifespan_hook
            from dazzle.back.runtime.sse_stream import SSEStreamManager, create_sse_routes

            sse_manager = SSEStreamManager(event_bus=sse_bus)
            self._app.include_router(create_sse_routes(sse_manager))

            async def _start_sse() -> None:
                await sse_manager.start()

            async def _stop_sse() -> None:
                await sse_manager.stop()

            register_lifespan_hook(self._app, startup=_start_sse, shutdown=_stop_sse)
```

> Implementer note: confirm `EventFramework.get_bus()` returns the bus (it does —
> `framework.py:161`). If `get_bus()` returns `None` before `start()`, stash the
> framework instead and resolve `.bus` inside `_start_sse` (the framework's start
> hook runs before the SSE start hook because it is registered earlier by
> `EventsSubsystem`). Verify ordering with the integration test in Task 6 before
> finalising; adjust to stash the framework if delivery fails.

- [ ] **Step 4: Harden the `/events` tenant filter**

In `src/dazzle/back/runtime/sse_stream.py`, the `/events` endpoint currently trusts the `tenant_id` query param. Prefer a request-resolved tenant when present (TenantResolutionMiddleware sets `request.state.tenant_id`), falling back to the query param:

```python
    @router.get("/events")
    async def stream_events(
        request: Request,
        entity: str | None = Query(None, description="Filter by entity name"),
        tenant_id: str | None = Query(None, description="Filter by tenant ID"),
        last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        resolved_tenant = getattr(request.state, "tenant_id", None) or tenant_id
        sub_id = stream_manager.create_subscription(
            stream_type=StreamType.EVENTS,
            entity_filter=entity,
            tenant_id=resolved_tenant,
            last_event_id=last_event_id,
        )
        # ... existing StreamingResponse(...) unchanged ...
```

> Do NOT add `from __future__ import annotations` to this file (ADR-0014).

- [ ] **Step 5: Run the test + lint/type**

Run: `pytest tests/unit/test_workspace_live_push_1399.py::TestSseMountGate -v`
Expected: PASS.
Run: `ruff check src/dazzle/back/runtime/server.py src/dazzle/back/runtime/sse_stream.py --fix && mypy src/dazzle`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/back/runtime/server.py src/dazzle/back/runtime/sse_stream.py tests/unit/test_workspace_live_push_1399.py
git commit -m "feat(runtime): wire + mount SSE live push when a workspace is live (#1399)"
```

---

### Task 5: Renderer — populate `WorkspaceContext.sse_url` when live

**Files:**
- Modify: `src/dazzle/ui/runtime/workspace_renderer.py` (`build_workspace_context`, the `WorkspaceContext(...)` return at ~line 741)
- Test: `tests/unit/test_workspace_live_push_1399.py`

**Interfaces:**
- Consumes: `WorkspaceSpec.live` (Task 1).
- Produces: `WorkspaceContext.sse_url == "/_ops/sse/events"` when the spec is live, else `""`. This flips the already-wired `sse_enabled=bool(workspace.sse_url)` path (line 928) and `DashboardGrid(sse_url=...)` (line 975) on.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/unit/test_workspace_live_push_1399.py
class TestRendererSseUrl:
    def _ctx_for(self, dsl: str):
        from dazzle.ui.runtime.workspace_renderer import build_workspace_context
        spec = parse_dsl(dsl)
        ws = next(w for w in spec.workspaces if w.name == "ops")
        return build_workspace_context(ws, spec)

    def test_live_populates_sse_url(self) -> None:
        ctx = self._ctx_for(_LIVE_DSL)
        assert ctx.sse_url == "/_ops/sse/events"

    def test_not_live_leaves_sse_url_empty(self) -> None:
        ctx = self._ctx_for(_NOLIVE_DSL)
        assert ctx.sse_url == ""
```

> Implementer note: confirm `build_workspace_context`'s exact parameter names/order
> with `sed -n '444,470p' src/dazzle/ui/runtime/workspace_renderer.py` and adjust the
> call (`build_workspace_context(ws, spec)`) to match.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_workspace_live_push_1399.py::TestRendererSseUrl -v`
Expected: FAIL — `sse_url` is `""` even when live.

- [ ] **Step 3: Populate `sse_url` in the builder**

In `build_workspace_context`, in the `WorkspaceContext(...)` return (~line 741), add:

```python
        sse_url="/_ops/sse/events" if getattr(workspace, "live", False) else "",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_workspace_live_push_1399.py::TestRendererSseUrl -v`
Expected: PASS.

- [ ] **Step 5: Confirm the client half activates (no `_render_dashboard.py` change)**

Run: `pytest tests/unit/test_workspace_live_refresh_1391.py -q`
Expected: PASS (no regression — the dashboard renderer already emits `sse-connect` + `sse:entity.*` when `sse_enabled`).

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/ui/runtime/workspace_renderer.py tests/unit/test_workspace_live_push_1399.py
git commit -m "feat(ui): populate sse_url when workspace is live (#1399)"
```

---

### Task 6: Runtime-path integration test (postgres-marked)

**Files:**
- Create: `tests/integration/test_sse_live_push_pg.py`

**Interfaces:**
- Consumes: the full booted runtime — `CRUDService.create` → nudge callback → `bus.publish("entity.created", …)` → `SSEStreamManager` → `/_ops/sse/events` SSE frame.

This is the load-bearing test: the unit tests prove each link in isolation; only this proves the bus→SSE delivery chain actually flows end-to-end (lesson: *verify the runtime path, not just the unit*).

- [ ] **Step 1: Write the test**

```python
# tests/integration/test_sse_live_push_pg.py
"""#1399 slice 1 — end-to-end: entity mutation -> SSE frame. Postgres-marked."""
import asyncio

import pytest

pytestmark = pytest.mark.postgres


@pytest.mark.asyncio
async def test_mutation_emits_entity_sse_frame(live_app_with_pg) -> None:
    """A create on a live workspace's entity yields an `entity.created` SSE frame.

    `live_app_with_pg` is a fixture that boots a DazzleServer for a small DSL with
    `workspace ops: live: on` + `entity Job`, against the test Postgres DSN, and
    yields (app, services, base_url). Reuse the existing booted-app integration
    fixture pattern from tests/integration/ (e.g. test_scope_runtime_pg.py).
    """
    app, services, client = live_app_with_pg

    # Open the SSE stream, then mutate, then read the first data frame.
    async with client.stream("GET", "/_ops/sse/events") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        job_service = services["Job"]
        await job_service.create({"status": "queued"})

        frame = await asyncio.wait_for(_first_event(resp), timeout=5.0)
        assert "event: entity.created" in frame


async def _first_event(resp) -> str:
    buf = ""
    async for line in resp.aiter_lines():
        buf += line + "\n"
        if line == "" and "event:" in buf:  # SSE frames end on a blank line
            return buf
    return buf
```

> Implementer note: wire `live_app_with_pg` by copying the booted-app fixture used in
> `tests/integration/test_scope_runtime_pg.py` and pointing it at a 1-entity,
> 1-live-workspace DSL. If the bus relay needs a poll tick, the 5s timeout absorbs it;
> if delivery never arrives, that confirms the Task 4 ordering note (stash the
> framework and resolve `.bus` in the SSE start hook) — fix there, not here.

- [ ] **Step 2: Run the test against Postgres**

Run: `DATABASE_URL="$TEST_DATABASE_URL" pytest tests/integration/test_sse_live_push_pg.py -m postgres -v`
Expected: PASS. If it FAILS on delivery (timeout), apply the Task 4 ordering fix and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_sse_live_push_pg.py
git commit -m "test(integration): SSE live-push runtime path (#1399)"
```

---

### Task 7: Example coverage, CHANGELOG, docs, ship

**Files:**
- Modify: `examples/ops_dashboard/dsl/*.dsl` (add `live: on` to one workspace)
- Modify: `CHANGELOG.md`, `docs/reference/reports.md` or `grammar.md` cross-ref as needed
- Modify: version files (via `/bump`)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Wire `live: on` into an example**

In `examples/ops_dashboard` find the dashboard workspace and add `live: on` under the workspace header (a workspace whose regions already use `refresh: every Ns` is ideal so push + heartbeat coexist). Then validate:

Run: `cd examples/ops_dashboard && dazzle validate`
Expected: PASS, no new lint errors.

- [ ] **Step 2: Confirm boot + route presence (local)**

Run: `cd examples/ops_dashboard && dazzle serve --local` (or the project's standard boot-check), then confirm `/_ops/sse/events` is mounted (e.g. `curl -sI localhost:8000/_ops/sse/events` returns `200` / `text/event-stream`). Stop the server.

> If the project has a fuzz/boot-stderr check (`/fuzz`), run it for ops_dashboard to
> confirm no duplicate-route or boot regression.

- [ ] **Step 3: Add CHANGELOG entry**

Under `## [Unreleased]`, add an `### Added` bullet describing workspace SSE live push (`live: on`), the nudge-only design, the poll-as-fallback relationship, and an `### Agent Guidance` note: *"SSE live push is nudge-only — events carry no row data; cards re-fetch via the scope-gated endpoint. Enable per-workspace with `live: on`; the `refresh: every Ns` poll is retained as a fallback heartbeat."* Note the `ir-types` baseline change under the same entry.

- [ ] **Step 4: Full pre-ship gates**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`
Run: `mypy src/dazzle`
Run: `pytest tests/ -m "not e2e" -q`
Run: `DATABASE_URL="$TEST_DATABASE_URL" pytest -m postgres -q`
Expected: all green.

- [ ] **Step 5: Bump + ship**

Run `/bump patch`, then `/ship` (commits, tags, pushes — triggers PyPI + Homebrew). Confirm clean worktree after.

---

## Self-Review

**Spec coverage:**
- Nudge-only signal → Task 3 (payload = entity+id only; tenant in header). ✓
- Explicit `live: on` opt-in → Tasks 1, 2. ✓
- SSE supersedes poll, poll retained as fallback → Task 5 (sse_url flips client triggers on; card keeps `every Ns`); confirmed by Task 5 Step 5. ✓
- Reuse framework bus + existing `/_ops/sse/events` → Tasks 3, 4. ✓
- Gap 1 (no `sse_url` field/flag) → Tasks 1, 5. ✓
- Gap 2 (SSE never mounted) → Task 4 (mount independent of ops). ✓
- Gap 3 (CRUDService emits nothing) → Tasks 3, 4. ✓
- Gap 4 (topic mismatch) → resolved by design: publish to canonical `entity.<action>` topics with matching `event_type` (Task 3); no remap needed. ✓
- Tenancy / RBAC → Task 4 Step 4 (request-resolved tenant) + nudge-only re-fetch is scope-gated. ✓
- Testing incl. mandatory runtime-path test → Task 6. ✓
- Out-of-scope (bus consolidation, payload SSE, surface SSE) → not built. ✓

**Placeholder scan:** No TBD/TODO; every code step shows code; implementer notes point to exact grep/`sed` commands to confirm local idioms rather than guessing. ✓

**Type consistency:** `register_sse_callbacks(services, bus, *, _is_target)` signature identical across Tasks 3 and 4. Callback shape `(entity_name, entity_id, entity_data, old_data)` matches `service_generator.py:_notify_callbacks` (line 173). Topic/event_type strings (`entity.created/updated/deleted`) consistent across Tasks 3, 4, 6 and match `SSEStreamManager.STREAM_TOPICS` + client `sse:entity.*` triggers. `WorkspaceContext.sse_url` (str) matches the field at `workspace_renderer.py:256`. ✓

## Open risk carried into execution

The framework `EventBus.get_bus()` may return `None` until `framework.start()` runs. Task 4's mount registers the SSE start hook *after* `EventsSubsystem`'s framework start hook, so ordering should hold — but Task 6's integration test is the gate that proves delivery. If it times out, switch Task 4 to stash the framework and resolve `.bus` inside `_start_sse`. This is called out inline in Tasks 4 and 6.
