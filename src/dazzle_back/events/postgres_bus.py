"""
PostgreSQL-Backed Event Bus for Dazzle (Tier 1).

Provides a durable event bus using PostgreSQL with:
- FOR UPDATE SKIP LOCKED for competing consumers
- LISTEN/NOTIFY for low-latency wake-up
- Full EventBus interface compliance
- Transactional publish with domain writes

Ideal for Heroku deployments using existing PostgreSQL database.

Tables created:
- _dazzle_events: Event log with sequence numbers
- _dazzle_consumer_offsets: Consumer group positions
- _dazzle_dlq: Dead letter queue for failed events
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from dazzle_back.events.bus import (
    ConsumerNotFoundError,
    ConsumerStatus,
    EventBus,
    EventHandler,
    EventNotFoundError,
    NackReason,
    SubscriptionInfo,
)
from dazzle_back.events.envelope import EventEnvelope

# Conditional import for psycopg (async)
try:
    import psycopg
    import psycopg_pool
    from psycopg.rows import dict_row

    ASYNCPG_AVAILABLE = True  # Keep name for backward compat
except ImportError:
    ASYNCPG_AVAILABLE = False

logger = logging.getLogger(__name__)

# SQL statements for schema creation
CREATE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS {prefix}events (
    id UUID PRIMARY KEY,
    topic VARCHAR(255) NOT NULL,
    event_type VARCHAR(255) NOT NULL,
    event_version VARCHAR(50) NOT NULL DEFAULT '1.0',
    key VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL,
    headers JSONB DEFAULT '{{}}',
    correlation_id UUID,
    causation_id UUID,
    timestamp TIMESTAMPTZ NOT NULL,
    producer VARCHAR(255) NOT NULL DEFAULT 'dazzle',
    sequence_num BIGSERIAL NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_EVENTS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_{prefix}events_topic
    ON {prefix}events(topic);
CREATE INDEX IF NOT EXISTS idx_{prefix}events_topic_seq
    ON {prefix}events(topic, sequence_num);
CREATE INDEX IF NOT EXISTS idx_{prefix}events_key
    ON {prefix}events(key);
CREATE INDEX IF NOT EXISTS idx_{prefix}events_timestamp
    ON {prefix}events(timestamp);
CREATE INDEX IF NOT EXISTS idx_{prefix}events_type
    ON {prefix}events(event_type);
"""

CREATE_OFFSETS_TABLE = """
CREATE TABLE IF NOT EXISTS {prefix}consumer_offsets (
    topic VARCHAR(255) NOT NULL,
    group_id VARCHAR(255) NOT NULL,
    last_sequence BIGINT NOT NULL DEFAULT 0,
    last_processed_at TIMESTAMPTZ,
    PRIMARY KEY (topic, group_id)
);
"""

CREATE_DLQ_TABLE = """
CREATE TABLE IF NOT EXISTS {prefix}dlq (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL,
    topic VARCHAR(255) NOT NULL,
    group_id VARCHAR(255) NOT NULL,
    envelope JSONB NOT NULL,
    reason_code VARCHAR(100) NOT NULL,
    reason_message TEXT NOT NULL,
    reason_metadata JSONB,
    attempts INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (event_id, group_id)
);
"""

