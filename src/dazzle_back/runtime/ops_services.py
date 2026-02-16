"""
Operations Platform Services.

Business logic extracted from ops_routes.py.
Contains session management, query builders, and data formatting
functions used by the ops route handlers.
"""

import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from dazzle_back.runtime.ops_database import OpsDatabase

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
        expires = datetime.now(UTC) + self.session_duration
        self._sessions[token] = (username, expires)
        return token

    def validate_session(self, token: str) -> str | None:
        """Validate session token and return username if valid."""
        if token not in self._sessions:
            return None

        username, expires = self._sessions[token]
        if datetime.now(UTC) > expires:
            del self._sessions[token]
            return None

        return username

    def revoke_session(self, token: str) -> None:
        """Revoke a session."""
        self._sessions.pop(token, None)

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count of removed sessions."""
        now = datetime.now(UTC)
        expired = [t for t, (_, exp) in self._sessions.items() if now > exp]
        for token in expired:
            del self._sessions[token]
        return len(expired)


# =============================================================================
# Health Formatting
# =============================================================================


def format_health_result(health: Any) -> dict[str, Any]:
    """Format a HealthResult into the HealthSummary dict shape."""
    return {
        "status": health.status.value,
        "checked_at": health.checked_at.isoformat(),
        "summary": {
            "total": health.total_components,
            "healthy": health.healthy_count,
            "degraded": health.degraded_count,
            "unhealthy": health.unhealthy_count,
            "unknown": health.unknown_count,
        },
        "components": [
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
    }


# =============================================================================
# API Call Queries
# =============================================================================


def query_recent_api_calls(
    ops_db: OpsDatabase,
    service_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Query recent API calls with optional filters."""
    with ops_db.connection() as conn:
        query = "SELECT * FROM api_calls"
        params: list[Any] = []
        conditions = []

        if service_name:
            conditions.append("service_name = %s")
            params.append(service_name)

        if status == "success":
            conditions.append("(status_code IS NULL OR status_code < 400)")
        elif status == "error":
            conditions.append("(status_code >= 400 OR error_message IS NOT NULL)")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY called_at DESC LIMIT %s"
        params.append(limit)

        cursor = conn.execute(query, params)
        return [
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
            for row in cursor.fetchall()
        ]


def query_api_costs(
    ops_db: OpsDatabase,
    days: int = 30,
    group_by: str = "service",
) -> dict[str, Any]:
    """Query API cost breakdown by service or day."""
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

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
                WHERE called_at >= %s
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
                WHERE called_at >= %s
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


def query_api_errors(
    ops_db: OpsDatabase,
    hours: int = 24,
    service_name: str | None = None,
) -> dict[str, Any]:
    """Query recent API errors with summary."""
    cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

    with ops_db.connection() as conn:
        query = """
            SELECT * FROM api_calls
            WHERE called_at >= %s
            AND (status_code >= 400 OR error_message IS NOT NULL)
        """
        params: list[Any] = [cutoff]

        if service_name:
            query += " AND service_name = %s"
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
        "recent_errors": errors[:20],
    }


# =============================================================================
# Analytics Queries
# =============================================================================


def query_page_view_stats(
    ops_db: OpsDatabase,
    tenant_id: str,
    days: int = 7,
) -> dict[str, Any]:
    """Query page view statistics for a tenant."""
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    with ops_db.connection() as conn:
        # Daily page views
        daily_cursor = conn.execute(
            """
            SELECT
                DATE(recorded_at) as date,
                COUNT(*) as views,
                COUNT(DISTINCT session_id) as sessions
            FROM analytics_events
            WHERE tenant_id = %s AND event_type = 'page_view'
            AND recorded_at >= %s
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
            WHERE tenant_id = %s AND event_type = 'page_view'
            AND recorded_at >= %s
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
            WHERE tenant_id = %s AND event_type = 'page_view'
            AND recorded_at >= %s
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


def query_traffic_sources(
    ops_db: OpsDatabase,
    tenant_id: str,
    days: int = 7,
) -> dict[str, Any]:
    """Query traffic source breakdown for a tenant."""
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

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
            WHERE tenant_id = %s AND event_type = 'page_view'
            AND recorded_at >= %s
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
            WHERE tenant_id = %s AND event_type = 'page_view'
            AND recorded_at >= %s
            AND properties LIKE '%%utm_%%'
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


def query_analytics_tenants(ops_db: OpsDatabase) -> dict[str, Any]:
    """List all tenants with analytics data."""
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


# =============================================================================
# Email Queries
# =============================================================================


def query_email_stats(ops_db: OpsDatabase, days: int = 7) -> dict[str, Any]:
    """Query email statistics with daily breakdown and rates."""
    since = datetime.now(UTC) - timedelta(days=days)
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
              AND recorded_at >= %s
            GROUP BY event_type
            """,
            (since_str,),
        )

        stats: dict[str, int] = {}
        for row in cursor.fetchall():
            event_type = row["event_type"]
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
              AND recorded_at >= %s
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
        "daily": [{"date": date, **counts} for date, counts in sorted(daily.items(), reverse=True)],
    }


def query_recent_emails(
    ops_db: OpsDatabase,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Query recent email events."""
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
            LIMIT %s
            """,
            (limit,),
        )

        emails: list[dict[str, Any]] = []
        for row in cursor.fetchall():
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

    return emails


def query_top_email_links(
    ops_db: OpsDatabase,
    days: int = 30,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Query top clicked links in emails."""
    since = datetime.now(UTC) - timedelta(days=days)
    since_str = since.isoformat()

    with ops_db.connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                payload::jsonb->>'click_url' as url,
                COUNT(*) as clicks
            FROM events
            WHERE entity_name = 'email'
              AND event_type = 'email.clicked'
              AND recorded_at >= %s
              AND payload::jsonb->>'click_url' IS NOT NULL
            GROUP BY payload::jsonb->>'click_url'
            ORDER BY clicks DESC
            LIMIT %s
            """,
            (since_str, limit),
        )

        return [{"url": row["url"], "clicks": row["clicks"]} for row in cursor.fetchall()]
