"""#1390 — `dazzle db migrate` reconciliation + `--sql` refuse-cleanly behaviour.

The real reconcile/stamp round-trip is proven against Postgres in
``tests/integration/test_migrate_autostamp_pg.py``. These unit tests pin the
CLI control flow without a DB by patching the introspection probes:

  * ``--sql`` in the empty-`alembic_version` + materialized state refuses cleanly
    (exit 1, directed message) instead of crashing with ``NoInspectionAvailable``.
  * the apply path runs the auto-stamp reconciliation before autogenerate.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from dazzle.cli.db import db_app

runner = CliRunner()


class TestMigrateSqlRefusesCleanly:
    @patch("dazzle.cli.db._schema_is_materialized", return_value=True)
    @patch("dazzle.cli.db._alembic_version_is_empty", return_value=True)
    @patch("dazzle.cli.db._get_alembic_cfg")
    @patch("dazzle.cli.db._resolve_url", return_value="postgresql+psycopg://x/y")
    def test_sql_empty_materialized_refuses(
        self,
        _url: MagicMock,
        _cfg: MagicMock,
        _empty: MagicMock,
        _mat: MagicMock,
    ) -> None:
        result = runner.invoke(db_app, ["migrate", "--sql"])
        assert result.exit_code == 1
        assert "Offline --sql preview isn't available" in result.output
        # It must NOT have attempted the crashing offline replay.

    @patch("dazzle.cli.db._schema_is_materialized", return_value=False)
    @patch("dazzle.cli.db._alembic_version_is_empty", return_value=False)
    @patch("dazzle.cli.db._get_alembic_cfg")
    @patch("dazzle.cli.db._resolve_url", return_value="postgresql+psycopg://x/y")
    def test_sql_normal_state_renders(
        self,
        _url: MagicMock,
        _cfg: MagicMock,
        _empty: MagicMock,
        _mat: MagicMock,
    ) -> None:
        with patch("alembic.command.upgrade") as up:
            result = runner.invoke(db_app, ["migrate", "--sql"])
        assert result.exit_code == 0
        up.assert_called_once()
        # sql=True is forwarded to the offline replay.
        assert up.call_args.kwargs.get("sql") is True

    @patch("dazzle.cli.db._schema_is_materialized", return_value=False)
    @patch("dazzle.cli.db._alembic_version_is_empty", return_value=False)
    @patch("dazzle.cli.db._get_alembic_cfg")
    @patch("dazzle.cli.db._resolve_url", return_value="postgresql+psycopg://x/y")
    def test_sql_offline_error_is_directed_not_traceback(
        self,
        _url: MagicMock,
        _cfg: MagicMock,
        _empty: MagicMock,
        _mat: MagicMock,
    ) -> None:
        with patch("alembic.command.upgrade", side_effect=RuntimeError("NoInspectionAvailable")):
            result = runner.invoke(db_app, ["migrate", "--sql"])
        assert result.exit_code == 1
        assert "Could not render migration SQL offline" in result.output


class TestMigrateApplyReconciles:
    @patch("dazzle.cli.db._autostamp_if_materialized", return_value=True)
    @patch("dazzle.cli.db._get_alembic_cfg")
    @patch("dazzle.cli.db._resolve_url", return_value="postgresql+psycopg://x/y")
    def test_apply_runs_autostamp_before_autogenerate(
        self, _url: MagicMock, _cfg: MagicMock, stamp: MagicMock
    ) -> None:
        with (
            patch("alembic.command.revision", return_value=None) as rev,
            patch("alembic.command.upgrade"),
        ):
            result = runner.invoke(db_app, ["migrate"])
        assert result.exit_code == 0
        stamp.assert_called_once()
        rev.assert_called_once()  # autogenerate still attempted after reconcile
