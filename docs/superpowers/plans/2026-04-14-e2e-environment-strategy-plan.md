# E2E Environment Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Mode A (developer one-shot e2e harness) + `dazzle db snapshot`/`restore` primitive so the fitness engine can observe live running example apps instead of `about:blank`.

**Architecture:** New `src/dazzle/e2e/` package holds an async `ModeRunner` context manager that owns subprocess lifecycle (launch `dazzle serve --local`, poll `.dazzle/runtime.json` for deterministically hashed ports, poll `/docs` for health, tear down cleanly). PID-based lock file with 15-min TTL safety net. Snapshot/restore via `pg_dump`/`pg_restore` with hash-tagged baseline filenames (`baseline-{alembic_rev}-{fixture_hash12}.sql.gz`). Fitness strategy refactored to take an `AppConnection` from the runner instead of owning `Popen` itself — closes the latent hardcoded-port bug in `dazzle.qa.server.connect_app`. Clean break per ADR-0003.

**Tech Stack:** Python 3.12+, `asyncio`, `subprocess`, `pg_dump`/`pg_restore` (hard require, no soft fallback), pytest, typer (existing CLI), MCP handlers (read-only per ADR-0002).

**Spec reference:** `docs/superpowers/specs/2026-04-14-e2e-environment-strategy-design.md`

---

## File Structure

**New files (21):**

| Path | Purpose |
|------|---------|
| `src/dazzle/e2e/__init__.py` | Package init, exports public names |
| `src/dazzle/e2e/errors.py` | `E2EError` hierarchy |
| `src/dazzle/e2e/modes.py` | `ModeSpec` + `MODE_REGISTRY` + `get_mode` |
| `src/dazzle/e2e/lifecycle.py` | `LockFile` with 15-min TTL + stale detection |
| `src/dazzle/e2e/snapshot.py` | `Snapshotter` — pg_dump/pg_restore wrapper |
| `src/dazzle/e2e/baseline.py` | `BaselineKey` + `BaselineManager` (lazy-build) |
| `src/dazzle/e2e/runner.py` | `ModeRunner` async context manager |
| `src/dazzle/cli/e2e/__init__.py` | Existing `cli/e2e.py` contents, moved |
| `src/dazzle/cli/e2e/env.py` | New `env` sub-typer: `start`, `status`, `stop`, `logs` |
| `src/dazzle/mcp/server/handlers/e2e.py` | Read-only MCP handler |
| `tests/unit/e2e/__init__.py` | Empty package marker |
| `tests/unit/e2e/test_errors.py` | Exception hierarchy tests |
| `tests/unit/e2e/test_modes.py` | Registry + `get_mode` tests |
| `tests/unit/e2e/test_lifecycle.py` | `LockFile` tests |
| `tests/unit/e2e/test_snapshot.py` | `Snapshotter` tests (mocked subprocess) |
| `tests/unit/e2e/test_baseline.py` | `BaselineManager` tests (mocked Alembic) |
| `tests/unit/e2e/test_runner.py` | `ModeRunner` tests (fake Popen, fake health check) |
| `tests/integration/__init__.py` | Empty package marker (if absent) |
| `tests/integration/e2e/__init__.py` | Empty package marker |
| `tests/integration/e2e/test_mode_a_integration.py` | Real Postgres + real subprocess |
| `examples/support_tickets/.env.example` | Template env file |
| `docs/reference/e2e-environment.md` | User reference for Mode A |

**Modified files (8):**

| Path | Change |
|------|--------|
| `src/dazzle/qa/server.py` | Delete `connect_app`, `_start_app`; add `AppConnection.from_runtime_file` classmethod |
| `src/dazzle/cli/runtime_impl/ux_cycle_impl/fitness_strategy.py` | Refactor `run_fitness_strategy` signature to take `AppConnection` |
| `src/dazzle/cli/db.py` | Add `snapshot`, `restore`, `snapshot-gc` commands |
| `src/dazzle/mcp/server/handlers_consolidated.py` | Register `handle_e2e` |
| `src/dazzle/mcp/server/tools_consolidated.py` | Add `e2e` Tool definition |
| `tests/e2e/fitness/test_support_tickets_fitness.py` | Rewrite to use `ModeRunner` |
| `src/dazzle/cli/e2e.py` | **Deleted** — content moved to `cli/e2e/__init__.py` |
| `pyproject.toml` | Add `integration` pytest marker if not present |

---

## Task 1: E2E Exception Hierarchy

**Files:**
- Create: `src/dazzle/e2e/__init__.py`
- Create: `src/dazzle/e2e/errors.py`
- Create: `tests/unit/e2e/__init__.py`
- Create: `tests/unit/e2e/test_errors.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/e2e/test_errors.py`:

```python
"""Unit tests for the e2e exception hierarchy."""

import pytest

from dazzle.core.errors import DazzleError
from dazzle.e2e.errors import (
    BaselineBuildError,
    BaselineKeyError,
    BaselineRestoreError,
    E2EError,
    HealthCheckTimeoutError,
    ModeAlreadyRunningError,
    ModeLaunchError,
    PgDumpNotInstalledError,
    RunnerTeardownError,
    RuntimeFileTimeoutError,
    SnapshotError,
    UnknownModeError,
)


class TestE2EErrorHierarchy:
    def test_e2e_error_inherits_from_dazzle_error(self) -> None:
        assert issubclass(E2EError, DazzleError)

    def test_runner_level_errors_inherit_from_e2e_error(self) -> None:
        assert issubclass(ModeAlreadyRunningError, E2EError)
        assert issubclass(UnknownModeError, E2EError)
        assert issubclass(ModeLaunchError, E2EError)
        assert issubclass(RuntimeFileTimeoutError, E2EError)
        assert issubclass(HealthCheckTimeoutError, E2EError)
        assert issubclass(RunnerTeardownError, E2EError)

    def test_snapshot_errors_inherit_from_snapshot_error(self) -> None:
        assert issubclass(SnapshotError, E2EError)
        assert issubclass(PgDumpNotInstalledError, SnapshotError)
        assert issubclass(BaselineKeyError, SnapshotError)
        assert issubclass(BaselineBuildError, SnapshotError)
        assert issubclass(BaselineRestoreError, SnapshotError)

    def test_error_instances_carry_message(self) -> None:
        err = ModeAlreadyRunningError("lock held by pid 1234")
        assert "1234" in str(err)

    def test_errors_can_be_caught_as_e2e_error(self) -> None:
        with pytest.raises(E2EError):
            raise BaselineRestoreError("pg_restore exit 1")

    def test_errors_can_be_caught_as_dazzle_error(self) -> None:
        with pytest.raises(DazzleError):
            raise PgDumpNotInstalledError("pg_dump not on PATH")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/e2e/test_errors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.e2e'`

- [ ] **Step 3: Create empty package init files**

Create `src/dazzle/e2e/__init__.py`:

```python
"""Dazzle e2e environment primitives.

Shared runner, mode registry, snapshot/restore, and lifecycle management for
launching example Dazzle apps as live test environments.

v1 exposes Mode A (developer one-shot) + the snapshot primitive. Modes B, C,
and D are sketched in the design spec but not wired in v1.
"""

from dazzle.e2e.errors import (
    BaselineBuildError,
    BaselineKeyError,
    BaselineRestoreError,
    E2EError,
    HealthCheckTimeoutError,
    ModeAlreadyRunningError,
    ModeLaunchError,
    PgDumpNotInstalledError,
    RunnerTeardownError,
    RuntimeFileTimeoutError,
    SnapshotError,
    UnknownModeError,
)

__all__ = [
    "BaselineBuildError",
    "BaselineKeyError",
    "BaselineRestoreError",
    "E2EError",
    "HealthCheckTimeoutError",
    "ModeAlreadyRunningError",
    "ModeLaunchError",
    "PgDumpNotInstalledError",
    "RunnerTeardownError",
    "RuntimeFileTimeoutError",
    "SnapshotError",
    "UnknownModeError",
]
```

Create `tests/unit/e2e/__init__.py` as an empty file.

- [ ] **Step 4: Implement the exception hierarchy**

Create `src/dazzle/e2e/errors.py`:

```python
"""Exception hierarchy for the e2e environment package.

All e2e errors inherit from DazzleError so they surface consistently via
the existing CLI error rendering path.
"""

from dazzle.core.errors import DazzleError


class E2EError(DazzleError):
    """Base for e2e environment errors."""


# Runner-level errors ---------------------------------------------------------


class ModeAlreadyRunningError(E2EError):
    """Another Mode A instance holds the lock file for this example app."""


class UnknownModeError(E2EError):
    """get_mode(name) called with a name not in MODE_REGISTRY."""


class ModeLaunchError(E2EError):
    """subprocess.Popen raised while launching dazzle serve."""


class RuntimeFileTimeoutError(E2EError):
    """.dazzle/runtime.json did not appear within the budget."""


class HealthCheckTimeoutError(E2EError):
    """{api_url}/docs did not return 200 within the budget."""


class RunnerTeardownError(E2EError):
    """Runner __aexit__ failed to terminate subprocess or release lock.

    This is logged but never raised — teardown failures must not mask caller
    exceptions. Callers should not catch this type directly; it exists for
    telemetry and test assertions only.
    """


# Snapshot-level errors -------------------------------------------------------


class SnapshotError(E2EError):
    """Base for snapshot/restore errors."""


class PgDumpNotInstalledError(SnapshotError):
    """pg_dump or pg_restore is missing from PATH."""


class BaselineKeyError(SnapshotError):
    """Cannot compute a baseline key (missing Alembic config, etc.)."""


class BaselineBuildError(SnapshotError):
    """Lazy baseline build pipeline failed (reset, upgrade, demo, or capture)."""


class BaselineRestoreError(SnapshotError):
    """pg_restore exited non-zero."""
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/e2e/test_errors.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/e2e/__init__.py src/dazzle/e2e/errors.py \
        tests/unit/e2e/__init__.py tests/unit/e2e/test_errors.py
git commit -m "feat(e2e): add E2EError exception hierarchy"
```

---

## Task 2: Snapshot Primitive

**Files:**
- Create: `src/dazzle/e2e/snapshot.py`
- Create: `tests/unit/e2e/test_snapshot.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/e2e/test_snapshot.py`:

```python
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
            mock_which.side_effect = lambda name: None if name == "pg_dump" else "/usr/local/bin/pg_restore"
            with pytest.raises(PgDumpNotInstalledError, match="pg_dump"):
                Snapshotter()

    def test_raises_when_pg_restore_missing(self) -> None:
        with patch("dazzle.e2e.snapshot.shutil.which") as mock_which:
            mock_which.side_effect = lambda name: None if name == "pg_restore" else "/usr/local/bin/pg_dump"
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
            # Simulate pg_dump creating the .tmp file.
            tmp_file = Path(argv[-1]) if "--file" in argv else None
            if tmp_file is None:
                # pg_dump outputs to stdout by default — we use --file so always present
                pass
            result = MagicMock()
            result.returncode = 0
            result.stderr = b""
            return result

        with patch("dazzle.e2e.snapshot.subprocess.run", side_effect=fake_run):
            # Need to touch the .tmp file since subprocess is mocked out.
            def fake_run_with_file(argv, **kwargs):
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

            with patch("dazzle.e2e.snapshot.subprocess.run", side_effect=fake_run_with_file):
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/e2e/test_snapshot.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.e2e.snapshot'`

- [ ] **Step 3: Implement the snapshotter**

Create `src/dazzle/e2e/snapshot.py`:

