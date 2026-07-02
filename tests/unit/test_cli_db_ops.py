"""Tests for dazzle db CLI commands (status, verify, reset, cleanup, stamp, baseline)."""

from unittest.mock import DEFAULT, MagicMock, patch

import pytest
import sqlalchemy
from typer.testing import CliRunner

from dazzle.cli.db import (
    ALEMBIC_VERSION_NUM_MAX_LEN,
    _validate_revision_widths,
    _verify_snapshot_consistency,
    db_app,
)


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


class TestDbStatusCommand:
    @patch("dazzle.cli.db.asyncio.run", side_effect=_close_coro)
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
    @patch("dazzle.cli.db.asyncio.run", side_effect=_close_coro)
    @patch("dazzle.cli.db.load_project_appspec")
    def test_verify_shows_results(self, mock_load: MagicMock, mock_run: MagicMock) -> None:
        appspec = MagicMock()
        appspec.domain.entities = []
        mock_load.return_value = appspec

        # Post-#840 the runner returns {"fk": ..., "money": ...}; #1340 adds
        # "signable" (signable schema-drift); Phase D adds "rls" (RLS policy
        # drift) so all four appear in one output.
        mock_run.return_value = {
            "fk": {"checks": [], "total_issues": 0},
            "money": {
                "drifts": [],
                "drift_count": 0,
                "partial_count": 0,
                "applied_count": 0,
                "errors": [],
            },
            "signable": [],
            "rls": [],
        }

        result = runner.invoke(db_app, ["verify"])
        assert result.exit_code == 0
        assert (
            "0" in result.output
            or "issues" in result.output.lower()
            or "valid" in result.output.lower()
        )

    @patch("dazzle.cli.db.asyncio.run", side_effect=_close_coro)
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
        # #1035 (v0.67.21): money-drift findings now trigger exit 1 so
        # CI / nightly quality swarms can wire `dazzle db verify` without
        # a wrapper. Pre-fix the command exited 0 even when drift was
        # reported — the contradiction this issue called out.
        assert result.exit_code == 1
        assert "Company" in result.output
        assert "revenue" in result.output
        assert "--fix-money" in result.output


class TestDbResetCommand:
    @patch("dazzle.cli.db.asyncio.run", side_effect=_close_coro)
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
    @patch("dazzle.cli.db.asyncio.run", side_effect=_close_coro)
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
    @pytest.mark.parametrize(
        "revision",
        ["head", "6ff3f549985c"],
        ids=["test_stamp_head", "test_stamp_specific_revision"],
    )
    @patch("dazzle.cli.db._get_alembic_cfg")
    @patch("alembic.command.stamp")
    def test_stamp_revision(
        self, mock_stamp: MagicMock, mock_cfg: MagicMock, revision: str
    ) -> None:
        """'dazzle db stamp <rev>' forwards the revision arg to alembic.command.stamp."""
        result = runner.invoke(db_app, ["stamp", revision])
        assert result.exit_code == 0
        mock_stamp.assert_called_once_with(mock_cfg.return_value, revision)
        assert f"Stamped at: {revision}" in result.output

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


