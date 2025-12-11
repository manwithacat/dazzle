"""
Unit tests for DAZZLE messaging outbox pattern (v0.9.0).

Tests the transactional outbox for reliable message delivery.
"""

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dazzle_dnr_back.channels.outbox import (
    OutboxMessage,
    OutboxRepository,
    OutboxStatus,
    create_outbox_message,
)
from dazzle_dnr_back.runtime.repository import DatabaseManager


@pytest.fixture
def db_manager():
    """Create a temporary database manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        manager = DatabaseManager(str(db_path))
        yield manager


@pytest.fixture
def outbox_repo(db_manager):
    """Create an outbox repository."""
    return OutboxRepository(db_manager)


class TestOutboxMessage:
    """Tests for OutboxMessage dataclass."""

    def test_create_outbox_message(self):
        """Test creating an outbox message."""
        msg = create_outbox_message(
            channel_name="notifications",
            operation_name="welcome",
            message_type="WelcomeEmail",
            payload={"to": "user@example.com", "subject": "Welcome!"},
            recipient="user@example.com",
        )

        assert msg.channel_name == "notifications"
        assert msg.operation_name == "welcome"
        assert msg.message_type == "WelcomeEmail"
        assert msg.recipient == "user@example.com"
        assert msg.status == OutboxStatus.PENDING
        assert msg.attempts == 0

    def test_message_to_dict(self):
        """Test converting message to dictionary."""
        msg = create_outbox_message(
            channel_name="notifications",
            operation_name="welcome",
            message_type="WelcomeEmail",
            payload={"to": "user@example.com"},
            recipient="user@example.com",
            metadata={"source": "signup"},
        )

        d = msg.to_dict()
        assert d["channel_name"] == "notifications"
        assert d["status"] == "pending"
        assert json.loads(d["payload"]) == {"to": "user@example.com"}
        assert json.loads(d["metadata"]) == {"source": "signup"}

    def test_message_from_dict(self):
        """Test creating message from dictionary."""
        d = {
            "id": "test-id",
            "channel_name": "notifications",
            "operation_name": "welcome",
            "message_type": "WelcomeEmail",
            "payload": '{"to": "user@example.com"}',
            "recipient": "user@example.com",
            "status": "pending",
            "created_at": "2024-01-15T10:00:00+00:00",
            "updated_at": "2024-01-15T10:00:00+00:00",
            "attempts": 0,
            "max_attempts": 3,
            "metadata": "{}",
        }

        msg = OutboxMessage.from_dict(d)
        assert msg.id == "test-id"
        assert msg.channel_name == "notifications"
        assert msg.payload == {"to": "user@example.com"}
        assert msg.status == OutboxStatus.PENDING

    def test_message_with_scheduled_delivery(self):
        """Test message with scheduled delivery time."""
        scheduled = datetime.now(UTC) + timedelta(hours=1)
        msg = create_outbox_message(
            channel_name="notifications",
            operation_name="reminder",
            message_type="Reminder",
            payload={"message": "Don't forget!"},
            recipient="user@example.com",
            scheduled_for=scheduled,
        )

        assert msg.scheduled_for == scheduled


class TestOutboxRepository:
    """Tests for OutboxRepository."""

    def test_table_created(self, outbox_repo, db_manager):
        """Test that outbox table is created."""
        with db_manager.connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='_dazzle_outbox'"
            )
            assert cursor.fetchone() is not None

    def test_create_message(self, outbox_repo):
        """Test creating a message in the outbox."""
        msg = create_outbox_message(
            channel_name="notifications",
            operation_name="welcome",
            message_type="WelcomeEmail",
            payload={"to": "user@example.com"},
            recipient="user@example.com",
        )

        created = outbox_repo.create(msg)
        assert created.id == msg.id

        # Verify it was stored
        retrieved = outbox_repo.get(msg.id)
        assert retrieved is not None
        assert retrieved.channel_name == "notifications"

    def test_get_pending_messages(self, outbox_repo):
        """Test getting pending messages."""
        # Create some messages
        for i in range(5):
            msg = create_outbox_message(
                channel_name="notifications",
                operation_name="test",
                message_type="TestMessage",
                payload={"index": i},
                recipient=f"user{i}@example.com",
            )
            outbox_repo.create(msg)

        pending = outbox_repo.get_pending(limit=10)
        assert len(pending) == 5
        assert all(m.status == OutboxStatus.PENDING for m in pending)

    def test_get_pending_by_channel(self, outbox_repo):
        """Test filtering pending messages by channel."""
        # Create messages for different channels
        for channel in ["email", "email", "queue"]:
            msg = create_outbox_message(
                channel_name=channel,
                operation_name="test",
                message_type="TestMessage",
                payload={},
                recipient="user@example.com",
            )
            outbox_repo.create(msg)

        email_pending = outbox_repo.get_pending(channel_name="email")
        assert len(email_pending) == 2

        queue_pending = outbox_repo.get_pending(channel_name="queue")
        assert len(queue_pending) == 1

    def test_mark_processing(self, outbox_repo):
        """Test marking a message as processing."""
        msg = create_outbox_message(
            channel_name="notifications",
            operation_name="test",
            message_type="TestMessage",
            payload={},
            recipient="user@example.com",
        )
        outbox_repo.create(msg)

        # Claim the message
        claimed = outbox_repo.mark_processing(msg.id)
        assert claimed is True

        # Verify status changed
        retrieved = outbox_repo.get(msg.id)
        assert retrieved.status == OutboxStatus.PROCESSING

        # Second claim should fail
        claimed_again = outbox_repo.mark_processing(msg.id)
        assert claimed_again is False

    def test_mark_sent(self, outbox_repo):
        """Test marking a message as sent."""
        msg = create_outbox_message(
            channel_name="notifications",
            operation_name="test",
            message_type="TestMessage",
            payload={},
            recipient="user@example.com",
        )
        outbox_repo.create(msg)

        outbox_repo.mark_sent(msg.id)

        retrieved = outbox_repo.get(msg.id)
        assert retrieved.status == OutboxStatus.SENT
        assert retrieved.attempts == 1

    def test_mark_failed_with_retry(self, outbox_repo):
        """Test marking a message as failed (with retry)."""
        msg = create_outbox_message(
            channel_name="notifications",
            operation_name="test",
            message_type="TestMessage",
            payload={},
            recipient="user@example.com",
        )
        outbox_repo.create(msg)

        outbox_repo.mark_failed(msg.id, "Connection timeout")

        retrieved = outbox_repo.get(msg.id)
        # Should go back to pending for retry
        assert retrieved.status == OutboxStatus.PENDING
        assert retrieved.attempts == 1
        assert retrieved.last_error == "Connection timeout"

    def test_mark_failed_dead_letter(self, outbox_repo):
        """Test message moves to dead letter after max attempts."""
        msg = OutboxMessage(
            id="test-id",
            channel_name="notifications",
            operation_name="test",
            message_type="TestMessage",
            payload={},
            recipient="user@example.com",
            attempts=2,  # Already tried twice
            max_attempts=3,
        )
        outbox_repo.create(msg)

        # Third failure should move to dead letter
        outbox_repo.mark_failed(msg.id, "Final failure")

        retrieved = outbox_repo.get(msg.id)
        assert retrieved.status == OutboxStatus.DEAD_LETTER
        assert retrieved.attempts == 3

    def test_get_dead_letters(self, outbox_repo):
        """Test getting dead letter messages."""
        # Create a dead letter message directly
        msg = OutboxMessage(
            id="dead-id",
            channel_name="notifications",
            operation_name="test",
            message_type="TestMessage",
            payload={},
            recipient="user@example.com",
            status=OutboxStatus.DEAD_LETTER,
            attempts=3,
            max_attempts=3,
            last_error="All retries failed",
        )
        outbox_repo.create(msg)

        dead_letters = outbox_repo.get_dead_letters()
        assert len(dead_letters) == 1
        assert dead_letters[0].id == "dead-id"

    def test_retry_dead_letter(self, outbox_repo):
        """Test retrying a dead letter message."""
        msg = OutboxMessage(
            id="dead-id",
            channel_name="notifications",
            operation_name="test",
            message_type="TestMessage",
            payload={},
            recipient="user@example.com",
            status=OutboxStatus.DEAD_LETTER,
            attempts=3,
            max_attempts=3,
        )
        outbox_repo.create(msg)

        retried = outbox_repo.retry_dead_letter(msg.id)
        assert retried is True

        retrieved = outbox_repo.get(msg.id)
        assert retrieved.status == OutboxStatus.PENDING
        assert retrieved.attempts == 0
        assert retrieved.last_error is None

    def test_get_stats(self, outbox_repo):
        """Test getting outbox statistics."""
        # Create messages with different statuses
        statuses = [
            OutboxStatus.PENDING,
            OutboxStatus.PENDING,
            OutboxStatus.SENT,
            OutboxStatus.FAILED,
        ]
        for i, status in enumerate(statuses):
            msg = OutboxMessage(
                id=f"msg-{i}",
                channel_name="notifications",
                operation_name="test",
                message_type="TestMessage",
                payload={},
                recipient="user@example.com",
                status=status,
            )
            outbox_repo.create(msg)

        stats = outbox_repo.get_stats()
        assert stats.get("pending", 0) == 2
        assert stats.get("sent", 0) == 1
        assert stats.get("failed", 0) == 1

    def test_scheduled_messages_not_returned(self, outbox_repo):
        """Test that future scheduled messages aren't returned as pending."""
        # Create a message scheduled for the future
        msg = create_outbox_message(
            channel_name="notifications",
            operation_name="test",
            message_type="TestMessage",
            payload={},
            recipient="user@example.com",
            scheduled_for=datetime.now(UTC) + timedelta(hours=1),
        )
        outbox_repo.create(msg)

        pending = outbox_repo.get_pending()
        assert len(pending) == 0

    def test_create_within_transaction(self, outbox_repo, db_manager):
        """Test creating message within an existing transaction."""
        msg = create_outbox_message(
            channel_name="notifications",
            operation_name="test",
            message_type="TestMessage",
            payload={},
            recipient="user@example.com",
        )

        # Create within transaction
        with db_manager.connection() as conn:
            outbox_repo.create(msg, conn=conn)
            # Message should be visible within transaction
            cursor = conn.execute("SELECT id FROM _dazzle_outbox WHERE id = ?", (msg.id,))
            assert cursor.fetchone() is not None

        # Verify still there after commit
        retrieved = outbox_repo.get(msg.id)
        assert retrieved is not None
