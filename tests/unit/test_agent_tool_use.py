"""Tests for the DazzleAgent tool-use code path.

Covers:
- use_tool_calls kwarg on __init__ (3 tests)
- Three-way branch in _decide + MCP sampling warning latch (3 tests, added in task 5)
- _decide_via_anthropic_tools implementation (8 tests, added in task 6)
"""

from unittest.mock import AsyncMock, MagicMock

from dazzle.agent.core import AgentTool, DazzleAgent, Mission
from dazzle.agent.models import PageState


def _mock_observer() -> MagicMock:
    obs = AsyncMock()
    obs.observe.return_value = PageState(url="http://test", title="test")
    obs.navigate = AsyncMock()
    return obs


def _mock_executor() -> MagicMock:
    return AsyncMock()


def _simple_mission() -> Mission:
    return Mission(name="test", system_prompt="test", max_steps=1)


def _structured_tool() -> AgentTool:
    """A tool with a schema suitable for Anthropic tool use."""
    return AgentTool(
        name="read_file",
        description="Read a file from the project tree.",
        schema={
            "type": "object",
            "required": ["path"],
            "properties": {"path": {"type": "string"}},
        },
        handler=lambda path: {"content": f"contents of {path}"},
    )


class TestUseToolCallsKwarg:
    """The use_tool_calls constructor kwarg."""

    def test_defaults_to_false(self) -> None:
        agent = DazzleAgent(_mock_observer(), _mock_executor(), api_key="test")
        assert agent._use_tool_calls is False

    def test_can_be_set_true(self) -> None:
        agent = DazzleAgent(
            _mock_observer(),
            _mock_executor(),
            api_key="test",
            use_tool_calls=True,
        )
        assert agent._use_tool_calls is True

    def test_tool_use_warned_latch_starts_false(self) -> None:
        agent = DazzleAgent(
            _mock_observer(),
            _mock_executor(),
            api_key="test",
            use_tool_calls=True,
        )
        assert agent._tool_use_warned is False
