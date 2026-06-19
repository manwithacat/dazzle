"""#1392 item 2 — route-override response contract (`# dazzle:returns`)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from dazzle.back.runtime.route_overrides import discover_route_overrides


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

from dazzle.back.runtime.route_overrides import _wrap_with_response_contract  # noqa: E402
from dazzle.ui.runtime.page_routes import build_app_page_context  # noqa: E402


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
    from dazzle.back.runtime import route_overrides

    route_overrides._RESPONSE_CONTRACT_NUDGED.discard("/app/undeclared")

    async def h(request):
        return "<div>x</div>"

    with caplog.at_level(logging.WARNING, logger="dazzle.back.runtime.route_overrides"):
        _call(h, kind=None, path="/app/undeclared", builder=_builder, request=_fake_request())
        _call(h, kind=None, path="/app/undeclared", builder=_builder, request=_fake_request())
    nudges = [r for r in caplog.records if "declares no `# dazzle:returns`" in r.message]
    assert len(nudges) == 1  # one-time, keyed by path
