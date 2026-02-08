"""
Founder Console Routes.

HTMX + DaisyUI control plane for founders:
- Health dashboard
- App map (entities, surfaces, integrations)
- Spec versioning and change tracking
- Performance monitoring
- Deployment pipeline (via deploy_routes)
- Rollback (via deploy_routes)

Route prefix: /_console/ (full pages) + /_console/partials/ (HTMX fragments)
Auth: Reuses OpsSessionManager cookie-based sessions from ops_routes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
    from fastapi.responses import HTMLResponse, RedirectResponse

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

if TYPE_CHECKING:
    from jinja2 import Environment

    from dazzle_back.runtime.health_aggregator import HealthAggregator
    from dazzle_back.runtime.ops_database import OpsDatabase

logger = logging.getLogger("dazzle.console")

# Template directory (same Jinja2 env as DNR UI)
TEMPLATES_DIR = Path(__file__).parent.parent.replace("dazzle_back", "dazzle_ui") if False else None  # noqa: E501

NAV_ITEMS = [
    {"route": "/_console/", "label": "Dashboard", "icon": "chart-bar"},
    {"route": "/_console/app-map", "label": "App Map", "icon": "map"},
    {"route": "/_console/changes", "label": "Changes", "icon": "clock"},
    {"route": "/_console/deploy", "label": "Deploy", "icon": "rocket"},
    {"route": "/_console/performance", "label": "Performance", "icon": "bolt"},
]


def _get_templates_dir() -> Path:
    """Resolve templates directory from dazzle_ui package."""
    import dazzle_ui

    return Path(dazzle_ui.__file__).parent / "templates"


def _create_jinja_env() -> Environment:
    """Create a Jinja2 environment for console templates."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    templates_dir = _get_templates_dir()
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html"]),
    )
    return env


