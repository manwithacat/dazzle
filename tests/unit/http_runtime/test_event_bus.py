"""
Tests for entity event bus.

Tests event emission and handler registration.
"""

from typing import Any

import pytest

from dazzle.http.runtime.event_bus import EntityEventBus, EntityEventType


@pytest.fixture
def event_bus() -> Any:
    """Create a fresh event bus for testing."""
    return EntityEventBus()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("emit", "kwargs", "event_type", "data", "user_id"),
    [
        pytest.param(
            "emit_created",
            {"data": {"title": "Test"}, "user_id": "user_456"},
            EntityEventType.CREATED,
            {"title": "Test"},
            "user_456",
            id="created",
        ),
        pytest.param(
            "emit_updated",
            {"data": {"title": "Updated"}},
            EntityEventType.UPDATED,
            {"title": "Updated"},
            None,
            id="updated",
        ),
        pytest.param("emit_deleted", {}, EntityEventType.DELETED, None, None, id="deleted-no-data"),
    ],
)
async def test_emit_delivers_one_event(
    event_bus: Any, emit: str, kwargs: dict, event_type: Any, data: Any, user_id: Any
) -> None:
    events: list[Any] = []

    async def handler(event: Any) -> None:
        events.append(event)

    event_bus.add_handler(handler)
    await getattr(event_bus, emit)(entity_name="Task", entity_id="123", **kwargs)

    assert len(events) == 1
    event = events[0]
    assert (event.event_type, event.entity_name, event.entity_id) == (event_type, "Task", "123")
    assert (event.data, event.user_id) == (data, user_id)
    assert event.timestamp > 0


@pytest.mark.asyncio
async def test_every_async_and_sync_handler_is_called(event_bus: Any) -> None:
    calls: list[str] = []

    async def first(event: Any) -> None:
        calls.append("async-1")

    async def second(event: Any) -> None:
        calls.append("async-2")

    def sync(event: Any) -> None:
        calls.append("sync")

    event_bus.add_handler(first)
    event_bus.add_handler(second)
    event_bus.add_sync_handler(sync)

    await event_bus.emit_created("Task", "123", {"title": "Test"})

    assert sorted(calls) == ["async-1", "async-2", "sync"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["async", "sync"])
async def test_failing_handler_does_not_stop_others(event_bus: Any, kind: str) -> None:
    events: list[Any] = []

    def failing_sync(event: Any) -> None:
        raise ValueError("Handler failed")

    def working_sync(event: Any) -> None:
        events.append(event)

    async def failing_async(event: Any) -> None:
        failing_sync(event)

    async def working_async(event: Any) -> None:
        working_sync(event)

    if kind == "async":
        event_bus.add_handler(failing_async)
        event_bus.add_handler(working_async)
    else:
        event_bus.add_sync_handler(failing_sync)
        event_bus.add_sync_handler(working_sync)

    await event_bus.emit_created("Task", "123", {})  # must not raise

    assert len(events) == 1
