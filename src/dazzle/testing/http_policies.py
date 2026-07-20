"""Shared HTTP request policies for Dazzle testing clients.

CSRF is the first built-in policy: cookie ``dazzle_csrf`` → header
``X-CSRF-Token`` on mutations. Single home for walk runner, ``test_runner``,
``ux.htmx_client``, and the RBAC verification harness so double-submit
behaviour stays consistent (#1639 CyFuture requirements + reuse).
"""

from __future__ import annotations

import logging
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)

CSRF_COOKIE: Final = "dazzle_csrf"
CSRF_HEADER: Final = "X-CSRF-Token"
SESSION_COOKIE: Final = "dazzle_session"
MUTATING_METHODS: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def csrf_token_from_client(client: Any) -> str | None:
    """Read ``dazzle_csrf`` from an httpx client cookie jar (sync or async)."""
    token = client.cookies.get(CSRF_COOKIE)
    if token is None:
        return None
    return str(token)


def csrf_headers(client: Any) -> dict[str, str]:
    """Return ``{X-CSRF-Token: token}`` when the cookie is present, else ``{}``."""
    token = csrf_token_from_client(client)
    return {CSRF_HEADER: token} if token else {}


def inject_csrf_headers(
    method: str,
    headers: dict[str, str] | None,
    client: Any,
) -> dict[str, str]:
    """Copy *headers* and setdefault CSRF on mutating methods from the jar.

    Does not overwrite an explicit caller header. Safe to call for GET —
    returns a copy of *headers* (or ``{}``) unchanged.
    """
    out = dict(headers or {})
    if method.upper() not in MUTATING_METHODS:
        return out
    token = csrf_token_from_client(client)
    if token:
        out.setdefault(CSRF_HEADER, token)
    return out


def extract_csrf_from_set_cookie(set_cookie_headers: list[str]) -> str:
    """Parse ``dazzle_csrf`` value from raw Set-Cookie header strings."""
    prefix = f"{CSRF_COOKIE}="
    for cookie_header in set_cookie_headers:
        if prefix in cookie_header:
            return cookie_header.split(prefix, 1)[1].split(";", 1)[0]
    return ""


async def prime_csrf_cookie(client: httpx.AsyncClient, base_url: str) -> str | None:
    """Ensure ``dazzle_csrf`` is in the cookie jar; GET /health if missing.

    Returns the token value (or None if still absent). Does not log the token
    at INFO (R5.1).
    """
    existing = client.cookies.get(CSRF_COOKIE)
    if existing:
        return existing
    try:
        await client.get(f"{base_url.rstrip('/')}/health")
    except Exception:
        logger.debug("CSRF priming health-check failed", exc_info=True)
    token = client.cookies.get(CSRF_COOKIE)
    if token:
        logger.debug("CSRF cookie primed via GET /health")
    return token


def prime_csrf_cookie_sync(client: httpx.Client, base_url: str) -> str | None:
    """Sync counterpart of :func:`prime_csrf_cookie` for ``httpx.Client``."""
    existing = client.cookies.get(CSRF_COOKIE)
    if existing:
        return existing
    try:
        client.get(f"{base_url.rstrip('/')}/health")
    except Exception:
        logger.debug("CSRF priming health-check failed", exc_info=True)
    token = client.cookies.get(CSRF_COOKIE)
    if token:
        logger.debug("CSRF cookie primed via GET /health")
    return token


def attach_csrf_request_hook(client: httpx.AsyncClient) -> None:
    """Register an httpx request hook that injects CSRF on mutating methods.

    Async hook required by ``httpx.AsyncClient`` (request hooks are awaited).
    For sync ``httpx.Client`` callers, use :func:`inject_csrf_headers` or
    :func:`prime_csrf_cookie_sync` instead. Idempotent if called once per
    client. Reads the live cookie jar so Set-Cookie rotation is respected
    (R1.3).
    """

    async def _on_request(request: httpx.Request) -> None:
        if request.method.upper() not in MUTATING_METHODS:
            return
        token = client.cookies.get(CSRF_COOKIE)
        if not token:
            return
        # Do not overwrite an explicit caller header
        if CSRF_HEADER in request.headers:
            return
        request.headers[CSRF_HEADER] = token

    hooks = client.event_hooks.setdefault("request", [])
    # Avoid double-attach
    if any(getattr(h, "__name__", "") == "_on_request" for h in hooks):
        return
    hooks.append(_on_request)


def cookies_for_playwright(
    client: httpx.AsyncClient | httpx.Client, base_url: str
) -> list[dict[str, str]]:
    """Export session + CSRF cookies for Playwright context (R4.1)."""
    out: list[dict[str, str]] = []
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        val = client.cookies.get(name)
        if val:
            out.append({"name": name, "value": val, "url": base_url.rstrip("/")})
    return out
