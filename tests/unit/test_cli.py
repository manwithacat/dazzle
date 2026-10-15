"""Tests for CLI commands."""

from pathlib import Path

import pytest

from tests.unit.helpers.cli import invoke, run_cli


@pytest.fixture
def test_project(tmp_path: Path):
    """Create a temporary test project."""
    # Create project structure
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()

    # Create a simple DSL file
    dsl_file = dsl_dir / "test.dsl"
    dsl_file.write_text(
        """
module testapp

app test_app "Test App"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: enum[todo,done]=todo

  permit:
    list: authenticated
    read: authenticated

  scope:
    list: all
      as: *
    # Pair read with list so gated_read / detail hubs work (#303)
    read: all
      as: *

  fitness:
    repr_fields: [title, status]

surface task_list "Tasks":
  uses entity Task
  mode: list

  section main "Tasks":
    field title "Title"
    field status "Status"
"""
    )

    # Create dazzle.toml
    manifest = tmp_path / "dazzle.toml"
    manifest.write_text(
        """
[project]
name = "test_app"
version = "0.1.0"
root = "testapp"

[modules]
paths = ["dsl/"]
"""
    )

    return tmp_path


def test_validate_command_success(test_project: Path) -> None:
    out = run_cli(["validate", "--manifest", test_project / "dazzle.toml"])
    assert "Spec is valid" in out


def test_validate_command_reports_unknown_surface_field(tmp_path: Path) -> None:
    """A surface naming a field the entity lacks fails validation with exit 1."""
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "test.dsl").write_text(
        """
module testapp

app test_app "Test App"

entity Task:
  id: uuid pk
  title: str(200) required

surface task_list:
  uses entity Task
  mode: list

  section main:
    field nonexistent "Nonexistent Field"
"""
    )
    manifest = tmp_path / "dazzle.toml"
    manifest.write_text(
        """
[project]
name = "test_app"
version = "0.1.0"
root = "testapp"

[modules]
paths = ["./dsl"]
"""
    )

    result = invoke(["validate", "--manifest", manifest])
    assert result.exit_code == 1
    assert "nonexistent" in result.stderr


def test_lint_command_passes_on_valid_project(test_project: Path) -> None:
    run_cli(["lint", "--manifest", test_project / "dazzle.toml"])


def test_inspect_project_lists_entities_and_surfaces(test_project: Path) -> None:
    """`dazzle inspect project` (moved under the inspect group in #1120)."""
    out = run_cli(["inspect", "project", "--manifest", test_project / "dazzle.toml"])
    assert "Entities" in out
    assert "Task" in out
    assert "task_list" in out


# ===========================================================================
# Discoverability: `dazzle search`
# ===========================================================================


@pytest.mark.parametrize(
    ("keyword", "exit_code", "fragments"),
    [
        pytest.param("serve", 0, ["dazzle serve"], id="finds_serve"),
        pytest.param("validate", 0, ["dazzle validate"], id="finds_validate"),
        pytest.param("xyznonexistent999", 1, ["No commands found"], id="no_match_exits_1"),
    ],
)
def test_search_command(keyword: str, exit_code: int, fragments: list[str]) -> None:
    out = run_cli(["search", keyword], exit_code=exit_code)
    for fragment in fragments:
        assert fragment in out
