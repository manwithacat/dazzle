"""
Tenant-Scoped Analytics Collector.

Collects analytics events from the application and stores them
in the ops database with tenant scoping for privacy.

Analytics types:
- Page views
- User actions (clicks, form submissions)
- Feature usage
- Conversions
- Custom events

All analytics are tenant-scoped to ensure data isolation.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from dazzle_back.runtime.ops_database import AnalyticsEvent, OpsDatabase

if TYPE_CHECKING:
    from dazzle_back.events.bus import EventBus

logger = logging.getLogger(__name__)


class AnalyticsEventType:
    """Standard analytics event types."""

    PAGE_VIEW = "page_view"
    ACTION = "action"
    CLICK = "click"
    FORM_SUBMIT = "form_submit"
    SEARCH = "search"
    CONVERSION = "conversion"
    ERROR = "error"
    FEATURE_USE = "feature_use"
    CUSTOM = "custom"


@dataclass
class AnalyticsContext:
    """Context for analytics events."""

    tenant_id: str
    user_id: str | None = None
    session_id: str | None = None
    page_url: str | None = None
    referrer: str | None = None
    user_agent: str | None = None
    ip_address: str | None = None  # Anonymized for GDPR


@dataclass
class AnalyticsConfig:
    """Analytics configuration."""

    # Whether to collect analytics
    enabled: bool = True

    # Whether to emit events to EventBus for SSE streaming
    emit_events: bool = True

    # Batch settings for performance
    batch_size: int = 10
    batch_interval_seconds: float = 5.0

    # Privacy settings
    anonymize_ip: bool = True
    collect_user_agent: bool = True

    # Excluded paths (e.g., health checks, static assets)
    excluded_paths: list[str] = field(
        default_factory=lambda: [
            "/_ops/",
            "/health",
            "/static/",
            "/favicon.ico",
        ]
    )


class AnalyticsCollector:
    """
    Collects and stores tenant-scoped analytics.

    Analytics are batched for performance and can be streamed
    via SSE for real-time monitoring.
    """

    def __init__(
        self,
        ops_db: OpsDatabase,
        event_bus: EventBus | None = None,
        config: AnalyticsConfig | None = None,
    ):
        """
        Initialize analytics collector.

        Args:
            ops_db: Operations database for storage
            event_bus: Optional event bus for SSE streaming
            config: Analytics configuration
        """
        self.ops_db = ops_db
        self.event_bus = event_bus
        self.config = config or AnalyticsConfig()

        self._batch: list[AnalyticsEvent] = []
        self._batch_lock = asyncio.Lock()
        self._running = False
        self._flush_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the analytics collector."""
        if self._running:
            return

        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        """Stop the collector and flush remaining events."""
        self._running = False

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Flush remaining events
        await self._flush_batch()

    # =========================================================================
    # Event Collection
    # =========================================================================

    async def track_page_view(
        self,
        context: AnalyticsContext,
        page_title: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """
        Track a page view.

        Args:
            context: Analytics context with tenant and user info
            page_title: Optional page title
            properties: Additional properties

        Returns:
            Event ID
        """
        return await self._track(
            context=context,
            event_type=AnalyticsEventType.PAGE_VIEW,
            event_name=page_title or context.page_url or "unknown",
            properties={
                "url": context.page_url,
                "referrer": context.referrer,
                **(properties or {}),
            },
        )

    async def track_action(
        self,
        context: AnalyticsContext,
        action_name: str,
        category: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """
        Track a user action.

        Args:
            context: Analytics context
            action_name: Name of the action
            category: Optional category
            properties: Additional properties

        Returns:
            Event ID
        """
        return await self._track(
            context=context,
            event_type=AnalyticsEventType.ACTION,
            event_name=action_name,
            properties={
                "category": category,
                **(properties or {}),
            },
        )

    async def track_click(
        self,
        context: AnalyticsContext,
        element_id: str,
        element_text: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """
        Track a click event.

        Args:
            context: Analytics context
            element_id: ID of clicked element
            element_text: Optional text of clicked element
            properties: Additional properties

        Returns:
            Event ID
        """
        return await self._track(
            context=context,
            event_type=AnalyticsEventType.CLICK,
            event_name=element_id,
            properties={
                "element_text": element_text,
                **(properties or {}),
            },
        )

    async def track_form_submit(
        self,
        context: AnalyticsContext,
        form_name: str,
        success: bool = True,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """
        Track a form submission.

        Args:
            context: Analytics context
            form_name: Name of the form
            success: Whether submission was successful
            properties: Additional properties

        Returns:
            Event ID
        """
        return await self._track(
            context=context,
            event_type=AnalyticsEventType.FORM_SUBMIT,
            event_name=form_name,
            properties={
                "success": success,
                **(properties or {}),
            },
        )

    async def track_search(
        self,
        context: AnalyticsContext,
        query: str,
        results_count: int | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """
        Track a search event.

        Args:
            context: Analytics context
            query: Search query
            results_count: Number of results
            properties: Additional properties

        Returns:
            Event ID
        """
        return await self._track(
            context=context,
            event_type=AnalyticsEventType.SEARCH,
            event_name="search",
            properties={
                "query": query,
                "results_count": results_count,
                **(properties or {}),
            },
        )

    async def track_conversion(
        self,
        context: AnalyticsContext,
        conversion_name: str,
        value: float | None = None,
        currency: str = "GBP",
        properties: dict[str, Any] | None = None,
    ) -> str:
        """
        Track a conversion event.

        Args:
            context: Analytics context
            conversion_name: Name of the conversion
            value: Optional monetary value
            currency: Currency code
            properties: Additional properties

        Returns:
            Event ID
        """
        return await self._track(
            context=context,
            event_type=AnalyticsEventType.CONVERSION,
            event_name=conversion_name,
            properties={
                "value": value,
                "currency": currency,
                **(properties or {}),
            },
        )

    async def track_feature_use(
        self,
        context: AnalyticsContext,
        feature_name: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """
        Track feature usage.

        Args:
            context: Analytics context
            feature_name: Name of the feature
            properties: Additional properties

        Returns:
            Event ID
        """
        return await self._track(
            context=context,
            event_type=AnalyticsEventType.FEATURE_USE,
            event_name=feature_name,
            properties=properties,
        )

    async def track_error(
        self,
        context: AnalyticsContext,
        error_name: str,
        error_message: str | None = None,
        stack_trace: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """
        Track an error event.

        Args:
            context: Analytics context
            error_name: Name/type of error
            error_message: Error message
            stack_trace: Optional stack trace
            properties: Additional properties

        Returns:
            Event ID
        """
        return await self._track(
            context=context,
            event_type=AnalyticsEventType.ERROR,
            event_name=error_name,
            properties={
                "message": error_message,
                "stack_trace": stack_trace,
                **(properties or {}),
            },
        )

    async def track_custom(
        self,
        context: AnalyticsContext,
        event_name: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """
        Track a custom event.

        Args:
            context: Analytics context
            event_name: Custom event name
            properties: Event properties

        Returns:
            Event ID
        """
        return await self._track(
            context=context,
            event_type=AnalyticsEventType.CUSTOM,
            event_name=event_name,
            properties=properties,
        )

    # =========================================================================
    # Internal Methods
    # =========================================================================

    async def _track(
        self,
        context: AnalyticsContext,
        event_type: str,
        event_name: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """Internal method to track an event."""
        if not self.config.enabled:
            return ""

        # Check excluded paths
        if context.page_url:
            for excluded in self.config.excluded_paths:
                if context.page_url.startswith(excluded):
                    return ""

        # Create event
        event_id = str(uuid4())
        event = AnalyticsEvent(
            id=event_id,
            tenant_id=context.tenant_id,
            event_type=event_type,
            event_name=event_name,
            user_id=context.user_id,
            session_id=context.session_id,
            properties=self._build_properties(context, properties),
            recorded_at=datetime.now(UTC),
        )

        # Add to batch
        async with self._batch_lock:
            self._batch.append(event)

            # Flush if batch is full
            if len(self._batch) >= self.config.batch_size:
                await self._flush_batch()

        # Emit to event bus for SSE
        if self.config.emit_events and self.event_bus:
            await self._emit_event(event)

        return event_id

    def _build_properties(
        self,
        context: AnalyticsContext,
        additional: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build event properties with context."""
        properties: dict[str, Any] = {}

        if context.page_url:
            properties["page_url"] = context.page_url
        if context.referrer:
            properties["referrer"] = context.referrer
        if self.config.collect_user_agent and context.user_agent:
            properties["user_agent"] = context.user_agent
        if context.ip_address:
            if self.config.anonymize_ip:
                # Anonymize by removing last octet
                parts = context.ip_address.split(".")
                if len(parts) == 4:
                    properties["ip_address"] = ".".join(parts[:3]) + ".0"
            else:
                properties["ip_address"] = context.ip_address

        if additional:
            properties.update(additional)

        return properties

    async def _flush_batch(self) -> None:
        """Flush the current batch to storage."""
        async with self._batch_lock:
            if not self._batch:
                return

            events = self._batch
            self._batch = []

        # Store all events
        for event in events:
            try:
                self.ops_db.record_analytics_event(event)
            except Exception as e:
                # Log but don't fail
                print(f"Failed to store analytics event: {e}")

    async def _flush_loop(self) -> None:
        """Background loop for periodic flushing."""
        while self._running:
            await asyncio.sleep(self.config.batch_interval_seconds)
            try:
                await self._flush_batch()
            except Exception:
                logger.warning("Analytics flush failed", exc_info=True)

    async def _emit_event(self, event: AnalyticsEvent) -> None:
        """Emit event to EventBus for SSE streaming."""
        if not self.event_bus:
            return

        try:
            from dazzle_back.events.envelope import EventEnvelope

            envelope = EventEnvelope.create(
                event_type=f"ops.analytics.{event.event_type}",
                key=event.tenant_id,
                payload={
                    "id": event.id,
                    "tenant_id": event.tenant_id,
                    "event_type": event.event_type,
                    "event_name": event.event_name,
                    "user_id": event.user_id,
                    "properties": event.properties,
                    "recorded_at": event.recorded_at.isoformat(),
                },
                headers={"tenant_id": event.tenant_id},
            )
            await self.event_bus.publish("ops.analytics", envelope)
        except Exception as e:
            print(f"Failed to emit analytics event: {e}")


# =============================================================================
# FastAPI Integration
# =============================================================================


def create_analytics_routes(collector: AnalyticsCollector) -> Any:
    """
    Create FastAPI routes for analytics collection.

    These endpoints allow the frontend to send analytics events.
    All events are tenant-scoped.

    Args:
        collector: AnalyticsCollector instance

    Returns:
        FastAPI APIRouter
    """
    try:
        from fastapi import APIRouter, Header, Request
        from pydantic import BaseModel
    except ImportError:
        raise RuntimeError("FastAPI required for analytics routes")

    router = APIRouter(prefix="/_analytics", tags=["Analytics"])

    class TrackRequest(BaseModel):
        event_type: str
        event_name: str
        properties: dict[str, Any] | None = None

    class TrackResponse(BaseModel):
        event_id: str

    @router.post("/track", response_model=TrackResponse)
    async def track_event(
        request: Request,
        body: TrackRequest,
        x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
        x_user_id: str | None = Header(None, alias="X-User-ID"),
        x_session_id: str | None = Header(None, alias="X-Session-ID"),
    ) -> TrackResponse:
        """
        Track an analytics event.

        Tenant ID is required. User and session IDs are optional.
        """
        context = AnalyticsContext(
            tenant_id=x_tenant_id,
            user_id=x_user_id,
            session_id=x_session_id,
            page_url=request.headers.get("Referer"),
            user_agent=request.headers.get("User-Agent"),
            ip_address=request.client.host if request.client else None,
        )

        event_id = await collector.track_custom(
            context=context,
            event_name=body.event_name,
            properties={"event_type": body.event_type, **(body.properties or {})},
        )

        return TrackResponse(event_id=event_id)

    @router.post("/page-view", response_model=TrackResponse)
    async def track_page_view(
        request: Request,
        x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
        x_user_id: str | None = Header(None, alias="X-User-ID"),
        x_session_id: str | None = Header(None, alias="X-Session-ID"),
    ) -> TrackResponse:
        """
        Track a page view.

        Uses Referer header for page URL.
        """
        context = AnalyticsContext(
            tenant_id=x_tenant_id,
            user_id=x_user_id,
            session_id=x_session_id,
            page_url=request.headers.get("Referer"),
            user_agent=request.headers.get("User-Agent"),
            ip_address=request.client.host if request.client else None,
        )

        event_id = await collector.track_page_view(context)
        return TrackResponse(event_id=event_id)

    # -------------------------------------------------------------------------
    # Beacon-friendly endpoints (for sendBeacon API)
    # -------------------------------------------------------------------------

    class BeaconPageView(BaseModel):
        """Page view data from client-side beacon."""

        path: str
        title: str | None = None
        query: dict[str, str] | None = None
        referrer: str | None = None
        screen_size: str | None = None
        load_time_ms: int | None = None
        session_id: str | None = None
        tenant_id: str | None = None

    class BeaconEvent(BaseModel):
        """Custom event data from client-side beacon."""

        event_type: str
        event_name: str
        properties: dict[str, Any] | None = None
        session_id: str | None = None
        tenant_id: str | None = None

    @router.post("/beacon/pageview")
    async def beacon_page_view(
        request: Request,
        body: BeaconPageView,
    ) -> dict[str, str]:
        """
        Track a page view via sendBeacon API.

        Designed for client-side JavaScript using navigator.sendBeacon().
        Session ID is generated client-side. Tenant ID is optional
        (derived from authenticated user if available).
        """
        # Get tenant_id from body or try to get from header
        tenant_id = body.tenant_id or request.headers.get("X-Tenant-ID") or "default"

        context = AnalyticsContext(
            tenant_id=tenant_id,
            session_id=body.session_id,
            page_url=body.path,
            referrer=body.referrer,
            user_agent=request.headers.get("User-Agent"),
            ip_address=request.client.host if request.client else None,
        )

        event_id = await collector.track_page_view(
            context=context,
            page_title=body.title,
            properties={
                "query_params": body.query,
                "screen_size": body.screen_size,
                "load_time_ms": body.load_time_ms,
            },
        )

        return {"event_id": event_id}

    @router.post("/beacon/event")
    async def beacon_event(
        request: Request,
        body: BeaconEvent,
    ) -> dict[str, str]:
        """
        Track a custom event via sendBeacon API.
        """
        tenant_id = body.tenant_id or request.headers.get("X-Tenant-ID") or "default"

        context = AnalyticsContext(
            tenant_id=tenant_id,
            session_id=body.session_id,
            page_url=request.headers.get("Referer"),
            user_agent=request.headers.get("User-Agent"),
            ip_address=request.client.host if request.client else None,
        )

        event_id = await collector.track_custom(
            context=context,
            event_name=body.event_name,
            properties={"event_type": body.event_type, **(body.properties or {})},
        )

        return {"event_id": event_id}

    return router
