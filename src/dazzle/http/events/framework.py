"""
Event Framework for Dazzle Runtime.

The EventFramework is the central orchestration point for all event-related
functionality in a Dazzle application. It coordinates:

- Event bus (via tier system)
- Outbox publisher (for transactional event delivery)
- Consumer management (for event handlers)
- Lifecycle management (startup/shutdown)

Usage:
    framework = EventFramework(config=EventFrameworkConfig(database_url="postgresql://..."))
    await framework.start()

    # Application runs...

    await framework.stop()

Or as context manager:
    async with EventFramework(config=EventFrameworkConfig(database_url="postgresql://...")) as framework:
        # Application runs...
        pass
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import psycopg

from dazzle.core.db_url import normalise_postgres_scheme
from dazzle.http.events.bus import EventBus, EventHandler
from dazzle.http.events.consumer import ConsumerConfig, IdempotentConsumer
from dazzle.http.events.envelope import EventEnvelope, topic_of
from dazzle.http.events.inbox import EventInbox
from dazzle.http.events.outbox import EventOutbox
from dazzle.http.events.publisher import OutboxPublisher, PublisherConfig

# Connection factory type: async callable returning a connection
ConnectFn = Callable[[], Awaitable[Any]]

logger = logging.getLogger(__name__)


@dataclass
class EventFrameworkConfig:
    """Configuration for the event framework."""

    # PostgreSQL connection URL (required)
    database_url: str | None = None

    # Redis connection URL (enables Redis event bus tier)
    redis_url: str | None = None

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
        framework = EventFramework(config=EventFrameworkConfig(database_url="postgresql://..."))
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
    ) -> None:
        """
        Initialize the event framework.

        Args:
            config: Framework configuration
        """
        self._config = config or EventFrameworkConfig()

        self._use_postgres = bool(self._config.database_url)

        # Components (initialized on start)
        self._bus: EventBus | None = None
        self._outbox: EventOutbox | None = None
        self._inbox: EventInbox | None = None
        self._publisher: OutboxPublisher | None = None

        # Connection for outbox operations
        self._conn: Any = None

        # Registered handlers: topic -> [(group_id, handler, event_type filter)]
        self._handlers: dict[str, list[tuple[str, EventHandler, str | None]]] = {}

        # Null tier (no REDIS_URL): handlers delivered in-process by publish()
        self._local_handlers: dict[str, list[tuple[str, EventHandler]]] = {}

        # Active consumers
        self._consumers: dict[str, IdempotentConsumer] = {}

        # Statistics
        self._stats = FrameworkStats()

    def _make_connect_fn(self) -> ConnectFn:
        """Build an async connection factory based on the configured backend."""
        database_url = self._config.database_url
        if database_url is None:
            raise ValueError("database_url is required for event system")

        url = normalise_postgres_scheme(database_url)

        async def _pg_connect() -> psycopg.AsyncConnection[dict[str, Any]]:
            import psycopg
            from psycopg.rows import dict_row

            return await psycopg.AsyncConnection.connect(
                url, row_factory=dict_row, connect_timeout=10
            )

        return _pg_connect

    @property
    def _is_null_tier(self) -> bool:
        return not self._config.redis_url

    def get_bus(self) -> EventBus | None:
        """Return the underlying event bus, or None if not configured."""
        return self._bus

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
        Uses create_bus() from tier.py for unified bus creation.
        """
        if self._stats.is_running:
            return

        logger.info("Starting event framework")

        connect_fn = self._make_connect_fn()

        self._outbox = EventOutbox()
        self._inbox = EventInbox()

        # Connect to database and create tables
        self._conn = await connect_fn()
        await self._outbox.create_table(self._conn)
        await self._inbox.create_table(self._conn)

        # Create event bus via unified tier factory
        from dazzle.http.events.tier import EventTier, TierConfig, create_bus

        # Determine tier from config values (don't rely on env detection alone).
        # Without Redis the bus is the null tier: the Postgres bus that used to
        # serve here was parked in flense ship AR (DD-006).
        if self._config.redis_url:
            explicit_tier = EventTier.REDIS
        else:
            explicit_tier = EventTier.NULL

        tier_config = TierConfig(tier=explicit_tier, redis_url=self._config.redis_url)
        self._bus = create_bus(tier_config)
        if hasattr(self._bus, "connect"):
            await self._bus.connect()

        # Start publisher
        if self._config.auto_start_publisher:
            self._publisher = OutboxPublisher(
                bus=self._bus,
                outbox=self._outbox,
                config=PublisherConfig(
                    poll_interval=self._config.publisher_poll_interval,
                    batch_size=self._config.publisher_batch_size,
                ),
                connect=connect_fn,
            )
            await self._publisher.start()

        # Register handlers and start consumers
        if self._config.auto_start_consumers:
            await self._start_consumers()

        self._stats.is_running = True
        self._stats.started_at = datetime.now(UTC)

        bus_type = type(self._bus).__name__
        tier = "redis" if self._config.redis_url else "null"
        logger.info(
            "Event framework started",
            extra={
                "tier": tier,
                "bus_type": bus_type,
                "publisher_running": self._publisher is not None and self._publisher.is_running,
                "consumer_count": len(self._consumers),
            },
        )

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
        topic: str | None = None,
        *,
        group_id: str | None = None,
        event_type: str | None = None,
    ) -> Any:
        """
        Decorator to register an event handler.

        Args:
            topic: Topic to subscribe to (derived from ``event_type`` when omitted)
            group_id: Consumer group ID (defaults to handler function name)
            event_type: Only deliver events of this full type (#1852)

        Example:
            @framework.on(event_type="auth.user.registered")
            async def handle_signup(event: EventEnvelope):
                print(f"Received: {event.event_type}")
        """

        def decorator(func: EventHandler) -> EventHandler:
            self.register_handler(topic, group_id or func.__name__, func, event_type=event_type)
            return func

        return decorator

    def register_handler(
        self,
        topic: str | None,
        group_id: str,
        handler: EventHandler,
        *,
        event_type: str | None = None,
    ) -> None:
        """
        Register an event handler programmatically.

        Events publish on their topic, which is the event type without the
        action (``auth.user.registered`` -> ``auth.user``). A handler on a
        topic receives every action; pass ``event_type`` to receive one.

        Args:
            topic: Topic to subscribe to (derived from ``event_type`` when None)
            group_id: Consumer group ID
            handler: Handler function
            event_type: Only deliver events of this full type

        Raises:
            ValueError: If neither is given, or ``topic`` is not ``event_type``'s topic.
        """
        if event_type is not None:
            derived = topic_of(event_type)
            if topic is not None and topic != derived:
                raise ValueError(
                    f"event_type {event_type!r} publishes on topic {derived!r}, not {topic!r}"
                )
            topic = derived
        if topic is None:
            raise ValueError("register_handler needs a topic or an event_type")
        if self._stats.is_running:
            logger.warning(
                "Handler %s registered on %s after the event framework started; "
                "it will not receive events",
                group_id,
                event_type or topic,
            )
        self._handlers.setdefault(topic, []).append((group_id, handler, event_type))
        self._stats.active_subscriptions += 1

    async def publish(self, envelope: EventEnvelope, topic: str | None = None) -> None:
        """
        Publish an event directly (not through the outbox).

        With Redis the event goes to the bus. On the null tier (no
        ``REDIS_URL``) the handlers registered in this process are called
        in turn; a failing handler is logged and does not stop the others.
        Null-tier delivery is not durable: an event is lost if the process
        dies mid-delivery.
        """
        topic = topic or envelope.topic
        if self._bus is None:
            raise RuntimeError("EventFramework not started")
        if not self._is_null_tier:
            await self._bus.publish(topic, envelope)
            return
        for group_id, handler in self._local_handlers.get(topic, []):
            try:
                await handler(envelope)
            except Exception:
                logger.exception(
                    "In-process handler %s failed on %s", group_id, envelope.event_type
                )

    async def emit_event(
        self,
        conn: Any,
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

    async def get_connection(self) -> Any:
        """
        Get a database connection for transactional operations.

        Returns a new connection that should be used within a transaction.
        """
        return await self._make_connect_fn()()

    async def _start_consumers(self) -> None:
        """Start consumer tasks for registered handlers."""
        if self._bus is None:
            return

        connect_fn = self._make_connect_fn()

        for topic, handlers in self._handlers.items():
            for group_id, handler, event_type in handlers:
                # Create idempotent consumer
                consumer = IdempotentConsumer(
                    inbox=self._inbox,
                    config=ConsumerConfig(consumer_name=group_id),
                    bus=self._bus,
                    connect=connect_fn,
                )
                await consumer.connect()

                # Wrap handler with consumer
                wrapped = _only_event_type(consumer.handler(handler), event_type)

                if self._is_null_tier:
                    self._local_handlers.setdefault(topic, []).append((group_id, wrapped))
                else:
                    await self._bus.subscribe(topic, group_id, wrapped)

                self._consumers[f"{topic}:{group_id}"] = consumer

        if self._is_null_tier and self._local_handlers:
            logger.info(
                "REDIS_URL not set: %d event handler(s) run in-process on publish "
                "(not durable; outbox events are not delivered)",
                sum(len(h) for h in self._local_handlers.values()),
            )

        # Start bus consumer loops
        await self._bus.start_consumer_loop(poll_interval=self._config.consumer_poll_interval)  # type: ignore[attr-defined]

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

    async def health_check(self) -> dict[str, Any]:
        """Return a concise health snapshot of the event system."""
        outbox_depth = 0
        if self._outbox and self._conn:
            try:
                stats = await self._outbox.get_stats(self._conn)
                outbox_depth = stats.get("pending", 0)
            except Exception:
                logger.debug("Failed to get outbox stats", exc_info=True)

        publisher_stats = self._publisher.stats if self._publisher else None

        tier = "redis" if self._config.redis_url else "null"

        result: dict[str, Any] = {
            "tier": tier,
            "bus_type": type(self._bus).__name__ if self._bus else None,
            "publisher_running": self._publisher.is_running if self._publisher else False,
            "consumer_count": len(self._consumers),
            "outbox_depth": outbox_depth,
            "last_publish_at": (
                publisher_stats.last_publish_at.isoformat()
                if publisher_stats and publisher_stats.last_publish_at
                else None
            ),
            "last_error": publisher_stats.last_error if publisher_stats else None,
        }

        # Add Redis-specific health when Redis tier is active
        if tier == "redis" and self._bus is not None:
            try:
                topics = await self._bus.list_topics()
                result["redis_connected"] = True
                result["redis_topics"] = len(topics)
            except Exception:
                result["redis_connected"] = False

        return result


def _only_event_type(handler: EventHandler, event_type: str | None) -> EventHandler:
    """Wrap *handler* so it only sees events of *event_type* (None = all)."""
    if event_type is None:
        return handler

    async def filtered(event: EventEnvelope) -> None:
        if event.event_type == event_type:
            await handler(event)

    return filtered
