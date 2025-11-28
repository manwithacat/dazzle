"""
Tests for WebSocket manager.

Tests connection management, channel subscriptions, and message routing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from dazzle_dnr_back.runtime.websocket_manager import (
    WebSocketManager,
    Connection,
    RealtimeMessage,
    MessageType,
    create_websocket_manager,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def ws_manager():
    """Create a WebSocket manager for testing."""
    return create_websocket_manager(
        max_subscriptions=10,
        heartbeat_timeout=30,
    )


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


# =============================================================================
# Connection Tests
# =============================================================================


class TestConnection:
    """Tests for Connection class."""

    def test_create_connection(self, mock_websocket):
        """Test creating a connection."""
        conn = Connection(
            id="conn_123",
            websocket=mock_websocket,
            user_id="user_456",
            user_name="Alice",
        )

        assert conn.id == "conn_123"
        assert conn.user_id == "user_456"
        assert conn.user_name == "Alice"
        assert len(conn.subscriptions) == 0
        assert isinstance(conn.connected_at, datetime)
        assert isinstance(conn.last_heartbeat, datetime)

    def test_update_heartbeat(self, mock_websocket):
        """Test updating heartbeat."""
        conn = Connection(id="conn_123", websocket=mock_websocket)
        old_heartbeat = conn.last_heartbeat

        # Wait a tiny bit then update
        conn.update_heartbeat()

        assert conn.last_heartbeat >= old_heartbeat


# =============================================================================
# RealtimeMessage Tests
# =============================================================================


class TestRealtimeMessage:
    """Tests for RealtimeMessage class."""

    def test_create_message(self):
        """Test creating a message."""
        msg = RealtimeMessage(
            type=MessageType.ENTITY_CREATED,
            channel="entity:Task",
            payload={"id": "123", "title": "Test"},
        )

        assert msg.type == MessageType.ENTITY_CREATED
        assert msg.channel == "entity:Task"
        assert msg.payload["title"] == "Test"
        assert msg.timestamp > 0

    def test_to_dict(self):
        """Test converting message to dict."""
        msg = RealtimeMessage(
            type=MessageType.SUBSCRIBE,
            channel="entity:Task",
            request_id="req_123",
        )

        d = msg.to_dict()

        assert d["type"] == "subscribe"
        assert d["channel"] == "entity:Task"
        assert d["requestId"] == "req_123"
        assert "timestamp" in d

    def test_from_dict(self):
        """Test creating message from dict."""
        d = {
            "type": "entity:updated",
            "channel": "entity:Task",
            "payload": {"id": "123"},
            "requestId": "req_456",
            "timestamp": 1234567890000,
        }

        msg = RealtimeMessage.from_dict(d)

        assert msg.type == "entity:updated"
        assert msg.channel == "entity:Task"
        assert msg.payload["id"] == "123"
        assert msg.request_id == "req_456"
        assert msg.timestamp == 1234567890000


# =============================================================================
# WebSocketManager Tests
# =============================================================================


class TestWebSocketManager:
    """Tests for WebSocketManager class."""

    @pytest.mark.asyncio
    async def test_connect(self, ws_manager, mock_websocket):
        """Test accepting a connection."""
        connection_id = await ws_manager.connect(
            mock_websocket,
            user_id="user_123",
            user_name="Alice",
        )

        assert connection_id is not None
        assert ws_manager.connection_count == 1

        mock_websocket.accept.assert_called_once()
        mock_websocket.send_json.assert_called_once()

        # Verify connected message
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "connected"
        assert call_args["payload"]["connectionId"] == connection_id
        assert call_args["payload"]["userId"] == "user_123"

    @pytest.mark.asyncio
    async def test_disconnect(self, ws_manager, mock_websocket):
        """Test disconnecting."""
        connection_id = await ws_manager.connect(mock_websocket, user_id="user_123")
        assert ws_manager.connection_count == 1

        await ws_manager.disconnect(connection_id)

        assert ws_manager.connection_count == 0
        assert ws_manager.get_connection(connection_id) is None

    @pytest.mark.asyncio
    async def test_get_connection(self, ws_manager, mock_websocket):
        """Test getting a connection."""
        connection_id = await ws_manager.connect(mock_websocket, user_id="user_123")

        conn = ws_manager.get_connection(connection_id)

        assert conn is not None
        assert conn.id == connection_id
        assert conn.user_id == "user_123"

    @pytest.mark.asyncio
    async def test_get_user_connections(self, ws_manager, mock_websocket):
        """Test getting all connections for a user."""
        # Connect same user twice
        conn1 = await ws_manager.connect(mock_websocket, user_id="user_123")
        mock_websocket2 = AsyncMock()
        mock_websocket2.accept = AsyncMock()
        mock_websocket2.send_json = AsyncMock()
        conn2 = await ws_manager.connect(mock_websocket2, user_id="user_123")

        connections = ws_manager.get_user_connections("user_123")

        assert len(connections) == 2
        assert {c.id for c in connections} == {conn1, conn2}


# =============================================================================
# Channel Subscription Tests
# =============================================================================


class TestChannelSubscriptions:
    """Tests for channel subscriptions."""

    @pytest.mark.asyncio
    async def test_subscribe(self, ws_manager, mock_websocket):
        """Test subscribing to a channel."""
        connection_id = await ws_manager.connect(mock_websocket)

        result = await ws_manager.subscribe(connection_id, "entity:Task")

        assert result is True
        assert ws_manager.is_subscribed(connection_id, "entity:Task")
        assert ws_manager.channel_count == 1

        # Verify subscribed message
        assert mock_websocket.send_json.call_count == 2  # connected + subscribed
        last_call = mock_websocket.send_json.call_args[0][0]
        assert last_call["type"] == "subscribed"
        assert last_call["channel"] == "entity:Task"

    @pytest.mark.asyncio
    async def test_unsubscribe(self, ws_manager, mock_websocket):
        """Test unsubscribing from a channel."""
        connection_id = await ws_manager.connect(mock_websocket)
        await ws_manager.subscribe(connection_id, "entity:Task")

        result = await ws_manager.unsubscribe(connection_id, "entity:Task")

        assert result is True
        assert not ws_manager.is_subscribed(connection_id, "entity:Task")
        assert ws_manager.channel_count == 0

    @pytest.mark.asyncio
    async def test_subscription_limit(self, ws_manager, mock_websocket):
        """Test subscription limit is enforced."""
        connection_id = await ws_manager.connect(mock_websocket)

        # Subscribe to max channels
        for i in range(10):
            await ws_manager.subscribe(connection_id, f"channel:{i}")

        # Try to subscribe to one more
        result = await ws_manager.subscribe(connection_id, "channel:extra")

        assert result is False
        assert not ws_manager.is_subscribed(connection_id, "channel:extra")

    @pytest.mark.asyncio
    async def test_get_channel_subscribers(self, ws_manager, mock_websocket):
        """Test getting channel subscribers."""
        conn1 = await ws_manager.connect(mock_websocket)
        mock_websocket2 = AsyncMock()
        mock_websocket2.accept = AsyncMock()
        mock_websocket2.send_json = AsyncMock()
        conn2 = await ws_manager.connect(mock_websocket2)

        await ws_manager.subscribe(conn1, "entity:Task")
        await ws_manager.subscribe(conn2, "entity:Task")

        subscribers = ws_manager.get_channel_subscribers("entity:Task")

        assert len(subscribers) == 2
        assert set(subscribers) == {conn1, conn2}

    @pytest.mark.asyncio
    async def test_disconnect_removes_subscriptions(self, ws_manager, mock_websocket):
        """Test that disconnect removes all subscriptions."""
        connection_id = await ws_manager.connect(mock_websocket)
        await ws_manager.subscribe(connection_id, "entity:Task")
        await ws_manager.subscribe(connection_id, "entity:User")

        await ws_manager.disconnect(connection_id)

        assert ws_manager.channel_count == 0


# =============================================================================
# Message Handling Tests
# =============================================================================


class TestMessageHandling:
    """Tests for message handling."""

    @pytest.mark.asyncio
    async def test_handle_ping(self, ws_manager, mock_websocket):
        """Test handling ping message."""
        connection_id = await ws_manager.connect(mock_websocket)
        mock_websocket.send_json.reset_mock()

        await ws_manager.handle_message(connection_id, {"type": "ping"})

        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "pong"

    @pytest.mark.asyncio
    async def test_handle_subscribe(self, ws_manager, mock_websocket):
        """Test handling subscribe message."""
        connection_id = await ws_manager.connect(mock_websocket)

        await ws_manager.handle_message(connection_id, {
            "type": "subscribe",
            "channel": "entity:Task",
            "requestId": "req_123",
        })

        assert ws_manager.is_subscribed(connection_id, "entity:Task")

    @pytest.mark.asyncio
    async def test_handle_unsubscribe(self, ws_manager, mock_websocket):
        """Test handling unsubscribe message."""
        connection_id = await ws_manager.connect(mock_websocket)
        await ws_manager.subscribe(connection_id, "entity:Task")

        await ws_manager.handle_message(connection_id, {
            "type": "unsubscribe",
            "channel": "entity:Task",
        })

        assert not ws_manager.is_subscribed(connection_id, "entity:Task")

    @pytest.mark.asyncio
    async def test_handle_unknown_message(self, ws_manager, mock_websocket):
        """Test handling unknown message type."""
        connection_id = await ws_manager.connect(mock_websocket)
        mock_websocket.send_json.reset_mock()

        await ws_manager.handle_message(connection_id, {
            "type": "unknown_type",
            "requestId": "req_123",
        })

        # Should send error
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "error"
        assert "UNKNOWN_MESSAGE_TYPE" in call_args["payload"]["code"]

    @pytest.mark.asyncio
    async def test_custom_handler(self, ws_manager, mock_websocket):
        """Test registering and using custom handler."""
        handler_called = []

        async def custom_handler(conn_id, message):
            handler_called.append((conn_id, message.type))

        ws_manager.register_handler("custom:event", custom_handler)
        connection_id = await ws_manager.connect(mock_websocket)

        await ws_manager.handle_message(connection_id, {
            "type": "custom:event",
            "payload": {"data": "test"},
        })

        assert len(handler_called) == 1
        assert handler_called[0][0] == connection_id
        assert handler_called[0][1] == "custom:event"


# =============================================================================
# Broadcasting Tests
# =============================================================================


class TestBroadcasting:
    """Tests for message broadcasting."""

    @pytest.mark.asyncio
    async def test_broadcast_to_channel(self, ws_manager, mock_websocket):
        """Test broadcasting to channel subscribers."""
        conn1 = await ws_manager.connect(mock_websocket)
        mock_websocket2 = AsyncMock()
        mock_websocket2.accept = AsyncMock()
        mock_websocket2.send_json = AsyncMock()
        conn2 = await ws_manager.connect(mock_websocket2)

        await ws_manager.subscribe(conn1, "entity:Task")
        await ws_manager.subscribe(conn2, "entity:Task")

        mock_websocket.send_json.reset_mock()
        mock_websocket2.send_json.reset_mock()

        message = RealtimeMessage(
            type=MessageType.ENTITY_CREATED,
            payload={"id": "123"},
        )
        sent_count = await ws_manager.broadcast("entity:Task", message)

        assert sent_count == 2
        assert mock_websocket.send_json.called
        assert mock_websocket2.send_json.called

    @pytest.mark.asyncio
    async def test_broadcast_exclude_sender(self, ws_manager, mock_websocket):
        """Test broadcasting with sender excluded."""
        conn1 = await ws_manager.connect(mock_websocket)
        mock_websocket2 = AsyncMock()
        mock_websocket2.accept = AsyncMock()
        mock_websocket2.send_json = AsyncMock()
        conn2 = await ws_manager.connect(mock_websocket2)

        await ws_manager.subscribe(conn1, "entity:Task")
        await ws_manager.subscribe(conn2, "entity:Task")

        mock_websocket.send_json.reset_mock()
        mock_websocket2.send_json.reset_mock()

        message = RealtimeMessage(type=MessageType.ENTITY_UPDATED)
        sent_count = await ws_manager.broadcast("entity:Task", message, exclude_connection=conn1)

        assert sent_count == 1
        assert not mock_websocket.send_json.called
        assert mock_websocket2.send_json.called

    @pytest.mark.asyncio
    async def test_broadcast_to_all(self, ws_manager, mock_websocket):
        """Test broadcasting to all connections."""
        conn1 = await ws_manager.connect(mock_websocket)
        mock_websocket2 = AsyncMock()
        mock_websocket2.accept = AsyncMock()
        mock_websocket2.send_json = AsyncMock()
        conn2 = await ws_manager.connect(mock_websocket2)

        mock_websocket.send_json.reset_mock()
        mock_websocket2.send_json.reset_mock()

        message = RealtimeMessage(type=MessageType.PING)
        sent_count = await ws_manager.broadcast_to_all(message)

        assert sent_count == 2

    @pytest.mark.asyncio
    async def test_send_to_user(self, ws_manager, mock_websocket):
        """Test sending to specific user."""
        conn1 = await ws_manager.connect(mock_websocket, user_id="user_123")
        mock_websocket2 = AsyncMock()
        mock_websocket2.accept = AsyncMock()
        mock_websocket2.send_json = AsyncMock()
        conn2 = await ws_manager.connect(mock_websocket2, user_id="user_456")

        mock_websocket.send_json.reset_mock()
        mock_websocket2.send_json.reset_mock()

        message = RealtimeMessage(type=MessageType.ENTITY_UPDATED)
        sent_count = await ws_manager.send_to_user("user_123", message)

        assert sent_count == 1
        assert mock_websocket.send_json.called
        assert not mock_websocket2.send_json.called


# =============================================================================
# Stale Connection Cleanup Tests
# =============================================================================


class TestStaleCleanup:
    """Tests for stale connection cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_stale_connections(self, ws_manager, mock_websocket):
        """Test cleaning up stale connections."""
        connection_id = await ws_manager.connect(mock_websocket)

        # Manually set heartbeat to past
        conn = ws_manager.get_connection(connection_id)
        conn.last_heartbeat = datetime.utcnow() - timedelta(seconds=120)

        stale = await ws_manager.cleanup_stale_connections()

        assert len(stale) == 1
        assert stale[0] == connection_id
        assert ws_manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_keeps_active_connections(self, ws_manager, mock_websocket):
        """Test that active connections are not cleaned up."""
        connection_id = await ws_manager.connect(mock_websocket)

        # Connection is fresh, should not be cleaned up
        stale = await ws_manager.cleanup_stale_connections()

        assert len(stale) == 0
        assert ws_manager.connection_count == 1


# =============================================================================
# Statistics Tests
# =============================================================================


class TestStatistics:
    """Tests for manager statistics."""

    @pytest.mark.asyncio
    async def test_get_stats(self, ws_manager, mock_websocket):
        """Test getting statistics."""
        conn1 = await ws_manager.connect(mock_websocket, user_id="user_123")
        mock_websocket2 = AsyncMock()
        mock_websocket2.accept = AsyncMock()
        mock_websocket2.send_json = AsyncMock()
        conn2 = await ws_manager.connect(mock_websocket2, user_id="user_456")

        await ws_manager.subscribe(conn1, "entity:Task")
        await ws_manager.subscribe(conn1, "entity:User")
        await ws_manager.subscribe(conn2, "entity:Task")

        stats = ws_manager.get_stats()

        assert stats["connections"] == 2
        assert stats["channels"] == 2  # entity:Task and entity:User
        assert stats["users"] == 2
        assert stats["subscriptions"] == 3
