"""
Audit log query routes.

Admin-only endpoints for querying access control audit trail.
Mounted at /api/_audit/*.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    from fastapi import APIRouter, Depends, HTTPException, Query

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore[misc, assignment]
    Depends = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[misc, assignment]
    Query = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from dazzle_back.runtime.audit_log import AuditLogger
    from dazzle_back.runtime.auth import AuthContext


def create_audit_routes(
    audit_logger: AuditLogger,
    auth_dep: Any = None,
) -> APIRouter:
    """Create admin-only audit query routes.

    Args:
        audit_logger: AuditLogger instance for querying logs.
        auth_dep: FastAPI auth dependency that requires authentication.

    Returns:
        FastAPI router with audit endpoints.
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for audit routes")

    router = APIRouter(prefix="/api/_audit", tags=["Audit"])

    def _require_admin(auth_context: AuthContext) -> None:
        """Check that the authenticated user is a superuser."""
        if not auth_context or not auth_context.is_authenticated:
            raise HTTPException(status_code=401, detail="Authentication required")
        user = auth_context.user
        if not user or not getattr(user, "is_superuser", False):
            raise HTTPException(status_code=403, detail="Admin access required")

    if auth_dep is not None:

        @router.get("/logs", summary="Query audit logs")
        async def query_logs(
            auth_context: AuthContext = Depends(auth_dep),
            entity: str | None = Query(None, description="Filter by entity name"),
            operation: str | None = Query(None, description="Filter by operation"),
            user_id: str | None = Query(None, description="Filter by user ID"),
            since: str | None = Query(None, description="ISO timestamp to filter from"),
            limit: int = Query(100, ge=1, le=1000, description="Max results"),
        ) -> dict[str, Any]:
            """Query audit logs with optional filters."""
            _require_admin(auth_context)
            logs = audit_logger.query_logs(
                entity_name=entity,
                operation=operation,
                user_id=user_id,
                since=since,
                limit=limit,
            )
            return {"logs": logs, "count": len(logs)}

        @router.get("/logs/{entity_name}/{entity_id}", summary="Query entity audit logs")
        async def query_entity_logs(
            entity_name: str,
            entity_id: str,
            auth_context: AuthContext = Depends(auth_dep),
            limit: int = Query(100, ge=1, le=1000, description="Max results"),
        ) -> dict[str, Any]:
            """Query all audit entries for a specific record."""
            _require_admin(auth_context)
            logs = audit_logger.query_entity_logs(
                entity_name=entity_name,
                entity_id=entity_id,
                limit=limit,
            )
            return {"logs": logs, "count": len(logs)}

        @router.get("/stats", summary="Audit statistics")
        async def query_stats(
            auth_context: AuthContext = Depends(auth_dep),
            entity: str | None = Query(None, description="Filter by entity name"),
            window: int = Query(24, ge=1, le=720, description="Window in hours"),
        ) -> dict[str, Any]:
            """Get aggregated audit statistics."""
            _require_admin(auth_context)
            return audit_logger.query_stats(
                entity_name=entity,
                window_hours=window,
            )

    else:
        # No auth — still expose endpoints (dev/test mode)
        @router.get("/logs", summary="Query audit logs")
        async def query_logs_noauth(
            entity: str | None = Query(None, description="Filter by entity name"),
            operation: str | None = Query(None, description="Filter by operation"),
            user_id: str | None = Query(None, description="Filter by user ID"),
            since: str | None = Query(None, description="ISO timestamp to filter from"),
            limit: int = Query(100, ge=1, le=1000, description="Max results"),
        ) -> dict[str, Any]:
            """Query audit logs with optional filters (no auth)."""
            logs = audit_logger.query_logs(
                entity_name=entity,
                operation=operation,
                user_id=user_id,
                since=since,
                limit=limit,
            )
            return {"logs": logs, "count": len(logs)}

        @router.get("/logs/{entity_name}/{entity_id}", summary="Query entity audit logs")
        async def query_entity_logs_noauth(
            entity_name: str,
            entity_id: str,
            limit: int = Query(100, ge=1, le=1000, description="Max results"),
        ) -> dict[str, Any]:
            """Query all audit entries for a specific record."""
            logs = audit_logger.query_entity_logs(
                entity_name=entity_name,
                entity_id=entity_id,
                limit=limit,
            )
            return {"logs": logs, "count": len(logs)}

        @router.get("/stats", summary="Audit statistics")
        async def query_stats_noauth(
            entity: str | None = Query(None, description="Filter by entity name"),
            window: int = Query(24, ge=1, le=720, description="Window in hours"),
        ) -> dict[str, Any]:
            """Get aggregated audit statistics (no auth)."""
            return audit_logger.query_stats(
                entity_name=entity,
                window_hours=window,
            )

    return router
