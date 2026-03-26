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

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Any

from pydantic import BaseModel, Field

from dazzle_back.metrics.system_collector import SystemMetricsCollector
from dazzle_back.runtime._fastapi_compat import (
    FASTAPI_AVAILABLE,
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
)
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

DEPRECATION_HEADER_KEY = "X-Dazzle-Deprecated"
DEPRECATION_HEADER_VALUE = (
    "Use admin workspace (_platform_admin). Console will be removed in a future release."
)

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
# Dependencies Container
# =============================================================================


@dataclass
class _OpsDeps:
    ops_db: OpsDatabase
    health_aggregator: HealthAggregator | None
    sse_manager: SSEStreamManager | None
    simulator: OpsSimulator | None
    metrics_collector: SystemMetricsCollector | None
    session_manager: OpsSessionManager
    require_auth: bool


# =============================================================================
# Module-level handler functions
# =============================================================================

# -------------------------------------------------------------------------
# Authentication Dependency
# -------------------------------------------------------------------------


async def _get_current_ops_user(
    deps: _OpsDeps,
    ops_session: str | None = Cookie(None),
) -> str:
    """Validate ops session and return username."""
    if not deps.require_auth:
        return "anonymous"

    if not ops_session:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = deps.session_manager.validate_session(ops_session)
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


async def _check_setup_required(deps: _OpsDeps) -> dict[str, bool]:
    """Check if initial ops admin setup is required."""
    return {"setup_required": not deps.ops_db.has_credentials()}


async def _setup_ops_admin(
    deps: _OpsDeps,
    request: OpsSetupRequest,
    response: Response,
    http_request: Request,
) -> OpsLoginResponse:
    """
    Initial ops admin setup.

    Creates the first ops admin account. Only works if no
    credentials exist yet.
    """
    from dazzle_back.runtime.auth.crypto import cookie_secure

    if deps.ops_db.has_credentials():
        raise HTTPException(
            status_code=400,
            detail="Ops admin already configured",
        )

    if len(request.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters",
        )

    deps.ops_db.create_credentials(request.username, request.password)
    token = deps.session_manager.create_session(request.username)

    response.set_cookie(
        key="ops_session",
        value=token,
        httponly=True,
        secure=cookie_secure(http_request),
        samesite="lax",
        max_age=86400,  # 24 hours
    )

    return OpsLoginResponse(
        success=True,
        message="Ops admin created",
        token=token,
    )


async def _login(
    deps: _OpsDeps,
    request: OpsLoginRequest,
    response: Response,
    http_request: Request,
) -> OpsLoginResponse:
    """
    Ops admin login.

    Returns a session token for authenticated access.
    """
    from dazzle_back.runtime.auth.crypto import cookie_secure

    if not deps.ops_db.verify_credentials(request.username, request.password):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

    token = deps.session_manager.create_session(request.username)

    response.set_cookie(
        key="ops_session",
        value=token,
        httponly=True,
        secure=cookie_secure(http_request),
        samesite="lax",
        max_age=86400,
    )

    return OpsLoginResponse(
        success=True,
        message="Login successful",
        token=token,
    )


async def _logout(
    deps: _OpsDeps,
    response: Response,
    ops_session: str | None = Cookie(None),
) -> dict[str, str]:
    """Log out and clear session."""
    if ops_session:
        deps.session_manager.revoke_session(ops_session)

    response.delete_cookie("ops_session")
    return {"status": "logged_out"}


async def _get_current_user_info(
    deps: _OpsDeps,
    username: str,
) -> dict[str, str]:
    """Get current authenticated user info."""
    return {"username": username}


# -------------------------------------------------------------------------
# Health Endpoints
# -------------------------------------------------------------------------


async def _get_health(
    deps: _OpsDeps,
    username: str,
) -> HealthSummary:
    """
    Get current system health status.

    Returns aggregated health from all registered components.
    """
    if not deps.health_aggregator:
        return HealthSummary(
            status="unknown",
            checked_at=datetime.now(UTC).isoformat(),
            summary={"total": 0, "healthy": 0, "degraded": 0, "unhealthy": 0, "unknown": 0},
            components=[],
        )

    health = deps.health_aggregator.get_latest()
    return HealthSummary(**format_health_result(health))


