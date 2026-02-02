"""
Server-Sent Events (SSE) streaming infrastructure.

Provides SSE endpoints that subscribe to the EventBus and stream
events to clients in real-time. This leverages the existing Kafka-shaped
EventBus abstraction (DevBusMemory, DevBrokerSQLite) for event delivery.

Key features:
- Multiple named streams (health, events, analytics, api_calls)
- Client-specific subscriptions with filters
- Automatic reconnection support via Last-Event-ID
- Tenant-scoped streams for multi-tenant analytics
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from dazzle_back.events.bus import EventBus
    from dazzle_back.events.envelope import EventEnvelope

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


class StreamType(str, Enum):
    """Available SSE stream types."""

    HEALTH = "health"  # System health updates
    EVENTS = "events"  # Entity lifecycle events
    API_CALLS = "api_calls"  # External API call tracking
    ANALYTICS = "analytics"  # Tenant analytics events
    ALL = "all"  # All streams combined


@dataclass
class SSEMessage:
    """Server-Sent Event message."""

    event: str  # Event type (maps to SSE 'event' field)
    data: dict[str, Any]  # JSON payload
    id: str | None = None  # Event ID for reconnection
    retry: int | None = None  # Retry interval in ms

    def serialize(self) -> str:
        """Serialize to SSE format."""
        lines = []
        if self.id:
            lines.append(f"id: {self.id}")
        if self.event:
            lines.append(f"event: {self.event}")
        if self.retry is not None:
            lines.append(f"retry: {self.retry}")

        # Data can be multiline - each line needs 'data:' prefix
        data_str = json.dumps(self.data)
        for line in data_str.split("\n"):
            lines.append(f"data: {line}")

        lines.append("")  # Empty line terminates the event
        return "\n".join(lines) + "\n"


@dataclass
class StreamSubscription:
    """Client subscription to an SSE stream."""

    subscription_id: str
    stream_type: StreamType
    tenant_id: str | None = None  # For tenant-scoped streams
    entity_filter: str | None = None  # Filter by entity name
    last_event_id: str | None = None  # For reconnection
    created_at: datetime = field(default_factory=_utcnow)


class SSEStreamManager:
    """
    Manages SSE stream subscriptions and event delivery.

    Subscribes to EventBus topics and streams events to connected
    SSE clients. Supports multiple stream types with filtering.
    """

    # Map stream types to EventBus topics
    STREAM_TOPICS: dict[StreamType, list[str]] = {
        StreamType.HEALTH: ["ops.health"],
        StreamType.EVENTS: ["entity.created", "entity.updated", "entity.deleted"],
        StreamType.API_CALLS: ["ops.api_call"],
        StreamType.ANALYTICS: ["ops.analytics"],
    }

    def __init__(
        self,
        event_bus: EventBus,
        heartbeat_interval: float = 30.0,
    ):
        """
        Initialize SSE stream manager.

        Args:
            event_bus: EventBus for subscribing to events
            heartbeat_interval: Seconds between heartbeat messages
        """
        self.event_bus = event_bus
        self.heartbeat_interval = heartbeat_interval
        self._subscriptions: dict[str, StreamSubscription] = {}
        self._queues: dict[str, asyncio.Queue[SSEMessage]] = {}
        self._running = False
        self._consumer_tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        """Start consuming events from EventBus."""
        if self._running:
            return

        self._running = True

        # Subscribe to all topics
        all_topics = set()
        for topics in self.STREAM_TOPICS.values():
            all_topics.update(topics)

        for topic in all_topics:
            task = asyncio.create_task(self._consume_topic(topic))
            self._consumer_tasks.append(task)

    async def stop(self) -> None:
        """Stop consuming events."""
        self._running = False

        for task in self._consumer_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._consumer_tasks.clear()

    async def _consume_topic(self, topic: str) -> None:
        """Consume events from a topic and route to subscriptions."""
        consumer_group = f"sse-stream-{uuid4().hex[:8]}"

        # Subscribe to topic
        try:
            await self.event_bus.subscribe(topic, consumer_group, self._handle_envelope)
        except Exception as e:
            logger.error(f"Failed to subscribe to topic {topic}: {e}")
            return

        # Poll loop - poll_and_process may not exist on all EventBus implementations
        # but is available on DevBrokerSQLite and KafkaBus
        while self._running:
            try:
                if hasattr(self.event_bus, "poll_and_process"):
                    await self.event_bus.poll_and_process(topic, consumer_group)
            except Exception as e:
                logger.error(f"Error polling topic {topic}: {e}")

            await asyncio.sleep(0.1)  # Small delay between polls

    async def _handle_envelope(self, envelope: EventEnvelope) -> None:
        """Handle incoming event envelope and route to subscribers."""
        # Determine which streams this event belongs to
        event_type = envelope.event_type

        for stream_type, topics in self.STREAM_TOPICS.items():
            # Check if this event matches the stream
            matches = any(event_type.startswith(topic.replace(".*", "")) for topic in topics)
            if not matches:
                continue

            # Route to subscriptions for this stream type
            for sub_id, subscription in list(self._subscriptions.items()):
                if subscription.stream_type not in (stream_type, StreamType.ALL):
                    continue

                # Apply tenant filter
                if subscription.tenant_id:
                    event_tenant = envelope.headers.get("tenant_id")
                    if event_tenant != subscription.tenant_id:
                        continue

                # Apply entity filter
                if subscription.entity_filter:
                    entity_name = envelope.entity_name
                    if entity_name != subscription.entity_filter:
                        continue

                # Create SSE message
                message = SSEMessage(
                    event=event_type,
                    data=envelope.payload,
                    id=str(envelope.event_id),
                )

                # Put in subscriber's queue
                queue = self._queues.get(sub_id)
                if queue:
                    try:
                        queue.put_nowait(message)
                    except asyncio.QueueFull:
                        # Drop old messages if queue is full
                        try:
                            queue.get_nowait()
                            queue.put_nowait(message)
                        except asyncio.QueueEmpty:
                            pass

    def create_subscription(
        self,
        stream_type: StreamType,
        tenant_id: str | None = None,
        entity_filter: str | None = None,
        last_event_id: str | None = None,
    ) -> str:
        """
        Create a new SSE subscription.

        Args:
            stream_type: Type of stream to subscribe to
            tenant_id: Optional tenant ID for scoped streams
            entity_filter: Optional entity name filter
            last_event_id: Last event ID for reconnection

        Returns:
            Subscription ID
        """
        sub_id = str(uuid4())
        subscription = StreamSubscription(
            subscription_id=sub_id,
            stream_type=stream_type,
            tenant_id=tenant_id,
            entity_filter=entity_filter,
            last_event_id=last_event_id,
        )
        self._subscriptions[sub_id] = subscription
        self._queues[sub_id] = asyncio.Queue(maxsize=100)

        return sub_id

    def remove_subscription(self, subscription_id: str) -> None:
        """Remove a subscription."""
        self._subscriptions.pop(subscription_id, None)
        self._queues.pop(subscription_id, None)

    async def stream(
        self,
        subscription_id: str,
    ) -> AsyncGenerator[str, None]:
        """
        Generate SSE stream for a subscription.

        Yields serialized SSE messages. Includes periodic heartbeats
        to keep the connection alive.

        Args:
            subscription_id: Subscription ID from create_subscription

        Yields:
            Serialized SSE messages
        """
        queue = self._queues.get(subscription_id)
        if not queue:
            return

        # Send initial connection message
        yield SSEMessage(
            event="connected",
            data={"subscription_id": subscription_id},
            retry=3000,  # 3 second retry
        ).serialize()

        try:
            while True:
                try:
                    # Wait for message with timeout for heartbeat
                    message = await asyncio.wait_for(
                        queue.get(),
                        timeout=self.heartbeat_interval,
                    )
                    yield message.serialize()
                except TimeoutError:
                    # Send heartbeat
                    yield SSEMessage(
                        event="heartbeat",
                        data={"timestamp": datetime.now(UTC).isoformat()},
                    ).serialize()
        finally:
            self.remove_subscription(subscription_id)

    def get_stats(self) -> dict[str, Any]:
        """Get stream statistics."""
        return {
            "active_subscriptions": len(self._subscriptions),
            "subscriptions_by_type": {
                st.value: sum(1 for s in self._subscriptions.values() if s.stream_type == st)
                for st in StreamType
            },
            "running": self._running,
        }


# =============================================================================
# FastAPI Integration
# =============================================================================


def create_sse_routes(stream_manager: SSEStreamManager) -> Any:
    """
    Create FastAPI routes for SSE streaming.

    Args:
        stream_manager: SSEStreamManager instance

    Returns:
        FastAPI APIRouter with SSE endpoints
    """
    try:
        from fastapi import APIRouter, Header, Query, Request
        from fastapi.responses import StreamingResponse
    except ImportError:
        raise RuntimeError("FastAPI required for SSE routes")

    router = APIRouter(prefix="/_ops/sse", tags=["SSE Streaming"])

    @router.get("/health")
    async def stream_health(
        request: Request,
        last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        """
        Stream health updates via SSE.

        Streams real-time health check results as they occur.
        Supports reconnection via Last-Event-ID header.
        """
        sub_id = stream_manager.create_subscription(
            stream_type=StreamType.HEALTH,
            last_event_id=last_event_id,
        )

        return StreamingResponse(
            stream_manager.stream(sub_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    @router.get("/events")
    async def stream_events(
        request: Request,
        entity: str | None = Query(None, description="Filter by entity name"),
        tenant_id: str | None = Query(None, description="Filter by tenant ID"),
        last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        """
        Stream entity lifecycle events via SSE.

        Streams create, update, delete events for entities.
        Can filter by entity name and/or tenant ID.
        """
        sub_id = stream_manager.create_subscription(
            stream_type=StreamType.EVENTS,
            tenant_id=tenant_id,
            entity_filter=entity,
            last_event_id=last_event_id,
        )

        return StreamingResponse(
            stream_manager.stream(sub_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/api-calls")
    async def stream_api_calls(
        request: Request,
        tenant_id: str | None = Query(None, description="Filter by tenant ID"),
        last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        """
        Stream external API call events via SSE.

        Streams API call tracking events including latency,
        status codes, and costs.
        """
        sub_id = stream_manager.create_subscription(
            stream_type=StreamType.API_CALLS,
            tenant_id=tenant_id,
            last_event_id=last_event_id,
        )

        return StreamingResponse(
            stream_manager.stream(sub_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/analytics")
    async def stream_analytics(
        request: Request,
        tenant_id: str = Query(..., description="Tenant ID (required)"),
        last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        """
        Stream analytics events via SSE.

        Streams tenant-scoped analytics events (page views, actions, etc.).
        Tenant ID is required for privacy.
        """
        sub_id = stream_manager.create_subscription(
            stream_type=StreamType.ANALYTICS,
            tenant_id=tenant_id,
            last_event_id=last_event_id,
        )

        return StreamingResponse(
            stream_manager.stream(sub_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/all")
    async def stream_all(
        request: Request,
        tenant_id: str | None = Query(None, description="Filter by tenant ID"),
        last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        """
        Stream all events via SSE.

        Combined stream of health, events, API calls, and analytics.
        Useful for unified Control Plane monitoring.
        """
        sub_id = stream_manager.create_subscription(
            stream_type=StreamType.ALL,
            tenant_id=tenant_id,
            last_event_id=last_event_id,
        )

        return StreamingResponse(
            stream_manager.stream(sub_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/stats")
    async def get_stats() -> dict[str, Any]:
        """Get SSE stream statistics."""
        return stream_manager.get_stats()

    return router
