"""Tests for the sentinel fuzz CLI command."""

from unittest.mock import patch

from typer.testing import CliRunner

from dazzle.cli.sentinel import sentinel_app

runner = CliRunner()


class TestSentinelFuzzCLI:
    @patch("dazzle.testing.fuzzer.run_campaign")
    @patch("dazzle.testing.fuzzer.generate_report")
    def test_fuzz_command_exists(self, mock_report, mock_campaign) -> None:
        mock_campaign.return_value = []
        mock_report.return_value = "# Report\n0 samples"
        result = runner.invoke(sentinel_app, ["fuzz", "--samples", "5"])
        assert result.exit_code == 0

    @patch("dazzle.testing.fuzzer.run_campaign")
    @patch("dazzle.testing.fuzzer.generate_report")
    def test_fuzz_layer_filter(self, mock_report, mock_campaign) -> None:
        mock_campaign.return_value = []
        mock_report.return_value = "# Report"
        result = runner.invoke(sentinel_app, ["fuzz", "--layer", "mutate", "--samples", "5"])
        assert result.exit_code == 0
        mock_campaign.assert_called_once()
        call_kwargs = mock_campaign.call_args
        assert call_kwargs[1]["layers"] == ["mutate"] or call_kwargs.kwargs["layers"] == ["mutate"]

    @patch("dazzle.testing.fuzzer.run_campaign")
    def test_fuzz_dry_run(self, mock_campaign) -> None:
        mock_campaign.return_value = []
        result = runner.invoke(sentinel_app, ["fuzz", "--dry-run", "--samples", "5"])
        assert result.exit_code == 0