class TestDbBaselineCommand:
    @patch("alembic.command.revision")
    @patch("dazzle.http.alembic.metadata_loader.load_target_metadata")
    @patch("dazzle.cli.db._get_alembic_cfg")
    @patch("dazzle.cli.db._resolve_url", return_value="")
    def test_baseline_metadata_path_no_alembic_context_crash(
        self,
        mock_url: MagicMock,
        mock_cfg: MagicMock,
        mock_load_metadata: MagicMock,
        mock_revision: MagicMock,
    ) -> None:
        """`dazzle db baseline` loads DSL metadata without an active Alembic context.

        Regression for the AttributeError crash: importing
        ``dazzle.http.alembic.env`` runs ``config = context.config`` at module
        level, which fails outside an Alembic run. ``baseline_command`` must
        instead call the side-effect-free ``metadata_loader``. This test fails
        if anyone re-introduces the ``env`` import — the patch target
        ``dazzle.http.alembic.metadata_loader.load_target_metadata`` would no
        longer intercept the call.
        """
        # Fake metadata with one table — the non-empty path.
        metadata = sqlalchemy.MetaData()
        sqlalchemy.Table("Task", metadata, sqlalchemy.Column("id", sqlalchemy.Integer))
        mock_load_metadata.return_value = metadata

        rev = MagicMock()
        rev.revision = "abc123"
        mock_revision.return_value = rev

        result = runner.invoke(db_app, ["baseline"])

        assert result.exit_code == 0, result.output
        assert "AttributeError" not in result.output
        assert "DSL declares 1 tables" in result.output
        mock_load_metadata.assert_called_once()

    @patch("alembic.command.revision")
    @patch("dazzle.http.alembic.metadata_loader.load_target_metadata")
    @patch("dazzle.cli.db._get_alembic_cfg")
    @patch("dazzle.cli.db._resolve_url", return_value="")
    def test_baseline_real_dsl_error_stops_command(
        self,
        mock_url: MagicMock,
        mock_cfg: MagicMock,
        mock_load_metadata: MagicMock,
        mock_revision: MagicMock,
    ) -> None:
        """A genuine DSL load error aborts baseline instead of being swallowed.

        Proceeding against empty metadata would autogenerate a migration that
        drops every table — so a ParseError/LinkError must exit non-zero.
        """
        mock_load_metadata.side_effect = ValueError("DSL parse failed")

        result = runner.invoke(db_app, ["baseline"])

        assert result.exit_code == 1
        assert "DSL metadata load failed" in result.output
        # The command must NOT have proceeded to autogenerate.
        mock_revision.assert_not_called()


# ---------------------------------------------------------------------------
# #1282 — pre-upgrade revision-width validation
# ---------------------------------------------------------------------------


class TestValidateRevisionWidths1282:
    """`alembic_version.version_num` is VARCHAR(128) after migration 0004.
    `_validate_revision_widths` walks every revision in the chain and
    fails fast if any id would overflow that column — otherwise the
    DDL applies and the `UPDATE alembic_version` truncates mid-upgrade,
    leaving schema-vs-version-state divergent (#1282).
    """

    def _stub_cfg(self, revision_ids: list[str]) -> MagicMock:
        """Build a mock cfg whose ScriptDirectory enumerates `revision_ids`."""
        cfg = MagicMock()
        return cfg

    def _make_mock_revisions(self, ids: list[str]) -> list[MagicMock]:
        revs = []
        for rid in ids:
            r = MagicMock()
            r.revision = rid
            revs.append(r)
        return revs

    def test_accepts_short_revision_ids(self) -> None:
        """Standard revision ids well under the cap pass cleanly."""
        ids = ["0001_baseline", "0002_short", "0003_another_short_one"]
        with patch("alembic.script.ScriptDirectory.from_config") as mock_sd:
            mock_sd.return_value.walk_revisions.return_value = self._make_mock_revisions(ids)
            # Should not raise.
            _validate_revision_widths(MagicMock(), "head")

    def test_accepts_revision_id_exactly_at_cap(self) -> None:
        """Boundary: an id of exactly ALEMBIC_VERSION_NUM_MAX_LEN chars
        fits — the check is `>` not `>=`."""
        cap_id = "x" * ALEMBIC_VERSION_NUM_MAX_LEN
        with patch("alembic.script.ScriptDirectory.from_config") as mock_sd:
            mock_sd.return_value.walk_revisions.return_value = self._make_mock_revisions([cap_id])
            _validate_revision_widths(MagicMock(), "head")  # no raise

    def test_rejects_revision_id_one_over_cap(self) -> None:
        """An id 1 char over the cap is rejected upfront with a clear
        message; no DDL fires."""
        over_id = "x" * (ALEMBIC_VERSION_NUM_MAX_LEN + 1)
        with patch("alembic.script.ScriptDirectory.from_config") as mock_sd:
            mock_sd.return_value.walk_revisions.return_value = self._make_mock_revisions([over_id])
            with pytest.raises(RuntimeError, match="exceed"):
                _validate_revision_widths(MagicMock(), "head")

    def test_error_message_lists_every_offender(self) -> None:
        """When multiple ids overflow, the error names all of them so
        the user can rename in one pass."""
        ids = [
            "0001_short",
            "x" * 150,
            "0002_normal",
            "y" * 200,
        ]
        with patch("alembic.script.ScriptDirectory.from_config") as mock_sd:
            mock_sd.return_value.walk_revisions.return_value = self._make_mock_revisions(ids)
            with pytest.raises(RuntimeError) as exc_info:
                _validate_revision_widths(MagicMock(), "head")
        msg = str(exc_info.value)
        assert "2 revision id(s) exceed" in msg
        assert "150 chars" in msg
        assert "200 chars" in msg