CREATE_DLQ_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_{prefix}dlq_topic ON {prefix}dlq(topic);
CREATE INDEX IF NOT EXISTS idx_{prefix}dlq_group ON {prefix}dlq(group_id);
"""


@dataclass
class PostgresConfig:
    """Configuration for PostgreSQL event bus."""

    dsn: str
    """PostgreSQL connection string (DATABASE_URL)."""

    table_prefix: str = "_dazzle_"
    """Prefix for event tables."""

    max_retries: int = 3
    """Maximum retry attempts before moving to DLQ."""

    visibility_timeout: int = 300
    """Seconds before stuck events are recovered."""

    poll_interval: float = 0.5
    """Seconds between polls when no events available."""

    pool_min_size: int = 2
    """Minimum connection pool size."""

    pool_max_size: int = 10
    """Maximum connection pool size."""


@dataclass
class ActiveSubscription:
    """An active subscription in the broker."""

    topic: str
    group_id: str
    handler: EventHandler
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class PostgresBus(EventBus):
    """
    PostgreSQL-backed EventBus implementation.

    Uses psycopg (v3) for async database access with:
    - Connection pooling for efficiency
    - LISTEN/NOTIFY for low-latency event notification
    - FOR UPDATE SKIP LOCKED for competing consumers

    Example:
        config = PostgresConfig(dsn=os.environ["DATABASE_URL"])
        async with PostgresBus(config) as bus:
            await bus.publish("app.Order", envelope)

            async def handler(event):
                print(f"Received: {event.event_type}")

            await bus.subscribe("app.Order", "my-consumer", handler)
            await bus.start_consumer_loop()
    """

    def __init__(self, config: PostgresConfig) -> None:
        """
        Initialize the PostgreSQL bus.

        Args:
            config: PostgreSQL configuration
        """
        if not ASYNCPG_AVAILABLE:
            raise ImportError(
                "psycopg is required for PostgresBus. Install with: pip install dazzle[postgres]"
            )

        self._config = config
        self._prefix = config.table_prefix
        # typed Any because row_factory=dict_row is passed via kwargs at runtime
        # but psycopg_pool generics don't propagate that to mypy
        self._pool: Any = None
        self._subscriptions: dict[tuple[str, str], ActiveSubscription] = {}
        self._lock = asyncio.Lock()
        self._consumer_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._running = False
        self._listen_conn: psycopg.AsyncConnection | None = None
        self._listen_task: asyncio.Task[None] | None = None
        self._notify_event = asyncio.Event()

    async def connect(self) -> None:
        """Connect to the database and create tables if needed."""
        self._pool = psycopg_pool.AsyncConnectionPool(
            conninfo=self._config.dsn,
            min_size=self._config.pool_min_size,
            max_size=self._config.pool_max_size,
            kwargs={"row_factory": dict_row, "autocommit": True},
        )
        await self._pool.wait()
        await self._create_tables()
        await self._setup_listen()

    async def close(self) -> None:
        """Close the database connection and stop consumers."""
        self._running = False

        # Cancel consumer tasks
        for task in self._consumer_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._consumer_tasks.clear()

        # Cancel listen task
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None

        # Close listen connection
        if self._listen_conn:
            await self._listen_conn.close()
            self._listen_conn = None

        # Close pool
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def __aenter__(self) -> PostgresBus:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def _get_pool(self) -> Any:
        """Get database pool with error handling."""
        if self._pool is None:
            raise RuntimeError("PostgresBus not connected. Call connect() first.")
        return self._pool

    async def _create_tables(self) -> None:
        """Create required tables if they don't exist."""
        pool = self._get_pool()
        prefix = self._prefix

        async with pool.connection() as conn:
            await conn.execute(CREATE_EVENTS_TABLE.format(prefix=prefix))
            await conn.execute(CREATE_EVENTS_INDEXES.format(prefix=prefix))
            await conn.execute(CREATE_OFFSETS_TABLE.format(prefix=prefix))
            await conn.execute(CREATE_DLQ_TABLE.format(prefix=prefix))
            await conn.execute(CREATE_DLQ_INDEXES.format(prefix=prefix))

    async def _setup_listen(self) -> None:
        """Set up LISTEN connection for event notifications."""
        self._listen_conn = await psycopg.AsyncConnection.connect(self._config.dsn, autocommit=True)
        await self._listen_conn.execute(f"LISTEN {self._prefix}events_channel")
        self._listen_task = asyncio.create_task(self._listen_loop())

    async def _listen_loop(self) -> None:
        """Background task that receives NOTIFY events."""
        try:
            async for _notify in self._listen_conn.notifies():  # type: ignore[union-attr]
                self._notify_event.set()
        except Exception:
            pass  # Connection closed during shutdown

    async def _notify(self) -> None:
        """Send NOTIFY to wake up consumers."""
        pool = self._get_pool()
        async with pool.connection() as conn:
            await conn.execute(f"NOTIFY {self._prefix}events_channel")

    async def publish(
        self,
        topic: str,
        envelope: EventEnvelope,
        *,
        transactional: bool = False,
    ) -> None:
        """
        Publish an event to a topic.

        Events are immediately written to the database. Use transactional=True
        when publishing as part of a larger database transaction.
        """
        pool = self._get_pool()
        prefix = self._prefix

        async with pool.connection() as conn:
            await conn.execute(
                f"""
                INSERT INTO {prefix}events (
                    id, topic, event_type, event_version, key, payload,
                    headers, correlation_id, causation_id, timestamp, producer
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(envelope.event_id),
                    topic,
                    envelope.event_type,
                    envelope.event_version,
                    envelope.key,
                    json.dumps(envelope.payload),
                    json.dumps(envelope.headers),
                    str(envelope.correlation_id) if envelope.correlation_id else None,
                    str(envelope.causation_id) if envelope.causation_id else None,
                    envelope.timestamp.isoformat() if envelope.timestamp else None,
                    envelope.producer,
                ),
            )

        # Notify consumers
        await self._notify()

    async def publish_with_connection(
        self,
        conn: psycopg.AsyncConnection,
        topic: str,
        envelope: EventEnvelope,
    ) -> None:
        """
        Publish an event using an existing connection (for transactions).

        Use this when publishing must be atomic with other database operations.

        Example:
            async with pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute("INSERT INTO orders ...")
                    await bus.publish_with_connection(conn, "app.Order", envelope)
        """
        prefix = self._prefix

        await conn.execute(
            f"""
            INSERT INTO {prefix}events (
                id, topic, event_type, event_version, key, payload,
                headers, correlation_id, causation_id, timestamp, producer
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(envelope.event_id),
                topic,
                envelope.event_type,
                envelope.event_version,
                envelope.key,
                json.dumps(envelope.payload),
                json.dumps(envelope.headers),
                str(envelope.correlation_id) if envelope.correlation_id else None,
                str(envelope.causation_id) if envelope.causation_id else None,
                envelope.timestamp.isoformat() if envelope.timestamp else None,
                envelope.producer,
            ),
        )

    async def subscribe(
        self,
        topic: str,
        group_id: str,
        handler: EventHandler,
    ) -> SubscriptionInfo:
        """Subscribe to events from a topic."""
        async with self._lock:
            key = (topic, group_id)

            # Create subscription record
            sub = ActiveSubscription(
                topic=topic,
                group_id=group_id,
                handler=handler,
            )
            self._subscriptions[key] = sub

            # Ensure consumer offset exists
            pool = self._get_pool()
            prefix = self._prefix

            async with pool.connection() as conn:
                await conn.execute(
                    f"""
                    INSERT INTO {prefix}consumer_offsets (topic, group_id, last_sequence)
                    VALUES (%s, %s, 0)
                    ON CONFLICT (topic, group_id) DO NOTHING
                    """,
                    (topic, group_id),
                )

            return SubscriptionInfo(
                topic=topic,
                group_id=group_id,
                handler=handler,
            )

    async def unsubscribe(
        self,
        topic: str,
        group_id: str,
    ) -> None:
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

    async def ack(
        self,
        topic: str,
        group_id: str,
        event_id: UUID,
    ) -> None:
        """Acknowledge successful processing of an event."""
        pool = self._get_pool()
        prefix = self._prefix

        async with pool.connection() as conn:
            # Get event's sequence number
            cur = await conn.execute(
                f"SELECT sequence_num FROM {prefix}events WHERE id = %s AND topic = %s",
                (str(event_id), topic),
            )
            row = await cur.fetchone()
            if not row:
                raise EventNotFoundError(event_id)

            sequence_num = row["sequence_num"]

            # Update consumer offset
            await conn.execute(
                f"""
                UPDATE {prefix}consumer_offsets
                SET last_sequence = GREATEST(last_sequence, %s),
                    last_processed_at = NOW()
                WHERE topic = %s AND group_id = %s
                """,
                (sequence_num, topic, group_id),
            )

    async def nack(
        self,
        topic: str,
        group_id: str,
        event_id: UUID,
        reason: NackReason,
    ) -> None:
        """Reject an event, indicating processing failed."""
        pool = self._get_pool()
        prefix = self._prefix

        async with pool.connection() as conn:
            # Get event
            cur = await conn.execute(
                f"""
                SELECT id, topic, event_type, event_version, key, payload,
                       headers, correlation_id, causation_id, timestamp, producer,
                       sequence_num
                FROM {prefix}events WHERE id = %s
                """,
                (str(event_id),),
            )
            row = await cur.fetchone()
            if not row:
                raise EventNotFoundError(event_id)

            envelope = self._row_to_envelope(row)

            if not reason.retryable:
                # Move to DLQ
                await conn.execute(
                    f"""
                    INSERT INTO {prefix}dlq (
                        event_id, topic, group_id, envelope,
                        reason_code, reason_message, reason_metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (event_id, group_id) DO UPDATE SET
                        attempts = {prefix}dlq.attempts + 1,
                        reason_code = EXCLUDED.reason_code,
                        reason_message = EXCLUDED.reason_message
                    """,
                    (
                        str(event_id),
                        topic,
                        group_id,
                        json.dumps(envelope.to_dict()),
                        reason.code,
                        reason.message,
                        json.dumps(reason.metadata),
                    ),
                )

                # Advance offset past this event (skip it)
                await conn.execute(
                    f"""
                    UPDATE {prefix}consumer_offsets
                    SET last_sequence = GREATEST(last_sequence, %s)
                    WHERE topic = %s AND group_id = %s
                    """,
                    (row["sequence_num"], topic, group_id),
                )
            # If retryable, don't advance offset - event will be redelivered

    async def replay(
        self,
        topic: str,
        *,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
        from_offset: int | None = None,
        to_offset: int | None = None,
        key_filter: str | None = None,
    ) -> AsyncIterator[EventEnvelope]:
        """Replay events from a topic."""
        pool = self._get_pool()
        prefix = self._prefix

        conditions = ["topic = %s"]
        params: list[Any] = [topic]

        if from_timestamp is not None:
            conditions.append("timestamp >= %s")
            params.append(from_timestamp)

        if to_timestamp is not None:
            conditions.append("timestamp < %s")
            params.append(to_timestamp)

        if from_offset is not None:
            conditions.append("sequence_num >= %s")
            params.append(from_offset)

        if to_offset is not None:
            conditions.append("sequence_num < %s")
            params.append(to_offset)

        if key_filter is not None:
            conditions.append("key = %s")
            params.append(key_filter)

        query = f"""
            SELECT id, topic, event_type, event_version, key, payload,
                   headers, correlation_id, causation_id, timestamp, producer
            FROM {prefix}events
            WHERE {" AND ".join(conditions)}
            ORDER BY sequence_num ASC
        """

        async with pool.connection() as conn:
            cur = await conn.execute(query, tuple(params))
            async for row in cur:
                yield self._row_to_envelope(row)

    async def get_consumer_status(
        self,
        topic: str,
        group_id: str,
    ) -> ConsumerStatus:
        """Get status information for a consumer group."""
        pool = self._get_pool()
        prefix = self._prefix

        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                SELECT last_sequence, last_processed_at
                FROM {prefix}consumer_offsets
                WHERE topic = %s AND group_id = %s
                """,
                (topic, group_id),
            )
            row = await cur.fetchone()
            if not row:
                raise ConsumerNotFoundError(topic, group_id)

            # Count pending events
            cur2 = await conn.execute(
                f"""
                SELECT COUNT(*) as pending
                FROM {prefix}events
                WHERE topic = %s AND sequence_num > %s
                """,
                (topic, row["last_sequence"]),
            )
            pending_row = await cur2.fetchone()

            return ConsumerStatus(
                topic=topic,
                group_id=group_id,
                last_offset=row["last_sequence"],
                pending_count=pending_row["pending"] if pending_row else 0,
                last_processed_at=row["last_processed_at"],
            )

    async def list_topics(self) -> list[str]:
        """List all topics in the bus."""
        pool = self._get_pool()
        prefix = self._prefix

        async with pool.connection() as conn:
            cur = await conn.execute(f"SELECT DISTINCT topic FROM {prefix}events ORDER BY topic")
            rows = await cur.fetchall()
            return [row["topic"] for row in rows]

    async def list_consumer_groups(self, topic: str) -> list[str]:
        """List all consumer groups for a topic."""
        pool = self._get_pool()
        prefix = self._prefix

        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                SELECT group_id FROM {prefix}consumer_offsets
                WHERE topic = %s ORDER BY group_id
                """,
                (topic,),
            )
            rows = await cur.fetchall()
            return [row["group_id"] for row in rows]

    async def get_topic_info(self, topic: str) -> dict[str, Any]:
        """Get information about a topic."""
        pool = self._get_pool()
        prefix = self._prefix

        async with pool.connection() as conn:
            # Event stats
            cur = await conn.execute(
                f"""
                SELECT
                    COUNT(*) as event_count,
                    MIN(timestamp) as oldest_event,
                    MAX(timestamp) as newest_event,
                    MAX(sequence_num) as current_sequence
                FROM {prefix}events
                WHERE topic = %s
                """,
                (topic,),
            )
            stats = await cur.fetchone()

            # Consumer groups
            cur2 = await conn.execute(
                f"SELECT group_id FROM {prefix}consumer_offsets WHERE topic = %s",
                (topic,),
            )
            groups = await cur2.fetchall()

            # DLQ count
            cur3 = await conn.execute(
                f"SELECT COUNT(*) as dlq_count FROM {prefix}dlq WHERE topic = %s",
                (topic,),
            )
            dlq = await cur3.fetchone()

            return {
                "topic": topic,
                "event_count": stats["event_count"] if stats else 0,
                "oldest_event": (
                    stats["oldest_event"].isoformat() if stats and stats["oldest_event"] else None
                ),
                "newest_event": (
                    stats["newest_event"].isoformat() if stats and stats["newest_event"] else None
                ),
                "current_sequence": stats["current_sequence"] if stats else 0,
                "consumer_groups": [row["group_id"] for row in groups],
                "dlq_count": dlq["dlq_count"] if dlq else 0,
            }

    def _row_to_envelope(self, row: dict[str, Any]) -> EventEnvelope:
        """Convert a database row to an EventEnvelope."""
        payload = row["payload"]
        headers = row["headers"]

        # Handle JSONB which may be auto-deserialized
        if isinstance(payload, str):
            payload = json.loads(payload)
        if isinstance(headers, str):
            headers = json.loads(headers)

        return EventEnvelope(
            event_id=row["id"],
            event_type=row["event_type"],
            event_version=row["event_version"],
            key=row["key"],
            payload=payload,
            headers=headers or {},
            correlation_id=row["correlation_id"],
            causation_id=row["causation_id"],
            timestamp=row["timestamp"],
            producer=row["producer"],
        )

    # Consumer loop methods

    async def start_consumer_loop(self, poll_interval: float | None = None) -> None:
        """
        Start consumer loops for all subscriptions.

        This runs until stop_consumer_loop() is called or the bus is closed.

        Args:
            poll_interval: Seconds between polls (defaults to config value)
        """
        self._running = True
        interval = poll_interval or self._config.poll_interval

        for key, sub in self._subscriptions.items():
            if key not in self._consumer_tasks:
                task = asyncio.create_task(self._consumer_loop(sub.topic, sub.group_id, interval))
                self._consumer_tasks[key] = task

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

    async def _consumer_loop(
        self,
        topic: str,
        group_id: str,
        poll_interval: float,
    ) -> None:
        """Main consumer loop for a subscription."""
        while self._running:
            try:
                processed = await self.poll_and_process(topic, group_id, max_events=10)
                if processed == 0:
                    # Wait for notification or timeout
                    self._notify_event.clear()
                    try:
                        await asyncio.wait_for(
                            self._notify_event.wait(),
                            timeout=poll_interval,
                        )
                    except TimeoutError:
                        pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consumer loop error for {topic}/{group_id}: {e}")
                await asyncio.sleep(poll_interval)

    async def poll_and_process(
        self,
        topic: str,
        group_id: str,
        *,
        max_events: int = 10,
    ) -> int:
        """
        Poll for and process pending events using SKIP LOCKED.

        This implements competing consumers - multiple workers can safely
        call this method and events will be distributed among them.

        Args:
            topic: Topic to poll
            group_id: Consumer group
            max_events: Maximum events to process in one batch

        Returns:
            Number of events processed
        """
        key = (topic, group_id)
        if key not in self._subscriptions:
            raise ConsumerNotFoundError(topic, group_id)

        handler = self._subscriptions[key].handler
        pool = self._get_pool()
        prefix = self._prefix

        async with pool.connection() as conn:
            # Get current offset
            cur = await conn.execute(
                f"""
                SELECT last_sequence FROM {prefix}consumer_offsets
                WHERE topic = %s AND group_id = %s
                """,
                (topic, group_id),
            )
            offset_row = await cur.fetchone()
            last_sequence = offset_row["last_sequence"] if offset_row else 0

            # Fetch and lock pending events using SKIP LOCKED
            # This allows competing consumers to process different events
            cur2 = await conn.execute(
                f"""
                SELECT id, topic, event_type, event_version, key, payload,
                       headers, correlation_id, causation_id, timestamp, producer
                FROM {prefix}events
                WHERE topic = %s AND sequence_num > %s
                ORDER BY sequence_num ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (topic, last_sequence, max_events),
            )
            rows = await cur2.fetchall()

            processed = 0
            for row in rows:
                envelope = self._row_to_envelope(row)

                try:
                    await handler(envelope)
                    await self.ack(topic, group_id, envelope.event_id)
                    processed += 1
                except Exception as e:
                    await self.nack(
                        topic,
                        group_id,
                        envelope.event_id,
                        NackReason.handler_error(str(e)),
                    )

            return processed

    # DLQ methods

    async def get_dlq_events(
        self,
        topic: str | None = None,
        group_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get events from the dead letter queue."""
        pool = self._get_pool()
        prefix = self._prefix

        conditions = []
        params: list[Any] = []

        if topic:
            conditions.append("topic = %s")
            params.append(topic)

        if group_id:
            conditions.append("group_id = %s")
            params.append(group_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                SELECT event_id, topic, group_id, envelope,
                       reason_code, reason_message, attempts, created_at
                FROM {prefix}dlq
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = await cur.fetchall()

            results = []
            for row in rows:
                envelope_data = row["envelope"]
                if isinstance(envelope_data, str):
                    envelope_data = json.loads(envelope_data)

                results.append(
                    {
                        "event_id": str(row["event_id"]),
                        "topic": row["topic"],
                        "group_id": row["group_id"],
                        "envelope": EventEnvelope.from_dict(envelope_data),
                        "reason_code": row["reason_code"],
                        "reason_message": row["reason_message"],
                        "attempts": row["attempts"],
                        "created_at": row["created_at"].isoformat(),
                    }
                )

            return results

    async def get_dlq_count(self, topic: str | None = None) -> int:
        """Get count of events in dead letter queue."""
        pool = self._get_pool()
        prefix = self._prefix

        async with pool.connection() as conn:
            if topic:
                cur = await conn.execute(
                    f"SELECT COUNT(*) as count FROM {prefix}dlq WHERE topic = %s",
                    (topic,),
                )
            else:
                cur = await conn.execute(f"SELECT COUNT(*) as count FROM {prefix}dlq")
            row = await cur.fetchone()
            return row["count"] if row else 0

    async def replay_dlq_event(
        self,
        event_id: str,
        group_id: str,
    ) -> bool:
        """
        Replay a single event from the DLQ.

        The event is removed from DLQ and reprocessed through the normal path.

        Returns:
            True if event was found and replayed successfully
        """
        pool = self._get_pool()
        prefix = self._prefix

        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                SELECT topic, envelope FROM {prefix}dlq
                WHERE event_id = %s AND group_id = %s
                """,
                (str(UUID(event_id)), group_id),
            )
            row = await cur.fetchone()
            if not row:
                return False

            topic = row["topic"]
            envelope_data = row["envelope"]
            if isinstance(envelope_data, str):
                envelope_data = json.loads(envelope_data)

            envelope = EventEnvelope.from_dict(envelope_data)

            # Process through handler
            key = (topic, group_id)
            if key not in self._subscriptions:
                raise ConsumerNotFoundError(topic, group_id)

            handler = self._subscriptions[key].handler

            try:
                await handler(envelope)
                # Remove from DLQ on success
                await conn.execute(
                    f"DELETE FROM {prefix}dlq WHERE event_id = %s AND group_id = %s",
                    (str(UUID(event_id)), group_id),
                )
                return True
            except Exception:
                # Update attempts count
                await conn.execute(
                    f"""
                    UPDATE {prefix}dlq SET attempts = attempts + 1
                    WHERE event_id = %s AND group_id = %s
                    """,
                    (str(UUID(event_id)), group_id),
                )
                raise

    async def clear_dlq(
        self,
        topic: str | None = None,
        group_id: str | None = None,
    ) -> int:
        """
        Clear events from the dead letter queue.

        Returns:
            Number of events cleared
        """
        pool = self._get_pool()
        prefix = self._prefix

        conditions = []
        params: list[Any] = []

        if topic:
            conditions.append("topic = %s")
            params.append(topic)

        if group_id:
            conditions.append("group_id = %s")
            params.append(group_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params_tuple = tuple(params) if params else ()

        async with pool.connection() as conn:
            # Get count first
            cur = await conn.execute(
                f"SELECT COUNT(*) as count FROM {prefix}dlq {where_clause}",
                params_tuple,
            )
            count_row = await cur.fetchone()
            count = count_row["count"] if count_row else 0

            # Delete
            await conn.execute(
                f"DELETE FROM {prefix}dlq {where_clause}",
                params_tuple,
            )

            return count
