"""
CSRF protection for Dazzle Backend applications.

Implements the double-submit cookie pattern:
- Sets a `dazzle_csrf` cookie (httponly=False so JS can read it)
- On state-changing requests (POST/PUT/DELETE/PATCH), validates that the
  `X-CSRF-Token` header matches the cookie value
- Exempts Bearer-authenticated requests (JWT already proves non-CSRF)
- Exempts configured paths (health, docs, webhooks)
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


@dataclass
class CSRFConfig:
    """CSRF protection configuration."""

    enabled: bool = False
    cookie_name: str = "dazzle_csrf"
    header_name: str = "X-CSRF-Token"
    token_length: int = 32
    exempt_paths: list[str] = field(
        default_factory=lambda: ["/health", "/docs", "/openapi.json", "/redoc"]
    )
    exempt_path_prefixes: list[str] = field(
        default_factory=lambda: ["/webhooks/", "/api/v1/webhooks/"]
    )


def configure_csrf_for_profile(profile: str) -> CSRFConfig:
    """Get CSRF configuration based on security profile.

    Args:
        profile: Security profile (basic, standard, strict)

    Returns:
        CSRFConfig for the profile
    """
    if profile == "basic":
        return CSRFConfig(enabled=False)
    else:  # standard or strict
        return CSRFConfig(enabled=True)


def create_csrf_middleware(config: CSRFConfig) -> Any:
    """Create a Starlette middleware class implementing double-submit cookie CSRF.

    Args:
        config: CSRF configuration

    Returns:
        Starlette middleware class
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response

    class CSRFMiddleware(BaseHTTPMiddleware):
        """Double-submit cookie CSRF protection."""

        async def dispatch(self, request: Request, call_next: Any) -> Response:
            # Always ensure the CSRF cookie is set
            csrf_token = request.cookies.get(config.cookie_name)
            new_token = None
            if not csrf_token:
                new_token = secrets.token_hex(config.token_length)
                csrf_token = new_token

            # Safe methods don't need validation
            if request.method in SAFE_METHODS:
                response = await call_next(request)
                if new_token:
                    response.set_cookie(
                        key=config.cookie_name,
                        value=new_token,
                        httponly=False,  # JS must read this
                        samesite="lax",
                        secure=request.url.scheme == "https",
                    )
                return response  # type: ignore[no-any-return]

            # Check exemptions before validating
            path = request.url.path
            if path in config.exempt_paths:
                response = await call_next(request)
                if new_token:
                    response.set_cookie(
                        key=config.cookie_name,
                        value=new_token,
                        httponly=False,
                        samesite="lax",
                        secure=request.url.scheme == "https",
                    )
                return response  # type: ignore[no-any-return]

            for prefix in config.exempt_path_prefixes:
                if path.startswith(prefix):
                    response = await call_next(request)
                    if new_token:
                        response.set_cookie(
                            key=config.cookie_name,
                            value=new_token,
                            httponly=False,
                            samesite="lax",
                            secure=request.url.scheme == "https",
                        )
                    return response  # type: ignore[no-any-return]

            # Bearer-authenticated requests are exempt (JWT proves non-CSRF)
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                response = await call_next(request)
                if new_token:
                    response.set_cookie(
                        key=config.cookie_name,
                        value=new_token,
                        httponly=False,
                        samesite="lax",
                        secure=request.url.scheme == "https",
                    )
                return response  # type: ignore[no-any-return]

            # Validate CSRF token
            header_token = request.headers.get(config.header_name)
            if not header_token or not csrf_token or header_token != csrf_token:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token missing or invalid"},
                )

            response = await call_next(request)
            if new_token:
                response.set_cookie(
                    key=config.cookie_name,
                    value=new_token,
                    httponly=False,
                    samesite="lax",
                    secure=request.url.scheme == "https",
                )
            return response  # type: ignore[no-any-return]

    return CSRFMiddleware


def apply_csrf_protection(app: FastAPI, profile: str) -> None:
    """Apply CSRF protection middleware to a FastAPI application.

    Args:
        app: FastAPI application instance
        profile: Security profile (basic, standard, strict)
    """
    config = configure_csrf_for_profile(profile)
    app.state.csrf_config = config

    if not config.enabled:
        return

    CSRFMiddleware = create_csrf_middleware(config)
    app.add_middleware(CSRFMiddleware)

    logger.info("CSRF protection enabled (profile=%s)", profile)
