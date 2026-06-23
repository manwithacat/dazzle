"""Regression gate for GitHub issue #1309.

Shipping the framework baseline migrations in the wheel (#1308, v0.80.59) added
a second alembic head for any project whose own first migration is a *parallel
root* (`down_revision = None`, authored before the framework shipped baselines).
`dazzle db upgrade head` then failed with "Multiple head revisions" and the
Heroku release phase broke.

Fixes under test:
1. `dazzle db reconcile-baseline` generates a project-side merge migration
   collapsing the parallel heads into one.
2. `dazzle db upgrade head` / `revision` give actionable reconcile guidance
   instead of alembic's raw multi-head error.

Note: the old Part 1 (0001_framework_baseline idempotency guard) was removed
when 0001-0018 were squashed into 0019_process_runtime_tables (ADR-0044).  The
squashed baseline uses IF NOT EXISTS throughout — no separate early-exit guard
needed.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FRAMEWORK_ALEMBIC = _REPO_ROOT / "src/dazzle/http/alembic"


# ---------------------------------------------------------------------------
# Parts 2 & 3 — parallel-head detection, guard, and reconcile
# ---------------------------------------------------------------------------


def _write_rev(d: Path, rid: str, down: str | None) -> None:
    (d / f"{rid}.py").write_text(
        f'"""r"""\nrevision = {rid!r}\ndown_revision = {down!r}\n'
        f"branch_labels = None\ndepends_on = None\n"
        f"def upgrade():\n    pass\ndef downgrade():\n    pass\n"
    )


def _two_root_cfg(tmp: Path) -> tuple[Any, Path]:
    """Build an alembic Config with two parallel roots (framework + project),
    mirroring the real `version_locations` chaining. Returns (cfg, project_dir).
    """
    from alembic.config import Config

    script_loc = tmp / "alembic"
    script_loc.mkdir()
    shutil.copy(_FRAMEWORK_ALEMBIC / "script.py.mako", script_loc / "script.py.mako")
    fw = tmp / "fw_versions"
    fw.mkdir()
    proj = tmp / "proj_versions"
    proj.mkdir()
    # Framework baseline root (the real revision id the guard recognises).
    _write_rev(fw, "0001_framework_baseline", None)
    # Project baseline — a SECOND parallel root.
    _write_rev(proj, "proj_base", None)

    cfg = Config()
    cfg.set_main_option("script_location", str(script_loc))
    cfg.set_main_option("version_locations", f"{fw} {proj}")
    return cfg, proj


class TestHeadGuards1309:
    def test_get_heads_returns_both_roots(self, tmp_path: Path) -> None:
        from dazzle.cli.db import _get_heads

        cfg, _ = _two_root_cfg(tmp_path)
        assert set(_get_heads(cfg)) == {"0001_framework_baseline", "proj_base"}

    def test_guard_raises_on_parallel_heads(self, tmp_path: Path) -> None:
        from dazzle.cli.db import _guard_single_head

        cfg, _ = _two_root_cfg(tmp_path)
        with pytest.raises(RuntimeError, match="reconcile-baseline"):
            _guard_single_head(cfg, "head")

    def test_guard_message_names_parallel_baseline_roots(self, tmp_path: Path) -> None:
        from dazzle.cli.db import _guard_single_head

        cfg, _ = _two_root_cfg(tmp_path)
        with pytest.raises(RuntimeError, match="parallel baseline roots"):
            _guard_single_head(cfg, "head")

    def test_guard_traces_framework_root_when_head_is_descendant(self, tmp_path: Path) -> None:
        """The REAL #1309 case: the framework HEAD is `0004…`, not `0001` —
        so the guard must trace ancestry to recognise the framework root, not
        just match the head id directly."""
        from alembic.config import Config

        from dazzle.cli.db import _guard_single_head

        script_loc = tmp_path / "alembic"
        script_loc.mkdir()
        shutil.copy(_FRAMEWORK_ALEMBIC / "script.py.mako", script_loc / "script.py.mako")
        fw = tmp_path / "fw"
        fw.mkdir()
        proj = tmp_path / "proj"
        proj.mkdir()
        # Framework chain 0001 -> 0004-ish (head is the descendant, not 0001).
        _write_rev(fw, "0001_framework_baseline", None)
        _write_rev(fw, "0004_widen_alembic_version_num", "0001_framework_baseline")
        _write_rev(proj, "proj_base", None)
        cfg = Config()
        cfg.set_main_option("script_location", str(script_loc))
        cfg.set_main_option("version_locations", f"{fw} {proj}")

        from dazzle.cli.db import _get_heads

        assert set(_get_heads(cfg)) == {"0004_widen_alembic_version_num", "proj_base"}
        with pytest.raises(RuntimeError, match="parallel baseline roots"):
            _guard_single_head(cfg, "head")

    def test_guard_ignores_explicit_heads_target(self, tmp_path: Path) -> None:
        """An explicit `upgrade heads` is the user opting into all heads — don't
        block it."""
        from dazzle.cli.db import _guard_single_head

        cfg, _ = _two_root_cfg(tmp_path)
        _guard_single_head(cfg, "heads")  # must not raise

    def test_guard_noop_on_single_head(self, tmp_path: Path) -> None:
        from alembic.config import Config

        from dazzle.cli.db import _guard_single_head

        script_loc = tmp_path / "alembic"
        script_loc.mkdir()
        shutil.copy(_FRAMEWORK_ALEMBIC / "script.py.mako", script_loc / "script.py.mako")
        v = tmp_path / "versions"
        v.mkdir()
        _write_rev(v, "0001_framework_baseline", None)
        cfg = Config()
        cfg.set_main_option("script_location", str(script_loc))
        cfg.set_main_option("version_locations", str(v))
        _guard_single_head(cfg, "head")  # single head → must not raise


class TestReconcileBaseline1309:
    def test_reconcile_collapses_two_heads_to_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`dazzle db reconcile-baseline` writes a merge migration into the
        PROJECT dir whose down_revision is the tuple of both heads, leaving a
        single head."""
        from alembic.script import ScriptDirectory

        import dazzle.cli.db as db

        cfg, proj = _two_root_cfg(tmp_path)
        monkeypatch.setattr(db, "_get_alembic_cfg", lambda: cfg)
        monkeypatch.setattr(db, "_get_project_versions_dir", lambda: proj)

        db.reconcile_baseline_command()

        # Exactly one new merge file landed in the project dir.
        files = {p.name for p in proj.glob("*.py")}
        assert "proj_base.py" in files
        merge_files = files - {"proj_base.py"}
        assert len(merge_files) == 1, f"expected 1 merge file, got {merge_files}"

        # Heads collapsed to one, and it's a true merge (tuple down_revision).
        script = ScriptDirectory.from_config(cfg)
        heads = list(script.get_heads())
        assert len(heads) == 1
        merge = script.get_revision(heads[0])
        assert set(merge.down_revision) == {"0001_framework_baseline", "proj_base"}

    def test_reconcile_noop_on_single_head(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from alembic.config import Config

        import dazzle.cli.db as db

        script_loc = tmp_path / "alembic"
        script_loc.mkdir()
        shutil.copy(_FRAMEWORK_ALEMBIC / "script.py.mako", script_loc / "script.py.mako")
        v = tmp_path / "versions"
        v.mkdir()
        _write_rev(v, "only_head", None)
        cfg = Config()
        cfg.set_main_option("script_location", str(script_loc))
        cfg.set_main_option("version_locations", str(v))
        monkeypatch.setattr(db, "_get_alembic_cfg", lambda: cfg)
        monkeypatch.setattr(db, "_get_project_versions_dir", lambda: v)

        db.reconcile_baseline_command()
        # No new file written.
        assert {p.name for p in v.glob("*.py")} == {"only_head.py"}