class TestBaselineWidensVersionNum1282:
    """The squashed baseline (0019_process_runtime_tables, ADR-0044) carries the
    alembic_version widening that was formerly in the deleted migration 0004.
    Verify the widening is present in the baseline so the column always fits
    long revision ids (cap = ``ALEMBIC_VERSION_NUM_MAX_LEN``)."""

    def test_baseline_alters_version_num_to_128(self) -> None:
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        baseline = (
            repo_root
            / "src"
            / "dazzle"
            / "http"
            / "alembic"
            / "versions"
            / "0019_process_runtime_tables.py"
        )
        assert baseline.exists()
        text = baseline.read_text(encoding="utf-8")
        assert "VARCHAR(128)" in text
        assert "version_num" in text
        # Baseline is the chain root — no predecessor.
        assert "down_revision = None" in text


class TestPytestImports1282:
    """Sanity test — pytest + patch must be importable for the new tests
    above to run. Also pins that the cap matches the baseline."""

    def test_cap_matches_baseline(self) -> None:
        assert ALEMBIC_VERSION_NUM_MAX_LEN == 128


# ---------------------------------------------------------------------------
# Task 6.1 — post-generation snapshot consistency verification check
# ---------------------------------------------------------------------------


class TestVerifySnapshotConsistency:
    """``_verify_snapshot_consistency`` is a warn-only internal-consistency check
    that runs after the engine embeds ``SCHEMA_SNAPSHOT`` into a generated file.

    It compares the snapshot literal stashed on ``cfg.attributes`` (the
    engine's intended post-state) against ``project_current()`` (the live DSL
    projection).  A divergence means the engine's embedded post-state doesn't
    match what the DSL says — i.e. a concurrent DSL change raced the revision,
    or an engine bug.

    Invariants:
    - WARNS (logger.warning) when the embedded snapshot differs from project_current().
    - Does NOT warn on the happy path (snapshots agree).
    - NEVER raises — always returns None.
    - NEVER calls project_current() when there is no snapshot on cfg (no-op for
      legacy / empty / suppressed revisions).
    """

    def _make_rev(self) -> MagicMock:
        rev = MagicMock()
        rev.path = "/fake/versions/abc123_add_task.py"
        return rev

    def _make_cfg(self, snapshot_literal: str | None) -> MagicMock:
        cfg = MagicMock()
        cfg.attributes = {}
        if snapshot_literal is not None:
            cfg.attributes["dazzle_schema_snapshot"] = snapshot_literal
        return cfg

    def test_warns_when_snapshots_diverge(self, caplog: pytest.LogCaptureFixture) -> None:
        """When the embedded snapshot differs from project_current(), a warning is logged."""
        import logging

        embedded_literal = "{'Task': {'columns': {'id': {'default': None, 'nullable': False, 'pk': True, 'type': 'uuid'}}, 'fks': {}, 'indexes': [], 'uniques': []}}"
        # project_current() returns a DIFFERENT snapshot (extra table)
        live_snapshot = {
            "Task": {
                "columns": {
                    "id": {"default": None, "nullable": False, "pk": True, "type": "uuid"},
                    "title": {"default": None, "nullable": False, "pk": False, "type": "text"},
                },
                "fks": {},
                "indexes": [],
                "uniques": [],
            }
        }

        with patch(
            "dazzle.db.schema_snapshot.project_current", return_value=live_snapshot
        ) as mock_pc:
            with caplog.at_level(logging.WARNING, logger="dazzle.cli.db"):
                _verify_snapshot_consistency(self._make_rev(), self._make_cfg(embedded_literal))

        mock_pc.assert_called_once()
        assert any(
            "snapshot" in rec.message.lower() and rec.levelno == logging.WARNING
            for rec in caplog.records
        ), f"Expected a WARNING about snapshot divergence; got: {caplog.records}"

    def test_no_warn_when_snapshots_agree(self, caplog: pytest.LogCaptureFixture) -> None:
        """When embedded snapshot matches project_current(), no warning is logged."""
        import logging

        snapshot_dict = {
            "Task": {
                "columns": {"id": {"default": None, "nullable": False, "pk": True, "type": "uuid"}},
                "fks": {},
                "indexes": [],
                "uniques": [],
            }
        }
        from dazzle.db.schema_snapshot import render_snapshot_literal

        embedded_literal = render_snapshot_literal(snapshot_dict)

        with patch("dazzle.db.schema_snapshot.project_current", return_value=snapshot_dict):
            with caplog.at_level(logging.WARNING, logger="dazzle.cli.db"):
                _verify_snapshot_consistency(self._make_rev(), self._make_cfg(embedded_literal))

        assert not any(rec.levelno >= logging.WARNING for rec in caplog.records), (
            f"Unexpected warning on happy path: {caplog.records}"
        )

    def test_no_op_when_no_snapshot_on_cfg(self, caplog: pytest.LogCaptureFixture) -> None:
        """When cfg carries no dazzle_schema_snapshot (legacy / suppressed path),
        project_current() is never called and no warning is logged."""
        import logging

        with patch("dazzle.db.schema_snapshot.project_current") as mock_pc:
            with caplog.at_level(logging.WARNING, logger="dazzle.cli.db"):
                _verify_snapshot_consistency(self._make_rev(), self._make_cfg(None))

        mock_pc.assert_not_called()
        assert not any(rec.levelno >= logging.WARNING for rec in caplog.records)

    def test_never_raises_on_project_current_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When project_current() raises (no project / broken DSL), the check
        swallows the exception and returns None — never blocks db revision."""
        import logging

        embedded_literal = "{'Task': {}}"

        with patch(
            "dazzle.db.schema_snapshot.project_current",
            side_effect=RuntimeError("no dazzle.toml"),
        ):
            with caplog.at_level(logging.DEBUG, logger="dazzle.cli.db"):
                result = _verify_snapshot_consistency(
                    self._make_rev(), self._make_cfg(embedded_literal)
                )

        assert result is None

    def test_never_raises_on_none_rev(self, caplog: pytest.LogCaptureFixture) -> None:
        """When rev is None (Alembic produced no file), the check is a no-op."""
        import logging

        with patch("dazzle.db.schema_snapshot.project_current") as mock_pc:
            with caplog.at_level(logging.WARNING, logger="dazzle.cli.db"):
                result = _verify_snapshot_consistency(None, self._make_cfg("{'x': {}}"))

        mock_pc.assert_not_called()
        assert result is None


# ---------------------------------------------------------------------------
# Task 6.2 — snapshot-baseline re-stamp guard
# ---------------------------------------------------------------------------


class TestSnapshotBaselineReStampGuard:
    """``snapshot_baseline_command`` must be a no-op when the head already
    carries SCHEMA_SNAPSHOT.  Running it twice (or on a project whose head was
    generated by the engine) must print a clear message and NOT write a new
    revision file.
    """

    def _make_script_dir_with_snapshot(self, snapshot: dict) -> MagicMock:
        """Mock ScriptDirectory whose head module exposes a non-empty SCHEMA_SNAPSHOT."""
        head_module = MagicMock()
        head_module.SCHEMA_SNAPSHOT = snapshot
        head_script = MagicMock()
        head_script.module = head_module
        script_dir = MagicMock()
        script_dir.get_heads.return_value = ["abc123"]
        script_dir.get_revision.return_value = head_script
        return script_dir

    def _make_script_dir_no_snapshot(self) -> MagicMock:
        """Mock ScriptDirectory whose head module has NO SCHEMA_SNAPSHOT attribute."""
        head_module = MagicMock(spec=[])  # no attributes → hasattr returns False
        head_script = MagicMock()
        head_script.module = head_module
        script_dir = MagicMock()
        script_dir.get_heads.return_value = ["abc123"]
        script_dir.get_revision.return_value = head_script
        return script_dir

    @patch("alembic.command.revision")
    @patch("alembic.script.ScriptDirectory.from_config")
    @patch("dazzle.cli.db._get_heads", return_value=["abc123"])
    @patch("dazzle.cli.db._get_alembic_cfg")
    @patch("dazzle.cli.db._get_project_versions_dir")
    def test_noop_when_head_already_has_snapshot(
        self,
        mock_versions_dir: MagicMock,
        mock_cfg: MagicMock,
        mock_heads: MagicMock,
        mock_sd_from_cfg: MagicMock,
        mock_revision: MagicMock,
        tmp_path: object,
    ) -> None:
        """When head already carries SCHEMA_SNAPSHOT, no new revision is written."""
        existing_snapshot = {
            "task": {
                "columns": {"id": {"type": "uuid", "nullable": False, "default": None, "pk": True}},
                "fks": {},
                "uniques": [],
                "indexes": [],
            }
        }
        mock_sd_from_cfg.return_value = self._make_script_dir_with_snapshot(existing_snapshot)
        mock_versions_dir.return_value = tmp_path

        result = runner.invoke(db_app, ["snapshot-baseline"])

        assert result.exit_code == 0, result.output
        assert "already carries SCHEMA_SNAPSHOT" in result.output
        assert "nothing to do" in result.output
        # The crucial assertion: no revision file was written.
        mock_revision.assert_not_called()

    @patch("alembic.command.revision")
    @patch("alembic.script.ScriptDirectory.from_config")
    @patch("dazzle.cli.db._get_heads", return_value=["abc123"])
    @patch("dazzle.cli.db._get_alembic_cfg")
    @patch("dazzle.cli.db._get_project_versions_dir")
    @patch("dazzle.db.schema_snapshot.project_current")
    @patch("dazzle.db.schema_snapshot.render_snapshot_literal", return_value="{'task': {}}")
    def test_proceeds_when_head_has_no_snapshot(
        self,
        mock_render: MagicMock,
        mock_project_current: MagicMock,
        mock_versions_dir: MagicMock,
        mock_cfg: MagicMock,
        mock_heads: MagicMock,
        mock_sd_from_cfg: MagicMock,
        mock_revision: MagicMock,
        tmp_path: object,
    ) -> None:
        """When head has no SCHEMA_SNAPSHOT, snapshot-baseline proceeds normally."""
        mock_sd_from_cfg.return_value = self._make_script_dir_no_snapshot()
        mock_versions_dir.return_value = tmp_path
        mock_project_current.return_value = {"task": {}}

        rev = MagicMock()
        rev.path = str(tmp_path / "abc_snapshot_baseline.py")
        # Write a stub file so _inject_schema_snapshot finds it.
        (tmp_path / "abc_snapshot_baseline.py").write_text("# stub\n", encoding="utf-8")
        rev.path = str(tmp_path / "abc_snapshot_baseline.py")
        mock_revision.return_value = rev

        result = runner.invoke(db_app, ["snapshot-baseline"])

        assert result.exit_code == 0, result.output
        assert "already carries SCHEMA_SNAPSHOT" not in result.output
        mock_revision.assert_called_once()
