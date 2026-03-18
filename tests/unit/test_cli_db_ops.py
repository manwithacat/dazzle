"""Tests for dazzle db status/verify/reset/cleanup CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from dazzle.cli.db import db_app

runner = CliRunner()


class TestDbStatusCommand:
    @patch("dazzle.cli.db.asyncio.run")
    @patch("dazzle.cli.db.load_project_appspec")
    def test_status_shows_entities(self, mock_load: MagicMock, mock_run: MagicMock) -> None:
        appspec = MagicMock()
        e1 = MagicMock()
        e1.name = "Task"
        appspec.domain.entities = [e1]
        mock_load.return_value = appspec

        mock_run.return_value = {
            "entities": [{"name": "Task", "table": "task", "rows": 42, "error": None}],
            "total_entities": 1,
            "total_rows": 42,
            "database_size": "1 MB",
        }

        result = runner.invoke(db_app, ["status"])
        assert result.exit_code == 0
        assert "Task" in result.output
        assert "42" in result.output


class TestDbVerifyCommand:
    @patch("dazzle.cli.db.asyncio.run")
    @patch("dazzle.cli.db.load_project_appspec")
    def test_verify_shows_results(self, mock_load: MagicMock, mock_run: MagicMock) -> None:
        appspec = MagicMock()
        appspec.domain.entities = []
        mock_load.return_value = appspec

        mock_run.return_value = {
            "checks": [],
            "total_issues": 0,
        }

        result = runner.invoke(db_app, ["verify"])
        assert result.exit_code == 0
        assert (
            "0" in result.output
            or "issues" in result.output.lower()
            or "valid" in result.output.lower()
        )


class TestDbResetCommand:
    @patch("dazzle.cli.db.asyncio.run")
    @patch("dazzle.cli.db.load_project_appspec")
    def test_reset_dry_run(self, mock_load: MagicMock, mock_run: MagicMock) -> None:
        appspec = MagicMock()
        e1 = MagicMock()
        e1.name = "Task"
        appspec.domain.entities = [e1]
        mock_load.return_value = appspec

        mock_run.return_value = {
            "dry_run": True,
            "would_truncate": 1,
            "total_rows": 42,
            "tables": [{"name": "Task", "table": "task", "rows": 42}],
            "preserved": [],
        }

        result = runner.invoke(db_app, ["reset", "--dry-run"])
        assert result.exit_code == 0
        assert "42" in result.output


class TestDbCleanupCommand:
    @patch("dazzle.cli.db.asyncio.run")
    @patch("dazzle.cli.db.load_project_appspec")
    def test_cleanup_dry_run(self, mock_load: MagicMock, mock_run: MagicMock) -> None:
        appspec = MagicMock()
        appspec.domain.entities = []
        mock_load.return_value = appspec

        mock_run.return_value = {
            "dry_run": True,
            "would_delete": 0,
            "findings": [],
        }

        result = runner.invoke(db_app, ["cleanup", "--dry-run"])
        assert result.exit_code == 0
