"""Dispatch helper: routes by surface.render with Fragment fallback.

Post-#1051 (v0.67.85+) the legacy "jinja" renderer adapter is retired;
the dispatcher's default is now "fragment".
"""

from unittest.mock import MagicMock

import pytest

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.http.runtime.renderers.init import register_default_renderers
from dazzle.http.runtime.services import RuntimeServices
from dazzle.render.dispatch import dispatch_render
from dazzle.render.fragment.errors import FragmentError


def _make_services() -> RuntimeServices:
    services = RuntimeServices()
    register_default_renderers(services)
    return services


def test_dispatch_uses_fragment_when_render_is_none() -> None:
    services = _make_services()
    sentinel = MagicMock(spec=["render"])
    sentinel.render.return_value = "<fragment-output/>"
    services.renderer_registry._handlers["fragment"] = sentinel

    surface = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST)
    html = dispatch_render(surface, ctx={"items": []}, services=services)
    assert html == "<fragment-output/>"
    sentinel.render.assert_called_once()


def test_dispatch_uses_fragment_when_render_is_fragment() -> None:
    services = _make_services()
    sentinel = MagicMock(spec=["render"])
    sentinel.render.return_value = "<fragment-output/>"
    services.renderer_registry._handlers["fragment"] = sentinel

    surface = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST, render="fragment")
    html = dispatch_render(surface, ctx={"items": []}, services=services)
    assert html == "<fragment-output/>"
    sentinel.render.assert_called_once()


def test_dispatch_unknown_renderer_raises() -> None:
    services = _make_services()
    surface = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST, render="moonbeam")
    with pytest.raises(FragmentError, match="moonbeam"):
        dispatch_render(surface, ctx={"items": []}, services=services)


def test_dispatch_calls_handler_with_surface_and_ctx() -> None:
    """Plan 5: renderer receives (surface, ctx) — no shape-routing
    in the dispatcher."""
    services = _make_services()

    fragment_sentinel = MagicMock(spec=["render"])
    fragment_sentinel.render.return_value = "<fragment/>"
    services.renderer_registry._handlers["fragment"] = fragment_sentinel

    ctx: dict = {"items": []}
    surface = SurfaceSpec(name="x", mode=SurfaceMode.LIST)

    dispatch_render(surface, ctx=ctx, services=services)

    args = fragment_sentinel.render.call_args
    assert args[0][0] is surface
    assert args[0][1] is ctx
