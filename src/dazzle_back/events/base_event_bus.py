"""
Base Event Bus with shared consumer loop infrastructure.

Provides a BaseEventBus that implements the common consumer loop,
subscription management, DLQ replay, and stop/unsubscribe patterns shared
across the PostgreSQL, Redis, and SQLite event bus implementations.

Subclasses must implement:
- All abstract methods from EventBus (publish, subscribe storage, ack, nack, etc.)
- _create_consumer_task() — backend-specific consumer loop creation
- _fetch_dlq_event() / _delete_dlq_event() / _increment_dlq_attempts()
  for DLQ replay support
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from dazzle_back.events.bus import (
    ConsumerNotFoundError,
    EventBus,
    EventHandler,
)
from dazzle_back.events.envelope import EventEnvelope

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

    # ── DLQ replay template ──────────────────────────────────────────

    async def replay_dlq_event(
        self,
        event_id: str,
        group_id: str,
    ) -> bool:
        """
        Replay a single event from the DLQ.

        Template method: fetches the event via _fetch_dlq_event(), invokes the
        handler, and on success removes it via _delete_dlq_event().  On failure,
        increments the attempt counter via _increment_dlq_attempts() and re-raises.

        Returns:
            True if event was found and replayed successfully
        """
        result = await self._fetch_dlq_event(event_id, group_id)
        if result is None:
            return False

        topic, envelope = result
        handler = self._get_handler(topic, group_id)

        try:
            await handler(envelope)
            await self._delete_dlq_event(event_id, group_id)
            return True
        except Exception:
            await self._increment_dlq_attempts(event_id, group_id)
            raise

    async def _fetch_dlq_event(
        self, event_id: str, group_id: str
    ) -> tuple[str, EventEnvelope] | None:
        """Fetch a DLQ event. Return (topic, envelope) or None if not found.

        Subclasses must override this with backend-specific lookup.
        """
        raise NotImplementedError

    async def _delete_dlq_event(self, event_id: str, group_id: str) -> None:
        """Delete a DLQ event after successful replay.

        Subclasses must override this with backend-specific deletion.
        """
        raise NotImplementedError

    async def _increment_dlq_attempts(self, event_id: str, group_id: str) -> None:
        """Increment the attempt counter for a DLQ event after failed replay.

        Subclasses must override this with backend-specific update.
        """
        raise NotImplementedError

    # ── DLQ filter helpers ───────────────────────────────────────────

    @staticmethod
    def _build_dlq_filter_clause(
        topic: str | None,
        group_id: str | None,
        *,
        placeholder: str = "?",
    ) -> tuple[str, list[Any]]:
        """Build a WHERE clause for DLQ queries from optional topic/group_id.

        Args:
            topic: Optional topic filter.
            group_id: Optional group_id filter.
            placeholder: SQL parameter placeholder ("?" for SQLite, "%s" for PG).

        Returns:
            (where_clause, params) — clause is empty string when no filters.
        """
        conditions: list[str] = []
        params: list[Any] = []

        if topic:
            conditions.append(f"topic = {placeholder}")
            params.append(topic)

        if group_id:
            conditions.append(f"group_id = {placeholder}")
            params.append(group_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        return where_clause, params