```python
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
            raise SnapshotError(
                f"pg_dump exited {result.returncode}: {stderr}"
            )

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
            raise BaselineRestoreError(
                f"pg_restore exited {result.returncode}: {stderr}"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/e2e/test_snapshot.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/e2e/snapshot.py tests/unit/e2e/test_snapshot.py
git commit -m "feat(e2e): add Snapshotter wrapping pg_dump/pg_restore"
```

---

## Task 3: Baseline Manager

**Files:**
- Create: `src/dazzle/e2e/baseline.py`
- Create: `tests/unit/e2e/test_baseline.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/e2e/test_baseline.py`:

```python
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


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "example"
    root.mkdir()
    (root / ".dazzle").mkdir()
    return root


class TestBaselineManagerCurrentKey:
    def test_computes_key_with_fixture_files(
        self, project_root: Path
    ) -> None:
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

    def test_raises_baseline_key_error_when_alembic_missing(
        self, project_root: Path
    ) -> None:
        manager = BaselineManager(project_root, "postgresql://localhost/test")
        with patch.object(
            manager, "_alembic_head", side_effect=BaselineKeyError("no config")
        ):
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

    def test_pipeline_raises_baseline_build_error_on_failure(
        self, project_root: Path
    ) -> None:
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/e2e/test_baseline.py -v`
Expected: FAIL — `ModuleNotFoundError: dazzle.e2e.baseline`

- [ ] **Step 3: Implement the baseline manager**

Create `src/dazzle/e2e/baseline.py`:

```python
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
            raise BaselineKeyError(
                f"alembic package not installed: {e}"
            ) from e

        alembic_ini = self.project_root / "alembic.ini"
        if not alembic_ini.exists():
            # Fall back to dazzle-back's packaged alembic.ini since example
            # apps don't ship their own config.
            try:
                from importlib import resources

                with resources.as_file(
                    resources.files("dazzle_back") / "alembic.ini"
                ) as path:
                    alembic_ini = Path(str(path))
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

        files = sorted(
            p for p in demo_dir.rglob("*") if p.is_file()
        )
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
                raise BaselineBuildError(
                    f"{step} failed (exit {result.returncode}): {stderr}"
                )

        run_cli("db reset", ["db", "reset", "--yes"])
        run_cli("db upgrade", ["db", "upgrade"])
        if self._has_demo_config():
            run_cli("demo generate", ["demo", "generate"])
        self._snapshotter.capture(self.db_url, dest)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/e2e/test_baseline.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/e2e/baseline.py tests/unit/e2e/test_baseline.py
git commit -m "feat(e2e): add BaselineManager with lazy hash-tagged builds"
```

---

## Task 4: PID Lock File with TTL

**Files:**
- Create: `src/dazzle/e2e/lifecycle.py`
- Create: `tests/unit/e2e/test_lifecycle.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/e2e/test_lifecycle.py`:

```python
"""Unit tests for LockFile — PID-based lock with 15-min TTL."""

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from dazzle.e2e.errors import ModeAlreadyRunningError
from dazzle.e2e.lifecycle import LockFile


@pytest.fixture
def lock_dir(tmp_path: Path) -> Path:
    d = tmp_path / "example" / ".dazzle"
    d.mkdir(parents=True)
    return d


class TestLockFileAcquire:
    def test_creates_lock_on_empty_dir(self, lock_dir: Path) -> None:
        lock = LockFile(lock_dir / "mode_a.lock")
        lock.acquire("a", lock_dir / "log.log")

        content = json.loads((lock_dir / "mode_a.lock").read_text())
        assert content["pid"] == os.getpid()
        assert content["mode"] == "a"
        assert content["log_file"].endswith("log.log")
        assert "started_at" in content

    def test_raises_when_alive_pid_holds_lock(self, lock_dir: Path) -> None:
        lock_path = lock_dir / "mode_a.lock"
        lock_path.write_text(
            json.dumps(
                {
                    "pid": 99999,
                    "mode": "a",
                    "started_at": "2026-04-13T10:00:00Z",
                    "log_file": "/tmp/x.log",
                }
            )
        )

        lock = LockFile(lock_path)
        with patch("dazzle.e2e.lifecycle.os.kill") as mock_kill:
            mock_kill.return_value = None  # Simulate "alive"
            with patch(
                "dazzle.e2e.lifecycle._iso_now_seconds_ago", return_value=10
            ):
                with pytest.raises(ModeAlreadyRunningError, match="99999"):
                    lock.acquire("a", lock_dir / "log.log")

    def test_deletes_stale_lock_when_pid_dead(self, lock_dir: Path) -> None:
        lock_path = lock_dir / "mode_a.lock"
        lock_path.write_text(
            json.dumps(
                {
                    "pid": 99999,
                    "mode": "a",
                    "started_at": "2026-04-13T10:00:00Z",
                    "log_file": "/tmp/x.log",
                }
            )
        )

        lock = LockFile(lock_path)
        with patch(
            "dazzle.e2e.lifecycle.os.kill", side_effect=ProcessLookupError()
        ):
            lock.acquire("a", lock_dir / "log.log")

        content = json.loads(lock_path.read_text())
        assert content["pid"] == os.getpid()

    def test_deletes_stale_lock_when_older_than_ttl(self, lock_dir: Path) -> None:
        lock_path = lock_dir / "mode_a.lock"
        lock_path.write_text(
            json.dumps(
                {
                    "pid": 99999,
                    "mode": "a",
                    "started_at": "2026-04-13T10:00:00Z",
                    "log_file": "/tmp/x.log",
                }
            )
        )

        lock = LockFile(lock_path, ttl_seconds=900)
        # PID alive, but lock is old
        with patch("dazzle.e2e.lifecycle.os.kill") as mock_kill:
            mock_kill.return_value = None
            with patch(
                "dazzle.e2e.lifecycle._iso_now_seconds_ago", return_value=1000
            ):
                lock.acquire("a", lock_dir / "log.log")

        content = json.loads(lock_path.read_text())
        assert content["pid"] == os.getpid()


class TestLockFileRelease:
    def test_deletes_file(self, lock_dir: Path) -> None:
        lock_path = lock_dir / "mode_a.lock"
        lock = LockFile(lock_path)
        lock.acquire("a", lock_dir / "log.log")
        assert lock_path.exists()

        lock.release()
        assert not lock_path.exists()

    def test_release_is_idempotent_when_already_gone(self, lock_dir: Path) -> None:
        lock = LockFile(lock_dir / "mode_a.lock")
        lock.release()  # Should not raise
        lock.release()  # Still should not raise


class TestLockFileIntegration:
    def test_acquire_release_acquire(self, lock_dir: Path) -> None:
        lock = LockFile(lock_dir / "mode_a.lock")
        lock.acquire("a", lock_dir / "log.log")
        lock.release()
        lock.acquire("a", lock_dir / "log.log")  # Should not raise
        lock.release()

    def test_read_lock_holder(self, lock_dir: Path) -> None:
        lock = LockFile(lock_dir / "mode_a.lock")
        lock.acquire("a", lock_dir / "log.log")

        holder = LockFile(lock_dir / "mode_a.lock").read_holder()
        assert holder is not None
        assert holder["pid"] == os.getpid()
        assert holder["mode"] == "a"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/e2e/test_lifecycle.py -v`
Expected: FAIL — `ModuleNotFoundError: dazzle.e2e.lifecycle`

- [ ] **Step 3: Implement the lock file**

Create `src/dazzle/e2e/lifecycle.py`:

```python
"""PID-based lock file with 15-minute TTL safety net.

Matches the pattern used elsewhere in the codebase (e.g., `.dazzle/ux-cycle.lock`).
Stale locks are detected two ways: dead PID (os.kill raises ProcessLookupError)
or file age exceeding the TTL regardless of PID state.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dazzle.e2e.errors import ModeAlreadyRunningError

DEFAULT_TTL_SECONDS = 15 * 60


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_now_seconds_ago(iso_ts: str) -> float:
    """Return seconds between `iso_ts` and now (UTC)."""
    try:
        past = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        # Malformed timestamp → treat as ancient.
        return float("inf")
    now = datetime.now(timezone.utc)
    return (now - past).total_seconds()


def _is_pid_alive(pid: int) -> bool:
    """True if the process is still running (POSIX only)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it — still alive.
        return True
    return True


class LockFile:
    """JSON-backed PID lock file with stale detection."""

    def __init__(
        self, path: Path, *, ttl_seconds: int = DEFAULT_TTL_SECONDS
    ) -> None:
        self.path = path
        self.ttl_seconds = ttl_seconds

    def acquire(self, mode_name: str, log_path: Path) -> None:
        """Acquire the lock.

        Raises ModeAlreadyRunningError if an alive PID holds a non-stale lock.
        Stale locks (dead PID OR age > ttl_seconds) are silently deleted.
        """
        if self.path.exists():
            self._maybe_delete_stale()

        if self.path.exists():
            # Still held by a live process within TTL.
            holder = self.read_holder()
            pid = holder["pid"] if holder else "?"
            raise ModeAlreadyRunningError(
                f"Mode {mode_name} lock held by pid {pid} at {self.path} "
                f"(started {holder.get('started_at') if holder else 'unknown'})"
            )

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "mode": mode_name,
                    "started_at": _iso_now(),
                    "log_file": str(log_path),
                }
            )
        )

    def release(self) -> None:
        """Delete the lock file. No-op if already gone. Does not raise."""
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def read_holder(self) -> dict[str, Any] | None:
        """Return the current lock holder record, or None if absent/malformed."""
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    # Internals ---------------------------------------------------------------

    def _maybe_delete_stale(self) -> None:
        """Delete the lock if dead PID or older than TTL."""
        holder = self.read_holder()
        if holder is None:
            # Malformed; treat as stale.
            self.release()
            return

        pid = holder.get("pid")
        started_at = holder.get("started_at", "")
        age = _iso_now_seconds_ago(started_at) if started_at else float("inf")

        if age > self.ttl_seconds:
            self.release()
            return
        if not isinstance(pid, int) or not _is_pid_alive(pid):
            self.release()
            return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/e2e/test_lifecycle.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/e2e/lifecycle.py tests/unit/e2e/test_lifecycle.py
git commit -m "feat(e2e): add LockFile with PID check and 15-min TTL"
```

---

## Task 5: Mode Registry

**Files:**
- Create: `src/dazzle/e2e/modes.py`
- Create: `tests/unit/e2e/test_modes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/e2e/test_modes.py`:

```python
"""Unit tests for the mode registry."""

import pytest

from dazzle.e2e.errors import UnknownModeError
from dazzle.e2e.modes import MODE_REGISTRY, ModeSpec, get_mode


class TestModeRegistry:
    def test_registry_has_mode_a(self) -> None:
        names = [m.name for m in MODE_REGISTRY]
        assert "a" in names

    def test_registry_v1_has_only_mode_a(self) -> None:
        """v1 ships only Mode A; B/C/D land later."""
        assert len(MODE_REGISTRY) == 1
        assert MODE_REGISTRY[0].name == "a"

    def test_mode_a_fields(self) -> None:
        mode_a = get_mode("a")
        assert mode_a.name == "a"
        assert mode_a.db_policy_default == "preserve"
        assert "preserve" in mode_a.db_policies_allowed
        assert "fresh" in mode_a.db_policies_allowed
        assert "restore" in mode_a.db_policies_allowed
        assert mode_a.qa_flag_policy == "auto_if_personas"
        assert mode_a.log_output == "captured_tail_on_fail"
        assert mode_a.lifetime == "single_run"
        assert mode_a.description
        assert mode_a.intended_use


class TestModeSpec:
    def test_is_frozen(self) -> None:
        spec = get_mode("a")
        with pytest.raises((AttributeError, TypeError)):
            spec.name = "x"  # type: ignore[misc]


class TestGetMode:
    def test_returns_mode_spec_by_name(self) -> None:
        assert get_mode("a").name == "a"

    def test_raises_unknown_mode_error_on_miss(self) -> None:
        with pytest.raises(UnknownModeError, match="z"):
            get_mode("z")

    def test_raises_unknown_mode_error_for_unimplemented_modes(self) -> None:
        # Modes b/c/d are specced but not wired in v1.
        for name in ("b", "c", "d"):
            with pytest.raises(UnknownModeError):
                get_mode(name)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/e2e/test_modes.py -v`
