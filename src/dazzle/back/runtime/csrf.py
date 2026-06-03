"""
CSRF protection for Dazzle Backend applications.

Implements the double-submit cookie pattern using a pure ASGI middleware
(not BaseHTTPMiddleware, which has body consumption issues):
- Sets a `dazzle_csrf` cookie (httponly=False so JS can read it)
- On state-changing requests (POST/PUT/DELETE/PATCH), validates that the
  `X-CSRF-Token` header matches the cookie value
- Exempts Bearer-authenticated requests (JWT already proves non-CSRF)
- Exempts configured paths (health, docs, webhooks, auth, test)
"""

from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

SAFE_METHODS = frozenset({b"GET", b"HEAD", b"OPTIONS", b"TRACE"})

# UUID shapes used to anchor the signing-route CSRF exemption to the route's
# ``record_id: UUID`` path param (#1284). Both the canonical hyphenated
# 8-4-4-4-12 form and the 32-char no-hyphen form are matched, because
# Pydantic's ``UUID`` validator (which backs FastAPI path params) accepts both
# — a hyphen-only anchor would wrongly CSRF-block a legitimate no-hyphen
# submission. The ``urn:`` and brace-wrapped forms ``uuid.UUID`` also accepts
# are not valid URL path segments, so they never reach the middleware.
_UUID_RE = (
    r"(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|[0-9a-fA-F]{32})"
)


@dataclass
class CSRFConfig:
    """CSRF protection configuration."""

    enabled: bool = False
    cookie_name: str = "dazzle_csrf"
    header_name: str = "X-CSRF-Token"
    token_length: int = 32
    exempt_paths: list[str] = field(
        default_factory=lambda: [
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/feedbackreports",
            # v0.61.12 (#868): consent endpoints are idempotent cookie-setters
            # invoked from anon visitors on marketing pages that don't carry
            # a CSRF token (no meta tag, no dazzle_csrf cookie issued to
            # unauthenticated sessions). Blocking them at CSRF makes the
            # banner unusable — buttons click, fetch 403s, banner never
            # dismisses. Same-origin is enforced by the fetch credentials
            # policy on the client side.
            "/_dazzle/consent",
            "/_dazzle/consent/banner",
            "/_dazzle/consent/state",
        ]
    )
    exempt_path_prefixes: list[str] = field(
        default_factory=lambda: [
            "/webhooks/",
            "/api/v1/webhooks/",
            "/__test__/",
            "/dazzle/dev/",
            "/auth/",
            "/feedbackreports/",
            # QA mode magic-link generator (#768). Dev-only — the endpoint
            # is triple-gated by env flags, mount-time check, and request-
            # time check inside the handler. Exempt from CSRF so automated
            # testers (Playwright, curl) can hit it without a session.
            "/qa/",
            # Locale switcher (#955 cycle 6). Same rationale as
            # /_dazzle/consent above: idempotent cookie-setter, no privilege
            # escalation, SameSite=Lax blocks cross-site form posts.
            # The endpoint validates the locale tag against the
            # project's supported_locales allow-list before writing
            # the cookie.
            "/_dazzle/i18n/",
        ]
    )
    exempt_path_regexes: list[str] = field(
        default_factory=lambda: [
            # Native document signing routes (#1283, narrowed in #1284).
            # The HMAC signing token carried in the request (query-param on
            # GET, body on POST) is a stronger per-resource credential than a
            # session CSRF cookie, so CSRF double-submit is redundant here.
            # Both the signing page (GET /sign/<entity>/<id>) and the submit
            # endpoint (POST /api/sign/<entity>/<id>) are exempt;
            # unauthenticated signers never have a session cookie from which a
            # CSRF cookie would be issued.
            #
            # The match is deliberately a regex anchored to the exact route
            # shape — /<sign-or-api-sign>/<entity>/<record_id> where
            # ``record_id`` is a UUID — rather than a broad `startswith`
            # prefix. A future route mounted deeper or with a non-UUID tail —
            # e.g. /api/sign/admin/revoke-all — does NOT silently inherit this
            # exemption, but instead falls back to normal CSRF validation. The
            # UUID anchor mirrors the route's ``record_id: UUID`` path param
            # (a non-UUID tail is unreachable — FastAPI 422s it). Decline is a
            # body flag on the same POST endpoint, not a subpath, so no extra
            # pattern is required.
            r"^/sign/[^/]+/" + _UUID_RE + r"$",
            r"^/api/sign/[^/]+/" + _UUID_RE + r"$",
        ]
    )


def configure_csrf_for_profile(
    profile: str, extra_exempt_paths: list[str] | None = None
) -> CSRFConfig:
    """Get CSRF configuration based on security profile.

    Args:
        profile: Security profile name (``basic``/``standard``/``strict``).
        extra_exempt_paths: Optional list of additional exact paths to mark as
            CSRF-exempt. Merged with the framework defaults; duplicates are
            silently de-duplicated. Use this from a downstream app's
            ``ServerConfig.csrf_exempt_paths`` to register internal POST
            endpoints (e.g. a public-read GraphQL gateway authenticated by
            Bearer) without mutating ``app.state.csrf_config`` after boot
            (#1212).
    """
    config = CSRFConfig(enabled=True)
    if extra_exempt_paths:
        for path in extra_exempt_paths:
            if path not in config.exempt_paths:
                config.exempt_paths.append(path)
    return config


