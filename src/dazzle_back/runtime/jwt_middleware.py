"""
JWT Bearer token middleware for FastAPI.

Provides authentication middleware that validates JWT tokens from mobile clients.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from dazzle_back.runtime.jwt_auth import JWTClaims, JWTError, JWTService

# FastAPI is optional - import for type hints and runtime
try:
    from fastapi import Request as FastAPIRequest

    FASTAPI_AVAILABLE = True
except ImportError:
    FastAPIRequest = None  # type: ignore
    FASTAPI_AVAILABLE = False

if TYPE_CHECKING:
    pass


# =============================================================================
# Auth Context
# =============================================================================


class JWTAuthContext(BaseModel):
    """
    JWT authentication context.

    Available on request.state after JWT middleware processes the request.
    """

    claims: JWTClaims | None = Field(default=None, description="Decoded JWT claims")
    is_authenticated: bool = Field(default=False, description="Whether user is authenticated")
    error: str | None = Field(default=None, description="Authentication error if any")
    error_code: str | None = Field(default=None, description="Error code")

    @property
    def user_id(self) -> str | None:
        """Get the authenticated user's ID."""
        return self.claims.sub if self.claims else None

    @property
    def email(self) -> str | None:
        """Get the authenticated user's email."""
        return self.claims.email if self.claims else None

    @property
    def roles(self) -> list[str]:
        """Get the authenticated user's roles."""
        return self.claims.roles if self.claims else []

    @property
    def tenant_id(self) -> str | None:
        """Get the tenant ID for multi-tenancy."""
        return self.claims.tenant_id if self.claims else None


# =============================================================================
# JWT Middleware
# =============================================================================


class JWTMiddleware:
    """
    JWT authentication middleware for FastAPI.

    Extracts and validates JWT tokens from Authorization header.
    Sets JWTAuthContext on request.state.jwt_auth.
    """

    def __init__(
        self,
        jwt_service: JWTService,
        exclude_paths: list[str] | None = None,
        optional_paths: list[str] | None = None,
    ):
        """
        Initialize the JWT middleware.

        Args:
            jwt_service: JWT service for token validation
            exclude_paths: Paths to exclude from authentication
            optional_paths: Paths where auth is optional (no error if missing)
        """
        self.jwt_service = jwt_service
        self.exclude_paths = exclude_paths or [
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/auth/token",
            "/auth/register",
        ]
        self.optional_paths = optional_paths or []

    def _extract_token(self, request: FastAPIRequest) -> str | None:
        """
        Extract JWT token from Authorization header.

        Supports: Authorization: Bearer <token>

        Args:
            request: FastAPI request

        Returns:
            Token string or None
        """
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        return parts[1]

    def _is_excluded_path(self, path: str) -> bool:
        """Check if path is excluded from authentication."""
        for excluded in self.exclude_paths:
            if path.startswith(excluded):
                return True
        return False

    def _is_optional_path(self, path: str) -> bool:
        """Check if authentication is optional for this path."""
        for optional in self.optional_paths:
            if path.startswith(optional):
                return True
        return False

    def get_auth_context(self, request: FastAPIRequest) -> JWTAuthContext:
        """
        Get JWT auth context from request.

        Extracts and validates the JWT token, returning an auth context.

        Args:
            request: FastAPI request

        Returns:
            JWT authentication context
        """
        # Check for excluded paths
        if self._is_excluded_path(request.url.path):
            return JWTAuthContext()

        # Extract token
        token = self._extract_token(request)

        if not token:
            if self._is_optional_path(request.url.path):
                return JWTAuthContext()
            return JWTAuthContext(
                error="Missing authentication token",
                error_code="missing_token",
            )

        # Validate token
        try:
            claims = self.jwt_service.verify_access_token(token)
            return JWTAuthContext(
                claims=claims,
                is_authenticated=True,
            )
        except JWTError as e:
            return JWTAuthContext(
                error=e.message,
                error_code=e.code,
            )


# =============================================================================
# FastAPI Dependencies
# =============================================================================


