"""
Health Check Aggregator.

Aggregates health status from all system components:
- Database connectivity
- Event bus status
- External API connections
- Background workers
- WebSocket connections

Emits health events for SSE streaming.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from dazzle_back.runtime.ops_database import (
    ComponentType,
    HealthCheckRecord,
    HealthStatus,
    OpsDatabase,
)

if TYPE_CHECKING:
    from dazzle_back.events.bus import EventBus


class AggregateStatus(StrEnum):
    """Overall system health status."""

    ALL_HEALTHY = "all_healthy"
    SOME_DEGRADED = "some_degraded"
    SOME_UNHEALTHY = "some_unhealthy"
    ALL_UNHEALTHY = "all_unhealthy"


@dataclass
class ComponentHealth:
    """Health status of a single component."""

    name: str
    component_type: ComponentType
    status: HealthStatus
    latency_ms: float | None = None
    message: str | None = None
    last_checked: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemHealth:
    """Aggregated system health."""

    status: AggregateStatus
    components: list[ComponentHealth]
    checked_at: datetime
    healthy_count: int
    degraded_count: int
    unhealthy_count: int
    unknown_count: int

    @property
    def total_components(self) -> int:
        return len(self.components)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "checked_at": self.checked_at.isoformat(),
            "summary": {
                "total": self.total_components,
                "healthy": self.healthy_count,
                "degraded": self.degraded_count,
                "unhealthy": self.unhealthy_count,
                "unknown": self.unknown_count,
            },
            "components": [
                {
                    "name": c.name,
                    "type": c.component_type.value,
                    "status": c.status.value,
                    "latency_ms": c.latency_ms,
                    "message": c.message,
                    "last_checked": c.last_checked.isoformat() if c.last_checked else None,
                    "metadata": c.metadata,
                }
                for c in self.components
            ],
        }


# Type alias for health check functions
HealthCheckFn = Callable[[], Coroutine[Any, Any, ComponentHealth]]


class HealthAggregator:
    """
    Aggregates health from registered components.

    Components register health check functions that are called
    periodically. Results are stored in OpsDatabase and emitted
    via EventBus for SSE streaming.
    """

    def __init__(
        self,
        ops_db: OpsDatabase,
        event_bus: EventBus | None = None,
        check_interval_seconds: float = 30.0,
    ):
        """
        Initialize health aggregator.

        Args:
            ops_db: Operations database for storing health history
            event_bus: Optional event bus for emitting health events
            check_interval_seconds: Interval between health checks
        """
        self.ops_db = ops_db
        self.event_bus = event_bus
        self.check_interval = check_interval_seconds
        self._checks: dict[str, tuple[ComponentType, HealthCheckFn]] = {}
        self._latest: dict[str, ComponentHealth] = {}
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def register(
        self,
        name: str,
        component_type: ComponentType,
        check_fn: HealthCheckFn,
    ) -> None:
        """
        Register a health check function.

        Args:
            name: Unique component name
            component_type: Type of component
            check_fn: Async function that returns ComponentHealth
        """
        self._checks[name] = (component_type, check_fn)

    def unregister(self, name: str) -> None:
        """Unregister a health check."""
        self._checks.pop(name, None)
        self._latest.pop(name, None)

    async def check_component(self, name: str) -> ComponentHealth | None:
        """Run health check for a single component."""
        if name not in self._checks:
            return None

        component_type, check_fn = self._checks[name]

        start = time.monotonic()
        try:
            health = await asyncio.wait_for(check_fn(), timeout=10.0)
        except TimeoutError:
            health = ComponentHealth(
                name=name,
                component_type=component_type,
                status=HealthStatus.UNHEALTHY,
                message="Health check timed out",
            )
        except Exception as e:
            health = ComponentHealth(
                name=name,
                component_type=component_type,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
            )

        # Set latency if not already set
        if health.latency_ms is None:
            health.latency_ms = (time.monotonic() - start) * 1000

        health.last_checked = datetime.now(UTC)
        self._latest[name] = health

        # Record to database
        record = HealthCheckRecord(
            id=str(uuid4()),
            component=name,
            component_type=component_type,
            status=health.status,
            latency_ms=health.latency_ms,
            message=health.message,
            metadata=health.metadata,
            checked_at=health.last_checked,
        )
        self.ops_db.record_health_check(record)

        return health

    async def check_all(self) -> SystemHealth:
        """Run all registered health checks."""
        tasks = [self.check_component(name) for name in self._checks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        components: list[ComponentHealth] = []
        for result in results:
            if isinstance(result, ComponentHealth):
                components.append(result)
            elif isinstance(result, Exception):
                # This shouldn't happen given our error handling, but be safe
                pass

        # Calculate aggregate status
        healthy = sum(1 for c in components if c.status == HealthStatus.HEALTHY)
        degraded = sum(1 for c in components if c.status == HealthStatus.DEGRADED)
        unhealthy = sum(1 for c in components if c.status == HealthStatus.UNHEALTHY)
        unknown = sum(1 for c in components if c.status == HealthStatus.UNKNOWN)

        if unhealthy == len(components):
            aggregate_status = AggregateStatus.ALL_UNHEALTHY
        elif unhealthy > 0:
            aggregate_status = AggregateStatus.SOME_UNHEALTHY
        elif degraded > 0:
            aggregate_status = AggregateStatus.SOME_DEGRADED
        else:
            aggregate_status = AggregateStatus.ALL_HEALTHY

        system_health = SystemHealth(
            status=aggregate_status,
            components=components,
            checked_at=datetime.now(UTC),
            healthy_count=healthy,
            degraded_count=degraded,
            unhealthy_count=unhealthy,
            unknown_count=unknown,
        )

        # Emit event for SSE subscribers
        if self.event_bus:
            await self._emit_health_event(system_health)

        return system_health

    async def _emit_health_event(self, health: SystemHealth) -> None:
        """Emit health update event via EventBus."""
        if not self.event_bus:
            return

        from dazzle_back.events.envelope import EventEnvelope

        envelope = EventEnvelope.create(
            event_type="ops.health.updated",
            key="system",
            payload=health.to_dict(),
        )
        await self.event_bus.publish("ops.health", envelope)

    def get_latest(self) -> SystemHealth:
        """Get most recent health status without running new checks."""
        components = list(self._latest.values())

        healthy = sum(1 for c in components if c.status == HealthStatus.HEALTHY)
        degraded = sum(1 for c in components if c.status == HealthStatus.DEGRADED)
        unhealthy = sum(1 for c in components if c.status == HealthStatus.UNHEALTHY)
        unknown = sum(1 for c in components if c.status == HealthStatus.UNKNOWN)

        if not components:
            aggregate_status = AggregateStatus.ALL_HEALTHY
        elif unhealthy == len(components):
            aggregate_status = AggregateStatus.ALL_UNHEALTHY
        elif unhealthy > 0:
            aggregate_status = AggregateStatus.SOME_UNHEALTHY
        elif degraded > 0:
            aggregate_status = AggregateStatus.SOME_DEGRADED
        else:
            aggregate_status = AggregateStatus.ALL_HEALTHY

        return SystemHealth(
            status=aggregate_status,
            components=components,
            checked_at=datetime.now(UTC),
            healthy_count=healthy,
            degraded_count=degraded,
            unhealthy_count=unhealthy,
            unknown_count=unknown,
        )

    async def start_periodic_checks(self) -> None:
        """Start periodic health checking."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._check_loop())

    async def stop_periodic_checks(self) -> None:
        """Stop periodic health checking."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _check_loop(self) -> None:
        """Background loop for periodic checks."""
        while self._running:
            try:
                await self.check_all()
            except Exception:
                # Log but don't crash the loop
                pass
            await asyncio.sleep(self.check_interval)


# =============================================================================
# Built-in Health Checks
# =============================================================================


def create_database_check(
    db_path: str,
    name: str = "database",
    database_url: str | None = None,
) -> HealthCheckFn:
    """Create a database connectivity health check."""

    async def check() -> ComponentHealth:
        start = time.monotonic()
        try:
            if database_url:
                import psycopg

                conn: Any = psycopg.connect(database_url)
            else:
                import sqlite3

                conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            conn.close()
            latency = (time.monotonic() - start) * 1000

            return ComponentHealth(
                name=name,
                component_type=ComponentType.DATABASE,
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Database responding",
            )
        except Exception as e:
            return ComponentHealth(
                name=name,
                component_type=ComponentType.DATABASE,
                status=HealthStatus.UNHEALTHY,
                message=f"Database error: {e}",
            )

    return check


def create_event_bus_check(
    event_bus: EventBus,
    name: str = "event_bus",
) -> HealthCheckFn:
    """Create an event bus health check."""

    async def check() -> ComponentHealth:
        start = time.monotonic()
        try:
            # Try to get topics or perform a lightweight operation
            # This depends on the EventBus implementation
            stats: dict[str, Any] = getattr(event_bus, "get_stats", lambda: {})()
            latency = (time.monotonic() - start) * 1000

            return ComponentHealth(
                name=name,
                component_type=ComponentType.EVENT_BUS,
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Event bus operational",
                metadata=stats if isinstance(stats, dict) else {},
            )
        except Exception as e:
            return ComponentHealth(
                name=name,
                component_type=ComponentType.EVENT_BUS,
                status=HealthStatus.UNHEALTHY,
                message=f"Event bus error: {e}",
            )

    return check


def create_external_api_check(
    url: str,
    name: str,
    timeout_seconds: float = 5.0,
) -> HealthCheckFn:
    """Create an external API health check."""

    async def check() -> ComponentHealth:
        try:
            import httpx
        except ImportError:
            return ComponentHealth(
                name=name,
                component_type=ComponentType.EXTERNAL_API,
                status=HealthStatus.UNKNOWN,
                message="httpx not installed",
            )

        start = time.monotonic()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=timeout_seconds)
                latency = (time.monotonic() - start) * 1000

                if response.status_code < 400:
                    return ComponentHealth(
                        name=name,
                        component_type=ComponentType.EXTERNAL_API,
                        status=HealthStatus.HEALTHY,
                        latency_ms=latency,
                        message=f"API responding (HTTP {response.status_code})",
                    )
                elif response.status_code < 500:
                    return ComponentHealth(
                        name=name,
                        component_type=ComponentType.EXTERNAL_API,
                        status=HealthStatus.DEGRADED,
                        latency_ms=latency,
                        message=f"API client error (HTTP {response.status_code})",
                    )
                else:
                    return ComponentHealth(
                        name=name,
                        component_type=ComponentType.EXTERNAL_API,
                        status=HealthStatus.UNHEALTHY,
                        latency_ms=latency,
                        message=f"API server error (HTTP {response.status_code})",
                    )
        except httpx.TimeoutException:
            return ComponentHealth(
                name=name,
                component_type=ComponentType.EXTERNAL_API,
                status=HealthStatus.UNHEALTHY,
                message=f"API timeout after {timeout_seconds}s",
            )
        except Exception as e:
            return ComponentHealth(
                name=name,
                component_type=ComponentType.EXTERNAL_API,
                status=HealthStatus.UNHEALTHY,
                message=f"API error: {e}",
            )

    return check


def create_websocket_check(
    ws_manager: Any,
    name: str = "websocket",
) -> HealthCheckFn:
    """Create a WebSocket manager health check."""

    async def check() -> ComponentHealth:
        try:
            # Get connection stats from WebSocket manager
            stats = ws_manager.get_stats() if hasattr(ws_manager, "get_stats") else {}
            connection_count = stats.get("connections", 0)

            return ComponentHealth(
                name=name,
                component_type=ComponentType.WEBSOCKET,
                status=HealthStatus.HEALTHY,
                message=f"{connection_count} active connections",
                metadata=stats,
            )
        except Exception as e:
            return ComponentHealth(
                name=name,
                component_type=ComponentType.WEBSOCKET,
                status=HealthStatus.UNHEALTHY,
                message=f"WebSocket error: {e}",
            )

    return check
