"""
Unit tests for DAZZLE ChannelManager (v0.9.0).

Tests channel manager initialization, sending, and status reporting.
"""

import tempfile
from pathlib import Path

import pytest

from dazzle.core.ir import ChannelKind, ChannelSpec
from dazzle_back.channels import (
    ChannelManager,
    create_channel_manager,
)
from dazzle_back.channels.detection import DetectionResult, ProviderStatus
from dazzle_back.channels.outbox import OutboxStatus
from dazzle_back.runtime.repository import DatabaseManager


@pytest.fixture
def db_manager():
    """Create a temporary database manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        manager = DatabaseManager(str(db_path))
        yield manager


@pytest.fixture
def email_channel_spec():
    """Create an email channel spec."""
    return ChannelSpec(
        name="notifications",
        kind=ChannelKind.EMAIL,
        provider="auto",
    )


@pytest.fixture
def mock_file_detection():
    """Mock file email detection."""
    return DetectionResult(
        provider_name="file",
        status=ProviderStatus.AVAILABLE,
        connection_url="file://.dazzle/mail",
        detection_method="fallback",
    )


class TestChannelManagerCreation:
    """Tests for ChannelManager creation."""

    def test_create_channel_manager(self, db_manager, email_channel_spec):
        """Test creating a channel manager."""
        manager = create_channel_manager(
            db_manager=db_manager,
            channel_specs=[email_channel_spec],
            build_id="test-build-123",
        )

        assert manager is not None
        assert manager.db_manager is db_manager
        assert manager.build_id == "test-build-123"
        assert not manager._initialized

    def test_create_without_database(self, email_channel_spec):
        """Test creating without database."""
        manager = ChannelManager(
            db_manager=None,
            channel_specs=[email_channel_spec],
        )

        assert manager.db_manager is None


class TestChannelManagerInitialization:
    """Tests for ChannelManager initialization."""

    @pytest.mark.asyncio
    async def test_initialize_creates_outbox(self, db_manager, email_channel_spec):
        """Test initialization creates outbox repository."""
        manager = ChannelManager(
            db_manager=db_manager,
            channel_specs=[email_channel_spec],
        )

        await manager.initialize()

        assert manager._initialized
        assert manager._outbox is not None

    @pytest.mark.asyncio
    async def test_initialize_resolves_channels(self, db_manager, email_channel_spec):
        """Test initialization resolves channels."""
        manager = ChannelManager(
            db_manager=db_manager,
            channel_specs=[email_channel_spec],
        )

        await manager.initialize()

        assert "notifications" in manager._resolutions
        assert "notifications" in manager._statuses

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, db_manager, email_channel_spec):
        """Test initialization is idempotent."""
        manager = ChannelManager(
            db_manager=db_manager,
            channel_specs=[email_channel_spec],
        )

        await manager.initialize()
        await manager.initialize()  # Second call should be no-op

        assert manager._initialized


class TestChannelStatus:
    """Tests for channel status reporting."""

    @pytest.mark.asyncio
    async def test_get_channel_status(self, db_manager, email_channel_spec):
        """Test getting channel status."""
        manager = ChannelManager(
            db_manager=db_manager,
            channel_specs=[email_channel_spec],
        )

        await manager.initialize()

        status = manager.get_channel_status("notifications")
        assert status is not None
        assert status.name == "notifications"
        assert status.kind == "email"
        assert status.provider_name in ["file", "mailpit"]  # Depends on detection

    @pytest.mark.asyncio
    async def test_get_all_statuses(self, db_manager):
        """Test getting all channel statuses."""
        specs = [
            ChannelSpec(name="email1", kind=ChannelKind.EMAIL, provider="auto"),
            ChannelSpec(name="email2", kind=ChannelKind.EMAIL, provider="auto"),
        ]

        manager = ChannelManager(
            db_manager=db_manager,
            channel_specs=specs,
        )

        await manager.initialize()

        statuses = manager.get_all_statuses()
        assert len(statuses) == 2

    @pytest.mark.asyncio
    async def test_channel_status_to_dict(self, db_manager, email_channel_spec):
        """Test ChannelStatus to_dict."""
        manager = ChannelManager(
            db_manager=db_manager,
            channel_specs=[email_channel_spec],
        )

        await manager.initialize()

        status = manager.get_channel_status("notifications")
        d = status.to_dict()

        assert "name" in d
        assert "kind" in d
        assert "provider_name" in d
        assert "status" in d


class TestMessageSending:
    """Tests for message sending."""

    @pytest.mark.asyncio
    async def test_send_queues_message(self, db_manager, email_channel_spec):
        """Test sending a message queues it in outbox."""
        manager = ChannelManager(
            db_manager=db_manager,
            channel_specs=[email_channel_spec],
        )

        await manager.initialize()

        msg = await manager.send(
            channel="notifications",
            operation="welcome",
            message_type="WelcomeEmail",
            payload={"to": "user@example.com", "subject": "Hello"},
            recipient="user@example.com",
        )

        assert msg is not None
        assert msg.channel_name == "notifications"
        assert msg.operation_name == "welcome"
        assert msg.status == OutboxStatus.PENDING

    @pytest.mark.asyncio
    async def test_send_with_metadata(self, db_manager, email_channel_spec):
        """Test sending with metadata."""
        manager = ChannelManager(
            db_manager=db_manager,
            channel_specs=[email_channel_spec],
        )

        await manager.initialize()

        msg = await manager.send(
            channel="notifications",
            operation="welcome",
            message_type="WelcomeEmail",
            payload={"to": "user@example.com"},
            recipient="user@example.com",
            correlation_id="corr-123",
            metadata={"source": "signup"},
        )

        assert msg.correlation_id == "corr-123"
        assert msg.metadata["source"] == "signup"

    @pytest.mark.asyncio
    async def test_send_unknown_channel_raises(self, db_manager, email_channel_spec):
        """Test sending to unknown channel raises error."""
        manager = ChannelManager(
            db_manager=db_manager,
            channel_specs=[email_channel_spec],
        )

        await manager.initialize()

        with pytest.raises(ValueError) as exc_info:
            await manager.send(
                channel="unknown",
                operation="test",
                message_type="Test",
                payload={},
                recipient="test@example.com",
            )

        assert "unknown" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_not_initialized_raises(self, db_manager, email_channel_spec):
        """Test sending before initialization raises error."""
        manager = ChannelManager(
            db_manager=db_manager,
            channel_specs=[email_channel_spec],
        )

        with pytest.raises(RuntimeError) as exc_info:
            await manager.send(
                channel="notifications",
                operation="test",
                message_type="Test",
                payload={},
                recipient="test@example.com",
            )

        assert "not initialized" in str(exc_info.value)


class TestOutboxStats:
    """Tests for outbox statistics."""

    @pytest.mark.asyncio
    async def test_get_outbox_stats(self, db_manager, email_channel_spec):
        """Test getting outbox stats."""
        manager = ChannelManager(
            db_manager=db_manager,
            channel_specs=[email_channel_spec],
        )

        await manager.initialize()

        # Send some messages
        await manager.send(
            channel="notifications",
            operation="test",
            message_type="Test",
            payload={},
            recipient="test@example.com",
        )

        stats = manager.get_outbox_stats()
        assert "pending" in stats
        assert stats["pending"] >= 1

    @pytest.mark.asyncio
    async def test_get_outbox_stats_without_db(self, email_channel_spec):
        """Test getting outbox stats without database."""
        manager = ChannelManager(
            db_manager=None,
            channel_specs=[email_channel_spec],
        )

        await manager.initialize()

        stats = manager.get_outbox_stats()
        assert stats == {}

    @pytest.mark.asyncio
    async def test_get_recent_messages(self, db_manager, email_channel_spec):
        """Test getting recent messages."""
        manager = ChannelManager(
            db_manager=db_manager,
            channel_specs=[email_channel_spec],
        )

        await manager.initialize()

        # Send some messages
        for i in range(3):
            await manager.send(
                channel="notifications",
                operation="test",
                message_type="Test",
                payload={"subject": f"Test {i}"},
                recipient=f"test{i}@example.com",
            )

        recent = manager.get_recent_messages(limit=10)
        assert len(recent) == 3

    @pytest.mark.asyncio
    async def test_get_recent_messages_without_db(self, email_channel_spec):
        """Test getting recent messages without database."""
        manager = ChannelManager(
            db_manager=None,
            channel_specs=[email_channel_spec],
        )

        await manager.initialize()

        recent = manager.get_recent_messages()
        assert recent == []


class TestTemplateRendering:
    """Tests for template rendering through manager."""

    @pytest.mark.asyncio
    async def test_render_message(self, db_manager, email_channel_spec):
        """Test rendering a message template."""
        manager = ChannelManager(
            db_manager=db_manager,
            channel_specs=[email_channel_spec],
        )

        result = manager.render_message(
            "Hello {{ name }}!",
            {"name": "World"},
        )

        assert result == "Hello World!"


class TestShutdown:
    """Tests for manager shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown(self, db_manager, email_channel_spec):
        """Test manager shutdown."""
        manager = ChannelManager(
            db_manager=db_manager,
            channel_specs=[email_channel_spec],
        )

        await manager.initialize()
        await manager.shutdown()

        assert not manager._initialized