def create_console_routes(
    ops_db: OpsDatabase,
    health_aggregator: HealthAggregator | None = None,
    appspec: Any | None = None,
    spec_version_store: Any | None = None,
    deploy_history_store: Any | None = None,
    require_auth: bool = True,
) -> APIRouter:
    """
    Create Founder Console routes.

    Args:
        ops_db: Operations database
        health_aggregator: Health check aggregator
        appspec: Loaded AppSpec IR (in-memory)
        spec_version_store: Spec version store for change tracking
        deploy_history_store: Deployment history store
        require_auth: Whether to require authentication

    Returns:
        FastAPI APIRouter with console endpoints
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI required for console routes")

    from dazzle_back.runtime.ops_routes import OpsSessionManager

    router = APIRouter(prefix="/_console", tags=["Founder Console"])
    session_manager = OpsSessionManager()
    jinja_env = _create_jinja_env()

    # -------------------------------------------------------------------------
    # Auth dependency (reuses ops_session cookie)
    # -------------------------------------------------------------------------

    async def get_current_user(ops_session: str | None = Cookie(None)) -> str:
        """Validate ops session and return username."""
        if not require_auth:
            return "anonymous"
        if not ops_session:
            raise HTTPException(status_code=401, detail="Not authenticated")
        username = session_manager.validate_session(ops_session)
        if not username:
            raise HTTPException(status_code=401, detail="Session expired")
        return username

    async def get_optional_user(ops_session: str | None = Cookie(None)) -> str | None:
        """Return username if authenticated, None otherwise."""
        if not require_auth:
            return "anonymous"
        if not ops_session:
            return None
        return session_manager.validate_session(ops_session)

    # -------------------------------------------------------------------------
    # Helper: render template
    # -------------------------------------------------------------------------

    def render(template_name: str, context: dict[str, Any] | None = None) -> HTMLResponse:
        """Render a Jinja2 template to HTMLResponse."""
        ctx = {
            "nav_items": NAV_ITEMS,
            "app_name": "Dazzle Console",
            **(context or {}),
        }
        template = jinja_env.get_template(template_name)
        html = template.render(**ctx)
        return HTMLResponse(content=html)

    # -------------------------------------------------------------------------
    # Login / Logout
    # -------------------------------------------------------------------------

    @router.get("/login", response_model=None)
    async def login_page(
        user: str | None = Depends(get_optional_user),
    ) -> Response:
        """Show login page or redirect if already authenticated."""
        if user:
            return RedirectResponse(url="/_console/", status_code=302)
        return render("console/login.html", {"setup_required": not ops_db.has_credentials()})

    @router.post("/login", response_model=None)
    async def login_submit(
        request: Request,
        response: Response,
    ) -> Response:
        """Handle login form submission (HTMX or standard)."""
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))

        if not ops_db.has_credentials():
            # First-time setup
            if len(password) < 8:
                return render(
                    "console/login.html",
                    {
                        "error": "Password must be at least 8 characters",
                        "setup_required": True,
                    },
                )
            ops_db.create_credentials(username, password)

        if not ops_db.verify_credentials(username, password):
            return render(
                "console/login.html",
                {
                    "error": "Invalid credentials",
                    "setup_required": False,
                },
            )

        token = session_manager.create_session(username)
        resp = RedirectResponse(url="/_console/", status_code=302)
        resp.set_cookie(
            key="ops_session",
            value=token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=86400,
        )
        return resp

    @router.get("/logout")
    async def logout(
        response: Response,
        ops_session: str | None = Cookie(None),
    ) -> RedirectResponse:
        """Log out and redirect to login."""
        if ops_session:
            session_manager.revoke_session(ops_session)
        resp = RedirectResponse(url="/_console/login", status_code=302)
        resp.delete_cookie("ops_session")
        return resp

    # -------------------------------------------------------------------------
    # Dashboard (Phase 1)
    # -------------------------------------------------------------------------

    @router.get("/", response_model=None)
    async def dashboard(
        user: str | None = Depends(get_optional_user),
    ) -> Response:
        """Main dashboard page."""
        if not user:
            return RedirectResponse(url="/_console/login", status_code=302)

        # Gather app summary from appspec
        app_summary = _get_app_summary(appspec)

        return render(
            "console/dashboard.html",
            {
                "current_route": "/_console/",
                "username": user,
                "app_summary": app_summary,
            },
        )

    @router.get("/partials/health-cards", response_class=HTMLResponse)
    async def health_cards_partial(
        user: str = Depends(get_current_user),
    ) -> HTMLResponse:
        """HTMX partial: health status cards."""
        health_data = _get_health_data(health_aggregator)
        return render(
            "console/partials/health_cards.html",
            {
                "health": health_data,
            },
        )

    # -------------------------------------------------------------------------
    # App Map (Phase 2)
    # -------------------------------------------------------------------------

    @router.get("/app-map", response_model=None)
    async def app_map(
        user: str | None = Depends(get_optional_user),
    ) -> Response:
        """App map page showing entities, surfaces, integrations."""
        if not user:
            return RedirectResponse(url="/_console/login", status_code=302)
        return render(
            "console/app_map.html",
            {
                "current_route": "/_console/app-map",
                "username": user,
            },
        )

    @router.get("/partials/entities", response_class=HTMLResponse)
    async def entities_partial(
        user: str = Depends(get_current_user),
    ) -> HTMLResponse:
        """HTMX partial: entity list."""
        entities = _get_entities(appspec)
        return render("console/partials/entity_list.html", {"entities": entities})

    @router.get("/partials/surfaces", response_class=HTMLResponse)
    async def surfaces_partial(
        user: str = Depends(get_current_user),
    ) -> HTMLResponse:
        """HTMX partial: surface list."""
        surfaces = _get_surfaces(appspec)
        return render("console/partials/surface_list.html", {"surfaces": surfaces})

    @router.get("/partials/integrations", response_class=HTMLResponse)
    async def integrations_partial(
        user: str = Depends(get_current_user),
    ) -> HTMLResponse:
        """HTMX partial: integrations/services/foreign models list."""
        integrations = _get_integrations(appspec)
        return render("console/partials/integration_list.html", {"integrations": integrations})

    # -------------------------------------------------------------------------
    # Changes / Spec Versioning (Phase 3)
    # -------------------------------------------------------------------------

    @router.get("/changes", response_model=None)
    async def changes_page(
        user: str | None = Depends(get_optional_user),
    ) -> Response:
        """Spec versioning and change tracking page."""
        if not user:
            return RedirectResponse(url="/_console/login", status_code=302)
        return render(
            "console/changes.html",
            {
                "current_route": "/_console/changes",
                "username": user,
            },
        )

    @router.get("/partials/version-timeline", response_class=HTMLResponse)
    async def version_timeline_partial(
        page: int = Query(default=1, ge=1),
        user: str = Depends(get_current_user),
    ) -> HTMLResponse:
        """HTMX partial: paginated version timeline."""
        versions: list[dict[str, Any]] = []
        total = 0
        if spec_version_store:
            versions = spec_version_store.list_versions(page=page, per_page=10)
            total = spec_version_store.count_versions()
        return render(
            "console/partials/version_timeline.html",
            {
                "versions": versions,
                "page": page,
                "total": total,
                "per_page": 10,
            },
        )

    @router.get("/partials/spec-diff/{version_id}", response_class=HTMLResponse)
    async def spec_diff_partial(
        version_id: str,
        user: str = Depends(get_current_user),
    ) -> HTMLResponse:
        """HTMX partial: structured diff for a spec version."""
        diff: dict[str, Any] = {}
        if spec_version_store:
            diff = spec_version_store.get_diff(version_id)
        return render("console/partials/spec_diff.html", {"diff": diff, "version_id": version_id})

    # -------------------------------------------------------------------------
    # Deploy (Phase 4) - delegates to deploy_routes
    # -------------------------------------------------------------------------

    @router.get("/deploy", response_model=None)
    async def deploy_page(
        user: str | None = Depends(get_optional_user),
    ) -> Response:
        """Deployment pipeline page."""
        if not user:
            return RedirectResponse(url="/_console/login", status_code=302)
        return render(
            "console/deploy.html",
            {
                "current_route": "/_console/deploy",
                "username": user,
            },
        )

    @router.get("/partials/deploy-history", response_class=HTMLResponse)
    async def deploy_history_partial(
        user: str = Depends(get_current_user),
    ) -> HTMLResponse:
        """HTMX partial: deployment history table."""
        history: list[dict[str, Any]] = []
        if deploy_history_store:
            history = deploy_history_store.list_deployments(limit=20)
        return render("console/partials/deploy_history.html", {"history": history})

    # -------------------------------------------------------------------------
    # Performance (Phase 5)
    # -------------------------------------------------------------------------

    @router.get("/performance", response_model=None)
    async def performance_page(
        user: str | None = Depends(get_optional_user),
    ) -> Response:
        """Performance monitoring page."""
        if not user:
            return RedirectResponse(url="/_console/login", status_code=302)
        return render(
            "console/performance.html",
            {
                "current_route": "/_console/performance",
                "username": user,
            },
        )

    @router.get("/partials/api-perf", response_class=HTMLResponse)
    async def api_perf_partial(
        hours: int = Query(default=24, le=168),
        user: str = Depends(get_current_user),
    ) -> HTMLResponse:
        """HTMX partial: API performance table."""
        stats = ops_db.get_api_call_stats(hours=hours)
        # Also get p95 from raw data
        perf_data = _get_api_perf_data(ops_db, hours)
        return render(
            "console/partials/api_performance.html",
            {
                "stats": stats,
                "perf_data": perf_data,
                "hours": hours,
            },
        )

    @router.get("/partials/errors", response_class=HTMLResponse)
    async def errors_partial(
        hours: int = Query(default=24, le=168),
        user: str = Depends(get_current_user),
    ) -> HTMLResponse:
        """HTMX partial: error summary."""
        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        error_data = _get_error_data(ops_db, cutoff)
        return render(
            "console/partials/error_summary.html",
            {
                "error_data": error_data,
                "hours": hours,
            },
        )

    @router.get("/partials/costs", response_class=HTMLResponse)
    async def costs_partial(
        hours: int = Query(default=24, le=168),
        user: str = Depends(get_current_user),
    ) -> HTMLResponse:
        """HTMX partial: cost indicators."""
        cost_data = _get_cost_data(ops_db, hours)
        return render(
            "console/partials/cost_indicators.html",
            {
                "cost_data": cost_data,
                "hours": hours,
            },
        )

    return router


# =============================================================================
# Data helpers
# =============================================================================


def _get_app_summary(appspec: Any) -> dict[str, Any]:
    """Extract app summary from AppSpec."""
    if not appspec:
        return {
            "name": "Unknown",
            "version": "0.0.0",
            "entities": 0,
            "surfaces": 0,
            "integrations": 0,
        }

    entities = getattr(appspec, "entities", [])
    surfaces = getattr(appspec, "surfaces", [])
    integrations = getattr(appspec, "integrations", [])
    services = getattr(appspec, "services", [])
    name = getattr(appspec, "name", "Unknown")
    version = getattr(appspec, "version", "0.0.0")

    return {
        "name": name,
        "version": version,
        "entities": len(entities) if entities else 0,
        "surfaces": len(surfaces) if surfaces else 0,
        "integrations": (len(integrations) if integrations else 0)
        + (len(services) if services else 0),
    }


def _get_health_data(health_aggregator: Any) -> dict[str, Any]:
    """Get health data from aggregator."""
    if not health_aggregator:
        return {
            "status": "unknown",
            "components": [],
            "summary": {"total": 0, "healthy": 0, "degraded": 0, "unhealthy": 0},
        }

    health = health_aggregator.get_latest()
    return {
        "status": health.status.value,
        "checked_at": health.checked_at.isoformat() if health.checked_at else "",
        "components": [
            {
                "name": c.name,
                "type": c.component_type.value,
                "status": c.status.value,
                "latency_ms": round(c.latency_ms, 1) if c.latency_ms else None,
                "message": c.message,
            }
            for c in health.components
        ],
        "summary": {
            "total": health.total_components,
            "healthy": health.healthy_count,
            "degraded": health.degraded_count,
            "unhealthy": health.unhealthy_count,
        },
    }


def _get_entities(appspec: Any) -> list[dict[str, Any]]:
    """Extract entity data from AppSpec."""
    if not appspec:
        return []
    entities = getattr(appspec, "entities", [])
    result = []
    for entity in entities:
        fields = []
        for f in getattr(entity, "fields", []):
            fields.append(
                {
                    "name": getattr(f, "name", ""),
                    "type": str(getattr(f, "type", getattr(f, "field_type", ""))),
                    "required": getattr(f, "required", False),
                    "primary_key": getattr(f, "primary_key", False),
                }
            )
        result.append(
            {
                "name": getattr(entity, "name", ""),
                "label": getattr(entity, "label", getattr(entity, "name", "")),
                "fields": fields,
                "field_count": len(fields),
                "has_state_machine": bool(getattr(entity, "state_machine", None)),
            }
        )
    return result


def _get_surfaces(appspec: Any) -> list[dict[str, Any]]:
    """Extract surface data from AppSpec."""
    if not appspec:
        return []
    surfaces = getattr(appspec, "surfaces", [])
    result = []
    for surface in surfaces:
        sections = getattr(surface, "sections", [])
        field_count = sum(len(getattr(s, "fields", [])) for s in sections)
        entity_name = getattr(surface, "entity", None)
        if entity_name and hasattr(entity_name, "name"):
            entity_name = entity_name.name
        result.append(
            {
                "name": getattr(surface, "name", ""),
                "label": getattr(surface, "label", getattr(surface, "name", "")),
                "mode": getattr(surface, "mode", "unknown"),
                "entity": entity_name or "",
                "field_count": field_count,
                "section_count": len(sections),
            }
        )
    return result


def _get_integrations(appspec: Any) -> list[dict[str, Any]]:
    """Extract integrations, services, and foreign models from AppSpec."""
    if not appspec:
        return []
    result = []
    for item in getattr(appspec, "integrations", []):
        result.append(
            {
                "name": getattr(item, "name", ""),
                "label": getattr(item, "label", getattr(item, "name", "")),
                "kind": "integration",
                "provider": getattr(item, "provider", ""),
            }
        )
    for item in getattr(appspec, "services", []):
        result.append(
            {
                "name": getattr(item, "name", ""),
                "label": getattr(item, "label", getattr(item, "name", "")),
                "kind": "service",
            }
        )
    for item in getattr(appspec, "foreign_models", []):
        result.append(
            {
                "name": getattr(item, "name", ""),
                "label": getattr(item, "label", getattr(item, "name", "")),
                "kind": "foreign_model",
                "source": getattr(item, "source", ""),
            }
        )
    return result


def _get_api_perf_data(ops_db: Any, hours: int) -> list[dict[str, Any]]:
    """Get API performance data with p95 latency."""
    from datetime import UTC, datetime, timedelta

    cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    result = []
    try:
        with ops_db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    endpoint,
                    method,
                    COUNT(*) as count,
                    AVG(latency_ms) as avg_ms,
                    MAX(latency_ms) as max_ms
                FROM api_calls
                WHERE called_at >= ?
                GROUP BY endpoint, method
                ORDER BY count DESC
                LIMIT 50
                """,
                (cutoff,),
            )
            for row in cursor.fetchall():
                result.append(
                    {
                        "endpoint": row["endpoint"],
                        "method": row["method"],
                        "count": row["count"],
                        "avg_ms": round(row["avg_ms"], 1) if row["avg_ms"] else 0,
                        "max_ms": round(row["max_ms"], 1) if row["max_ms"] else 0,
                    }
                )
    except Exception:
        pass
    return result


