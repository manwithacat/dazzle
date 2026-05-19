"""``dazzle perf trace`` runs uvicorn in a subprocess; the unit test
exercises the pre-launch wiring (env var, db path planning) without
actually booting the server."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from dazzle.cli import app


@pytest.fixture
def cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dazzle.toml").write_text("[project]\nname='t'\n")
    return tmp_path


def test_trace_plans_run_db_and_sets_env(cwd: Path) -> None:
    captured: dict[str, object] = {}

    def fake_runner(*, run_id: str, db_path: Path, urls: tuple[str, ...], duration: int) -> None:
        captured["run_id"] = run_id
        captured["db_path"] = db_path
        captured["urls"] = urls
        captured["duration"] = duration

    with patch("dazzle.cli.perf_impl.trace._execute_trace_run", side_effect=fake_runner):
        result = CliRunner().invoke(
            app,
            ["perf", "trace", "--url", "/tasks", "--duration", "3"],
        )
    assert result.exit_code == 0
    assert captured["urls"] == ("/tasks",)
    assert captured["duration"] == 3
    assert isinstance(captured["db_path"], Path)
    assert captured["db_path"].parent.name == "perf"


def test_trace_creates_perf_dir(cwd: Path) -> None:
    with patch(
        "dazzle.cli.perf_impl.trace._execute_trace_run",
        side_effect=lambda **kwargs: None,
    ):
        CliRunner().invoke(app, ["perf", "trace", "--url", "/tasks", "--duration", "1"])
    assert (cwd / ".dazzle" / "perf").is_dir()


def test_trace_requires_url_or_duration(cwd: Path) -> None:
    result = CliRunner().invoke(app, ["perf", "trace"])
    assert result.exit_code != 0
    # Error message should mention --url or --duration
    combined = (result.stdout or "") + (result.stderr or "")
    assert "url" in combined.lower() or "duration" in combined.lower()
