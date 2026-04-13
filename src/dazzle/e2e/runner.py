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
from datetime import UTC, datetime
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
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _tail_log(log_path: Path | None, n: int = LOG_TAIL_LINES) -> list[str]:
    if log_path is None or not log_path.exists():
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
                raise ModeLaunchError(f"subprocess.Popen failed: {e}") from e

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
            ready = await wait_for_ready(conn.api_url, timeout=HEALTH_CHECK_BUDGET_SECONDS)
            if not ready:
                raise HealthCheckTimeoutError(
                    f"{conn.api_url}/docs did not return 200 within {HEALTH_CHECK_BUDGET_SECONDS}s"
                )

            return conn
        except BaseException:
            # Enter failed — teardown, release lock, reraise.
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
                raise RunnerTeardownError(str(teardown_exc)) from teardown_exc
        # Returning None means any caller exception propagates.

    # Helpers ----------------------------------------------------------------

    def _apply_db_policy(self) -> None:
        if self.db_policy == "preserve" and not self.fresh:
            return

        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            if self.db_policy == "restore":
                raise ModeLaunchError(
                    "DATABASE_URL must be set for db_policy=restore. "
                    "Export it or set it in .env before launching."
                )
            return

        if self.db_policy == "fresh" or self.fresh:
            mgr = BaselineManager(self.project_root, db_url)
            subprocess.run(
                [sys.executable, "-m", "dazzle", "db", "reset", "--yes"],
                cwd=self.project_root,
                check=True,
            )
            subprocess.run(
                [sys.executable, "-m", "dazzle", "db", "upgrade"],
                cwd=self.project_root,
                check=True,
            )
            if mgr._has_demo_config():
                subprocess.run(
                    [sys.executable, "-m", "dazzle", "demo", "generate"],
                    cwd=self.project_root,
                    check=True,
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
        loop = asyncio.get_event_loop()
        deadline = loop.time() + RUNTIME_POLL_BUDGET_SECONDS
        while loop.time() < deadline:
            if path.exists():
                try:
                    return json.loads(path.read_text())
                except (OSError, json.JSONDecodeError):
                    pass
            await asyncio.sleep(RUNTIME_POLL_INTERVAL_SECONDS)

        tail = _tail_log(self._log_path)
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
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)

        try:
            self._prev_sigint = signal.signal(signal.SIGINT, handler)
            self._prev_sigterm = signal.signal(signal.SIGTERM, handler)
        except ValueError:
            # signal.signal only works in the main thread; tests may not be
            # in the main thread. Skip.
            pass

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

            # For fake Popens that don't propagate signals, mark terminated
            if self._proc is not None and hasattr(self._proc, "terminated"):
                try:
                    self._proc.terminate()
                except Exception:
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
