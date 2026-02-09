"""
Idempotent Consumer Wrapper for Event Handlers.

This module provides decorators and wrappers that make event handlers
idempotent by automatically checking the inbox before processing and
marking events as processed after successful handling.

Rule 2: At-least-once delivery is assumed; consumers must be idempotent
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import wraps
from typing import Any, TypeVar

from dazzle_back.events.bus import EventBus, NackReason
from dazzle_back.events.envelope import EventEnvelope
from dazzle_back.events.inbox import EventInbox, ProcessingResult

# Connection factory type: async callable returning a connection (aiosqlite or psycopg)
ConnectFn = Callable[[], Awaitable[Any]]

logger = logging.getLogger(__name__)

# Type for event handlers
EventHandler = Callable[[EventEnvelope], Awaitable[None]]
T = TypeVar("T")


@dataclass
class ConsumerConfig:
    """Configuration for an idempotent consumer."""

    # Consumer group name (used for inbox deduplication)
    consumer_name: str

    # Maximum retry attempts for failed events
    max_retries: int = 3

    # Whether to auto-ack events after successful processing
    auto_ack: bool = True

    # Whether to move to DLQ after max retries
    use_dlq: bool = True


@dataclass
class ConsumerStats:
    """Statistics for a consumer."""

    events_processed: int = 0
    events_skipped: int = 0  # Already processed (dedupe)
    events_failed: int = 0
    events_dlq: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_event_at: datetime | None = None


class IdempotentConsumer:
    """
    Wrapper that makes event handlers idempotent.

    Automatically checks the inbox before processing and marks events
    as processed after successful handling. Handles retries and DLQ.

    Usage:
        inbox = EventInbox()
        consumer = IdempotentConsumer(
            db_path="app.db",
            inbox=inbox,
            config=ConsumerConfig(consumer_name="order-processor"),
        )

        @consumer.handler
        async def handle_order_created(event: EventEnvelope) -> None:
            # Process the event
            pass

        # Use with event bus
        await bus.subscribe("app.Order", "order-processor", handle_order_created)
    """

    def __init__(
        self,
        db_path: str | None = None,
        inbox: EventInbox | None = None,
        config: ConsumerConfig | None = None,
        *,
        bus: EventBus | None = None,
        connect: ConnectFn | None = None,
    ) -> None:
        """
        Initialize the idempotent consumer.

        Args:
            db_path: Path to SQLite database (deprecated — use connect)
            inbox: Inbox instance (creates default if None)
            config: Consumer configuration
            bus: Optional event bus for ack/nack
            connect: Async callable returning a database connection
        """
        if connect is not None:
            self._connect_fn = connect
        elif db_path is not None:
            warnings.warn(
                "IdempotentConsumer(db_path=...) is deprecated, use connect= instead",
                DeprecationWarning,
                stacklevel=2,
            )

            async def _aiosqlite_connect() -> Any:
                import aiosqlite

                return await aiosqlite.connect(db_path)

            self._connect_fn = _aiosqlite_connect
        else:
            raise ValueError("Either connect or db_path must be provided")

        self._db_path = db_path
        self._inbox = inbox or EventInbox()
        self._config = config or ConsumerConfig(consumer_name="default")
        self._bus = bus
        self._stats = ConsumerStats()
        self._conn: Any = None

    @property
    def stats(self) -> ConsumerStats:
        """Get current consumer statistics."""
        return self._stats

    @property
    def consumer_name(self) -> str:
        """Get the consumer name."""
        return self._config.consumer_name

    async def connect(self) -> None:
        """Open database connection."""
        try:
            self._conn = await self._connect_fn()
        except Exception:
            logger.error("Failed to connect to event database", exc_info=True)
            raise
        await self._inbox.create_table(self._conn)

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self) -> IdempotentConsumer:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def handler(
        self,
        func: EventHandler,
    ) -> EventHandler:
        """
        Decorator that wraps an event handler with idempotency.

        Usage:
            @consumer.handler
            async def handle_event(event: EventEnvelope) -> None:
                # Process event
                pass
        """

        @wraps(func)
        async def wrapper(event: EventEnvelope) -> None:
            await self.process(event, func)

        return wrapper

    async def process(
        self,
        event: EventEnvelope,
        handler: EventHandler,
    ) -> bool:
        """
        Process an event with idempotency guarantees.

        Args:
            event: Event to process
            handler: Handler function

        Returns:
            True if event was processed, False if skipped (duplicate)
        """
        if not self._conn:
            await self.connect()

        assert self._conn is not None

        # Check if already processed
        if not await self._inbox.should_process(
            self._conn,
            event.event_id,
            self._config.consumer_name,
        ):
            logger.debug(
                "Skipping duplicate event",
                extra={
                    "event_id": str(event.event_id),
                    "consumer": self._config.consumer_name,
                },
            )
            self._stats.events_skipped += 1
            return False

        # Process the event
        try:
            await handler(event)

            # Mark as processed
            await self._inbox.mark_processed(
                self._conn,
                event.event_id,
                self._config.consumer_name,
                result=ProcessingResult.SUCCESS,
            )

            self._stats.events_processed += 1
            self._stats.last_event_at = datetime.now(UTC)

            logger.debug(
                "Processed event",
                extra={
                    "event_id": str(event.event_id),
                    "event_type": event.event_type,
                    "consumer": self._config.consumer_name,
                },
            )

            # Auto-ack if configured
            if self._config.auto_ack and self._bus:
                await self._bus.ack(
                    event.topic,
                    self._config.consumer_name,
                    event.event_id,
                )

            return True

        except Exception as e:
            logger.exception(
                "Error processing event",
                extra={
                    "event_id": str(event.event_id),
                    "event_type": event.event_type,
                    "consumer": self._config.consumer_name,
                },
            )

            # Mark as error in inbox
            await self._inbox.mark_error(
                self._conn,
                event.event_id,
                self._config.consumer_name,
                str(e),
            )

            self._stats.events_failed += 1

            # Nack to bus if configured
            if self._bus:
                # Decide if retryable based on exception type
                retryable = not isinstance(e, ValueError | TypeError)
                await self._bus.nack(
                    event.topic,
                    self._config.consumer_name,
                    event.event_id,
                    NackReason.handler_error(str(e), retryable=retryable),
                )

            raise

    async def get_status(self) -> dict[str, Any]:
        """Get detailed consumer status."""
        inbox_stats = {}
        if self._conn:
            inbox_stats = await self._inbox.get_stats(
                self._conn,
                consumer_name=self._config.consumer_name,
            )

        return {
            "consumer_name": self._config.consumer_name,
            "started_at": self._stats.started_at.isoformat(),
            "events_processed": self._stats.events_processed,
            "events_skipped": self._stats.events_skipped,
            "events_failed": self._stats.events_failed,
            "events_dlq": self._stats.events_dlq,
            "last_event_at": (
                self._stats.last_event_at.isoformat() if self._stats.last_event_at else None
            ),
            "inbox": inbox_stats,
        }


def idempotent(
    consumer_name: str,
    *,
    db_path: str | None = None,
    connect: ConnectFn | None = None,
) -> Callable[[EventHandler], EventHandler]:
    """
    Decorator factory for making handlers idempotent.

    Simpler alternative to IdempotentConsumer class for single handlers.

    Usage:
        @idempotent("order-processor", connect=connect_fn)
        async def handle_order(event: EventEnvelope) -> None:
            # Process event
            pass
    """
    if connect is not None:
        connect_fn = connect
    elif db_path is not None:
        warnings.warn(
            "idempotent(db_path=...) is deprecated, use connect= instead",
            DeprecationWarning,
            stacklevel=2,
        )

        async def _aiosqlite_connect() -> Any:
            import aiosqlite

            return await aiosqlite.connect(db_path)

        connect_fn = _aiosqlite_connect
    else:
        raise ValueError("Either connect or db_path must be provided")

    inbox = EventInbox()
    _conn: Any = None

    def decorator(func: EventHandler) -> EventHandler:
        @wraps(func)
        async def wrapper(event: EventEnvelope) -> None:
            nonlocal _conn

            if _conn is None:
                _conn = await connect_fn()
                await inbox.create_table(_conn)

            # Check if already processed
            if not await inbox.should_process(_conn, event.event_id, consumer_name):
                logger.debug(
                    "Skipping duplicate event",
                    extra={
                        "event_id": str(event.event_id),
                        "consumer": consumer_name,
                    },
                )
                return

            try:
                await func(event)
                await inbox.mark_processed(
                    _conn,
                    event.event_id,
                    consumer_name,
                )
            except Exception as e:
                await inbox.mark_error(_conn, event.event_id, consumer_name, str(e))
                raise

        return wrapper

    return decorator


class ConsumerGroup:
    """
    Manages multiple consumers as a group.

    Provides lifecycle management and aggregated statistics for
    multiple IdempotentConsumer instances.
    """

    def __init__(self, group_id: str) -> None:
        self._group_id = group_id
        self._consumers: dict[str, IdempotentConsumer] = {}

    @property
    def group_id(self) -> str:
        """Get the group identifier."""
        return self._group_id

    def add(self, name: str, consumer: IdempotentConsumer) -> None:
        """Add a consumer to the group."""
        self._consumers[name] = consumer

    def get(self, name: str) -> IdempotentConsumer | None:
        """Get a consumer by name."""
        return self._consumers.get(name)

    async def start_all(self) -> None:
        """Start all consumers in the group."""
        for consumer in self._consumers.values():
            await consumer.connect()

    async def stop_all(self) -> None:
        """Stop all consumers in the group."""
        for consumer in self._consumers.values():
            await consumer.close()

    async def get_status(self) -> dict[str, Any]:
        """Get aggregated status for all consumers."""
        statuses = {}
        for name, consumer in self._consumers.items():
            statuses[name] = await consumer.get_status()

        total_processed = sum(s["events_processed"] for s in statuses.values())
        total_failed = sum(s["events_failed"] for s in statuses.values())

        return {
            "group_id": self._group_id,
            "consumer_count": len(self._consumers),
            "total_processed": total_processed,
            "total_failed": total_failed,
            "consumers": statuses,
        }
