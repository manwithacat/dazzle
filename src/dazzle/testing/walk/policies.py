"""Request policies for walk HTTP clients (#1639 CSRF / CyFuture requirements).

CSRF is the first built-in policy: cookie ``dazzle_csrf`` → header
``X-CSRF-Token`` on mutations. Mirrors ``dazzle.testing.test_runner`` and
``dazzle.testing.ux.htmx_client``.
"""

from __future__ import annotations

import logging
from typing import Final

import httpx

logger = logging.getLogger(__name__)

CSRF_COOKIE: Final = "dazzle_csrf"
CSRF_HEADER: Final = "X-CSRF-Token"
MUTATING_METHODS: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})


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


def attach_csrf_request_hook(client: httpx.AsyncClient) -> None:
    """Register an httpx request hook that injects CSRF on mutating methods.

    Idempotent if called once per client. Reads the live cookie jar so
    Set-Cookie rotation is respected (R1.3).
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


def cookies_for_playwright(client: httpx.AsyncClient, base_url: str) -> list[dict[str, str]]:
    """Export session + CSRF cookies for Playwright context (R4.1)."""
    out: list[dict[str, str]] = []
    for name in ("dazzle_session", CSRF_COOKIE):
        val = client.cookies.get(name)
        if val:
            out.append({"name": name, "value": val, "url": base_url.rstrip("/")})
    return out
