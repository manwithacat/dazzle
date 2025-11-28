"""
WebSocket manager for DNR real-time features.

Provides connection management, channel subscriptions, and message routing.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Awaitable

if TYPE_CHECKING:
    from fastapi import WebSocket


# =============================================================================
# Message Types
# =============================================================================


class MessageType(str, Enum):
    """WebSocket message types."""

    # Channel operations
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"

    # Data events
    ENTITY_CREATED = "entity:created"
    ENTITY_UPDATED = "entity:updated"
    ENTITY_DELETED = "entity:deleted"

    # Presence
    PRESENCE_JOIN = "presence:join"
    PRESENCE_LEAVE = "presence:leave"
    PRESENCE_SYNC = "presence:sync"
    PRESENCE_HEARTBEAT = "presence:heartbeat"

    # System
    PING = "ping"
    PONG = "pong"
    ERROR = "error"
    CONNECTED = "connected"


@dataclass
class RealtimeMessage:
    """A real-time message."""

    type: str
    channel: str | None = None
    payload: dict[str, Any] | None = None
    request_id: str | None = None
    timestamp: float = field(default_factory=lambda: time.time() * 1000)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "type": self.type,
            "timestamp": self.timestamp,
        }
        if self.channel is not None:
            result["channel"] = self.channel
        if self.payload is not None:
            result["payload"] = self.payload
        if self.request_id is not None:
            result["requestId"] = self.request_id
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RealtimeMessage":
        """Create from dictionary."""
        return cls(
            type=data.get("type", ""),
            channel=data.get("channel"),
            payload=data.get("payload"),
            request_id=data.get("requestId"),
            timestamp=data.get("timestamp", time.time() * 1000),
        )


# =============================================================================
# Connection
# =============================================================================


@dataclass
class Connection:
    """A WebSocket connection."""

    id: str
    websocket: "WebSocket"
    user_id: str | None = None
    user_name: str | None = None
    subscriptions: set[str] = field(default_factory=set)
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def update_heartbeat(self) -> None:
        """Update the last heartbeat time."""
        self.last_heartbeat = datetime.utcnow()


# =============================================================================
# WebSocket Manager
# =============================================================================


MessageHandler = Callable[[str, RealtimeMessage], Awaitable[None]]


@dataclass
class WebSocketManager:
    """
    Manages WebSocket connections and message routing.

    Provides:
    - Connection lifecycle management
    - Channel-based pub/sub
    - Message routing to handlers
    - Broadcast to all or filtered connections
    """

    max_subscriptions_per_connection: int = 50
    heartbeat_timeout_seconds: int = 60

    _connections: dict[str, Connection] = field(default_factory=dict)
    _channels: dict[str, set[str]] = field(default_factory=dict)  # channel -> connection_ids
    _user_connections: dict[str, set[str]] = field(default_factory=dict)  # user_id -> connection_ids
    _handlers: dict[str, MessageHandler] = field(default_factory=dict)

    def register_handler(self, message_type: str, handler: MessageHandler) -> None:
        """Register a handler for a message type."""
        self._handlers[message_type] = handler

    async def connect(
        self,
        websocket: "WebSocket",
        user_id: str | None = None,
        user_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Accept a new WebSocket connection.

        Args:
            websocket: FastAPI WebSocket instance
            user_id: Optional authenticated user ID
            user_name: Optional user display name
            metadata: Optional connection metadata

        Returns:
            Connection ID
        """
        await websocket.accept()

        connection_id = str(uuid.uuid4())
        connection = Connection(
            id=connection_id,
            websocket=websocket,
            user_id=user_id,
            user_name=user_name,
            metadata=metadata or {},
        )

        self._connections[connection_id] = connection

        # Track user connections
        if user_id:
            if user_id not in self._user_connections:
                self._user_connections[user_id] = set()
            self._user_connections[user_id].add(connection_id)

        # Send connected message
        await self._send(
            connection_id,
            RealtimeMessage(
                type=MessageType.CONNECTED,
                payload={
                    "connectionId": connection_id,
                    "userId": user_id,
                },
            ),
        )

        return connection_id

    async def disconnect(self, connection_id: str) -> None:
        """
        Handle connection disconnect.

        Cleans up subscriptions and user tracking.
        """
        connection = self._connections.get(connection_id)
        if not connection:
            return

        # Remove from all channels
        for channel in list(connection.subscriptions):
            await self._remove_from_channel(connection_id, channel)

        # Remove from user tracking
        if connection.user_id:
            user_connections = self._user_connections.get(connection.user_id)
            if user_connections:
                user_connections.discard(connection_id)
                if not user_connections:
                    del self._user_connections[connection.user_id]

        # Remove connection
        del self._connections[connection_id]

    def get_connection(self, connection_id: str) -> Connection | None:
        """Get a connection by ID."""
        return self._connections.get(connection_id)

    def get_user_connections(self, user_id: str) -> list[Connection]:
        """Get all connections for a user."""
        connection_ids = self._user_connections.get(user_id, set())
        return [
            self._connections[cid]
            for cid in connection_ids
            if cid in self._connections
        ]

    @property
    def connection_count(self) -> int:
        """Get total number of connections."""
        return len(self._connections)

    @property
    def channel_count(self) -> int:
        """Get total number of active channels."""
        return len(self._channels)

    # =========================================================================
    # Channel Subscriptions
    # =========================================================================

    async def subscribe(
        self,
        connection_id: str,
        channel: str,
        request_id: str | None = None,
    ) -> bool:
        """
        Subscribe a connection to a channel.

        Args:
            connection_id: Connection to subscribe
            channel: Channel name
            request_id: Optional request ID for response correlation

        Returns:
            True if subscribed, False if limit reached
        """
        connection = self._connections.get(connection_id)
        if not connection:
            return False

        # Check subscription limit
        if len(connection.subscriptions) >= self.max_subscriptions_per_connection:
            await self._send(
                connection_id,
                RealtimeMessage(
                    type=MessageType.ERROR,
                    request_id=request_id,
                    payload={
                        "code": "SUBSCRIPTION_LIMIT",
                        "message": f"Maximum {self.max_subscriptions_per_connection} subscriptions allowed",
                    },
                ),
            )
            return False

        # Add to channel
        if channel not in self._channels:
            self._channels[channel] = set()
        self._channels[channel].add(connection_id)
        connection.subscriptions.add(channel)

        # Send confirmation
        await self._send(
            connection_id,
            RealtimeMessage(
                type=MessageType.SUBSCRIBED,
                channel=channel,
                request_id=request_id,
            ),
        )

        return True

    async def unsubscribe(
        self,
        connection_id: str,
        channel: str,
        request_id: str | None = None,
    ) -> bool:
        """
        Unsubscribe a connection from a channel.

        Args:
            connection_id: Connection to unsubscribe
            channel: Channel name
            request_id: Optional request ID for response correlation

        Returns:
            True if unsubscribed
        """
        connection = self._connections.get(connection_id)
        if not connection:
            return False

        await self._remove_from_channel(connection_id, channel)

        # Send confirmation
        await self._send(
            connection_id,
            RealtimeMessage(
                type=MessageType.UNSUBSCRIBED,
                channel=channel,
                request_id=request_id,
            ),
        )

        return True

    async def _remove_from_channel(self, connection_id: str, channel: str) -> None:
        """Remove a connection from a channel."""
        connection = self._connections.get(connection_id)
        if connection:
            connection.subscriptions.discard(channel)

        channel_connections = self._channels.get(channel)
        if channel_connections:
            channel_connections.discard(connection_id)
            if not channel_connections:
                del self._channels[channel]

    def get_channel_subscribers(self, channel: str) -> list[str]:
        """Get all connection IDs subscribed to a channel."""
        return list(self._channels.get(channel, set()))

    def is_subscribed(self, connection_id: str, channel: str) -> bool:
        """Check if a connection is subscribed to a channel."""
        connection = self._connections.get(connection_id)
        return connection is not None and channel in connection.subscriptions

    # =========================================================================
    # Message Handling
    # =========================================================================

    async def handle_message(
        self,
        connection_id: str,
        data: dict[str, Any],
    ) -> None:
        """
        Handle an incoming message from a connection.

        Routes to appropriate handler based on message type.
        """
        connection = self._connections.get(connection_id)
        if not connection:
            return

        message = RealtimeMessage.from_dict(data)
        connection.update_heartbeat()

        # Built-in handlers
        if message.type == MessageType.PING:
            await self._send(
                connection_id,
                RealtimeMessage(type=MessageType.PONG),
            )
            return

        if message.type == MessageType.SUBSCRIBE and message.channel:
            await self.subscribe(connection_id, message.channel, message.request_id)
            return

        if message.type == MessageType.UNSUBSCRIBE and message.channel:
            await self.unsubscribe(connection_id, message.channel, message.request_id)
            return

        # Custom handlers
        handler = self._handlers.get(message.type)
        if handler:
            await handler(connection_id, message)
        else:
            await self._send(
                connection_id,
                RealtimeMessage(
                    type=MessageType.ERROR,
                    request_id=message.request_id,
                    payload={
                        "code": "UNKNOWN_MESSAGE_TYPE",
                        "message": f"Unknown message type: {message.type}",
                    },
                ),
            )

    # =========================================================================
    # Broadcasting
    # =========================================================================

    async def broadcast(
        self,
        channel: str,
        message: RealtimeMessage,
        exclude_connection: str | None = None,
    ) -> int:
        """
        Broadcast a message to all subscribers of a channel.

        Args:
            channel: Channel to broadcast to
            message: Message to send
            exclude_connection: Optional connection to exclude (e.g., sender)

        Returns:
            Number of connections message was sent to
        """
        message.channel = channel
        connection_ids = self._channels.get(channel, set())
        sent_count = 0

        for connection_id in connection_ids:
            if connection_id == exclude_connection:
                continue
            if await self._send(connection_id, message):
                sent_count += 1

        return sent_count

    async def broadcast_to_all(
        self,
        message: RealtimeMessage,
        exclude_connection: str | None = None,
    ) -> int:
        """
        Broadcast a message to all connected clients.

        Args:
            message: Message to send
            exclude_connection: Optional connection to exclude

        Returns:
            Number of connections message was sent to
        """
        sent_count = 0

        for connection_id in self._connections:
            if connection_id == exclude_connection:
                continue
            if await self._send(connection_id, message):
                sent_count += 1

        return sent_count

    async def send_to_user(
        self,
        user_id: str,
        message: RealtimeMessage,
    ) -> int:
        """
        Send a message to all connections for a user.

        Args:
            user_id: User to send to
            message: Message to send

        Returns:
            Number of connections message was sent to
        """
        connection_ids = self._user_connections.get(user_id, set())
        sent_count = 0

        for connection_id in connection_ids:
            if await self._send(connection_id, message):
                sent_count += 1

        return sent_count

    async def send_to_connection(
        self,
        connection_id: str,
        message: RealtimeMessage,
    ) -> bool:
        """
        Send a message to a specific connection.

        Args:
            connection_id: Connection to send to
            message: Message to send

        Returns:
            True if sent successfully
        """
        return await self._send(connection_id, message)

    async def _send(
        self,
        connection_id: str,
        message: RealtimeMessage,
    ) -> bool:
        """Send a message to a connection."""
        connection = self._connections.get(connection_id)
        if not connection:
            return False

        try:
            await connection.websocket.send_json(message.to_dict())
            return True
        except Exception:
            # Connection may be closed, will be cleaned up
            return False

    # =========================================================================
    # Maintenance
    # =========================================================================

    async def cleanup_stale_connections(self) -> list[str]:
        """
        Remove connections that haven't sent a heartbeat recently.

        Returns:
            List of disconnected connection IDs
        """
        now = datetime.utcnow()
        stale_connections = []

        for connection_id, connection in list(self._connections.items()):
            delta = (now - connection.last_heartbeat).total_seconds()
            if delta > self.heartbeat_timeout_seconds:
                stale_connections.append(connection_id)

        for connection_id in stale_connections:
            await self.disconnect(connection_id)

        return stale_connections

    def get_stats(self) -> dict[str, Any]:
        """Get manager statistics."""
        return {
            "connections": len(self._connections),
            "channels": len(self._channels),
            "users": len(self._user_connections),
            "subscriptions": sum(
                len(c.subscriptions) for c in self._connections.values()
            ),
        }


# =============================================================================
# Convenience Functions
# =============================================================================


def create_websocket_manager(
    max_subscriptions: int = 50,
    heartbeat_timeout: int = 60,
) -> WebSocketManager:
    """
    Create a WebSocket manager with default settings.

    Args:
        max_subscriptions: Maximum subscriptions per connection
        heartbeat_timeout: Seconds before connection considered stale

    Returns:
        Configured WebSocketManager
    """
    return WebSocketManager(
        max_subscriptions_per_connection=max_subscriptions,
        heartbeat_timeout_seconds=heartbeat_timeout,
    )
