"""
Base Event Bus with shared consumer loop infrastructure.

Provides a BaseEventBus that implements the common consumer loop,
subscription management, and stop/unsubscribe patterns shared across
the PostgreSQL, Redis, and SQLite event bus implementations.

Subclasses must implement:
- All abstract methods from EventBus (publish, subscribe storage, ack, nack, etc.)
- _create_consumer_task() — backend-specific consumer loop creation
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from dazzle_back.events.bus import (
    ConsumerNotFoundError,
    EventBus,
    EventHandler,
)

logger = logging.getLogger(__name__)


@dataclass
class ActiveSubscription:
    """An active subscription in the broker."""

    topic: str
    group_id: str
    handler: EventHandler
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class BaseEventBus(EventBus):
    """
    Base class for event bus implementations with shared infrastructure.

    Provides common implementations for:
    - Subscription tracking (_subscriptions dict)
    - Consumer task management (_consumer_tasks dict)
    - start_consumer_loop() / stop_consumer_loop()
    - unsubscribe() with task cancellation
    - close() with task cleanup (subclasses call super then close their resources)

    Subclasses must set up self._subscriptions and self._consumer_tasks
    in __init__, and implement _create_consumer_task().
    """

    def _init_base(self) -> None:
        """Initialize shared state. Call from subclass __init__."""
        self._subscriptions: dict[tuple[str, str], ActiveSubscription] = {}
        self._lock = asyncio.Lock()
        self._consumer_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._running = False

    async def stop_consumer_loop(self) -> None:
        """Stop all consumer loops."""
        self._running = False
        for task in self._consumer_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._consumer_tasks.clear()

    async def _cancel_consumer_tasks(self) -> None:
        """Cancel all consumer tasks and clear tracking. Used by close()."""
        self._running = False
        for task in self._consumer_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._consumer_tasks.clear()

    async def unsubscribe(self, topic: str, group_id: str) -> None:
        """Unsubscribe a consumer group from a topic."""
        async with self._lock:
            key = (topic, group_id)
            if key not in self._subscriptions:
                raise ConsumerNotFoundError(topic, group_id)

            # Stop consumer task if running
            if key in self._consumer_tasks:
                self._consumer_tasks[key].cancel()
                try:
                    await self._consumer_tasks[key]
                except asyncio.CancelledError:
                    pass
                del self._consumer_tasks[key]

            del self._subscriptions[key]

    def _get_handler(self, topic: str, group_id: str) -> EventHandler:
        """Get handler for a subscription, raising if not found."""
        key = (topic, group_id)
        if key not in self._subscriptions:
            raise ConsumerNotFoundError(topic, group_id)
        return self._subscriptions[key].handler
