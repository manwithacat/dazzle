"""#1852: without REDIS_URL, framework handlers are delivered in-process.

The null tier used to drop every publish, so an ``auth.user.registered``
handler never ran on a Redis-less deployment. The topic was also the event
type minus its action, so a handler keyed on the full type never matched even
with Redis. ``register_handler(event_type=...)`` now subscribes on the derived
topic and filters; on the null tier ``EventFramework.publish`` calls the
registered handlers (inbox-deduped) directly.
"""

from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from dazzle.http.events.envelope import EventEnvelope
from dazzle.http.events.framework import EventFramework, EventFrameworkConfig
from dazzle.http.events.null import NullBus
from dazzle.http.runtime.auth.events import configure_auth_events, emit_user_registered
from dazzle.http.runtime.auth.models import UserRecord


class _MemoryInbox:
    """Inbox stand-in: remembers (event_id, consumer) pairs it has processed."""

    def __init__(self) -> None:
        self.seen: set[tuple[UUID, str]] = set()

    async def create_table(self, conn: Any) -> None:
        pass

    async def should_process(self, conn: Any, event_id: UUID, consumer: str) -> bool:
        return (event_id, consumer) not in self.seen

    async def mark_processed(self, conn: Any, event_id: UUID, consumer: str, **_: Any) -> None:
        self.seen.add((event_id, consumer))


async def _started(redis_url: str | None = None) -> EventFramework:
    """A framework past ``_start_consumers`` without a database or Redis."""
    fw = EventFramework(
        EventFrameworkConfig(database_url="postgresql://unused/db", redis_url=redis_url)
    )
    fw._make_connect_fn = lambda: AsyncMock(return_value=AsyncMock())  # type: ignore[method-assign]
    fw._inbox = _MemoryInbox()  # type: ignore[assignment]
    fw._bus = NullBus() if redis_url is None else AsyncMock()
    return fw


def _envelope(event_type: str) -> EventEnvelope:
    return EventEnvelope.create(event_type=event_type, key="k", payload={})


@pytest.mark.asyncio
async def test_event_type_handler_runs_in_process_without_redis() -> None:
    fw = await _started()
    got: list[str] = []
    other: list[str] = []
    every: list[str] = []

    async def on_registered(e: EventEnvelope) -> None:
        got.append(e.event_type)

    async def on_password(e: EventEnvelope) -> None:
        other.append(e.event_type)

    async def on_topic(e: EventEnvelope) -> None:
        every.append(e.event_type)

    fw.register_handler(None, "provision", on_registered, event_type="auth.user.registered")
    fw.register_handler(None, "pw", on_password, event_type="auth.user.password_changed")
    fw.register_handler("auth.user", "audit", on_topic)
    await fw._start_consumers()

    await fw.publish(_envelope("auth.user.registered"))
    await fw.publish(_envelope("auth.user.logged_in"))

    assert got == ["auth.user.registered"]
    assert other == []
    assert every == ["auth.user.registered", "auth.user.logged_in"]


@pytest.mark.asyncio
async def test_replayed_event_is_deduped_and_a_failing_handler_does_not_block_others() -> None:
    fw = await _started()
    calls: list[str] = []

    async def boom(e: EventEnvelope) -> None:
        raise RuntimeError("handler bug")

    async def ok(e: EventEnvelope) -> None:
        calls.append(e.event_type)

    fw.register_handler("auth.user", "boom", boom)
    fw.register_handler("auth.user", "ok", ok)
    await fw._start_consumers()

    envelope = _envelope("auth.user.registered")
    await fw.publish(envelope)
    await fw.publish(envelope)

    assert calls == ["auth.user.registered"]


@pytest.mark.asyncio
async def test_with_redis_publish_goes_to_the_bus_once() -> None:
    fw = await _started(redis_url="redis://unused")
    envelope = _envelope("auth.user.registered")
    await fw.publish(envelope)
    fw._bus.publish.assert_awaited_once_with("auth.user", envelope)  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_auth_emit_reaches_a_registered_handler_without_redis() -> None:
    fw = await _started()
    got: list[str] = []

    async def on_registered(e: EventEnvelope) -> None:
        got.append(e.payload["email"])

    fw.register_handler(None, "provision", on_registered, event_type="auth.user.registered")
    await fw._start_consumers()
    fw._stats.is_running = True
    configure_auth_events(fw)
    try:
        user = UserRecord(email="new@example.com", password_hash="x", username="New")
        await emit_user_registered(user)
    finally:
        configure_auth_events(None)

    assert got == ["new@example.com"]


def test_register_handler_rejects_a_topic_that_is_not_the_event_types() -> None:
    fw = EventFramework(EventFrameworkConfig())

    async def h(e: EventEnvelope) -> None:
        pass

    with pytest.raises(ValueError, match="publishes on topic 'auth.user'"):
        fw.register_handler("auth.user.registered", "g", h, event_type="auth.user.registered")
    with pytest.raises(ValueError, match="topic or an event_type"):
        fw.register_handler(None, "g", h)
