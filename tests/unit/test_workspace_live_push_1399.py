"""#1399 slice 1 — workspace SSE live push (IR + parser + wiring + renderer)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.workspaces import WorkspaceSpec


class TestWorkspaceLiveIR:
    def test_live_defaults_false(self) -> None:
        ws = WorkspaceSpec(name="ops")
        assert ws.live is False

    def test_live_can_be_set(self) -> None:
        ws = WorkspaceSpec(name="ops", live=True)
        assert ws.live is True


_LIVE_DSL = """module t
app t "Test"
entity Job "Job":
  id: uuid pk
  status: str(20) = "queued"
workspace ops "Ops":
  live: on
  jobs:
    source: Job
    display: list
    refresh: every 10s
"""

_NOLIVE_DSL = _LIVE_DSL.replace("  live: on\n", "")


def _workspace(dsl: str) -> WorkspaceSpec:
    module = parse_dsl(dsl, Path("test.dsl"))[5]
    return next(w for w in module.workspaces if w.name == "ops")


class TestWorkspaceLiveParse:
    def test_live_on_sets_flag(self) -> None:
        assert _workspace(_LIVE_DSL).live is True

    def test_absent_live_defaults_false(self) -> None:
        assert _workspace(_NOLIVE_DSL).live is False


# ─────────────────────────── sse_wiring ────────────────────────────


class _RecordingBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, object]] = []

    async def publish(self, topic: str, envelope: object, *, transactional: bool = False) -> None:
        self.published.append((topic, envelope))


class _FakeCRUDService:
    """Mimics the on_created/on_updated/on_deleted registration surface."""

    def __init__(self, entity_name: str) -> None:
        self.entity_name = entity_name
        self._created: list = []
        self._updated: list = []
        self._deleted: list = []

    def on_created(self, cb: object) -> None:
        self._created.append(cb)

    def on_updated(self, cb: object) -> None:
        self._updated.append(cb)

    def on_deleted(self, cb: object) -> None:
        self._deleted.append(cb)


class TestSseWiring:
    def test_created_callback_publishes_nudge(self) -> None:
        import asyncio

        from dazzle.http.runtime.sse_wiring import register_sse_callbacks

        bus = _RecordingBus()
        svc = _FakeCRUDService("Job")
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

    def test_updated_and_deleted_topics(self) -> None:
        import asyncio

        from dazzle.http.runtime.sse_wiring import register_sse_callbacks

        bus = _RecordingBus()
        svc = _FakeCRUDService("Job")
        register_sse_callbacks({"Job": svc}, bus, _is_target=lambda s: True)

        asyncio.run(svc._updated[0]("Job", "id2", {"id": "id2"}, {"id": "id2"}))
        asyncio.run(svc._deleted[0]("Job", "id3", {"id": "id3"}, None))
        topics = [t for t, _ in bus.published]
        assert topics == ["entity.updated", "entity.deleted"]
        # No tenant header when the row carries no tenant_id.
        assert bus.published[0][1].headers == {}

    def test_no_bus_wires_nothing(self) -> None:
        from dazzle.http.runtime.sse_wiring import register_sse_callbacks

        svc = _FakeCRUDService("Job")
        assert register_sse_callbacks({"Job": svc}, None, _is_target=lambda s: True) == 0
        assert svc._created == []


class TestLazyFrameworkBus:
    def test_publish_drops_when_bus_not_ready(self) -> None:
        import asyncio

        from dazzle.http.runtime.sse_wiring import LazyFrameworkBus

        framework = SimpleNamespace(get_bus=lambda: None)
        lazy = LazyFrameworkBus(framework)
        # No bus yet -> publish is a silent no-op (must not raise).
        asyncio.run(lazy.publish("entity.created", object()))

    def test_publish_delegates_when_bus_ready(self) -> None:
        import asyncio

        from dazzle.http.runtime.sse_wiring import LazyFrameworkBus

        real = _RecordingBus()
        framework = SimpleNamespace(get_bus=lambda: real)
        lazy = LazyFrameworkBus(framework)
        env = object()
        asyncio.run(lazy.publish("entity.created", env))
        assert real.published == [("entity.created", env)]

    def test_falls_back_to_bus_property_when_no_get_bus(self) -> None:
        # NullEventFramework exposes `.bus` (a no-op NullBus) but no get_bus().
        # The proxy must resolve via `.bus` instead of treating it as not-ready.
        import asyncio

        from dazzle.http.runtime.sse_wiring import LazyFrameworkBus

        real = _RecordingBus()
        framework = SimpleNamespace(bus=real)  # no get_bus attribute
        lazy = LazyFrameworkBus(framework)
        asyncio.run(lazy.publish("entity.updated", object()))
        assert real.published and real.published[0][0] == "entity.updated"


class TestRendererSseUrl:
    def _ctx(self, dsl: str) -> object:
        from dazzle.page.runtime.workspace_renderer import build_workspace_context

        module = parse_dsl(dsl, Path("test.dsl"))[5]
        ws = next(w for w in module.workspaces if w.name == "ops")
        # sse_url derives only from ws.live; app_spec (entity metadata) is irrelevant.
        return build_workspace_context(ws, None)

    def test_live_populates_sse_url(self) -> None:
        assert self._ctx(_LIVE_DSL).sse_url == "/_ops/sse/events"

    def test_not_live_leaves_sse_url_empty(self) -> None:
        assert self._ctx(_NOLIVE_DSL).sse_url == ""


class TestSseMountGate:
    def test_any_workspace_live(self) -> None:
        from dazzle.http.runtime.server import _any_workspace_live

        assert (
            _any_workspace_live([SimpleNamespace(live=True), SimpleNamespace(live=False)]) is True
        )
        assert _any_workspace_live([SimpleNamespace(live=False)]) is False
        assert _any_workspace_live([]) is False


class TestSseDeliveryIntegration:
    """Runtime-path: a real nudge envelope (from the actual lifecycle callback)
    routes through ``SSEStreamManager._handle_envelope`` to a subscriber's queue
    as an ``entity.created`` SSE frame, with tenant isolation.

    This connects the two halves we own — the publish-side nudge builder and the
    SSE routing/filtering — using the genuine envelope, not a mock. The bus
    transport itself (postgres LISTEN/NOTIFY) is covered by the events suite;
    our code is bus-transport-agnostic (publishes via the EventBus interface).
    """

    async def _nudge_envelope(self, tenant: str | None) -> object:
        from dazzle.http.runtime.sse_wiring import register_sse_callbacks

        bus = _RecordingBus()
        svc = _FakeCRUDService("Job")
        register_sse_callbacks({"Job": svc}, bus, _is_target=lambda s: True)
        await svc._created[0]("Job", "id-1", {"id": "id-1", "tenant_id": tenant}, None)
        return bus.published[0][1]

    async def test_nudge_reaches_matching_subscriber(self) -> None:
        from dazzle.http.runtime.sse_stream import SSEStreamManager, StreamType

        envelope = await self._nudge_envelope("t1")
        manager = SSEStreamManager(event_bus=_RecordingBus())
        sub_id = manager.create_subscription(stream_type=StreamType.EVENTS, tenant_id="t1")

        await manager._handle_envelope(envelope)

        msg = manager._queues[sub_id].get_nowait()
        assert msg.event == "entity.created"  # matches the client `sse:entity.created` trigger
        assert msg.data.get("entity") == "Job"

    async def test_nudge_isolated_across_tenants(self) -> None:
        from dazzle.http.runtime.sse_stream import SSEStreamManager, StreamType

        envelope = await self._nudge_envelope("t1")
        manager = SSEStreamManager(event_bus=_RecordingBus())
        other = manager.create_subscription(stream_type=StreamType.EVENTS, tenant_id="t2")

        await manager._handle_envelope(envelope)

        assert manager._queues[other].empty()  # t2 must not receive t1's nudge
