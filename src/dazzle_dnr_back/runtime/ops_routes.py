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

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

try:
    from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore
    HTTPException = None  # type: ignore

if TYPE_CHECKING:
    from dazzle_dnr_back.runtime.health_aggregator import HealthAggregator
    from dazzle_dnr_back.runtime.ops_database import OpsDatabase
    from dazzle_dnr_back.runtime.ops_simulator import OpsSimulator
    from dazzle_dnr_back.runtime.sse_stream import SSEStreamManager


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
# Session Management
# =============================================================================


class OpsSessionManager:
    """
    Simple session manager for ops authentication.

    Uses secure tokens stored in memory with expiration.
    In production, consider Redis or database-backed sessions.
    """

    def __init__(self, session_duration_hours: int = 24):
        self._sessions: dict[str, tuple[str, datetime]] = {}  # token -> (username, expires)
        self.session_duration = timedelta(hours=session_duration_hours)

    def create_session(self, username: str) -> str:
        """Create a new session and return token."""
        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + self.session_duration
        self._sessions[token] = (username, expires)
        return token

    def validate_session(self, token: str) -> str | None:
        """Validate session token and return username if valid."""
        if token not in self._sessions:
            return None

        username, expires = self._sessions[token]
        if datetime.utcnow() > expires:
            del self._sessions[token]
            return None

        return username

    def revoke_session(self, token: str) -> None:
        """Revoke a session."""
        self._sessions.pop(token, None)

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count of removed sessions."""
        now = datetime.utcnow()
        expired = [t for t, (_, exp) in self._sessions.items() if now > exp]
        for token in expired:
            del self._sessions[token]
        return len(expired)


# =============================================================================
# Route Factory
# =============================================================================


def create_ops_routes(
    ops_db: OpsDatabase,
    health_aggregator: HealthAggregator | None = None,
    sse_manager: SSEStreamManager | None = None,
    simulator: OpsSimulator | None = None,
    require_auth: bool = True,
) -> APIRouter:
    """
    Create Operations Platform routes.

    Args:
        ops_db: Operations database
        health_aggregator: Health check aggregator (optional)
        sse_manager: SSE stream manager (optional)
        simulator: Ops simulator for demo mode (optional)
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

    async def get_current_user(
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
        username: str = Depends(get_current_user),
    ) -> dict[str, str]:
        """Get current authenticated user info."""
        return {"username": username}

    # -------------------------------------------------------------------------
    # Health Endpoints
    # -------------------------------------------------------------------------

    @router.get("/health", response_model=HealthSummary)
    async def get_health(
        username: str = Depends(get_current_user),
    ) -> HealthSummary:
        """
        Get current system health status.

        Returns aggregated health from all registered components.
        """
        if not health_aggregator:
            return HealthSummary(
                status="unknown",
                checked_at=datetime.utcnow().isoformat(),
                summary={"total": 0, "healthy": 0, "degraded": 0, "unhealthy": 0, "unknown": 0},
                components=[],
            )

        health = health_aggregator.get_latest()
        return HealthSummary(
            status=health.status.value,
            checked_at=health.checked_at.isoformat(),
            summary={
                "total": health.total_components,
                "healthy": health.healthy_count,
                "degraded": health.degraded_count,
                "unhealthy": health.unhealthy_count,
                "unknown": health.unknown_count,
            },
            components=[
                {
                    "name": c.name,
                    "type": c.component_type.value,
                    "status": c.status.value,
                    "latency_ms": c.latency_ms,
                    "message": c.message,
                    "last_checked": c.last_checked.isoformat() if c.last_checked else None,
                }
                for c in health.components
            ],
        )

    @router.post("/health/check")
    async def run_health_check(
        username: str = Depends(get_current_user),
    ) -> HealthSummary:
        """
        Trigger an immediate health check.

        Runs all registered health checks and returns results.
        """
        if not health_aggregator:
            raise HTTPException(status_code=503, detail="Health aggregator not configured")

        health = await health_aggregator.check_all()
        return HealthSummary(
            status=health.status.value,
            checked_at=health.checked_at.isoformat(),
            summary={
                "total": health.total_components,
                "healthy": health.healthy_count,
                "degraded": health.degraded_count,
                "unhealthy": health.unhealthy_count,
                "unknown": health.unknown_count,
            },
            components=[
                {
                    "name": c.name,
                    "type": c.component_type.value,
                    "status": c.status.value,
                    "latency_ms": c.latency_ms,
                    "message": c.message,
                    "last_checked": c.last_checked.isoformat() if c.last_checked else None,
                }
                for c in health.components
            ],
        )

    @router.get("/health/history/{component}")
    async def get_health_history(
        component: str,
        hours: int = Query(default=24, le=168),
        username: str = Depends(get_current_user),
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
        username: str = Depends(get_current_user),
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
        username: str = Depends(get_current_user),
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
        username: str = Depends(get_current_user),
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
        username: str = Depends(get_current_user),
    ) -> dict[str, Any]:
        """
        Get recent API calls.

        Returns individual API call records for debugging.
        """
        # Build query - we need to add this method to ops_db
        # For now, use a simple query via the connection
        with ops_db.connection() as conn:
            query = "SELECT * FROM api_calls"
            params: list[Any] = []
            conditions = []

            if service_name:
                conditions.append("service_name = ?")
                params.append(service_name)

            if status == "success":
                conditions.append("(status_code IS NULL OR status_code < 400)")
            elif status == "error":
                conditions.append("(status_code >= 400 OR error_message IS NOT NULL)")

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY called_at DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            calls = []
            for row in cursor.fetchall():
                calls.append(
                    {
                        "id": row["id"],
                        "service_name": row["service_name"],
                        "endpoint": row["endpoint"],
                        "method": row["method"],
                        "status_code": row["status_code"],
                        "latency_ms": row["latency_ms"],
                        "error_message": row["error_message"],
                        "cost_cents": row["cost_cents"],
                        "called_at": row["called_at"],
                        "tenant_id": row["tenant_id"],
                    }
                )

        return {
            "calls": calls,
            "count": len(calls),
        }

    @router.get("/api-calls/costs")
    async def get_api_costs(
        days: int = Query(default=30, le=90),
        group_by: str = Query(default="service", description="service or day"),
        username: str = Depends(get_current_user),
    ) -> dict[str, Any]:
        """
        Get API cost breakdown.

        Returns cost aggregation by service or by day.
        """
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        with ops_db.connection() as conn:
            if group_by == "day":
                cursor = conn.execute(
                    """
                    SELECT
                        DATE(called_at) as date,
                        service_name,
                        SUM(COALESCE(cost_cents, 0)) as total_cost_cents,
                        COUNT(*) as call_count
                    FROM api_calls
                    WHERE called_at >= ?
                    GROUP BY DATE(called_at), service_name
                    ORDER BY date DESC, total_cost_cents DESC
                    """,
                    (cutoff,),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT
                        service_name,
                        SUM(COALESCE(cost_cents, 0)) as total_cost_cents,
                        COUNT(*) as call_count,
                        AVG(latency_ms) as avg_latency_ms
                    FROM api_calls
                    WHERE called_at >= ?
                    GROUP BY service_name
                    ORDER BY total_cost_cents DESC
                    """,
                    (cutoff,),
                )

            results = [dict(row) for row in cursor.fetchall()]

        total_cost = sum(r.get("total_cost_cents", 0) or 0 for r in results)

        return {
            "period_days": days,
            "group_by": group_by,
            "total_cost_cents": total_cost,
            "total_cost_gbp": round(total_cost / 100, 2),
            "breakdown": results,
        }

    @router.get("/api-calls/errors")
    async def get_api_errors(
        hours: int = Query(default=24, le=168),
        service_name: str | None = Query(None),
        username: str = Depends(get_current_user),
    ) -> dict[str, Any]:
        """
        Get recent API errors.

        Returns failed API calls for debugging.
        """
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        with ops_db.connection() as conn:
            query = """
                SELECT * FROM api_calls
                WHERE called_at >= ?
                AND (status_code >= 400 OR error_message IS NOT NULL)
            """
            params: list[Any] = [cutoff]

            if service_name:
                query += " AND service_name = ?"
                params.append(service_name)

            query += " ORDER BY called_at DESC LIMIT 100"

            cursor = conn.execute(query, params)
            errors = [dict(row) for row in cursor.fetchall()]

        # Group by error type
        error_summary: dict[str, int] = {}
        for error in errors:
            key = f"{error['service_name']}:{error.get('status_code') or 'connection_error'}"
            error_summary[key] = error_summary.get(key, 0) + 1

        return {
            "period_hours": hours,
            "total_errors": len(errors),
            "error_summary": error_summary,
            "recent_errors": errors[:20],  # Last 20 for display
        }

    # -------------------------------------------------------------------------
    # Analytics Endpoints
    # -------------------------------------------------------------------------

    @router.get("/analytics/{tenant_id}")
    async def get_analytics_summary(
        tenant_id: str,
        event_type: str | None = Query(None),
        days: int = Query(default=7, le=90),
        username: str = Depends(get_current_user),
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
        username: str = Depends(get_current_user),
    ) -> dict[str, Any]:
        """
        Get page view statistics for a tenant.

        Returns daily page views, top pages, and session metrics.
        """
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        with ops_db.connection() as conn:
            # Daily page views
            daily_cursor = conn.execute(
                """
                SELECT
                    DATE(recorded_at) as date,
                    COUNT(*) as views,
                    COUNT(DISTINCT session_id) as sessions
                FROM analytics_events
                WHERE tenant_id = ? AND event_type = 'page_view'
                AND recorded_at >= ?
                GROUP BY DATE(recorded_at)
                ORDER BY date DESC
                """,
                (tenant_id, cutoff),
            )
            daily_views = [dict(row) for row in daily_cursor.fetchall()]

            # Top pages
            pages_cursor = conn.execute(
                """
                SELECT
                    event_name as page,
                    COUNT(*) as views
                FROM analytics_events
                WHERE tenant_id = ? AND event_type = 'page_view'
                AND recorded_at >= ?
                GROUP BY event_name
                ORDER BY views DESC
                LIMIT 10
                """,
                (tenant_id, cutoff),
            )
            top_pages = [dict(row) for row in pages_cursor.fetchall()]

            # Session stats
            session_cursor = conn.execute(
                """
                SELECT
                    COUNT(DISTINCT session_id) as total_sessions,
                    COUNT(*) as total_views,
                    CAST(COUNT(*) AS FLOAT) / MAX(1, COUNT(DISTINCT session_id)) as avg_views_per_session
                FROM analytics_events
                WHERE tenant_id = ? AND event_type = 'page_view'
                AND recorded_at >= ?
                """,
                (tenant_id, cutoff),
            )
            session_stats = dict(session_cursor.fetchone())

        return {
            "period_days": days,
            "tenant_id": tenant_id,
            "daily_views": daily_views,
            "top_pages": top_pages,
            "session_stats": session_stats,
        }

    @router.get("/analytics/{tenant_id}/traffic-sources")
    async def get_traffic_sources(
        tenant_id: str,
        days: int = Query(default=7, le=90),
        username: str = Depends(get_current_user),
    ) -> dict[str, Any]:
        """
        Get traffic source breakdown for a tenant.

        Returns referrer breakdown and UTM parameter analysis.
        """
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        with ops_db.connection() as conn:
            # Referrer breakdown
            ref_cursor = conn.execute(
                """
                SELECT
                    COALESCE(
                        CASE
                            WHEN properties LIKE '%"referrer"%' THEN
                                CASE
                                    WHEN properties LIKE '%google.%' THEN 'Google'
                                    WHEN properties LIKE '%bing.%' THEN 'Bing'
                                    WHEN properties LIKE '%twitter.%' OR properties LIKE '%t.co%' THEN 'Twitter'
                                    WHEN properties LIKE '%facebook.%' OR properties LIKE '%fb.%' THEN 'Facebook'
                                    WHEN properties LIKE '%linkedin.%' THEN 'LinkedIn'
                                    WHEN properties = '' OR properties IS NULL THEN 'Direct'
                                    ELSE 'Other'
                                END
                            ELSE 'Direct'
                        END,
                        'Direct'
                    ) as source,
                    COUNT(*) as views
                FROM analytics_events
                WHERE tenant_id = ? AND event_type = 'page_view'
                AND recorded_at >= ?
                GROUP BY source
                ORDER BY views DESC
                """,
                (tenant_id, cutoff),
            )
            sources = [dict(row) for row in ref_cursor.fetchall()]

            # UTM campaigns
            utm_cursor = conn.execute(
                """
                SELECT
                    properties,
                    COUNT(*) as count
                FROM analytics_events
                WHERE tenant_id = ? AND event_type = 'page_view'
                AND recorded_at >= ?
                AND properties LIKE '%utm_%'
                GROUP BY properties
                ORDER BY count DESC
                LIMIT 10
                """,
                (tenant_id, cutoff),
            )
            utm_raw = [dict(row) for row in utm_cursor.fetchall()]

        return {
            "period_days": days,
            "tenant_id": tenant_id,
            "sources": sources,
            "utm_campaigns": utm_raw,
        }

    @router.get("/analytics/tenants")
    async def list_analytics_tenants(
        username: str = Depends(get_current_user),
    ) -> dict[str, Any]:
        """
        List all tenants with analytics data.

        Returns tenant IDs and event counts for tenant selection.
        """
        with ops_db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    tenant_id,
                    COUNT(*) as event_count,
                    MIN(recorded_at) as first_event,
                    MAX(recorded_at) as last_event
                FROM analytics_events
                GROUP BY tenant_id
                ORDER BY event_count DESC
                """
            )
            tenants = [dict(row) for row in cursor.fetchall()]

        return {
            "tenants": tenants,
            "count": len(tenants),
        }

    # -------------------------------------------------------------------------
    # Configuration Endpoints
    # -------------------------------------------------------------------------

    @router.get("/config/retention")
    async def get_retention_config(
        username: str = Depends(get_current_user),
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
        username: str = Depends(get_current_user),
    ) -> dict[str, Any]:
        """
        Update data retention configuration.

        Changes take effect on next retention enforcement run.
        """
        from dazzle_dnr_back.runtime.ops_database import RetentionConfig

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
        username: str = Depends(get_current_user),
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
        username: str = Depends(get_current_user),
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
        username: str = Depends(get_current_user),
    ) -> dict[str, Any]:
        """
        Get email statistics.

        Returns counts of sent, opened, and clicked emails.
        """
        from datetime import timedelta

        since = datetime.utcnow() - timedelta(days=days)
        since_str = since.isoformat()

        with ops_db.connection() as conn:
            # Get event counts by type
            cursor = conn.execute(
                """
                SELECT
                    event_type,
                    COUNT(*) as count
                FROM events
                WHERE entity_name = 'email'
                  AND recorded_at >= ?
                GROUP BY event_type
                """,
                (since_str,),
            )

            stats: dict[str, int] = {}
            for row in cursor.fetchall():
                event_type = row["event_type"]
                # Convert email.sent -> sent
                short_type = event_type.replace("email.", "")
                stats[short_type] = row["count"]

            # Get daily breakdown
            cursor = conn.execute(
                """
                SELECT
                    DATE(recorded_at) as date,
                    event_type,
                    COUNT(*) as count
                FROM events
                WHERE entity_name = 'email'
                  AND recorded_at >= ?
                GROUP BY DATE(recorded_at), event_type
                ORDER BY date DESC
                """,
                (since_str,),
            )

            daily: dict[str, dict[str, int]] = {}
            for row in cursor.fetchall():
                date = row["date"]
                event_type = row["event_type"].replace("email.", "")
                if date not in daily:
                    daily[date] = {"sent": 0, "opened": 0, "clicked": 0}
                daily[date][event_type] = row["count"]

            # Calculate rates
            sent = stats.get("sent", 0)
            opened = stats.get("opened", 0)
            clicked = stats.get("clicked", 0)

            open_rate = (opened / sent * 100) if sent > 0 else 0
            click_rate = (clicked / sent * 100) if sent > 0 else 0

        return {
            "period_days": days,
            "totals": {
                "sent": sent,
                "opened": opened,
                "clicked": clicked,
            },
            "rates": {
                "open_rate": round(open_rate, 1),
                "click_rate": round(click_rate, 1),
            },
            "daily": [
                {"date": date, **counts} for date, counts in sorted(daily.items(), reverse=True)
            ],
        }

    @router.get("/email/recent")
    async def get_recent_emails(
        limit: int = Query(default=50, le=200),
        username: str = Depends(get_current_user),
    ) -> dict[str, Any]:
        """
        Get recent email events.

        Returns individual email tracking events for debugging.
        """
        with ops_db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    id,
                    entity_id as email_id,
                    event_type,
                    payload,
                    recorded_at
                FROM events
                WHERE entity_name = 'email'
                ORDER BY recorded_at DESC
                LIMIT ?
                """,
                (limit,),
            )

            emails: list[dict[str, Any]] = []
            for row in cursor.fetchall():
                import json

                payload = json.loads(row["payload"]) if row["payload"] else {}
                emails.append(
                    {
                        "id": row["id"],
                        "email_id": row["email_id"],
                        "event_type": row["event_type"].replace("email.", ""),
                        "click_url": payload.get("click_url"),
                        "user_agent": payload.get("user_agent"),
                        "recorded_at": row["recorded_at"],
                    }
                )

        return {
            "emails": emails,
            "count": len(emails),
        }

    @router.get("/email/top-links")
    async def get_top_email_links(
        days: int = Query(default=30, le=90),
        limit: int = Query(default=10, le=50),
        username: str = Depends(get_current_user),
    ) -> dict[str, Any]:
        """
        Get top clicked links in emails.

        Returns the most frequently clicked URLs for link optimization.
        """
        from datetime import timedelta

        since = datetime.utcnow() - timedelta(days=days)
        since_str = since.isoformat()

        with ops_db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    json_extract(payload, '$.click_url') as url,
                    COUNT(*) as clicks
                FROM events
                WHERE entity_name = 'email'
                  AND event_type = 'email.clicked'
                  AND recorded_at >= ?
                  AND json_extract(payload, '$.click_url') IS NOT NULL
                GROUP BY json_extract(payload, '$.click_url')
                ORDER BY clicks DESC
                LIMIT ?
                """,
                (since_str, limit),
            )

            links = [{"url": row["url"], "clicks": row["clicks"]} for row in cursor.fetchall()]

        return {
            "period_days": days,
            "links": links,
        }

    # -------------------------------------------------------------------------
    # Simulation Endpoints
    # -------------------------------------------------------------------------

    @router.get("/simulation/status")
    async def get_simulation_status(
        username: str = Depends(get_current_user),
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
        username: str = Depends(get_current_user),
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
        username: str = Depends(get_current_user),
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

    return router