def _get_error_data(ops_db: Any, cutoff: str) -> dict[str, Any]:
    """Get error summary data."""
    result: dict[str, Any] = {"by_endpoint": {}, "recent": [], "total": 0}
    try:
        with ops_db.connection() as conn:
            # Errors by endpoint
            cursor = conn.execute(
                """
                SELECT endpoint, status_code, COUNT(*) as count
                FROM api_calls
                WHERE called_at >= ? AND (status_code >= 400 OR error_message IS NOT NULL)
                GROUP BY endpoint, status_code
                ORDER BY count DESC
                LIMIT 20
                """,
                (cutoff,),
            )
            for row in cursor.fetchall():
                key = f"{row['endpoint']} ({row['status_code'] or 'error'})"
                result["by_endpoint"][key] = row["count"]
                result["total"] += row["count"]

            # Recent errors
            cursor = conn.execute(
                """
                SELECT endpoint, method, status_code, error_message, called_at
                FROM api_calls
                WHERE called_at >= ? AND (status_code >= 400 OR error_message IS NOT NULL)
                ORDER BY called_at DESC
                LIMIT 10
                """,
                (cutoff,),
            )
            result["recent"] = [dict(row) for row in cursor.fetchall()]
    except Exception:
        pass
    return result


def _get_cost_data(ops_db: Any, hours: int) -> dict[str, Any]:
    """Get cost indicator data."""
    from datetime import UTC, datetime, timedelta

    cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    result: dict[str, Any] = {"by_service": {}, "total_cents": 0, "total_calls": 0}
    try:
        with ops_db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    service_name,
                    COUNT(*) as calls,
                    SUM(COALESCE(cost_cents, 0)) as cost_cents
                FROM api_calls
                WHERE called_at >= ?
                GROUP BY service_name
                ORDER BY cost_cents DESC
                """,
                (cutoff,),
            )
            for row in cursor.fetchall():
                result["by_service"][row["service_name"]] = {
                    "calls": row["calls"],
                    "cost_cents": row["cost_cents"] or 0,
                }
                result["total_cents"] += row["cost_cents"] or 0
                result["total_calls"] += row["calls"]
    except Exception:
        pass
    return result
