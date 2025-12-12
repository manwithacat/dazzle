"""Tests for CLI commands."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from dazzle.cli import app


@pytest.fixture
def cli_runner():
    """Return a CLI test runner."""
    return CliRunner()


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


def test_validate_command_success(cli_runner: CliRunner, test_project: Path):
    """Test validate command with valid DSL."""
    result = cli_runner.invoke(app, ["validate", "--manifest", str(test_project / "dazzle.toml")])
    assert result.exit_code == 0
    assert "Spec is valid" in result.stdout


def test_validate_command_with_errors(cli_runner: CliRunner, tmp_path: Path):
    """Test validate command with invalid DSL."""
    # Create project with invalid DSL (surface references non-existent field)
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()

    dsl_file = dsl_dir / "test.dsl"
    dsl_file.write_text(
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

    result = cli_runner.invoke(app, ["validate", "--manifest", str(manifest)])
    assert result.exit_code == 1
    # Error messages go to stderr
    assert "ERROR" in result.stderr or "Error" in result.stderr


def test_lint_command(cli_runner: CliRunner, test_project: Path):
    """Test lint command."""
    result = cli_runner.invoke(app, ["lint", "--manifest", str(test_project / "dazzle.toml")])
    # Should pass (may have warnings but no errors)
    assert result.exit_code == 0 or "WARNING" in result.stdout


def test_inspect_command_default(cli_runner: CliRunner, test_project: Path):
    """Test inspect command with default options."""
    result = cli_runner.invoke(app, ["inspect", "--manifest", str(test_project / "dazzle.toml")])

    assert result.exit_code == 0
    # Should show project structure with entities and surfaces
    assert "Entities" in result.stdout or "test_app" in result.stdout
