"""
JWT Bearer token middleware for FastAPI.

Provides authentication middleware that validates JWT tokens from mobile clients.
"""

from fastapi import Request as FastAPIRequest
from pydantic import BaseModel, Field

from dazzle.http.runtime.jwt_auth import JWTClaims, JWTError, JWTService

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