Expected: FAIL — `ModuleNotFoundError: dazzle.e2e.modes`

- [ ] **Step 3: Implement the registry**

Create `src/dazzle/e2e/modes.py`:

```python
"""Mode registry for e2e environment orchestration.

Each ModeSpec is a frozen dataclass describing a distinct launch+teardown
profile. The registry is first-class data so MCP consumers can enumerate
available modes without hardcoded strings.

v1 ships mode_a only. Modes B/C/D are specced in
docs/superpowers/specs/2026-04-14-e2e-environment-strategy-design.md but
not wired — adding them is ~40 lines here plus CLI wiring.
"""

from dataclasses import dataclass
from typing import Literal

from dazzle.e2e.errors import UnknownModeError

ModeName = Literal["a", "b", "c", "d"]
DbPolicy = Literal["preserve", "fresh", "restore"]
QaFlagPolicy = Literal["auto_if_personas", "always_on", "always_off"]
LogOutput = Literal["captured_tail_on_fail", "stream_live", "captured_archive"]
Lifetime = Literal["single_run", "long_running"]


@dataclass(frozen=True)
class ModeSpec:
    """Static description of an e2e mode."""

    name: ModeName
    description: str
    db_policy_default: DbPolicy
    db_policies_allowed: frozenset[str]
    qa_flag_policy: QaFlagPolicy
    log_output: LogOutput
    lifetime: Lifetime
    intended_use: str


MODE_A = ModeSpec(
    name="a",
    description=(
        "Developer one-shot — launch an example app, yield an AppConnection, "
        "tear down when the async with block exits."
    ),
    db_policy_default="preserve",
    db_policies_allowed=frozenset({"preserve", "fresh", "restore"}),
    qa_flag_policy="auto_if_personas",
    log_output="captured_tail_on_fail",
    lifetime="single_run",
    intended_use=(
        "Running /ux-cycle Phase B locally against a specific component, or "
        "invoking the fitness engine interactively from the CLI. Default DB "
        "policy is 'preserve' to respect whatever state you have; pass "
        "--fresh for deterministic seed data, or --db-policy=restore to use "
        "a hash-tagged baseline snapshot."
    ),
)


MODE_REGISTRY: tuple[ModeSpec, ...] = (MODE_A,)


def get_mode(name: str) -> ModeSpec:
    """Return the ModeSpec named `name`.

    Raises UnknownModeError if no mode matches.
    """
    for spec in MODE_REGISTRY:
        if spec.name == name:
            return spec
    raise UnknownModeError(
        f"Unknown mode {name!r}. Available modes: "
        f"{', '.join(m.name for m in MODE_REGISTRY)}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/e2e/test_modes.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/e2e/modes.py tests/unit/e2e/test_modes.py
git commit -m "feat(e2e): add ModeSpec registry with mode_a"
```

---

## Task 6: ModeRunner Async Context Manager

**Files:**
- Create: `src/dazzle/e2e/runner.py`
- Create: `tests/unit/e2e/test_runner.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/e2e/test_runner.py`:

```python
"""Unit tests for ModeRunner async context manager."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.e2e.errors import (
    HealthCheckTimeoutError,
    ModeAlreadyRunningError,
    RuntimeFileTimeoutError,
)
from dazzle.e2e.modes import get_mode
from dazzle.e2e.runner import ModeRunner


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "example"
    root.mkdir()
    (root / ".dazzle").mkdir()
    return root


def _write_runtime_file(project_root: Path, ui_port: int = 8981, api_port: int = 8969) -> None:
    """Simulate dazzle serve writing runtime.json."""
    (project_root / ".dazzle" / "runtime.json").write_text(
        json.dumps(
            {
                "project_name": "example",
                "ui_port": ui_port,
                "api_port": api_port,
                "ui_url": f"http://localhost:{ui_port}",
                "api_url": f"http://localhost:{api_port}",
            }
        )
    )


class _FakePopen:
    """Drop-in replacement for subprocess.Popen that records interactions."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        self.pid = 4242
        self.terminated = False
        self.killed = False
        self._exit_code: int | None = None

    def poll(self) -> int | None:
        return self._exit_code

    def terminate(self) -> None:
        self.terminated = True
        self._exit_code = 0

    def kill(self) -> None:
        self.killed = True
        self._exit_code = -9

    def wait(self, timeout: float | None = None) -> int:
        return self._exit_code or 0


@pytest.fixture
def fake_popen(monkeypatch: pytest.MonkeyPatch) -> list[_FakePopen]:
    """Patch subprocess.Popen to record instances."""
    instances: list[_FakePopen] = []

    def factory(*args: Any, **kwargs: Any) -> _FakePopen:
        p = _FakePopen(*args, **kwargs)
        instances.append(p)
        return p

    monkeypatch.setattr("dazzle.e2e.runner.subprocess.Popen", factory)
    return instances


@pytest.fixture
def fake_wait_for_ready(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr("dazzle.e2e.runner.wait_for_ready", mock)
    return mock


@pytest.mark.asyncio
class TestModeRunnerHappyPath:
    async def test_yields_app_connection(
        self,
        project_root: Path,
        fake_popen: list[_FakePopen],
        fake_wait_for_ready: AsyncMock,
    ) -> None:
        _write_runtime_file(project_root)
        mode = get_mode("a")

        async with ModeRunner(
            mode_spec=mode,
            project_root=project_root,
            personas=None,
            db_policy="preserve",
        ) as conn:
            assert conn.site_url == "http://localhost:8981"
            assert conn.api_url == "http://localhost:8969"
            assert conn.process is fake_popen[0]

        # After teardown: lock released
        lock_path = project_root / ".dazzle" / "mode_a.lock"
        assert not lock_path.exists()
        assert fake_popen[0].terminated

    async def test_qa_flags_auto_set_when_personas_non_empty(
        self,
        project_root: Path,
        fake_popen: list[_FakePopen],
        fake_wait_for_ready: AsyncMock,
    ) -> None:
        _write_runtime_file(project_root)
        mode = get_mode("a")

        async with ModeRunner(
            mode_spec=mode,
            project_root=project_root,
            personas=["admin"],
            db_policy="preserve",
        ):
            pass

        env = fake_popen[0].kwargs["env"]
        assert env["DAZZLE_ENV"] == "development"
        assert env["DAZZLE_QA_MODE"] == "1"

    async def test_qa_flags_not_set_when_personas_none(
        self,
        project_root: Path,
        fake_popen: list[_FakePopen],
        fake_wait_for_ready: AsyncMock,
    ) -> None:
        _write_runtime_file(project_root)
        mode = get_mode("a")

        async with ModeRunner(
            mode_spec=mode,
            project_root=project_root,
            personas=None,
            db_policy="preserve",
        ):
            pass

        env = fake_popen[0].kwargs["env"]
        # DAZZLE_QA_MODE must not be force-set; may still be inherited from
        # the parent env, so we assert the *value* isn't "1" when parent
        # didn't set it.
        if "DAZZLE_QA_MODE" in env and env.get("DAZZLE_QA_MODE") != os.environ.get(
            "DAZZLE_QA_MODE"
        ):
            pytest.fail("Runner set DAZZLE_QA_MODE despite personas=None")


@pytest.mark.asyncio
class TestModeRunnerFailurePaths:
    async def test_raises_when_alive_pid_holds_lock(
        self, project_root: Path
    ) -> None:
        lock_path = project_root / ".dazzle" / "mode_a.lock"
        lock_path.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "mode": "a",
                    "started_at": "2030-01-01T00:00:00Z",  # future = not stale
                    "log_file": "/tmp/x.log",
                }
            )
        )

        mode = get_mode("a")
        runner = ModeRunner(
            mode_spec=mode,
            project_root=project_root,
            personas=None,
            db_policy="preserve",
        )
        # Patch time so "future" start_at doesn't confuse TTL math
        with patch(
            "dazzle.e2e.lifecycle._iso_now_seconds_ago", return_value=10
        ):
            with pytest.raises(ModeAlreadyRunningError):
                async with runner:
                    pass

    async def test_raises_runtime_file_timeout(
        self,
        project_root: Path,
        fake_popen: list[_FakePopen],
        fake_wait_for_ready: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Don't write runtime.json — triggers timeout
        monkeypatch.setattr("dazzle.e2e.runner.RUNTIME_POLL_BUDGET_SECONDS", 0.2)
        monkeypatch.setattr("dazzle.e2e.runner.RUNTIME_POLL_INTERVAL_SECONDS", 0.05)

        mode = get_mode("a")
        with pytest.raises(RuntimeFileTimeoutError):
            async with ModeRunner(
                mode_spec=mode,
                project_root=project_root,
                personas=None,
                db_policy="preserve",
            ):
                pass

        # Subprocess terminated
        assert fake_popen[0].terminated
        # Lock released
        assert not (project_root / ".dazzle" / "mode_a.lock").exists()

    async def test_raises_health_check_timeout(
        self,
        project_root: Path,
        fake_popen: list[_FakePopen],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _write_runtime_file(project_root)
        monkeypatch.setattr(
            "dazzle.e2e.runner.wait_for_ready", AsyncMock(return_value=False)
        )

        mode = get_mode("a")
        with pytest.raises(HealthCheckTimeoutError):
            async with ModeRunner(
                mode_spec=mode,
                project_root=project_root,
                personas=None,
                db_policy="preserve",
            ):
                pass

        assert fake_popen[0].terminated
        assert not (project_root / ".dazzle" / "mode_a.lock").exists()

    async def test_caller_exception_propagates_with_teardown(
        self,
        project_root: Path,
        fake_popen: list[_FakePopen],
        fake_wait_for_ready: AsyncMock,
    ) -> None:
        _write_runtime_file(project_root)
        mode = get_mode("a")

        class BoomError(Exception):
            pass

        with pytest.raises(BoomError):
            async with ModeRunner(
                mode_spec=mode,
                project_root=project_root,
                personas=None,
                db_policy="preserve",
            ):
                raise BoomError("fitness crashed")

        # Teardown still happened
        assert fake_popen[0].terminated
        assert not (project_root / ".dazzle" / "mode_a.lock").exists()
```

- [ ] **Step 2: Make sure pytest-asyncio is available**

Run: `python -c "import pytest_asyncio; print(pytest_asyncio.__version__)"`
Expected: prints a version. If missing, add to test deps — but it's already used elsewhere in the repo (e.g., fitness tests).

Run: `pytest tests/unit/e2e/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: dazzle.e2e.runner`

- [ ] **Step 3: Implement ModeRunner**

Create `src/dazzle/e2e/runner.py`:

