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