def _parse_cookies(headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
    """Extract cookies from raw ASGI headers."""
    cookies: dict[str, str] = {}
    for key, value in headers:
        if key == b"cookie":
            for chunk in value.decode("latin-1").split("; "):
                if "=" in chunk:
                    k, v = chunk.split("=", 1)
                    cookies[k.strip()] = v.strip()
    return cookies


def _get_header(headers: list[tuple[bytes, bytes]], name: bytes) -> str | None:
    """Get a single header value from raw ASGI headers."""
    for key, value in headers:
        if key == name:
            return value.decode("latin-1")
    return None


class CSRFMiddleware:
    """Pure ASGI middleware for double-submit cookie CSRF protection.

    Uses raw ASGI interface to avoid the body consumption issues of
    Starlette's BaseHTTPMiddleware.
    """

    def __init__(self, app: Any, config: CSRFConfig) -> None:
        self.app = app
        self.config = config
        # Precompile exempt-path regexes once at mount time; matched on the
        # hot path for every state-changing request.
        self._exempt_regexes = [re.compile(pattern) for pattern in config.exempt_path_regexes]

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").encode()
        path: str = scope.get("path", "/")
        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])

        # Parse existing CSRF cookie
        cookies = _parse_cookies(headers)
        csrf_token = cookies.get(self.config.cookie_name)
        new_token: str | None = None
        if not csrf_token:
            new_token = secrets.token_hex(self.config.token_length)
            csrf_token = new_token

        # Safe methods — pass through, set cookie if needed
        if method in SAFE_METHODS:
            await self._pass_through(scope, receive, send, new_token)
            return

        # Check exemptions
        if path in self.config.exempt_paths:
            await self._pass_through(scope, receive, send, new_token)
            return

        for prefix in self.config.exempt_path_prefixes:
            if path.startswith(prefix):
                await self._pass_through(scope, receive, send, new_token)
                return

        for pattern in self._exempt_regexes:
            # fullmatch (not match) so the trailing-anchor intent is structural
            # rather than relying on a load-bearing ``$`` in each pattern.
            if pattern.fullmatch(path):
                await self._pass_through(scope, receive, send, new_token)
                return

        # Bearer auth exempt
        auth = _get_header(headers, b"authorization") or ""
        if auth.startswith("Bearer "):
            await self._pass_through(scope, receive, send, new_token)
            return

        # Validate CSRF token
        header_name_bytes = self.config.header_name.lower().encode()
        header_token = _get_header(headers, header_name_bytes)
        if not header_token or not csrf_token or header_token != csrf_token:
            # Reject — send 403 directly without touching the body
            await self._send_403(send)
            return

        # Valid CSRF — pass through
        await self._pass_through(scope, receive, send, new_token)

    async def _pass_through(
        self, scope: dict[str, Any], receive: Any, send: Any, new_token: str | None
    ) -> None:
        """Forward to the app, injecting Set-Cookie on the response if needed."""
        if not new_token:
            await self.app(scope, receive, send)
            return

        # Wrap send to inject the CSRF cookie into response headers
        scheme = "https" if scope.get("scheme") == "https" else "http"
        cookie_header = self._build_cookie_header(new_token, secure=(scheme == "https"))
        cookie_prefix = (self.config.cookie_name + "=").encode()

        async def send_with_cookie(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                # Defer to a cookie the downstream route already set (e.g. a login
                # route binding dazzle_csrf to the session secret). Browsers keep
                # the last Set-Cookie of a given name, so appending a second one
                # here would clobber the session-bound cookie with a transient
                # middleware-minted token. (#1337 declarative-CSRF Phase 1.)
                already_set = any(
                    key == b"set-cookie" and value.startswith(cookie_prefix)
                    for key, value in headers
                )
                if not already_set:
                    headers.append((b"set-cookie", cookie_header.encode()))
                    message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_cookie)

    def _build_cookie_header(self, token: str, *, secure: bool) -> str:
        """Build a Set-Cookie header value."""
        parts = [
            f"{self.config.cookie_name}={token}",
            "Path=/",
            "SameSite=Lax",
        ]
        if secure:
            parts.append("Secure")
        return "; ".join(parts)

    async def _send_403(self, send: Any) -> None:
        """Send a 403 CSRF rejection response."""
        body = b'{"detail":"CSRF token missing or invalid"}'
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body,
            }
        )


def apply_csrf_protection(
    app: Any, profile: str, extra_exempt_paths: list[str] | None = None
) -> None:
    """Apply CSRF protection middleware to a FastAPI application.

    Args:
        app: The FastAPI application.
        profile: Security profile name (``basic``/``standard``/``strict``).
        extra_exempt_paths: Optional list of additional exact paths to mark as
            CSRF-exempt. See :func:`configure_csrf_for_profile` (#1212).
    """
    config = configure_csrf_for_profile(profile, extra_exempt_paths=extra_exempt_paths)
    app.state.csrf_config = config

    if not config.enabled:
        return

    # Register as raw ASGI middleware via Starlette's add_middleware.
    # The 'config' kwarg is passed to CSRFMiddleware.__init__.
    app.add_middleware(CSRFMiddleware, config=config)

    logger.info("CSRF protection enabled (profile=%s)", profile)
