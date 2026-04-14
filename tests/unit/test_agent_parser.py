"""Tests for the DazzleAgent text-protocol parser and bracket counter helper.

Covers:
- _extract_first_json_object bracket counter (9 tests)
- _parse_action three-tier fallback (14 tests, added in task 2)
- Cycle 147 prose-before-JSON regression (1 test, added in task 3)
"""

import json
from unittest.mock import AsyncMock

from dazzle.agent.core import AgentTool, DazzleAgent, _extract_first_json_object
from dazzle.agent.models import ActionType, PageState


class TestBracketCounter:
    """Unit tests for _extract_first_json_object.

    The helper scans a string for the first balanced JSON object, respecting
    string literals and escape sequences. It returns (json_substring, surrounding_text)
    where surrounding_text is everything in the input minus the extracted object.
    If no balanced object is found, returns (None, original_text).
    """

    def test_extract_simple_object(self) -> None:
        json_str, surrounding = _extract_first_json_object('{"a": 1}')
        assert json_str == '{"a": 1}'
        assert surrounding == ""

    def test_extract_with_prose_before(self) -> None:
        json_str, surrounding = _extract_first_json_object('hello {"a": 1}')
        assert json_str == '{"a": 1}'
        assert surrounding == "hello "

    def test_extract_with_prose_after(self) -> None:
        json_str, surrounding = _extract_first_json_object('{"a": 1} world')
        assert json_str == '{"a": 1}'
        assert surrounding == " world"

    def test_extract_with_prose_around(self) -> None:
        json_str, surrounding = _extract_first_json_object('before {"a": 1} after')
        assert json_str == '{"a": 1}'
        assert surrounding == "before  after"

    def test_extract_nested(self) -> None:
        json_str, surrounding = _extract_first_json_object('{"a": {"b": 1}}')
        assert json_str == '{"a": {"b": 1}}'
        assert surrounding == ""

    def test_extract_with_brace_in_string(self) -> None:
        """Braces inside string literals must not be counted as structural brackets."""
        json_str, surrounding = _extract_first_json_object('{"a": "hello {world}"}')
        assert json_str == '{"a": "hello {world}"}'
        assert surrounding == ""

    def test_extract_with_escaped_quote(self) -> None:
        """Backslash-escaped quotes inside string literals must not close the string."""
        json_str, surrounding = _extract_first_json_object('{"a": "she said \\"hi\\""}')
        assert json_str == '{"a": "she said \\"hi\\""}'
        assert surrounding == ""

    def test_extract_multiple_objects_takes_first(self) -> None:
        json_str, surrounding = _extract_first_json_object('{"a": 1} {"b": 2}')
        assert json_str == '{"a": 1}'
        assert surrounding == ' {"b": 2}'

    def test_extract_no_object(self) -> None:
        json_str, surrounding = _extract_first_json_object("no braces here")
        assert json_str is None
        assert surrounding == "no braces here"

    def test_extract_unbalanced(self) -> None:
        """Missing closing brace — no balanced object found."""
        json_str, surrounding = _extract_first_json_object('{"a": 1')
        assert json_str is None
        assert surrounding == '{"a": 1'


def _make_agent() -> DazzleAgent:
    """Build a DazzleAgent with no-op observer/executor for parser tests."""
    observer = AsyncMock()
    observer.observe.return_value = PageState(url="http://test", title="test")
    executor = AsyncMock()
    return DazzleAgent(observer, executor, api_key="test-key")


def _tool(name: str = "read_file") -> AgentTool:
    return AgentTool(
        name=name,
        description=f"stub tool: {name}",
        schema={"type": "object", "properties": {"path": {"type": "string"}}},
        handler=lambda **kwargs: {"ok": True},
    )


