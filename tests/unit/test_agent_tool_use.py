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


class TestDecideViaAnthropicTools:
    """Unit tests for _decide_via_anthropic_tools.

    These tests mock the Anthropic SDK client and verify that the method
    builds tools=[...] correctly, processes content blocks, and returns
    a well-formed AgentAction for each of the expected response shapes.
    """

    def _make_response(
        self,
        text_blocks: list[str] | None = None,
        tool_use_blocks: list[dict] | None = None,
        input_tokens: int = 100,
        output_tokens: int = 50,
    ) -> MagicMock:
        """Build a mock Anthropic Message with the given content blocks."""
        content = []
        for text in text_blocks or []:
            content.append(MagicMock(type="text", text=text))
        for tub in tool_use_blocks or []:
            block = MagicMock(type="tool_use")
            block.name = tub["name"]
            block.input = tub["input"]
            content.append(block)
        response = MagicMock(
            content=content,
            usage=MagicMock(input_tokens=input_tokens, output_tokens=output_tokens),
        )
        return response

    def _make_agent_with_mock_client(self, mock_response: MagicMock) -> DazzleAgent:
        """Build a DazzleAgent with its client replaced by a mock."""
        agent = DazzleAgent(
            _mock_observer(),
            _mock_executor(),
            api_key="test",
            use_tool_calls=True,
        )
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        agent._client = mock_client  # inject
        return agent

    def test_tool_use_text_and_tool_block(self) -> None:
        """Happy path: text reasoning + one tool_use block."""
        import json as _json

        response = self._make_response(
            text_blocks=["I'll read the file to understand the error."],
            tool_use_blocks=[{"name": "read_file", "input": {"path": "/foo"}}],
        )
        agent = self._make_agent_with_mock_client(response)

        action, tokens = agent._decide_via_anthropic_tools(
            system_prompt="test",
            messages=[],
            tool_registry={"read_file": _structured_tool()},
        )

        assert action.type == ActionType.TOOL
        assert action.target == "read_file"
        assert _json.loads(action.value) == {"path": "/foo"}
        assert "I'll read the file" in action.reasoning
        assert tokens == 150

    def test_tool_use_multiple_text_blocks_concatenated(self) -> None:
        response = self._make_response(
            text_blocks=["First thought.", "Second thought."],
            tool_use_blocks=[{"name": "read_file", "input": {"path": "/a"}}],
        )
        agent = self._make_agent_with_mock_client(response)

        action, _ = agent._decide_via_anthropic_tools(
            system_prompt="test",
            messages=[],
            tool_registry={"read_file": _structured_tool()},
        )

        assert "First thought." in action.reasoning
        assert "Second thought." in action.reasoning

    def test_tool_use_only_text_no_tool_block(self) -> None:
        """Model emitted reasoning only, no tool_use → DONE sentinel."""
        response = self._make_response(
            text_blocks=["I don't know what to do next."],
            tool_use_blocks=[],
        )
        agent = self._make_agent_with_mock_client(response)

        action, _ = agent._decide_via_anthropic_tools(
            system_prompt="test",
            messages=[],
            tool_registry={"read_file": _structured_tool()},
        )

        assert action.type == ActionType.DONE
        assert action.success is False
        assert "I don't know what to do next" in action.reasoning

    def test_tool_use_empty_content(self) -> None:
        """Completely empty response → DONE sentinel with default reasoning."""
        response = self._make_response(text_blocks=[], tool_use_blocks=[])
        agent = self._make_agent_with_mock_client(response)

        action, _ = agent._decide_via_anthropic_tools(
            system_prompt="test",
            messages=[],
            tool_registry={"read_file": _structured_tool()},
        )

        assert action.type == ActionType.DONE
        assert action.success is False
        assert "no tool_use block" in action.reasoning.lower()

    def test_tool_use_multiple_tool_blocks_takes_first(self, caplog) -> None:
        """Multiple tool_use blocks → take first, log rest at INFO."""
        import logging

        caplog.set_level(logging.INFO, logger="dazzle.agent.core")
        response = self._make_response(
            text_blocks=["Reading both files."],
            tool_use_blocks=[
                {"name": "read_file", "input": {"path": "/first"}},
                {"name": "read_file", "input": {"path": "/second"}},
            ],
        )
        agent = self._make_agent_with_mock_client(response)

        action, _ = agent._decide_via_anthropic_tools(
            system_prompt="test",
            messages=[],
            tool_registry={"read_file": _structured_tool()},
        )

        import json as _json

        assert _json.loads(action.value) == {"path": "/first"}
        # Verify the ignored block was logged
        ignored_logs = [r for r in caplog.records if "ignored" in r.message.lower()]
        assert len(ignored_logs) == 1

    def test_tool_use_builds_tools_from_schema(self) -> None:
        """The merged tools=[...] list contains both builtin actions and mission tools.

        Cycle 194 change: ``_decide_via_anthropic_tools`` now prepends the 8
        builtin page-action tools (navigate/click/type/select/scroll/wait/assert/
        done) to the mission tools. This test verifies the mission tool is
        still present and unchanged within the merged list.
        """
        response = self._make_response(
            text_blocks=[],
            tool_use_blocks=[{"name": "read_file", "input": {"path": "/x"}}],
        )
        agent = self._make_agent_with_mock_client(response)
        tool = _structured_tool()

        agent._decide_via_anthropic_tools(
            system_prompt="test",
            messages=[{"role": "user", "content": "hello"}],
            tool_registry={"read_file": tool},
        )

        call_args = agent._client.messages.create.call_args
        tools_arg = call_args.kwargs.get("tools")
        assert tools_arg is not None
        # 8 builtin page actions + 1 mission tool
        assert len(tools_arg) == 9
        builtin_names = {"navigate", "click", "type", "select", "scroll", "wait", "assert", "done"}
        names = {t["name"] for t in tools_arg}
        assert builtin_names.issubset(names)
        mission_tool_entry = next(t for t in tools_arg if t["name"] == "read_file")
        assert mission_tool_entry["description"] == tool.description
        assert mission_tool_entry["input_schema"] == tool.schema

    def test_tool_use_input_serialised_to_string(self) -> None:
        """tool_use.input arrives as a dict; agent serialises to string for _execute_tool compat."""
        import json as _json

        nested_input = {
            "fixes": [{"file_path": "a.py", "diff": "foo", "rationale": "r", "confidence": 0.9}],
            "rationale": "test",
        }
        response = self._make_response(
            text_blocks=[],
            tool_use_blocks=[{"name": "read_file", "input": nested_input}],
        )
        agent = self._make_agent_with_mock_client(response)

        action, _ = agent._decide_via_anthropic_tools(
            system_prompt="test",
            messages=[],
            tool_registry={"read_file": _structured_tool()},
        )

        # action.value is a string
        assert isinstance(action.value, str)
        # but it deserialises back to the original nested dict
        assert _json.loads(action.value) == nested_input

    def test_tool_use_tokens_reported(self) -> None:
        """Token usage extraction from response.usage."""
        response = self._make_response(
            text_blocks=[],
            tool_use_blocks=[{"name": "read_file", "input": {"path": "/x"}}],
            input_tokens=200,
            output_tokens=100,
        )
        agent = self._make_agent_with_mock_client(response)

        _, tokens = agent._decide_via_anthropic_tools(
            system_prompt="test",
            messages=[],
            tool_registry={"read_file": _structured_tool()},
        )
        assert tokens == 300

    def test_tool_use_empty_mission_registry_still_sends_builtin_tools(self) -> None:
        """Empty mission tool_registry still passes the 8 builtin page actions.

        Cycle 194 change: builtin page actions (navigate/click/type/...) are now
        declared as native SDK tools and sent on every tool-use call, regardless
        of whether the mission registered any tools. The pre-cycle-194
        "tools kwarg omitted on empty registry" contract no longer applies —
        the merged list is never empty.
        """
        response = self._make_response(
            text_blocks=["I have no mission tools to call."],
            tool_use_blocks=[],
        )
        agent = self._make_agent_with_mock_client(response)

        action, _ = agent._decide_via_anthropic_tools(
            system_prompt="test",
            messages=[],
            tool_registry={},  # empty mission registry
        )

        # Action is a DONE sentinel because no tool_use block was returned
        assert action.type == ActionType.DONE
        assert action.success is False

        # tools=... kwarg MUST be present and hold the 8 builtin page actions
        call_kwargs = agent._client.messages.create.call_args.kwargs
        assert "tools" in call_kwargs
        builtin_names = {"navigate", "click", "type", "select", "scroll", "wait", "assert", "done"}
        names = {t["name"] for t in call_kwargs["tools"]}
        assert names == builtin_names


