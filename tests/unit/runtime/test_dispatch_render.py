"""Dispatch helper: routes by surface.render with Jinja fallback."""

from unittest.mock import MagicMock

import pytest

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.render.fragment.errors import FragmentError
from dazzle_back.runtime.renderers.dispatch import dispatch_render
from dazzle_back.runtime.renderers.init import register_default_renderers
from dazzle_back.runtime.services import RuntimeServices


def _make_services() -> RuntimeServices:
    services = RuntimeServices()
    register_default_renderers(services)
    return services


def test_dispatch_uses_jinja_when_render_is_none() -> None:
    services = _make_services()
    sentinel = MagicMock(spec=["render"])
    sentinel.render.return_value = "<jinja-output/>"
    services.renderer_registry._handlers["jinja"] = sentinel

    surface = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST)
    html = dispatch_render(surface, ctx={"items": []}, services=services)
    assert html == "<jinja-output/>"
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
