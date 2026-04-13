"""Unit tests for Snapshotter — pg_dump/pg_restore wrapper."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dazzle.e2e.errors import (
    BaselineRestoreError,
    PgDumpNotInstalledError,
    SnapshotError,
)
from dazzle.e2e.snapshot import Snapshotter


class TestSnapshotterInit:
    def test_probes_pg_dump_on_path(self) -> None:
        with patch("dazzle.e2e.snapshot.shutil.which") as mock_which:
            mock_which.side_effect = lambda name: f"/usr/local/bin/{name}"
            Snapshotter()
        # Must probe both binaries.
        assert mock_which.call_count == 2

    def test_raises_when_pg_dump_missing(self) -> None:
        with patch("dazzle.e2e.snapshot.shutil.which") as mock_which:
            mock_which.side_effect = lambda name: (
                None if name == "pg_dump" else "/usr/local/bin/pg_restore"
            )
            with pytest.raises(PgDumpNotInstalledError, match="pg_dump"):
                Snapshotter()

    def test_raises_when_pg_restore_missing(self) -> None:
        with patch("dazzle.e2e.snapshot.shutil.which") as mock_which:
            mock_which.side_effect = lambda name: (
                None if name == "pg_restore" else "/usr/local/bin/pg_dump"
            )
            with pytest.raises(PgDumpNotInstalledError, match="pg_restore"):
                Snapshotter()


@pytest.fixture
def snapshotter() -> Snapshotter:
    with patch("dazzle.e2e.snapshot.shutil.which", side_effect=lambda n: f"/usr/local/bin/{n}"):
        return Snapshotter()


class TestSnapshotterCapture:
    def test_builds_expected_argv(self, snapshotter: Snapshotter, tmp_path: Path) -> None:
        dest = tmp_path / "baseline.sql.gz"
        recorded: list[list[str]] = []

        def fake_run(argv, **kwargs):
            recorded.append(argv)
            # Emulate pg_dump writing the file
            for i, a in enumerate(argv):
                if a == "--file":
                    Path(argv[i + 1]).write_bytes(b"fake dump")
                    break
            result = MagicMock()
            result.returncode = 0
            result.stderr = b""
            return result

        with patch("dazzle.e2e.snapshot.subprocess.run", side_effect=fake_run):
            snapshotter.capture("postgresql://localhost/test", dest)

        argv = recorded[-1]
        assert argv[0].endswith("pg_dump")
        assert "-Fc" in argv
        assert "-Z" in argv
        assert "9" in argv
        assert "--no-owner" in argv
        assert "--no-privileges" in argv
        assert "postgresql://localhost/test" in argv

    def test_capture_writes_tmp_then_renames(
        self, snapshotter: Snapshotter, tmp_path: Path
    ) -> None:
        dest = tmp_path / "baseline.sql.gz"

        def fake_run(argv, **kwargs):
            # Find --file argument and write to it.
            for i, a in enumerate(argv):
                if a == "--file":
                    Path(argv[i + 1]).write_bytes(b"fake dump")
                    break
            result = MagicMock()
            result.returncode = 0
            result.stderr = b""
            return result

        with patch("dazzle.e2e.snapshot.subprocess.run", side_effect=fake_run):
            snapshotter.capture("postgresql://localhost/test", dest)

        assert dest.exists()
        assert dest.read_bytes() == b"fake dump"
        # .tmp file should be gone (renamed away)
        assert not (tmp_path / "baseline.sql.gz.tmp").exists()

    def test_capture_raises_on_non_zero_exit(
        self, snapshotter: Snapshotter, tmp_path: Path
    ) -> None:
        dest = tmp_path / "baseline.sql.gz"

        def fake_run(argv, **kwargs):
            result = MagicMock()
            result.returncode = 1
            result.stderr = b"connection refused"
            return result

        with patch("dazzle.e2e.snapshot.subprocess.run", side_effect=fake_run):
            with pytest.raises(SnapshotError, match="connection refused"):
                snapshotter.capture("postgresql://localhost/test", dest)

        # No canonical file left behind on failure.
        assert not dest.exists()


class TestSnapshotterRestore:
    def test_builds_expected_argv(self, snapshotter: Snapshotter, tmp_path: Path) -> None:
        src = tmp_path / "baseline.sql.gz"
        src.write_bytes(b"fake dump")
        recorded: list[list[str]] = []

        def fake_run(argv, **kwargs):
            recorded.append(argv)
            result = MagicMock()
            result.returncode = 0
            result.stderr = b""
            return result

        with patch("dazzle.e2e.snapshot.subprocess.run", side_effect=fake_run):
            snapshotter.restore(src, "postgresql://localhost/test")

        argv = recorded[-1]
        assert argv[0].endswith("pg_restore")
        assert "--clean" in argv
        assert "--if-exists" in argv
        assert "--no-owner" in argv
        assert "--no-privileges" in argv
        assert any(a.startswith("--dbname=") for a in argv)

    def test_restore_raises_baseline_restore_error_on_failure(
        self, snapshotter: Snapshotter, tmp_path: Path
    ) -> None:
        src = tmp_path / "baseline.sql.gz"
        src.write_bytes(b"fake")

        def fake_run(argv, **kwargs):
            result = MagicMock()
            result.returncode = 2
            result.stderr = b"invalid input"
            return result

        with patch("dazzle.e2e.snapshot.subprocess.run", side_effect=fake_run):
            with pytest.raises(BaselineRestoreError, match="invalid input"):
                snapshotter.restore(src, "postgresql://localhost/test")
