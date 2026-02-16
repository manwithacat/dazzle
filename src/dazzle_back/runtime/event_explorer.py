"""
Event Explorer routes for runtime inspection.

Provides /_dazzle/events/* endpoints for inspecting the event system,
including topics, events, consumers, and outbox status.

These endpoints are always available in development mode (localhost).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

try:
    from fastapi import APIRouter, Query

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore[misc, assignment]
    Query = None  # type: ignore[assignment]

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from dazzle_back.events.envelope import EventEnvelope
    from dazzle_back.events.framework import EventFramework


@runtime_checkable
class EventBusExplorer(Protocol):
    """Protocol for the EventBus methods used by the event explorer."""

    async def list_topics(self) -> list[str]: ...
    async def list_consumer_groups(self, topic: str) -> list[str]: ...
    async def get_topic_info(self, topic: str) -> dict[str, Any]: ...
    def replay(
        self,
        topic: str,
        *,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
        from_offset: int | None = None,
        to_offset: int | None = None,
        key_filter: str | None = None,
    ) -> AsyncIterator[EventEnvelope]: ...
    async def get_event(self, event_id: str) -> Any: ...
    async def get_consumer_info(self, group_id: str, topic: str) -> dict[str, Any]: ...
    async def get_dlq_count(self, topic: str | None = None) -> int: ...
    async def get_dlq_events(
        self, topic: str | None = None, group_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]: ...
    async def replay_dlq_event(self, event_id: str, group_id: str) -> bool: ...


# =============================================================================
# Response Models
# =============================================================================


class TopicInfo(BaseModel):
    """Information about an event topic."""

    name: str
    event_count: int
    consumer_groups: list[str] = Field(default_factory=list)
    dlq_count: int = 0
    oldest_event: str | None = None
    newest_event: str | None = None


class TopicsResponse(BaseModel):
    """Response for list topics endpoint."""

    topics: list[TopicInfo]
    total_events: int


class EventSummary(BaseModel):
    """Summary of an event for listing."""

    event_id: str
    event_type: str
    key: str
    timestamp: str
    payload_preview: str


class EventDetail(BaseModel):
    """Full event details."""

    event_id: str
    event_type: str
    event_version: str
    key: str
    timestamp: str
    payload: dict[str, Any]
    headers: dict[str, str]
    correlation_id: str | None
    causation_id: str | None
    topic: str


class EventsResponse(BaseModel):
    """Response for list events endpoint."""

    topic: str
    events: list[EventSummary]
    total: int
    offset: int
    limit: int


class ConsumerInfo(BaseModel):
    """Information about a consumer group."""

    group_id: str
    topic: str
    last_sequence: int
    lag: int  # How many events behind


class ConsumersResponse(BaseModel):
    """Response for list consumers endpoint."""

    consumers: list[ConsumerInfo]


class OutboxEntry(BaseModel):
    """An outbox entry."""

    id: str
    topic: str
    event_type: str
    key: str
    status: str
    created_at: str
    published_at: str | None
    attempts: int
    last_error: str | None = None


class OutboxStats(BaseModel):
    """Outbox statistics."""

    pending: int
    publishing: int
    published: int
    failed: int
    oldest_pending: str | None = None


class OutboxResponse(BaseModel):
    """Response for outbox status endpoint."""

    stats: OutboxStats
    recent_entries: list[OutboxEntry]


class DLQEntry(BaseModel):
    """A dead letter queue entry."""

    event_id: str
    topic: str
    group_id: str
    reason_code: str
    reason_message: str
    attempts: int
    created_at: str


class DLQResponse(BaseModel):
    """Response for DLQ list endpoint."""

    entries: list[DLQEntry]
    total: int


class EventSystemStatus(BaseModel):
    """Overall event system status."""

    running: bool
    broker_type: str
    topics_count: int
    consumers_count: int
    outbox_pending: int
    dlq_count: int


# =============================================================================
# Event Explorer Routes
# =============================================================================


def create_event_explorer_routes(framework: EventFramework | None) -> APIRouter:
    """
    Create event explorer routes for runtime inspection.

    Args:
        framework: EventFramework instance (may be None if events disabled)

    Returns:
        APIRouter with event explorer endpoints

    Raises:
        RuntimeError: If FastAPI is not available
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError(
            "FastAPI is required for event explorer routes. Install it with: pip install fastapi"
        )

    router = APIRouter(prefix="/_dazzle/events", tags=["Event Explorer"])

    @router.get("/status", response_model=EventSystemStatus)
    async def event_system_status() -> EventSystemStatus:
        """
        Get event system status.

        Returns whether the event system is running and summary statistics.
        """
        if framework is None or framework.bus is None:
            return EventSystemStatus(
                running=False,
                broker_type="none",
                topics_count=0,
                consumers_count=0,
                outbox_pending=0,
                dlq_count=0,
            )

        bus = cast(EventBusExplorer, framework.bus)
        topics = await bus.list_topics()
        consumers = await bus.list_consumer_groups(topic="*")
        outbox_stats = await framework.get_outbox_stats()
        dlq_count = await bus.get_dlq_count()

        return EventSystemStatus(
            running=True,
            broker_type=bus.__class__.__name__,
            topics_count=len(topics),
            consumers_count=len(consumers),
            outbox_pending=outbox_stats.get("pending", 0),
            dlq_count=dlq_count,
        )

    @router.get("/topics", response_model=TopicsResponse)
    async def list_topics() -> TopicsResponse:
        """
        List all event topics.

        Returns topic names with event counts and consumer groups.
        """
        if framework is None or framework.bus is None:
            return TopicsResponse(topics=[], total_events=0)

        topics: list[TopicInfo] = []
        total_events = 0

        topic_names = await framework.bus.list_topics()
        for name in topic_names:
            info = await framework.bus.get_topic_info(name)
            topics.append(
                TopicInfo(
                    name=name,
                    event_count=info.get("event_count", 0),
                    consumer_groups=info.get("consumer_groups", []),
                    dlq_count=info.get("dlq_count", 0),
                    oldest_event=info.get("oldest_event"),
                    newest_event=info.get("newest_event"),
                )
            )
            total_events += info.get("event_count", 0)

        return TopicsResponse(topics=topics, total_events=total_events)

    @router.get("/topics/{topic}", response_model=EventsResponse)
    async def list_events(
        topic: str,
        offset: int = Query(default=0, ge=0, description="Number of events to skip"),
        limit: int = Query(default=20, ge=1, le=100, description="Maximum events to return"),
        key: str | None = Query(default=None, description="Filter by partition key"),
        event_type: str | None = Query(default=None, description="Filter by event type"),
    ) -> EventsResponse:
        """
        List events in a topic.

        Returns paginated events with optional filtering.
        """
        if framework is None or framework.bus is None:
            return EventsResponse(
                topic=topic,
                events=[],
                total=0,
                offset=offset,
                limit=limit,
            )

        bus = cast(EventBusExplorer, framework.bus)
        events: list[EventSummary] = []
        total = 0
        current = 0

        async for event in bus.replay(  # type: ignore[call-arg]  # event_type_filter not in ABC
            topic,
            key_filter=key,
            event_type_filter=event_type,
        ):
            total += 1
            if current >= offset and len(events) < limit:
                payload_preview = json.dumps(event.payload, default=str)[:100]
                if len(payload_preview) == 100:
                    payload_preview += "..."

                events.append(
                    EventSummary(
                        event_id=str(event.event_id),
                        event_type=event.event_type,
                        key=event.key,
                        timestamp=event.timestamp.isoformat(),
                        payload_preview=payload_preview,
                    )
                )
            current += 1

        return EventsResponse(
            topic=topic,
            events=events,
            total=total,
            offset=offset,
            limit=limit,
        )

    @router.get("/event/{event_id}", response_model=EventDetail | None)
    async def get_event(event_id: str) -> EventDetail | None:
        """
        Get full details of a specific event.

        Args:
            event_id: UUID of the event to retrieve
        """
        if framework is None or framework.bus is None:
            return None

        bus = cast(EventBusExplorer, framework.bus)
        event = await bus.get_event(event_id)
        if event is None:
            return None

        return EventDetail(
            event_id=str(event.event_id),
            event_type=event.event_type,
            event_version=event.event_version,
            key=event.key,
            timestamp=event.timestamp.isoformat(),
            payload=event.payload,
            headers=event.headers,
            correlation_id=str(event.correlation_id) if event.correlation_id else None,
            causation_id=str(event.causation_id) if event.causation_id else None,
            topic=getattr(event, "topic", "unknown"),
        )

    @router.get("/consumers", response_model=ConsumersResponse)
    async def list_consumers() -> ConsumersResponse:
        """
        List all consumer groups.

        Returns consumer group status and lag information.
        """
        if framework is None or framework.bus is None:
            return ConsumersResponse(consumers=[])

        bus = cast(EventBusExplorer, framework.bus)
        consumers: list[ConsumerInfo] = []
        groups: Any = await bus.list_consumer_groups(topic="*")

        for group in groups:
            info = await bus.get_consumer_info(group["group_id"], group["topic"])
            consumers.append(
                ConsumerInfo(
                    group_id=group["group_id"],
                    topic=group["topic"],
                    last_sequence=info.get("last_sequence", 0),
                    lag=info.get("lag", 0),
                )
            )

        return ConsumersResponse(consumers=consumers)

    @router.get("/outbox", response_model=OutboxResponse)
    async def outbox_status() -> OutboxResponse:
        """
        Get outbox status.

        Returns outbox statistics and recent entries.
        """
        if framework is None:
            return OutboxResponse(
                stats=OutboxStats(
                    pending=0,
                    publishing=0,
                    published=0,
                    failed=0,
                ),
                recent_entries=[],
            )

        stats_dict = await framework.get_outbox_stats()
        recent = await framework.get_recent_outbox_entries(limit=10)

        entries: list[OutboxEntry] = []
        for entry in recent:
            entries.append(
                OutboxEntry(
                    id=str(entry.id),
                    topic=entry.topic,
                    event_type=entry.event_type,
                    key=entry.key,
                    status=entry.status,
                    created_at=entry.created_at.isoformat()
                    if isinstance(entry.created_at, datetime)
                    else entry.created_at,
                    published_at=entry.published_at.isoformat()
                    if entry.published_at and isinstance(entry.published_at, datetime)
                    else entry.published_at,
                    attempts=entry.attempts,
                    last_error=entry.last_error,
                )
            )

        return OutboxResponse(
            stats=OutboxStats(
                pending=stats_dict.get("pending", 0),
                publishing=stats_dict.get("publishing", 0),
                published=stats_dict.get("published", 0),
                failed=stats_dict.get("failed", 0),
                oldest_pending=stats_dict.get("oldest_pending"),
            ),
            recent_entries=entries,
        )

    @router.get("/dlq", response_model=DLQResponse)
    async def dlq_list(
        topic: str | None = Query(default=None, description="Filter by topic"),
        limit: int = Query(default=20, ge=1, le=100, description="Maximum entries to return"),
    ) -> DLQResponse:
        """
        List dead letter queue entries.

        Returns failed events that exceeded retry attempts.
        """
        if framework is None or framework.bus is None:
            return DLQResponse(entries=[], total=0)

        bus = cast(EventBusExplorer, framework.bus)
        dlq_events = await bus.get_dlq_events(topic=topic, limit=limit)

        entries: list[DLQEntry] = []
        for event in dlq_events:
            entries.append(
                DLQEntry(
                    event_id=event["event_id"],
                    topic=event["topic"],
                    group_id=event["group_id"],
                    reason_code=event.get("reason_code", "unknown"),
                    reason_message=event.get("reason_message", ""),
                    attempts=event.get("attempts", 0),
                    created_at=event.get("created_at", ""),
                )
            )

        total = await bus.get_dlq_count(topic=topic)

        return DLQResponse(entries=entries, total=total)

    @router.post("/dlq/{event_id}/replay")
    async def replay_dlq_event(
        event_id: str,
        group_id: str = Query(..., description="Consumer group to replay to"),
    ) -> dict[str, Any]:
        """
        Replay a single event from the DLQ.

        Removes the event from DLQ and re-queues it for processing.
        """
        if framework is None or framework.bus is None:
            return {"success": False, "error": "Event system not running"}

        bus = cast(EventBusExplorer, framework.bus)
        try:
            success = await bus.replay_dlq_event(event_id, group_id)
            if success:
                return {"success": True, "message": f"Event {event_id} replayed successfully"}
            else:
                return {"success": False, "error": f"Event {event_id} not found in DLQ"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    return router
