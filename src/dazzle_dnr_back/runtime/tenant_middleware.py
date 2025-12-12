"""
Tenant middleware for DNR-Back applications.

Extracts tenant ID from requests and sets it in the request context.
Works with TenantDatabaseManager to route requests to the correct database.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI


# =============================================================================
# Tenant Header Configuration
# =============================================================================


# HTTP header for tenant identification
TENANT_HEADER = "X-Tenant-ID"

# Cookie name for tenant (fallback)
TENANT_COOKIE = "dazzle_tenant_id"

# Query parameter for tenant (lowest priority)
TENANT_QUERY_PARAM = "tenant_id"


# =============================================================================
# Tenant Middleware
# =============================================================================


def create_tenant_middleware(
    on_tenant_not_found: Callable[[str], Any] | None = None,
    allow_missing_tenant: bool = False,
) -> Any:
    """
    Create a middleware that extracts and sets tenant ID.

    Tenant ID is extracted from (in order of priority):
    1. X-Tenant-ID header
    2. dazzle_tenant_id cookie
    3. tenant_id query parameter

    Args:
        on_tenant_not_found: Optional callback when tenant doesn't exist
        allow_missing_tenant: If True, allow requests without tenant ID

    Returns:
        Starlette middleware class
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response

    from dazzle_dnr_back.runtime.tenant_isolation import set_current_tenant_id

    class TenantMiddleware(BaseHTTPMiddleware):
        """Middleware to extract and set tenant ID for each request."""

        async def dispatch(self, request: Request, call_next: Any) -> Response:
            # Extract tenant ID from various sources
            tenant_id = self._extract_tenant_id(request)

            # Set tenant context
            set_current_tenant_id(tenant_id)

            # Store in request state for easy access
            request.state.tenant_id = tenant_id

            # Check if tenant is required but missing
            if not allow_missing_tenant and tenant_id is None:
                # Skip check for certain paths (health checks, auth, etc.)
                path = request.url.path
                skip_paths = [
                    "/health",
                    "/docs",
                    "/openapi.json",
                    "/redoc",
                    "/auth/",
                    "/_dazzle/",
                    "/_dnr/",
                ]
                if not any(path.startswith(skip) for skip in skip_paths):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "detail": f"Missing required {TENANT_HEADER} header",
                            "error": "tenant_required",
                        },
                    )

            # Validate tenant exists if callback provided
            if tenant_id and on_tenant_not_found:
                # Let the callback handle validation
                error_response = on_tenant_not_found(tenant_id)
                if error_response:
                    return error_response  # type: ignore[no-any-return]

            try:
                response = await call_next(request)
                return response  # type: ignore[no-any-return]
            finally:
                # Clean up context
                set_current_tenant_id(None)

        def _extract_tenant_id(self, request: Request) -> str | None:
            """Extract tenant ID from request."""
            # 1. Check header (highest priority)
            tenant_id = request.headers.get(TENANT_HEADER)
            if tenant_id:
                return tenant_id

            # 2. Check cookie
            tenant_id = request.cookies.get(TENANT_COOKIE)
            if tenant_id:
                return tenant_id

            # 3. Check query parameter (lowest priority)
            tenant_id = request.query_params.get(TENANT_QUERY_PARAM)
            if tenant_id:
                return tenant_id

            return None

    return TenantMiddleware


def apply_tenant_middleware(
    app: FastAPI,
    tenant_manager: Any,
    *,
    allow_missing_tenant: bool = False,
    auto_provision: bool = True,
) -> None:
    """
    Apply tenant middleware to a FastAPI application.

    Args:
        app: FastAPI application instance
        tenant_manager: TenantDatabaseManager instance
        allow_missing_tenant: If True, allow requests without tenant ID
        auto_provision: If True, auto-provision new tenants
    """
    from starlette.responses import JSONResponse

    def on_tenant_not_found(tenant_id: str) -> JSONResponse | None:
        """Handle missing tenant."""
        if tenant_manager.tenant_exists(tenant_id):
            return None  # Tenant exists, continue

        if auto_provision:
            # Auto-provision the tenant
            try:
                tenant_manager.provision_tenant(tenant_id)
                return None  # Successfully provisioned
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={
                        "detail": f"Failed to provision tenant: {e}",
                        "error": "tenant_provision_failed",
                    },
                )
        else:
            return JSONResponse(
                status_code=404,
                content={
                    "detail": f"Tenant '{tenant_id}' not found",
                    "error": "tenant_not_found",
                },
            )

    TenantMiddleware = create_tenant_middleware(
        on_tenant_not_found=on_tenant_not_found,
        allow_missing_tenant=allow_missing_tenant,
    )
    app.add_middleware(TenantMiddleware)


# =============================================================================
# Dependency Helpers
# =============================================================================


def get_tenant_db_dependency(tenant_manager: Any) -> Callable[..., Any]:
    """
    Create a FastAPI dependency that returns the tenant's DatabaseManager.

    Args:
        tenant_manager: TenantDatabaseManager instance

    Returns:
        FastAPI dependency function
    """
    from fastapi import Request

    def get_tenant_db(request: Request) -> Any:
        """Get the database manager for the current tenant."""
        tenant_id = getattr(request.state, "tenant_id", None)
        if not tenant_id:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="Tenant ID required")
        return tenant_manager.get_tenant_manager(tenant_id)

    return get_tenant_db
