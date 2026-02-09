"""
SQLite-Backed Event Broker for Development.

DevBrokerSQLite provides a durable, file-based implementation of the EventBus
interface that requires zero infrastructure (no Docker, no Kafka, no Redis).

Features:
- Durable event storage in SQLite
- Consumer offset tracking for at-least-once delivery
- Dead letter queue support
- Full EventBus interface compliance
- Suitable for development and small deployments

The broker uses the same database file as the application by default,
making it easy to run a complete event-driven app with just `dazzle serve`.

Tables created:
- _dazzle_events: Event log (append-only)
- _dazzle_consumer_offsets: Consumer group positions
- _dazzle_dlq: Dead letter queue for failed events
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import aiosqlite

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

# SQL statements for schema creation
CREATE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS _dazzle_events (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_version TEXT NOT NULL DEFAULT '1.0',
    key TEXT NOT NULL,
    payload TEXT NOT NULL,
    headers TEXT,
    correlation_id TEXT,
    causation_id TEXT,
    timestamp TEXT NOT NULL,
    producer TEXT NOT NULL DEFAULT 'dazzle',
    sequence_num INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_EVENTS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_events_topic ON _dazzle_events(topic);
CREATE INDEX IF NOT EXISTS idx_events_topic_seq ON _dazzle_events(topic, sequence_num);
CREATE INDEX IF NOT EXISTS idx_events_key ON _dazzle_events(key);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON _dazzle_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON _dazzle_events(event_type);
"""

CREATE_OFFSETS_TABLE = """
CREATE TABLE IF NOT EXISTS _dazzle_consumer_offsets (
    topic TEXT NOT NULL,
    group_id TEXT NOT NULL,
    last_sequence INTEGER NOT NULL DEFAULT 0,
    last_processed_at TEXT,
    PRIMARY KEY (topic, group_id)
);
"""

CREATE_DLQ_TABLE = """
CREATE TABLE IF NOT EXISTS _dazzle_dlq (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    group_id TEXT NOT NULL,
    envelope TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    reason_message TEXT NOT NULL,
    reason_metadata TEXT,
    attempts INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (event_id, group_id)
);
"""