class TestParseActionTier1:
    """Tier 1: plain json.loads succeeds (well-behaved output)."""

    def test_parse_plain_json_click(self) -> None:
        agent = _make_agent()
        response = '{"action": "click", "target": "#submit", "reasoning": "needed"}'
        action = agent._parse_action(response, tool_registry={})
        assert action.type == ActionType.CLICK
        assert action.target == "#submit"
        assert action.reasoning == "needed"

    def test_parse_plain_json_tool(self) -> None:
        agent = _make_agent()
        response = (
            '{"action": "tool", "target": "read_file", '
            '"value": {"path": "/foo"}, "reasoning": "inspect"}'
        )
        action = agent._parse_action(response, tool_registry={"read_file": _tool()})
        assert action.type == ActionType.TOOL
        assert action.target == "read_file"
        # value is serialised to a JSON string (existing contract with _execute_tool)
        assert json.loads(action.value) == {"path": "/foo"}
        assert action.reasoning == "inspect"

    def test_parse_plain_json_done(self) -> None:
        agent = _make_agent()
        response = '{"action": "done", "success": true, "reasoning": "complete"}'
        action = agent._parse_action(response, tool_registry={})
        assert action.type == ActionType.DONE
        assert action.success is True
        assert action.reasoning == "complete"


class TestParseActionTier2:
    """Tier 2: bracket counter extracts JSON from prose-wrapped responses."""

    def test_parse_prose_before_json(self) -> None:
        agent = _make_agent()
        response = (
            "I'll start by exploring the ticket form. "
            '{"action": "navigate", "target": "/app/ticket/create", '
            '"reasoning": "entry point"}'
        )
        action = agent._parse_action(response, tool_registry={})
        assert action.type == ActionType.NAVIGATE
        assert action.target == "/app/ticket/create"
        # Reasoning preserves both the JSON's reasoning field AND the prose
        assert "entry point" in action.reasoning
        assert "I'll start by exploring the ticket form" in action.reasoning
        assert "[PROSE]" in action.reasoning

    def test_parse_prose_after_json(self) -> None:
        agent = _make_agent()
        response = '{"action": "done", "reasoning": "ok"} Okay, that should work.'
        action = agent._parse_action(response, tool_registry={})
        assert action.type == ActionType.DONE
        assert "ok" in action.reasoning
        assert "that should work" in action.reasoning

    def test_parse_prose_around_json(self) -> None:
        agent = _make_agent()
        response = (
            "Let me think... "
            '{"action": "click", "target": "#foo", "reasoning": "target found"}'
            " — yes that's right."
        )
        action = agent._parse_action(response, tool_registry={})
        assert action.type == ActionType.CLICK
        assert "target found" in action.reasoning
        assert "Let me think" in action.reasoning
        assert "yes that's right" in action.reasoning

    def test_parse_markdown_code_fence(self) -> None:
        """Bracket counter finds the object inside markdown fences."""
        agent = _make_agent()
        response = '```json\n{"action": "click", "target": "#foo", "reasoning": "found"}\n```'
        action = agent._parse_action(response, tool_registry={})
        assert action.type == ActionType.CLICK
        assert action.target == "#foo"

    def test_parse_nested_object_value(self) -> None:
        """Tool value can contain nested objects — parser handles the outer extraction."""
        agent = _make_agent()
        response = (
            '{"action": "tool", "target": "read_file", '
            '"value": {"nested": {"key": "val"}}, "reasoning": "go"}'
        )
        action = agent._parse_action(response, tool_registry={"read_file": _tool()})
        assert action.type == ActionType.TOOL
        assert json.loads(action.value) == {"nested": {"key": "val"}}

    def test_parse_json_with_string_containing_braces(self) -> None:
        """Bracket counter respects string literals — braces inside strings don't count."""
        agent = _make_agent()
        response = (
            '{"action": "type", "target": "#input", "value": "hello {world}", "reasoning": "test"}'
        )
        action = agent._parse_action(response, tool_registry={})
        assert action.type == ActionType.TYPE
        assert action.value == "hello {world}"

    def test_parse_json_with_escaped_quote(self) -> None:
        agent = _make_agent()
        response = (
            '{"action": "type", "target": "#input", '
            '"value": "she said \\"hi\\"", "reasoning": "test"}'
        )
        action = agent._parse_action(response, tool_registry={})
        assert action.type == ActionType.TYPE
        assert action.value == 'she said "hi"'

    def test_parse_tier2_extracted_substring_is_invalid_json(self) -> None:
        """Tier 2 succeeds at bracket extraction but the substring is malformed JSON.

        The bracket counter returns any balanced {...}, including JSON-looking but
        invalid content (unquoted keys, trailing commas, etc.). This test verifies
        the parser handles that case gracefully and returns a DONE/failure sentinel
        with a diagnostic reasoning, not a crash.
        """
        agent = _make_agent()
        response = "I think: {key: value}"  # balanced braces, not valid JSON
        action = agent._parse_action(response, tool_registry={})
        assert action.type == ActionType.DONE
        assert action.success is False
        assert "Extracted JSON was invalid" in action.reasoning

    def test_parse_json_root_is_not_an_object(self) -> None:
        """json.loads succeeds but returns a list → should fall through to tier 2 or tier 3.

        If the model emits `[{"action": "click"}]` (wrapped in a list), the parser
        should extract the first balanced object via tier 2. If the model emits
        `42` or `"hello"`, no extraction is possible and tier 3 returns DONE/failure.
        """
        agent = _make_agent()

        # Array wrapping — tier 1 rejects, tier 2 extracts the inner object
        response = '[{"action": "click", "target": "#foo", "reasoning": "wrapped"}]'
        action = agent._parse_action(response, tool_registry={})
        assert action.type == ActionType.CLICK
        assert action.target == "#foo"

        # Scalar at root — all tiers fail
        action = agent._parse_action("42", tool_registry={})
        assert action.type == ActionType.DONE
        assert action.success is False


