"""
Event Inbox for Idempotent Consumer Processing.

The inbox pattern tracks which events have been processed by each consumer,
enabling at-least-once delivery with idempotent handling. When an event
arrives, the consumer checks the inbox first - if already processed, it's
skipped.

Rule 2: At-least-once delivery is assumed; consumers must be idempotent
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class ProcessingResult(StrEnum):
    """Result of processing an event."""

    SUCCESS = "success"
    SKIPPED = "skipped"  # Business logic decided not to process
    ERROR = "error"  # Processing failed


@dataclass
class InboxEntry:
    """A record of a processed event."""

    event_id: UUID
    consumer_name: str
    processed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    result: ProcessingResult = ProcessingResult.SUCCESS
    result_data: dict[str, Any] | None = None


# SQL statements for inbox table
CREATE_INBOX_TABLE = """
CREATE TABLE IF NOT EXISTS _dazzle_event_inbox (
    event_id TEXT NOT NULL,
    consumer_name TEXT NOT NULL,
    processed_at TEXT NOT NULL DEFAULT (datetime('now')),
    result TEXT NOT NULL DEFAULT 'success',
    result_data TEXT,
    PRIMARY KEY (event_id, consumer_name)
);
"""

CREATE_INBOX_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_inbox_consumer ON _dazzle_event_inbox(consumer_name);
CREATE INDEX IF NOT EXISTS idx_inbox_processed ON _dazzle_event_inbox(processed_at);
"""

# SQL statements for inbox table (PostgreSQL)
CREATE_INBOX_TABLE_POSTGRES = """
CREATE TABLE IF NOT EXISTS _dazzle_event_inbox (
    event_id TEXT NOT NULL,
    consumer_name TEXT NOT NULL,
    processed_at TEXT NOT NULL DEFAULT (now()::text),
    result TEXT NOT NULL DEFAULT 'success',
    result_data TEXT,
    PRIMARY KEY (event_id, consumer_name)
);
"""

CREATE_INBOX_INDEXES_POSTGRES = (
    "CREATE INDEX IF NOT EXISTS idx_inbox_consumer ON _dazzle_event_inbox(consumer_name)",
    "CREATE INDEX IF NOT EXISTS idx_inbox_processed ON _dazzle_event_inbox(processed_at)",
)


