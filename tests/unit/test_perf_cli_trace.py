"""``dazzle perf trace`` runs uvicorn in a subprocess; these tests exercise
the pre-launch wiring (option parsing, db path planning, route discovery)
with the trace runner replaced by a recorder, so no server boots."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from dazzle.cli.perf_impl.trace import (
    _parse_set_cookie_value,
    _stamp_run_ended,
    _traceable_page_urls,
)
from tests.unit.helpers.cli import run_cli

_RUNNER = "dazzle.cli.perf_impl.trace._execute_trace_run"
_DERIVE = "dazzle.cli.perf_impl.trace._derive_surface_urls"


@pytest.fixture
def cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dazzle.toml").write_text("[project]\nname='t'\n")
    return tmp_path


@pytest.fixture
def trace_run(cwd: Path) -> Iterator[dict[str, Any]]:
    """Replace the trace runner with a recorder; yields the kwargs it received."""
    captured: dict[str, Any] = {}
    with patch(_RUNNER, side_effect=lambda **kwargs: captured.update(kwargs)):
        yield captured


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        pytest.param(
            ["--url", "/tasks", "--duration", "3"],
            {"urls": ("/tasks",), "duration": 3, "login": None, "cookies": ()},
            id="url_and_duration",
        ),
        pytest.param(
            ["--url", "/", "--login", "u@example.com:hunter2"],
            {"login": "u@example.com:hunter2", "cookies": ()},
            id="login_threaded_as_string",
        ),
        pytest.param(
            ["--url", "/", "--cookie", "a=1", "--cookie", "b=2"],
            {"cookies": ("a=1", "b=2")},
            id="cookie_repeatable",
        ),
    ],
)
def test_trace_options_reach_the_runner(
    trace_run: dict[str, Any], args: list[str], expected: dict[str, Any]
) -> None:
    run_cli(["perf", "trace", *args])
    assert {k: trace_run[k] for k in expected} == expected


def test_trace_plans_run_db_under_perf_dir(cwd: Path, trace_run: dict[str, Any]) -> None:
    run_cli(["perf", "trace", "--url", "/tasks", "--duration", "1"])
    assert trace_run["db_path"].parent == cwd / ".dazzle" / "perf"
    assert trace_run["db_path"].parent.is_dir()


@pytest.mark.parametrize(
    ("args", "derived", "expected_urls"),
    [
        pytest.param(
            ["--url", "/", "--all-surfaces"],
            ["/alerts", "/systems"],
            ("/", "/alerts", "/systems"),
            id="merged_with_explicit_url",
        ),
        pytest.param(["--all-surfaces"], ["/alerts"], ("/alerts",), id="alone_is_valid"),
    ],
)
def test_trace_all_surfaces_folds_in_discovered_routes(
    trace_run: dict[str, Any], args: list[str], derived: list[str], expected_urls: tuple[str, ...]
) -> None:
    with patch(_DERIVE, return_value=derived):
        run_cli(["perf", "trace", *args])
    assert trace_run["urls"] == expected_urls


@pytest.mark.parametrize(
    ("args", "message"),
    [
        pytest.param([], "Provide at least one --url", id="no_url_or_duration"),
        pytest.param(
            ["--all-surfaces"], "Provide at least one --url", id="all_surfaces_found_none"
        ),
        pytest.param(
            ["--url", "/", "--login", "no-colon-here"], "EMAIL:PASSWORD", id="login_without_colon"
        ),
        pytest.param(
            ["--url", "/", "--cookie", "novalue"], "NAME=VALUE", id="cookie_without_equals"
        ),
    ],
)
def test_trace_rejects_unusable_invocation(cwd: Path, args: list[str], message: str) -> None:
    with patch(_RUNNER) as runner, patch(_DERIVE, return_value=[]):
        out = run_cli(["perf", "trace", *args], exit_code=1)
    assert message in out
    runner.assert_not_called()


def test_traceable_page_urls_filters_to_getable_pages() -> None:
    """--all-surfaces keeps GET-able workspace/surface pages, drops
    parameterised detail routes and framework plumbing."""
    entries = [
        SimpleNamespace(name="/command_center/alerts", detail="workspace  GET POST"),
        SimpleNamespace(name="/alerts", detail="surface  GET"),
        SimpleNamespace(name="/alerts/{id}", detail="surface  GET"),  # param — dropped
        SimpleNamespace(name="/alerts", detail="surface  POST"),  # no GET — dropped
        SimpleNamespace(name="/api/workspaces/x", detail="api  GET"),  # api — dropped
        SimpleNamespace(name="/docs", detail="docs  GET"),  # docs — dropped
    ]
    assert _traceable_page_urls(entries) == ["/alerts", "/command_center/alerts"]  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("ended_at", "stamped"),
    [
        pytest.param(None, lambda v: v is not None, id="sigtermed_run_gets_ended_at"),
        pytest.param("ORIGINAL", lambda v: v == "ORIGINAL", id="clean_shutdown_not_overwritten"),
    ],
)
def test_stamp_run_ended(tmp_path: Path, ended_at: str | None, stamped: Any) -> None:
    """The traced server is SIGTERM'd, so the exporter's own shutdown write
    never fires; the runner stamps runs.ended_at unless it is already set."""
    db = tmp_path / "run.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE runs (run_id TEXT, started_at TEXT, ended_at TEXT)")
    conn.execute("INSERT INTO runs VALUES ('r1', '2026-01-01T00:00:00Z', ?)", (ended_at,))
    conn.commit()
    conn.close()

    _stamp_run_ended(db, "r1")

    row = sqlite3.connect(db).execute("SELECT ended_at FROM runs WHERE run_id = 'r1'").fetchone()
    assert stamped(row[0]), row


def test_stamp_run_ended_missing_db_is_silent(tmp_path: Path) -> None:
    """No DB file (server never booted) — stamping is a quiet no-op."""
    _stamp_run_ended(tmp_path / "absent.db", "r1")  # must not raise
    assert not (tmp_path / "absent.db").exists()


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        pytest.param("dazzle_session=abc123; HttpOnly", "abc123", id="single_cookie"),
        pytest.param(
            "other=foo; Path=/, dazzle_session=xyz; HttpOnly", "xyz", id="second_of_two_cookies"
        ),
        pytest.param("", None, id="empty_header"),
        pytest.param("other=foo", None, id="cookie_absent"),
    ],
)
def test_parse_set_cookie_value(header: str, expected: str | None) -> None:
    assert _parse_set_cookie_value(header, "dazzle_session") == expected
