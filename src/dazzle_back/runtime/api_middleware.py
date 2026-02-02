"""
API Tracking Middleware.

FastAPI middleware that automatically tracks outbound API calls
when using the integrated HTTP client.

Also provides request correlation for tracing API calls back to
the originating user request.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from fastapi import FastAPI, Request, Response
    from starlette.middleware.base import RequestResponseEndpoint

    from dazzle_back.runtime.api_tracker import ApiTracker


# Context variable for request correlation
_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)
_tenant_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("tenant_id", default=None)
_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)


def get_correlation_id() -> str | None:
    """Get the current request's correlation ID."""
    return _correlation_id.get()


def get_tenant_id() -> str | None:
    """Get the current request's tenant ID."""
    return _tenant_id.get()


def get_user_id() -> str | None:
    """Get the current request's user ID."""
    return _user_id.get()


@dataclass
class RequestContext:
    """Current request context for API tracking."""

    correlation_id: str
    tenant_id: str | None = None
    user_id: str | None = None

    @classmethod
    def current(cls) -> RequestContext:
        """Get current request context from context vars."""
        return cls(
            correlation_id=_correlation_id.get() or str(uuid4()),
            tenant_id=_tenant_id.get(),
            user_id=_user_id.get(),
        )


class ApiTrackingMiddleware:
    """
    ASGI middleware for API call correlation.

    Sets up context variables for:
    - Correlation ID (for tracing)
    - Tenant ID (from header or auth)
    - User ID (from auth)

    These are automatically used by ApiTracker for scoping.
    """

    def __init__(self, app: Any, tracker: ApiTracker | None = None):
        """
        Initialize middleware.

        Args:
            app: ASGI application
            tracker: Optional ApiTracker for recording inbound requests
        """
        self.app = app
        self.tracker = tracker

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """ASGI middleware entry point."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract headers
        headers = dict(scope.get("headers", []))

        # Set correlation ID (from header or generate)
        correlation_id = headers.get(b"x-correlation-id", b"").decode() or str(uuid4())
        _correlation_id.set(correlation_id)

        # Set tenant ID from header
        tenant_id = headers.get(b"x-tenant-id", b"").decode() or None
        _tenant_id.set(tenant_id)

        # User ID would come from auth middleware, set later
        _user_id.set(None)

        # Add correlation ID to response headers
        original_send = send

        async def send_with_correlation(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-correlation-id", correlation_id.encode()))
                message["headers"] = headers
            await original_send(message)

        await self.app(scope, receive, send_with_correlation)


def add_api_tracking_middleware(
    app: FastAPI,
    tracker: ApiTracker | None = None,
) -> None:
    """
    Add API tracking middleware to a FastAPI app.

    Args:
        app: FastAPI application
        tracker: Optional ApiTracker instance
    """
    # Add as raw ASGI middleware for better control
    app.add_middleware(ApiTrackingMiddleware, tracker=tracker)


# =============================================================================
# Starlette BaseHTTPMiddleware version (alternative)
# =============================================================================


def create_correlation_middleware(tracker: ApiTracker | None = None) -> type:
    """
    Create a Starlette BaseHTTPMiddleware for correlation tracking.

    Returns:
        Middleware class

    Usage:
        app.add_middleware(create_correlation_middleware(tracker))
    """
    from starlette.middleware.base import BaseHTTPMiddleware

    class CorrelationMiddleware(BaseHTTPMiddleware):
        async def dispatch(
            self,
            request: Request,
            call_next: RequestResponseEndpoint,
        ) -> Response:
            # Set correlation ID
            correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
            _correlation_id.set(correlation_id)

            # Set tenant ID
            tenant_id = request.headers.get("X-Tenant-ID")
            _tenant_id.set(tenant_id)

            # Set user ID if available from state (set by auth middleware)
            user = getattr(request.state, "user", None)
            if user:
                _user_id.set(getattr(user, "id", None))

            # Process request
            response = await call_next(request)

            # Add correlation ID to response
            response.headers["X-Correlation-ID"] = correlation_id

            return response

    return CorrelationMiddleware


# =============================================================================
# Tracked Client Factory
# =============================================================================


def create_tracked_client(
    tracker: ApiTracker,
    service_name: str,
    base_url: str = "",
    **httpx_kwargs: Any,
) -> Any:
    """
    Create a tracked HTTP client with automatic context.

    The client automatically picks up tenant_id from the current
    request context.

    Args:
        tracker: ApiTracker instance
        service_name: Name of the external service
        base_url: Base URL for the service
        **httpx_kwargs: Additional kwargs for httpx.AsyncClient

    Returns:
        TrackedHttpxClient with automatic context
    """
    from dazzle_back.runtime.api_tracker import TrackedHttpxClient

    class ContextAwareTrackedClient(TrackedHttpxClient):
        """TrackedHttpxClient that uses request context."""

        async def request(self, method: str, url: str, **kwargs: Any) -> Any:
            # Override tenant_id with current context
            self.tenant_id = get_tenant_id()
            return await super().request(method, url, **kwargs)

    return ContextAwareTrackedClient(
        tracker=tracker,
        service_name=service_name,
        base_url=base_url,
        **httpx_kwargs,
    )
