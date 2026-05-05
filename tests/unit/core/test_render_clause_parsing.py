"""Tests for the render: DSL clause on SurfaceSpec and WorkspaceRegion."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
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


def test_surface_parser_accepts_render_clause() -> None:
    src = """
module test
app sample "Demo"

entity Task "Task":
  id: uuid pk
  title: str(200)

surface task_list "Tasks":
  uses entity Task
  mode: list
  render: fragment
"""
    _, _, _, _, _, fragment = parse_dsl(src, Path("test.dsl"))
    assert len(fragment.surfaces) == 1
    assert fragment.surfaces[0].render == "fragment"


def test_surface_parser_render_omitted_remains_none() -> None:
    src = """
module test
app sample "Demo"

entity Task "Task":
  id: uuid pk

surface task_list "Tasks":
  uses entity Task
  mode: list
"""
    _, _, _, _, _, fragment = parse_dsl(src, Path("test.dsl"))
    assert fragment.surfaces[0].render is None


def test_workspace_region_parser_accepts_render_clause() -> None:
    src = """
module test
app sample "Demo"

entity Task "Task":
  id: uuid pk
  title: str(200)

surface task_list "Tasks":
  uses entity Task
  mode: list

workspace ops "Ops":
  tasks:
    source: Task
    render: fragment
"""
    _, _, _, _, _, fragment = parse_dsl(src, Path("test.dsl"))
    assert len(fragment.workspaces) == 1
    region = fragment.workspaces[0].regions[0]
    assert region.render == "fragment"
