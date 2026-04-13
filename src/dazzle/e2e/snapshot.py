"""pg_dump / pg_restore wrapper for baseline snapshots.

Probes PATH at init time and hard-requires both binaries. No soft fallback —
per design, silently falling back to slow "reset + upgrade + demo" paths hides
the kind of "where did my 30s go" mysteries that make CI flaky.
"""

import shutil
import subprocess
from pathlib import Path

from dazzle.e2e.errors import (
    BaselineRestoreError,
    PgDumpNotInstalledError,
    SnapshotError,
)


class Snapshotter:
    """Thin wrapper around pg_dump/pg_restore subprocess calls."""

    def __init__(self) -> None:
        pg_dump = shutil.which("pg_dump")
        pg_restore = shutil.which("pg_restore")
        if pg_dump is None:
            raise PgDumpNotInstalledError(
                "pg_dump is not on PATH. Install PostgreSQL client tools:\n"
                "  macOS:  brew install postgresql@16\n"
                "  Debian: apt-get install postgresql-client-16"
            )
        if pg_restore is None:
            raise PgDumpNotInstalledError(
                "pg_restore is not on PATH. Install PostgreSQL client tools:\n"
                "  macOS:  brew install postgresql@16\n"
                "  Debian: apt-get install postgresql-client-16"
            )
        self._pg_dump = pg_dump
        self._pg_restore = pg_restore

    def capture(self, db_url: str, dest: Path) -> None:
        """Write a custom-format compressed dump of `db_url` to `dest`.

        Writes to `<dest>.tmp` first and atomically renames on success. On
        failure, the canonical path is never created.

        Raises SnapshotError with captured stderr on non-zero exit.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = dest.with_suffix(dest.suffix + ".tmp")

        argv = [
            self._pg_dump,
            "-Fc",
            "-Z",
            "9",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(tmp_path),
            db_url,
        ]
        result = subprocess.run(argv, capture_output=True)
        if result.returncode != 0:
            if tmp_path.exists():
                tmp_path.unlink()
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise SnapshotError(f"pg_dump exited {result.returncode}: {stderr}")

        tmp_path.replace(dest)

    def restore(self, src: Path, db_url: str) -> None:
        """Restore `src` into `db_url`, dropping existing objects first.

        Uses --clean --if-exists so restoring over an existing DB works.
        Raises BaselineRestoreError with captured stderr on non-zero exit.
        """
        argv = [
            self._pg_restore,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            f"--dbname={db_url}",
            str(src),
        ]
        result = subprocess.run(argv, capture_output=True)
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise BaselineRestoreError(f"pg_restore exited {result.returncode}: {stderr}")
