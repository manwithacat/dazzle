"""
Tests for presence tracker.

Tests presence join/leave, heartbeat, and cleanup.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest

from dazzle_back.runtime.presence_tracker import (
    PresenceEntry,
    PresenceTracker,
    create_presence_tracker,
    get_presence_tracker,
    reset_presence_tracker,
    set_presence_tracker,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_global_tracker() -> Any:
    """Reset global presence tracker before each test."""
    reset_presence_tracker()
    yield
    reset_presence_tracker()


@pytest.fixture
def tracker() -> Any:
    """Create a presence tracker for testing."""
    return create_presence_tracker(timeout_seconds=30)


@pytest.fixture
def mock_ws_manager() -> Any:
    """Create a mock WebSocket manager."""
    manager = AsyncMock()
    manager.broadcast = AsyncMock(return_value=2)
    manager.send_to_connection = AsyncMock(return_value=True)
    return manager


# =============================================================================
# PresenceEntry Tests
# =============================================================================


class TestPresenceEntry:
    """Tests for PresenceEntry class."""

    def test_create_entry(self) -> None:
        """Test creating a presence entry."""
        entry = PresenceEntry(
            user_id="user_123",
            user_name="Alice",
            resource="workspace/tasks",
            connection_id="conn_456",
        )

        assert entry.user_id == "user_123"
        assert entry.user_name == "Alice"
        assert entry.resource == "workspace/tasks"
        assert entry.connection_id == "conn_456"
        assert isinstance(entry.joined_at, datetime)
        assert isinstance(entry.last_seen, datetime)

    def test_to_dict(self) -> None:
        """Test converting entry to dict."""
        entry = PresenceEntry(
            user_id="user_123",
            user_name="Alice",
            resource="workspace/tasks",
            connection_id="conn_456",
            metadata={"color": "blue"},
        )

        d = entry.to_dict()

        assert d["userId"] == "user_123"
        assert d["userName"] == "Alice"
        assert d["resource"] == "workspace/tasks"
        assert "joinedAt" in d
        assert "lastSeen" in d
        assert d["metadata"]["color"] == "blue"

    def test_update_heartbeat(self) -> None:
        """Test updating heartbeat."""
        entry = PresenceEntry(
            user_id="user_123",
            user_name="Alice",
            resource="workspace/tasks",
            connection_id="conn_456",
        )
        old_last_seen = entry.last_seen

        entry.update_heartbeat()

        assert entry.last_seen >= old_last_seen


# =============================================================================
# PresenceTracker Join/Leave Tests
# =============================================================================


class TestPresenceJoinLeave:
    """Tests for join/leave operations."""

    @pytest.mark.asyncio
    async def test_join(self, tracker: Any) -> None:
        """Test joining a resource."""
        entry = await tracker.join(
            resource="workspace/tasks",
            user_id="user_123",
            connection_id="conn_456",
            user_name="Alice",
        )

        assert entry is not None
        assert entry.user_id == "user_123"
        assert tracker.is_present("workspace/tasks", "user_123")

    @pytest.mark.asyncio
    async def test_leave(self, tracker: Any) -> None:
        """Test leaving a resource."""
        await tracker.join("workspace/tasks", "user_123", "conn_456")

        result = await tracker.leave("workspace/tasks", "user_123")

        assert result is True
        assert not tracker.is_present("workspace/tasks", "user_123")

    @pytest.mark.asyncio
    async def test_leave_not_present(self, tracker: Any) -> None:
        """Test leaving when not present."""
        result = await tracker.leave("workspace/tasks", "user_123")

        assert result is False

    @pytest.mark.asyncio
    async def test_multiple_users_same_resource(self, tracker: Any) -> None:
        """Test multiple users on same resource."""
        await tracker.join("workspace/tasks", "user_1", "conn_1")
        await tracker.join("workspace/tasks", "user_2", "conn_2")
        await tracker.join("workspace/tasks", "user_3", "conn_3")

        users = tracker.get_present("workspace/tasks")

        assert len(users) == 3
        assert {u.user_id for u in users} == {"user_1", "user_2", "user_3"}

    @pytest.mark.asyncio
    async def test_same_user_multiple_resources(self, tracker: Any) -> None:
        """Test same user on multiple resources."""
        await tracker.join("workspace/tasks", "user_123", "conn_1")
        await tracker.join("workspace/projects", "user_123", "conn_1")

        resources = tracker.get_user_resources("user_123")

        assert len(resources) == 2
        assert set(resources) == {"workspace/tasks", "workspace/projects"}


# =============================================================================
# PresenceTracker Query Tests
# =============================================================================


class TestPresenceQueries:
    """Tests for presence queries."""

    @pytest.mark.asyncio
    async def test_get_present(self, tracker: Any) -> None:
        """Test getting all present users."""
        await tracker.join("workspace/tasks", "user_1", "conn_1", "Alice")
        await tracker.join("workspace/tasks", "user_2", "conn_2", "Bob")

        users = tracker.get_present("workspace/tasks")

        assert len(users) == 2

    @pytest.mark.asyncio
    async def test_get_present_empty(self, tracker: Any) -> None:
        """Test getting present users from empty resource."""
        users = tracker.get_present("workspace/tasks")

        assert users == []

    @pytest.mark.asyncio
    async def test_get_present_user_ids(self, tracker: Any) -> None:
        """Test getting just user IDs."""
        await tracker.join("workspace/tasks", "user_1", "conn_1")
        await tracker.join("workspace/tasks", "user_2", "conn_2")

        user_ids = tracker.get_present_user_ids("workspace/tasks")

        assert set(user_ids) == {"user_1", "user_2"}

    @pytest.mark.asyncio
    async def test_is_present(self, tracker: Any) -> None:
        """Test checking if user is present."""
        await tracker.join("workspace/tasks", "user_123", "conn_456")

        assert tracker.is_present("workspace/tasks", "user_123") is True
        assert tracker.is_present("workspace/tasks", "user_456") is False
        assert tracker.is_present("workspace/other", "user_123") is False

    @pytest.mark.asyncio
    async def test_get_entry(self, tracker: Any) -> None:
        """Test getting specific entry."""
        await tracker.join("workspace/tasks", "user_123", "conn_456", "Alice")

        entry = tracker.get_entry("workspace/tasks", "user_123")

        assert entry is not None
        assert entry.user_name == "Alice"

    @pytest.mark.asyncio
    async def test_get_entry_not_found(self, tracker: Any) -> None:
        """Test getting non-existent entry."""
        entry = tracker.get_entry("workspace/tasks", "user_123")

        assert entry is None


# =============================================================================
# Heartbeat Tests
# =============================================================================


class TestHeartbeat:
    """Tests for heartbeat functionality."""

    @pytest.mark.asyncio
    async def test_heartbeat(self, tracker: Any) -> None:
        """Test updating heartbeat."""
        await tracker.join("workspace/tasks", "user_123", "conn_456")
        entry = tracker.get_entry("workspace/tasks", "user_123")
        old_last_seen = entry.last_seen

        result = tracker.heartbeat("workspace/tasks", "user_123")

        assert result is True
        entry = tracker.get_entry("workspace/tasks", "user_123")
        assert entry.last_seen >= old_last_seen

    @pytest.mark.asyncio
    async def test_heartbeat_not_present(self, tracker: Any) -> None:
        """Test heartbeat when not present."""
        result = tracker.heartbeat("workspace/tasks", "user_123")

        assert result is False

    @pytest.mark.asyncio
    async def test_heartbeat_all_for_connection(self, tracker: Any) -> None:
        """Test heartbeat for all presence of a connection."""
        await tracker.join("workspace/tasks", "user_123", "conn_456")
        await tracker.join("workspace/projects", "user_123", "conn_456")

        updated = tracker.heartbeat_all_for_connection("conn_456")

        assert updated == 2


# =============================================================================
# Connection Cleanup Tests
# =============================================================================


class TestConnectionCleanup:
    """Tests for connection cleanup."""

    @pytest.mark.asyncio
    async def test_leave_all_for_connection(self, tracker: Any) -> None:
        """Test leaving all resources for a connection."""
        await tracker.join("workspace/tasks", "user_123", "conn_456")
        await tracker.join("workspace/projects", "user_123", "conn_456")

        removed = await tracker.leave_all_for_connection("conn_456")

        assert len(removed) == 2
        assert not tracker.is_present("workspace/tasks", "user_123")
        assert not tracker.is_present("workspace/projects", "user_123")

    @pytest.mark.asyncio
    async def test_leave_all_only_removes_own_entries(self, tracker: Any) -> None:
        """Test that leave_all only removes the connection's entries."""
        await tracker.join("workspace/tasks", "user_1", "conn_1")
        await tracker.join("workspace/tasks", "user_2", "conn_2")

        removed = await tracker.leave_all_for_connection("conn_1")

        assert len(removed) == 1
        assert not tracker.is_present("workspace/tasks", "user_1")
        assert tracker.is_present("workspace/tasks", "user_2")


