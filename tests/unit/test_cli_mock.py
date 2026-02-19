"""Tests for dazzle mock CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from dazzle.cli.mock import mock_app

runner = CliRunner()


# ---------------------------------------------------------------------------
# dazzle mock list
# ---------------------------------------------------------------------------


class TestMockList:
    @patch("dazzle.cli.mock.load_project_appspec")
    def test_list_with_packs(self, mock_load: MagicMock) -> None:
        appspec = MagicMock()
        api1 = MagicMock()
        api1.spec_inline = "pack:sumsub_kyc"
        api2 = MagicMock()
        api2.spec_inline = "pack:stripe_payments"
        appspec.apis = [api1, api2]
        mock_load.return_value = appspec

        result = runner.invoke(mock_app, ["list"])
        assert result.exit_code == 0
        assert "sumsub_kyc" in result.output
        assert "stripe_payments" in result.output
        assert "2 vendor" in result.output

    @patch("dazzle.cli.mock.load_project_appspec")
    def test_list_no_packs(self, mock_load: MagicMock) -> None:
        appspec = MagicMock()
        appspec.apis = []
        mock_load.return_value = appspec

        result = runner.invoke(mock_app, ["list"])
        assert result.exit_code == 0
        assert "No API pack references" in result.output

    @patch("dazzle.cli.mock.load_project_appspec")
    def test_list_load_error(self, mock_load: MagicMock) -> None:
        mock_load.side_effect = RuntimeError("Parse error")
        result = runner.invoke(mock_app, ["list"])
        assert result.exit_code == 1
        assert "Error loading spec" in result.output


# ---------------------------------------------------------------------------
# dazzle mock scenario
# ---------------------------------------------------------------------------


class TestMockScenario:
    def test_list_scenarios(self) -> None:
        result = runner.invoke(mock_app, ["scenario", "sumsub_kyc", "--list"])
        assert result.exit_code == 0
        assert "kyc_approved" in result.output
        assert "kyc_rejected" in result.output

    def test_inspect_scenario(self) -> None:
        result = runner.invoke(mock_app, ["scenario", "sumsub_kyc", "kyc_rejected"])
        assert result.exit_code == 0
        assert "kyc_rejected" in result.output
        assert "document face mismatch" in result.output.lower()
        assert "Steps" in result.output

    def test_scenario_not_found(self) -> None:
        result = runner.invoke(mock_app, ["scenario", "sumsub_kyc", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_unknown_vendor_scenarios(self) -> None:
        result = runner.invoke(mock_app, ["scenario", "nonexistent_vendor", "--list"])
        assert result.exit_code == 0
        assert "No scenarios found" in result.output

    def test_scenario_shows_vendor_name_alone(self) -> None:
        """Running with just vendor name shows list."""
        result = runner.invoke(mock_app, ["scenario", "stripe_payments"])
        assert result.exit_code == 0
        assert "payment_succeeded" in result.output


# ---------------------------------------------------------------------------
# dazzle mock webhook
# ---------------------------------------------------------------------------


class TestMockWebhook:
    def test_list_webhook_events(self) -> None:
        result = runner.invoke(mock_app, ["webhook", "sumsub_kyc", "--list"])
        assert result.exit_code == 0
        assert "applicant_reviewed" in result.output
        assert "applicant_created" in result.output

    def test_list_unknown_vendor(self) -> None:
        result = runner.invoke(mock_app, ["webhook", "nonexistent", "--list"])
        assert result.exit_code == 0
        assert "No webhook events" in result.output

    def test_fire_webhook_connection_error(self) -> None:
        """Firing to a non-running server records the error."""
        result = runner.invoke(
            mock_app,
            ["webhook", "sumsub_kyc", "applicant_reviewed", "--target", "http://127.0.0.1:19999"],
        )
        assert result.exit_code == 0
        assert "failed" in result.output.lower()

    def test_fire_webhook_invalid_json(self) -> None:
        result = runner.invoke(
            mock_app,
            ["webhook", "sumsub_kyc", "applicant_reviewed", "--data", "not-json"],
        )
        assert result.exit_code == 1
        assert "Invalid JSON" in result.output

    def test_list_events_no_event_arg(self) -> None:
        """Running with just vendor name shows list."""
        result = runner.invoke(mock_app, ["webhook", "stripe_payments"])
        assert result.exit_code == 0
        assert "payment_intent.succeeded" in result.output
