"""Tests for the Activity Explorer HTTP server."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path

import pytest


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Create a KG database with activity data for the explorer."""
    from dazzle.mcp.knowledge_graph import KnowledgeGraph

    db = tmp_path / ".dazzle" / "knowledge_graph.db"
    db.parent.mkdir(parents=True)
    graph = KnowledgeGraph(db)

    sid = graph.start_activity_session(
        project_name="test_project",
        project_path=str(tmp_path),
        version="1.0.0",
    )

    # Add some events
    graph.log_activity_event(sid, "tool_start", "dsl", "validate")
    graph.log_activity_event(
        sid,
        "tool_end",
        "dsl",
        "validate",
        success=True,
        duration_ms=42.0,
    )
    graph.log_activity_event(sid, "tool_start", "story", "propose")
    graph.log_activity_event(
        sid,
        "tool_end",
        "story",
        "propose",
        success=False,
        error="Entity not found",
        duration_ms=15.0,
    )

    # Also add a tool_invocation for the invocations endpoint
    graph.log_tool_invocation(
        tool_name="dsl",
        operation="validate",
        success=True,
        duration_ms=42.0,
    )

    return db


@pytest.fixture()
def explorer_server(db_path, tmp_path):
    """Start the explorer server on a random port in a background thread."""
    from http.server import HTTPServer

    from dazzle.mcp.server.explorer import _make_handler_class

    handler_class = _make_handler_class(db_path)
    server = HTTPServer(("127.0.0.1", 0), handler_class)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield port

    server.shutdown()


def _get(port: int, path: str) -> tuple[int, dict | list | str]:
    """Make a GET request and parse JSON response."""
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read().decode()
    status = resp.status
    conn.close()
    if resp.getheader("Content-Type", "").startswith("application/json"):
        return status, json.loads(body)
    return status, body


# ── HTML page ────────────────────────────────────────────────────────────────


class TestExplorerHtml:
    def test_root_serves_html(self, explorer_server):
        status, body = _get(explorer_server, "/")
        assert status == 200
        assert "Activity Explorer" in body


# ── Sessions API ─────────────────────────────────────────────────────────────


class TestSessionsApi:
    def test_list_sessions(self, explorer_server):
        status, data = _get(explorer_server, "/api/sessions")
        assert status == 200
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["project_name"] == "test_project"


# ── Events API ───────────────────────────────────────────────────────────────


class TestEventsApi:
    def test_list_all_events(self, explorer_server):
        status, data = _get(explorer_server, "/api/events?since_id=0")
        assert status == 200
        assert isinstance(data, list)
        assert len(data) == 4

    def test_events_with_session_filter(self, explorer_server):
        # First get the session ID
        _, sessions = _get(explorer_server, "/api/sessions")
        sid = sessions[0]["id"]

        status, data = _get(explorer_server, f"/api/events?session_id={sid}&since_id=0")
        assert status == 200
        assert len(data) == 4

    def test_events_pagination(self, explorer_server):
        status, data = _get(explorer_server, "/api/events?since_id=0&limit=2")
        assert status == 200
        assert len(data) == 2

        # Continue from cursor
        last_id = data[-1]["id"]
        status, more = _get(explorer_server, f"/api/events?since_id={last_id}&limit=10")
        assert status == 200
        assert len(more) == 2


# ── Stats API ────────────────────────────────────────────────────────────────


class TestStatsApi:
    def test_stats_all(self, explorer_server):
        status, data = _get(explorer_server, "/api/stats")
        assert status == 200
        assert data["total_events"] == 4
        assert data["tool_calls_ok"] == 1
        assert data["tool_calls_error"] == 1
        assert len(data["by_tool"]) == 2

    def test_stats_by_session(self, explorer_server):
        _, sessions = _get(explorer_server, "/api/sessions")
        sid = sessions[0]["id"]

        status, data = _get(explorer_server, f"/api/stats?session_id={sid}")
        assert status == 200
        assert data["tool_calls_ok"] == 1


# ── Invocations API ──────────────────────────────────────────────────────────


class TestInvocationsApi:
    def test_list_invocations(self, explorer_server):
        status, data = _get(explorer_server, "/api/invocations")
        assert status == 200
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_filter_by_tool(self, explorer_server):
        status, data = _get(explorer_server, "/api/invocations?tool=dsl")
        assert status == 200
        assert all(r["tool_name"] == "dsl" for r in data)


# ── 404 ──────────────────────────────────────────────────────────────────────


class TestNotFound:
    def test_unknown_path(self, explorer_server):
        status, _ = _get(explorer_server, "/unknown")
        assert status == 404
