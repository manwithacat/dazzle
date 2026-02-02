"""
Security middleware for DNR-Back applications.

Provides configurable security based on security profile:
- Security headers (X-Frame-Options, X-Content-Type-Options, HSTS, CSP)
- CORS configuration
- Request origin validation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI


# =============================================================================
# Security Headers Configuration
# =============================================================================


@dataclass
class SecurityHeadersConfig:
    """
    Configuration for security headers.

    Attributes:
        enable_hsts: Enable HTTP Strict Transport Security
        hsts_max_age: HSTS max-age in seconds (default: 1 year)
        enable_csp: Enable Content Security Policy
        csp_directives: Custom CSP directives (uses secure defaults if None)
        x_frame_options: X-Frame-Options value (DENY, SAMEORIGIN, or None)
        x_content_type_options: Whether to enable X-Content-Type-Options: nosniff
        x_xss_protection: X-XSS-Protection value (deprecated but still useful)
        referrer_policy: Referrer-Policy header value
    """

    enable_hsts: bool = False
    hsts_max_age: int = 31536000  # 1 year
    enable_csp: bool = False
    csp_directives: dict[str, str] | None = None
    x_frame_options: str = "DENY"
    x_content_type_options: bool = True
    x_xss_protection: str = "1; mode=block"
    referrer_policy: str = "strict-origin-when-cross-origin"


def _build_csp_header(directives: dict[str, str] | None) -> str:
    """
    Build Content-Security-Policy header value.

    Args:
        directives: Custom directives or None for defaults

    Returns:
        CSP header string
    """
    # Secure defaults that work for most apps
    default_directives = {
        "default-src": "'self'",
        "script-src": "'self' 'unsafe-inline'",  # Needed for inline event handlers
        "style-src": "'self' 'unsafe-inline'",  # Needed for inline styles
        "img-src": "'self' data: blob:",
        "font-src": "'self'",
        "connect-src": "'self'",
        "frame-ancestors": "'none'",
        "form-action": "'self'",
        "base-uri": "'self'",
    }

    if directives:
        default_directives.update(directives)

    return "; ".join(f"{k} {v}" for k, v in default_directives.items())


# =============================================================================
# CORS Configuration
# =============================================================================


@dataclass
class CORSConfig:
    """
    CORS configuration.

    Attributes:
        allow_origins: List of allowed origins, or ["*"] for all
        allow_credentials: Whether to allow credentials (cookies, auth headers)
        allow_methods: Allowed HTTP methods
        allow_headers: Allowed request headers
        expose_headers: Headers to expose to browser
        max_age: Preflight cache time in seconds
    """

    allow_origins: list[str] | None = None
    allow_credentials: bool = True
    allow_methods: list[str] | None = None
    allow_headers: list[str] | None = None
    expose_headers: list[str] | None = None
    max_age: int = 600  # 10 minutes


def configure_cors_for_profile(profile: str, custom_origins: list[str] | None = None) -> CORSConfig:
    """
    Get CORS configuration based on security profile.

    Args:
        profile: Security profile (basic, standard, strict)
        custom_origins: Custom origins to override profile defaults

    Returns:
        CORSConfig for the profile
    """
    if profile == "basic":
        # Permissive CORS for development/internal tools
        return CORSConfig(
            allow_origins=custom_origins or ["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    elif profile == "standard":
        # Reasonable defaults for standard apps
        # Same-origin by default, but allow customization
        return CORSConfig(
            allow_origins=custom_origins,  # None = same-origin only in production
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Tenant-ID"],
        )
    else:  # strict
        # Restrictive CORS for multi-tenant SaaS
        return CORSConfig(
            allow_origins=custom_origins,  # Must be explicitly configured
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Tenant-ID"],
            expose_headers=["X-Request-ID"],
        )


def configure_headers_for_profile(profile: str) -> SecurityHeadersConfig:
    """
    Get security headers configuration based on security profile.

    Args:
        profile: Security profile (basic, standard, strict)

    Returns:
        SecurityHeadersConfig for the profile
    """
    if profile == "basic":
        # Minimal headers for internal tools
        return SecurityHeadersConfig(
            enable_hsts=False,
            enable_csp=False,
            x_frame_options="SAMEORIGIN",
        )
    elif profile == "standard":
        # Standard security headers
        return SecurityHeadersConfig(
            enable_hsts=True,
            enable_csp=False,  # CSP can break many apps
            x_frame_options="DENY",
        )
    else:  # strict
        # Full security headers
        return SecurityHeadersConfig(
            enable_hsts=True,
            enable_csp=True,
            x_frame_options="DENY",
        )


# =============================================================================
# Middleware Application
# =============================================================================


def create_security_headers_middleware(config: SecurityHeadersConfig) -> Any:
    """
    Create a middleware that adds security headers to responses.

    Args:
        config: Security headers configuration

    Returns:
        Starlette middleware class
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        """Middleware to add security headers to all responses."""

        async def dispatch(self, request: Request, call_next: Any) -> Response:
            response = await call_next(request)

            # X-Frame-Options - prevent clickjacking
            if config.x_frame_options:
                response.headers["X-Frame-Options"] = config.x_frame_options

            # X-Content-Type-Options - prevent MIME sniffing
            if config.x_content_type_options:
                response.headers["X-Content-Type-Options"] = "nosniff"

            # X-XSS-Protection - legacy but still helps
            if config.x_xss_protection:
                response.headers["X-XSS-Protection"] = config.x_xss_protection

            # Referrer-Policy
            if config.referrer_policy:
                response.headers["Referrer-Policy"] = config.referrer_policy

            # HSTS - only in production (HTTPS)
            if config.enable_hsts:
                response.headers["Strict-Transport-Security"] = (
                    f"max-age={config.hsts_max_age}; includeSubDomains"
                )

            # CSP - Content Security Policy
            if config.enable_csp:
                response.headers["Content-Security-Policy"] = _build_csp_header(
                    config.csp_directives
                )

            return response  # type: ignore[no-any-return]

    return SecurityHeadersMiddleware


def apply_security_middleware(
    app: FastAPI,
    security_profile: str,
    cors_origins: list[str] | None = None,
    enable_headers: bool = True,
) -> None:
    """
    Apply security middleware stack to a FastAPI application.

    This replaces the default permissive CORS with profile-based security.

    Args:
        app: FastAPI application instance
        security_profile: Security profile (basic, standard, strict)
        cors_origins: Custom CORS origins (overrides profile defaults)
        enable_headers: Whether to enable security headers middleware
    """
    from fastapi.middleware.cors import CORSMiddleware

    # Get configurations for the profile
    cors_config = configure_cors_for_profile(security_profile, cors_origins)
    headers_config = configure_headers_for_profile(security_profile)

    # Apply CORS middleware
    # For "basic" profile with ["*"] origins, use permissive settings
    origins = cors_config.allow_origins
    if origins == ["*"]:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=cors_config.allow_credentials,
            allow_methods=cors_config.allow_methods or ["*"],
            allow_headers=cors_config.allow_headers or ["*"],
        )
    elif origins:
        # Specific origins
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=cors_config.allow_credentials,
            allow_methods=cors_config.allow_methods or ["*"],
            allow_headers=cors_config.allow_headers or ["*"],
            expose_headers=cors_config.expose_headers or [],
            max_age=cors_config.max_age,
        )
    # If origins is None/empty, skip CORS (same-origin only)

    # Apply security headers middleware
    if enable_headers and security_profile != "basic":
        SecurityHeadersMiddleware = create_security_headers_middleware(headers_config)
        app.add_middleware(SecurityHeadersMiddleware)
