"""#1392 item 2 — route-override response contract (`# dazzle:returns`)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from dazzle.http.runtime.route_overrides import discover_route_overrides


def _write(tmp_path: Path, body: str, name: str = "ov.py") -> Path:
    routes = tmp_path / "routes"
    routes.mkdir(exist_ok=True)
    (routes / name).write_text(textwrap.dedent(body))
    return routes


# ---------------------------------------------------------------- P2: marker scan


def test_returns_kind_parsed(tmp_path: Path) -> None:
    routes = _write(
        tmp_path,
        """
        # dazzle:route-override GET /app/board
        # dazzle:returns fragment

        async def handler(request):
            return "<div>board</div>"
        """,
    )
    o = next(o for o in discover_route_overrides(routes) if o.path == "/app/board")
    assert o.returns_kind == "fragment"


def test_no_returns_marker_is_none(tmp_path: Path) -> None:
    routes = _write(
        tmp_path,
        """
        # dazzle:route-override GET /app/plain

        async def handler(request):
            return "<div>x</div>"
        """,
    )
    assert discover_route_overrides(routes)[0].returns_kind is None


def test_unknown_returns_kind_is_error(tmp_path: Path) -> None:
    routes = _write(
        tmp_path,
        """
        # dazzle:route-override GET /x
        # dazzle:returns bogus

        async def handler(request):
            return "x"
        """,
    )
    with pytest.raises(ValueError, match="dazzle:returns"):
        discover_route_overrides(routes)


# ---------------------------------------------------------- P3: contract wrapper

import asyncio  # noqa: E402
import logging  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from typing import Any  # noqa: E402

from fastapi import HTTPException  # noqa: E402
from starlette.responses import HTMLResponse, JSONResponse  # noqa: E402

from dazzle.http.runtime.page_routes import build_app_page_context  # noqa: E402
from dazzle.http.runtime.route_overrides import (  # noqa: E402
    _wrap_with_response_contract,
    build_override_router,
)


def _fake_request(*, hx: bool = False) -> Any:
    app_state = SimpleNamespace(
        appspec=SimpleNamespace(app_title="App", name="app"),
        fragment_chrome_css_links=("/x.css",),
        fragment_chrome_js_scripts=("/x.js",),
        fragment_chrome_theme=None,
        fragment_chrome_font_preconnect=(),
        fragment_chrome_favicon="/f.svg",
    )
    return SimpleNamespace(
        headers={"HX-Request": "true"} if hx else {},
        app=SimpleNamespace(state=app_state),
        state=SimpleNamespace(tenant_config={}),
    )


async def _builder(request: Any, current_route: str) -> Any:
    return await build_app_page_context(request, current_route=current_route)


def _call(handler, *, kind, path, builder, request):
    wrapped = _wrap_with_response_contract(
        handler, returns_kind=kind, path=path, page_ctx_builder=builder
    )
    return asyncio.run(wrapped(request=request))


def test_fragment_htmx_returns_inner() -> None:
    async def h(request):
        return "<div>frag</div>"

    resp = _call(
        h, kind="fragment", path="/app/x", builder=_builder, request=_fake_request(hx=True)
    )
    assert isinstance(resp, HTMLResponse)
    assert resp.body.decode() == "<div>frag</div>"


def test_fragment_full_page_is_chromed() -> None:
    async def h(request):
        return "<div>frag</div>"

    resp = _call(h, kind="fragment", path="/app/x", builder=_builder, request=_fake_request())
    body = resp.body.decode()
    assert "<div>frag</div>" in body and "<html" in body.lower()  # wrapped in the shell


def test_fragment_full_document_is_refused() -> None:
    async def h(request):
        return "<!doctype html><html><body>escape</body></html>"

    try:
        _call(h, kind="fragment", path="/app/x", builder=_builder, request=_fake_request())
        assert False, "expected refusal"
    except HTTPException as exc:
        assert exc.status_code == 500 and "response_contract_violation" in str(exc.detail)


def test_partial_served_raw() -> None:
    async def h(request):
        return "<li>row</li>"

    resp = _call(h, kind="partial", path="/app/x", builder=_builder, request=_fake_request())
    assert resp.body.decode() == "<li>row</li>"  # no chrome


def test_page_full_document_allowed() -> None:
    async def h(request):
        return HTMLResponse("<!doctype html><html><body>novel</body></html>")

    resp = _call(h, kind="page", path="/app/x", builder=_builder, request=_fake_request())
    assert "novel" in resp.body.decode()  # full-bleed, never refused


def test_json_passthrough() -> None:
    async def h(request):
        return JSONResponse({"ok": True})

    resp = _call(h, kind="json", path="/api/x", builder=_builder, request=_fake_request())
    assert isinstance(resp, JSONResponse)


def test_undeclared_app_html_nudges_once(caplog) -> None:
    from dazzle.http.runtime import route_overrides

    route_overrides._RESPONSE_CONTRACT_NUDGED.discard("/app/undeclared")

    async def h(request):
        return "<div>x</div>"

    with caplog.at_level(logging.WARNING, logger="dazzle.http.runtime.route_overrides"):
        _call(h, kind=None, path="/app/undeclared", builder=_builder, request=_fake_request())
        _call(h, kind=None, path="/app/undeclared", builder=_builder, request=_fake_request())
    nudges = [r for r in caplog.records if "declares no `# dazzle:returns`" in r.message]
    assert len(nudges) == 1  # one-time, keyed by path


# ---------------------------------------------------- P4: integration dogfood


def test_build_override_router_chromes_fragment_and_serves_page(tmp_path) -> None:
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    routes = tmp_path / "routes"
    routes.mkdir()
    (routes / "board.py").write_text(
        "# dazzle:route-override GET /app/board\n# dazzle:returns fragment\n\n"
        "from starlette.requests import Request\n"
        "async def handler(request: Request):\n    return '<section>board</section>'\n"
    )
    (routes / "kiosk.py").write_text(
        "# dazzle:route-override GET /app/kiosk\n# dazzle:returns page\n\n"
        "from starlette.requests import Request\n"
        "from starlette.responses import HTMLResponse\n"
        "async def handler(request: Request):\n"
        "    return HTMLResponse('<!doctype html><html><body>kiosk</body></html>')\n"
    )
    router = build_override_router(routes, page_ctx_builder=_builder)
    app = FastAPI()
    app.state.appspec = SimpleNamespace(app_title="App", name="app")
    for attr, val in {
        "fragment_chrome_css_links": ("/x.css",),
        "fragment_chrome_js_scripts": ("/x.js",),
        "fragment_chrome_theme": None,
        "fragment_chrome_font_preconnect": (),
        "fragment_chrome_favicon": "/f.svg",
    }.items():
        setattr(app.state, attr, val)
    app.include_router(router)
    client = TestClient(app)

    # fragment, full-page nav → chromed (inner inside the app shell document)
    full = client.get("/app/board")
    assert full.status_code == 200
    assert "<section>board</section>" in full.text and "<html" in full.text.lower()

    # fragment, HTMX → inner only (no shell)
    inner = client.get("/app/board", headers={"HX-Request": "true"})
    assert inner.text == "<section>board</section>"

    # page → full document served as-is (novel/full-bleed, never refused)
    page = client.get("/app/kiosk")
    assert "kiosk" in page.text and page.text.strip().lower().startswith("<!doctype")
