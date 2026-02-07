"""
WebSocket routes for DNR real-time features.

Provides the WebSocket endpoint and message handlers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI, WebSocket

    from dazzle_back.runtime.auth import AuthStore

from dazzle_back.runtime.event_bus import EntityEventBus, create_event_bus
from dazzle_back.runtime.presence_tracker import (
    PresenceTracker,
    create_presence_tracker,
)
from dazzle_back.runtime.websocket_manager import (
    MessageType,
    RealtimeMessage,
    WebSocketManager,
    create_websocket_manager,
)

# =============================================================================
# Realtime Context
# =============================================================================


class RealtimeContext:
    """
    Container for all real-time components.

    Provides a single entry point for setting up real-time features.
    """

    def __init__(
        self,
        ws_manager: WebSocketManager | None = None,
        event_bus: EntityEventBus | None = None,
        presence_tracker: PresenceTracker | None = None,
    ):
        self.ws_manager = ws_manager or create_websocket_manager()
        self.event_bus = event_bus or create_event_bus()
        self.presence_tracker = presence_tracker or create_presence_tracker()

        # Wire components together
        self.event_bus.set_websocket_manager(self.ws_manager)
        self.presence_tracker.set_websocket_manager(self.ws_manager)

        # Register presence handlers
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register message handlers."""
        self.ws_manager.register_handler(
            MessageType.PRESENCE_JOIN,
            self._handle_presence_join,
        )
        self.ws_manager.register_handler(
            MessageType.PRESENCE_LEAVE,
            self._handle_presence_leave,
        )
        self.ws_manager.register_handler(
            MessageType.PRESENCE_HEARTBEAT,
            self._handle_presence_heartbeat,
        )

    async def _handle_presence_join(
        self,
        connection_id: str,
        message: RealtimeMessage,
    ) -> None:
        """Handle presence join request."""
        connection = self.ws_manager.get_connection(connection_id)
        if not connection:
            return

        payload = message.payload or {}
        resource = payload.get("resource")
        if not resource:
            return

        # Only authenticated users can have presence
        if not connection.user_id:
            await self.ws_manager.send_to_connection(
                connection_id,
                RealtimeMessage(
                    type=MessageType.ERROR,
                    request_id=message.request_id,
                    payload={
                        "code": "UNAUTHENTICATED",
                        "message": "Must be authenticated for presence",
                    },
                ),
            )
            return

        await self.presence_tracker.join(
            resource=resource,
            user_id=connection.user_id,
            connection_id=connection_id,
            user_name=connection.user_name,
            metadata=payload.get("metadata"),
        )

        # Subscribe to presence channel
        channel = f"presence:{resource}"
        await self.ws_manager.subscribe(connection_id, channel)

        # Send current presence state
        await self.presence_tracker.send_sync(connection_id, resource)

    async def _handle_presence_leave(
        self,
        connection_id: str,
        message: RealtimeMessage,
    ) -> None:
        """Handle presence leave request."""
        connection = self.ws_manager.get_connection(connection_id)
        if not connection or not connection.user_id:
            return

        payload = message.payload or {}
        resource = payload.get("resource")
        if not resource:
            return

        await self.presence_tracker.leave(resource, connection.user_id)

        # Unsubscribe from presence channel
        channel = f"presence:{resource}"
        await self.ws_manager.unsubscribe(connection_id, channel)

    async def _handle_presence_heartbeat(
        self,
        connection_id: str,
        message: RealtimeMessage,
    ) -> None:
        """Handle presence heartbeat."""
        self.presence_tracker.heartbeat_all_for_connection(connection_id)

    async def on_disconnect(self, connection_id: str) -> None:
        """Handle connection disconnect - clean up presence."""
        await self.presence_tracker.leave_all_for_connection(connection_id)
        await self.ws_manager.disconnect(connection_id)


# =============================================================================
# Route Setup
# =============================================================================


def create_realtime_routes(
    app: FastAPI,
    context: RealtimeContext | None = None,
    auth_store: AuthStore | None = None,
    path: str = "/ws",
) -> RealtimeContext:
    """
    Create WebSocket routes for real-time features.

    Args:
        app: FastAPI application
        context: Optional RealtimeContext (creates new if not provided)
        auth_store: Optional auth store for token validation
        path: WebSocket endpoint path

    Returns:
        The RealtimeContext being used
    """
    try:
        from fastapi import Query, WebSocket, WebSocketDisconnect  # noqa: F401
    except ImportError:
        raise RuntimeError("FastAPI is required for realtime routes")

    if context is None:
        context = RealtimeContext()

    @app.websocket(path)
    async def websocket_endpoint(
        websocket: WebSocket,
        token: str | None = Query(None),
    ) -> None:
        """WebSocket endpoint for real-time communication."""
        # Authenticate if token provided
        user_id: str | None = None
        user_name: str | None = None

        if token and auth_store:
            user = await _validate_token_async(auth_store, token)
            if user:
                user_id = str(user.get("id", ""))
                user_name = user.get("username") or user.get("name")

        # Accept connection
        connection_id = await context.ws_manager.connect(
            websocket,
            user_id=user_id,
            user_name=user_name,
        )

        try:
            while True:
                data = await websocket.receive_json()
                await context.ws_manager.handle_message(connection_id, data)
        except WebSocketDisconnect:
            await context.on_disconnect(connection_id)
        except Exception:
            await context.on_disconnect(connection_id)

    # Add stats endpoint
    @app.get(f"{path}/stats", tags=["Realtime"])
    async def realtime_stats() -> dict[str, Any]:
        """Get real-time connection statistics."""
        return {
            "websocket": context.ws_manager.get_stats(),
            "presence": context.presence_tracker.get_stats(),
        }

    return context


async def _validate_token_async(auth_store: AuthStore, token: str) -> dict[str, Any] | None:
    """Validate auth token asynchronously."""
    # AuthStore.get_session_user is sync, wrap it
    import asyncio

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, auth_store.get_session_user, token)  # type: ignore[attr-defined]


# =============================================================================
# Integration with DNRBackendApp
# =============================================================================


def setup_realtime(
    app: FastAPI,
    auth_store: AuthStore | None = None,
    ws_path: str = "/ws",
) -> RealtimeContext:
    """
    Set up real-time features for a DNR backend app.

    This is the main entry point for adding real-time to an existing app.

    Args:
        app: FastAPI application
        auth_store: Optional auth store for authentication
        ws_path: WebSocket endpoint path

    Returns:
        RealtimeContext with all components configured
    """
    context = RealtimeContext()
    create_realtime_routes(
        app=app,
        context=context,
        auth_store=auth_store,
        path=ws_path,
    )
    return context