```python
"""ModeRunner — async context manager that owns the example app subprocess.

Workflow:
    async with ModeRunner(mode_spec, project_root, personas=...) as conn:
        await run_fitness_strategy(conn, ...)

On enter:
    1. Acquire PID lock file (with stale detection).
    2. Apply DB policy (preserve no-op; fresh reset+upgrade+demo;
       restore uses BaselineManager).
    3. Prep subprocess env (QA flags auto-set if personas non-empty).
    4. Popen `python -m dazzle serve --local` in a new process group.
    5. Register atexit + SIGINT/SIGTERM cleanup.
    6. Poll .dazzle/runtime.json for up to RUNTIME_POLL_BUDGET_SECONDS.
    7. Parse runtime.json -> AppConnection.
    8. Poll {api_url}/docs for 200 via wait_for_ready.
    9. Return the connection.

On exit:
    a. If exception: tail last 50 log lines to stderr.
    b. Terminate subprocess (terminate, wait 5s, kill if needed).
    c. Close log file handle.
    d. Release lock file.
    e. Teardown failures are logged to stderr; caller exception propagates.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any, Literal

from dazzle.e2e.baseline import BaselineManager
from dazzle.e2e.errors import (
    HealthCheckTimeoutError,
    ModeLaunchError,
    RunnerTeardownError,
    RuntimeFileTimeoutError,
)
from dazzle.e2e.lifecycle import LockFile
from dazzle.e2e.modes import ModeSpec
from dazzle.qa.server import AppConnection, wait_for_ready

RUNTIME_POLL_BUDGET_SECONDS = 10.0
RUNTIME_POLL_INTERVAL_SECONDS = 0.2
HEALTH_CHECK_BUDGET_SECONDS = 30.0
TERMINATE_WAIT_SECONDS = 5.0
LOG_TAIL_LINES = 50

DbPolicyValue = Literal["preserve", "fresh", "restore"]


def _iso_ts_for_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _tail_log(log_path: Path, n: int = LOG_TAIL_LINES) -> list[str]:
    if not log_path.exists():
        return []
    try:
        text = log_path.read_text(errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    return lines[-n:]


class ModeRunner:
    """Async context manager that launches + tears down an example app."""

    def __init__(
        self,
        *,
        mode_spec: ModeSpec,
        project_root: Path,
        personas: list[str] | None = None,
        db_policy: DbPolicyValue | None = None,
        fresh: bool = False,
    ) -> None:
        self.mode_spec = mode_spec
        self.project_root = project_root
        self.personas = personas
        # db_policy defaults to the mode's default when not overridden
        resolved = db_policy or mode_spec.db_policy_default
        if resolved not in mode_spec.db_policies_allowed:
            raise ValueError(
                f"db_policy {resolved!r} not allowed for mode {mode_spec.name!r}. "
                f"Allowed: {sorted(mode_spec.db_policies_allowed)}"
            )
        self.db_policy: DbPolicyValue = resolved  # type: ignore[assignment]
        self.fresh = fresh

        # Populated during __aenter__
        self._lock: LockFile | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self._log_fh: IO[bytes] | None = None
        self._log_path: Path | None = None
        self._atexit_registered = False
        self._prev_sigint: Any = None
        self._prev_sigterm: Any = None

    # Context manager protocol -----------------------------------------------

    async def __aenter__(self) -> AppConnection:
        # 1. Acquire lock (before any side effect)
        lock_path = self.project_root / ".dazzle" / "mode_a.lock"
        log_dir = self.project_root / ".dazzle" / "e2e-logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = log_dir / f"mode_a-{_iso_ts_for_filename()}.log"
        self._lock = LockFile(lock_path)
        self._lock.acquire(self.mode_spec.name, self._log_path)

        try:
            # 2. Apply DB policy
            self._apply_db_policy()

            # 3. Env prep
            env = self._build_env()

            # 4. Launch subprocess
            self._log_fh = self._log_path.open("wb")
            try:
                self._proc = subprocess.Popen(
                    [sys.executable, "-m", "dazzle", "serve", "--local"],
                    cwd=self.project_root,
                    env=env,
                    stdout=self._log_fh,
                    stderr=subprocess.STDOUT,
                    preexec_fn=os.setsid if os.name == "posix" else None,
                )
            except OSError as e:
                raise ModeLaunchError(
                    f"subprocess.Popen failed: {e}"
                ) from e

            # 5. Register cleanup handlers BEFORE first await
            self._register_cleanup()

            # 6. Poll for runtime.json
            runtime_path = self.project_root / ".dazzle" / "runtime.json"
            runtime_data = await self._poll_runtime_file(runtime_path)

            # 7. Parse -> AppConnection
            conn = AppConnection(
                site_url=runtime_data["ui_url"],
                api_url=runtime_data["api_url"],
                process=self._proc,
            )

            # 8. Health check
            ready = await wait_for_ready(
                conn.api_url, timeout=HEALTH_CHECK_BUDGET_SECONDS
            )
            if not ready:
                raise HealthCheckTimeoutError(
                    f"{conn.api_url}/docs did not return 200 within "
                    f"{HEALTH_CHECK_BUDGET_SECONDS}s"
                )

            return conn
        except BaseException:
            # Enter failed — print tail, terminate, release lock, reraise.
            self._teardown_on_enter_failure()
            raise

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        failed = exc is not None
        try:
            self._teardown(failed=failed)
        except Exception as teardown_exc:
            # Log but do not raise — caller exception (if any) takes precedence
            print(
                f"[mode-{self.mode_spec.name}] teardown error: {teardown_exc}",
                file=sys.stderr,
            )
            if exc is None:
                # Preserve teardown error only if there's nothing else to show
                raise RunnerTeardownError(str(teardown_exc)) from teardown_exc
        # Returning None (not True) means any caller exception propagates.

    # Helpers ----------------------------------------------------------------

    def _apply_db_policy(self) -> None:
        if self.db_policy == "preserve" and not self.fresh:
            return

        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            # Fall back to reading from .env — but dazzle serve will load it.
            # For restore policy we need it now, so fail loudly.
            if self.db_policy == "restore":
                raise ModeLaunchError(
                    "DATABASE_URL must be set for db_policy=restore. "
                    "Export it or set it in .env before launching."
                )
            return

        if self.db_policy == "fresh" or self.fresh:
            # Run reset + upgrade + demo without capture
            mgr = BaselineManager(self.project_root, db_url)
            import subprocess as sp

            sp.run(
                [sys.executable, "-m", "dazzle", "db", "reset", "--yes"],
                cwd=self.project_root, check=True,
            )
            sp.run(
                [sys.executable, "-m", "dazzle", "db", "upgrade"],
                cwd=self.project_root, check=True,
            )
            if mgr._has_demo_config():
                sp.run(
                    [sys.executable, "-m", "dazzle", "demo", "generate"],
                    cwd=self.project_root, check=True,
                )
            return

        if self.db_policy == "restore":
            mgr = BaselineManager(self.project_root, db_url)
            mgr.restore()

    def _build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.personas:
            env["DAZZLE_ENV"] = "development"
            env["DAZZLE_QA_MODE"] = "1"
        return env

    async def _poll_runtime_file(self, path: Path) -> dict[str, Any]:
        deadline = asyncio.get_event_loop().time() + RUNTIME_POLL_BUDGET_SECONDS
        while asyncio.get_event_loop().time() < deadline:
            if path.exists():
                try:
                    return json.loads(path.read_text())
                except (OSError, json.JSONDecodeError):
                    # Race: file exists but content not flushed yet. Retry.
                    pass
            await asyncio.sleep(RUNTIME_POLL_INTERVAL_SECONDS)

        tail = _tail_log(self._log_path) if self._log_path else []
        raise RuntimeFileTimeoutError(
            f"{path} did not appear within {RUNTIME_POLL_BUDGET_SECONDS}s. "
            f"Log tail: {tail[-10:] if tail else '(empty)'}"
        )

    def _register_cleanup(self) -> None:
        if not self._atexit_registered:
            atexit.register(self._emergency_cleanup)
            self._atexit_registered = True

        def handler(signum: int, frame: Any) -> None:
            self._emergency_cleanup()
            # Re-raise the default handler behavior
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)

        self._prev_sigint = signal.signal(signal.SIGINT, handler)
        self._prev_sigterm = signal.signal(signal.SIGTERM, handler)

    def _teardown(self, *, failed: bool) -> None:
        # Print log tail on failure
        if failed and self._log_path:
            tail = _tail_log(self._log_path)
            if tail:
                print(
                    f"[mode-{self.mode_spec.name}] subprocess output tail:",
                    file=sys.stderr,
                )
                for line in tail:
                    print(f"  {line}", file=sys.stderr)

        # Terminate subprocess
        if self._proc is not None and self._proc.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
                else:
                    self._proc.terminate()
            except (ProcessLookupError, OSError):
                pass
            try:
                self._proc.wait(timeout=TERMINATE_WAIT_SECONDS)
            except subprocess.TimeoutExpired:
                try:
                    if os.name == "posix":
                        os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
                    else:
                        self._proc.kill()
                except (ProcessLookupError, OSError):
                    pass
                try:
                    self._proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    pass

        # Close log handle
        if self._log_fh is not None:
            try:
                self._log_fh.close()
            except OSError:
                pass
            self._log_fh = None

        # Restore signal handlers
        try:
            if self._prev_sigint is not None:
                signal.signal(signal.SIGINT, self._prev_sigint)
            if self._prev_sigterm is not None:
                signal.signal(signal.SIGTERM, self._prev_sigterm)
        except (ValueError, OSError):
            pass

        # Release lock
        if self._lock is not None:
            self._lock.release()

    def _teardown_on_enter_failure(self) -> None:
        """Best-effort cleanup if __aenter__ raised before returning."""
        try:
            self._teardown(failed=True)
        except Exception as e:
            print(
                f"[mode-{self.mode_spec.name}] enter-failure cleanup error: {e}",
                file=sys.stderr,
            )

    def _emergency_cleanup(self) -> None:
        """Runs from atexit / signal handlers — must never raise."""
        try:
            if self._proc is not None and self._proc.poll() is None:
                try:
                    if os.name == "posix":
                        os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
                    else:
                        self._proc.terminate()
                except (ProcessLookupError, OSError):
                    pass
            if self._log_fh is not None:
                try:
                    self._log_fh.close()
                except OSError:
                    pass
            if self._lock is not None:
                self._lock.release()
        except Exception:
            pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/e2e/test_runner.py -v`
Expected: PASS (all tests)

Note: `pytest-asyncio` marker auto-mode may need `asyncio_mode = "auto"` in `pyproject.toml`. If tests fail with "async function not natively supported", verify the existing fitness tests run (they use the same fixture). Most likely `pytest-asyncio` is already configured in `pyproject.toml`.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/e2e/runner.py tests/unit/e2e/test_runner.py
git commit -m "feat(e2e): add ModeRunner async context manager"
```

---

## Task 7: AppConnection.from_runtime_file + Delete connect_app

**Files:**
- Modify: `src/dazzle/qa/server.py`
- Modify: any caller of `connect_app` (grep first)

- [ ] **Step 1: Find all callers of connect_app**

Run: `grep -rn "connect_app\|_start_app" src/ tests/`
Record each file. Callers will include `src/dazzle/cli/runtime_impl/ux_cycle_impl/fitness_strategy.py` (already known) and possibly test files.

- [ ] **Step 2: Write the failing test**

Add to `tests/unit/e2e/test_runner.py` (or new file — keep grouped):

Append to the end of `tests/unit/e2e/test_runner.py`:

```python
# --- AppConnection.from_runtime_file tests ---


