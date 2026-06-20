"""C1 (#1337 declarative-CSRF Phase 1): the middleware must defer to a route-set
``dazzle_csrf`` cookie.

This branch makes the CSRF token session-bound — login routes set
``dazzle_csrf`` to the server-side session's ``csrf_secret``. The CSRF
middleware mints its own random ``dazzle_csrf`` for any request that arrives
without one (``new_token``). On a fresh login (logout deletes the cookie),
*both* the route and the middleware emit a ``Set-Cookie: dazzle_csrf=...``.
Browsers keep the LAST one of a given name, so the middleware's transient
token would clobber the session-bound cookie — silently defeating the feature
and guaranteeing double-submit 403s in Phase 2.

The fix: ``send_with_cookie`` checks whether the downstream response already
set a cookie named ``config.cookie_name`` and, if so, does NOT append the
middleware's competing one. These tests pin both halves of that contract:
the route cookie survives when present, and the middleware still mints when
the route sets none.
"""

from __future__ import annotations

import asyncio

from dazzle.http.runtime.csrf import CSRFConfig, CSRFMiddleware


async def _drive_collecting_set_cookies(
    config: CSRFConfig,
    *,
    inner_set_cookie: bytes | None,
) -> list[bytes]:
    """Run a GET (no dazzle_csrf cookie) through the middleware and return every
    ``set-cookie`` header value the outer client observes.

    The inner app optionally emits its own ``Set-Cookie`` (simulating a login
    route binding ``dazzle_csrf`` to the session secret).
    """
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/login",
        "headers": [],  # no dazzle_csrf cookie → middleware would mint
        "scheme": "http",
    }
    collected: list[bytes] = []

    async def inner_app(scope, receive, send):  # noqa: ANN001 - test stub
        headers: list[tuple[bytes, bytes]] = []
        if inner_set_cookie is not None:
            headers.append((b"set-cookie", inner_set_cookie))
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():  # noqa: ANN202 - test stub
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):  # noqa: ANN001 - test stub
        if message["type"] == "http.response.start":
            for key, value in message.get("headers", []):
                if key == b"set-cookie":
                    collected.append(value)

    middleware = CSRFMiddleware(inner_app, config)
    await middleware(scope, receive, send)
    return collected


def _dazzle_csrf_cookies(set_cookies: list[bytes]) -> list[bytes]:
    return [c for c in set_cookies if c.startswith(b"dazzle_csrf=")]


def test_route_set_cookie_survives_not_clobbered_by_middleware() -> None:
    """A login route's session-bound dazzle_csrf cookie must reach the browser
    unclobbered — exactly ONE dazzle_csrf Set-Cookie, carrying the route value."""
    config = CSRFConfig(enabled=True)
    route_cookie = b"dazzle_csrf=ROUTE_SECRET; Path=/; SameSite=Lax"

    set_cookies = asyncio.run(_drive_collecting_set_cookies(config, inner_set_cookie=route_cookie))

    dazzle_cookies = _dazzle_csrf_cookies(set_cookies)
    assert len(dazzle_cookies) == 1, (
        "Expected exactly one dazzle_csrf Set-Cookie; the middleware must defer "
        f"to the route-set cookie and not append its own. Got: {dazzle_cookies!r}"
    )
    assert dazzle_cookies[0].startswith(b"dazzle_csrf=ROUTE_SECRET"), (
        "The surviving dazzle_csrf cookie must be the route's session-bound value, "
        f"not a middleware-minted random token. Got: {dazzle_cookies[0]!r}"
    )


def test_middleware_still_mints_when_route_sets_none() -> None:
    """Preserve existing behaviour: if the inner app sets no dazzle_csrf cookie,
    the middleware DOES inject its minted one."""
    config = CSRFConfig(enabled=True)

    set_cookies = asyncio.run(_drive_collecting_set_cookies(config, inner_set_cookie=None))

    dazzle_cookies = _dazzle_csrf_cookies(set_cookies)
    assert len(dazzle_cookies) == 1, (
        "The middleware must still mint a dazzle_csrf cookie when the route sets "
        f"none. Got: {dazzle_cookies!r}"
    )
    value = dazzle_cookies[0].split(b";", 1)[0].split(b"=", 1)[1]
    assert value and value != b"ROUTE_SECRET", (
        "Minted token should be a non-empty random value, not the route sentinel."
    )
