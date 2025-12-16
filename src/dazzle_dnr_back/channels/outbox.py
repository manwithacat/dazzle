"""
Transactional outbox pattern for DAZZLE messaging.

The outbox pattern ensures reliable message delivery by:
1. Writing messages to an outbox table within the same transaction as business data
2. A background processor reads from the outbox and sends to providers
3. Messages are marked as sent/failed with retry support

This provides at-least-once delivery semantics with transactional consistency.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle_dnr_back.runtime.repository import DatabaseManager

logger = logging.getLogger("dazzle.channels.outbox")


class OutboxStatus(str, Enum):
    """Status of an outbox message."""

    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


@dataclass
class OutboxMessage:
    """A message in the outbox.

    Attributes:
        id: Unique message identifier
        channel_name: Name of the channel to send through
        operation_name: Name of the send operation
        message_type: Type of message (from DSL)
        payload: Serialized message payload
        recipient: Primary recipient (for deduplication)
        status: Current message status
        created_at: When the message was created
        updated_at: When the message was last updated
        scheduled_for: When to send the message (for delayed delivery)
        attempts: Number of send attempts
        max_attempts: Maximum retry attempts
        last_error: Last error message
        correlation_id: For tracking related messages
        build_id: Build identifier for observability
        metadata: Additional metadata
    """

    id: str
    channel_name: str
    operation_name: str
    message_type: str
    payload: dict[str, Any]
    recipient: str
    status: OutboxStatus = OutboxStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    scheduled_for: datetime | None = None
    attempts: int = 0
    max_attempts: int = 3
    last_error: str | None = None
    correlation_id: str | None = None
    build_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "channel_name": self.channel_name,
            "operation_name": self.operation_name,
            "message_type": self.message_type,
            "payload": json.dumps(self.payload),
            "recipient": self.recipient,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "scheduled_for": self.scheduled_for.isoformat() if self.scheduled_for else None,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "last_error": self.last_error,
            "correlation_id": self.correlation_id,
            "build_id": self.build_id,
            "metadata": json.dumps(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutboxMessage:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            channel_name=data["channel_name"],
            operation_name=data["operation_name"],
            message_type=data["message_type"],
            payload=json.loads(data["payload"])
            if isinstance(data["payload"], str)
            else data["payload"],
            recipient=data["recipient"],
            status=OutboxStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            scheduled_for=(
                datetime.fromisoformat(data["scheduled_for"]) if data.get("scheduled_for") else None
            ),
            attempts=data.get("attempts", 0),
            max_attempts=data.get("max_attempts", 3),
            last_error=data.get("last_error"),
            correlation_id=data.get("correlation_id"),
            build_id=data.get("build_id"),
            metadata=json.loads(data["metadata"])
            if isinstance(data.get("metadata"), str)
            else data.get("metadata", {}),
        )


class OutboxRepository:
    """Repository for outbox message persistence.

    Handles all database operations for the outbox table.
    """

    TABLE_NAME = "_dazzle_outbox"

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Ensure outbox table exists."""
        sql = f"""
        CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
            id TEXT PRIMARY KEY,
            channel_name TEXT NOT NULL,
            operation_name TEXT NOT NULL,
            message_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            recipient TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            scheduled_for TEXT,
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3,
            last_error TEXT,
            correlation_id TEXT,
            build_id TEXT,
            metadata TEXT
        )
        """
        with self.db.connection() as conn:
            conn.execute(sql)

            # Create indexes for efficient querying
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_status "
                f"ON {self.TABLE_NAME}(status)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_channel "
                f"ON {self.TABLE_NAME}(channel_name)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_scheduled "
                f"ON {self.TABLE_NAME}(scheduled_for)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_recipient "
                f"ON {self.TABLE_NAME}(recipient, channel_name)"
            )

    def create(
        self, message: OutboxMessage, conn: sqlite3.Connection | None = None
    ) -> OutboxMessage:
        """Create a new outbox message.

        Args:
            message: Message to create
            conn: Optional connection for transaction participation

        Returns:
            Created message
        """
        data = message.to_dict()
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        sql = f"INSERT INTO {self.TABLE_NAME} ({columns}) VALUES ({placeholders})"

        if conn:
            conn.execute(sql, list(data.values()))
        else:
            with self.db.connection() as c:
                c.execute(sql, list(data.values()))

        logger.debug(
            f"Created outbox message {message.id} for {message.channel_name}:{message.operation_name}"
        )
        return message

    def get(self, message_id: str) -> OutboxMessage | None:
        """Get a message by ID."""
        sql = f"SELECT * FROM {self.TABLE_NAME} WHERE id = ?"
        with self.db.connection() as conn:
            cursor = conn.execute(sql, (message_id,))
            row = cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return OutboxMessage.from_dict(dict(zip(columns, row, strict=False)))
        return None

    def get_pending(
        self,
        limit: int = 100,
        channel_name: str | None = None,
    ) -> list[OutboxMessage]:
        """Get pending messages ready to be sent.

        Args:
            limit: Maximum messages to return
            channel_name: Optional filter by channel

        Returns:
            List of pending messages
        """
        now = datetime.now(UTC).isoformat()
        sql = f"""
            SELECT * FROM {self.TABLE_NAME}
            WHERE status = 'pending'
            AND (scheduled_for IS NULL OR scheduled_for <= ?)
        """
        params: list[Any] = [now]

        if channel_name:
            sql += " AND channel_name = ?"
            params.append(channel_name)

        sql += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)

        with self.db.connection() as conn:
            cursor = conn.execute(sql, params)
            columns = [desc[0] for desc in cursor.description]
            return [
                OutboxMessage.from_dict(dict(zip(columns, row, strict=False)))
                for row in cursor.fetchall()
            ]

    def mark_processing(self, message_id: str) -> bool:
        """Mark a message as processing (claim it).

        Uses optimistic locking to prevent concurrent processing.

        Returns:
            True if successfully claimed, False if already claimed
        """
        sql = f"""
            UPDATE {self.TABLE_NAME}
            SET status = 'processing', updated_at = ?
            WHERE id = ? AND status = 'pending'
        """
        with self.db.connection() as conn:
            cursor = conn.execute(sql, (datetime.now(UTC).isoformat(), message_id))
            return cursor.rowcount > 0

    def mark_sent(self, message_id: str) -> None:
        """Mark a message as successfully sent."""
        sql = f"""
            UPDATE {self.TABLE_NAME}
            SET status = 'sent', updated_at = ?, attempts = attempts + 1
            WHERE id = ?
        """
        with self.db.connection() as conn:
            conn.execute(sql, (datetime.now(UTC).isoformat(), message_id))

        logger.info(f"Outbox message {message_id} sent successfully")

    def mark_failed(self, message_id: str, error: str) -> None:
        """Mark a message as failed with retry logic.

        If max attempts reached, moves to dead letter status.
        """
        message = self.get(message_id)
        if not message:
            return

        new_attempts = message.attempts + 1
        if new_attempts >= message.max_attempts:
            new_status = OutboxStatus.DEAD_LETTER.value
            logger.error(
                f"Outbox message {message_id} moved to dead letter after {new_attempts} attempts"
            )
        else:
            new_status = OutboxStatus.PENDING.value
            logger.warning(
                f"Outbox message {message_id} failed (attempt {new_attempts}/{message.max_attempts}): {error}"
            )

        sql = f"""
            UPDATE {self.TABLE_NAME}
            SET status = ?, updated_at = ?, attempts = ?, last_error = ?
            WHERE id = ?
        """
        with self.db.connection() as conn:
            conn.execute(
                sql,
                (new_status, datetime.now(UTC).isoformat(), new_attempts, error, message_id),
            )

    def get_dead_letters(self, limit: int = 100) -> list[OutboxMessage]:
        """Get messages that have failed permanently."""
        sql = f"""
            SELECT * FROM {self.TABLE_NAME}
            WHERE status = 'dead_letter'
            ORDER BY updated_at DESC
            LIMIT ?
        """
        with self.db.connection() as conn:
            cursor = conn.execute(sql, (limit,))
            columns = [desc[0] for desc in cursor.description]
            return [
                OutboxMessage.from_dict(dict(zip(columns, row, strict=False)))
                for row in cursor.fetchall()
            ]

    def retry_dead_letter(self, message_id: str) -> bool:
        """Retry a dead letter message.

        Resets the message to pending status with fresh attempts.
        """
        sql = f"""
            UPDATE {self.TABLE_NAME}
            SET status = 'pending', updated_at = ?, attempts = 0, last_error = NULL
            WHERE id = ? AND status = 'dead_letter'
        """
        with self.db.connection() as conn:
            cursor = conn.execute(sql, (datetime.now(UTC).isoformat(), message_id))
            return cursor.rowcount > 0

    def get_stats(self) -> dict[str, int]:
        """Get outbox statistics by status."""
        sql = f"""
            SELECT status, COUNT(*) as count
            FROM {self.TABLE_NAME}
            GROUP BY status
        """
        with self.db.connection() as conn:
            cursor = conn.execute(sql)
            return {row[0]: row[1] for row in cursor.fetchall()}

    def get_recent(self, limit: int = 20) -> list[OutboxMessage]:
        """Get recent messages across all statuses.

        Args:
            limit: Maximum messages to return

        Returns:
            List of recent messages, newest first
        """
        sql = f"""
            SELECT * FROM {self.TABLE_NAME}
            ORDER BY created_at DESC
            LIMIT ?
        """
        with self.db.connection() as conn:
            cursor = conn.execute(sql, (limit,))
            columns = [desc[0] for desc in cursor.description]
            return [
                OutboxMessage.from_dict(dict(zip(columns, row, strict=False)))
                for row in cursor.fetchall()
            ]

    def cleanup_sent(self, older_than_days: int = 7) -> int:
        """Remove old sent messages.

        Args:
            older_than_days: Delete messages sent more than this many days ago

        Returns:
            Number of deleted messages
        """
        from datetime import timedelta

        cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat()
        sql = f"""
            DELETE FROM {self.TABLE_NAME}
            WHERE status = 'sent' AND updated_at < ?
        """
        with self.db.connection() as conn:
            cursor = conn.execute(sql, (cutoff,))
            count = cursor.rowcount

        if count > 0:
            logger.info(f"Cleaned up {count} sent messages older than {older_than_days} days")

        return count


def create_outbox_message(
    channel_name: str,
    operation_name: str,
    message_type: str,
    payload: dict[str, Any],
    recipient: str,
    *,
    scheduled_for: datetime | None = None,
    correlation_id: str | None = None,
    build_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> OutboxMessage:
    """Create a new outbox message.

    This is the primary factory function for creating outbox messages.

    Args:
        channel_name: Name of the channel to send through
        operation_name: Name of the send operation
        message_type: Type of message (from DSL)
        payload: Message payload dictionary
        recipient: Primary recipient for deduplication
        scheduled_for: Optional delayed delivery time
        correlation_id: Optional correlation ID for tracking
        build_id: Optional build identifier
        metadata: Optional additional metadata

    Returns:
        New OutboxMessage ready to be persisted
    """
    return OutboxMessage(
        id=str(uuid.uuid4()),
        channel_name=channel_name,
        operation_name=operation_name,
        message_type=message_type,
        payload=payload,
        recipient=recipient,
        scheduled_for=scheduled_for,
        correlation_id=correlation_id,
        build_id=build_id,
        metadata=metadata or {},
    )