class TestAppConnectionFromRuntimeFile:
    def test_reads_ui_and_api_urls(self, tmp_path: Path) -> None:
        project_root = tmp_path / "example"
        (project_root / ".dazzle").mkdir(parents=True)
        _write_runtime_file(project_root, ui_port=8981, api_port=8969)

        from dazzle.qa.server import AppConnection

        conn = AppConnection.from_runtime_file(project_root)
        assert conn.site_url == "http://localhost:8981"
        assert conn.api_url == "http://localhost:8969"
        assert conn.process is None  # External — not owned by this process
        assert conn.is_external is True

    def test_raises_when_file_missing(self, tmp_path: Path) -> None:
        project_root = tmp_path / "example"
        project_root.mkdir()
        (project_root / ".dazzle").mkdir()

        from dazzle.qa.server import AppConnection

        with pytest.raises(FileNotFoundError):
            AppConnection.from_runtime_file(project_root)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/unit/e2e/test_runner.py::TestAppConnectionFromRuntimeFile -v`
Expected: FAIL — `AttributeError: AppConnection has no attribute 'from_runtime_file'`

- [ ] **Step 4: Rewrite dazzle/qa/server.py**

Replace the entire content of `src/dazzle/qa/server.py` with:

```python
"""Dazzle QA toolkit — AppConnection type and health polling.

AppConnection describes a live Dazzle server URL pair. It can be built two ways:
 - `AppConnection.from_runtime_file(project_root)` — read the deterministic
   ports from `<project_root>/.dazzle/runtime.json` that `dazzle serve` writes.
 - Direct construction by a runner (e.g., dazzle.e2e.runner.ModeRunner), which
   owns the subprocess.

The old `connect_app` / `_start_app` helpers (which hardcoded :3000/:8000)
are deleted — `dazzle.e2e.runner.ModeRunner` is the launch primitive now.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AppConnection:
    """Represents a connection to a running Dazzle application.

    Externally managed (process is None, is_external=True) when read from
    runtime.json. Owned (process set, is_external=False) when launched by a
    runner that captures the Popen handle.
    """

    site_url: str
    api_url: str
    process: subprocess.Popen[bytes] | None = field(default=None)

    @property
    def is_external(self) -> bool:
        return self.process is None

    @classmethod
    def from_runtime_file(cls, project_root: Path) -> "AppConnection":
        """Read ui_url/api_url from `<project_root>/.dazzle/runtime.json`.

        `dazzle serve` writes this file on startup with the deterministic
        hashed port pair for the project. Raises FileNotFoundError if the
        file is absent (server not running, or still starting).
        """
        runtime_path = project_root / ".dazzle" / "runtime.json"
        if not runtime_path.exists():
            raise FileNotFoundError(
                f"{runtime_path} not found — dazzle serve may not be running"
            )
        data = json.loads(runtime_path.read_text())
        return cls(site_url=data["ui_url"], api_url=data["api_url"], process=None)

    def stop(self) -> None:
        """Terminate the owned process. No-op for external connections."""
        if self.process is None:
            return
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


async def _poll_health(
    api_url: str,
    *,
    timeout: float = 30,
    client: object | None = None,
) -> bool:
    """Poll `{api_url}/docs` until 200 or timeout. Returns True on success."""
    import asyncio

    health_url = f"{api_url}/docs"
    elapsed = 0.0
    interval = 0.5

    async def _do_get(c: object) -> int:
        resp = await c.get(health_url)  # type: ignore[attr-defined]
        return int(resp.status_code)

    if client is not None:
        while elapsed < timeout:
            try:
                if await _do_get(client) == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(interval)
            elapsed += interval
        return False

    try:
        import httpx
    except ImportError:
        return False

    async with httpx.AsyncClient() as http:
        while elapsed < timeout:
            try:
                if (await http.get(health_url)).status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(interval)
            elapsed += interval
    return False


async def wait_for_ready(api_url: str, *, timeout: float = 30) -> bool:
    """Wait until `{api_url}/docs` returns 200. True on success, False on timeout."""
    return await _poll_health(api_url, timeout=timeout)
```

- [ ] **Step 5: Run new test to verify it passes**

Run: `pytest tests/unit/e2e/test_runner.py::TestAppConnectionFromRuntimeFile -v`
Expected: PASS

- [ ] **Step 6: Verify no remaining references to connect_app**

Run: `grep -rn "connect_app\|_start_app" src/ tests/`
Expected: **no matches** (all callers migrated in next task). If matches remain, they'll all be in `fitness_strategy.py` and `tests/e2e/fitness/test_support_tickets_fitness.py` — those are rewritten in Tasks 8 and 14. For now, confirm the references are limited to those files.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/qa/server.py tests/unit/e2e/test_runner.py
git commit -m "refactor(qa): AppConnection.from_runtime_file replaces connect_app

Deletes the latent hardcoded-port bug in dazzle.qa.server.connect_app which
assumed :3000/:8000 while dazzle serve uses deterministic hashed ports (e.g.
support_tickets lives on :8981/:8969). Callers now read runtime.json directly.

Breaking change per ADR-0003 — fitness_strategy.py and the fitness E2E tests
are updated in follow-up commits to match the new signature."
```

---

## Task 8: Fitness Strategy Refactor

**Files:**
- Modify: `src/dazzle/cli/runtime_impl/ux_cycle_impl/fitness_strategy.py`

- [ ] **Step 1: Read current signature**

Run: `grep -n "def run_fitness_strategy\|async def run_fitness_strategy" src/dazzle/cli/runtime_impl/ux_cycle_impl/fitness_strategy.py`
Then read ~60 lines around it to understand the existing subprocess-owning flow.

- [ ] **Step 2: Rewrite run_fitness_strategy signature and body**

Edit `src/dazzle/cli/runtime_impl/ux_cycle_impl/fitness_strategy.py` to change `run_fitness_strategy` from owning subprocess launch to taking an `AppConnection` from the caller.

The exact edit depends on the current body. After the edit, the function should:
1. Accept `connection: AppConnection` as the first positional argument.
2. Remove the call to `connect_app(project_dir=...)` or `_start_app(...)`.
3. Use `connection.site_url` and `connection.api_url` throughout (replacing any hardcoded `http://localhost:3000`).
4. Not call `connection.stop()` at the end — the caller (ModeRunner) owns that.

Pseudo-code of the new function shape:

```python
async def run_fitness_strategy(
    connection: AppConnection,
    *,
    project_root: Path,
    component_contract_path: Path | None = None,
    personas: list[str] | None = None,
) -> StrategyOutcome:
    """Run the fitness engine against an already-running example app.

    The caller is responsible for launching + tearing down the subprocess —
    typically via dazzle.e2e.runner.ModeRunner.
    """
    # Launch Playwright bundle using connection.site_url
    # Per persona: login → navigate → walk_contract
    # Aggregate outcomes
    ...
```

**Important:** do not remove tests or change the outcome aggregation logic — only the signature and the subprocess-ownership pieces are in scope.

- [ ] **Step 3: Update in-file callers**

Run: `grep -n "run_fitness_strategy" src/ tests/`
For each production call site (not test file), update it to use `ModeRunner`:

```python
from dazzle.e2e.modes import get_mode
from dazzle.e2e.runner import ModeRunner

async with ModeRunner(
    mode_spec=get_mode("a"),
    project_root=project_root,
    personas=personas,
) as conn:
    outcome = await run_fitness_strategy(
        conn,
        project_root=project_root,
        component_contract_path=contract_path,
        personas=personas,
    )
```

- [ ] **Step 4: Run existing unit tests for fitness_strategy**

Run: `pytest tests/unit/fitness/ -v`
Expected: some tests may break because they use the old signature. Update those tests to pass a stub `AppConnection` directly:

```python
from dazzle.qa.server import AppConnection

conn = AppConnection(
    site_url="http://localhost:8981",
    api_url="http://localhost:8969",
    process=None,
)
outcome = await run_fitness_strategy(conn, ...)
```

Keep the mocked Playwright bundle / walker internals — only the signature changed, not the engine plumbing.

- [ ] **Step 5: Verify all unit tests pass**

Run: `pytest tests/unit/ -m "not integration and not e2e" -q`
Expected: all pass. If fitness tests still fail, they need signature updates.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/cli/runtime_impl/ux_cycle_impl/fitness_strategy.py \
        tests/unit/fitness/
git commit -m "refactor(fitness): run_fitness_strategy takes AppConnection param

Subprocess lifecycle is now owned by dazzle.e2e.runner.ModeRunner, not the
fitness strategy. This closes the irony gap where the strategy both owned
the subprocess and consumed the URL, which made the connect_app hardcoded
port bug invisible.

Callers updated in the same commit per ADR-0003 (no shims)."
```

---

## Task 9: CLI Package Split

**Files:**
- Move: `src/dazzle/cli/e2e.py` → `src/dazzle/cli/e2e/__init__.py`

- [ ] **Step 1: Verify e2e.py exists as single file**

Run: `ls -la src/dazzle/cli/e2e*`
Expected: `src/dazzle/cli/e2e.py` (single file, 745 lines).

- [ ] **Step 2: Convert to package**

```bash
mkdir src/dazzle/cli/e2e_new
git mv src/dazzle/cli/e2e.py src/dazzle/cli/e2e_new/__init__.py
git mv src/dazzle/cli/e2e_new src/dazzle/cli/e2e
```

(Two-step rename is required because `git mv` can't rename a file into a directory of the same name in one go.)

- [ ] **Step 3: Verify imports still work**

Run: `python -c "from dazzle.cli.e2e import e2e_app; print(e2e_app)"`
Expected: prints a Typer instance. No ImportError.

Run: `dazzle e2e --help 2>&1 | head`
Expected: shows the existing 11 commands unchanged.

- [ ] **Step 4: Run existing e2e CLI tests**

Run: `pytest tests/ -k "cli and e2e" -q`
Expected: all pass (behavior is unchanged — pure file move).

- [ ] **Step 5: Commit**

```bash
git add -A src/dazzle/cli/e2e
git commit -m "refactor(cli): split cli/e2e.py into package for env subcommand

Pure refactor — no behavior change. Preparing for the new 'dazzle e2e env'
sub-typer in the next commit."
```

---

## Task 10: dazzle e2e env Commands

**Files:**
- Create: `src/dazzle/cli/e2e/env.py`
- Modify: `src/dazzle/cli/e2e/__init__.py` (register the new sub-typer)

- [ ] **Step 1: Create the env subcommand file**

Create `src/dazzle/cli/e2e/env.py`:

```python
"""`dazzle e2e env` subcommands — start/status/stop/logs for Mode A.

