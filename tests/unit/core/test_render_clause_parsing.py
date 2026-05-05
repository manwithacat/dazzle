"""Tests for the render: DSL clause on SurfaceSpec and WorkspaceRegion."""

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec


def test_surface_spec_render_default_none() -> None:
    s = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST)
    assert s.render is None


def test_surface_spec_render_explicit() -> None:
    s = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST, render="fragment")
    assert s.render == "fragment"
