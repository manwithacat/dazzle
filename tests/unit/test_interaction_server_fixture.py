"""Unit tests for the INTERACTION_WALK server fixture.

The fixture spawns ``python -m dazzle serve --local`` as a subprocess.
Running a real server in unit tests is out of scope (it requires
Postgres + Redis); these tests patch ``subprocess.Popen`` and the
filesystem to exercise the lifecycle logic — "does it wait for
runtime.json?", "does it clean up on exit?", "does it raise a
distinguishable error on timeout?".
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dazzle.testing.ux.interactions.server_fixture import (
    InteractionServerError,
    launch_interaction_server,
)
from dazzle.testing.ux.interactions.server_fixture import (
    _wait_for_server_ready as _real_wait_for_server_ready,
)


@pytest.fixture
def fake_project(tmp_path: Path) -> Path:
    """Build a directory that looks like a Dazzle project root."""
    (tmp_path / "dazzle.toml").write_text("[app]\nname = 'test'\n")
    return tmp_path


@pytest.fixture(autouse=True)
def stub_server_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the real HTTP readiness probe in all tests by default.

    The fixture patches ``_wait_for_server_ready`` to a no-op so the
    existing tests (which don't actually bind a TCP port) don't hang
    polling a non-existent server. Tests that specifically cover the
    readiness-probe behaviour opt out by re-patching it inside their
    own scope.
    """
    monkeypatch.setattr(
        "dazzle.testing.ux.interactions.server_fixture._wait_for_server_ready",
        lambda *args, **kwargs: None,
    )


def _write_runtime_json(project_root: Path, ui_url: str, api_url: str) -> None:
    dazzle_dir = project_root / ".dazzle"
    dazzle_dir.mkdir(parents=True, exist_ok=True)
    (dazzle_dir / "runtime.json").write_text(json.dumps({"ui_url": ui_url, "api_url": api_url}))


class TestProjectValidation:
    def test_rejects_dir_without_dazzle_toml(self, tmp_path: Path) -> None:
        with pytest.raises(InteractionServerError, match="no dazzle.toml"):
            with launch_interaction_server(tmp_path):
                pass


