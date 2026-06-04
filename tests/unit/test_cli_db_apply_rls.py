"""Tests for `dazzle db apply-rls` command wiring (RLS tenancy Phase D).

These exercise the command's dispatch logic only (typer runner + stubbed
appspec/connection-runner). The real-PG apply proof is in
``tests/integration/test_rls_apply_and_drift_pg.py`` (Task 4).
"""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from dazzle.cli.db import db_app

runner = CliRunner()


def _shared_schema_appspec() -> MagicMock:
    """A stub appspec whose tenancy isolation is shared_schema (row-level)."""
    from dazzle.core.ir import TenancyMode

    appspec = MagicMock()
    appspec.tenancy.isolation.mode = TenancyMode.SHARED_SCHEMA
    appspec.domain.entities = []
    return appspec


def _non_tenant_appspec() -> MagicMock:
    """A stub appspec with no row-level tenancy."""
    appspec = MagicMock()
    appspec.tenancy = None
    appspec.domain.entities = []
    return appspec


class TestApplyRlsNonTenant:
    @patch("dazzle.cli.db.load_project_appspec")
    def test_non_tenant_app_is_noop_exit_zero(self, mock_load: MagicMock) -> None:
        mock_load.return_value = _non_tenant_appspec()

        result = runner.invoke(db_app, ["apply-rls"])

        assert result.exit_code == 0
        assert "nothing to apply" in result.output.lower()

    @patch("dazzle.cli.db.load_project_appspec")
    def test_non_tenant_app_json(self, mock_load: MagicMock) -> None:
        mock_load.return_value = _non_tenant_appspec()

        result = runner.invoke(db_app, ["apply-rls", "--json"])

        assert result.exit_code == 0
        assert '"applied": 0' in result.output


class TestApplyRlsSharedSchema:
    @patch("dazzle.cli.db.asyncio.run")
    @patch("dazzle.cli.db._resolve_url")
    @patch("dazzle.cli.db.load_project_appspec")
    def test_shared_schema_invokes_apply(
        self,
        mock_load: MagicMock,
        mock_resolve: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        mock_load.return_value = _shared_schema_appspec()
        mock_resolve.return_value = "postgresql://localhost/db"
        # asyncio.run wraps _run_with_connection(... apply_rls_policies ...);
        # stub the applied-statement count it ultimately returns.
        mock_run.return_value = 7

        result = runner.invoke(db_app, ["apply-rls"])

        assert result.exit_code == 0
        # The connection runner was driven (the apply path, not the no-op gate).
        assert mock_run.called
        assert "Applied 7 RLS policy statements" in result.output
        # The owner-role note is surfaced.
        assert "owns the tables" in result.output

    @patch("dazzle.cli.db.asyncio.run")
    @patch("dazzle.cli.db._resolve_url")
    @patch("dazzle.cli.db.load_project_appspec")
    def test_shared_schema_json_reports_count(
        self,
        mock_load: MagicMock,
        mock_resolve: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        mock_load.return_value = _shared_schema_appspec()
        mock_resolve.return_value = "postgresql://localhost/db"
        mock_run.return_value = 1

        result = runner.invoke(db_app, ["apply-rls", "--json"])

        assert result.exit_code == 0
        assert '"applied": 1' in result.output
