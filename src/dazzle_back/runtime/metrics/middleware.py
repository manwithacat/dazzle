"""
FastAPI Middleware for automatic HTTP metrics collection.

Automatically tracks:
- Request count (http_requests_total)
- Request latency (http_latency_ms)
- Error count (http_errors_total)
"""

from __future__ import annotations

import re
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .emitter import get_emitter

if TYPE_CHECKING:
    from starlette.types import ASGIApp

# Type alias for the call_next function
RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware that automatically collects HTTP metrics.

    Emits metrics to Redis streams via the MetricsEmitter.
    Zero-overhead if REDIS_URL is not configured.
    """

    def __init__(
        self,
        app: ASGIApp,
        exclude_paths: list[str] | None = None,
    ):
        """
        Initialize the middleware.

        Args:
            app: ASGI application
            exclude_paths: Paths to exclude from metrics (e.g., /health)
        """
        super().__init__(app)
        self._exclude_paths = set(exclude_paths or ["/health", "/metrics", "/favicon.ico"])

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request and emit metrics."""
        # Skip excluded paths
        if request.url.path in self._exclude_paths:
            response: Response = await call_next(request)
            return response

        emitter = get_emitter()
        if not emitter:
            # No metrics configured, pass through
            response = await call_next(request)
            return response

        # Collect request info
        method = request.method
        path = self._normalize_path(request.url.path)

        # Time the request
        start_time = time.perf_counter()
        status_code = 500  # Default in case of unhandled exception

        try:
            tracked_response: Response = await call_next(request)
            status_code = tracked_response.status_code
            return tracked_response
        finally:
            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Common tags
            tags = {
                "method": method,
                "path": path,
                "status": str(status_code),
            }

            # Emit metrics
            emitter.increment("http_requests_total", tags)
            emitter.timing("http_latency_ms", duration_ms, tags)

            # Track errors separately for easier alerting
            if status_code >= 400:
                error_tags = {
                    "method": method,
                    "path": path,
                    "status": str(status_code),
                    "error_class": "client" if status_code < 500 else "server",
                }
                emitter.increment("http_errors_total", error_tags)

    def _normalize_path(self, path: str) -> str:
        """
        Normalize path for consistent metric grouping.

        Replaces dynamic path segments (UUIDs, IDs) with placeholders
        to avoid metric cardinality explosion.
        """
        # Replace UUIDs
        path = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            ":id",
            path,
            flags=re.IGNORECASE,
        )

        # Replace numeric IDs
        path = re.sub(r"/\d+(?=/|$)", "/:id", path)

        return path


def add_metrics_middleware(app: Any, exclude_paths: list[str] | None = None) -> None:
    """
    Add metrics middleware to a FastAPI/Starlette app.

    Usage:
        from dazzle_back.runtime.metrics import add_metrics_middleware
        add_metrics_middleware(app)
    """
    default_excludes = [
        "/health",
        "/metrics",
        "/favicon.ico",
        "/_dazzle",
        "/__test__",
    ]
    app.add_middleware(
        MetricsMiddleware,
        exclude_paths=exclude_paths or default_excludes,
    )
