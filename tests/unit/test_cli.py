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


# ===========================================================================
# Discoverability commands: `dazzle commands` and `dazzle search`
# ===========================================================================


class TestCommandsCommand:
    """Tests for `dazzle commands` — list all CLI commands."""

    def test_commands_lists_output(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(app, ["commands"])
        assert result.exit_code == 0
        assert "serve" in result.output

    def test_commands_json_output(self, cli_runner: CliRunner) -> None:
        import json

        result = cli_runner.invoke(app, ["commands", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "serve" in data

    def test_commands_json_entries_have_description(self, cli_runner: CliRunner) -> None:
        import json

        result = cli_runner.invoke(app, ["commands", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for cmd, info in data.items():
            assert "description" in info, f"'{cmd}' missing description in JSON output"

    def test_commands_category_filter_runtime(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(app, ["commands", "--category", "Runtime"])
        assert result.exit_code == 0
        assert "serve" in result.output

    def test_commands_category_filter_case_insensitive(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(app, ["commands", "--category", "runtime"])
        assert result.exit_code == 0
        assert "serve" in result.output

    def test_commands_unknown_category_returns_empty(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(app, ["commands", "--category", "NonExistentCategoryXYZ"])
        # Empty category → no output lines with "dazzle", but exit code still 0
        assert result.exit_code == 0


class TestSearchCommand:
    """Tests for `dazzle search` — keyword search over commands."""

    def test_search_finds_serve(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(app, ["search", "serve"])
        assert result.exit_code == 0
        assert "serve" in result.output

    def test_search_finds_validate(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(app, ["search", "validate"])
        assert result.exit_code == 0

    def test_search_no_results_exits_1(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(app, ["search", "xyznonexistent999"])
        assert result.exit_code == 1

    def test_search_no_results_prints_message(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(app, ["search", "xyznonexistent999"])
        assert "No commands found" in result.output

    def test_search_output_contains_dazzle_prefix(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(app, ["search", "serve"])
        assert result.exit_code == 0
        assert "dazzle" in result.output
