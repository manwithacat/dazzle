"""A project switch must not expose the previous project's graph."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dazzle.mcp.server import _execute_tool
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
