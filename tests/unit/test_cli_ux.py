"""Tests for the UX verification CLI command."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from dazzle.cli.ux import ux_app

runner = CliRunner()


class TestUxVerifyCLI:
    @patch("dazzle.cli.ux._run_structural_only")
    def test_structural_only_mode(self, mock_run: MagicMock) -> None:
        mock_run.return_value = 0
        # Typer collapses single-command apps, so invoke without subcommand name
        result = runner.invoke(ux_app, ["--structural"])
        assert result.exit_code == 0

    def test_help_works(self) -> None:
        result = runner.invoke(ux_app, ["--help"])
        assert result.exit_code == 0
        assert "verify" in result.output.lower() or "UX" in result.output
