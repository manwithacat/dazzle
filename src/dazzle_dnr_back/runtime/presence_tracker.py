"""
Presence tracking for DNR real-time features.

Tracks which users are viewing which resources for collaboration awareness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle_dnr_back.runtime.websocket_manager import (
        WebSocketManager,
    )


# =============================================================================
# Presence Entry
# =============================================================================


@dataclass
class PresenceEntry:
    """A presence entry for a user at a resource."""

    user_id: str
    user_name: str | None
    resource: str
    connection_id: str
    joined_at: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "userId": self.user_id,
            "userName": self.user_name,
            "resource": self.resource,
            "joinedAt": self.joined_at.isoformat(),
            "lastSeen": self.last_seen.isoformat(),
            "metadata": self.metadata,
        }

    def update_heartbeat(self) -> None:
        """Update the last seen time."""
        self.last_seen = datetime.utcnow()


# =============================================================================
# Presence Tracker
# =============================================================================


@dataclass
class PresenceTracker:
    """
    Tracks user presence across resources.

    Provides:
    - Join/leave tracking for resources
    - Heartbeat-based activity detection
    - Automatic cleanup of stale entries
    - Presence sync for new connections
    """

    timeout_seconds: int = 30  # Consider offline after this time

    # resource -> user_id -> PresenceEntry
    _entries: dict[str, dict[str, PresenceEntry]] = field(default_factory=dict)
    # connection_id -> (resource, user_id) for cleanup
    _connection_presence: dict[str, list[tuple[str, str]]] = field(default_factory=dict)

    ws_manager: WebSocketManager | None = None

    def set_websocket_manager(self, manager: WebSocketManager) -> None:
        """Set the WebSocket manager for broadcasting."""
        self.ws_manager = manager

    # =========================================================================
    # Join/Leave Operations
    # =========================================================================

    async def join(
        self,
        resource: str,
        user_id: str,
        connection_id: str,
        user_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PresenceEntry:
        """
        User joined a resource.

        Args:
            resource: Resource identifier (e.g., "workspace/tasks", "entity/Task/123")
            user_id: User ID
            connection_id: WebSocket connection ID
            user_name: Optional display name
            metadata: Optional additional data

        Returns:
            The presence entry
        """
        # Create or update entry
        if resource not in self._entries:
            self._entries[resource] = {}

        entry = PresenceEntry(
            user_id=user_id,
            user_name=user_name,
            resource=resource,
            connection_id=connection_id,
            metadata=metadata or {},
        )
        self._entries[resource][user_id] = entry

        # Track by connection for cleanup
        if connection_id not in self._connection_presence:
            self._connection_presence[connection_id] = []
        self._connection_presence[connection_id].append((resource, user_id))

        # Broadcast join event
        await self._broadcast_join(resource, entry)

        return entry

    async def leave(
        self,
        resource: str,
        user_id: str,
    ) -> bool:
        """
        User left a resource.

        Args:
            resource: Resource identifier
            user_id: User ID

        Returns:
            True if user was present
        """
        resource_entries = self._entries.get(resource)
        if not resource_entries:
            return False

        entry = resource_entries.pop(user_id, None)
        if not entry:
            return False

        # Clean up empty resources
        if not resource_entries:
            del self._entries[resource]

        # Remove from connection tracking
        if entry.connection_id in self._connection_presence:
            conn_presence = self._connection_presence[entry.connection_id]
            self._connection_presence[entry.connection_id] = [
                (r, u) for r, u in conn_presence if not (r == resource and u == user_id)
            ]

        # Broadcast leave event
        await self._broadcast_leave(resource, user_id, entry.user_name)

        return True

    async def leave_all_for_connection(self, connection_id: str) -> list[tuple[str, str]]:
        """
        Remove all presence entries for a connection.

        Called when a WebSocket disconnects.

        Args:
            connection_id: Connection ID

        Returns:
            List of (resource, user_id) pairs that were removed
        """
        removed = []
        presence_list = self._connection_presence.pop(connection_id, [])

        for resource, user_id in presence_list:
            resource_entries = self._entries.get(resource)
            if resource_entries:
                entry = resource_entries.get(user_id)
                if entry and entry.connection_id == connection_id:
                    del resource_entries[user_id]
                    removed.append((resource, user_id))

                    # Broadcast leave
                    await self._broadcast_leave(resource, user_id, entry.user_name)

                    # Clean up empty resources
                    if not resource_entries:
                        del self._entries[resource]

        return removed

    # =========================================================================
    # Heartbeat
    # =========================================================================

    def heartbeat(
        self,
        resource: str,
        user_id: str,
    ) -> bool:
        """
        Update user's last seen time.

        Args:
            resource: Resource identifier
            user_id: User ID

        Returns:
            True if user was present
        """
        resource_entries = self._entries.get(resource)
        if not resource_entries:
            return False

        entry = resource_entries.get(user_id)
        if not entry:
            return False

        entry.update_heartbeat()
        return True

    def heartbeat_all_for_connection(self, connection_id: str) -> int:
        """
        Update heartbeat for all presence entries of a connection.

        Args:
            connection_id: Connection ID

        Returns:
            Number of entries updated
        """
        presence_list = self._connection_presence.get(connection_id, [])
        updated = 0

        for resource, user_id in presence_list:
            if self.heartbeat(resource, user_id):
                updated += 1

        return updated

    # =========================================================================
    # Query Operations
    # =========================================================================

    def get_present(self, resource: str) -> list[PresenceEntry]:
        """
        Get all users present at a resource.

        Args:
            resource: Resource identifier

        Returns:
            List of presence entries
        """
        resource_entries = self._entries.get(resource, {})
        return list(resource_entries.values())

    def get_present_user_ids(self, resource: str) -> list[str]:
        """
        Get IDs of all users present at a resource.

        Args:
            resource: Resource identifier

        Returns:
            List of user IDs
        """
        resource_entries = self._entries.get(resource, {})
        return list(resource_entries.keys())

    def is_present(self, resource: str, user_id: str) -> bool:
        """
        Check if a user is present at a resource.

        Args:
            resource: Resource identifier
            user_id: User ID

        Returns:
            True if present
        """
        resource_entries = self._entries.get(resource, {})
        return user_id in resource_entries

    def get_user_resources(self, user_id: str) -> list[str]:
        """
        Get all resources where a user is present.

        Args:
            user_id: User ID

        Returns:
            List of resource identifiers
        """
        resources = []
        for resource, entries in self._entries.items():
            if user_id in entries:
                resources.append(resource)
        return resources

    def get_entry(self, resource: str, user_id: str) -> PresenceEntry | None:
        """
        Get a specific presence entry.

        Args:
            resource: Resource identifier
            user_id: User ID

        Returns:
            Presence entry or None
        """
        resource_entries = self._entries.get(resource, {})
        return resource_entries.get(user_id)

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def cleanup_stale(self) -> list[tuple[str, str]]:
        """
        Remove stale presence entries.

        Returns:
            List of (resource, user_id) pairs that were removed
        """
        now = datetime.utcnow()
        stale = []

        for resource, entries in list(self._entries.items()):
            for user_id, entry in list(entries.items()):
                delta = (now - entry.last_seen).total_seconds()
                if delta > self.timeout_seconds:
                    stale.append((resource, user_id))

        for resource, user_id in stale:
            await self.leave(resource, user_id)

        return stale

    # =========================================================================
    # Broadcasting
    # =========================================================================

    def _get_presence_channel(self, resource: str) -> str:
        """Get the presence channel name for a resource."""
        return f"presence:{resource}"

    async def _broadcast_join(self, resource: str, entry: PresenceEntry) -> None:
        """Broadcast a join event."""
        if not self.ws_manager:
            return

        from dazzle_dnr_back.runtime.websocket_manager import MessageType, RealtimeMessage

        channel = self._get_presence_channel(resource)
        message = RealtimeMessage(
            type=MessageType.PRESENCE_JOIN,
            channel=channel,
            payload=entry.to_dict(),
        )

        await self.ws_manager.broadcast(channel, message)

    async def _broadcast_leave(
        self,
        resource: str,
        user_id: str,
        user_name: str | None,
    ) -> None:
        """Broadcast a leave event."""
        if not self.ws_manager:
            return

        from dazzle_dnr_back.runtime.websocket_manager import MessageType, RealtimeMessage

        channel = self._get_presence_channel(resource)
        message = RealtimeMessage(
            type=MessageType.PRESENCE_LEAVE,
            channel=channel,
            payload={
                "userId": user_id,
                "userName": user_name,
            },
        )

        await self.ws_manager.broadcast(channel, message)

    async def send_sync(self, connection_id: str, resource: str) -> None:
        """
        Send current presence state to a connection.

        Called when a user first subscribes to presence.

        Args:
            connection_id: Connection to send to
            resource: Resource to sync
        """
        if not self.ws_manager:
            return

        from dazzle_dnr_back.runtime.websocket_manager import MessageType, RealtimeMessage

        entries = self.get_present(resource)
        channel = self._get_presence_channel(resource)

        message = RealtimeMessage(
            type=MessageType.PRESENCE_SYNC,
            channel=channel,
            payload={
                "users": [e.to_dict() for e in entries],
            },
        )

        await self.ws_manager.send_to_connection(connection_id, message)

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_stats(self) -> dict[str, Any]:
        """Get presence statistics."""
        total_entries = sum(len(entries) for entries in self._entries.values())
        return {
            "resources": len(self._entries),
            "entries": total_entries,
            "connections": len(self._connection_presence),
        }


# =============================================================================
# Global Presence Tracker
# =============================================================================


_global_presence_tracker: PresenceTracker | None = None


def get_presence_tracker() -> PresenceTracker:
    """Get the global presence tracker instance."""
    global _global_presence_tracker
    if _global_presence_tracker is None:
        _global_presence_tracker = PresenceTracker()
    return _global_presence_tracker


def set_presence_tracker(tracker: PresenceTracker) -> None:
    """Set the global presence tracker instance."""
    global _global_presence_tracker
    _global_presence_tracker = tracker


def reset_presence_tracker() -> None:
    """Reset the global presence tracker (mainly for testing)."""
    global _global_presence_tracker
    _global_presence_tracker = None


# =============================================================================
# Convenience Functions
# =============================================================================


def create_presence_tracker(
    timeout_seconds: int = 30,
    ws_manager: WebSocketManager | None = None,
) -> PresenceTracker:
    """
    Create a presence tracker.

    Args:
        timeout_seconds: Seconds before user considered offline
        ws_manager: Optional WebSocket manager for broadcasting

    Returns:
        Configured PresenceTracker
    """
    return PresenceTracker(
        timeout_seconds=timeout_seconds,
        ws_manager=ws_manager,
    )
