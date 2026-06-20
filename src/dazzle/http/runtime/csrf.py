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
from enum import StrEnum
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


class Disposition(StrEnum):
    """How a state-changing request relates to CSRF (spec §4.1).

    CSRF is a control on *ambient authority* (the session cookie). A request
    authenticated by a caller-presented credential is structurally immune, so it
    derives an ``NA_*`` disposition rather than being CSRF-validated.

    NOTE: ``UNAUTH_MUTATING`` and ``ESCAPE_HATCH`` are defined for completeness
    but are NOT produced by ``csrf_disposition`` in this phase — they require
    request-time session-presence detection and the DSL escape-hatch knob, which
    land in Phase 4. The classifier currently returns only the other four.
    """

    PROTECTED_SESSION = "protected_session"
    NA_BEARER = "na_bearer"
    NA_SIGNATURE = "na_signature"
    NA_PREAUTH = "na_preauth"
    UNAUTH_MUTATING = "unauth_mutating"
    ESCAPE_HATCH = "escape_hatch"


@dataclass
class CSRFConfig:
    """CSRF protection configuration."""

    enabled: bool = False
    cookie_name: str = "dazzle_csrf"
    header_name: str = "X-CSRF-Token"
    token_length: int = 32
    # Pre-auth exempt surface (spec §4.1 NA_PREAUTH). Unlike the
    # disposition-named ``na_signature_*`` fields below, ``exempt_paths`` /
    # ``exempt_path_prefixes`` keep their generic names because they are the
    # pre-existing app-facing config surface; ``csrf_disposition`` derives
    # NA_PREAUTH from them.
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
    # Anchored overrides that force PROTECTED_SESSION even when a path would
    # otherwise match an exempt prefix above (auth Plan 1b). The org-context
    # POSTs live under `/auth/` for cohesion with the login views, but unlike the
    # rest of `/auth/` (pre-session cookie-setters) they are authenticated,
    # non-idempotent, privilege-changing mutations — they rotate the session's
    # active org (`active_membership_id`), which moves the RLS fence + role set.
    # They must run the full origin-primary CSRF gate, not inherit NA_PREAUTH.
    # Exact-match (not prefix) so nothing deeper silently joins the override.
    protected_paths: list[str] = field(
        default_factory=lambda: [
            "/auth/select-org",
            "/auth/switch-org",
            # auth Plan 3a: authenticated org-member-management POSTs under /auth/
            # must run the CSRF gate (else swept into NA_PREAUTH by the /auth/ prefix).
            "/auth/invite",
            "/auth/accept-invite",
            # auth Plan 3b: member-admin mutations (membership_id in the query).
            "/auth/members/roles",
            "/auth/members/suspend",
            "/auth/members/reactivate",
            "/auth/members/remove",
            # auth Plan 3c.ii: the member's own profile upsert.
            "/me/profile",
            # org-admin connection surface: authenticated domain-management mutations
            # (NOT the cross-origin SAML ACS — those stay NA_PREAUTH under /auth/).
            "/auth/connections/add-domain",
            "/auth/connections/verify-domain",
            "/auth/connections/create",
        ]
    )
    # Signature-authenticated endpoints (spec §4.1 NA_SIGNATURE). The HMAC /
    # shared-secret signature IS the control; CSRF is categorically N/A. Moved
    # out of the generic exempt lists so the disposition is explicit + auditable.
    na_signature_prefixes: list[str] = field(
        default_factory=lambda: ["/webhooks/", "/api/v1/webhooks/"]
    )
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
    # The /resend subpath (TR-53) carries the same expired HMAC token in
    # its form body as its credential — CSRF double-submit is just as
    # redundant here as on the sign routes. Anchored to the UUID tail so
    # only the exact recovery route inherits the exemption.
    na_signature_regexes: list[str] = field(
        default_factory=lambda: [
            r"^/sign/[^/]+/" + _UUID_RE + r"$",
            r"^/sign/[^/]+/" + _UUID_RE + r"/resend$",
            r"^/api/sign/[^/]+/" + _UUID_RE + r"$",
        ]
    )
    # Phase 2 (declarative CSRF §4.2): origins to admit even when they don't
    # match the request Host (e.g. a same-site embedder). Same-origin requests
    # never need to be listed — they pass via the Origin==Host check. Empty by
    # default: a vanilla app admits only its own origin.
    trusted_origins: list[str] = field(default_factory=list)


