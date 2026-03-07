"""Tests for NullBus and NullEventFramework no-op implementations."""

import pytest

from dazzle_back.events.bus import NackReason
from dazzle_back.events.envelope import EventEnvelope
from dazzle_back.events.null import NullBus, NullEventFramework


@pytest.fixture
def bus():
    return NullBus()


@pytest.fixture
def framework():
    return NullEventFramework()


# --- NullBus ---


async def test_null_bus_publish(bus):
    envelope = EventEnvelope.create("app.Order.created", key="1", payload={"id": "1"})
    await bus.publish("app.Order", envelope)


async def test_null_bus_subscribe(bus):
    async def handler(e):
        pass

    info = await bus.subscribe("app.Order", "group-1", handler)
    assert info.topic == "app.Order"
    assert info.group_id == "group-1"


async def test_null_bus_unsubscribe(bus):
    await bus.unsubscribe("app.Order", "group-1")


async def test_null_bus_ack(bus):
    from uuid import uuid4

    await bus.ack("app.Order", "group-1", uuid4())


async def test_null_bus_nack(bus):
    from uuid import uuid4

    reason = NackReason.transient_error("test")
    await bus.nack("app.Order", "group-1", uuid4(), reason)


async def test_null_bus_replay_yields_nothing(bus):
    events = [e async for e in bus.replay("app.Order")]
    assert events == []


async def test_null_bus_list_topics(bus):
    assert await bus.list_topics() == []


async def test_null_bus_list_consumer_groups(bus):
    assert await bus.list_consumer_groups("app.Order") == []


async def test_null_bus_get_consumer_status(bus):
    status = await bus.get_consumer_status("app.Order", "group-1")
    assert status.pending_count == 0
    assert status.last_offset == 0


async def test_null_bus_get_topic_info(bus):
    info = await bus.get_topic_info("app.Order")
    assert info["event_count"] == 0


# --- NullEventFramework ---


async def test_null_framework_start_stop(framework):
    await framework.start()
    await framework.stop()


async def test_null_framework_context_manager(framework):
    async with framework as f:
        assert f is framework


async def test_null_framework_emit_noop(framework):
    envelope = EventEnvelope.create("app.Order.created", key="1", payload={"id": "1"})
    await framework.emit_event(None, envelope)


async def test_null_framework_health_check(framework):
    health = await framework.health_check()
    assert health["tier"] == "null"
    assert health["bus_type"] == "NullBus"


async def test_null_framework_get_status(framework):
    status = await framework.get_status()
    assert status["is_running"] is False
    assert status["events_published"] == 0


async def test_null_framework_bus_property(framework):
    assert isinstance(framework.bus, NullBus)


async def test_null_framework_outbox_stats(framework):
    stats = await framework.get_outbox_stats()
    assert stats["pending"] == 0


async def test_null_framework_recent_outbox_entries(framework):
    entries = await framework.get_recent_outbox_entries()
    assert entries == []


async def test_null_framework_is_not_running(framework):
    assert framework.is_running is False
