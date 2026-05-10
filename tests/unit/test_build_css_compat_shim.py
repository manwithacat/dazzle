"""Issue #1038 (v0.67.21): regression tests for the `dazzle build-css`
no-op CLI command.

The build implementation was removed in v0.62; downstream
`bin/post_compile` deploy hooks (e.g. cyfuture's) had been silently
failing with typer's "No such command" since then. This re-
introduces the command name as a no-op that prints a migration
note + exits 0 so deploy hooks keep working until they're cleaned
up. The build behaviour itself remains removed.
"""

from __future__ import annotations

from typer.testing import CliRunner

from dazzle.cli import app


def test_build_css_invocation_succeeds() -> None:
    """The shim exits 0 — deploy hooks invoking it shouldn't fail."""
    runner = CliRunner()
    result = runner.invoke(app, ["build-css"])
    assert result.exit_code == 0


def test_build_css_prints_migration_note() -> None:
    """The visible output names the new asset path so operators can
    audit their deploy hooks against the correct location."""
    runner = CliRunner()
    result = runner.invoke(app, ["build-css"])
    assert "no-op since v0.62" in result.output
    assert "dazzle.min.css" in result.output
    assert "/static/dist/dazzle.min.css" in result.output


def test_build_css_no_args_does_not_crash() -> None:
    """The pre-fix shape (typer 'No such command') would emit error
    output to stderr; the shim emits a clean stdout note."""
    runner = CliRunner()
    result = runner.invoke(app, ["build-css"])
    # No traceback / typer error chrome.
    assert "Usage:" not in result.output
    assert "Error" not in result.output


def test_build_css_registered_in_app_commands() -> None:
    """Sanity: the command name shows up in --help output."""
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert "build-css" in result.output