class TestBuiltinActionToolUse:
    """Cycle 194: builtin page actions are routed through native tool use.

    Before cycle 194, page actions (navigate/click/type/...) were text-protocol
    only in the tool-use path — the LLM emitted them as text JSON, the SDK path
    found no tool_use block, and the agent returned DONE after 1 step. These
    tests verify that builtin actions now round-trip through ``tool_use`` blocks
    correctly, that mission tools still coexist, and that the system prompt
    omits the text-protocol reference when tool-use is enabled.
    """

    def _make_response(
        self,
        text_blocks: list[str] | None = None,
        tool_use_blocks: list[dict] | None = None,
    ) -> MagicMock:
        content = []
        for text in text_blocks or []:
            content.append(MagicMock(type="text", text=text))
        for tub in tool_use_blocks or []:
            block = MagicMock(type="tool_use")
            block.name = tub["name"]
            block.input = tub["input"]
            content.append(block)
        return MagicMock(
            content=content,
            usage=MagicMock(input_tokens=10, output_tokens=5),
        )

    def _agent(self, response: MagicMock) -> DazzleAgent:
        agent = DazzleAgent(
            _mock_observer(),
            _mock_executor(),
            api_key="test",
            use_tool_calls=True,
        )
        mock_client = MagicMock()
        mock_client.messages.create.return_value = response
        agent._client = mock_client
        return agent

    def test_navigate_tool_use_maps_to_navigate_action(self) -> None:
        """A tool_use block named 'navigate' produces ActionType.NAVIGATE."""
        response = self._make_response(
            text_blocks=["Exploring the contacts page."],
            tool_use_blocks=[
                {
                    "name": "navigate",
                    "input": {
                        "target": "/app/workspaces/contacts",
                        "reasoning": "Explore core contact management",
                    },
                }
            ],
        )
        agent = self._agent(response)

        action, _ = agent._decide_via_anthropic_tools(
            system_prompt="test",
            messages=[],
            tool_registry={},
        )

        assert action.type == ActionType.NAVIGATE
        assert action.target == "/app/workspaces/contacts"
        assert "Explore core contact management" in action.reasoning

    def test_click_tool_use_maps_to_click_action(self) -> None:
        response = self._make_response(
            text_blocks=[],
            tool_use_blocks=[
                {"name": "click", "input": {"target": "button.create", "reasoning": "open form"}}
            ],
        )
        agent = self._agent(response)
        action, _ = agent._decide_via_anthropic_tools(
            system_prompt="test", messages=[], tool_registry={}
        )
        assert action.type == ActionType.CLICK
        assert action.target == "button.create"

    def test_type_tool_use_maps_to_type_action_with_value(self) -> None:
        response = self._make_response(
            text_blocks=[],
            tool_use_blocks=[
                {
                    "name": "type",
                    "input": {
                        "target": "#field-email",
                        "value": "admin@example.com",
                        "reasoning": "fill email",
                    },
                }
            ],
        )
        agent = self._agent(response)
        action, _ = agent._decide_via_anthropic_tools(
            system_prompt="test", messages=[], tool_registry={}
        )
        assert action.type == ActionType.TYPE
        assert action.target == "#field-email"
        assert action.value == "admin@example.com"

    def test_done_tool_use_extracts_success_flag(self) -> None:
        response = self._make_response(
            text_blocks=[],
            tool_use_blocks=[
                {
                    "name": "done",
                    "input": {"success": False, "reasoning": "stuck on login page"},
                }
            ],
        )
        agent = self._agent(response)
        action, _ = agent._decide_via_anthropic_tools(
            system_prompt="test", messages=[], tool_registry={}
        )
        assert action.type == ActionType.DONE
        assert action.success is False
        assert "stuck on login" in action.reasoning

    def test_mission_tool_coexists_with_builtins(self) -> None:
        """A mission tool_use block still routes to ActionType.TOOL."""
        import json as _json

        response = self._make_response(
            text_blocks=[],
            tool_use_blocks=[
                {
                    "name": "read_file",
                    "input": {"path": "/x"},
                }
            ],
        )
        agent = self._agent(response)
        action, _ = agent._decide_via_anthropic_tools(
            system_prompt="test",
            messages=[],
            tool_registry={"read_file": _structured_tool()},
        )
        assert action.type == ActionType.TOOL
        assert action.target == "read_file"
        assert _json.loads(action.value) == {"path": "/x"}

    def test_mission_tool_with_builtin_name_is_dropped(self, caplog) -> None:
        """A mission tool named like a builtin (e.g. 'click') is dropped with a warning."""
        import logging

        caplog.set_level(logging.WARNING, logger="dazzle.agent.core")

        colliding_tool = AgentTool(
            name="click",
            description="mission-level click that should NOT win",
            schema={"type": "object", "properties": {}},
            handler=lambda: None,
        )
        response = self._make_response(
            text_blocks=[],
            tool_use_blocks=[{"name": "click", "input": {"target": "button.x"}}],
        )
        agent = self._agent(response)
        agent._decide_via_anthropic_tools(
            system_prompt="test",
            messages=[],
            tool_registry={"click": colliding_tool},
        )

        # Warning logged
        assert any("collides with a builtin" in r.message for r in caplog.records)

        # Only the builtin 'click' appears in tools=[...]; the mission one dropped
        call_kwargs = agent._client.messages.create.call_args.kwargs
        click_entries = [t for t in call_kwargs["tools"] if t["name"] == "click"]
        assert len(click_entries) == 1
        assert "mission-level click" not in click_entries[0]["description"]

    def test_system_prompt_tool_use_mode_omits_text_protocol(self) -> None:
        """Under use_tool_calls=True the prompt must not include text-protocol action block."""
        agent = DazzleAgent(_mock_observer(), _mock_executor(), api_key="test", use_tool_calls=True)
        mission = Mission(name="test", system_prompt="Explore the app.")
        prompt = agent._build_system_prompt(mission, tool_registry={})

        assert "Respond with a JSON object" not in prompt
        assert "## Available Page Actions" not in prompt
        assert "CRITICAL OUTPUT FORMAT" not in prompt
        # But the nudge to use tools is present
        assert "`done` tool" in prompt or "Use the provided tools" in prompt

    def test_system_prompt_legacy_mode_retains_text_protocol(self) -> None:
        """Under use_tool_calls=False the legacy text-protocol block is unchanged."""
        agent = DazzleAgent(
            _mock_observer(), _mock_executor(), api_key="test", use_tool_calls=False
        )
        mission = Mission(name="test", system_prompt="Explore the app.")
        prompt = agent._build_system_prompt(mission, tool_registry={})

        assert "Respond with a JSON object" in prompt
        assert "## Available Page Actions" in prompt
        assert "CRITICAL OUTPUT FORMAT" in prompt