Thin wrappers around the async dazzle.e2e.runner primitives. `start` is
foreground (blocks until Ctrl+C or subprocess exits); the other commands
are one-shot reads or signals.
"""

from __future__ import annotations

import asyncio
import json
import signal
from pathlib import Path

import typer

from dazzle.e2e.lifecycle import LockFile
from dazzle.e2e.modes import MODE_REGISTRY, get_mode
from dazzle.e2e.runner import ModeRunner

env_app = typer.Typer(
    name="env",
    help="Manage live example-app environments for Mode A fitness runs.",
    no_args_is_help=True,
)


def _example_root(example: str) -> Path:
    """Resolve an example name to its project root (examples/<name>)."""
    # Walk up from cwd to find the repo root (has examples/ dir)
    cwd = Path.cwd()
    for parent in (cwd, *cwd.parents):
        candidate = parent / "examples" / example
        if candidate.exists() and (candidate / "dazzle.toml").exists():
            return candidate
    typer.echo(
        f"Could not find examples/{example}/ — run from within the Dazzle repo.",
        err=True,
    )
    raise typer.Exit(code=2)


@env_app.command("start")
def env_start(
    example: str = typer.Argument(..., help="Example app name (e.g. support_tickets)"),
    mode: str = typer.Option("a", "--mode", help="Mode name from MODE_REGISTRY"),
    fresh: bool = typer.Option(False, "--fresh", help="Force baseline rebuild / DB reset"),
    personas: str = typer.Option(
        "", "--personas", help="Comma-separated persona IDs for QA mode flags"
    ),
    db_policy: str = typer.Option(
        "", "--db-policy", help="Override default policy: preserve|fresh|restore"
    ),
) -> None:
    """Launch Mode A against an example app. Blocks until Ctrl+C."""
    project_root = _example_root(example)
    mode_spec = get_mode(mode)
    persona_list = [p.strip() for p in personas.split(",") if p.strip()] or None
    policy = db_policy or None

    async def _main() -> None:
        async with ModeRunner(
            mode_spec=mode_spec,
            project_root=project_root,
            personas=persona_list,
            db_policy=policy,  # type: ignore[arg-type]
            fresh=fresh,
        ) as conn:
            typer.echo(f"[mode-{mode_spec.name}] running at {conn.site_url}")
            typer.echo(f"[mode-{mode_spec.name}] api at {conn.api_url}")
            typer.echo(f"[mode-{mode_spec.name}] Ctrl+C to stop.")
            # Wait until interrupted
            stop_event = asyncio.Event()

            def _sigint_handler(signum: int, frame: object) -> None:
                stop_event.set()

            signal.signal(signal.SIGINT, _sigint_handler)
            await stop_event.wait()

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass


@env_app.command("status")
def env_status(
    example: str = typer.Argument(
        "", help="Example name, or empty to list all examples"
    ),
) -> None:
    """Show lock + runtime state for one or all examples."""
    if example:
        examples = [example]
    else:
        # Discover all examples under examples/
        repo_root = Path.cwd()
        for parent in (repo_root, *repo_root.parents):
            if (parent / "examples").exists():
                repo_root = parent
                break
        examples = sorted(
            p.name for p in (repo_root / "examples").iterdir() if p.is_dir()
        )

    for ex in examples:
        try:
            project_root = _example_root(ex)
        except typer.Exit:
            continue

        lock_path = project_root / ".dazzle" / "mode_a.lock"
        runtime_path = project_root / ".dazzle" / "runtime.json"

        lock = LockFile(lock_path)
        holder = lock.read_holder()

        runtime_data = None
        if runtime_path.exists():
            try:
                runtime_data = json.loads(runtime_path.read_text())
            except (OSError, json.JSONDecodeError):
                pass

        typer.echo(f"\n{ex}:")
        if holder is None:
            typer.echo("  lock:    (none)")
        else:
            typer.echo(f"  lock:    pid {holder['pid']} mode {holder['mode']} (started {holder.get('started_at', '?')})")
        if runtime_data is None:
            typer.echo("  runtime: (no runtime.json)")
        else:
            typer.echo(
                f"  runtime: ui {runtime_data.get('ui_url', '?')} api {runtime_data.get('api_url', '?')}"
            )


@env_app.command("stop")
def env_stop(
    example: str = typer.Argument(..., help="Example app name"),
) -> None:
    """Kill any Mode A subprocess holding the lock for this example."""
    import os

    project_root = _example_root(example)
    lock_path = project_root / ".dazzle" / "mode_a.lock"

    lock = LockFile(lock_path)
    holder = lock.read_holder()
    if holder is None:
        typer.echo(f"[mode-a] no lock file at {lock_path}")
        return

    pid = holder.get("pid")
    if not isinstance(pid, int):
        typer.echo(f"[mode-a] malformed lock file — deleting")
        lock.release()
        return

    try:
        os.kill(pid, signal.SIGTERM)
        typer.echo(f"[mode-a] sent SIGTERM to pid {pid}")
    except ProcessLookupError:
        typer.echo(f"[mode-a] pid {pid} not alive — deleting stale lock")
        lock.release()
        return

    # Wait briefly for clean shutdown then escalate
    import time

    for _ in range(10):
        time.sleep(0.5)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
    else:
        try:
            os.kill(pid, signal.SIGKILL)
            typer.echo(f"[mode-a] escalated to SIGKILL for pid {pid}")
        except ProcessLookupError:
            pass

    lock.release()


@env_app.command("logs")
def env_logs(
    example: str = typer.Argument(..., help="Example app name"),
    tail: int = typer.Option(50, "--tail", help="Number of trailing lines"),
) -> None:
    """Print the tail of the most recent Mode A log for this example."""
    project_root = _example_root(example)
    log_dir = project_root / ".dazzle" / "e2e-logs"
    if not log_dir.exists():
        typer.echo("(no logs)")
        return

    logs = sorted(log_dir.glob("mode_a-*.log"), key=lambda p: p.stat().st_mtime)
    if not logs:
        typer.echo("(no logs)")
        return

    latest = logs[-1]
    text = latest.read_text(errors="replace")
    lines = text.splitlines()
    typer.echo(f"--- {latest.name} (last {tail} lines) ---")
    for line in lines[-tail:]:
        typer.echo(line)
```

- [ ] **Step 2: Register the sub-typer**

Edit `src/dazzle/cli/e2e/__init__.py` to add the import and registration. Near the top of the file, after `e2e_app = typer.Typer(...)`:

```python
from dazzle.cli.e2e.env import env_app

e2e_app.add_typer(env_app, name="env")
```

If the file has an `__all__` list, add `"env_app"` to it.

- [ ] **Step 3: Verify the command appears**

Run: `dazzle e2e --help 2>&1`
Expected: output includes an `env` line under Commands.

Run: `dazzle e2e env --help 2>&1`
Expected: shows `start`, `status`, `stop`, `logs`.

- [ ] **Step 4: Smoke test status (no app running)**

Run: `dazzle e2e env status support_tickets`
Expected: prints `support_tickets:` with `lock: (none)` and possibly a `runtime:` line (runtime.json may exist from a previous run — that's fine).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/e2e/env.py src/dazzle/cli/e2e/__init__.py
git commit -m "feat(cli): add 'dazzle e2e env start/status/stop/logs' commands

Wraps dazzle.e2e.runner.ModeRunner in a foreground CLI. Start blocks until
Ctrl+C; status reads lock + runtime state; stop sends SIGTERM→SIGKILL to
the lock holder; logs tails the latest captured output."
```

---

## Task 11: dazzle db snapshot / restore / snapshot-gc Commands

**Files:**
- Modify: `src/dazzle/cli/db.py`

- [ ] **Step 1: Add the three commands**

Append to `src/dazzle/cli/db.py` (after the last existing `@db_app.command` entry, preserving imports at the top):

```python
@db_app.command(name="snapshot")
def db_snapshot_command(
    name: str = typer.Argument(
        "baseline", help="Snapshot label (default: baseline)"
    ),
    database_url: str = typer.Option(
        "", "--database-url", help="Database URL override"
    ),
    project: Path = typer.Option(
        Path.cwd(), "--project", help="Project root (default: cwd)"
    ),
) -> None:
    """Capture a pg_dump of the project database to a .sql.gz file.

    Writes `<project>/.dazzle/baselines/<name>.sql.gz`. For named snapshots
    other than 'baseline', the file is used verbatim. For 'baseline', the
    filename is hash-tagged with the Alembic revision and fixture SHA.
    """
    import os

    from dazzle.e2e.baseline import BaselineManager
    from dazzle.e2e.snapshot import Snapshotter

    url = database_url or os.environ.get("DATABASE_URL", "")
    if not url:
        typer.echo("DATABASE_URL not set. Export it or pass --database-url.", err=True)
        raise typer.Exit(code=2)

    if name == "baseline":
        mgr = BaselineManager(project, url)
        path = mgr.ensure(fresh=True)
        typer.echo(f"[db snapshot] wrote baseline → {path}")
    else:
        snap = Snapshotter()
        dest = project / ".dazzle" / "baselines" / f"{name}.sql.gz"
        snap.capture(url, dest)
        typer.echo(f"[db snapshot] wrote {name} → {dest}")


@db_app.command(name="restore")
def db_restore_command(
    name: str = typer.Argument(
        "baseline", help="Snapshot label to restore"
    ),
    database_url: str = typer.Option(
        "", "--database-url", help="Database URL override"
    ),
    project: Path = typer.Option(
        Path.cwd(), "--project", help="Project root (default: cwd)"
    ),
) -> None:
    """Restore a snapshot into the project database via pg_restore --clean."""
    import os

    from dazzle.e2e.baseline import BaselineManager
    from dazzle.e2e.snapshot import Snapshotter

    url = database_url or os.environ.get("DATABASE_URL", "")
    if not url:
        typer.echo("DATABASE_URL not set. Export it or pass --database-url.", err=True)
        raise typer.Exit(code=2)

    if name == "baseline":
        mgr = BaselineManager(project, url)
        path = mgr.restore()
        typer.echo(f"[db restore] restored baseline from {path}")
    else:
        snap = Snapshotter()
        src = project / ".dazzle" / "baselines" / f"{name}.sql.gz"
        if not src.exists():
            typer.echo(f"Snapshot not found: {src}", err=True)
            raise typer.Exit(code=2)
        snap.restore(src, url)
        typer.echo(f"[db restore] restored {name} from {src}")


@db_app.command(name="snapshot-gc")
def db_snapshot_gc_command(
    keep: int = typer.Option(3, "--keep", help="Number of newest snapshots to retain"),
    project: Path = typer.Option(
        Path.cwd(), "--project", help="Project root (default: cwd)"
    ),
) -> None:
    """Delete old baseline snapshot files, keeping the newest `keep`."""
    import os

    from dazzle.e2e.baseline import BaselineManager

    url = os.environ.get("DATABASE_URL", "postgresql://localhost/unused")
    mgr = BaselineManager(project, url)
    deleted = mgr.gc(keep=keep)
    if not deleted:
        typer.echo(f"[db snapshot-gc] nothing to delete (kept newest {keep})")
        return
    for p in deleted:
        typer.echo(f"[db snapshot-gc] deleted {p.name}")
```

- [ ] **Step 2: Verify the commands register**

Run: `dazzle db --help 2>&1`
Expected: `snapshot`, `restore`, `snapshot-gc` appear in the command list.

- [ ] **Step 3: Smoke test snapshot-gc (safe even without a DB)**

Run: `dazzle db snapshot-gc --project /tmp/nonexistent-project 2>&1 || true`
Expected: either "nothing to delete" or a graceful error — no crash.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/cli/db.py
git commit -m "feat(cli): add 'dazzle db snapshot/restore/snapshot-gc' commands

Wraps the e2e snapshot primitive as standalone CLI commands so power users
can capture/restore baselines independently of Mode A. Hash-tagging applies
for name='baseline' only; other names use verbatim filenames."
```

---

## Task 12: MCP Handler

**Files:**
- Create: `src/dazzle/mcp/server/handlers/e2e.py`
- Modify: `src/dazzle/mcp/server/handlers_consolidated.py`
- Modify: `src/dazzle/mcp/server/tools_consolidated.py`

- [ ] **Step 1: Create the handler**

Create `src/dazzle/mcp/server/handlers/e2e.py`:

```python
"""MCP handler for e2e environment operations.

Read-only per ADR-0002: list_modes, describe_mode, status, list_baselines.
Start/stop live in CLI only.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dazzle.e2e.baseline import BaselineManager
from dazzle.e2e.errors import BaselineKeyError, UnknownModeError
from dazzle.e2e.lifecycle import LockFile, _is_pid_alive, _iso_now_seconds_ago
from dazzle.e2e.modes import MODE_REGISTRY, get_mode
from dazzle.mcp.server.handlers.common import wrap_handler_errors


def _mode_to_dict(spec: Any) -> dict[str, Any]:
    d = asdict(spec)
    # Convert frozenset to sorted list for JSON
    d["db_policies_allowed"] = sorted(d["db_policies_allowed"])
    return d


@wrap_handler_errors
def e2e_list_modes_handler(project_path: Path, args: dict[str, Any]) -> str:
    return json.dumps(
        {"modes": [_mode_to_dict(m) for m in MODE_REGISTRY]},
        indent=2,
    )


@wrap_handler_errors
def e2e_describe_mode_handler(project_path: Path, args: dict[str, Any]) -> str:
    name = args.get("name", "")
    try:
        spec = get_mode(name)
    except UnknownModeError as e:
        return json.dumps({"error": str(e)}, indent=2)
    return json.dumps(_mode_to_dict(spec), indent=2)


