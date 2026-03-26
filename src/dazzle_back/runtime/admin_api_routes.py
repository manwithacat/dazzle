"""
Admin workspace API routes for action triggers.

Provides POST endpoints for admin actions (deploy, rollback) that are
surfaced as buttons in admin workspace regions.

All endpoints require super_admin authentication.
"""

import logging
from typing import Any

from dazzle_back.runtime._fastapi_compat import FASTAPI_AVAILABLE

if FASTAPI_AVAILABLE:
    from fastapi import APIRouter, HTTPException, Request
    from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def create_admin_api_routes(
    *,
    deploy_history_store: Any | None = None,
    rollback_manager: Any | None = None,
) -> Any:
    """Create admin API routes for workspace region actions.

    Args:
        deploy_history_store: Store for deployment records.
        rollback_manager: Manager for DSL rollback operations.

    Returns:
        A FastAPI APIRouter with the admin action endpoints.
    """
    if not FASTAPI_AVAILABLE:
        return None

    router = APIRouter(prefix="/_admin/api", tags=["admin"])

    @router.post("/deploys/trigger")
    async def trigger_deploy(request: Request) -> JSONResponse:
        """Trigger a new deployment (super_admin only)."""
        user = getattr(request.state, "user", None)
        if not user or getattr(user, "role", None) != "super_admin":
            raise HTTPException(status_code=403, detail="super_admin required")

        if deploy_history_store is None:
            raise HTTPException(status_code=501, detail="Deploy history store not configured")

        try:
            record = deploy_history_store.create_deployment(
                environment="production",
                initiated_by=getattr(user, "email", "admin"),
            )
            logger.info("Deploy triggered: %s by %s", record.id, getattr(user, "email", "admin"))
            return JSONResponse({"status": "ok", "deployment_id": record.id})
        except Exception as exc:
            logger.error("Deploy trigger failed: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    @router.post("/deploys/{deploy_id}/rollback")
    async def rollback_deploy(deploy_id: str, request: Request) -> JSONResponse:
        """Rollback to a specific deployment (super_admin only)."""
        user = getattr(request.state, "user", None)
        if not user or getattr(user, "role", None) != "super_admin":
            raise HTTPException(status_code=403, detail="super_admin required")

        if rollback_manager is None:
            raise HTTPException(status_code=501, detail="Rollback manager not configured")

        try:
            rollback_manager.rollback_to(deploy_id)
            logger.info("Rollback to %s by %s", deploy_id, getattr(user, "email", "admin"))
            return JSONResponse({"status": "ok", "rolled_back_to": deploy_id})
        except Exception as exc:
            logger.error("Rollback failed: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    return router
