"""Tests for the agent_commands MCP handler."""

import json
from pathlib import Path
from unittest.mock import patch

from dazzle.mcp.server.handlers.agent_commands import handle_check_updates, handle_get, handle_list


def _mock_ctx(**overrides: object) -> dict[str, object]:
    ctx: dict[str, object] = {
        "entity_count": 3,
        "surface_count": 5,
        "story_count": 2,
        "has_spec_md": True,
        "has_github_remote": True,
        "validate_passes": True,
        "app_running": False,
        "entity_names": ["Task", "User", "Comment"],
        "persona_names": ["admin", "user"],
        "surface_names": ["task_list", "task_detail", "user_list", "user_detail", "comment_list"],
        "project_name": "test_app",
    }
    ctx.update(overrides)
    return ctx


def test_list_returns_all_commands() -> None:
    with patch(
        "dazzle.mcp.server.handlers.agent_commands.build_project_context",
        return_value=_mock_ctx(),
    ):
        result = handle_list(Path("/fake"), {})
    data = json.loads(result)
    assert "commands" in data
    names = [c["name"] for c in data["commands"]]
    assert "improve" in names
    assert "qa" in names


def test_list_shows_availability() -> None:
    with patch(
        "dazzle.mcp.server.handlers.agent_commands.build_project_context",
        return_value=_mock_ctx(surface_count=1),
    ):
        result = handle_list(Path("/fake"), {})
    data = json.loads(result)
    polish = next(c for c in data["commands"] if c["name"] == "polish")
    assert polish["available"] is False
    assert "surfaces" in polish["reason"].lower()


def test_get_returns_rendered_skill() -> None:
    with patch(
        "dazzle.mcp.server.handlers.agent_commands.build_project_context",
        return_value=_mock_ctx(),
    ):
        result = handle_get(Path("/fake"), {"command": "improve"})
    data = json.loads(result)
    assert "content" in data
    assert "Autonomous Improvement Loop" in data["content"]


def test_get_unknown_command() -> None:
    with patch(
        "dazzle.mcp.server.handlers.agent_commands.build_project_context",
        return_value=_mock_ctx(),
    ):
        result = handle_get(Path("/fake"), {"command": "nonexistent"})
    data = json.loads(result)
    assert "error" in data


def test_check_updates_current() -> None:
    result = handle_check_updates(Path("/fake"), {"commands_version": "1.0.0"})
    data = json.loads(result)
    assert data["up_to_date"] is True


def test_check_updates_stale() -> None:
    result = handle_check_updates(Path("/fake"), {"commands_version": "0.1.0"})
    data = json.loads(result)
    assert data["up_to_date"] is False
    assert "commands_version" in data
