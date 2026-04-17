"""Tests for the `dazzle version` subcommand and `--version` flag.

Both shapes must stay working because:

- ``--version`` is the long-standing top-level flag.
- ``version`` is the subcommand invoked by the homebrew-tap
  validate-formula workflow (and by most CLI conventions).
- ``version --full`` appends machine-readable feature flags that the
  tap test greps for (``python_available: true``).
"""

from __future__ import annotations

from typer.testing import CliRunner

from dazzle.cli import app

runner = CliRunner()


class TestVersionSubcommand:
    def test_version_subcommand_prints_header(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "DAZZLE version" in result.stdout

    def test_version_subcommand_prints_environment(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "Environment:" in result.stdout
        assert "Python:" in result.stdout
        assert "Platform:" in result.stdout

    def test_version_subcommand_without_full_omits_flags(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        # Without --full, the "Flags:" section is not emitted.
        assert "python_available:" not in result.stdout

    def test_version_full_emits_python_available_flag(self) -> None:
        # Tap's validate-formula grep target:
        #   dazzle version --full | grep -q "python_available"
        result = runner.invoke(app, ["version", "--full"])
        assert result.exit_code == 0
        assert "python_available: true" in result.stdout

    def test_version_full_includes_lsp_and_llm_flags(self) -> None:
        result = runner.invoke(app, ["version", "--full"])
        assert result.exit_code == 0
        assert "lsp_available:" in result.stdout
        assert "llm_available:" in result.stdout


class TestVersionFlag:
    def test_top_level_version_flag_still_works(self) -> None:
        # Regression: adding the `version` subcommand must not break
        # the existing `--version` entry point.
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "DAZZLE version" in result.stdout

    def test_short_version_flag(self) -> None:
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert "DAZZLE version" in result.stdout
