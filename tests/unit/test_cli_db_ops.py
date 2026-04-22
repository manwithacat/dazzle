"""Tests for dazzle db CLI commands (status, verify, reset, cleanup, stamp)."""

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

        # Post-#840 the runner returns {"fk": ..., "money": ...} so both
        # checks appear in one verify output.
        mock_run.return_value = {
            "fk": {"checks": [], "total_issues": 0},
            "money": {
                "drifts": [],
                "drift_count": 0,
                "partial_count": 0,
                "applied_count": 0,
                "errors": [],
            },
        }

        result = runner.invoke(db_app, ["verify"])
        assert result.exit_code == 0
        assert (
            "0" in result.output
            or "issues" in result.output.lower()
            or "valid" in result.output.lower()
        )

    @patch("dazzle.cli.db.asyncio.run")
    @patch("dazzle.cli.db.load_project_appspec")
    def test_verify_reports_money_drift(self, mock_load: MagicMock, mock_run: MagicMock) -> None:
        """Drift rows are printed to the user with the repair SQL."""
        appspec = MagicMock()
        appspec.domain.entities = []
        mock_load.return_value = appspec

        mock_run.return_value = {
            "fk": {"checks": [], "total_issues": 0},
            "money": {
                "drifts": [
                    {
                        "entity": "Company",
                        "field": "revenue",
                        "currency": "GBP",
                        "legacy_type": "double precision",
                        "status": "drift",
                        "repair_sql": (
                            'ALTER TABLE "Company" ADD COLUMN "revenue_minor" BIGINT;\n'
                            'ALTER TABLE "Company" ADD COLUMN "revenue_currency" TEXT;\n'
                            'UPDATE "Company" SET "revenue_minor" = ROUND("revenue"*100)::bigint, '
                            '"revenue_currency" = \'GBP\' WHERE "revenue" IS NOT NULL;\n'
                            'ALTER TABLE "Company" DROP COLUMN "revenue";'
                        ),
                    }
                ],
                "drift_count": 1,
                "partial_count": 0,
                "applied_count": 0,
                "errors": [],
            },
        }

        result = runner.invoke(db_app, ["verify"])
        assert result.exit_code == 0
        assert "Company" in result.output
        assert "revenue" in result.output
        assert "--fix-money" in result.output


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


class TestDbStampCommand:
    @patch("dazzle.cli.db._get_alembic_cfg")
    @patch("alembic.command.stamp")
    def test_stamp_head(self, mock_stamp: MagicMock, mock_cfg: MagicMock) -> None:
        """'dazzle db stamp head' calls alembic.command.stamp with 'head'."""
        result = runner.invoke(db_app, ["stamp", "head"])
        assert result.exit_code == 0
        mock_stamp.assert_called_once_with(mock_cfg.return_value, "head")
        assert "Stamped at: head" in result.output

    @patch("dazzle.cli.db._get_alembic_cfg")
    @patch("alembic.command.stamp")
    def test_stamp_specific_revision(self, mock_stamp: MagicMock, mock_cfg: MagicMock) -> None:
        """'dazzle db stamp <rev>' calls alembic.command.stamp with that rev."""
        result = runner.invoke(db_app, ["stamp", "6ff3f549985c"])
        assert result.exit_code == 0
        mock_stamp.assert_called_once_with(mock_cfg.return_value, "6ff3f549985c")

    def test_stamp_requires_revision_arg(self) -> None:
        """'dazzle db stamp' without argument shows error."""
        result = runner.invoke(db_app, ["stamp"])
        assert result.exit_code != 0

    @patch("dazzle.cli.db._get_alembic_cfg")
    @patch("alembic.command.stamp", side_effect=Exception("DB unreachable"))
    def test_stamp_failure(self, mock_stamp: MagicMock, mock_cfg: MagicMock) -> None:
        """Stamp failure prints error and exits with code 1."""
        result = runner.invoke(db_app, ["stamp", "head"])
        assert result.exit_code == 1
        assert "Stamp failed" in result.output
