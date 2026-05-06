"""End-to-end smoke: simple_task boots, validates, and renders unchanged
under the default (no `render:` clauses anywhere) configuration."""

import tempfile
from pathlib import Path

import pytest

from dazzle.core.linker import RenderValidationError, build_appspec
from dazzle.core.parser import parse_modules

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SIMPLE_TASK_ROOT = _REPO_ROOT / "examples" / "simple_task"
SIMPLE_TASK_DSL_DIR = SIMPLE_TASK_ROOT / "dsl"


def _load_simple_task_modules():
    """Parse all .dsl files under simple_task using the standard parse_modules path."""
    if not SIMPLE_TASK_DSL_DIR.exists():
        pytest.fail(f"simple_task DSL dir not found at {SIMPLE_TASK_DSL_DIR}")
    dsl_files = sorted(SIMPLE_TASK_DSL_DIR.glob("*.dsl"))
    if not dsl_files:
        pytest.fail(f"No .dsl files found under {SIMPLE_TASK_DSL_DIR}")
    return parse_modules(dsl_files)


def _root_module_name(modules) -> str:
    """Pick the module that declares an app — that's the linker entry point."""
    for m in modules:
        if m.app_name is not None:
            return m.name
    pytest.fail(f"No module with `app` declaration in {[m.name for m in modules]}")


def test_simple_task_links_with_known_renderers() -> None:
    """The example app links cleanly with the default known_renderers set.

    As of P3 Task 5 (2026-05), simple_task.task_list opts into render: fragment;
    every other surface still uses the default (None → legacy jinja path).
    """
    modules = _load_simple_task_modules()
    root = _root_module_name(modules)
    appspec = build_appspec(
        modules,
        root_module_name=root,
        known_renderers={"jinja", "fragment"},
    )
    assert appspec is not None
    # Plan 3 flipped task_list; Plan 8 added task_detail. As more surfaces
    # flip in subsequent plans, this set grows — keep the list explicit so
    # an accidental flip elsewhere fails the test.
    expected_flipped = {"task_list", "task_detail"}
    by_name = {s.name: s for s in appspec.surfaces}
    for name in expected_flipped:
        assert name in by_name, f"surface {name} missing from simple_task spec"
        assert by_name[name].render == "fragment", (
            f"expected {name}.render='fragment', got {by_name[name].render!r}"
        )
    # Every other surface should still be on the default (None).
    for s in appspec.surfaces:
        if s.name in expected_flipped:
            continue
        assert s.render is None, f"surface {s.name} has unexpected render={s.render!r}"


def test_simple_task_links_when_render_validation_disabled() -> None:
    """Backwards compat: known_renderers=None must not break the legacy path."""
    modules = _load_simple_task_modules()
    root = _root_module_name(modules)
    appspec = build_appspec(modules, root_module_name=root, known_renderers=None)
    assert appspec is not None


def test_unknown_renderer_in_synthetic_app_is_caught() -> None:
    """Inject a render: moonbeam clause and confirm linking rejects it."""
    test_module_src = """module synthetic
app sample "Demo"

entity Task "Task":
  id: uuid pk
  title: str(200)

surface task_list "Tasks":
  uses entity Task
  mode: list
  render: moonbeam
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".dsl", delete=False) as f:
        f.write(test_module_src)
        tmp_path = Path(f.name)
    modules = parse_modules([tmp_path])
    with pytest.raises(RenderValidationError, match="moonbeam"):
        build_appspec(
            modules,
            root_module_name="synthetic",
            known_renderers={"jinja", "fragment"},
        )