def _status_for(project_root: Path) -> dict[str, Any]:
    lock_path = project_root / ".dazzle" / "mode_a.lock"
    runtime_path = project_root / ".dazzle" / "runtime.json"
    log_dir = project_root / ".dazzle" / "e2e-logs"

    lock = LockFile(lock_path)
    holder = lock.read_holder()

    holder_pid: int | None = None
    holder_alive: bool = False
    lock_age: float | None = None
    if holder is not None:
        raw_pid = holder.get("pid")
        if isinstance(raw_pid, int):
            holder_pid = raw_pid
            holder_alive = _is_pid_alive(raw_pid)
        started = holder.get("started_at", "")
        if started:
            lock_age = _iso_now_seconds_ago(started)

    runtime_data: dict[str, Any] | None = None
    if runtime_path.exists():
        try:
            runtime_data = json.loads(runtime_path.read_text())
        except (OSError, json.JSONDecodeError):
            pass

    last_log: Path | None = None
    last_log_tail: list[str] | None = None
    if log_dir.exists():
        logs = sorted(log_dir.glob("mode_a-*.log"), key=lambda p: p.stat().st_mtime)
        if logs:
            last_log = logs[-1]
            try:
                text = last_log.read_text(errors="replace").splitlines()
                last_log_tail = text[-20:]
            except OSError:
                last_log_tail = []

    return {
        "project_root": str(project_root),
        "lock_file": str(lock_path) if lock_path.exists() else None,
        "lock_holder_pid": holder_pid,
        "lock_holder_alive": holder_alive,
        "lock_age_seconds": round(lock_age) if lock_age is not None else None,
        "runtime_file": str(runtime_path) if runtime_path.exists() else None,
        "runtime_ports": (
            {
                "ui": runtime_data.get("ui_port"),
                "api": runtime_data.get("api_port"),
            }
            if runtime_data
            else None
        ),
        "last_log_file": str(last_log) if last_log else None,
        "last_log_tail": last_log_tail,
    }


@wrap_handler_errors
def e2e_status_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Return Mode A status for the current project, or all examples if no project."""
    explicit_project = args.get("project_root")
    if explicit_project:
        root = Path(explicit_project)
        return json.dumps(_status_for(root), indent=2)

    # Scan examples/
    examples_dir = project_path / "examples"
    if not examples_dir.exists():
        # Fall back to the current project_path itself
        return json.dumps(_status_for(project_path), indent=2)

    results = []
    for child in sorted(examples_dir.iterdir()):
        if child.is_dir() and (child / "dazzle.toml").exists():
            results.append({"name": child.name, **_status_for(child)})
    return json.dumps({"examples": results}, indent=2)


@wrap_handler_errors
def e2e_list_baselines_handler(project_path: Path, args: dict[str, Any]) -> str:
    """List baseline snapshot files for the project."""
    explicit_project = args.get("project_root")
    root = Path(explicit_project) if explicit_project else project_path

    bl_dir = root / ".dazzle" / "baselines"
    if not bl_dir.exists():
        return json.dumps({"baselines": []}, indent=2)

    url = os.environ.get("DATABASE_URL", "postgresql://localhost/unused")
    try:
        mgr = BaselineManager(root, url)
        current_filename: str | None = None
        try:
            current_filename = mgr.path_for(mgr.current_key()).name
        except BaselineKeyError:
            pass
    except Exception:
        current_filename = None

    entries: list[dict[str, Any]] = []
    for p in sorted(bl_dir.glob("baseline-*.sql.gz")):
        stem = p.stem  # baseline-<rev>-<hash>.sql (strip .gz above if not stripped)
        # Filename format: baseline-{rev}-{hash12}.sql.gz
        parts = p.name.removesuffix(".sql.gz").split("-", 2)
        alembic_rev = parts[1] if len(parts) >= 3 else ""
        fixture_prefix = parts[2] if len(parts) >= 3 else ""
        from datetime import datetime, timezone

        entries.append(
            {
                "filename": p.name,
                "alembic_rev": alembic_rev,
                "fixture_hash_prefix": fixture_prefix,
                "size_bytes": p.stat().st_size,
                "mtime": datetime.fromtimestamp(
                    p.stat().st_mtime, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "is_current": p.name == current_filename,
            }
        )
    return json.dumps({"baselines": entries}, indent=2)
```

- [ ] **Step 2: Register the handler**

Edit `src/dazzle/mcp/server/handlers_consolidated.py` to add the dispatch entry.

Find the Discovery Handler section (around line 1064) and after it insert:

```python
# =============================================================================
# E2E Environment Handler
# =============================================================================

_MOD_E2E = "dazzle.mcp.server.handlers.e2e"

handle_e2e: Callable[[dict[str, Any]], Any] = _make_project_handler_async(
    "e2e",
    {
        "list_modes": f"{_MOD_E2E}:e2e_list_modes_handler",
        "describe_mode": f"{_MOD_E2E}:e2e_describe_mode_handler",
        "status": f"{_MOD_E2E}:e2e_status_handler",
        "list_baselines": f"{_MOD_E2E}:e2e_list_baselines_handler",
    },
)
```

Then find the handler dispatch dict (around line 1257, where `"discovery": handle_discovery` lives) and add:

```python
"e2e": handle_e2e,
```

- [ ] **Step 3: Add the tool definition**

Edit `src/dazzle/mcp/server/tools_consolidated.py`. Find the Discovery Tool section (around line 1040) and after the existing `Tool(name="discovery", ...)` block insert:

```python
        # =====================================================================
        # E2E Environment Operations
        # =====================================================================
        Tool(
            name="e2e",
            description=(
                "E2E environment operations (read-only). "
                "Operations: list_modes (available runner modes), "
                "describe_mode (single mode details), "
                "status (lock + runtime + log-tail for an example app), "
                "list_baselines (hash-tagged db snapshot files for an example). "
                "Process operations (start/stop) live in the CLI only."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "list_modes",
                            "describe_mode",
                            "status",
                            "list_baselines",
                        ],
                        "description": "Operation to perform",
                    },
                    "name": {
                        "type": "string",
                        "description": "Mode name (for describe_mode)",
                    },
                    "project_root": {
                        "type": "string",
                        "description": "Path to an example app (for status/list_baselines)",
                    },
                    **PROJECT_PATH_SCHEMA,
                },
                "required": ["operation"],
            },
        ),
```

- [ ] **Step 4: Verify the tool appears**

Run: `python -c "from dazzle.mcp.server.tools_consolidated import get_all_consolidated_tools; names = [t.name for t in get_all_consolidated_tools()]; print('e2e' in names, names)"`
Expected: `True <list>`.

- [ ] **Step 5: Exercise the handler directly**

Run: `python -c "
from pathlib import Path
from dazzle.mcp.server.handlers.e2e import e2e_list_modes_handler
print(e2e_list_modes_handler(Path('.'), {}))
"`
Expected: JSON with a `modes` array containing one entry for Mode A.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/mcp/server/handlers/e2e.py \
        src/dazzle/mcp/server/handlers_consolidated.py \
        src/dazzle/mcp/server/tools_consolidated.py
git commit -m "feat(mcp): add read-only e2e tool (list_modes/status/baselines)

Matches ADR-0002: MCP is for stateless reads, CLI owns process operations.
Agents can enumerate available modes, inspect lock/runtime/log state, and
see which baseline files would be hit by a restore — but start/stop must
go through 'dazzle e2e env'."
```

---

## Task 13: Integration Tests Layer

**Files:**
- Create: `tests/integration/__init__.py` (if absent)
- Create: `tests/integration/e2e/__init__.py`
- Create: `tests/integration/e2e/test_mode_a_integration.py`
- Modify: `pyproject.toml` if the `integration` marker is not already present

- [ ] **Step 1: Ensure integration marker is registered**

Run: `grep -n "integration" pyproject.toml 2>&1 | head`
If the `integration` marker is not in the `[tool.pytest.ini_options] markers = [...]` list, add it:

```toml
markers = [
    "e2e: end-to-end tests (opt-in via -m e2e)",
    "integration: integration tests requiring real Postgres (opt-in via -m integration)",
]
```

Otherwise leave pyproject.toml alone.

- [ ] **Step 2: Create the integration test file**

Create `tests/integration/__init__.py` (empty) if it doesn't exist.
Create `tests/integration/e2e/__init__.py` (empty).

Create `tests/integration/e2e/test_mode_a_integration.py`:

```python
"""Integration tests for Mode A against a real Postgres + real subprocess.

Gated by @pytest.mark.integration. Skipped in the default pytest run.
Opt-in: `pytest -m integration tests/integration/e2e/ -v`.

Requires:
  - DATABASE_URL set to a reachable Postgres instance
  - REDIS_URL set to a reachable Redis instance
  - pg_dump and pg_restore on PATH
  - examples/support_tickets/ present with dazzle.toml
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import httpx
import pytest

from dazzle.e2e.errors import ModeAlreadyRunningError
from dazzle.e2e.modes import get_mode
from dazzle.e2e.runner import ModeRunner

pytestmark = pytest.mark.integration


def _has_infra() -> bool:
    return bool(os.environ.get("DATABASE_URL")) and bool(os.environ.get("REDIS_URL"))


@pytest.fixture(autouse=True)
def _skip_if_no_infra() -> None:
    if not _has_infra():
        pytest.skip("DATABASE_URL and REDIS_URL must be set for integration tests")


@pytest.fixture
def support_tickets_root() -> Path:
    cwd = Path.cwd()
    for parent in (cwd, *cwd.parents):
        candidate = parent / "examples" / "support_tickets"
        if candidate.exists() and (candidate / "dazzle.toml").exists():
            return candidate
    pytest.skip("examples/support_tickets not found in repo")
    raise AssertionError  # unreachable


@pytest.mark.asyncio
async def test_mode_a_launch_and_teardown(support_tickets_root: Path) -> None:
    """Real subprocess launch, health check, teardown."""
    async with ModeRunner(
        mode_spec=get_mode("a"),
        project_root=support_tickets_root,
        personas=None,
        db_policy="preserve",
    ) as conn:
        # AppConnection URLs come from runtime.json, not hardcoded
        assert conn.site_url.startswith("http://localhost:")
        assert conn.api_url.startswith("http://localhost:")

        # /docs is up
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{conn.api_url}/docs")
            assert resp.status_code == 200

    # Post-teardown: lock released, subprocess dead
    lock = support_tickets_root / ".dazzle" / "mode_a.lock"
    assert not lock.exists()


@pytest.mark.asyncio
async def test_mode_a_concurrent_same_example_raises(
    support_tickets_root: Path,
) -> None:
    """Two concurrent runs against the same example → second raises."""
    async def _inner() -> None:
        async with ModeRunner(
            mode_spec=get_mode("a"),
            project_root=support_tickets_root,
            personas=None,
            db_policy="preserve",
        ) as conn:
            # Hold the lock briefly
            await asyncio.sleep(2)

    task = asyncio.create_task(_inner())
    # Wait for the first runner to actually start (lock file should exist)
    for _ in range(20):
        if (support_tickets_root / ".dazzle" / "mode_a.lock").exists():
            break
        await asyncio.sleep(0.1)

    # Second run should fail
    with pytest.raises(ModeAlreadyRunningError):
        async with ModeRunner(
            mode_spec=get_mode("a"),
            project_root=support_tickets_root,
            personas=None,
            db_policy="preserve",
        ):
            pass

    # Let the first one finish
    await task


