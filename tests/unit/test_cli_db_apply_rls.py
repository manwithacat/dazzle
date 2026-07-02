"""Tests for `dazzle db apply-rls` command wiring (RLS tenancy Phase D).

These exercise the command's dispatch logic only (typer runner + stubbed
appspec/connection-runner). The real-PG apply proof is in
``tests/integration/test_rls_apply_and_drift_pg.py`` (Task 4).
"""

from unittest.mock import DEFAULT, MagicMock, patch

from typer.testing import CliRunner

from dazzle.cli.db import db_app


def _close_coro(coro):  # pragma: no cover - test plumbing
    """Consume the coroutine handed to the mocked asyncio.run.

    The production code builds a real ``_run_with_connection(...)`` coroutine
    and passes it to ``asyncio.run``; a bare MagicMock drops it un-awaited
    (RuntimeWarning). Returning DEFAULT keeps ``mock_run.return_value``
    semantics intact.
    """
    coro.close()
    return DEFAULT


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
    @patch("dazzle.cli.db.asyncio.run", side_effect=_close_coro)
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

    @patch("dazzle.cli.db.asyncio.run", side_effect=_close_coro)
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

    @patch("dazzle.cli.db.asyncio.run", side_effect=_close_coro)
    @patch("dazzle.cli.db._resolve_url")
    @patch("dazzle.cli.db.load_project_appspec")
    def test_apply_failure_exits_nonzero_with_owner_hint(
        self,
        mock_load: MagicMock,
        mock_resolve: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        # The likeliest prod failure: running as the non-owner dazzle_app role →
        # InsufficientPrivilege. The command must exit non-zero with a clean
        # owner-role hint, not dump a raw driver traceback.
        mock_load.return_value = _shared_schema_appspec()
        mock_resolve.return_value = "postgresql://localhost/db"

        def _close_then_raise(coro):  # close the coro, then simulate the driver error
            coro.close()
            raise RuntimeError("permission denied for table Project")

        mock_run.side_effect = _close_then_raise

        result = runner.invoke(db_app, ["apply-rls"])

        assert result.exit_code == 1
        assert mock_run.called
        assert "Failed to apply RLS policies" in result.output
        assert "permission denied" in result.output
        # The owner-role hint is surfaced (Rich word-wraps; match a fragment).
        assert "OWNS the tables" in result.output


class TestDbUpgradeRlsHook:
    """The `dazzle db upgrade` post-migration RLS hook (_apply_rls_after_upgrade).

    alembic's `command.upgrade` + the DB-touching revision helpers are mocked so
    the migration "succeeds" without a real DB; the connection runner
    (`asyncio.run`, which wraps `_run_with_connection(... apply_rls_policies ...)`)
    is mocked to control success-vs-raise. We assert on whether that runner was
    invoked (= the apply path was reached) — consistent with the existing db CLI
    mocking style.
    """

    @patch("dazzle.cli.db.asyncio.run", side_effect=_close_coro)
    @patch("dazzle.cli.db.load_project_appspec")
    @patch("dazzle.cli.db._safe_current_revision")
    @patch("dazzle.cli.db._validate_revision_widths")
    @patch("dazzle.cli.db._guard_single_head")
    @patch("dazzle.cli.db._get_alembic_cfg")
    @patch("alembic.command.upgrade")
    def test_non_shared_schema_skips_apply(
        self,
        mock_upgrade: MagicMock,
        mock_cfg: MagicMock,
        _guard: MagicMock,
        _widths: MagicMock,
        mock_rev: MagicMock,
        mock_load: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        # Migration "succeeds"; report path: before != after so it prints Upgraded.
        mock_cfg.return_value.get_main_option.return_value = "postgresql://localhost/db"
        mock_rev.side_effect = ["base", "head"]
        mock_load.return_value = _non_tenant_appspec()

        result = runner.invoke(db_app, ["upgrade"])

        assert result.exit_code == 0
        # No-op for a non-shared_schema app — the connection runner is NOT driven.
        assert not mock_run.called

    @patch("dazzle.cli.db.asyncio.run", side_effect=_close_coro)
    @patch("dazzle.cli.db.load_project_appspec")
    @patch("dazzle.cli.db._safe_current_revision")
    @patch("dazzle.cli.db._validate_revision_widths")
    @patch("dazzle.cli.db._guard_single_head")
    @patch("dazzle.cli.db._get_alembic_cfg")
    @patch("alembic.command.upgrade")
    def test_no_rls_flag_skips_apply(
        self,
        mock_upgrade: MagicMock,
        mock_cfg: MagicMock,
        _guard: MagicMock,
        _widths: MagicMock,
        mock_rev: MagicMock,
        mock_load: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        mock_cfg.return_value.get_main_option.return_value = "postgresql://localhost/db"
        mock_rev.side_effect = ["base", "head"]
        # Even on a shared_schema app, --no-rls must skip the apply entirely
        # (so load_project_appspec isn't even reached for the hook).
        mock_load.return_value = _shared_schema_appspec()

        result = runner.invoke(db_app, ["upgrade", "--no-rls"])

        assert result.exit_code == 0
        assert not mock_run.called

    @patch("dazzle.cli.db.asyncio.run", side_effect=_close_coro)
    @patch("dazzle.cli.db.load_project_appspec")
    @patch("dazzle.cli.db._safe_current_revision")
    @patch("dazzle.cli.db._validate_revision_widths")
    @patch("dazzle.cli.db._guard_single_head")
    @patch("dazzle.cli.db._get_alembic_cfg")
    @patch("alembic.command.upgrade")
    def test_apply_failure_exits_nonzero_and_surfaces_error(
        self,
        mock_upgrade: MagicMock,
        mock_cfg: MagicMock,
        _guard: MagicMock,
        _widths: MagicMock,
        mock_rev: MagicMock,
        mock_load: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        # The load-bearing branch: migration succeeded, but the RLS apply RAISES.
        # The command must exit non-zero and surface the error — never silently
        # leave a migrated-but-unenforced schema.
        mock_cfg.return_value.get_main_option.return_value = "postgresql://localhost/db"
        mock_rev.side_effect = ["base", "head"]
        mock_load.return_value = _shared_schema_appspec()

        def _close_then_raise(coro):  # close the coro, then simulate the driver error
            coro.close()
            raise RuntimeError("permission denied for table Project")

        mock_run.side_effect = _close_then_raise

        result = runner.invoke(db_app, ["upgrade"])

        assert result.exit_code == 1
        assert mock_run.called
        # The error is surfaced (not swallowed) with the operator remediation.
        # (Rich word-wraps console output, so match on un-split fragments rather
        # than the full unbroken sentence.)
        assert "applying RLS policies failed" in result.output
        assert "permission denied" in result.output
        assert "NOT enforced" in result.output
        assert "dazzle db apply-rls" in result.output

    @patch("dazzle.cli.db.asyncio.run", side_effect=_close_coro)
    @patch("dazzle.cli.db.load_project_appspec")
    @patch("dazzle.cli.db._safe_current_revision")
    @patch("dazzle.cli.db._validate_revision_widths")
    @patch("dazzle.cli.db._guard_single_head")
    @patch("dazzle.cli.db._get_alembic_cfg")
    @patch("alembic.command.upgrade")
    def test_happy_path_applies_and_exits_zero(
        self,
        mock_upgrade: MagicMock,
        mock_cfg: MagicMock,
        _guard: MagicMock,
        _widths: MagicMock,
        mock_rev: MagicMock,
        mock_load: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        mock_cfg.return_value.get_main_option.return_value = "postgresql://localhost/db"
        mock_rev.side_effect = ["base", "head"]
        mock_load.return_value = _shared_schema_appspec()
        mock_run.return_value = 5  # 5 RLS statements applied

        result = runner.invoke(db_app, ["upgrade"])

        assert result.exit_code == 0
        assert mock_run.called
        assert "Applied 5 RLS policy statements" in result.output
        assert "owner role" in result.output
