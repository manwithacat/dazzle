"""
Event Outbox for Transactional Event Publishing.

The outbox pattern ensures events are published reliably by writing them
to a database table in the same transaction as the business operation.
A separate publisher process then drains the outbox to the event bus.

This prevents the "dual write" problem where a database commit succeeds
but event publishing fails (or vice versa).

Rule 1: No dual writes (DB and bus must not drift)

Supports both SQLite (default, local dev) and PostgreSQL (production).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

import aiosqlite

from dazzle_back.events.envelope import EventEnvelope

# Type alias for connection types (aiosqlite or psycopg async)
# Using Any to avoid import issues with psycopg which is optional
OutboxConnection = aiosqlite.Connection | Any


class OutboxStatus(StrEnum):
    """Status of an outbox entry."""

    PENDING = "pending"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass
class OutboxEntry:
    """An entry in the event outbox."""

    id: UUID
    topic: str
    event_type: str
    key: str
    envelope_json: str
    status: OutboxStatus = OutboxStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    published_at: datetime | None = None
    attempts: int = 0
    last_error: str | None = None
    lock_token: str | None = None
    lock_expires_at: datetime | None = None

    @property
    def envelope(self) -> EventEnvelope:
        """Deserialize the envelope from JSON."""
        return EventEnvelope.from_json(self.envelope_json)


# SQL statements for outbox table (SQLite)
CREATE_OUTBOX_TABLE_SQLITE = """
CREATE TABLE IF NOT EXISTS _dazzle_event_outbox (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    event_type TEXT NOT NULL,
    key TEXT NOT NULL,
    envelope_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    published_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    lock_token TEXT,
    lock_expires_at TEXT
);
"""

CREATE_OUTBOX_INDEXES_SQLITE = """
CREATE INDEX IF NOT EXISTS idx_outbox_status ON _dazzle_event_outbox(status);
CREATE INDEX IF NOT EXISTS idx_outbox_created ON _dazzle_event_outbox(created_at);
CREATE INDEX IF NOT EXISTS idx_outbox_topic ON _dazzle_event_outbox(topic);
"""

# SQL statements for outbox table (PostgreSQL)
CREATE_OUTBOX_TABLE_POSTGRES = """
CREATE TABLE IF NOT EXISTS _dazzle_event_outbox (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    event_type TEXT NOT NULL,
    key TEXT NOT NULL,
    envelope_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (now()::text),
    published_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    lock_token TEXT,
    lock_expires_at TEXT
);
"""

CREATE_OUTBOX_INDEXES_POSTGRES = [
    "CREATE INDEX IF NOT EXISTS idx_outbox_status ON _dazzle_event_outbox(status)",
    "CREATE INDEX IF NOT EXISTS idx_outbox_created ON _dazzle_event_outbox(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_outbox_topic ON _dazzle_event_outbox(topic)",
]

# Backwards compatibility
CREATE_OUTBOX_TABLE = CREATE_OUTBOX_TABLE_SQLITE
CREATE_OUTBOX_INDEXES = CREATE_OUTBOX_INDEXES_SQLITE


class EventOutbox:
    """
    Event outbox for transactional publishing.

    Supports both SQLite (default, local dev) and PostgreSQL (production).

    Usage in a service:
        async with db.transaction() as conn:
            # Perform business operation
            await conn.execute("INSERT INTO orders ...")

            # Write event to outbox in same transaction
            await outbox.append(conn, envelope)

    The publisher loop then drains the outbox asynchronously.
    """

    def __init__(
        self,
        table_name: str = "_dazzle_event_outbox",
        use_postgres: bool = False,
    ) -> None:
        """
        Initialize the outbox.

        Args:
            table_name: Name of the outbox table
            use_postgres: Whether to use PostgreSQL instead of SQLite
        """
        self._table = table_name
        self._use_postgres = use_postgres

    async def create_table(self, conn: OutboxConnection) -> None:
        """Create the outbox table if it doesn't exist."""
        if self._use_postgres:
            # PostgreSQL (psycopg async)
            await conn.execute(CREATE_OUTBOX_TABLE_POSTGRES)
            for index_sql in CREATE_OUTBOX_INDEXES_POSTGRES:
                await conn.execute(index_sql)
        else:
            # SQLite (aiosqlite)
            await conn.executescript(CREATE_OUTBOX_TABLE_SQLITE + CREATE_OUTBOX_INDEXES_SQLITE)
            await conn.commit()

    async def append(
        self,
        conn: OutboxConnection,
        envelope: EventEnvelope,
        topic: str | None = None,
    ) -> OutboxEntry:
        """
        Append an event to the outbox.

        MUST be called within a transaction alongside the business operation.
        This ensures atomicity - the event is only visible if the business
        operation commits.

        Args:
            conn: Database connection (should be in a transaction)
            envelope: Event to append
            topic: Override topic (defaults to envelope.topic)

        Returns:
            The created OutboxEntry
        """
        target_topic = topic or envelope.topic
        params = (
            str(envelope.event_id),
            target_topic,
            envelope.event_type,
            envelope.key,
            envelope.to_json(),
            OutboxStatus.PENDING.value,
            datetime.now(UTC).isoformat(),
        )

        if self._use_postgres:
            await conn.execute(
                f"""
                INSERT INTO {self._table} (
                    id, topic, event_type, key, envelope_json, status, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                params,
            )
        else:
            await conn.execute(
                f"""
                INSERT INTO {self._table} (
                    id, topic, event_type, key, envelope_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                params,
            )

        return OutboxEntry(
            id=envelope.event_id,
            topic=target_topic,
            event_type=envelope.event_type,
            key=envelope.key,
            envelope_json=envelope.to_json(),
            status=OutboxStatus.PENDING,
        )

    async def fetch_pending(
        self,
        conn: OutboxConnection,
        *,
        limit: int = 100,
        lock_token: str | None = None,
        lock_duration_seconds: int = 60,
    ) -> list[OutboxEntry]:
        """
        Fetch pending entries for publishing.

        If lock_token is provided, entries are locked to prevent
        concurrent publishers from processing the same events.

        Args:
            conn: Database connection
            limit: Maximum entries to fetch
            lock_token: Token to identify this publisher
            lock_duration_seconds: How long to hold the lock

        Returns:
            List of pending OutboxEntry
        """
        is_postgres = self._use_postgres

        if is_postgres:
            return await self._fetch_pending_postgres(
                conn,
                limit=limit,
                lock_token=lock_token,
                lock_duration_seconds=lock_duration_seconds,
            )
        else:
            return await self._fetch_pending_sqlite(
                conn,
                limit=limit,
                lock_token=lock_token,
                lock_duration_seconds=lock_duration_seconds,
            )

    async def _fetch_pending_sqlite(
        self,
        conn: aiosqlite.Connection,
        *,
        limit: int,
        lock_token: str | None,
        lock_duration_seconds: int,
    ) -> list[OutboxEntry]:
        """Fetch pending entries using SQLite."""
        conn.row_factory = aiosqlite.Row

        if lock_token:
            lock_expires = datetime.now(UTC).isoformat()

            await conn.execute(
                f"""
                UPDATE {self._table}
                SET lock_token = ?,
                    lock_expires_at = datetime('now', '+{lock_duration_seconds} seconds')
                WHERE id IN (
                    SELECT id FROM {self._table}
                    WHERE status = 'pending'
                    AND (lock_token IS NULL OR lock_expires_at < ?)
                    ORDER BY created_at ASC
                    LIMIT ?
                )
                """,
                (lock_token, lock_expires, limit),
            )
            await conn.commit()

            cursor = await conn.execute(
                f"""
                SELECT * FROM {self._table}
                WHERE lock_token = ? AND status = 'pending'
                ORDER BY created_at ASC
                """,
                (lock_token,),
            )
        else:
            cursor = await conn.execute(
                f"""
                SELECT * FROM {self._table}
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            )

        entries = []
        async for row in cursor:
            entries.append(self._row_to_entry(row))

        return entries

    async def _fetch_pending_postgres(
        self,
        conn: Any,
        *,
        limit: int,
        lock_token: str | None,
        lock_duration_seconds: int,
    ) -> list[OutboxEntry]:
        """Fetch pending entries using PostgreSQL."""
        if lock_token:
            lock_expires = datetime.now(UTC).isoformat()

            await conn.execute(
                f"""
                UPDATE {self._table}
                SET lock_token = %s,
                    lock_expires_at = (now() + interval '{lock_duration_seconds} seconds')::text
                WHERE id IN (
                    SELECT id FROM {self._table}
                    WHERE status = 'pending'
                    AND (lock_token IS NULL OR lock_expires_at < %s)
                    ORDER BY created_at ASC
                    LIMIT %s
                )
                """,
                (lock_token, lock_expires, limit),
            )

            cur = await conn.execute(
                f"""
                SELECT * FROM {self._table}
                WHERE lock_token = %s AND status = 'pending'
                ORDER BY created_at ASC
                """,
                (lock_token,),
            )
            rows = await cur.fetchall()
        else:
            cur = await conn.execute(
                f"""
                SELECT * FROM {self._table}
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (limit,),
            )
            rows = await cur.fetchall()

        return [self._row_to_entry(dict(row)) for row in rows]

    async def mark_published(
        self,
        conn: OutboxConnection,
        entry_id: UUID,
    ) -> None:
        """Mark an entry as successfully published."""
        if self._use_postgres:
            await conn.execute(
                f"""
                UPDATE {self._table}
                SET status = 'published',
                    published_at = now()::text,
                    lock_token = NULL
                WHERE id = %s
                """,
                (str(entry_id),),
            )
        else:
            await conn.execute(
                f"""
                UPDATE {self._table}
                SET status = 'published',
                    published_at = datetime('now'),
                    lock_token = NULL
                WHERE id = ?
                """,
                (str(entry_id),),
            )
            await conn.commit()

    async def mark_failed(
        self,
        conn: OutboxConnection,
        entry_id: UUID,
        error: str,
        *,
        max_attempts: int = 5,
    ) -> bool:
        """
        Mark an entry as failed.

        Args:
            conn: Database connection
            entry_id: Entry to mark
            error: Error message
            max_attempts: Maximum retry attempts before permanent failure

        Returns:
            True if entry should be retried, False if max attempts reached
        """
        is_postgres = self._use_postgres

        # Get current attempts
        if is_postgres:
            cur = await conn.execute(
                f"SELECT attempts FROM {self._table} WHERE id = %s",
                (str(entry_id),),
            )
            row = await cur.fetchone()
            attempts = (row["attempts"] if row else 0) + 1
        else:
            cursor = await conn.execute(
                f"SELECT attempts FROM {self._table} WHERE id = ?",
                (str(entry_id),),
            )
            row = await cursor.fetchone()
            attempts = (row[0] if row else 0) + 1

        if attempts >= max_attempts:
            # Permanent failure
            if is_postgres:
                await conn.execute(
                    f"""
                    UPDATE {self._table}
                    SET status = 'failed',
                        attempts = %s,
                        last_error = %s,
                        lock_token = NULL
                    WHERE id = %s
                    """,
                    (attempts, error, str(entry_id)),
                )
            else:
                await conn.execute(
                    f"""
                    UPDATE {self._table}
                    SET status = 'failed',
                        attempts = ?,
                        last_error = ?,
                        lock_token = NULL
                    WHERE id = ?
                    """,
                    (attempts, error, str(entry_id)),
                )
                await conn.commit()
            return False
        else:
            # Retry later
            if is_postgres:
                await conn.execute(
                    f"""
                    UPDATE {self._table}
                    SET attempts = %s,
                        last_error = %s,
                        lock_token = NULL
                    WHERE id = %s
                    """,
                    (attempts, error, str(entry_id)),
                )
            else:
                await conn.execute(
                    f"""
                    UPDATE {self._table}
                    SET attempts = ?,
                        last_error = ?,
                        lock_token = NULL
                    WHERE id = ?
                    """,
                    (attempts, error, str(entry_id)),
                )
                await conn.commit()
            return True

    async def get_stats(
        self,
        conn: OutboxConnection,
    ) -> dict[str, Any]:
        """Get outbox statistics."""
        is_postgres = self._use_postgres

        query = f"""
            SELECT
                status,
                COUNT(*) as count,
                MIN(created_at) as oldest,
                MAX(created_at) as newest
            FROM {self._table}
            GROUP BY status
        """

        stats: dict[str, Any] = {
            "pending": 0,
            "publishing": 0,
            "published": 0,
            "failed": 0,
            "oldest_pending": None,
        }

        if is_postgres:
            cur = await conn.execute(query)
            rows = await cur.fetchall()
            for row in rows:
                status = row["status"]
                stats[status] = row["count"]
                if status == "pending" and row["oldest"]:
                    stats["oldest_pending"] = row["oldest"]
        else:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(query)
            async for row in cursor:
                status = row["status"]
                stats[status] = row["count"]
                if status == "pending" and row["oldest"]:
                    stats["oldest_pending"] = row["oldest"]

        return stats

    async def cleanup_published(
        self,
        conn: OutboxConnection,
        *,
        older_than_hours: int = 24,
    ) -> int:
        """
        Delete old published entries.

        Args:
            conn: Database connection
            older_than_hours: Delete entries older than this

        Returns:
            Number of entries deleted
        """
        is_postgres = self._use_postgres

        if is_postgres:
            cur = await conn.execute(
                f"""
                DELETE FROM {self._table}
                WHERE status = 'published'
                AND published_at < (now() - interval '{older_than_hours} hours')::text
                """
            )
            return cur.rowcount
        else:
            cursor = await conn.execute(
                f"""
                DELETE FROM {self._table}
                WHERE status = 'published'
                AND published_at < datetime('now', '-{older_than_hours} hours')
                """
            )
            await conn.commit()
            return int(cursor.rowcount)

    async def get_failed_entries(
        self,
        conn: OutboxConnection,
        *,
        limit: int = 100,
    ) -> list[OutboxEntry]:
        """Get failed entries for inspection or manual retry."""
        is_postgres = self._use_postgres

        if is_postgres:
            cur = await conn.execute(
                f"""
                SELECT * FROM {self._table}
                WHERE status = 'failed'
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = await cur.fetchall()
            return [self._row_to_entry(dict(row)) for row in rows]
        else:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                f"""
                SELECT * FROM {self._table}
                WHERE status = 'failed'
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [self._row_to_entry(row) async for row in cursor]

    async def get_recent_entries(
        self,
        conn: OutboxConnection,
        *,
        limit: int = 10,
    ) -> list[OutboxEntry]:
        """Get recent entries regardless of status (for event explorer)."""
        is_postgres = self._use_postgres

        if is_postgres:
            cur = await conn.execute(
                f"""
                SELECT * FROM {self._table}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = await cur.fetchall()
            return [self._row_to_entry(dict(row)) for row in rows]
        else:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                f"""
                SELECT * FROM {self._table}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [self._row_to_entry(row) async for row in cursor]

    async def retry_failed(
        self,
        conn: OutboxConnection,
        entry_id: UUID,
    ) -> bool:
        """
        Reset a failed entry for retry.

        Returns:
            True if entry was found and reset
        """
        is_postgres = self._use_postgres

        if is_postgres:
            cur = await conn.execute(
                f"""
                UPDATE {self._table}
                SET status = 'pending', attempts = 0
                WHERE id = %s AND status = 'failed'
                """,
                (str(entry_id),),
            )
            return cur.rowcount > 0
        else:
            cursor = await conn.execute(
                f"""
                UPDATE {self._table}
                SET status = 'pending', attempts = 0
                WHERE id = ? AND status = 'failed'
                """,
                (str(entry_id),),
            )
            await conn.commit()
            return int(cursor.rowcount) > 0

    def _row_to_entry(self, row: aiosqlite.Row | dict[str, Any]) -> OutboxEntry:
        """Convert a database row to an OutboxEntry."""
        return OutboxEntry(
            id=UUID(row["id"]),
            topic=row["topic"],
            event_type=row["event_type"],
            key=row["key"],
            envelope_json=row["envelope_json"],
            status=OutboxStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            published_at=(
                datetime.fromisoformat(row["published_at"]) if row["published_at"] else None
            ),
            attempts=row["attempts"],
            last_error=row["last_error"],
            lock_token=row["lock_token"],
            lock_expires_at=(
                datetime.fromisoformat(row["lock_expires_at"]) if row["lock_expires_at"] else None
            ),
        )
