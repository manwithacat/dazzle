"""Authentication middleware for FastAPI."""

from typing import Any

from .models import AuthContext
from .store import AuthStore


class AuthMiddleware:
    """
    Authentication middleware for FastAPI.

    Validates session cookies and sets auth context on request.
    """

    def __init__(
        self,
        auth_store: AuthStore,
        cookie_name: str = "dazzle_session",
        exclude_paths: list[str] | None = None,
    ):
        """
        Initialize the auth middleware.

        Args:
            auth_store: Auth store instance
            cookie_name: Session cookie name
            exclude_paths: Paths to exclude from auth
        """
        self.auth_store = auth_store
        self.cookie_name = cookie_name
        self.exclude_paths = exclude_paths or [
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/auth/login",
            "/auth/register",
            "/auth/forgot-password",
            "/auth/reset-password",
            "/auth/2fa/challenge",
            "/auth/2fa/verify",
            "/auth/2fa/recovery",
            "/webhooks/ses/notifications",
        ]

    def get_auth_context(self, request: Any) -> AuthContext:
        """
        Get auth context from request.

        Reads session cookie and validates session.

        #1419: resolve the session id the same tenant-aware way the rest of the
        auth layer does (entity surfaces / permits read via ``read_session_id``).
        Under ``tenant_host:`` new logins write ``__Host-<app>_session``; a single
        fixed-name lookup returned an empty AuthContext → every workspace 403'd.
        ``read_session_id`` tries the legacy ``default`` first, so single-tenant
        apps are unchanged.
        """
        from dazzle.http.runtime.auth.cookie_name import read_session_id

        session_id = read_session_id(request, default=self.cookie_name)

        if not session_id:
            return AuthContext()

        return self.auth_store.validate_session(session_id)

    def is_excluded_path(self, path: str) -> bool:
        """Check if path is excluded from auth."""
        for excluded in self.exclude_paths:
            if path.startswith(excluded):
                return True
        return False
