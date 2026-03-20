"""Tests for the test_intelligence 'journey' MCP operation."""

from __future__ import annotations

import json
from pathlib import Path


def _get_handler():
    """Import handler lazily to avoid pytest collecting it as a test."""
    from dazzle.mcp.server.handlers.test_intelligence import test_journey_handler

    return test_journey_handler


def test_journey_handler_returns_analysis(tmp_path: Path) -> None:
    """Returns content of the most recent analysis.json."""
    sessions_dir = tmp_path / ".dazzle" / "test_sessions" / "2026-03-20"
    sessions_dir.mkdir(parents=True)
    analysis = {"run_id": "2026-03-20", "personas_analysed": 3}
    (sessions_dir / "analysis.json").write_text(json.dumps(analysis))

    handler = _get_handler()
    result = json.loads(handler(tmp_path, {}))
    assert result["run_id"] == "2026-03-20"
    assert result["personas_analysed"] == 3


def test_journey_handler_returns_most_recent(tmp_path: Path) -> None:
    """When multiple sessions exist, returns the latest (sorted by name)."""
    for date in ("2026-03-18", "2026-03-19", "2026-03-20"):
        d = tmp_path / ".dazzle" / "test_sessions" / date
        d.mkdir(parents=True)
        (d / "analysis.json").write_text(json.dumps({"run_id": date}))

    handler = _get_handler()
    result = json.loads(handler(tmp_path, {}))
    assert result["run_id"] == "2026-03-20"


def test_journey_handler_no_sessions_dir(tmp_path: Path) -> None:
    """Returns error when .dazzle/test_sessions does not exist."""
    handler = _get_handler()
    result = json.loads(handler(tmp_path, {}))
    assert "error" in result
    assert "No journey sessions found" in result["error"]


def test_journey_handler_empty_sessions_dir(tmp_path: Path) -> None:
    """Returns error when sessions directory exists but has no analysis files."""
    sessions_dir = tmp_path / ".dazzle" / "test_sessions"
    sessions_dir.mkdir(parents=True)

    handler = _get_handler()
    result = json.loads(handler(tmp_path, {}))
    assert "error" in result
    assert "No journey sessions found" in result["error"]
