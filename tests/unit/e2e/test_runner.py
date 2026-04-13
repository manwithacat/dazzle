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


def _make_fake_popen_factory(
    instances: list[MagicMock],
    *,
    project_root: Path | None = None,
    write_runtime_on_start: bool = True,
) -> Any:
    """Build a subprocess.Popen replacement for ModeRunner tests.

    When ``write_runtime_on_start`` is True (default), the factory writes
    a valid ``.dazzle/runtime.json`` to ``project_root`` each time Popen is
    called — mirroring what a real ``dazzle serve`` subprocess does shortly
    after startup. This matters because ``ModeRunner.__aenter__`` deletes
    any pre-existing runtime.json before launching (to avoid the stale-
    ports race from cycle 110), so tests that rely on the file being
    present have to regenerate it *after* Popen is called, not before.
    """

    def factory(*args: Any, **kwargs: Any) -> MagicMock:
        fake = MagicMock()
        fake.pid = 4242 + len(instances)
        fake.args_received = args
        fake.kwargs = kwargs
        state = {"terminated": False}

        def _poll() -> int | None:
            return 0 if state["terminated"] else None

        def _terminate() -> None:
            state["terminated"] = True

        def _kill() -> None:
            state["terminated"] = True

        def _wait(timeout: float | None = None) -> int:
            state["terminated"] = True
            return 0

        fake.poll.side_effect = _poll
        fake.terminate.side_effect = _terminate
        fake.kill.side_effect = _kill
        fake.wait.side_effect = _wait
        instances.append(fake)

        if write_runtime_on_start and project_root is not None:
            _write_runtime_file(project_root)

        return fake

    return factory


@pytest.fixture
def fake_popen(monkeypatch: pytest.MonkeyPatch, project_root: Path) -> list[MagicMock]:
    """Patch subprocess.Popen — each call writes a fresh runtime.json.

    Use this for tests that want the happy-path behavior (Popen started,
    runtime.json written, poll succeeds). Tests that want a timeout
    should use ``fake_popen_silent`` instead.
    """
    instances: list[MagicMock] = []
    factory = _make_fake_popen_factory(
        instances, project_root=project_root, write_runtime_on_start=True
    )
    monkeypatch.setattr("dazzle.e2e.runner.subprocess.Popen", factory)
    return instances


@pytest.fixture
def fake_popen_silent(monkeypatch: pytest.MonkeyPatch, project_root: Path) -> list[MagicMock]:
    """Patch subprocess.Popen without writing runtime.json.

    Use this for tests that need to trigger RuntimeFileTimeoutError.
    """
    instances: list[MagicMock] = []
    factory = _make_fake_popen_factory(
        instances, project_root=project_root, write_runtime_on_start=False
    )
    monkeypatch.setattr("dazzle.e2e.runner.subprocess.Popen", factory)
    return instances


@pytest.fixture
def fake_wait_for_ready(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr("dazzle.e2e.runner.wait_for_ready", mock)
    return mock


@pytest.fixture(autouse=True)
def killpg_recorder(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Record os.killpg pids — lets tests verify subprocess termination."""
    calls: list[int] = []

    def fake_killpg(pid: int, sig: int) -> None:
        calls.append(pid)

    monkeypatch.setattr("dazzle.e2e.runner.os.killpg", fake_killpg, raising=False)
    monkeypatch.setattr("dazzle.e2e.runner.os.getpgid", lambda pid: pid, raising=False)
    return calls


@pytest.mark.asyncio
class TestModeRunnerHappyPath:
    async def test_yields_app_connection(
        self,
        project_root: Path,
        fake_popen: list[MagicMock],
        fake_wait_for_ready: AsyncMock,
        killpg_recorder: list[int],
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

        # After teardown: lock released and killpg was called
        lock_path = project_root / ".dazzle" / "mode_a.lock"
        assert not lock_path.exists()
        assert killpg_recorder

    async def test_qa_flags_auto_set_when_personas_non_empty(
        self,
        project_root: Path,
        fake_popen: list[MagicMock],
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
        fake_popen: list[MagicMock],
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
        fake_popen_silent: list[MagicMock],
        fake_wait_for_ready: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        killpg_recorder: list[int],
    ) -> None:
        # fake_popen_silent does NOT write runtime.json — triggers timeout
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

        assert killpg_recorder
        assert not (project_root / ".dazzle" / "mode_a.lock").exists()

    async def test_raises_health_check_timeout(
        self,
        project_root: Path,
        fake_popen: list[MagicMock],
        monkeypatch: pytest.MonkeyPatch,
        killpg_recorder: list[int],
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

        assert killpg_recorder
        assert not (project_root / ".dazzle" / "mode_a.lock").exists()

    async def test_caller_exception_propagates_with_teardown(
        self,
        project_root: Path,
        fake_popen: list[MagicMock],
        fake_wait_for_ready: AsyncMock,
        killpg_recorder: list[int],
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

        assert killpg_recorder
        assert not (project_root / ".dazzle" / "mode_a.lock").exists()