class TestRuntimeFilePolling:
    def test_yields_connection_when_runtime_file_appears(
        self, fake_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Fake Popen: simulate the server writing runtime.json on
        # startup. A real `dazzle serve` writes the file from its
        # subprocess; we mirror that by writing from the side_effect.
        fake_proc = MagicMock(spec=subprocess.Popen)
        fake_proc.poll.return_value = None
        fake_proc.terminate = MagicMock()
        fake_proc.wait = MagicMock(return_value=0)

        def on_popen(*args: Any, **kwargs: Any) -> Any:
            _write_runtime_json(fake_project, "http://localhost:3001", "http://localhost:8001")
            return fake_proc

        with patch(
            "dazzle.testing.ux.interactions.server_fixture.subprocess.Popen",
            side_effect=on_popen,
        ):
            with launch_interaction_server(fake_project, timeout=5.0) as conn:
                assert conn.site_url == "http://localhost:3001"
                assert conn.api_url == "http://localhost:8001"
                assert conn.process is fake_proc

        # Teardown must terminate the subprocess.
        fake_proc.terminate.assert_called_once()

    def test_timeout_raises_interaction_server_error(self, fake_project: Path) -> None:
        # Don't write runtime.json; fake Popen that stays alive.
        fake_proc = MagicMock(spec=subprocess.Popen)
        fake_proc.poll.return_value = None
        fake_proc.terminate = MagicMock()
        fake_proc.wait = MagicMock(return_value=0)

        with (
            patch(
                "dazzle.testing.ux.interactions.server_fixture.subprocess.Popen",
                return_value=fake_proc,
            ),
            patch(
                "dazzle.testing.ux.interactions.server_fixture._RUNTIME_POLL_INTERVAL_SECONDS",
                0.01,
            ),
        ):
            with pytest.raises(InteractionServerError, match="did not write"):
                with launch_interaction_server(fake_project, timeout=0.1):
                    pass
        # Even on failure, the subprocess must be torn down.
        fake_proc.terminate.assert_called_once()

    def test_stale_runtime_file_is_cleared_before_launch(self, fake_project: Path) -> None:
        # Write a stale runtime.json pointing at an old run. The
        # fixture must unlink it before launching so the polling
        # doesn't mistake the stale URLs for the fresh run's URLs.
        _write_runtime_json(fake_project, "http://stale:9999", "http://stale:9998")
        # Build the fake Popen BEFORE entering the patch so
        # ``MagicMock(spec=subprocess.Popen)`` sees the real class.
        side_effect, _fake_proc = _make_fake_server_popen(
            fake_project,
            ui_url="http://localhost:3001",
            api_url="http://localhost:8001",
        )

        with patch(
            "dazzle.testing.ux.interactions.server_fixture.subprocess.Popen",
            side_effect=side_effect,
        ):
            with launch_interaction_server(fake_project, timeout=5.0) as conn:
                # If the stale file hadn't been cleared, we'd have seen
                # the stale URLs immediately. Instead the connection
                # reflects the newly-written file.
                assert "stale" not in conn.site_url
                assert conn.site_url == "http://localhost:3001"


def _make_fake_server_popen(
    project_root: Path,
    ui_url: str = "http://localhost:3001",
    api_url: str = "http://localhost:8001",
    poll_return: int | None = None,
) -> tuple[Any, Any]:
    """Build a (side_effect, fake_proc) pair for patching Popen.

    The side_effect writes runtime.json (simulating the real server)
    and returns a MagicMock whose poll() returns ``poll_return``.
    """
    fake_proc = MagicMock(spec=subprocess.Popen)
    fake_proc.poll.return_value = poll_return
    fake_proc.terminate = MagicMock()
    fake_proc.wait = MagicMock(return_value=0)

    def side_effect(*args: Any, **kwargs: Any) -> Any:
        _write_runtime_json(project_root, ui_url, api_url)
        return fake_proc

    return side_effect, fake_proc


class TestTeardown:
    def test_exception_inside_context_still_tears_down(self, fake_project: Path) -> None:
        side_effect, fake_proc = _make_fake_server_popen(fake_project)

        with patch(
            "dazzle.testing.ux.interactions.server_fixture.subprocess.Popen",
            side_effect=side_effect,
        ):
            with pytest.raises(RuntimeError, match="boom"):
                with launch_interaction_server(fake_project, timeout=5.0):
                    raise RuntimeError("boom")

        fake_proc.terminate.assert_called_once()

    def test_runtime_file_deleted_on_teardown(self, fake_project: Path) -> None:
        runtime_path = fake_project / ".dazzle" / "runtime.json"
        side_effect, fake_proc = _make_fake_server_popen(fake_project)

        with patch(
            "dazzle.testing.ux.interactions.server_fixture.subprocess.Popen",
            side_effect=side_effect,
        ):
            with launch_interaction_server(fake_project, timeout=5.0):
                # Mid-context the file exists (written by the side_effect).
                assert runtime_path.exists()

        # Teardown should have cleaned up the runtime file so the next
        # run can't mistakenly read stale URLs.
        assert not runtime_path.exists()

    def test_already_dead_process_does_not_block_teardown(self, fake_project: Path) -> None:
        # poll() returning 0 means the process exited on its own.
        side_effect, fake_proc = _make_fake_server_popen(fake_project, poll_return=0)

        with patch(
            "dazzle.testing.ux.interactions.server_fixture.subprocess.Popen",
            side_effect=side_effect,
        ):
            with launch_interaction_server(fake_project, timeout=5.0) as conn:
                assert conn is not None

        # Since the process had already exited, terminate() should NOT
        # be called — the guard on poll() covers this.
        fake_proc.terminate.assert_not_called()


class TestServerReadinessProbe:
    """Covers the health-check polling added to unblock the v0.57.52
    CI failure (Playwright hit ERR_CONNECTION_REFUSED because
    runtime.json was written before uvicorn bound its port).
    """

    def test_returns_when_http_responds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Opt out of the autouse stub so the real function runs.
        from dazzle.testing.ux.interactions import server_fixture as sf

        monkeypatch.setattr(
            "dazzle.testing.ux.interactions.server_fixture._wait_for_server_ready",
            _real_wait_for_server_ready,
        )

        fake_client = MagicMock()
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_client.__enter__ = MagicMock(return_value=fake_client)
        fake_client.__exit__ = MagicMock(return_value=False)
        fake_client.get = MagicMock(return_value=fake_response)

        with patch(
            "httpx.Client",
            return_value=fake_client,
        ):
            # Should return promptly, no exception.
            sf._wait_for_server_ready("http://localhost:9999", timeout=1.0)

    def test_raises_on_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from dazzle.testing.ux.interactions import server_fixture as sf

        monkeypatch.setattr(
            "dazzle.testing.ux.interactions.server_fixture._wait_for_server_ready",
            _real_wait_for_server_ready,
        )
        monkeypatch.setattr(
            "dazzle.testing.ux.interactions.server_fixture._HEALTH_POLL_INTERVAL_SECONDS",
            0.01,
        )

        fake_client = MagicMock()
        fake_client.__enter__ = MagicMock(return_value=fake_client)
        fake_client.__exit__ = MagicMock(return_value=False)
        fake_client.get = MagicMock(side_effect=ConnectionError("refused"))

        with patch("httpx.Client", return_value=fake_client):
            with pytest.raises(InteractionServerError, match="did not accept connections"):
                sf._wait_for_server_ready("http://localhost:9999", timeout=0.1)

    def test_4xx_counts_as_listening(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A 401/403/404 means the server is bound and answering —
        # Playwright can goto, even if the content redirects to login.
        from dazzle.testing.ux.interactions import server_fixture as sf

        monkeypatch.setattr(
            "dazzle.testing.ux.interactions.server_fixture._wait_for_server_ready",
            _real_wait_for_server_ready,
        )

        fake_client = MagicMock()
        fake_response = MagicMock()
        fake_response.status_code = 403
        fake_client.__enter__ = MagicMock(return_value=fake_client)
        fake_client.__exit__ = MagicMock(return_value=False)
        fake_client.get = MagicMock(return_value=fake_response)

        with patch("httpx.Client", return_value=fake_client):
            # Returns without exception.
            sf._wait_for_server_ready("http://localhost:9999", timeout=1.0)
