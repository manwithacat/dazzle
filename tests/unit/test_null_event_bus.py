"""Tests for NullBus and NullEventFramework no-op implementations."""

from uuid import uuid4

import pytest

from dazzle.http.events.bus import NackReason
from dazzle.http.events.envelope import EventEnvelope
from dazzle.http.events.null import NullBus, NullEventFramework


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
    await bus.ack("app.Order", "group-1", uuid4())


async def test_null_bus_nack(bus):
    reason = NackReason.transient_error("test")
    await bus.nack("app.Order", "group-1", uuid4(), reason)


async def test_null_bus_read_methods_yield_empty(bus):
    """Combined: replay, list_topics, list_consumer_groups, get_consumer_status, get_topic_info
    all return the empty/zero shape on a NullBus."""
    # replay yields nothing
    assert [e async for e in bus.replay("app.Order")] == []

    # list_topics empty
    assert await bus.list_topics() == []

    # list_consumer_groups empty
    assert await bus.list_consumer_groups("app.Order") == []

    # get_consumer_status returns zero counts
    status = await bus.get_consumer_status("app.Order", "group-1")
    assert status.pending_count == 0
    assert status.last_offset == 0

    # get_topic_info returns zero events
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
