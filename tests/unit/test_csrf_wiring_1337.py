"""Regression guard for the front-end CSRF wiring family (#1337).

The CSRF middleware (`back/runtime/csrf.py`) is enabled for *every* security
profile and 403s any state-changing request whose `X-CSRF-Token` header doesn't
echo the `dazzle_csrf` cookie. The browser-side echo lives in
`static/js/dz-csrf.js`, bundled into `dist/dazzle.min.js`. Before #1337 no such
handler existed on app pages at all, so every generated-form UI write 403'd in a
real browser — masked in CI only because the test clients echo the cookie by
hand. (Sibling of #1336, where the vendor widget JS was likewise absent.)

These tests pin two independent layers:

1. The *contract* the front-end must satisfy — the middleware accepts a POST iff
   the header echoes the cookie. This is asserted directly against the real
   ASGI middleware, so it can never drift from what the JS has to do.
2. The *wiring* — `dz-csrf.js` is bundled and the built bundle actually carries
   the cookie→header echo. A list-level assertion (#1336's lesson) isn't enough:
   we assert the capability's source markers are present in the shipped bundle,
   which is the exact thing that was missing.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from dazzle.http.runtime.csrf import CSRFConfig, CSRFMiddleware

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DIST_JS = _REPO_ROOT / "src" / "dazzle" / "page" / "runtime" / "static" / "dist" / "dazzle.min.js"
_CSRF_JS = _REPO_ROOT / "src" / "dazzle" / "page" / "runtime" / "static" / "js" / "dz-csrf.js"


async def _drive(
    config: CSRFConfig,
    *,
    method: str,
    path: str,
    cookie: str | None,
    header_token: str | None,
) -> int:
    """Run one request through CSRFMiddleware, returning the response status.

    A 200 means the middleware passed the request through to the inner app; any
    other status is the middleware's own response (e.g. its 403 rejection).
    """
    headers: list[tuple[bytes, bytes]] = []
    if cookie is not None:
        headers.append((b"cookie", f"dazzle_csrf={cookie}".encode()))
    if header_token is not None:
        headers.append((b"x-csrf-token", header_token.encode()))

    scope = {"type": "http", "method": method, "path": path, "headers": headers}
    status = {"code": 0}

    async def inner_app(scope, receive, send):  # noqa: ANN001 - test stub
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def receive():  # noqa: ANN202 - test stub
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):  # noqa: ANN001 - test stub
        if message["type"] == "http.response.start":
            status["code"] = message["status"]

    middleware = CSRFMiddleware(inner_app, config)
    await middleware(scope, receive, send)
    return status["code"]


class TestCSRFContract:
    """The contract dz-csrf.js exists to satisfy, pinned against the middleware."""

    def test_post_with_echoed_token_passes(self) -> None:
        config = CSRFConfig(enabled=True)
        status = asyncio.run(
            _drive(
                config,
                method="POST",
                path="/academicyears",
                cookie="deadbeef",
                header_token="deadbeef",
            )
        )
        assert status == 200, (
            "A POST whose X-CSRF-Token echoes the dazzle_csrf cookie must pass — "
            "this is exactly what dz-csrf.js wires onto htmx:config:request."
        )

    def test_post_without_header_is_rejected(self) -> None:
        """The failure mode #1337 reported — no header attached → 403."""
        config = CSRFConfig(enabled=True)
        status = asyncio.run(
            _drive(
                config,
                method="POST",
                path="/academicyears",
                cookie="deadbeef",
                header_token=None,
            )
        )
        assert status == 403

    def test_post_with_mismatched_header_is_rejected(self) -> None:
        config = CSRFConfig(enabled=True)
        status = asyncio.run(
            _drive(
                config,
                method="POST",
                path="/academicyears",
                cookie="deadbeef",
                header_token="not-the-cookie",
            )
        )
        assert status == 403

    def test_safe_get_needs_no_header(self) -> None:
        config = CSRFConfig(enabled=True)
        status = asyncio.run(
            _drive(
                config,
                method="GET",
                path="/academicyears",
                cookie="deadbeef",
                header_token=None,
            )
        )
        assert status == 200


class TestCSRFWiringBundled:
    """The wiring itself must ship in the bundle every app page loads."""

    def test_dz_csrf_js_in_build_manifest(self) -> None:
        # Imported lazily — scripts/ isn't a package, so load by path.
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "build_dist", _REPO_ROOT / "scripts" / "build_dist.py"
        )
        assert spec is not None and spec.loader is not None
        build_dist = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build_dist)
        names = {p.name for p in build_dist.JS_SOURCES}
        assert "dz-csrf.js" in names, (
            "dz-csrf.js dropped from build_dist.JS_SOURCES — the CSRF echo would "
            "vanish from the bundle and every UI write would 403 again (#1337)."
        )

    def test_source_module_wires_configrequest_echo(self) -> None:
        src = _CSRF_JS.read_text(encoding="utf-8")
        assert "htmx:config:request" in src
        assert "dazzle_csrf" in src
        assert "X-CSRF-Token" in src

    def test_built_bundle_carries_csrf_echo(self) -> None:
        """The shipped bundle — not just the source — must contain the echo.

        This is the assertion that would have failed on v0.81.13: a list-level
        'is the script referenced' check passes vacuously when the capability is
        simply absent, so we assert the capability's markers are in the bytes
        the browser actually executes.
        """
        assert _DIST_JS.exists(), "dist bundle missing — run scripts/build_dist.py"
        bundle = _DIST_JS.read_text(encoding="utf-8")
        assert "dazzle_csrf" in bundle, (
            "dist/dazzle.min.js has no dazzle_csrf echo — the CSRF wiring is not "
            "in the bundle app pages load. Rebuild with scripts/build_dist.py."
        )
        assert "X-CSRF-Token" in bundle
        assert "htmx:config:request" in bundle
