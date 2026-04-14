"""Integration test: investigator can emit propose_fix via Anthropic tool use.

This is the end-to-end proof that the task 1-7 changes solve bug 5b —
the investigator's nested-JSON propose_fix payload is no longer routed
through a stringified-JSON-in-JSON encoding, but arrives as a
structured tool_use block.

The test mocks the Anthropic SDK client but exercises the real
DazzleAgent code path, the real _decide_via_anthropic_tools
implementation, and the real investigator PROPOSE_FIX_SCHEMA. The
only thing faked is the remote LLM.
"""

import asyncio
import json as _json
from unittest.mock import AsyncMock, MagicMock

from dazzle.agent.core import AgentTool, DazzleAgent
from dazzle.agent.models import ActionType, PageState
from dazzle.fitness.investigator.tools_write import PROPOSE_FIX_SCHEMA


def _mock_observer() -> MagicMock:
    obs = AsyncMock()
    obs.observe.return_value = PageState(url="http://test", title="test")
    return obs


def _mock_executor() -> MagicMock:
    return AsyncMock()


def _mock_propose_fix_handler() -> tuple[MagicMock, list[dict]]:
    """Return (handler, call_log) where call_log captures every invocation."""
    call_log: list[dict] = []

    def handler(**kwargs) -> dict:
        call_log.append(kwargs)
        return {"status": "proposed", "proposal_id": "test-123"}

    return handler, call_log


class TestInvestigatorProposeFixViaToolUse:
    """End-to-end: investigator propose_fix via Anthropic native tool use."""

    def test_nested_changes_array_arrives_intact(self) -> None:
        """Bug 5b regression: the nested fixes array round-trips correctly."""
        # Given: a DazzleAgent with use_tool_calls=True and a propose_fix
        # tool that uses the tightened PROPOSE_FIX_SCHEMA
        handler, call_log = _mock_propose_fix_handler()
        propose_fix_tool = AgentTool(
            name="propose_fix",
            description="Write a proposal.",
            schema=PROPOSE_FIX_SCHEMA,
            handler=handler,
        )
        tool_registry = {"propose_fix": propose_fix_tool}

        # And: a mock Anthropic client that returns a tool_use block with
        # the exact nested structure propose_fix expects
        nested_input = {
            "fixes": [
                {
                    "file_path": "src/dazzle/fitness/engine.py",
                    "line_range": [148, 155],
                    "diff": "- findings.extend(...)\n+ findings.extend(...)",
                    "rationale": "Correct argument ordering",
                    "confidence": 0.9,
                },
                {
                    "file_path": "src/dazzle/fitness/cross_check.py",
                    "diff": "new function",
                    "rationale": "Add missing helper",
                    "confidence": 0.85,
                },
            ],
            "rationale": "Two related changes fix the cluster.",
            "overall_confidence": 0.88,
            "verification_plan": "Run pytest tests/fitness/ -v",
            "alternatives_considered": ["Do nothing", "Revert cycle 156"],
            "investigation_log": "Read engine.py, read cross_check.py, identified issue.",
        }

        tool_use_block = MagicMock(type="tool_use")
        tool_use_block.name = "propose_fix"
        tool_use_block.input = nested_input

        text_block = MagicMock(
            type="text",
            text="Based on the cluster evidence, the root cause is clear.",
        )

        mock_response = MagicMock(
            content=[text_block, tool_use_block],
            usage=MagicMock(input_tokens=500, output_tokens=200),
        )

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        agent = DazzleAgent(
            _mock_observer(),
            _mock_executor(),
            api_key="test",
            use_tool_calls=True,
        )
        agent._client = mock_client

        # When: _decide_via_anthropic_tools runs
        action, tokens = agent._decide_via_anthropic_tools(
            system_prompt="You are an investigator.",
            messages=[{"role": "user", "content": "investigate"}],
            tool_registry=tool_registry,
        )

        # Then: the action is a propose_fix tool invocation with the
        # nested structure serialised to a JSON string
        assert action.type == ActionType.TOOL
        assert action.target == "propose_fix"
        assert tokens == 700

        # And: the JSON string round-trips back to the original nested dict
        parsed_value = _json.loads(action.value)
        assert parsed_value == nested_input
        assert len(parsed_value["fixes"]) == 2
        assert parsed_value["fixes"][0]["line_range"] == [148, 155]
        assert parsed_value["fixes"][0]["confidence"] == 0.9

        # And: reasoning preserved the text block
        assert "root cause is clear" in action.reasoning

        # And: Anthropic was called with tools=[...] containing the full schema
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert len(call_kwargs["tools"]) == 1
        sent_schema = call_kwargs["tools"][0]["input_schema"]
        assert sent_schema["properties"]["fixes"]["items"]["required"] == [
            "file_path",
            "diff",
            "rationale",
            "confidence",
        ]

    def test_handler_receives_kwargs_from_tool_use_input(self) -> None:
        """After _execute_tool deserialises action.value, the handler gets kwargs."""
        handler, call_log = _mock_propose_fix_handler()
        propose_fix_tool = AgentTool(
            name="propose_fix",
            description="Write a proposal.",
            schema=PROPOSE_FIX_SCHEMA,
            handler=handler,
        )

        agent = DazzleAgent(
            _mock_observer(),
            _mock_executor(),
            api_key="test",
            use_tool_calls=True,
        )

        # Simulate a post-_decide_via_anthropic_tools AgentAction manually
        action_value = _json.dumps(
            {
                "fixes": [
                    {
                        "file_path": "a.py",
                        "diff": "x",
                        "rationale": "r",
                        "confidence": 0.5,
                    }
                ],
                "rationale": "test",
                "overall_confidence": 0.5,
                "verification_plan": "run tests",
                "alternatives_considered": [],
                "investigation_log": "minimal",
            }
        )

        # Execute via the agent's tool executor
        result = asyncio.run(agent._execute_tool(propose_fix_tool, action_value))

        # The handler received kwargs for every required field
        assert len(call_log) == 1
        call_kwargs = call_log[0]
        assert "fixes" in call_kwargs
        assert "rationale" in call_kwargs
        assert "overall_confidence" in call_kwargs
        assert "verification_plan" in call_kwargs
        assert "alternatives_considered" in call_kwargs
        assert "investigation_log" in call_kwargs
        assert call_kwargs["fixes"][0]["file_path"] == "a.py"
        assert result.ok