# =============================================================================
# Stale Cleanup Tests
# =============================================================================


class TestStaleCleanup:
    """Tests for stale entry cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_stale(self, tracker: Any) -> None:
        """Test cleaning up stale entries."""
        await tracker.join("workspace/tasks", "user_123", "conn_456")

        # Manually set last_seen to past
        entry = tracker.get_entry("workspace/tasks", "user_123")
        entry.last_seen = datetime.now(UTC) - timedelta(seconds=60)

        removed = await tracker.cleanup_stale()

        assert len(removed) == 1
        assert removed[0] == ("workspace/tasks", "user_123")
        assert not tracker.is_present("workspace/tasks", "user_123")

    @pytest.mark.asyncio
    async def test_cleanup_keeps_active(self, tracker: Any) -> None:
        """Test that active entries are not cleaned up."""
        await tracker.join("workspace/tasks", "user_123", "conn_456")

        removed = await tracker.cleanup_stale()

        assert len(removed) == 0
        assert tracker.is_present("workspace/tasks", "user_123")


# =============================================================================
# WebSocket Broadcasting Tests
# =============================================================================


class TestWebSocketBroadcasting:
    """Tests for WebSocket broadcasting integration."""

    @pytest.mark.asyncio
    async def test_broadcast_on_join(self, tracker: Any, mock_ws_manager: Any) -> None:
        """Test that join broadcasts to presence channel."""
        tracker.set_websocket_manager(mock_ws_manager)

        await tracker.join("workspace/tasks", "user_123", "conn_456", "Alice")

        mock_ws_manager.broadcast.assert_called_once()
        call_args = mock_ws_manager.broadcast.call_args[0]
        assert call_args[0] == "presence:workspace/tasks"

    @pytest.mark.asyncio
    async def test_broadcast_on_leave(self, tracker: Any, mock_ws_manager: Any) -> None:
        """Test that leave broadcasts to presence channel."""
        tracker.set_websocket_manager(mock_ws_manager)
        await tracker.join("workspace/tasks", "user_123", "conn_456")
        mock_ws_manager.broadcast.reset_mock()

        await tracker.leave("workspace/tasks", "user_123")

        mock_ws_manager.broadcast.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_sync(self, tracker: Any, mock_ws_manager: Any) -> None:
        """Test sending presence sync to a connection."""
        tracker.set_websocket_manager(mock_ws_manager)
        await tracker.join("workspace/tasks", "user_1", "conn_1", "Alice")
        await tracker.join("workspace/tasks", "user_2", "conn_2", "Bob")

        await tracker.send_sync("conn_new", "workspace/tasks")

        mock_ws_manager.send_to_connection.assert_called()
        call_args = mock_ws_manager.send_to_connection.call_args[0]
        assert call_args[0] == "conn_new"


# =============================================================================
# Statistics Tests
# =============================================================================


class TestStatistics:
    """Tests for tracker statistics."""

    @pytest.mark.asyncio
    async def test_get_stats(self, tracker: Any) -> None:
        """Test getting statistics."""
        await tracker.join("workspace/tasks", "user_1", "conn_1")
        await tracker.join("workspace/tasks", "user_2", "conn_2")
        await tracker.join("workspace/projects", "user_1", "conn_1")

        stats = tracker.get_stats()

        assert stats["resources"] == 2
        assert stats["entries"] == 3
        assert stats["connections"] == 2


# =============================================================================
# Global Presence Tracker Tests
# =============================================================================


class TestGlobalPresenceTracker:
    """Tests for global presence tracker functions."""

    def test_get_presence_tracker_creates_default(self) -> None:
        """Test that get_presence_tracker creates a default tracker."""
        tracker = get_presence_tracker()

        assert tracker is not None
        assert isinstance(tracker, PresenceTracker)

    def test_get_presence_tracker_returns_same(self) -> None:
        """Test that get_presence_tracker returns the same instance."""
        tracker1 = get_presence_tracker()
        tracker2 = get_presence_tracker()

        assert tracker1 is tracker2

    def test_set_presence_tracker(self) -> None:
        """Test setting a custom tracker."""
        custom_tracker = create_presence_tracker(timeout_seconds=60)
        set_presence_tracker(custom_tracker)

        assert get_presence_tracker() is custom_tracker

    def test_reset_presence_tracker(self) -> None:
        """Test resetting the global tracker."""
        tracker1 = get_presence_tracker()
        reset_presence_tracker()
        tracker2 = get_presence_tracker()

        assert tracker1 is not tracker2