def create_jwt_dependency(
    jwt_middleware: JWTMiddleware,
    require_auth: bool = True,
    require_roles: list[str] | None = None,
) -> Callable[[FastAPIRequest], Awaitable[JWTAuthContext]]:
    """
    Create a FastAPI dependency for JWT authentication.

    Args:
        jwt_middleware: JWT middleware instance
        require_auth: Whether authentication is required
        require_roles: Required roles (any of)

    Returns:
        FastAPI dependency function
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for JWT dependencies")

    from fastapi import HTTPException

    async def get_jwt_auth(request: FastAPIRequest) -> JWTAuthContext:
        """Validate JWT and return auth context."""
        context = jwt_middleware.get_auth_context(request)

        if require_auth and not context.is_authenticated:
            if context.error_code == "token_expired":
                raise HTTPException(status_code=401, detail="Token has expired")
            raise HTTPException(
                status_code=401,
                detail=context.error or "Authentication required",
            )

        if require_roles and context.is_authenticated:
            user_roles = set(context.roles)
            required = set(require_roles)
            if not required.intersection(user_roles):
                raise HTTPException(
                    status_code=403,
                    detail=f"Required roles: {require_roles}",
                )

        return context

    return get_jwt_auth


def create_optional_jwt_dependency(
    jwt_middleware: JWTMiddleware,
) -> Callable[[FastAPIRequest], Awaitable[JWTAuthContext]]:
    """
    Create a FastAPI dependency for optional JWT authentication.

    Returns auth context even if not authenticated.

    Args:
        jwt_middleware: JWT middleware instance

    Returns:
        FastAPI dependency function
    """
    return create_jwt_dependency(jwt_middleware, require_auth=False)


# =============================================================================
# Dual-Mode Auth (Cookie + JWT)
# =============================================================================


class DualAuthMiddleware:
    """
    Dual-mode authentication middleware.

    Supports both cookie-based sessions (web) and JWT tokens (mobile).
    Checks JWT first, falls back to session cookie.
    """

    def __init__(
        self,
        jwt_middleware: JWTMiddleware,
        auth_store: Any,  # AuthStore from auth.py
        cookie_name: str = "dazzle_session",
    ):
        """
        Initialize dual auth middleware.

        Args:
            jwt_middleware: JWT middleware for token auth
            auth_store: Session auth store
            cookie_name: Session cookie name
        """
        self.jwt_middleware = jwt_middleware
        self.auth_store = auth_store
        self.cookie_name = cookie_name

    def get_auth_context(self, request: FastAPIRequest) -> dict[str, Any]:
        """
        Get authentication context from either JWT or session.

        Returns a dict with:
        - auth_type: "jwt" | "session" | "none"
        - is_authenticated: bool
        - user_id: str | None
        - email: str | None
        - roles: list[str]
        - jwt_context: JWTAuthContext | None
        - session_context: AuthContext | None
        """
        # Try JWT first
        jwt_context = self.jwt_middleware.get_auth_context(request)
        if jwt_context.is_authenticated:
            return {
                "auth_type": "jwt",
                "is_authenticated": True,
                "user_id": jwt_context.user_id,
                "email": jwt_context.email,
                "roles": jwt_context.roles,
                "tenant_id": jwt_context.tenant_id,
                "jwt_context": jwt_context,
                "session_context": None,
            }

        # Fall back to session cookie
        session_id = request.cookies.get(self.cookie_name)
        if session_id:
            session_context = self.auth_store.validate_session(session_id)
            if session_context.is_authenticated:
                return {
                    "auth_type": "session",
                    "is_authenticated": True,
                    "user_id": str(session_context.user.id),
                    "email": session_context.user.email,
                    "roles": session_context.roles,
                    "tenant_id": None,
                    "jwt_context": None,
                    "session_context": session_context,
                }

        # Not authenticated
        return {
            "auth_type": "none",
            "is_authenticated": False,
            "user_id": None,
            "email": None,
            "roles": [],
            "tenant_id": None,
            "jwt_context": jwt_context if jwt_context.error else None,
            "session_context": None,
        }


def create_dual_auth_dependency(
    dual_middleware: DualAuthMiddleware,
    require_auth: bool = True,
    require_roles: list[str] | None = None,
) -> Callable[[FastAPIRequest], Awaitable[dict[str, Any]]]:
    """
    Create a FastAPI dependency for dual-mode authentication.

    Args:
        dual_middleware: Dual auth middleware instance
        require_auth: Whether authentication is required
        require_roles: Required roles (any of)

    Returns:
        FastAPI dependency function
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for auth dependencies")

    from fastapi import HTTPException

    async def get_dual_auth(request: FastAPIRequest) -> dict[str, Any]:
        """Validate auth and return context."""
        context = dual_middleware.get_auth_context(request)

        if require_auth and not context["is_authenticated"]:
            jwt_ctx = context.get("jwt_context")
            if jwt_ctx and jwt_ctx.error_code == "token_expired":
                raise HTTPException(status_code=401, detail="Token has expired")
            raise HTTPException(status_code=401, detail="Authentication required")

        if require_roles and context["is_authenticated"]:
            user_roles = set(context["roles"])
            required = set(require_roles)
            if not required.intersection(user_roles):
                raise HTTPException(
                    status_code=403,
                    detail=f"Required roles: {require_roles}",
                )

        return context

    return get_dual_auth
