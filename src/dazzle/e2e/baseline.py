"""Baseline key computation + lazy-build manager.

A baseline is a pg_dump snapshot of an example app's database after running
`reset → upgrade → demo generate`. Files are hash-tagged by the tuple
(alembic_head, sha256(demo fixture files)) so schema and fixture changes
automatically invalidate the cache.
"""

import hashlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from dazzle.e2e.errors import BaselineBuildError, BaselineKeyError
from dazzle.e2e.snapshot import Snapshotter

NO_FIXTURE_SENTINEL = "no-fixture"
"""String hashed when an example has no demo fixture files.

Using a stable sentinel (rather than an empty hash) keeps the baseline key
well-defined for fixture-less projects and lets them participate in the
snapshot/restore cycle without special-casing.
"""


@dataclass(frozen=True)
class BaselineKey:
    """Composite key identifying a baseline: alembic head + fixture hash."""

    alembic_rev: str
    fixture_hash: str  # SHA-256 hex

    def filename(self) -> str:
        """Return the canonical baseline filename for this key."""
        return f"baseline-{self.alembic_rev}-{self.fixture_hash[:12]}.sql.gz"


class BaselineManager:
    """Manages lazy-built, hash-tagged baseline files for an example app."""

    def __init__(self, project_root: Path, db_url: str) -> None:
        self.project_root = project_root
        self.db_url = db_url
        self._snapshotter = Snapshotter()

    # Public API --------------------------------------------------------------

    def current_key(self) -> BaselineKey:
        """Compute the current (alembic_head, fixture_hash) tuple.

        Raises BaselineKeyError if the project has no Alembic config.
        """
        return BaselineKey(
            alembic_rev=self._alembic_head(),
            fixture_hash=self._fixture_hash(),
        )

    def path_for(self, key: BaselineKey) -> Path:
        """Return the path where a baseline for `key` should live."""
        return self.project_root / ".dazzle" / "baselines" / key.filename()

    def ensure(self, *, fresh: bool = False) -> Path:
        """Return a path to a baseline file matching current_key().

        If `fresh=True` or the file is missing, lazy-build it.
        """
        key = self.current_key()
        path = self.path_for(key)
        if fresh or not path.exists():
            self._build(path)
        return path

    def restore(self) -> Path:
        """Ensure + restore. Returns the baseline path used."""
        path = self.ensure()
        self._snapshotter.restore(path, self.db_url)
        return path

    def gc(self, keep: int = 3) -> list[Path]:
        """Delete all baseline files for this project except the `keep` newest.

        Returns the deleted paths (for reporting). Matches by filename prefix
        `baseline-` in the baselines directory.
        """
        bl_dir = self.project_root / ".dazzle" / "baselines"
        if not bl_dir.exists():
            return []
        files = sorted(
            bl_dir.glob("baseline-*.sql.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        to_delete = files[keep:]
        for p in to_delete:
            p.unlink()
        return to_delete

    # Internals ---------------------------------------------------------------

    def _alembic_head(self) -> str:
        """Read the Alembic head revision for this project.

        Raises BaselineKeyError if Alembic config is missing or unreadable.
        """
        try:
            from alembic.config import Config
            from alembic.script import ScriptDirectory
        except ImportError as e:
            raise BaselineKeyError(f"alembic package not installed: {e}") from e

        alembic_ini = self.project_root / "alembic.ini"
        if not alembic_ini.exists():
            # Fall back to dazzle-back's packaged alembic.ini since example
            # apps don't ship their own config.
            try:
                import importlib.util

                spec = importlib.util.find_spec("dazzle_back")
                if spec is None or spec.origin is None:
                    raise FileNotFoundError("dazzle_back package not found")
                pkg_dir = Path(spec.origin).parent
                alembic_ini = pkg_dir / "alembic.ini"
                if not alembic_ini.exists():
                    raise FileNotFoundError(f"alembic.ini not found in {pkg_dir}")
            except Exception as e:
                raise BaselineKeyError(
                    f"no alembic.ini in project and dazzle_back fallback failed: {e}"
                ) from e

        try:
            cfg = Config(str(alembic_ini))
            script = ScriptDirectory.from_config(cfg)
            head = script.get_current_head()
        except Exception as e:
            raise BaselineKeyError(f"alembic introspection failed: {e}") from e

        if head is None:
            raise BaselineKeyError("alembic reports no head revision")
        return head

    def _fixture_hash(self) -> str:
        """SHA-256 hash over demo fixture files under .dazzle/demo/.

        Sorted by relative path for determinism. Returns sha256 of the
        literal sentinel when no fixtures exist.
        """
        demo_dir = self.project_root / ".dazzle" / "demo"
        if not demo_dir.exists():
            return hashlib.sha256(NO_FIXTURE_SENTINEL.encode()).hexdigest()

        files = sorted(p for p in demo_dir.rglob("*") if p.is_file())
        if not files:
            return hashlib.sha256(NO_FIXTURE_SENTINEL.encode()).hexdigest()

        h = hashlib.sha256()
        for p in files:
            h.update(p.read_bytes())
        return h.hexdigest()

    def _has_demo_config(self) -> bool:
        """True if the project has demo fixture configuration worth running."""
        demo_dir = self.project_root / ".dazzle" / "demo"
        return demo_dir.exists() and any(demo_dir.rglob("*"))

    def _build(self, dest: Path) -> None:
        """Run reset → upgrade → demo generate → capture, in that order.

        Shells out to the existing dazzle CLI subcommands so we inherit all
        the Alembic + demo-generation logic without reimplementing it.

        Raises BaselineBuildError on any step failure, with stderr captured.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)

        def run_cli(step: str, args: list[str]) -> None:
            argv = [sys.executable, "-m", "dazzle", *args]
            result = subprocess.run(
                argv,
                cwd=self.project_root,
                capture_output=True,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="replace").strip()
                raise BaselineBuildError(f"{step} failed (exit {result.returncode}): {stderr}")

        run_cli("db reset", ["db", "reset", "--yes"])
        run_cli("db upgrade", ["db", "upgrade"])
        if self._has_demo_config():
            run_cli("demo generate", ["demo", "generate"])
        self._snapshotter.capture(self.db_url, dest)
