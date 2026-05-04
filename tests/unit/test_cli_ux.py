"""Tests for the UX verification CLI command."""

import inspect
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from dazzle.cli.ux import ux_app

runner = CliRunner()


class TestUxVerifyCLI:
    @patch("dazzle.cli.ux._run_structural_only")
    def test_structural_only_mode(self, mock_run: MagicMock) -> None:
        mock_run.return_value = 0
        # `ux` now has multiple subcommands (verify, explore), so invoke
        # the verify subcommand explicitly.
        result = runner.invoke(ux_app, ["verify", "--structural"])
        assert result.exit_code == 0

    def test_help_works(self) -> None:
        result = runner.invoke(ux_app, ["--help"])
        assert result.exit_code == 0
        assert "verify" in result.output.lower() or "UX" in result.output


class TestVerifyContractsFlag:
    @pytest.mark.parametrize(
        "param_name",
        ["contracts", "browser", "strict", "update_baseline"],
        ids=[
            "test_contracts_flag_accepted",
            "test_browser_flag_accepted",
            "test_strict_flag_accepted",
            "test_update_baseline_flag_accepted",
        ],
    )
    def test_flag_accepted(self, param_name: str) -> None:
        from dazzle.cli.ux import verify_command

        param_names = list(inspect.signature(verify_command).parameters.keys())
        assert param_name in param_names
