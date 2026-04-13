"""Unit tests for ModeRunner async context manager."""

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


@pytest.fixture(autouse=True)
def _disable_killpg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent runner from sending real signals to fake PIDs."""
    monkeypatch.setattr("dazzle.e2e.runner.os.killpg", lambda pid, sig: None, raising=False)
    monkeypatch.setattr("dazzle.e2e.runner.os.getpgid", lambda pid: pid, raising=False)


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
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Ensure parent env doesn't leak DAZZLE_QA_MODE into the test
        monkeypatch.delenv("DAZZLE_QA_MODE", raising=False)
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
        assert env.get("DAZZLE_QA_MODE") != "1"


@pytest.mark.asyncio
class TestModeRunnerFailurePaths:
    async def test_raises_when_alive_pid_holds_lock(self, project_root: Path) -> None:
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
        with patch("dazzle.e2e.lifecycle._iso_now_seconds_ago", return_value=10):
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

        assert fake_popen[0].terminated
        assert not (project_root / ".dazzle" / "mode_a.lock").exists()

    async def test_raises_health_check_timeout(
        self,
        project_root: Path,
        fake_popen: list[_FakePopen],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _write_runtime_file(project_root)
        monkeypatch.setattr("dazzle.e2e.runner.wait_for_ready", AsyncMock(return_value=False))

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

        assert fake_popen[0].terminated
        assert not (project_root / ".dazzle" / "mode_a.lock").exists()
