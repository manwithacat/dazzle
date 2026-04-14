"""Tests for the DazzleAgent tool-use code path.

Covers:
- use_tool_calls kwarg on __init__ (3 tests)
- Three-way branch in _decide + MCP sampling warning latch (3 tests, added in task 5)
- _decide_via_anthropic_tools implementation (8 tests, added in task 6)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.agent.core import AgentTool, DazzleAgent, Mission
from dazzle.agent.models import ActionType, PageState


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


class TestDecideBranching:
    """Three-way branch logic in _decide."""

    @pytest.mark.asyncio
    async def test_mcp_session_with_tool_calls_logs_warning_once(self, caplog) -> None:
        """use_tool_calls=True + mcp_session → one-shot warning, falls back to text."""
        import logging

        caplog.set_level(logging.WARNING, logger="dazzle.agent.core")

        # Mock MCP session that returns a simple JSON action text
        session = MagicMock()
        session.create_message = AsyncMock(
            return_value=MagicMock(content=MagicMock(text='{"action": "done", "reasoning": "ok"}'))
        )

        agent = DazzleAgent(
            _mock_observer(),
            _mock_executor(),
            mcp_session=session,
            use_tool_calls=True,
        )
        mission = _simple_mission()
        state = PageState(url="http://test", title="test")

        # Call _decide twice — warning should fire only on the first call.
        await agent._decide(mission, state, tool_registry={})
        first_warning_count = sum(1 for r in caplog.records if "use_tool_calls" in r.message)

        await agent._decide(mission, state, tool_registry={})
        total_warning_count = sum(1 for r in caplog.records if "use_tool_calls" in r.message)

        assert first_warning_count == 1
        assert total_warning_count == 1  # latch prevents second warning

    @pytest.mark.asyncio
    async def test_mcp_session_without_tool_calls_no_warning(self, caplog) -> None:
        """use_tool_calls=False + mcp_session → no warning, existing behaviour."""
        import logging

        caplog.set_level(logging.WARNING, logger="dazzle.agent.core")

        session = MagicMock()
        session.create_message = AsyncMock(
            return_value=MagicMock(content=MagicMock(text='{"action": "done", "reasoning": "ok"}'))
        )

        agent = DazzleAgent(
            _mock_observer(),
            _mock_executor(),
            mcp_session=session,
            use_tool_calls=False,
        )
        mission = _simple_mission()
        state = PageState(url="http://test", title="test")
        await agent._decide(mission, state, tool_registry={})

        warning_count = sum(1 for r in caplog.records if "use_tool_calls" in r.message)
        assert warning_count == 0

    @pytest.mark.asyncio
    async def test_sdk_with_tool_calls_dispatches_to_tools_path(self) -> None:
        """use_tool_calls=True + no mcp_session → routes through _decide_via_anthropic_tools."""
        agent = DazzleAgent(
            _mock_observer(),
            _mock_executor(),
            api_key="test",
            use_tool_calls=True,
        )

        # Stub the tools method to assert it's called. It needs to return
        # a tuple (AgentAction, tokens) matching the real signature.
        from dazzle.agent.models import AgentAction

        stub_action = AgentAction(type=ActionType.DONE, reasoning="stubbed")
        agent._decide_via_anthropic_tools = MagicMock(return_value=(stub_action, 42))

        mission = _simple_mission()
        state = PageState(url="http://test", title="test")
        action, _, _, tokens = await agent._decide(mission, state, tool_registry={})

        agent._decide_via_anthropic_tools.assert_called_once()
        assert action is stub_action
        assert tokens == 42
