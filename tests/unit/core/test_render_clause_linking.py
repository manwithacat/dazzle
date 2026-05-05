"""Linker validation: render: references resolve to known renderer names."""

import tempfile
from pathlib import Path

import pytest

from dazzle.core.linker import RenderValidationError, build_appspec
from dazzle.core.parser import parse_modules

_DSL_BASE = """module test
app sample "Demo"

entity Task "Task":
  id: uuid pk
  title: str(200)
"""


def _link(extra: str, *, known_renderers: set[str] | None = None):
    full_src = _DSL_BASE + extra
    with tempfile.NamedTemporaryFile(mode="w", suffix=".dsl", delete=False) as f:
        f.write(full_src)
        tmp_path = Path(f.name)
    modules = parse_modules([tmp_path])
    return build_appspec(modules, root_module_name="test", known_renderers=known_renderers)


def test_linker_accepts_known_renderer_on_surface() -> None:
    appspec = _link(
        """
surface task_list "Tasks":
  uses entity Task
  mode: list
  render: fragment
""",
        known_renderers={"jinja", "fragment"},
    )
    surface = next(s for s in appspec.surfaces if s.name == "task_list")
    assert surface.render == "fragment"


def test_linker_rejects_unknown_renderer_on_surface() -> None:
    with pytest.raises(RenderValidationError, match="moonbeam"):
        _link(
            """
surface task_list "Tasks":
  uses entity Task
  mode: list
  render: moonbeam
""",
            known_renderers={"jinja", "fragment"},
        )


def test_linker_skips_render_validation_when_no_registry_supplied() -> None:
    """Backwards-compatible default for non-runtime callers (lint, tests)."""
    appspec = _link(
        """
surface task_list "Tasks":
  uses entity Task
  mode: list
  render: anything_at_all
""",
        known_renderers=None,
    )
    surface = next(s for s in appspec.surfaces if s.name == "task_list")
    assert surface.render == "anything_at_all"


def test_linker_accepts_known_renderer_on_region() -> None:
    appspec = _link(
        """
surface task_list "Tasks":
  uses entity Task
  mode: list

workspace ops "Ops":
  tasks:
    source: Task
    render: fragment
""",
        known_renderers={"jinja", "fragment"},
    )
    region = appspec.workspaces[0].regions[0]
    assert region.render == "fragment"


def test_linker_rejects_unknown_renderer_on_region() -> None:
    with pytest.raises(RenderValidationError, match="nope_3000"):
        _link(
            """
surface task_list "Tasks":
  uses entity Task
  mode: list

workspace ops "Ops":
  tasks:
    source: Task
    render: nope_3000
""",
            known_renderers={"jinja", "fragment"},
        )
