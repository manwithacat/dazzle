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

    def fake_runner(
        *,
        run_id: str,
        db_path: Path,
        urls: tuple[str, ...],
        duration: int,
        login: str | None,
        cookies: tuple[str, ...],
    ) -> None:
        captured["run_id"] = run_id
        captured["db_path"] = db_path
        captured["urls"] = urls
        captured["duration"] = duration
        captured["login"] = login
        captured["cookies"] = cookies

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
    assert captured["login"] is None
    assert captured["cookies"] == ()


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


def test_trace_login_option_threaded_through(cwd: Path) -> None:
    """--login should reach the trace runner as a string."""
    captured: dict[str, object] = {}

    def fake_runner(
        *,
        run_id: str,
        db_path: Path,
        urls: tuple[str, ...],
        duration: int,
        login: str | None,
        cookies: tuple[str, ...],
    ) -> None:
        captured["login"] = login
        captured["cookies"] = cookies

    with patch("dazzle.cli.perf_impl.trace._execute_trace_run", side_effect=fake_runner):
        result = CliRunner().invoke(
            app,
            ["perf", "trace", "--url", "/", "--login", "u@example.com:hunter2"],
        )
    assert result.exit_code == 0
    assert captured["login"] == "u@example.com:hunter2"
    assert captured["cookies"] == ()


def test_trace_cookie_option_repeatable(cwd: Path) -> None:
    captured: dict[str, object] = {}

    def fake_runner(
        *,
        run_id: str,
        db_path: Path,
        urls: tuple[str, ...],
        duration: int,
        login: str | None,
        cookies: tuple[str, ...],
    ) -> None:
        captured["cookies"] = cookies

    with patch("dazzle.cli.perf_impl.trace._execute_trace_run", side_effect=fake_runner):
        result = CliRunner().invoke(
            app,
            [
                "perf",
                "trace",
                "--url",
                "/",
                "--cookie",
                "a=1",
                "--cookie",
                "b=2",
            ],
        )
    assert result.exit_code == 0
    assert captured["cookies"] == ("a=1", "b=2")


def test_trace_login_malformed_rejected(cwd: Path) -> None:
    result = CliRunner().invoke(app, ["perf", "trace", "--url", "/", "--login", "no-colon-here"])
    assert result.exit_code != 0
    combined = (result.stdout or "") + (result.stderr or "")
    assert "login" in combined.lower()


def test_traceable_page_urls_filters_to_getable_pages() -> None:
    """--all-surfaces keeps GET-able workspace/surface pages, drops
    parameterised detail routes and framework plumbing."""
    from types import SimpleNamespace

    from dazzle.cli.perf_impl.trace import _traceable_page_urls

    entries = [
        SimpleNamespace(name="/command_center/alerts", detail="workspace  GET POST"),
        SimpleNamespace(name="/alerts", detail="surface  GET"),
        SimpleNamespace(name="/alerts/{id}", detail="surface  GET"),  # param — dropped
        SimpleNamespace(name="/alerts", detail="surface  POST"),  # no GET — dropped
        SimpleNamespace(name="/api/workspaces/x", detail="api  GET"),  # api — dropped
        SimpleNamespace(name="/docs", detail="docs  GET"),  # docs — dropped
    ]
    assert _traceable_page_urls(entries) == ["/alerts", "/command_center/alerts"]


def test_trace_all_surfaces_merges_derived_urls(cwd: Path) -> None:
    """--all-surfaces folds discovered page routes into the trace URL set."""
    captured: dict[str, object] = {}

    def fake_runner(*, urls: tuple[str, ...], **_: object) -> None:
        captured["urls"] = urls

    with (
        patch("dazzle.cli.perf_impl.trace._execute_trace_run", side_effect=fake_runner),
        patch(
            "dazzle.cli.perf_impl.trace._derive_surface_urls",
            return_value=["/alerts", "/systems"],
        ),
    ):
        result = CliRunner().invoke(app, ["perf", "trace", "--url", "/", "--all-surfaces"])
    assert result.exit_code == 0
    assert captured["urls"] == ("/", "/alerts", "/systems")


def test_trace_all_surfaces_alone_is_valid(cwd: Path) -> None:
    """--all-surfaces needs no --url/--duration when routes are discovered."""
    with (
        patch("dazzle.cli.perf_impl.trace._execute_trace_run", side_effect=lambda **_: None),
        patch("dazzle.cli.perf_impl.trace._derive_surface_urls", return_value=["/alerts"]),
    ):
        result = CliRunner().invoke(app, ["perf", "trace", "--all-surfaces"])
    assert result.exit_code == 0


def test_trace_all_surfaces_empty_still_requires_url_or_duration(cwd: Path) -> None:
    """--all-surfaces that discovers nothing falls back to the usual guard."""
    with patch("dazzle.cli.perf_impl.trace._derive_surface_urls", return_value=[]):
        result = CliRunner().invoke(app, ["perf", "trace", "--all-surfaces"])
    assert result.exit_code != 0
    combined = (result.stdout or "") + (result.stderr or "")
    assert "url" in combined.lower() or "duration" in combined.lower()


def test_parse_set_cookie_value() -> None:
    from dazzle.cli.perf_impl.trace import _parse_set_cookie_value

    assert _parse_set_cookie_value("dazzle_session=abc123; HttpOnly", "dazzle_session") == "abc123"
    assert (
        _parse_set_cookie_value(
            "other=foo; Path=/, dazzle_session=xyz; HttpOnly",
            "dazzle_session",
        )
        == "xyz"
    )
    assert _parse_set_cookie_value("", "dazzle_session") is None
    assert _parse_set_cookie_value("other=foo", "dazzle_session") is None