async def _run_health_check(
    deps: _OpsDeps,
    username: str,
) -> HealthSummary:
    """
    Trigger an immediate health check.

    Runs all registered health checks and returns results.
    """
    if not deps.health_aggregator:
        raise HTTPException(status_code=503, detail="Health aggregator not configured")

    health = await deps.health_aggregator.check_all()
    return HealthSummary(**format_health_result(health))


async def _get_health_history(
    deps: _OpsDeps,
    component: str,
    hours: int = Query(default=24, le=168),
    username: str = "",
) -> list[dict[str, Any]]:
    """
    Get health check history for a component.

    Returns historical health checks for analysis and debugging.
    """
    records = deps.ops_db.get_health_history(component, hours)
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


async def _get_events(
    deps: _OpsDeps,
    entity_name: str | None = Query(None),
    entity_id: str | None = Query(None),
    event_type: str | None = Query(None),
    correlation_id: str | None = Query(None),
    tenant_id: str | None = Query(None),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    username: str = "",
) -> dict[str, Any]:
    """
    Query event log.

    Returns events matching the specified filters.
    Supports pagination via limit/offset.
    """
    events = deps.ops_db.get_events(
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


async def _get_event(
    deps: _OpsDeps,
    event_id: str,
    username: str = "",
) -> dict[str, Any]:
    """Get a single event by ID."""
    events = deps.ops_db.get_events(limit=1)
    # TODO: Add get_event_by_id method to ops_db
    for event in events:
        if event["id"] == event_id:
            return event

    raise HTTPException(status_code=404, detail="Event not found")


# -------------------------------------------------------------------------
# API Call Tracking Endpoints (Integration Observatory)
# -------------------------------------------------------------------------


async def _get_api_call_stats(
    deps: _OpsDeps,
    service_name: str | None = Query(None),
    hours: int = Query(default=24, le=168),
    tenant_id: str | None = Query(None),
    username: str = "",
) -> dict[str, Any]:
    """
    Get API call statistics.

    Returns aggregated stats for external API calls including
    latency, error rates, and costs.
    """
    stats = deps.ops_db.get_api_call_stats(
        service_name=service_name,
        hours=hours,
        tenant_id=tenant_id,
    )
    return {
        "period_hours": hours,
        "services": stats,
    }


async def _get_recent_api_calls(
    deps: _OpsDeps,
    service_name: str | None = Query(None),
    status: str | None = Query(None, description="success, error, or all"),
    limit: int = Query(default=50, le=200),
    username: str = "",
) -> dict[str, Any]:
    """
    Get recent API calls.

    Returns individual API call records for debugging.
    """
    calls = query_recent_api_calls(
        deps.ops_db, service_name=service_name, status=status, limit=limit
    )
    return {
        "calls": calls,
        "count": len(calls),
    }


async def _get_api_costs(
    deps: _OpsDeps,
    days: int = Query(default=30, le=90),
    group_by: str = Query(default="service", description="service or day"),
    username: str = "",
) -> dict[str, Any]:
    """
    Get API cost breakdown.

    Returns cost aggregation by service or by day.
    """
    return query_api_costs(deps.ops_db, days=days, group_by=group_by)


async def _get_api_errors(
    deps: _OpsDeps,
    hours: int = Query(default=24, le=168),
    service_name: str | None = Query(None),
    username: str = "",
) -> dict[str, Any]:
    """
    Get recent API errors.

    Returns failed API calls for debugging.
    """
    return query_api_errors(deps.ops_db, hours=hours, service_name=service_name)


# -------------------------------------------------------------------------
# Analytics Endpoints
# -------------------------------------------------------------------------


async def _get_analytics_summary(
    deps: _OpsDeps,
    tenant_id: str,
    event_type: str | None = Query(None),
    days: int = Query(default=7, le=90),
    username: str = "",
) -> dict[str, Any]:
    """
    Get analytics summary for a tenant.

    Returns aggregated analytics data including event counts,
    unique users, and sessions.
    """
    return deps.ops_db.get_analytics_summary(
        tenant_id=tenant_id,
        event_type=event_type,
        days=days,
    )


async def _get_page_view_stats(
    deps: _OpsDeps,
    tenant_id: str,
    days: int = Query(default=7, le=90),
    username: str = "",
) -> dict[str, Any]:
    """
    Get page view statistics for a tenant.

    Returns daily page views, top pages, and session metrics.
    """
    return query_page_view_stats(deps.ops_db, tenant_id=tenant_id, days=days)


async def _get_traffic_sources(
    deps: _OpsDeps,
    tenant_id: str,
    days: int = Query(default=7, le=90),
    username: str = "",
) -> dict[str, Any]:
    """
    Get traffic source breakdown for a tenant.

    Returns referrer breakdown and UTM parameter analysis.
    """
    return query_traffic_sources(deps.ops_db, tenant_id=tenant_id, days=days)


async def _list_analytics_tenants(
    deps: _OpsDeps,
    username: str = "",
) -> dict[str, Any]:
    """
    List all tenants with analytics data.

    Returns tenant IDs and event counts for tenant selection.
    """
    return query_analytics_tenants(deps.ops_db)


# -------------------------------------------------------------------------
# Configuration Endpoints
# -------------------------------------------------------------------------


async def _get_retention_config(
    deps: _OpsDeps,
    username: str = "",
) -> dict[str, int]:
    """Get current data retention configuration."""
    config = deps.ops_db.get_retention_config()
    return {
        "health_checks_days": config.health_checks_days,
        "api_calls_days": config.api_calls_days,
        "analytics_days": config.analytics_days,
        "events_days": config.events_days,
    }


async def _update_retention_config(
    deps: _OpsDeps,
    update: RetentionConfigUpdate,
    username: str = "",
) -> dict[str, Any]:
    """
    Update data retention configuration.

    Changes take effect on next retention enforcement run.
    """
    from dazzle_back.runtime.ops_database import RetentionConfig

    current = deps.ops_db.get_retention_config()

    new_config = RetentionConfig(
        health_checks_days=update.health_checks_days or current.health_checks_days,
        api_calls_days=update.api_calls_days or current.api_calls_days,
        analytics_days=update.analytics_days or current.analytics_days,
        events_days=update.events_days or current.events_days,
    )

    deps.ops_db.set_retention_config(new_config)

    return {
        "status": "updated",
        "config": {
            "health_checks_days": new_config.health_checks_days,
            "api_calls_days": new_config.api_calls_days,
            "analytics_days": new_config.analytics_days,
            "events_days": new_config.events_days,
        },
    }


async def _enforce_retention(
    deps: _OpsDeps,
    username: str = "",
) -> dict[str, Any]:
    """
    Manually trigger retention enforcement.

    Deletes data older than configured retention periods.
    Returns count of deleted records per table.
    """
    deleted = deps.ops_db.enforce_retention()
    return {
        "status": "enforced",
        "deleted": deleted,
    }


# -------------------------------------------------------------------------
# SSE Stats Endpoint
# -------------------------------------------------------------------------


async def _get_sse_stats(
    deps: _OpsDeps,
    username: str = "",
) -> dict[str, Any]:
    """Get SSE stream statistics."""
    if not deps.sse_manager:
        return {"available": False}

    stats = deps.sse_manager.get_stats()
    stats["available"] = True
    return stats


# -------------------------------------------------------------------------
# Email Dashboard Endpoints
# -------------------------------------------------------------------------


async def _get_email_stats(
    deps: _OpsDeps,
    days: int = Query(default=7, le=90),
    username: str = "",
) -> dict[str, Any]:
    """
    Get email statistics.

    Returns counts of sent, opened, and clicked emails.
    """
    return query_email_stats(deps.ops_db, days=days)


async def _get_recent_emails(
    deps: _OpsDeps,
    limit: int = Query(default=50, le=200),
    username: str = "",
) -> dict[str, Any]:
    """
    Get recent email events.

    Returns individual email tracking events for debugging.
    """
    emails = query_recent_emails(deps.ops_db, limit=limit)
    return {
        "emails": emails,
        "count": len(emails),
    }


async def _get_top_email_links(
    deps: _OpsDeps,
    days: int = Query(default=30, le=90),
    limit: int = Query(default=10, le=50),
    username: str = "",
) -> dict[str, Any]:
    """
    Get top clicked links in emails.

    Returns the most frequently clicked URLs for link optimization.
    """
    links = query_top_email_links(deps.ops_db, days=days, limit=limit)
    return {
        "period_days": days,
        "links": links,
    }


# -------------------------------------------------------------------------
# Simulation Endpoints
# -------------------------------------------------------------------------


async def _get_simulation_status(
    deps: _OpsDeps,
    username: str = "",
) -> dict[str, Any]:
    """
    Get simulation status.

    Returns whether simulation is running and statistics.
    """
    if not deps.simulator:
        return {
            "available": False,
            "running": False,
            "message": "Simulator not configured",
        }

    stats = deps.simulator.stats
    return {
        "available": True,
        "running": deps.simulator.running,
        "stats": {
            "started_at": stats.started_at.isoformat() if stats.started_at else None,
            "events_generated": stats.events_generated,
            "health_checks": stats.health_checks,
            "api_calls": stats.api_calls,
            "emails": stats.emails,
        }
        if deps.simulator.running
        else None,
    }


async def _start_simulation(
    deps: _OpsDeps,
    username: str = "",
) -> dict[str, Any]:
    """
    Start the simulation.

    Generates synthetic events for dashboard demonstration.
    """
    if not deps.simulator:
        raise HTTPException(
            status_code=503,
            detail="Simulator not configured",
        )

    if deps.simulator.running:
        return {
            "success": True,
            "message": "Simulation already running",
        }

    await deps.simulator.start()
    return {
        "success": True,
        "message": "Simulation started",
    }


async def _stop_simulation(
    deps: _OpsDeps,
    username: str = "",
) -> dict[str, Any]:
    """
    Stop the simulation.

    Stops generating synthetic events.
    """
    if not deps.simulator:
        raise HTTPException(
            status_code=503,
            detail="Simulator not configured",
        )

    if not deps.simulator.running:
        return {
            "success": True,
            "message": "Simulation not running",
        }

    await deps.simulator.stop()
    return {
        "success": True,
        "message": "Simulation stopped",
        "stats": {
            "events_generated": deps.simulator.stats.events_generated,
        },
    }


# -------------------------------------------------------------------------
# System Metrics Endpoints
# -------------------------------------------------------------------------


async def _get_prometheus_metrics(deps: _OpsDeps) -> Response:
    """
    Prometheus metrics endpoint.

    Returns system metrics in Prometheus text format for scraping.
    No authentication required to allow Prometheus scraping.
    """
    if not deps.metrics_collector:
        return Response(
            content="# No metrics collector configured\n",
            media_type="text/plain; version=0.0.4",
        )

    snapshot = deps.metrics_collector.snapshot()
    return Response(
        content=snapshot.to_prometheus(),
        media_type="text/plain; version=0.0.4",
    )


async def _get_system_metrics(
    deps: _OpsDeps,
    username: str = "",
) -> dict[str, Any]:
    """
    Get system metrics as JSON.

    Returns comprehensive metrics from all system components
    for dashboard visualization.
    """
    if not deps.metrics_collector:
        return {
            "available": False,
            "message": "Metrics collector not configured",
        }

    snapshot = deps.metrics_collector.snapshot()
    data = snapshot.to_dict()
    data["available"] = True
    return data


async def _get_component_metrics(
    deps: _OpsDeps,
    component: str,
    username: str = "",
) -> dict[str, Any]:
    """
    Get metrics for a specific component.

    Returns detailed metrics for a single system component.
    """
    if not deps.metrics_collector:
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

    snapshot = deps.metrics_collector.snapshot()
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
            name: _compute_histogram_stats(samples) for name, samples in metrics.histograms.items()
        },
        "recent_errors": metrics.errors[-10:],
    }


