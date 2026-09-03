"""Spawn and track per-example ``dazzle serve`` processes."""

from __future__ import annotations

import importlib.util
import logging
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


def _hub_registry():
    """Load sibling registry under a unique name.

    The HM gallery ``site/registry.py`` also binds as ``registry``.
    Pytest xdist workers that already imported that module fail
    ``from registry import ExampleApp`` (cycle 2378 CI red on py3.12/3.13).
    """
    name = "example_hub.registry"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    path = Path(__file__).resolve().parent / "registry.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load hub registry from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_reg = _hub_registry()
ExampleApp = _reg.ExampleApp
repo_root = _reg.repo_root

logger = logging.getLogger(__name__)


def state_dir(root: Path | None = None) -> Path:
    d = (root or repo_root()) / ".dazzle" / "eval-hub"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class ProcState:
    app: str
    port: int
    pid: int | None = None
    log_path: Path | None = None
    started_at: float | None = None


@dataclass
class Supervisor:
    """Manage long-lived dazzle serve children."""

    root: Path = field(default_factory=repo_root)
    dazzle_bin: str = "dazzle"
    test_mode: bool = True
    start_timeout: float = 45.0
    _procs: dict[str, subprocess.Popen[bytes]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._state = state_dir(self.root)
        # Prefer monorepo venv dazzle
        venv_dz = self.root / ".venv" / "bin" / "dazzle"
        if venv_dz.is_file():
            self.dazzle_bin = str(venv_dz)

    def pid_path(self, app: str) -> Path:
        return self._state / f"{app}.pid"

    def log_path(self, app: str) -> Path:
        return self._state / f"{app}.log"

    def is_port_open(self, port: int, host: str = "127.0.0.1") -> bool:
        try:
            with socket.create_connection((host, port), timeout=0.4):
                return True
        except OSError:
            return False

    def _read_pidfile(self, app: str) -> int | None:
        path = self.pid_path(app)
        if not path.is_file():
            return None
        try:
            pid = int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
        return pid if pid > 0 else None

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _listener_pid(self, port: int) -> int | None:
        """PID listening on ``port``, or None if unknown."""
        try:
            out = subprocess.check_output(
                ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                text=True,
                timeout=2,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        for line in out.splitlines():
            line = line.strip()
            if line.isdigit():
                return int(line)
        return None

    @staticmethod
    def _cmdline(pid: int) -> str:
        try:
            out = subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "command="],
                text=True,
                timeout=2,
                stderr=subprocess.DEVNULL,
            )
            return out.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    def is_ours(self, app: ExampleApp) -> bool:
        """True only when this supervisor's pidfile process still owns the port.

        A listening port alone is not enough: leftover ``dazzle serve`` from
        another week (cycle 2377: 13-day hr_records/fieldtest_hub) 500'd HTML
        403s and auto-seeded false product bugs.
        """
        if app.name in self._procs:
            proc = self._procs[app.name]
            if proc.poll() is None:
                return True
            del self._procs[app.name]
        pid = self._read_pidfile(app.name)
        if pid is None or not self._pid_alive(pid):
            return False
        listener = self._listener_pid(app.port)
        if listener is not None and listener != pid:
            return False
        return True

    def is_running(self, app: ExampleApp) -> bool:
        if self.is_ours(app):
            return True
        pid_file = self.pid_path(app.name)
        pid = self._read_pidfile(app.name)
        if pid is not None and not self._pid_alive(pid):
            pid_file.unlink(missing_ok=True)
        return False

    def _reap_stale(self, app: ExampleApp) -> None:
        """SIGTERM a leftover ``dazzle serve`` occupying ``app.port``."""
        listener = self._listener_pid(app.port)
        if listener is None:
            self.pid_path(app.name).unlink(missing_ok=True)
            return
        cmd = self._cmdline(listener)
        if "dazzle" in cmd and "serve" in cmd and str(app.port) in cmd:
            logger.warning(
                "reaping stale %s listener pid=%s cmd=%s",
                app.name,
                listener,
                cmd[:160],
            )
            try:
                os.kill(listener, signal.SIGTERM)
            except OSError:
                logger.debug("reap kill failed", exc_info=True)
            deadline = time.time() + 5.0
            while time.time() < deadline and self.is_port_open(app.port):
                time.sleep(0.1)
        self.pid_path(app.name).unlink(missing_ok=True)

    def status(self, app: ExampleApp) -> ProcState:
        running = self.is_running(app)
        pid = None
        if app.name in self._procs and self._procs[app.name].poll() is None:
            pid = self._procs[app.name].pid
        elif self.pid_path(app.name).is_file():
            try:
                pid = int(self.pid_path(app.name).read_text(encoding="utf-8").strip())
            except ValueError:
                pid = None
        return ProcState(
            app=app.name,
            port=app.port,
            pid=pid if running else None,
            log_path=self.log_path(app.name) if running else None,
            started_at=None,
        )

    def start(self, app: ExampleApp, *, wait: bool = True) -> ProcState:
        if self.is_ours(app):
            return self.status(app)
        if self.is_port_open(app.port):
            self._reap_stale(app)

        log = self.log_path(app.name)
        cmd = [
            self.dazzle_bin,
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(app.port),
        ]
        if self.test_mode:
            cmd.append("--test-mode")

        log_fh = log.open("ab")
        env = os.environ.copy()
        env.setdefault("DAZZLE_ENV", "development")
        # Magic-link / smoke dig require QA mode on the child serve process.
        # ``--test-mode`` alone does not inherit DAZZLE_QA_MODE from a hub that
        # never set it — arm it here so fleet digs work after hub restart.
        if self.test_mode:
            env["DAZZLE_QA_MODE"] = "1"
            env.setdefault("DAZZLE_ENV", "development")
        logger.info("starting %s: %s", app.name, " ".join(cmd))
        proc = subprocess.Popen(
            cmd,
            cwd=str(app.path),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        self._procs[app.name] = proc
        self.pid_path(app.name).write_text(str(proc.pid), encoding="utf-8")

        if wait:
            deadline = time.time() + self.start_timeout
            while time.time() < deadline:
                if proc.poll() is not None:
                    logger.error("%s exited early code=%s — see %s", app.name, proc.returncode, log)
                    break
                if self.is_port_open(app.port):
                    break
                time.sleep(0.25)
        return self.status(app)

    def stop(self, app: ExampleApp) -> None:
        pid = None
        if app.name in self._procs:
            proc = self._procs.pop(app.name)
            pid = proc.pid
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                try:
                    proc.terminate()
                except OSError:
                    logger.debug("terminate failed", exc_info=True)
        if self.pid_path(app.name).is_file():
            try:
                pid = pid or int(self.pid_path(app.name).read_text(encoding="utf-8").strip())
            except ValueError:
                pid = None
            self.pid_path(app.name).unlink(missing_ok=True)
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                logger.debug("kill %s failed", pid, exc_info=True)

    def stop_all(self, apps: list[ExampleApp]) -> None:
        for a in apps:
            self.stop(a)

    def start_all(self, apps: list[ExampleApp]) -> list[ProcState]:
        return [self.start(a, wait=True) for a in apps]
