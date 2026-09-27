"""A project switch must not expose the previous project's graph."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dazzle.mcp.server import _execute_tool
from dazzle.mcp.server.handlers_consolidated import handle_graph
from dazzle.mcp.server.mcp_session import mcp_kg_db_path
from dazzle.mcp.server.state import get_state, reset_state


@pytest.mark.asyncio
async def test_project_tool_switches_graph_and_activity_store(tmp_path: Path) -> None:
    from dazzle.mcp.server.handlers import project as handler

    reset_state()
    state = get_state()
    state.is_dev_mode = True
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    for project in (project_a, project_b):
        project.mkdir()
        (project / "dazzle.toml").write_text("[project]\nname = 'test'\n")
    state.available_projects = {"a": project_a, "b": project_b}

    with (
        patch("dazzle.mcp.server.state.reinit_knowledge_graph") as reinit,
        patch("dazzle.mcp.server.state.init_activity_store") as activity,
        patch.object(handler, "load_appspec_for_project", return_value=True),
    ):
        for name, path in (("a", project_a), ("b", project_b)):
            result = json.loads(
                await _execute_tool("project", {"operation": "select", "project_name": name})
            )
            assert result["status"] == "selected"
            assert state.active_project == name
            reinit.assert_called_with(path)
            activity.assert_called_with(path)
    reset_state()


@pytest.mark.asyncio
async def test_failed_switch_clears_previous_project_state(tmp_path: Path) -> None:
    reset_state()
    state = get_state()
    state.is_dev_mode = True
    project = tmp_path / "other"
    project.mkdir()
    (project / "dazzle.toml").write_text("[project]\nname = 'other'\n")
    state.available_projects = {"other": project}
    state.active_project = "previous"
    state.knowledge_graph = MagicMock()
    state.appspec_data = {"name": "previous"}

    with patch("dazzle.mcp.server.state.reinit_knowledge_graph", side_effect=OSError("broken db")):
        result = json.loads(
            await _execute_tool("project", {"operation": "select", "project_name": "other"})
        )
    assert "Could not select project" in result["error"]
    assert state.active_project is None
    assert state.knowledge_graph is None
    assert state.appspec_data is None
    reset_state()


def test_graph_rejects_another_projects_database(tmp_path: Path) -> None:
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    graph = MagicMock()
    with (
        patch("dazzle.mcp.server.state.get_knowledge_graph", return_value=graph),
        patch("dazzle.mcp.server.state.get_graph_db_path", return_value=mcp_kg_db_path(project_a)),
    ):
        response = json.loads(
            handle_graph({"operation": "stats", "_resolved_project_path": project_b})
        )
    assert "different project" in response["error"]
    graph.get_stats.assert_not_called()
