"""Unit tests for BaselineKey and BaselineManager."""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dazzle.e2e.baseline import (
    NO_FIXTURE_SENTINEL,
    BaselineKey,
    BaselineManager,
)
from dazzle.e2e.errors import BaselineBuildError, BaselineKeyError


class TestBaselineKey:
    def test_filename_format(self) -> None:
        key = BaselineKey(alembic_rev="abc123", fixture_hash="def4567890ab")
        assert key.filename() == "baseline-abc123-def4567890ab.sql.gz"

    def test_filename_truncates_fixture_hash_to_12(self) -> None:
        full_hash = "0" * 64
        key = BaselineKey(alembic_rev="rev", fixture_hash=full_hash)
        assert key.filename() == "baseline-rev-000000000000.sql.gz"

    def test_is_frozen(self) -> None:
        key = BaselineKey(alembic_rev="a", fixture_hash="b")
        with pytest.raises((AttributeError, TypeError)):
            key.alembic_rev = "x"  # type: ignore[misc]


@pytest.fixture(autouse=True)
def mock_pg_binaries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend pg_dump/pg_restore are always on PATH.

    BaselineManager instantiates a Snapshotter eagerly in __init__, which
    probes shutil.which. Without this fixture the whole test file crashes
    on CI runners that don't have PostgreSQL client tools installed.
    """
    monkeypatch.setattr(
        "dazzle.e2e.snapshot.shutil.which",
        lambda name: f"/usr/local/bin/{name}",
    )


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "example"
    root.mkdir()
    (root / ".dazzle").mkdir()
    return root


class TestBaselineManagerCurrentKey:
    def test_computes_key_with_fixture_files(self, project_root: Path) -> None:
        demo_dir = project_root / ".dazzle" / "demo"
        demo_dir.mkdir()
        (demo_dir / "fixture1.json").write_text("content-1")
        (demo_dir / "fixture2.json").write_text("content-2")

        manager = BaselineManager(project_root, "postgresql://localhost/test")
        with patch.object(manager, "_alembic_head", return_value="abc123"):
            key = manager.current_key()

        assert key.alembic_rev == "abc123"
        # Hash is sha256 of concatenated fixture contents (sorted by path)
        expected = hashlib.sha256()
        for name in sorted(["fixture1.json", "fixture2.json"]):
            expected.update((demo_dir / name).read_bytes())
        assert key.fixture_hash == expected.hexdigest()

    def test_computes_key_when_no_fixtures(self, project_root: Path) -> None:
        manager = BaselineManager(project_root, "postgresql://localhost/test")
        with patch.object(manager, "_alembic_head", return_value="r"):
            key = manager.current_key()

        expected = hashlib.sha256(NO_FIXTURE_SENTINEL.encode()).hexdigest()
        assert key.fixture_hash == expected

    def test_raises_baseline_key_error_when_alembic_missing(self, project_root: Path) -> None:
        manager = BaselineManager(project_root, "postgresql://localhost/test")
        with patch.object(manager, "_alembic_head", side_effect=BaselineKeyError("no config")):
            with pytest.raises(BaselineKeyError):
                manager.current_key()


class TestBaselineManagerPathFor:
    def test_path_under_project_baselines_dir(self, project_root: Path) -> None:
        manager = BaselineManager(project_root, "postgresql://localhost/test")
        key = BaselineKey(alembic_rev="rev", fixture_hash="abc123456789" + "0" * 52)
        path = manager.path_for(key)
        assert path == project_root / ".dazzle" / "baselines" / "baseline-rev-abc123456789.sql.gz"


class TestBaselineManagerEnsure:
    def test_no_op_when_file_exists(self, project_root: Path) -> None:
        manager = BaselineManager(project_root, "postgresql://localhost/test")
        key = BaselineKey(alembic_rev="rev", fixture_hash="h" * 64)
        path = manager.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake")

        with patch.object(manager, "current_key", return_value=key):
            with patch.object(manager, "_build") as mock_build:
                result = manager.ensure()
                assert result == path
                mock_build.assert_not_called()

    def test_fresh_forces_rebuild_even_if_exists(self, project_root: Path) -> None:
        manager = BaselineManager(project_root, "postgresql://localhost/test")
        key = BaselineKey(alembic_rev="rev", fixture_hash="h" * 64)
        path = manager.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake")

        with patch.object(manager, "current_key", return_value=key):
            with patch.object(manager, "_build") as mock_build:
                manager.ensure(fresh=True)
                mock_build.assert_called_once_with(path)

    def test_builds_when_file_missing(self, project_root: Path) -> None:
        manager = BaselineManager(project_root, "postgresql://localhost/test")
        key = BaselineKey(alembic_rev="rev", fixture_hash="h" * 64)

        with patch.object(manager, "current_key", return_value=key):
            with patch.object(manager, "_build") as mock_build:
                manager.ensure()
                mock_build.assert_called_once_with(manager.path_for(key))


class TestBaselineManagerBuild:
    def test_pipeline_order(self, project_root: Path) -> None:
        """_build runs: reset → upgrade → demo → capture in that order."""
        manager = BaselineManager(project_root, "postgresql://localhost/test")
        dest = project_root / ".dazzle" / "baselines" / "test.sql.gz"

        call_order: list[str] = []

        def fake_run(argv: list[str], **kwargs):
            # Identify which dazzle CLI subcommand is being invoked
            if "reset" in argv:
                call_order.append("reset")
            elif "upgrade" in argv:
                call_order.append("upgrade")
            elif "generate" in argv:
                call_order.append("demo")
            result = MagicMock()
            result.returncode = 0
            result.stderr = b""
            return result

        mock_snapshotter = MagicMock()
        mock_snapshotter.capture.side_effect = lambda url, d: call_order.append("capture")
        manager._snapshotter = mock_snapshotter

        with patch("dazzle.e2e.baseline.subprocess.run", side_effect=fake_run):
            with patch.object(manager, "_has_demo_config", return_value=True):
                manager._build(dest)

        assert call_order == ["reset", "upgrade", "demo", "capture"]

    def test_pipeline_skips_demo_when_no_config(self, project_root: Path) -> None:
        manager = BaselineManager(project_root, "postgresql://localhost/test")
        dest = project_root / ".dazzle" / "baselines" / "test.sql.gz"
        call_order: list[str] = []

        def fake_run(argv: list[str], **kwargs):
            if "reset" in argv:
                call_order.append("reset")
            elif "upgrade" in argv:
                call_order.append("upgrade")
            elif "generate" in argv:
                call_order.append("demo")
            result = MagicMock()
            result.returncode = 0
            result.stderr = b""
            return result

        mock_snapshotter = MagicMock()
        mock_snapshotter.capture.side_effect = lambda url, d: call_order.append("capture")
        manager._snapshotter = mock_snapshotter

        with patch("dazzle.e2e.baseline.subprocess.run", side_effect=fake_run):
            with patch.object(manager, "_has_demo_config", return_value=False):
                manager._build(dest)

        assert call_order == ["reset", "upgrade", "capture"]

    def test_pipeline_raises_baseline_build_error_on_failure(self, project_root: Path) -> None:
        manager = BaselineManager(project_root, "postgresql://localhost/test")
        dest = project_root / ".dazzle" / "baselines" / "test.sql.gz"

        def fake_run(argv: list[str], **kwargs):
            result = MagicMock()
            if "upgrade" in argv:
                result.returncode = 1
                result.stderr = b"migration failed"
            else:
                result.returncode = 0
                result.stderr = b""
            return result

        with patch("dazzle.e2e.baseline.subprocess.run", side_effect=fake_run):
            with pytest.raises(BaselineBuildError, match="migration failed"):
                manager._build(dest)


class TestBaselineManagerGc:
    def test_keeps_newest_n_deletes_older(self, project_root: Path) -> None:
        manager = BaselineManager(project_root, "postgresql://localhost/test")
        bl_dir = project_root / ".dazzle" / "baselines"
        bl_dir.mkdir(parents=True)

        # Create files with distinct mtimes
        import time

        paths = []
        for i in range(5):
            p = bl_dir / f"baseline-rev{i}-hash{i:012x}.sql.gz"
            p.write_bytes(b"fake")
            # Force mtime: newer i = newer file
            t = time.time() + i
            import os

            os.utime(p, (t, t))
            paths.append(p)

        deleted = manager.gc(keep=2)

        # Newest 2 (indexes 4, 3) preserved; 0, 1, 2 deleted
        assert set(deleted) == {paths[0], paths[1], paths[2]}
        for p in paths[3:]:
            assert p.exists()
        for p in paths[:3]:
            assert not p.exists()
