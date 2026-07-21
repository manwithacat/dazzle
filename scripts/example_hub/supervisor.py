"""Spawn and track per-example ``dazzle serve`` processes."""

from __future__ import annotations

import logging
import os
import signal
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from registry import ExampleApp, repo_root

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

    def is_running(self, app: ExampleApp) -> bool:
        if app.name in self._procs:
            proc = self._procs[app.name]
            if proc.poll() is None:
                return True
            del self._procs[app.name]
        if self.is_port_open(app.port):
            return True
        pid_file = self.pid_path(app.name)
        if pid_file.is_file():
            try:
                pid = int(pid_file.read_text(encoding="utf-8").strip())
                os.kill(pid, 0)
                return True
            except (OSError, ValueError):
                pid_file.unlink(missing_ok=True)
        return False

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
        if self.is_running(app):
            return self.status(app)

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