class TestParseActionTier3:
    """Tier 3: no balanced JSON found — return DONE sentinel with diagnostic."""

    def test_parse_garbage(self) -> None:
        agent = _make_agent()
        response = "I'm sorry, I can't help with that."
        action = agent._parse_action(response, tool_registry={})
        assert action.type == ActionType.DONE
        assert action.success is False
        assert "Failed to extract action" in action.reasoning

    def test_parse_unbalanced_json(self) -> None:
        agent = _make_agent()
        response = '{"action": "click", "target": "#foo"'
        action = agent._parse_action(response, tool_registry={})
        assert action.type == ActionType.DONE
        assert action.success is False

    def test_parse_invalid_action_type(self) -> None:
        agent = _make_agent()
        response = '{"action": "teleport", "target": "moon"}'
        action = agent._parse_action(response, tool_registry={})
        assert action.type == ActionType.DONE
        assert action.success is False
        assert "teleport" in action.reasoning.lower() or "unknown" in action.reasoning.lower()

    def test_parse_unknown_tool_name(self) -> None:
        agent = _make_agent()
        response = (
            '{"action": "tool", "target": "nonexistent_tool", "value": {}, "reasoning": "bad"}'
        )
        action = agent._parse_action(response, tool_registry={"read_file": _tool()})
        # Parser strictly validates tool target against registry (task 2 change)
        assert action.type == ActionType.DONE
        assert action.success is False


class TestCycle147Regression:
    """Regression test for cycle 147's EXPLORE stagnation.

    In cycle 147 the agent stagnated at 8 steps because Claude 4.6
    consistently emitted prose preambles before the JSON action block.
    The strict parser returned DONE/failure on step 1, killing the
    mission. After task 2's parser refactor, the agent extracts the
    action from the prose-preambled response cleanly.

    This test uses the exact prose+JSON pattern captured from cycle 147's
    logs (see dev_docs/ux-log.md cycle 147 entry for the original
    occurrence).
    """

    def test_cycle_147_prose_preamble_pattern(self) -> None:
        """The exact pattern from cycle 147 logs must parse cleanly."""
        agent = _make_agent()
        # This pattern is copied verbatim from cycle 147's parsed-action
        # warning log message.
        cycle_147_response = (
            "I expect to see a forbidden error page, which suggests I need "
            "to navigate to a login page or the main application entry point "
            "to authenticate as admin.\n\n"
            '{"action": "navigate", "target": "/", '
            '"reasoning": "need to authenticate"}'
        )

        action = agent._parse_action(cycle_147_response, tool_registry={})

        # Before the fix: returned AgentAction(type=DONE, success=False).
        # After the fix: returns the parsed navigate action with prose preserved.
        assert action.type == ActionType.NAVIGATE
        assert action.target == "/"
        assert action.success is True
        assert "need to authenticate" in action.reasoning  # JSON reasoning field
        assert "forbidden error page" in action.reasoning  # prose preserved
        assert "[PROSE]" in action.reasoning  # marker present