CREATE_DLQ_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_dlq_topic ON _dazzle_dlq(topic);
CREATE INDEX IF NOT EXISTS idx_dlq_group ON _dazzle_dlq(group_id);
"""

CREATE_SEQUENCES_TABLE = """
CREATE TABLE IF NOT EXISTS _dazzle_topic_sequences (
    topic TEXT PRIMARY KEY,
    current_sequence INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass
class ActiveSubscription:
    """An active subscription in the broker."""

    topic: str
    group_id: str
    handler: EventHandler
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class DevBrokerSQLite(EventBus):
    """
    SQLite-backed EventBus implementation for development.

    Uses aiosqlite for async database access. The database file is created
    automatically if it doesn't exist.

    Example:
        async with DevBrokerSQLite("app.db") as bus:
            await bus.publish("app.Order", envelope)

            async def handler(event):
                print(f"Received: {event.event_type}")

            await bus.subscribe("app.Order", "my-consumer", handler)
            await bus.start_consumer_loop()
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        auto_create: bool = True,
    ) -> None:
        """
        Initialize the SQLite broker.

        Args:
            db_path: Path to SQLite database file
            auto_create: Create tables on connect if they don't exist
        """
        import warnings

        warnings.warn(
            "DevBrokerSQLite is deprecated. Use PostgreSQL or Redis.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._db_path = Path(db_path)
        self._auto_create = auto_create
        self._conn: aiosqlite.Connection | None = None
        self._subscriptions: dict[tuple[str, str], ActiveSubscription] = {}
        self._lock = asyncio.Lock()
        self._consumer_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._running = False

    async def connect(self) -> None:
        """Connect to the database and create tables if needed."""
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row

        if self._auto_create:
            await self._create_tables()

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

        if self._conn:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self) -> DevBrokerSQLite:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    @asynccontextmanager
    async def _get_conn(self) -> AsyncIterator[aiosqlite.Connection]:
        """Get database connection with error handling."""
        if self._conn is None:
            raise RuntimeError("DevBrokerSQLite not connected. Call connect() first.")
        yield self._conn

    async def _create_tables(self) -> None:
        """Create required tables if they don't exist."""
        async with self._get_conn() as conn:
            await conn.executescript(
                CREATE_EVENTS_TABLE
                + CREATE_EVENTS_INDEXES
                + CREATE_OFFSETS_TABLE
                + CREATE_DLQ_TABLE
                + CREATE_DLQ_INDEXES
                + CREATE_SEQUENCES_TABLE
            )
            await conn.commit()

    async def _get_next_sequence(self, topic: str) -> int:
        """Get and increment the sequence number for a topic."""
        async with self._get_conn() as conn:
            # Upsert sequence
            await conn.execute(
                """
                INSERT INTO _dazzle_topic_sequences (topic, current_sequence)
                VALUES (?, 1)
                ON CONFLICT(topic) DO UPDATE SET current_sequence = current_sequence + 1
                """,
                (topic,),
            )
            await conn.commit()

            # Get current value
            cursor = await conn.execute(
                "SELECT current_sequence FROM _dazzle_topic_sequences WHERE topic = ?",
                (topic,),
            )
            row = await cursor.fetchone()
            return row["current_sequence"] if row else 1

    async def publish(
        self,
        topic: str,
        envelope: EventEnvelope,
        *,
        transactional: bool = False,
    ) -> None:
        """
        Publish an event to a topic.

        Events are immediately written to the database. If transactional=True,
        the caller should use get_connection() and manage the transaction.
        """
        async with self._lock:
            sequence_num = await self._get_next_sequence(topic)

            async with self._get_conn() as conn:
                await conn.execute(
                    """
                    INSERT INTO _dazzle_events (
                        id, topic, event_type, event_version, key, payload,
                        headers, correlation_id, causation_id, timestamp,
                        producer, sequence_num
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        envelope.timestamp.isoformat(),
                        envelope.producer,
                        sequence_num,
                    ),
                )
                await conn.commit()

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
            async with self._get_conn() as conn:
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO _dazzle_consumer_offsets (topic, group_id, last_sequence)
                    VALUES (?, ?, 0)
                    """,
                    (topic, group_id),
                )
                await conn.commit()

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
        async with self._get_conn() as conn:
            # Get event's sequence number
            cursor = await conn.execute(
                "SELECT sequence_num FROM _dazzle_events WHERE id = ? AND topic = ?",
                (str(event_id), topic),
            )
            row = await cursor.fetchone()
            if not row:
                raise EventNotFoundError(event_id)

            sequence_num = row["sequence_num"]

            # Update consumer offset
            await conn.execute(
                """
                UPDATE _dazzle_consumer_offsets
                SET last_sequence = MAX(last_sequence, ?),
                    last_processed_at = datetime('now')
                WHERE topic = ? AND group_id = ?
                """,
                (sequence_num, topic, group_id),
            )
            await conn.commit()

    async def nack(
        self,
        topic: str,
        group_id: str,
        event_id: UUID,
        reason: NackReason,
    ) -> None:
        """Reject an event, indicating processing failed."""
        async with self._get_conn() as conn:
            # Get event
            cursor = await conn.execute(
                """
                SELECT id, topic, event_type, event_version, key, payload,
                       headers, correlation_id, causation_id, timestamp, producer
                FROM _dazzle_events WHERE id = ?
                """,
                (str(event_id),),
            )
            row = await cursor.fetchone()
            if not row:
                raise EventNotFoundError(event_id)

            envelope = self._row_to_envelope(row)

            if not reason.retryable:
                # Move to DLQ
                await conn.execute(
                    """
                    INSERT INTO _dazzle_dlq (
                        event_id, topic, group_id, envelope,
                        reason_code, reason_message, reason_metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(event_id, group_id) DO UPDATE SET
                        attempts = attempts + 1,
                        reason_code = excluded.reason_code,
                        reason_message = excluded.reason_message
                    """,
                    (
                        str(event_id),
                        topic,
                        group_id,
                        envelope.to_json(),
                        reason.code,
                        reason.message,
                        json.dumps(reason.metadata),
                    ),
                )

                # Advance offset past this event (skip it)
                cursor = await conn.execute(
                    "SELECT sequence_num FROM _dazzle_events WHERE id = ?",
                    (str(event_id),),
                )
                row = await cursor.fetchone()
                if row:
                    await conn.execute(
                        """
                        UPDATE _dazzle_consumer_offsets
                        SET last_sequence = MAX(last_sequence, ?)
                        WHERE topic = ? AND group_id = ?
                        """,
                        (row["sequence_num"], topic, group_id),
                    )

                await conn.commit()
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
        conditions = ["topic = ?"]
        params: list[Any] = [topic]

        if from_timestamp is not None:
            conditions.append("timestamp >= ?")
            params.append(from_timestamp.isoformat())

        if to_timestamp is not None:
            conditions.append("timestamp < ?")
            params.append(to_timestamp.isoformat())

        if from_offset is not None:
            conditions.append("sequence_num >= ?")
            params.append(from_offset)

        if to_offset is not None:
            conditions.append("sequence_num < ?")
            params.append(to_offset)

        if key_filter is not None:
            conditions.append("key = ?")
            params.append(key_filter)

        query = f"""
            SELECT id, topic, event_type, event_version, key, payload,
                   headers, correlation_id, causation_id, timestamp, producer
            FROM _dazzle_events
            WHERE {" AND ".join(conditions)}
            ORDER BY sequence_num ASC
        """

        async with self._get_conn() as conn:
            cursor = await conn.execute(query, params)
            async for row in cursor:
                yield self._row_to_envelope(row)

    async def get_consumer_status(
        self,
        topic: str,
        group_id: str,
    ) -> ConsumerStatus:
        """Get status information for a consumer group."""
        async with self._get_conn() as conn:
            cursor = await conn.execute(
                """
                SELECT last_sequence, last_processed_at
                FROM _dazzle_consumer_offsets
                WHERE topic = ? AND group_id = ?
                """,
                (topic, group_id),
            )
            row = await cursor.fetchone()
            if not row:
                raise ConsumerNotFoundError(topic, group_id)

            # Count pending events
            cursor = await conn.execute(
                """
                SELECT COUNT(*) as pending
                FROM _dazzle_events
                WHERE topic = ? AND sequence_num > ?
                """,
                (topic, row["last_sequence"]),
            )
            pending_row = await cursor.fetchone()

            last_processed = None
            if row["last_processed_at"]:
                last_processed = datetime.fromisoformat(row["last_processed_at"])

            return ConsumerStatus(
                topic=topic,
                group_id=group_id,
                last_offset=row["last_sequence"],
                pending_count=pending_row["pending"] if pending_row else 0,
                last_processed_at=last_processed,
            )

    async def list_topics(self) -> list[str]:
        """List all topics in the bus."""
        async with self._get_conn() as conn:
            cursor = await conn.execute("SELECT DISTINCT topic FROM _dazzle_events ORDER BY topic")
            return [row["topic"] async for row in cursor]

    async def list_consumer_groups(  # type: ignore[override]
        self,
        topic: str | None = None,
    ) -> list[str] | list[dict[str, str]]:
        """
        List consumer groups.

        Args:
            topic: If provided, returns list of group_id strings for that topic.
                   If None, returns list of dicts with topic and group_id.
        """
        async with self._get_conn() as conn:
            if topic:
                cursor = await conn.execute(
                    "SELECT group_id FROM _dazzle_consumer_offsets WHERE topic = ? ORDER BY group_id",
                    (topic,),
                )
                return [row["group_id"] async for row in cursor]
            else:
                cursor = await conn.execute(
                    "SELECT topic, group_id FROM _dazzle_consumer_offsets ORDER BY topic, group_id"
                )
                return [
                    {"topic": row["topic"], "group_id": row["group_id"]} async for row in cursor
                ]

    async def get_consumer_info(self, group_id: str, topic: str) -> dict[str, Any]:
        """Get detailed info for a specific consumer group."""
        async with self._get_conn() as conn:
            cursor = await conn.execute(
                """
                SELECT last_sequence, last_processed_at
                FROM _dazzle_consumer_offsets
                WHERE topic = ? AND group_id = ?
                """,
                (topic, group_id),
            )
            row = await cursor.fetchone()
            if not row:
                return {"last_sequence": 0, "lag": 0}

            # Get current max sequence
            cursor = await conn.execute(
                "SELECT MAX(sequence_num) as max_seq FROM _dazzle_events WHERE topic = ?",
                (topic,),
            )
            max_row = await cursor.fetchone()
            max_seq = max_row["max_seq"] if max_row and max_row["max_seq"] else 0

            return {
                "last_sequence": row["last_sequence"],
                "lag": max_seq - row["last_sequence"],
                "last_processed_at": row["last_processed_at"],
            }

    async def get_dlq_count(self, topic: str | None = None) -> int:
        """Get count of events in dead letter queue."""
        async with self._get_conn() as conn:
            if topic:
                cursor = await conn.execute(
                    "SELECT COUNT(*) as count FROM _dazzle_dlq WHERE topic = ?",
                    (topic,),
                )
            else:
                cursor = await conn.execute("SELECT COUNT(*) as count FROM _dazzle_dlq")
            row = await cursor.fetchone()
            return row["count"] if row else 0

    async def get_event(self, event_id: str) -> EventEnvelope | None:
        """Get a single event by ID."""
        async with self._get_conn() as conn:
            cursor = await conn.execute(
                """
                SELECT id, topic, event_type, event_version, key, payload,
                       headers, correlation_id, causation_id, timestamp, producer
                FROM _dazzle_events WHERE id = ?
                """,
                (event_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_envelope(row)

    async def get_topic_info(self, topic: str) -> dict[str, Any]:
        """Get information about a topic."""
        async with self._get_conn() as conn:
            # Event stats
            cursor = await conn.execute(
                """
                SELECT
                    COUNT(*) as event_count,
                    MIN(timestamp) as oldest_event,
                    MAX(timestamp) as newest_event,
                    MAX(sequence_num) as current_sequence
                FROM _dazzle_events
                WHERE topic = ?
                """,
                (topic,),
            )
            stats = await cursor.fetchone()

            # Consumer groups
            cursor = await conn.execute(
                "SELECT group_id FROM _dazzle_consumer_offsets WHERE topic = ?",
                (topic,),
            )
            groups = [row["group_id"] async for row in cursor]

            # DLQ count
            cursor = await conn.execute(
                "SELECT COUNT(*) as dlq_count FROM _dazzle_dlq WHERE topic = ?",
                (topic,),
            )
            dlq = await cursor.fetchone()

            return {
                "topic": topic,
                "event_count": stats["event_count"] if stats else 0,
                "oldest_event": stats["oldest_event"] if stats else None,
                "newest_event": stats["newest_event"] if stats else None,
                "current_sequence": stats["current_sequence"] if stats else 0,
                "consumer_groups": groups,
                "dlq_count": dlq["dlq_count"] if dlq else 0,
            }

    def _row_to_envelope(self, row: aiosqlite.Row) -> EventEnvelope:
        """Convert a database row to an EventEnvelope."""
        return EventEnvelope(
            event_id=UUID(row["id"]),
            event_type=row["event_type"],
            event_version=row["event_version"],
            key=row["key"],
            payload=json.loads(row["payload"]),
            headers=json.loads(row["headers"]) if row["headers"] else {},
            correlation_id=UUID(row["correlation_id"]) if row["correlation_id"] else None,
            causation_id=UUID(row["causation_id"]) if row["causation_id"] else None,
            timestamp=datetime.fromisoformat(row["timestamp"]),
            producer=row["producer"],
        )

    # Consumer loop methods

    async def start_consumer_loop(self, poll_interval: float = 0.5) -> None:
        """
        Start consumer loops for all subscriptions.

        This runs until stop_consumer_loop() is called or the broker is closed.

        Args:
            poll_interval: Seconds between polls for new events
        """
        self._running = True

        for key, sub in self._subscriptions.items():
            if key not in self._consumer_tasks:
                task = asyncio.create_task(
                    self._consumer_loop(sub.topic, sub.group_id, poll_interval)
                )
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
                    await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                # Log error and continue
                await asyncio.sleep(poll_interval)

    async def poll_and_process(
        self,
        topic: str,
        group_id: str,
        *,
        max_events: int = 10,
    ) -> int:
        """
        Poll for and process pending events.

        This is called by the consumer loop, but can also be called
        directly for testing or manual processing.

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

        async with self._get_conn() as conn:
            # Get current offset
            cursor = await conn.execute(
                "SELECT last_sequence FROM _dazzle_consumer_offsets WHERE topic = ? AND group_id = ?",
                (topic, group_id),
            )
            offset_row = await cursor.fetchone()
            last_sequence = offset_row["last_sequence"] if offset_row else 0

            # Fetch pending events
            cursor = await conn.execute(
                """
                SELECT id, topic, event_type, event_version, key, payload,
                       headers, correlation_id, causation_id, timestamp, producer
                FROM _dazzle_events
                WHERE topic = ? AND sequence_num > ?
                ORDER BY sequence_num ASC
                LIMIT ?
                """,
                (topic, last_sequence, max_events),
            )

            processed = 0
            async for row in cursor:
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
        conditions = []
        params: list[Any] = []

        if topic:
            conditions.append("topic = ?")
            params.append(topic)

        if group_id:
            conditions.append("group_id = ?")
            params.append(group_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        async with self._get_conn() as conn:
            cursor = await conn.execute(
                f"""
                SELECT event_id, topic, group_id, envelope,
                       reason_code, reason_message, attempts, created_at
                FROM _dazzle_dlq
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (*params, limit),
            )

            results = []
            async for row in cursor:
                results.append(
                    {
                        "event_id": row["event_id"],
                        "topic": row["topic"],
                        "group_id": row["group_id"],
                        "envelope": EventEnvelope.from_json(row["envelope"]),
                        "reason_code": row["reason_code"],
                        "reason_message": row["reason_message"],
                        "attempts": row["attempts"],
                        "created_at": row["created_at"],
                    }
                )

            return results

    async def replay_dlq_event(
        self,
        event_id: str,
        group_id: str,
    ) -> bool:
        """
        Replay a single event from the DLQ.

        The event is removed from DLQ and reprocessed through the normal path.

        Returns:
            True if event was found and replayed
        """
        async with self._get_conn() as conn:
            cursor = await conn.execute(
                "SELECT topic, envelope FROM _dazzle_dlq WHERE event_id = ? AND group_id = ?",
                (event_id, group_id),
            )
            row = await cursor.fetchone()
            if not row:
                return False

            topic = row["topic"]
            envelope = EventEnvelope.from_json(row["envelope"])

            # Process through handler
            key = (topic, group_id)
            if key not in self._subscriptions:
                raise ConsumerNotFoundError(topic, group_id)

            handler = self._subscriptions[key].handler

            try:
                await handler(envelope)
                # Remove from DLQ on success
                await conn.execute(
                    "DELETE FROM _dazzle_dlq WHERE event_id = ? AND group_id = ?",
                    (event_id, group_id),
                )
                await conn.commit()
                return True
            except Exception:
                # Update attempts count
                await conn.execute(
                    "UPDATE _dazzle_dlq SET attempts = attempts + 1 WHERE event_id = ? AND group_id = ?",
                    (event_id, group_id),
                )
                await conn.commit()
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
        conditions = []
        params: list[Any] = []

        if topic:
            conditions.append("topic = ?")
            params.append(topic)

        if group_id:
            conditions.append("group_id = ?")
            params.append(group_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        async with self._get_conn() as conn:
            cursor = await conn.execute(
                f"SELECT COUNT(*) as count FROM _dazzle_dlq {where_clause}",
                params,
            )
            row = await cursor.fetchone()
            count = row["count"] if row else 0

            await conn.execute(f"DELETE FROM _dazzle_dlq {where_clause}", params)
            await conn.commit()

            return count
