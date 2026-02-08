"""
Event Framework for Dazzle Runtime.

The EventFramework is the central orchestration point for all event-related
functionality in a Dazzle application. It coordinates:

- Event bus (DevBrokerSQLite for development)
- Outbox publisher (for transactional event delivery)
- Consumer management (for event handlers)
- Lifecycle management (startup/shutdown)

Usage:
    framework = EventFramework(db_path="app.db")
    await framework.start()

    # Application runs...

    await framework.stop()

Or as context manager:
    async with EventFramework(db_path="app.db") as framework:
        # Application runs...
        pass
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from dazzle_back.events.bus import EventBus, EventHandler
from dazzle_back.events.consumer import ConsumerConfig, IdempotentConsumer
from dazzle_back.events.dev_sqlite import DevBrokerSQLite
from dazzle_back.events.envelope import EventEnvelope
from dazzle_back.events.inbox import EventInbox
from dazzle_back.events.outbox import EventOutbox
from dazzle_back.events.publisher import OutboxPublisher, PublisherConfig

logger = logging.getLogger(__name__)


@dataclass
class EventFrameworkConfig:
    """Configuration for the event framework."""

    # Database path for SQLite event storage
    db_path: str = "app.db"

    # PostgreSQL connection URL (takes precedence over db_path when set)
    database_url: str | None = None

    # Whether to auto-start the publisher loop
    auto_start_publisher: bool = True

    # Whether to auto-start consumer loops
    auto_start_consumers: bool = True

    # Publisher configuration
    publisher_poll_interval: float = 1.0
    publisher_batch_size: int = 100

    # Consumer configuration
    consumer_poll_interval: float = 0.5


@dataclass
class FrameworkStats:
    """Runtime statistics for the framework."""

    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    events_published: int = 0
    events_consumed: int = 0
    active_subscriptions: int = 0
    is_running: bool = False


class EventFramework:
    """
    Central orchestrator for Dazzle event infrastructure.

    The EventFramework manages the lifecycle of all event components and
    provides a unified interface for event operations.

    Example:
        # Create and start framework
        framework = EventFramework(db_path="app.db")
        await framework.start()

        # Publish events (through outbox for transactional safety)
        async with framework.get_connection() as conn:
            await framework.emit_event(conn, envelope)

        # Subscribe to events
        @framework.on("app.Order")
        async def handle_order(event: EventEnvelope):
            print(f"Received: {event.event_type}")

        # Stop framework
        await framework.stop()
    """

    def __init__(
        self,
        config: EventFrameworkConfig | None = None,
        *,
        db_path: str | None = None,
    ) -> None:
        """
        Initialize the event framework.

        Args:
            config: Framework configuration
            db_path: Shorthand for config.db_path
        """
        self._config = config or EventFrameworkConfig()
        if db_path:
            self._config.db_path = db_path

        self._use_postgres = bool(self._config.database_url)

        # Components (initialized on start)
        self._bus: DevBrokerSQLite | EventBus | None = None
        self._outbox: EventOutbox | None = None
        self._inbox: EventInbox | None = None
        self._publisher: OutboxPublisher | None = None

        # Connection for outbox operations
        self._conn: aiosqlite.Connection | Any = None

        # Registered handlers
        self._handlers: dict[str, list[tuple[str, EventHandler]]] = {}

        # Active consumers
        self._consumers: dict[str, IdempotentConsumer] = {}

        # Statistics
        self._stats = FrameworkStats()

    @property
    def bus(self) -> EventBus:
        """Get the event bus (raises if not started)."""
        if self._bus is None:
            raise RuntimeError("EventFramework not started")
        return self._bus

    @property
    def outbox(self) -> EventOutbox:
        """Get the event outbox (raises if not started)."""
        if self._outbox is None:
            raise RuntimeError("EventFramework not started")
        return self._outbox

    @property
    def inbox(self) -> EventInbox:
        """Get the event inbox (raises if not started)."""
        if self._inbox is None:
            raise RuntimeError("EventFramework not started")
        return self._inbox

    @property
    def is_running(self) -> bool:
        """Check if the framework is running."""
        return self._stats.is_running

    async def start(self) -> None:
        """
        Start the event framework.

        Initializes all components and starts background tasks.
        """
        if self._stats.is_running:
            return

        logger.info("Starting event framework", extra={"db_path": self._config.db_path})

        if self._use_postgres:
            # PostgreSQL mode
            import asyncpg

            from dazzle_back.events.postgres_bus import PostgresBus, PostgresConfig

            self._outbox = EventOutbox(use_postgres=True)
            self._inbox = EventInbox(backend_type="postgres", placeholder="%s")

            database_url = self._config.database_url
            if database_url and database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", "postgresql://", 1)

            # Connect to database
            self._conn = await asyncpg.connect(database_url)

            # Create tables
            await self._outbox.create_table(self._conn)
            await self._inbox.create_table(self._conn)

            # Initialize PostgreSQL event bus
            pg_config = PostgresConfig(dsn=database_url or "")
            self._bus = PostgresBus(pg_config)
            await self._bus.connect()
        else:
            # SQLite mode (default)
            self._outbox = EventOutbox()
            self._inbox = EventInbox()

            # Connect to database
            self._conn = await aiosqlite.connect(self._config.db_path)

            # Create tables
            await self._outbox.create_table(self._conn)
            await self._inbox.create_table(self._conn)

            # Initialize event bus
            self._bus = DevBrokerSQLite(self._config.db_path)
            await self._bus.connect()

        # Start publisher
        if self._config.auto_start_publisher:
            self._publisher = OutboxPublisher(
                self._config.db_path,
                self._bus,
                self._outbox,
                config=PublisherConfig(
                    poll_interval=self._config.publisher_poll_interval,
                    batch_size=self._config.publisher_batch_size,
                ),
            )
            await self._publisher.start()

        # Register handlers and start consumers
        if self._config.auto_start_consumers:
            await self._start_consumers()

        self._stats.is_running = True
        self._stats.started_at = datetime.now(UTC)

        logger.info("Event framework started")

    async def stop(self) -> None:
        """
        Stop the event framework.

        Gracefully shuts down all components and background tasks.
        """
        if not self._stats.is_running:
            return

        logger.info("Stopping event framework")

        # Stop publisher
        if self._publisher:
            await self._publisher.stop()
            self._publisher = None

        # Stop consumers
        for consumer in self._consumers.values():
            await consumer.close()
        self._consumers.clear()

        # Close bus
        if self._bus:
            await self._bus.close()
            self._bus = None

        # Close connection
        if self._conn:
            await self._conn.close()
            self._conn = None

        self._stats.is_running = False

        logger.info("Event framework stopped")

    async def __aenter__(self) -> EventFramework:
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()

    def on(
        self,
        topic: str,
        *,
        group_id: str | None = None,
    ) -> Any:
        """
        Decorator to register an event handler.

        Args:
            topic: Topic to subscribe to
            group_id: Consumer group ID (defaults to handler function name)

        Example:
            @framework.on("app.Order")
            async def handle_order(event: EventEnvelope):
                print(f"Received: {event.event_type}")
        """

        def decorator(func: EventHandler) -> EventHandler:
            gid = group_id or func.__name__
            if topic not in self._handlers:
                self._handlers[topic] = []
            self._handlers[topic].append((gid, func))
            self._stats.active_subscriptions += 1
            return func

        return decorator

    def register_handler(
        self,
        topic: str,
        group_id: str,
        handler: EventHandler,
    ) -> None:
        """
        Register an event handler programmatically.

        Args:
            topic: Topic to subscribe to
            group_id: Consumer group ID
            handler: Handler function
        """
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append((group_id, handler))
        self._stats.active_subscriptions += 1

    async def emit_event(
        self,
        conn: aiosqlite.Connection | Any,
        envelope: EventEnvelope,
        topic: str | None = None,
    ) -> None:
        """
        Emit an event through the outbox.

        This should be called within the same transaction as the business
        operation for transactional safety.

        Args:
            conn: Database connection (should be in a transaction)
            envelope: Event to emit
            topic: Override topic (defaults to envelope.topic)
        """
        if self._outbox is None:
            raise RuntimeError("EventFramework not started")

        await self._outbox.append(conn, envelope, topic)
        self._stats.events_published += 1

    async def get_connection(self) -> aiosqlite.Connection | Any:
        """
        Get a database connection for transactional operations.

        Returns a new connection that should be used within a transaction.
        """
        if self._use_postgres:
            import asyncpg

            database_url = self._config.database_url
            if database_url and database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", "postgresql://", 1)
            return await asyncpg.connect(database_url)
        return await aiosqlite.connect(self._config.db_path)

    async def _start_consumers(self) -> None:
        """Start consumer tasks for registered handlers."""
        if self._bus is None:
            return

        for topic, handlers in self._handlers.items():
            for group_id, handler in handlers:
                # Create idempotent consumer
                consumer = IdempotentConsumer(
                    self._config.db_path,
                    self._inbox,
                    ConsumerConfig(consumer_name=group_id),
                    bus=self._bus,
                )
                await consumer.connect()

                # Wrap handler with consumer
                wrapped = consumer.handler(handler)

                # Subscribe to bus
                await self._bus.subscribe(topic, group_id, wrapped)

                self._consumers[f"{topic}:{group_id}"] = consumer

        # Start bus consumer loops
        await self._bus.start_consumer_loop(poll_interval=self._config.consumer_poll_interval)

    async def drain_outbox(self, *, timeout: float = 30.0) -> int:
        """
        Drain all pending events from the outbox.

        Useful for testing or graceful shutdown.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            Number of events drained
        """
        if self._publisher:
            return await self._publisher.drain(timeout=timeout)
        return 0

    async def get_status(self) -> dict[str, Any]:
        """Get detailed framework status."""
        publisher_status = {}
        if self._publisher:
            publisher_status = await self._publisher.get_status()

        outbox_stats = {}
        if self._outbox and self._conn:
            outbox_stats = await self._outbox.get_stats(self._conn)

        bus_info: dict[str, Any] = {}
        if self._bus:
            topics = await self._bus.list_topics()
            bus_info = {
                "topics": topics,
                "topic_count": len(topics),
            }

        return {
            "is_running": self._stats.is_running,
            "started_at": (self._stats.started_at.isoformat() if self._stats.started_at else None),
            "events_published": self._stats.events_published,
            "events_consumed": self._stats.events_consumed,
            "active_subscriptions": self._stats.active_subscriptions,
            "active_consumers": len(self._consumers),
            "publisher": publisher_status,
            "outbox": outbox_stats,
            "bus": bus_info,
        }

    async def get_outbox_stats(self) -> dict[str, Any]:
        """Get outbox statistics for the event explorer."""
        if self._outbox is None or self._conn is None:
            return {"pending": 0, "publishing": 0, "published": 0, "failed": 0}
        return await self._outbox.get_stats(self._conn)

    async def get_recent_outbox_entries(self, limit: int = 10) -> list[Any]:
        """Get recent outbox entries for the event explorer."""
        if self._outbox is None or self._conn is None:
            return []
        return await self._outbox.get_recent_entries(self._conn, limit=limit)


# Global framework instance (optional, for convenience)
_framework: EventFramework | None = None


def get_framework() -> EventFramework:
    """
    Get the global event framework instance.

    Raises:
        RuntimeError: If framework not initialized
    """
    if _framework is None:
        raise RuntimeError("Event framework not initialized. Call init_framework() first.")
    return _framework


async def init_framework(
    config: EventFrameworkConfig | None = None,
    *,
    db_path: str | None = None,
) -> EventFramework:
    """
    Initialize and start the global event framework.

    Args:
        config: Framework configuration
        db_path: Shorthand for config.db_path

    Returns:
        The initialized framework
    """
    global _framework

    if _framework is not None and _framework.is_running:
        return _framework

    _framework = EventFramework(config, db_path=db_path)
    await _framework.start()
    return _framework


async def shutdown_framework() -> None:
    """Shutdown the global event framework."""
    global _framework

    if _framework is not None:
        await _framework.stop()
        _framework = None
