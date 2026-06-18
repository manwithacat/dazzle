"""#1399 slice 1 — workspace SSE live push (IR + parser + wiring + renderer)."""

from __future__ import annotations

from pathlib import Path

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

        from dazzle.back.runtime.sse_wiring import register_sse_callbacks

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

        from dazzle.back.runtime.sse_wiring import register_sse_callbacks

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
        from dazzle.back.runtime.sse_wiring import register_sse_callbacks

        svc = _FakeCRUDService("Job")
        assert register_sse_callbacks({"Job": svc}, None, _is_target=lambda s: True) == 0
        assert svc._created == []
