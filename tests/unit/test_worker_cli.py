"""Tests for #953 cycle 9 — `dazzle worker` CLI.

The CLI command itself is a thin shim (load AppSpec → pick queue →
wire signals → run loops). We test the testable units rather than
spinning up the full subprocess:

  * `_build_queue` — Redis vs in-memory selection per `REDIS_URL`
  * Typer registration — command appears in the CLI app

End-to-end CLI invocation testing happens in the existing CLI
integration suite (also gated on REDIS_URL).
"""

from __future__ import annotations

import os
from unittest.mock import patch

from dazzle.cli.worker import _build_queue, worker_app

# ---------------------------------------------------------------------------
# Queue selection
# ---------------------------------------------------------------------------


class TestBuildQueue:
    def test_in_memory_when_no_redis_url(self):
        from dazzle_back.runtime.job_queue import InMemoryJobQueue

        with patch.dict(os.environ, {}, clear=True):
            queue, label = _build_queue(redis_key="test:key")
        assert isinstance(queue, InMemoryJobQueue)
        assert "in-memory" in label

    def test_redis_when_url_set(self):
        from dazzle_back.runtime.redis_job_queue import RedisJobQueue

        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"}):
            queue, label = _build_queue(redis_key="staging:jobs")
        assert isinstance(queue, RedisJobQueue)
        assert "Redis" in label
        assert "staging:jobs" in label

    def test_label_in_memory_mentions_redis_url_hint(self):
        # Operator running in dev should see a hint that they can
        # set REDIS_URL for persistence.
        with patch.dict(os.environ, {}, clear=True):
            _, label = _build_queue(redis_key="x")
        assert "REDIS_URL" in label

    def test_empty_redis_url_treated_as_unset(self):
        # `REDIS_URL=""` (rather than unset) should fall back to
        # in-memory rather than try to connect to nothing.
        from dazzle_back.runtime.job_queue import InMemoryJobQueue

        with patch.dict(os.environ, {"REDIS_URL": ""}):
            queue, _ = _build_queue(redis_key="x")
        assert isinstance(queue, InMemoryJobQueue)


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------


class TestCliRegistration:
    def test_worker_command_registered(self):
        # The worker_app should be importable + have callbacks.
        # `worker_app.registered_callback` is the typer-typer "main"
        # — checking it exists confirms the @worker_app.callback
        # decorator was applied.
        assert worker_app.registered_callback is not None

    def test_worker_command_has_help_text(self):
        assert worker_app.info.help
        assert "worker" in worker_app.info.help.lower()

    def test_main_app_includes_worker(self):
        # Walk the main typer's subcommands — `worker` must be one.
        from dazzle.cli import app as main_app

        registered_names = {grp.name for grp in main_app.registered_groups}
        assert "worker" in registered_names


# ---------------------------------------------------------------------------
# Defensive: empty appspec.jobs — `run` exits early
# ---------------------------------------------------------------------------


class TestNoJobsExitsEarly:
    def test_no_jobs_returns_zero(self, tmp_path, monkeypatch):
        # Patch load_project_appspec to return a minimal AppSpec
        # with no jobs; the run command should exit before
        # calling _run_worker (which would block).
        class _StubAppSpec:
            jobs = []

        from dazzle.cli import worker as worker_module

        monkeypatch.setattr(worker_module, "load_project_appspec", lambda _path: _StubAppSpec())

        # Use Typer's CliRunner-equivalent for direct call.
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(worker_app, ["--project", str(tmp_path)])
        assert result.exit_code == 0
        # Output mentions the no-op condition.
        assert "nothing to do" in result.stdout.lower()