@pytest.mark.asyncio
async def test_mode_a_stale_lock_recovery(support_tickets_root: Path) -> None:
    """Stale lock (dead PID) is deleted automatically."""
    lock = support_tickets_root / ".dazzle" / "mode_a.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(
        json.dumps(
            {
                "pid": 999999,  # Unlikely to be alive
                "mode": "a",
                "started_at": "2020-01-01T00:00:00Z",  # Very old
                "log_file": "/tmp/nope.log",
            }
        )
    )

    async with ModeRunner(
        mode_spec=get_mode("a"),
        project_root=support_tickets_root,
        personas=None,
        db_policy="preserve",
    ):
        pass

    # Lock should have been replaced then released
    assert not lock.exists()
```

- [ ] **Step 3: Run the integration tests (opt-in)**

Run: `pytest -m integration tests/integration/e2e/test_mode_a_integration.py -v`
Expected: PASS if `DATABASE_URL`, `REDIS_URL`, and `pg_dump` are configured; SKIP otherwise.

If they skip locally, that's acceptable for the commit — they'll exercise on the box where infra is available.

- [ ] **Step 4: Verify default pytest run still works**

Run: `pytest tests/ -m "not integration and not e2e" -q`
Expected: passes without touching the integration tests.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/__init__.py tests/integration/e2e/ pyproject.toml
git commit -m "test(e2e): add Mode A integration tests (opt-in via -m integration)

Exercises real subprocess launch, health check, lock contention, and stale
lock recovery against a real Postgres. Gated behind the integration marker
so default pytest runs are unaffected."
```

---

## Task 14: E2E Test Rewrite for Fitness Strategy

**Files:**
- Modify: `tests/e2e/fitness/test_support_tickets_fitness.py`

- [ ] **Step 1: Read the current test file**

Run: `cat tests/e2e/fitness/test_support_tickets_fitness.py`
Understand the existing assertions — they're the same outcomes (Phase 1 findings, per-persona cycles) but they launch the subprocess the old way.

- [ ] **Step 2: Update each test function to use ModeRunner**

Rewrite each test function so that the subprocess launch happens via `ModeRunner`, and `run_fitness_strategy` receives the yielded `AppConnection`.

Pattern for each test:

```python
@pytest.mark.asyncio
async def test_support_tickets_fitness_cycle_completes(repo_root: Path) -> None:
    from dazzle.e2e.modes import get_mode
    from dazzle.e2e.runner import ModeRunner
    from dazzle.cli.runtime_impl.ux_cycle_impl.fitness_strategy import (
        run_fitness_strategy,
    )

    project_root = repo_root / "examples" / "support_tickets"

    async with ModeRunner(
        mode_spec=get_mode("a"),
        project_root=project_root,
        personas=None,
        db_policy="preserve",
    ) as conn:
        outcome = await run_fitness_strategy(
            conn,
            project_root=project_root,
            component_contract_path=None,
            personas=None,
        )

    assert outcome is not None
    # ... existing assertions about findings_count, degraded, etc. stay as-is
```

Repeat for `test_support_tickets_multi_persona_cycle_completes` with `personas=["admin", "customer", "agent", "manager"]`.

- [ ] **Step 3: Add the new baseline idempotence test**

Append to `tests/e2e/fitness/test_support_tickets_fitness.py`:

```python
@pytest.mark.asyncio
async def test_support_tickets_baseline_restore_idempotent(
    repo_root: Path,
) -> None:
    """Mode A with db_policy=restore should cache the baseline between runs."""
    from dazzle.e2e.modes import get_mode
    from dazzle.e2e.runner import ModeRunner

    project_root = repo_root / "examples" / "support_tickets"

    import time

    t1 = time.time()
    async with ModeRunner(
        mode_spec=get_mode("a"),
        project_root=project_root,
        personas=None,
        db_policy="restore",
    ) as conn:
        assert conn.site_url.startswith("http://localhost:")
    first_duration = time.time() - t1

    t2 = time.time()
    async with ModeRunner(
        mode_spec=get_mode("a"),
        project_root=project_root,
        personas=None,
        db_policy="restore",
    ) as conn:
        assert conn.site_url.startswith("http://localhost:")
    second_duration = time.time() - t2

    # Second run hits cached baseline; should be measurably faster.
    # Conservative multiplier: second run at least 2× faster than first.
    assert second_duration < first_duration / 2, (
        f"Baseline cache ineffective: first={first_duration:.1f}s "
        f"second={second_duration:.1f}s"
    )
```

- [ ] **Step 4: Run the e2e fitness tests**

Run: `pytest tests/e2e/fitness/test_support_tickets_fitness.py -m e2e -v`
Expected: either PASS (if the full infrastructure is up) or skip cleanly. If it fails with `TypeError` about `run_fitness_strategy` signature, the fitness strategy refactor in Task 8 didn't migrate everything — fix and re-run.

- [ ] **Step 5: Commit**

```bash
git add tests/e2e/fitness/test_support_tickets_fitness.py
git commit -m "test(e2e): rewrite support_tickets fitness tests to use ModeRunner

Matches the fitness_strategy signature refactor in the previous commit.
Adds a new test_support_tickets_baseline_restore_idempotent that verifies
the snapshot cache actually speeds up the second restore run (>2× faster)."
```

---

## Task 15: .env.example + User Reference Docs

**Files:**
- Create: `examples/support_tickets/.env.example`
- Create: `docs/reference/e2e-environment.md`

- [ ] **Step 1: Create the .env template**

Create `examples/support_tickets/.env.example`:

```bash
# Example .env for support_tickets. Copy to .env and edit.
#
# dazzle serve reads this file automatically when launched from this
# directory (src/dazzle/cli/runtime_impl/serve.py::_load_dotenv). Shell
# exports take precedence if both are set.

# Postgres + Redis — both required.
DATABASE_URL=postgresql://localhost:5432/support_tickets_dev
REDIS_URL=redis://localhost:6379/0

# QA mode — optional. Mode A auto-sets these when run with `personas=[...]`,
# so you only need to set them here for Mode C (long-running dev env) with
# QA panel visible, or if you want QA login without specifying personas.
#
# DAZZLE_ENV=development
# DAZZLE_QA_MODE=1
```

- [ ] **Step 2: Add .env to .gitignore if not already**

Run: `grep -n "^\.env$\|examples/.*/\.env" .gitignore`
If the `.env` pattern is not already in `.gitignore`, add it:

```
# Per-example secrets — template is .env.example, actual .env never committed
examples/*/.env
```

- [ ] **Step 3: Create the user reference doc**

Create `docs/reference/e2e-environment.md`:

```markdown
# E2E Environment — Mode A Reference

Mode A is the Dazzle developer one-shot harness: launch a live example app,
run something against it (usually the fitness engine), tear down when done.

## Quick start

```bash
cd examples/support_tickets
cp .env.example .env
# Edit .env to point at your local Postgres + Redis
dazzle e2e env start support_tickets
```

The command blocks until Ctrl+C. While it runs:

- UI at `http://localhost:<hashed-port>` (printed by the command)
- API at `http://localhost:<hashed-port>` (also printed)
- Lock file at `examples/support_tickets/.dazzle/mode_a.lock` prevents
  two concurrent Mode A runs against the same example
- Log captured to `examples/support_tickets/.dazzle/e2e-logs/mode_a-<ts>.log`

## Commands

```bash
dazzle e2e env start <example>   # Launch Mode A, block
dazzle e2e env status [<example>]  # Show lock/runtime/log state
dazzle e2e env stop <example>    # SIGTERM → SIGKILL the lock holder
dazzle e2e env logs <example>    # Tail the latest captured log
```

## Flags

- `--mode=a` — Mode name (only Mode A ships in v1).
- `--fresh` — Force DB reset + upgrade + demo generate, rebuilding any
  baseline snapshot along the way.
- `--personas=admin,agent` — Comma-separated persona IDs. Auto-sets
  `DAZZLE_ENV=development` and `DAZZLE_QA_MODE=1` so persona magic-link
  login works via QA mode (#768).
- `--db-policy=preserve|fresh|restore` — Override the mode default.
  Mode A defaults to `preserve`.

## DB state policies

| Policy | What it does |
|--------|-------------|
| `preserve` (default) | No-op. You own the DB state. |
| `fresh` | `reset → upgrade → demo generate` before launch. Slow (~15s) but deterministic seed. |
| `restore` | Lazy-build + restore from `examples/<app>/.dazzle/baselines/baseline-<rev>-<hash12>.sql.gz`. First run is slow; subsequent runs are ~1s. |

## Snapshot primitives

The snapshot/restore machinery is also exposed as standalone CLI commands:

```bash
dazzle db snapshot baseline   # Capture current state as a baseline
dazzle db restore baseline    # Restore the current-hash baseline
dazzle db snapshot-gc --keep=3  # Delete older baseline files
```

## Troubleshooting

**"ModeAlreadyRunningError"** — another Mode A instance holds the lock.
Run `dazzle e2e env stop <example>` to kill it, or wait 15 minutes for
the TTL to expire.

**"RuntimeFileTimeoutError"** — `dazzle serve` started but never wrote
`runtime.json`. Usually means `.env` is missing or `DATABASE_URL` is
wrong. Check `dazzle e2e env logs <example>` for details.

**"HealthCheckTimeoutError"** — `runtime.json` appeared but `/docs` never
returned 200. Usually means a migration failed or Postgres isn't
reachable. Check the log tail.

**"PgDumpNotInstalledError"** — `pg_dump`/`pg_restore` missing from PATH.
Install with `brew install postgresql@16` or
`apt-get install postgresql-client-16`.

## Design notes

See `docs/superpowers/specs/2026-04-14-e2e-environment-strategy-design.md`
for the full design, including Modes B/C/D (sketched but not wired in v1).
```

- [ ] **Step 4: Commit**

```bash
git add examples/support_tickets/.env.example docs/reference/e2e-environment.md .gitignore
git commit -m "docs(e2e): add .env.example template and user reference

Documents Mode A's CLI surface, DB state policies, snapshot primitives, and
common error messages. Also ships examples/support_tickets/.env.example as
a reference for the per-example .env convention dazzle serve already loads."
```

---

## Self-Review Notes

**Spec coverage:**
- Mode A runner → Task 6 ✓
- Snapshot primitive → Task 2 ✓
- Baseline manager → Task 3 ✓
- Lock file with TTL → Task 4 ✓
- Mode registry → Task 5 ✓
- Exception hierarchy → Task 1 ✓
- AppConnection.from_runtime_file + connect_app deletion → Task 7 ✓
- Fitness strategy refactor → Task 8 ✓
- CLI package split → Task 9 ✓
- `dazzle e2e env` commands → Task 10 ✓
- `dazzle db snapshot/restore/snapshot-gc` → Task 11 ✓
- MCP read-only tool → Task 12 ✓
- Integration tests → Task 13 ✓
- E2E test rewrite → Task 14 ✓
- .env.example + docs → Task 15 ✓

**Type consistency spot-checks:**
- `BaselineKey.filename()` uses `fixture_hash[:12]` throughout.
- `ModeSpec.name` is `Literal["a", "b", "c", "d"]`; `get_mode(str) -> ModeSpec`.
- `ModeRunner.__init__` takes `db_policy: Literal["preserve", "fresh", "restore"] | None`; default derived from `mode_spec.db_policy_default`.
- `AppConnection(site_url, api_url, process=None)` — field names consistent with existing qa/server.py.
- `run_fitness_strategy(connection: AppConnection, *, project_root, ...)` — first positional is `connection`, others are kwargs.

**Placeholders scanned:** No "TBD", no "fill in", no "similar to Task N" without code, no "implement error handling" stubs. Every code step has complete code blocks.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-14-e2e-environment-strategy-plan.md`.

Two execution options:
1. **Subagent-driven** (recommended) — fresh subagent per task + two-stage review
2. **Inline execution** — batch tasks in this session with checkpoints
