"""
Operations Platform Routes.

Authenticated routes for the Control Plane dashboard:
- System health monitoring
- Event explorer
- API call tracking
- Analytics dashboard
- Configuration management

Authentication is separate from app auth - uses ops_database credentials.
Routes are prefixed with /_ops/ and require ops authentication.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

try:
    from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore
    HTTPException = None  # type: ignore

from dazzle_back.metrics.system_collector import SystemMetricsCollector
from dazzle_back.runtime.health_aggregator import HealthAggregator
from dazzle_back.runtime.ops_database import OpsDatabase
from dazzle_back.runtime.ops_services import (
    OpsSessionManager,
    format_health_result,
    query_analytics_tenants,
    query_api_costs,
    query_api_errors,
    query_email_stats,
    query_page_view_stats,
    query_recent_api_calls,
    query_recent_emails,
    query_top_email_links,
    query_traffic_sources,
)
from dazzle_back.runtime.ops_simulator import OpsSimulator
from dazzle_back.runtime.sse_stream import SSEStreamManager

# =============================================================================
# Request/Response Models
# =============================================================================


class OpsLoginRequest(BaseModel):
    """Ops admin login request."""

    username: str
    password: str


class OpsLoginResponse(BaseModel):
    """Ops admin login response."""

    success: bool
    message: str
    token: str | None = None


class OpsSetupRequest(BaseModel):
    """Initial ops admin setup request."""

    username: str = "ops_admin"
    password: str


class HealthSummary(BaseModel):
    """Health summary response."""

    status: str
    checked_at: str
    summary: dict[str, int]
    components: list[dict[str, Any]]


class EventQuery(BaseModel):
    """Event query parameters."""

    entity_name: str | None = None
    entity_id: str | None = None
    event_type: str | None = None
    correlation_id: str | None = None
    tenant_id: str | None = None
    limit: int = Field(default=100, le=1000)
    offset: int = Field(default=0, ge=0)


class ApiCallQuery(BaseModel):
    """API call query parameters."""

    service_name: str | None = None
    hours: int = Field(default=24, le=168)  # Max 1 week
    tenant_id: str | None = None


class AnalyticsQuery(BaseModel):
    """Analytics query parameters."""

    tenant_id: str
    event_type: str | None = None
    days: int = Field(default=7, le=90)


class RetentionConfigUpdate(BaseModel):
    """Retention configuration update."""

    health_checks_days: int | None = None
    api_calls_days: int | None = None
    analytics_days: int | None = None
    events_days: int | None = None


# =============================================================================
# Route Factory
# =============================================================================


def create_ops_routes(
    ops_db: OpsDatabase,
    health_aggregator: HealthAggregator | None = None,
    sse_manager: SSEStreamManager | None = None,
    simulator: OpsSimulator | None = None,
    metrics_collector: SystemMetricsCollector | None = None,
    require_auth: bool = True,
) -> APIRouter:
    """
    Create Operations Platform routes.

    Args:
        ops_db: Operations database
        health_aggregator: Health check aggregator (optional)
        sse_manager: SSE stream manager (optional)
        simulator: Ops simulator for demo mode (optional)
        metrics_collector: System metrics collector (optional)
        require_auth: Whether to require authentication (default True)

    Returns:
        FastAPI APIRouter with ops endpoints
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI required for ops routes")

    router = APIRouter(prefix="/_ops", tags=["Operations Platform"])
    session_manager = OpsSessionManager()

    # -------------------------------------------------------------------------
    # Authentication Dependency
    # -------------------------------------------------------------------------

    async def get_current_ops_user(
        ops_session: str | None = Cookie(None),
    ) -> str:
        """Validate ops session and return username."""
        if not require_auth:
            return "anonymous"

        if not ops_session:
            raise HTTPException(
                status_code=401,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        username = session_manager.validate_session(ops_session)
        if not username:
            raise HTTPException(
                status_code=401,
                detail="Session expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return username

    # -------------------------------------------------------------------------
    # Setup & Authentication Endpoints
    # -------------------------------------------------------------------------

    @router.get("/setup-required")
    async def check_setup_required() -> dict[str, bool]:
        """Check if initial ops admin setup is required."""
        return {"setup_required": not ops_db.has_credentials()}

    @router.post("/setup", response_model=OpsLoginResponse)
    async def setup_ops_admin(
        request: OpsSetupRequest,
        response: Response,
    ) -> OpsLoginResponse:
        """
        Initial ops admin setup.

        Creates the first ops admin account. Only works if no
        credentials exist yet.
        """
        if ops_db.has_credentials():
            raise HTTPException(
                status_code=400,
                detail="Ops admin already configured",
            )

        if len(request.password) < 8:
            raise HTTPException(
                status_code=400,
                detail="Password must be at least 8 characters",
            )

        ops_db.create_credentials(request.username, request.password)
        token = session_manager.create_session(request.username)

        response.set_cookie(
            key="ops_session",
            value=token,
            httponly=True,
            secure=False,  # Set True in production with HTTPS
            samesite="lax",
            max_age=86400,  # 24 hours
        )

        return OpsLoginResponse(
            success=True,
            message="Ops admin created",
            token=token,
        )

    @router.post("/login", response_model=OpsLoginResponse)
    async def login(
        request: OpsLoginRequest,
        response: Response,
    ) -> OpsLoginResponse:
        """
        Ops admin login.

        Returns a session token for authenticated access.
        """
        if not ops_db.verify_credentials(request.username, request.password):
            raise HTTPException(
                status_code=401,
                detail="Invalid credentials",
            )

        token = session_manager.create_session(request.username)

        response.set_cookie(
            key="ops_session",
            value=token,
            httponly=True,
            secure=False,  # Set True in production
            samesite="lax",
            max_age=86400,
        )

        return OpsLoginResponse(
            success=True,
            message="Login successful",
            token=token,
        )

    @router.post("/logout")
    async def logout(
        response: Response,
        ops_session: str | None = Cookie(None),
    ) -> dict[str, str]:
        """Log out and clear session."""
        if ops_session:
            session_manager.revoke_session(ops_session)

        response.delete_cookie("ops_session")
        return {"status": "logged_out"}

    @router.get("/me")
    async def get_current_user_info(
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, str]:
        """Get current authenticated user info."""
        return {"username": username}

    # -------------------------------------------------------------------------
    # Health Endpoints
    # -------------------------------------------------------------------------

    @router.get("/health", response_model=HealthSummary)
    async def get_health(
        username: str = Depends(get_current_ops_user),
    ) -> HealthSummary:
        """
        Get current system health status.

        Returns aggregated health from all registered components.
        """
        if not health_aggregator:
            return HealthSummary(
                status="unknown",
                checked_at=datetime.now(UTC).isoformat(),
                summary={"total": 0, "healthy": 0, "degraded": 0, "unhealthy": 0, "unknown": 0},
                components=[],
            )

        health = health_aggregator.get_latest()
        return HealthSummary(**format_health_result(health))

    @router.post("/health/check")
    async def run_health_check(
        username: str = Depends(get_current_ops_user),
    ) -> HealthSummary:
        """
        Trigger an immediate health check.

        Runs all registered health checks and returns results.
        """
        if not health_aggregator:
            raise HTTPException(status_code=503, detail="Health aggregator not configured")

        health = await health_aggregator.check_all()
        return HealthSummary(**format_health_result(health))

    @router.get("/health/history/{component}")
    async def get_health_history(
        component: str,
        hours: int = Query(default=24, le=168),
        username: str = Depends(get_current_ops_user),
    ) -> list[dict[str, Any]]:
        """
        Get health check history for a component.

        Returns historical health checks for analysis and debugging.
        """
        records = ops_db.get_health_history(component, hours)
        return [
            {
                "id": r.id,
                "status": r.status.value,
                "latency_ms": r.latency_ms,
                "message": r.message,
                "checked_at": r.checked_at.isoformat(),
            }
            for r in records
        ]

    # -------------------------------------------------------------------------
    # Event Explorer Endpoints
    # -------------------------------------------------------------------------

    @router.get("/events")
    async def get_events(
        entity_name: str | None = Query(None),
        entity_id: str | None = Query(None),
        event_type: str | None = Query(None),
        correlation_id: str | None = Query(None),
        tenant_id: str | None = Query(None),
        limit: int = Query(default=100, le=1000),
        offset: int = Query(default=0, ge=0),
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Query event log.

        Returns events matching the specified filters.
        Supports pagination via limit/offset.
        """
        events = ops_db.get_events(
            entity_name=entity_name,
            entity_id=entity_id,
            event_type=event_type,
            correlation_id=correlation_id,
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
        )
        return {
            "events": events,
            "count": len(events),
            "limit": limit,
            "offset": offset,
        }

    @router.get("/events/{event_id}")
    async def get_event(
        event_id: str,
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """Get a single event by ID."""
        events = ops_db.get_events(limit=1)
        # TODO: Add get_event_by_id method to ops_db
        for event in events:
            if event["id"] == event_id:
                return event

        raise HTTPException(status_code=404, detail="Event not found")

    # -------------------------------------------------------------------------
    # API Call Tracking Endpoints (Integration Observatory)
    # -------------------------------------------------------------------------

    @router.get("/api-calls/stats")
    async def get_api_call_stats(
        service_name: str | None = Query(None),
        hours: int = Query(default=24, le=168),
        tenant_id: str | None = Query(None),
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Get API call statistics.

        Returns aggregated stats for external API calls including
        latency, error rates, and costs.
        """
        stats = ops_db.get_api_call_stats(
            service_name=service_name,
            hours=hours,
            tenant_id=tenant_id,
        )
        return {
            "period_hours": hours,
            "services": stats,
        }

    @router.get("/api-calls/recent")
    async def get_recent_api_calls(
        service_name: str | None = Query(None),
        status: str | None = Query(None, description="success, error, or all"),
        limit: int = Query(default=50, le=200),
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Get recent API calls.

        Returns individual API call records for debugging.
        """
        calls = query_recent_api_calls(
            ops_db, service_name=service_name, status=status, limit=limit
        )
        return {
            "calls": calls,
            "count": len(calls),
        }

    @router.get("/api-calls/costs")
    async def get_api_costs(
        days: int = Query(default=30, le=90),
        group_by: str = Query(default="service", description="service or day"),
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Get API cost breakdown.

        Returns cost aggregation by service or by day.
        """
        return query_api_costs(ops_db, days=days, group_by=group_by)

    @router.get("/api-calls/errors")
    async def get_api_errors(
        hours: int = Query(default=24, le=168),
        service_name: str | None = Query(None),
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Get recent API errors.

        Returns failed API calls for debugging.
        """
        return query_api_errors(ops_db, hours=hours, service_name=service_name)

    # -------------------------------------------------------------------------
    # Analytics Endpoints
    # -------------------------------------------------------------------------

    @router.get("/analytics/{tenant_id}")
    async def get_analytics_summary(
        tenant_id: str,
        event_type: str | None = Query(None),
        days: int = Query(default=7, le=90),
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Get analytics summary for a tenant.

        Returns aggregated analytics data including event counts,
        unique users, and sessions.
        """
        return ops_db.get_analytics_summary(
            tenant_id=tenant_id,
            event_type=event_type,
            days=days,
        )

    @router.get("/analytics/{tenant_id}/page-views")
    async def get_page_view_stats(
        tenant_id: str,
        days: int = Query(default=7, le=90),
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Get page view statistics for a tenant.

        Returns daily page views, top pages, and session metrics.
        """
        return query_page_view_stats(ops_db, tenant_id=tenant_id, days=days)

    @router.get("/analytics/{tenant_id}/traffic-sources")
    async def get_traffic_sources(
        tenant_id: str,
        days: int = Query(default=7, le=90),
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Get traffic source breakdown for a tenant.

        Returns referrer breakdown and UTM parameter analysis.
        """
        return query_traffic_sources(ops_db, tenant_id=tenant_id, days=days)

    @router.get("/analytics/tenants")
    async def list_analytics_tenants(
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        List all tenants with analytics data.

        Returns tenant IDs and event counts for tenant selection.
        """
        return query_analytics_tenants(ops_db)

    # -------------------------------------------------------------------------
    # Configuration Endpoints
    # -------------------------------------------------------------------------

    @router.get("/config/retention")
    async def get_retention_config(
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, int]:
        """Get current data retention configuration."""
        config = ops_db.get_retention_config()
        return {
            "health_checks_days": config.health_checks_days,
            "api_calls_days": config.api_calls_days,
            "analytics_days": config.analytics_days,
            "events_days": config.events_days,
        }

    @router.put("/config/retention")
    async def update_retention_config(
        update: RetentionConfigUpdate,
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Update data retention configuration.

        Changes take effect on next retention enforcement run.
        """
        from dazzle_back.runtime.ops_database import RetentionConfig

        current = ops_db.get_retention_config()

        new_config = RetentionConfig(
            health_checks_days=update.health_checks_days or current.health_checks_days,
            api_calls_days=update.api_calls_days or current.api_calls_days,
            analytics_days=update.analytics_days or current.analytics_days,
            events_days=update.events_days or current.events_days,
        )

        ops_db.set_retention_config(new_config)

        return {
            "status": "updated",
            "config": {
                "health_checks_days": new_config.health_checks_days,
                "api_calls_days": new_config.api_calls_days,
                "analytics_days": new_config.analytics_days,
                "events_days": new_config.events_days,
            },
        }

    @router.post("/config/retention/enforce")
    async def enforce_retention(
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Manually trigger retention enforcement.

        Deletes data older than configured retention periods.
        Returns count of deleted records per table.
        """
        deleted = ops_db.enforce_retention()
        return {
            "status": "enforced",
            "deleted": deleted,
        }

    # -------------------------------------------------------------------------
    # SSE Stats Endpoint
    # -------------------------------------------------------------------------

    @router.get("/sse/stats")
    async def get_sse_stats(
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """Get SSE stream statistics."""
        if not sse_manager:
            return {"available": False}

        stats = sse_manager.get_stats()
        stats["available"] = True
        return stats

    # -------------------------------------------------------------------------
    # Email Dashboard Endpoints
    # -------------------------------------------------------------------------

    @router.get("/email/stats")
    async def get_email_stats(
        days: int = Query(default=7, le=90),
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Get email statistics.

        Returns counts of sent, opened, and clicked emails.
        """
        return query_email_stats(ops_db, days=days)

    @router.get("/email/recent")
    async def get_recent_emails(
        limit: int = Query(default=50, le=200),
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Get recent email events.

        Returns individual email tracking events for debugging.
        """
        emails = query_recent_emails(ops_db, limit=limit)
        return {
            "emails": emails,
            "count": len(emails),
        }

    @router.get("/email/top-links")
    async def get_top_email_links(
        days: int = Query(default=30, le=90),
        limit: int = Query(default=10, le=50),
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Get top clicked links in emails.

        Returns the most frequently clicked URLs for link optimization.
        """
        links = query_top_email_links(ops_db, days=days, limit=limit)
        return {
            "period_days": days,
            "links": links,
        }

    # -------------------------------------------------------------------------
    # Simulation Endpoints
    # -------------------------------------------------------------------------

    @router.get("/simulation/status")
    async def get_simulation_status(
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Get simulation status.

        Returns whether simulation is running and statistics.
        """
        if not simulator:
            return {
                "available": False,
                "running": False,
                "message": "Simulator not configured",
            }

        stats = simulator.stats
        return {
            "available": True,
            "running": simulator.running,
            "stats": {
                "started_at": stats.started_at.isoformat() if stats.started_at else None,
                "events_generated": stats.events_generated,
                "health_checks": stats.health_checks,
                "api_calls": stats.api_calls,
                "emails": stats.emails,
            }
            if simulator.running
            else None,
        }

    @router.post("/simulation/start")
    async def start_simulation(
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Start the simulation.

        Generates synthetic events for dashboard demonstration.
        """
        if not simulator:
            raise HTTPException(
                status_code=503,
                detail="Simulator not configured",
            )

        if simulator.running:
            return {
                "success": True,
                "message": "Simulation already running",
            }

        await simulator.start()
        return {
            "success": True,
            "message": "Simulation started",
        }

    @router.post("/simulation/stop")
    async def stop_simulation(
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Stop the simulation.

        Stops generating synthetic events.
        """
        if not simulator:
            raise HTTPException(
                status_code=503,
                detail="Simulator not configured",
            )

        if not simulator.running:
            return {
                "success": True,
                "message": "Simulation not running",
            }

        await simulator.stop()
        return {
            "success": True,
            "message": "Simulation stopped",
            "stats": {
                "events_generated": simulator.stats.events_generated,
            },
        }

    # -------------------------------------------------------------------------
    # System Metrics Endpoints
    # -------------------------------------------------------------------------

    @router.get("/metrics", include_in_schema=False)
    async def get_prometheus_metrics() -> Response:
        """
        Prometheus metrics endpoint.

        Returns system metrics in Prometheus text format for scraping.
        No authentication required to allow Prometheus scraping.
        """
        if not metrics_collector:
            return Response(
                content="# No metrics collector configured\n",
                media_type="text/plain; version=0.0.4",
            )

        snapshot = metrics_collector.snapshot()
        return Response(
            content=snapshot.to_prometheus(),
            media_type="text/plain; version=0.0.4",
        )

    @router.get("/system-metrics")
    async def get_system_metrics(
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Get system metrics as JSON.

        Returns comprehensive metrics from all system components
        for dashboard visualization.
        """
        if not metrics_collector:
            return {
                "available": False,
                "message": "Metrics collector not configured",
            }

        snapshot = metrics_collector.snapshot()
        data = snapshot.to_dict()
        data["available"] = True
        return data

    @router.get("/system-metrics/component/{component}")
    async def get_component_metrics(
        component: str,
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, Any]:
        """
        Get metrics for a specific component.

        Returns detailed metrics for a single system component.
        """
        if not metrics_collector:
            raise HTTPException(
                status_code=503,
                detail="Metrics collector not configured",
            )

        from dazzle_back.metrics.system_collector import ComponentType

        try:
            comp_type = ComponentType(component)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown component: {component}. Valid: {[c.value for c in ComponentType]}",
            )

        snapshot = metrics_collector.snapshot()
        metrics = snapshot.components.get(comp_type)

        if not metrics:
            raise HTTPException(
                status_code=404,
                detail=f"No metrics for component: {component}",
            )

        from dazzle_back.metrics.system_collector import _compute_histogram_stats

        return {
            "component": component,
            "status": metrics.status,
            "last_check": metrics.last_check.isoformat() if metrics.last_check else None,
            "counters": metrics.counters,
            "gauges": metrics.gauges,
            "histograms": {
                name: _compute_histogram_stats(samples)
                for name, samples in metrics.histograms.items()
            },
            "recent_errors": metrics.errors[-10:],
        }

    @router.post("/system-metrics/reset")
    async def reset_system_metrics(
        username: str = Depends(get_current_ops_user),
    ) -> dict[str, str]:
        """
        Reset all system metrics.

        Clears accumulated metrics data. Use with caution.
        """
        if not metrics_collector:
            raise HTTPException(
                status_code=503,
                detail="Metrics collector not configured",
            )

        metrics_collector.reset()
        return {"status": "reset", "message": "All metrics have been reset"}

    return router