def configure_csrf_for_profile(
    profile: str,
    extra_exempt_paths: list[str] | None = None,
    extra_trusted_origins: list[str] | None = None,
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
        extra_trusted_origins: Optional list of additional origins to admit
            even when they don't match the request Host (spec §4.2). Merged
            with the (empty) default ``trusted_origins``; duplicates are
            silently de-duplicated. Use this from a downstream app's
            ``ServerConfig.csrf_trusted_origins`` to admit a same-site
            embedder without mutating ``app.state.csrf_config`` after boot.
    """
    config = CSRFConfig(enabled=True)
    if extra_exempt_paths:
        for path in extra_exempt_paths:
            if path not in config.exempt_paths:
                config.exempt_paths.append(path)
    if extra_trusted_origins:
        for origin in extra_trusted_origins:
            if origin not in config.trusted_origins:
                config.trusted_origins.append(origin)
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


def _origin_host(origin: str) -> str | None:
    """Return the host[:port] authority of an Origin header, or None.

    `Origin` is `scheme://host[:port]`. Returns None for the opaque value
    "null" (sandboxed iframe / some privacy modes) so it never matches a Host.
    """
    if not origin or origin == "null":
        return None
    after_scheme = origin.split("://", 1)[-1]
    return after_scheme.split("/", 1)[0] or None


def origin_disposition(
    headers: list[tuple[bytes, bytes]],
    host: str | None,
    config: CSRFConfig,
) -> bool | None:
    """Decide admission from the request's origin signals (spec §4.2).

    Returns:
        True  — admit (same-origin / trusted).
        False — reject (provably cross-site / same-site / mismatched origin).
        None  — no origin signal at all; caller should fall back to the token.
    """
    trusted = set(config.trusted_origins)
    sec_fetch_site = _get_header(headers, b"sec-fetch-site")
    origin = _get_header(headers, b"origin")
    origin_host = _origin_host(origin) if origin else None

    if sec_fetch_site is not None:
        if sec_fetch_site in ("same-origin", "none"):
            return True
        if origin and origin in trusted:
            return True
        return False

    if origin is not None:
        if origin in trusted:
            return True
        if origin_host is not None and host is not None and origin_host == host:
            return True
        return False

    return None


def csrf_disposition(
    method: str,
    path: str,
    headers: list[tuple[bytes, bytes]],
    config: CSRFConfig,
    *,
    signature_regexes: list[Any] | None = None,
) -> Disposition:
    """Classify a request's CSRF disposition from its auth-class signals (§4.1).

    Returns NA_BEARER / NA_SIGNATURE / NA_PREAUTH / PROTECTED_SESSION.
    (UNAUTH_MUTATING / ESCAPE_HATCH are Phase 4 — see the enum.) Default-deny:
    anything not positively classified NA_* is PROTECTED_SESSION.

    ``signature_regexes`` accepts the middleware's precompiled patterns; when
    None it compiles from ``config.na_signature_regexes``.

    ``method`` is currently unread; it is the classification signal for the
    Phase-4 ``UNAUTH_MUTATING`` disposition (see the enum).
    """
    auth = _get_header(headers, b"authorization") or ""
    if auth.startswith("Bearer "):
        return Disposition.NA_BEARER

    for prefix in config.na_signature_prefixes:
        if path.startswith(prefix):
            return Disposition.NA_SIGNATURE
    sig_res = signature_regexes
    if sig_res is None:
        sig_res = [re.compile(p) for p in config.na_signature_regexes]
    for pattern in sig_res:
        if pattern.fullmatch(path):
            return Disposition.NA_SIGNATURE

    # Anchored protected-overrides win over the exempt prefixes below, so an
    # authenticated privilege-changing route under an otherwise-exempt prefix
    # (e.g. POST /auth/switch-org under /auth/) is not swept into NA_PREAUTH.
    if path in config.protected_paths:
        return Disposition.PROTECTED_SESSION

    if path in config.exempt_paths:
        return Disposition.NA_PREAUTH
    for prefix in config.exempt_path_prefixes:
        if path.startswith(prefix):
            return Disposition.NA_PREAUTH

    return Disposition.PROTECTED_SESSION


def csrf_admits(
    disposition: Disposition,
    headers: list[tuple[bytes, bytes]],
    host: str | None,
    csrf_cookie: str | None,
    config: CSRFConfig,
) -> bool:
    """Decide admission for a classified request (spec §4.2/§4.5).

    NA_* / ESCAPE_HATCH / UNAUTH_MUTATING admit. PROTECTED_SESSION runs the
    origin-primary gate (Phase 2) with the double-submit token as fallback.
    """
    if disposition is not Disposition.PROTECTED_SESSION:
        return True

    verdict = origin_disposition(headers, host, config)
    if verdict is True:
        return True
    if verdict is False:
        return False
    header_token = _get_header(headers, config.header_name.lower().encode())
    return bool(header_token and csrf_cookie and header_token == csrf_cookie)


def render_csrf_policy(config: CSRFConfig) -> list[str]:
    """Render the CSRF disposition policy as Markdown lines for the audit report.

    Lists every exemption rule with its derived disposition and rationale, so an
    agent/auditor can see WHAT is exempt from CSRF and WHY — rather than
    inferring protection from absence (spec §6).
    """
    if not config.enabled:
        return ["## CSRF Policy", "", "> CSRF protection is **disabled**.", ""]

    def _cell(value: str) -> str:
        # Escape Markdown table-cell delimiters so regex alternations (the
        # UUID-anchored sign patterns contain `|`) don't break the table.
        return value.replace("\\", "\\\\").replace("|", "\\|").replace("`", "\\`")

    lines = [
        "## CSRF Policy",
        "",
        "State-changing requests default to **PROTECTED_SESSION** (origin-primary "
        "gate + session-bound double-submit token). The rules below derive a "
        "non-protected disposition because the request is authenticated by a "
        "caller-presented credential, so CSRF is categorically N/A:",
        "",
        "> Reflects the framework-default policy for the resolved config. "
        "App-registered extras (`ServerConfig.csrf_exempt_paths` / "
        "`csrf_trusted_origins`, set programmatically) appear only when the live "
        "config is passed in.",
        "",
        "| Rule | Match | Disposition |",
        "| --- | --- | --- |",
    ]
    for path in config.protected_paths:
        lines.append(f"| `{_cell(path)}` | exact | PROTECTED_SESSION (override) |")
    for prefix in config.na_signature_prefixes:
        lines.append(f"| `{_cell(prefix)}` | prefix | NA_SIGNATURE |")
    for rx in config.na_signature_regexes:
        lines.append(f"| `{_cell(rx)}` | regex | NA_SIGNATURE |")
    for path in config.exempt_paths:
        lines.append(f"| `{_cell(path)}` | exact | NA_PREAUTH |")
    for prefix in config.exempt_path_prefixes:
        lines.append(f"| `{_cell(prefix)}` | prefix | NA_PREAUTH |")
    if config.trusted_origins:
        lines.append("")
        lines.append("Trusted cross-origin embedders (admitted despite Host mismatch):")
        for origin in config.trusted_origins:
            lines.append(f"- `{_cell(origin)}`")
    lines.append("")
    return lines


class CSRFMiddleware:
    """Pure ASGI middleware for double-submit cookie CSRF protection.

    Uses raw ASGI interface to avoid the body consumption issues of
    Starlette's BaseHTTPMiddleware.
    """

    def __init__(self, app: Any, config: CSRFConfig) -> None:
        self.app = app
        self.config = config
        # Precompile NA_SIGNATURE regexes once at mount time; matched on the
        # hot path for every state-changing request.
        self._na_signature_regexes = [
            re.compile(pattern) for pattern in config.na_signature_regexes
        ]

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

        # Classify + admit via the disposition predicate (spec §4.1/§4.5). This
        # consolidates the former exact/prefix/regex exemptions, the Bearer
        # check, the Phase-2 origin gate, and the double-submit token check into
        # one predicate (which a later phase's compliance report will enumerate).
        disposition = csrf_disposition(
            scope.get("method", "GET"),
            path,
            headers,
            self.config,
            signature_regexes=self._na_signature_regexes,
        )
        host = _get_header(headers, b"host")
        if csrf_admits(disposition, headers, host, csrf_token, self.config):
            await self._pass_through(scope, receive, send, new_token)
            return
        await self._send_403(send)
        return

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
    app: Any,
    profile: str,
    extra_exempt_paths: list[str] | None = None,
    extra_trusted_origins: list[str] | None = None,
) -> None:
    """Apply CSRF protection middleware to a FastAPI application.

    Args:
        app: The FastAPI application.
        profile: Security profile name (``basic``/``standard``/``strict``).
        extra_exempt_paths: Optional list of additional exact paths to mark as
            CSRF-exempt. See :func:`configure_csrf_for_profile` (#1212).
        extra_trusted_origins: Optional list of additional origins to admit.
            See :func:`configure_csrf_for_profile`.
    """
    config = configure_csrf_for_profile(
        profile,
        extra_exempt_paths=extra_exempt_paths,
        extra_trusted_origins=extra_trusted_origins,
    )
    app.state.csrf_config = config

    if not config.enabled:
        return

    # Register as raw ASGI middleware via Starlette's add_middleware.
    # The 'config' kwarg is passed to CSRFMiddleware.__init__.
    app.add_middleware(CSRFMiddleware, config=config)

    logger.info("CSRF protection enabled (profile=%s)", profile)
