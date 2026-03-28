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


class TestVerifyContractsFlag:
    def test_contracts_flag_accepted(self) -> None:
        import inspect

        from dazzle.cli.ux import verify_command

        sig = inspect.signature(verify_command)
        param_names = list(sig.parameters.keys())
        assert "contracts" in param_names

    def test_browser_flag_accepted(self) -> None:
        import inspect

        from dazzle.cli.ux import verify_command

        sig = inspect.signature(verify_command)
        param_names = list(sig.parameters.keys())
        assert "browser" in param_names

    def test_strict_flag_accepted(self) -> None:
        import inspect

        from dazzle.cli.ux import verify_command

        sig = inspect.signature(verify_command)
        param_names = list(sig.parameters.keys())
        assert "strict" in param_names

    def test_update_baseline_flag_accepted(self) -> None:
        import inspect

        from dazzle.cli.ux import verify_command

        sig = inspect.signature(verify_command)
        param_names = list(sig.parameters.keys())
        assert "update_baseline" in param_names