class EventInbox:
    """
    Event inbox for idempotent consumer processing.

    The inbox implements a simple deduplication mechanism:
    1. Before processing, check if event_id + consumer_name exists
    2. If exists, skip processing (already handled)
    3. If not exists, process and mark as processed

    Usage:
        async with inbox.acquire(conn, event_id, "my-consumer") as should_process:
            if should_process:
                # Process the event
                await handle_event(event)
                # Mark success
                await inbox.mark_processed(conn, event_id, "my-consumer")

    Or use the simpler pattern:
        if await inbox.should_process(conn, event_id, "my-consumer"):
            try:
                await handle_event(event)
                await inbox.mark_processed(conn, event_id, "my-consumer")
            except Exception as e:
                await inbox.mark_error(conn, event_id, "my-consumer", str(e))
    """

    def __init__(
        self,
        table_name: str = "_dazzle_event_inbox",
        placeholder: str = "?",
        backend_type: str = "sqlite",
    ) -> None:
        """
        Initialize the inbox.

        Args:
            table_name: Name of the inbox table
            placeholder: SQL placeholder style ("?" for SQLite, "%s" for Postgres)
            backend_type: Database backend type ("sqlite" or "postgres")
        """
        self._table = table_name
        self._ph = placeholder
        self._backend_type = backend_type

    async def create_table(self, conn: Any) -> None:
        """Create the inbox table if it doesn't exist."""
        if self._backend_type == "postgres":
            await conn.execute(CREATE_INBOX_TABLE_POSTGRES)
            for idx_sql in CREATE_INBOX_INDEXES_POSTGRES:
                await conn.execute(idx_sql)
            await conn.commit()
        else:
            await conn.executescript(CREATE_INBOX_TABLE + CREATE_INBOX_INDEXES)
            await conn.commit()

    async def is_processed(
        self,
        conn: Any,
        event_id: UUID,
        consumer_name: str,
    ) -> bool:
        """
        Check if an event has already been processed by this consumer.

        Args:
            conn: Database connection
            event_id: Event identifier
            consumer_name: Name of the consumer

        Returns:
            True if already processed, False otherwise
        """
        ph = self._ph
        cursor = await conn.execute(
            f"""
            SELECT 1 FROM {self._table}
            WHERE event_id = {ph} AND consumer_name = {ph}
            """,
            (str(event_id), consumer_name),
        )
        row = await cursor.fetchone()
        return row is not None

    async def should_process(
        self,
        conn: Any,
        event_id: UUID,
        consumer_name: str,
    ) -> bool:
        """
        Check if an event should be processed (inverse of is_processed).

        This is the typical entry point for idempotent processing.

        Args:
            conn: Database connection
            event_id: Event identifier
            consumer_name: Name of the consumer

        Returns:
            True if event should be processed, False if already handled
        """
        return not await self.is_processed(conn, event_id, consumer_name)

    async def mark_processed(
        self,
        conn: Any,
        event_id: UUID,
        consumer_name: str,
        *,
        result: ProcessingResult = ProcessingResult.SUCCESS,
        result_data: dict[str, Any] | None = None,
    ) -> bool:
        """
        Mark an event as processed.

        Uses INSERT with conflict handling to be idempotent - multiple calls
        with the same event_id + consumer_name are safe.

        Args:
            conn: Database connection
            event_id: Event identifier
            consumer_name: Name of the consumer
            result: Processing result
            result_data: Optional result metadata

        Returns:
            True if newly marked, False if already existed
        """
        import json

        result_json = json.dumps(result_data) if result_data else None
        ph = self._ph

        if self._backend_type == "postgres":
            sql = f"""
                INSERT INTO {self._table}
                (event_id, consumer_name, processed_at, result, result_data)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
                ON CONFLICT DO NOTHING
            """
        else:
            sql = f"""
                INSERT OR IGNORE INTO {self._table}
                (event_id, consumer_name, processed_at, result, result_data)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
            """

        cursor = await conn.execute(
            sql,
            (
                str(event_id),
                consumer_name,
                datetime.now(UTC).isoformat(),
                result.value,
                result_json,
            ),
        )
        await conn.commit()

        return int(cursor.rowcount) > 0

    async def mark_error(
        self,
        conn: Any,
        event_id: UUID,
        consumer_name: str,
        error_message: str,
    ) -> bool:
        """
        Mark an event as processed with an error.

        This still marks it as processed to prevent infinite retries.
        The error is recorded for debugging.

        Args:
            conn: Database connection
            event_id: Event identifier
            consumer_name: Name of the consumer
            error_message: Error description

        Returns:
            True if newly marked, False if already existed
        """
        return await self.mark_processed(
            conn,
            event_id,
            consumer_name,
            result=ProcessingResult.ERROR,
            result_data={"error": error_message},
        )

    async def get_entry(
        self,
        conn: Any,
        event_id: UUID,
        consumer_name: str,
    ) -> InboxEntry | None:
        """Get an inbox entry if it exists."""
        import json

        try:
            import aiosqlite

            conn.row_factory = aiosqlite.Row
        except ImportError:
            pass

        ph = self._ph
        cursor = await conn.execute(
            f"""
            SELECT * FROM {self._table}
            WHERE event_id = {ph} AND consumer_name = {ph}
            """,
            (str(event_id), consumer_name),
        )
        row = await cursor.fetchone()

        if not row:
            return None

        return InboxEntry(
            event_id=UUID(row["event_id"]),
            consumer_name=row["consumer_name"],
            processed_at=datetime.fromisoformat(row["processed_at"]),
            result=ProcessingResult(row["result"]),
            result_data=json.loads(row["result_data"]) if row["result_data"] else None,
        )

    async def delete_entry(
        self,
        conn: Any,
        event_id: UUID,
        consumer_name: str,
    ) -> bool:
        """
        Delete an inbox entry (allows reprocessing).

        Use with caution - this enables re-processing of an event.

        Returns:
            True if entry was deleted, False if not found
        """
        ph = self._ph
        cursor = await conn.execute(
            f"""
            DELETE FROM {self._table}
            WHERE event_id = {ph} AND consumer_name = {ph}
            """,
            (str(event_id), consumer_name),
        )
        await conn.commit()
        return int(cursor.rowcount) > 0

    async def get_stats(
        self,
        conn: Any,
        consumer_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Get inbox statistics.

        Args:
            conn: Database connection
            consumer_name: Optional filter by consumer

        Returns:
            Statistics dict with counts by result
        """
        try:
            import aiosqlite

            conn.row_factory = aiosqlite.Row
        except ImportError:
            pass

        ph = self._ph
        if consumer_name:
            cursor = await conn.execute(
                f"""
                SELECT result, COUNT(*) as count
                FROM {self._table}
                WHERE consumer_name = {ph}
                GROUP BY result
                """,
                (consumer_name,),
            )
        else:
            cursor = await conn.execute(
                f"""
                SELECT result, COUNT(*) as count
                FROM {self._table}
                GROUP BY result
                """
            )

        stats: dict[str, Any] = {
            "success": 0,
            "skipped": 0,
            "error": 0,
            "total": 0,
        }

        async for row in cursor:
            stats[row["result"]] = row["count"]
            stats["total"] += row["count"]

        return stats

    async def cleanup_old_entries(
        self,
        conn: Any,
        *,
        older_than_days: int = 7,
    ) -> int:
        """
        Delete old processed entries.

        Args:
            conn: Database connection
            older_than_days: Delete entries older than this

        Returns:
            Number of entries deleted
        """
        from datetime import timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat()
        ph = self._ph
        cursor = await conn.execute(
            f"""
            DELETE FROM {self._table}
            WHERE processed_at < {ph}
            """,
            (cutoff,),
        )
        await conn.commit()
        return int(cursor.rowcount)

    async def get_recent_entries(
        self,
        conn: Any,
        consumer_name: str,
        *,
        limit: int = 100,
    ) -> list[InboxEntry]:
        """Get recent entries for a consumer."""
        import json

        try:
            import aiosqlite

            conn.row_factory = aiosqlite.Row
        except ImportError:
            pass

        ph = self._ph
        cursor = await conn.execute(
            f"""
            SELECT * FROM {self._table}
            WHERE consumer_name = {ph}
            ORDER BY processed_at DESC
            LIMIT {ph}
            """,
            (consumer_name, limit),
        )

        entries = []
        async for row in cursor:
            entries.append(
                InboxEntry(
                    event_id=UUID(row["event_id"]),
                    consumer_name=row["consumer_name"],
                    processed_at=datetime.fromisoformat(row["processed_at"]),
                    result=ProcessingResult(row["result"]),
                    result_data=(json.loads(row["result_data"]) if row["result_data"] else None),
                )
            )

        return entries

    async def list_consumers(
        self,
        conn: Any,
    ) -> list[str]:
        """Get list of all consumer names that have processed events."""
        cursor = await conn.execute(
            f"SELECT DISTINCT consumer_name FROM {self._table} ORDER BY consumer_name"
        )
        return [row[0] async for row in cursor]
