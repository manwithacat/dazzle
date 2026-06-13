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


# ---------------------------------------------------------------------------
# #1117 — agent-actionable error message. The error must name both
# halves of the extension contract (manifest allowlist + runtime
# registration) so an LLM agent reading it knows exactly which two
# places need edits. Pre-#1117 the error was "unknown renderer X;
# registered: [Y]" — said what was wrong but not how to fix it.
# ---------------------------------------------------------------------------


def _surface_error_message() -> str:
    try:
        _link(
            """
surface task_list "Tasks":
  uses entity Task
  mode: list
  render: word_cloud
""",
            known_renderers={"fragment"},
        )
    except RenderValidationError as e:
        return str(e)
    raise AssertionError("expected RenderValidationError")


def test_unknown_renderer_error_mentions_dazzle_toml_allowlist() -> None:
    """The error must point at the `[renderers]` manifest table — the
    first half of the extension contract."""
    msg = _surface_error_message()
    assert "[renderers]" in msg
    assert "extra" in msg
    assert "dazzle.toml" in msg


def test_unknown_renderer_error_mentions_runtime_registration() -> None:
    """The error must point at the runtime registration call — the
    second half of the extension contract."""
    msg = _surface_error_message()
    assert "services.renderer_registry.register" in msg
    assert "handler=" in msg


def test_unknown_renderer_error_quotes_the_offending_name() -> None:
    """Both halves of the recipe should be templated with the actual
    name the agent wrote — not a placeholder. Cuts the read-write-fix
    loop in half."""
    msg = _surface_error_message()
    # Quoted in `[renderers] extra = ['word_cloud']`
    assert "'word_cloud'" in msg


def test_unknown_renderer_error_points_at_worked_example() -> None:
    """The error must mention the worked example so the agent knows
    there's a reference implementation to look at."""
    msg = _surface_error_message()
    assert "fixtures/custom_renderer" in msg


def test_unknown_renderer_error_lists_currently_known_set() -> None:
    """Keep the "registered renderers: [...]" hint so agents who
    typo'd a real renderer name see it spelled correctly."""
    msg = _surface_error_message()
    assert "fragment" in msg