async def _reset_system_metrics(
    deps: _OpsDeps,
    username: str = "",
) -> dict[str, str]:
    """
    Reset all system metrics.

    Clears accumulated metrics data. Use with caution.
    """
    if not deps.metrics_collector:
        raise HTTPException(
            status_code=503,
            detail="Metrics collector not configured",
        )

    deps.metrics_collector.reset()
    return {"status": "reset", "message": "All metrics have been reset"}


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
    deps = _OpsDeps(
        ops_db=ops_db,
        health_aggregator=health_aggregator,
        sse_manager=sse_manager,
        simulator=simulator,
        metrics_collector=metrics_collector,
        session_manager=OpsSessionManager(),
        require_auth=require_auth,
    )

    # Build the auth dependency bound to this deps instance
    auth_dep = partial(_get_current_ops_user, deps)

    # -------------------------------------------------------------------------
    # Setup & Authentication Endpoints
    # -------------------------------------------------------------------------

    router.add_api_route(
        "/setup-required",
        partial(_check_setup_required, deps),
        methods=["GET"],
    )
    router.add_api_route(
        "/setup",
        partial(_setup_ops_admin, deps),
        methods=["POST"],
        response_model=OpsLoginResponse,
    )
    router.add_api_route(
        "/login",
        partial(_login, deps),
        methods=["POST"],
        response_model=OpsLoginResponse,
    )
    router.add_api_route(
        "/logout",
        partial(_logout, deps),
        methods=["POST"],
    )

    async def _me_endpoint(username: str = Depends(auth_dep)) -> dict[str, str]:
        return await _get_current_user_info(deps, username)

    router.add_api_route("/me", _me_endpoint, methods=["GET"])

    # -------------------------------------------------------------------------
    # Health Endpoints
    # -------------------------------------------------------------------------

    async def _health_endpoint(username: str = Depends(auth_dep)) -> HealthSummary:
        return await _get_health(deps, username)

    async def _health_check_endpoint(username: str = Depends(auth_dep)) -> HealthSummary:
        return await _run_health_check(deps, username)

    async def _health_history_endpoint(
        component: str,
        hours: int = Query(default=24, le=168),
        username: str = Depends(auth_dep),
    ) -> list[dict[str, Any]]:
        return await _get_health_history(deps, component, hours, username)

    router.add_api_route("/health", _health_endpoint, methods=["GET"], response_model=HealthSummary)
    router.add_api_route(
        "/health/check", _health_check_endpoint, methods=["POST"], response_model=HealthSummary
    )
    router.add_api_route("/health/history/{component}", _health_history_endpoint, methods=["GET"])

    # -------------------------------------------------------------------------
    # Event Explorer Endpoints
    # -------------------------------------------------------------------------

    async def _events_endpoint(
        entity_name: str | None = Query(None),
        entity_id: str | None = Query(None),
        event_type: str | None = Query(None),
        correlation_id: str | None = Query(None),
        tenant_id: str | None = Query(None),
        limit: int = Query(default=100, le=1000),
        offset: int = Query(default=0, ge=0),
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _get_events(
            deps,
            entity_name=entity_name,
            entity_id=entity_id,
            event_type=event_type,
            correlation_id=correlation_id,
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
            username=username,
        )

    async def _event_endpoint(
        event_id: str,
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _get_event(deps, event_id, username)

    router.add_api_route("/events", _events_endpoint, methods=["GET"])
    router.add_api_route("/events/{event_id}", _event_endpoint, methods=["GET"])

    # -------------------------------------------------------------------------
    # API Call Tracking Endpoints (Integration Observatory)
    # -------------------------------------------------------------------------

    async def _api_call_stats_endpoint(
        service_name: str | None = Query(None),
        hours: int = Query(default=24, le=168),
        tenant_id: str | None = Query(None),
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _get_api_call_stats(deps, service_name, hours, tenant_id, username)

    async def _recent_api_calls_endpoint(
        service_name: str | None = Query(None),
        status: str | None = Query(None, description="success, error, or all"),
        limit: int = Query(default=50, le=200),
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _get_recent_api_calls(deps, service_name, status, limit, username)

    async def _api_costs_endpoint(
        days: int = Query(default=30, le=90),
        group_by: str = Query(default="service", description="service or day"),
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _get_api_costs(deps, days, group_by, username)

    async def _api_errors_endpoint(
        hours: int = Query(default=24, le=168),
        service_name: str | None = Query(None),
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _get_api_errors(deps, hours, service_name, username)

    router.add_api_route("/api-calls/stats", _api_call_stats_endpoint, methods=["GET"])
    router.add_api_route("/api-calls/recent", _recent_api_calls_endpoint, methods=["GET"])
    router.add_api_route("/api-calls/costs", _api_costs_endpoint, methods=["GET"])
    router.add_api_route("/api-calls/errors", _api_errors_endpoint, methods=["GET"])

    # -------------------------------------------------------------------------
    # Analytics Endpoints
    # -------------------------------------------------------------------------

    async def _analytics_summary_endpoint(
        tenant_id: str,
        event_type: str | None = Query(None),
        days: int = Query(default=7, le=90),
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _get_analytics_summary(deps, tenant_id, event_type, days, username)

    async def _page_view_stats_endpoint(
        tenant_id: str,
        days: int = Query(default=7, le=90),
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _get_page_view_stats(deps, tenant_id, days, username)

    async def _traffic_sources_endpoint(
        tenant_id: str,
        days: int = Query(default=7, le=90),
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _get_traffic_sources(deps, tenant_id, days, username)

    async def _analytics_tenants_endpoint(
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _list_analytics_tenants(deps, username)

    router.add_api_route("/analytics/{tenant_id}", _analytics_summary_endpoint, methods=["GET"])
    router.add_api_route(
        "/analytics/{tenant_id}/page-views", _page_view_stats_endpoint, methods=["GET"]
    )
    router.add_api_route(
        "/analytics/{tenant_id}/traffic-sources", _traffic_sources_endpoint, methods=["GET"]
    )
    router.add_api_route("/analytics/tenants", _analytics_tenants_endpoint, methods=["GET"])

    # -------------------------------------------------------------------------
    # Configuration Endpoints
    # -------------------------------------------------------------------------

    async def _retention_config_endpoint(
        username: str = Depends(auth_dep),
    ) -> dict[str, int]:
        return await _get_retention_config(deps, username)

    async def _update_retention_config_endpoint(
        update: RetentionConfigUpdate,
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _update_retention_config(deps, update, username)

    async def _enforce_retention_endpoint(
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _enforce_retention(deps, username)

    router.add_api_route("/config/retention", _retention_config_endpoint, methods=["GET"])
    router.add_api_route("/config/retention", _update_retention_config_endpoint, methods=["PUT"])
    router.add_api_route("/config/retention/enforce", _enforce_retention_endpoint, methods=["POST"])

    # -------------------------------------------------------------------------
    # SSE Stats Endpoint
    # -------------------------------------------------------------------------

    async def _sse_stats_endpoint(
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _get_sse_stats(deps, username)

    router.add_api_route("/sse/stats", _sse_stats_endpoint, methods=["GET"])

    # -------------------------------------------------------------------------
    # Email Dashboard Endpoints
    # -------------------------------------------------------------------------

    async def _email_stats_endpoint(
        days: int = Query(default=7, le=90),
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _get_email_stats(deps, days, username)

    async def _recent_emails_endpoint(
        limit: int = Query(default=50, le=200),
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _get_recent_emails(deps, limit, username)

    async def _top_email_links_endpoint(
        days: int = Query(default=30, le=90),
        limit: int = Query(default=10, le=50),
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _get_top_email_links(deps, days, limit, username)

    router.add_api_route("/email/stats", _email_stats_endpoint, methods=["GET"])
    router.add_api_route("/email/recent", _recent_emails_endpoint, methods=["GET"])
    router.add_api_route("/email/top-links", _top_email_links_endpoint, methods=["GET"])

    # -------------------------------------------------------------------------
    # Simulation Endpoints
    # -------------------------------------------------------------------------

    async def _simulation_status_endpoint(
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _get_simulation_status(deps, username)

    async def _start_simulation_endpoint(
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _start_simulation(deps, username)

    async def _stop_simulation_endpoint(
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _stop_simulation(deps, username)

    router.add_api_route("/simulation/status", _simulation_status_endpoint, methods=["GET"])
    router.add_api_route("/simulation/start", _start_simulation_endpoint, methods=["POST"])
    router.add_api_route("/simulation/stop", _stop_simulation_endpoint, methods=["POST"])

    # -------------------------------------------------------------------------
    # System Metrics Endpoints
    # -------------------------------------------------------------------------

    router.add_api_route(
        "/metrics",
        partial(_get_prometheus_metrics, deps),
        methods=["GET"],
        include_in_schema=False,
    )

    async def _system_metrics_endpoint(
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _get_system_metrics(deps, username)

    async def _component_metrics_endpoint(
        component: str,
        username: str = Depends(auth_dep),
    ) -> dict[str, Any]:
        return await _get_component_metrics(deps, component, username)

    async def _reset_system_metrics_endpoint(
        username: str = Depends(auth_dep),
    ) -> dict[str, str]:
        return await _reset_system_metrics(deps, username)

    router.add_api_route("/system-metrics", _system_metrics_endpoint, methods=["GET"])
    router.add_api_route(
        "/system-metrics/component/{component}", _component_metrics_endpoint, methods=["GET"]
    )
    router.add_api_route("/system-metrics/reset", _reset_system_metrics_endpoint, methods=["POST"])

    return router
