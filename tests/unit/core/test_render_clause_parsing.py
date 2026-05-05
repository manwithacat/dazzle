"""Tests for the render: DSL clause on SurfaceSpec and WorkspaceRegion."""

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.core.ir.workspaces import WorkspaceRegion


def test_surface_spec_render_default_none() -> None:
    s = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST)
    assert s.render is None


def test_surface_spec_render_explicit() -> None:
    s = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST, render="fragment")
    assert s.render == "fragment"


def test_workspace_region_render_default_none() -> None:
    r = WorkspaceRegion(name="alerts")
    assert r.render is None


def test_workspace_region_render_explicit() -> None:
    r = WorkspaceRegion(name="alerts", render="cytoscape_3d")
    assert r.render == "cytoscape_3d"
