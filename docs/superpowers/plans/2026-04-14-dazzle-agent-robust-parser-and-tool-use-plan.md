# DazzleAgent Robust Parser and Optional Tool Use Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix DazzleAgent's two protocol bugs (prose-before-JSON parse failure + nested-JSON-in-tool-values encoding) so autonomous cycles can run for hours without stagnating.

**Architecture:** Three-tier fallback parser (`json.loads` → bracket-counting extraction → diagnostic DONE sentinel) fixes the text-protocol parse bug on all paths. A new opt-in SDK-only code path wires Anthropic's native tool use API for missions that need structured outputs (investigator `propose_fix`). Single `DazzleAgent` class, additive changes, no refactor of the outer `observe → decide → execute → record` loop.

**Tech Stack:** Python 3.12, Anthropic SDK (already a dependency), pytest, mypy, ruff.

**Spec reference:** `docs/superpowers/specs/2026-04-14-dazzle-agent-robust-parser-and-tool-use-design.md` (commit `ea6c9a94`).

---

## Context for the implementing engineer

You have zero context for this codebase. Read this section before starting.

### What DazzleAgent is

`DazzleAgent` (`src/dazzle/agent/core.py`) is a mission-agnostic autonomous agent framework. You give it a Mission (system prompt + tools + completion criteria), an Observer (how to see a page, typically Playwright), and an Executor (how to act on a page). It runs an observe → decide → execute → record loop, calling an LLM at each step to pick the next action.

The LLM can produce one of 9 action types: `click`, `type`, `select`, `navigate`, `scroll`, `wait`, `assert`, `done`, or `tool` (invoke a mission-specific tool). Currently the LLM communicates with the agent via a text protocol: the system prompt describes the 9-action JSON schema, the LLM emits a JSON object, the agent parses it with `json.loads`.

Two bugs live in this protocol:

**Bug 5a — prose-before-JSON.** Claude 4.6 frequently emits reasoning prose before the JSON action block:
```
"I'll start by exploring the ticket form. {\"action\": \"navigate\", \"target\": \"/app/ticket/create\"}"
```
The current `_parse_action` calls `json.loads(response)` which fails on the prose prefix. On failure it returns `AgentAction(type=DONE, success=False)`. The outer loop treats DONE as terminal. Mission stagnates at step 1. Cycle 147 reproduced this empirically (8 steps, 0 findings).

**Bug 5b — nested-JSON-in-tool-values.** Tool invocations are encoded as:
```json
{"action": "tool", "target": "propose_fix", "value": "{\"fixes\": [{\"file_path\": \"...\"}], \"rationale\": \"...\"}"}
```
That's a JSON string inside a JSON string. For simple tools with one or two string args the LLM handles this. For the investigator's `propose_fix` which requires a nested `fixes` array of objects, Claude 4.6 gets the escaping wrong reliably enough that the investigator's terminal action is effectively broken.

### The fixes

**Bug 5a** → refactor `_parse_action` to try `json.loads` first, then fall back to bracket-counting extraction of the first balanced `{...}` in the response (preserving surrounding prose as reasoning), then fall back to a diagnostic DONE sentinel. Fast path for well-behaved output; graceful degradation for prose-preambled output; clean failure for garbage.

**Bug 5b** → opt-in support for Anthropic's native tool use API. Missions that need structured outputs set `DazzleAgent(use_tool_calls=True)`. When set AND the agent is on the direct SDK path, `_decide` routes through a new method that builds `tools=[...]` from the registry and processes `tool_use` content blocks directly (no stringified-JSON encoding). On the MCP sampling path, the flag is ignored with a one-time warning.

### Two spec-vs-reality deviations the implementing engineer must know about

**Deviation 1 — `AgentTool.schema` already exists.** The spec (Section 5.1) proposed adding an optional `input_schema` field to `AgentTool`. The codebase already has a required `schema: dict[str, Any]` field on `AgentTool` (see `src/dazzle/agent/core.py:35-42`). Every existing tool already constructs with a `schema=`. **This plan reuses the existing `schema` field — no rename, no new field.** The tool-use path will read `tool.schema` and pass it as Anthropic's `input_schema` parameter.

**Deviation 2 — Prompt hardening already exists.** The spec (Section 5.5) proposed appending a paragraph to the system prompt demanding JSON-only output. The current prompt already contains this (see `src/dazzle/agent/core.py:372-374`):
```
## CRITICAL OUTPUT FORMAT
Respond with ONLY a single JSON object. No text before or after.
Do NOT use markdown code blocks. Your entire response must be parseable as JSON.
```
Claude 4.6 ignores this instruction regularly — which is why Bug 5a exists in the first place. **This plan adds NO prompt hardening task.** The parser fix is the real fix; the prompt hardening was already in place and already failing. The plan adds one comment pointing back to cycle 147 so future maintainers know the prompt was never the solution.

### File layout you'll touch

Source code:
- `src/dazzle/agent/core.py` — parser refactor, new helper, new method, kwarg addition, three-way branch in `_decide`. Currently 485 LOC; expect to grow to ~600 LOC.
- `src/dazzle/fitness/investigator/tools_write.py` — tighten the propose_fix schema.
- `src/dazzle/fitness/investigator/runner.py` — flip `use_tool_calls=True`.

Tests:
- `tests/unit/test_agent_parser.py` — NEW. Parser + bracket counter + cycle 147 regression. ~24 tests.
- `tests/unit/test_agent_tool_use.py` — NEW. `_decide_via_anthropic_tools` + kwarg + branching. ~11 tests.
- `tests/integration/test_agent_investigator_tool_use.py` — NEW. End-to-end investigator with mocked Anthropic. 1 test.

### How tests work in this codebase

- Framework: pytest
- Run a single file: `pytest tests/unit/test_agent_parser.py -v`
- Run a single test: `pytest tests/unit/test_agent_parser.py::TestBracketCounter::test_extract_simple_object -v`
- Run the whole agent suite: `pytest tests/unit/test_agent_core.py tests/unit/test_agent_parser.py tests/unit/test_agent_tool_use.py -v`
- Existing fixtures in `tests/unit/test_agent_core.py` (`_mock_observer`, `_mock_executor`, `_simple_mission`) are reusable by copying into the new test files — they're small and each test file should be self-contained.
- Mock Anthropic responses: use `unittest.mock.MagicMock`. The Anthropic SDK's `Message` / `ContentBlock` types are duck-typed in our code (`block.type == "text"`, `block.text`, `block.type == "tool_use"`, `block.name`, `block.input`), so you can construct mocks with `MagicMock(type="text", text="...")` and they work.

### How to run quality gates

After every task, run:
```bash
ruff check src/dazzle/agent/ tests/unit/test_agent_parser.py tests/unit/test_agent_tool_use.py tests/integration/test_agent_investigator_tool_use.py --fix
ruff format src/dazzle/agent/ tests/unit/test_agent_parser.py tests/unit/test_agent_tool_use.py tests/integration/test_agent_investigator_tool_use.py
mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp --ignore-missing-imports --exclude 'eject'
```

Before the final commit:
```bash
pytest tests/unit/test_agent_core.py tests/unit/test_agent_parser.py tests/unit/test_agent_tool_use.py tests/integration/test_agent_investigator_tool_use.py -v
```

---

## File structure decision

**New files (create):**

1. `tests/unit/test_agent_parser.py` — Parser, bracket counter, and cycle 147 regression tests. Kept as one file because all three target the same function family (`_parse_action` + `_extract_first_json_object`).

2. `tests/unit/test_agent_tool_use.py` — `_decide_via_anthropic_tools` + `use_tool_calls` kwarg + three-way branch tests. Kept as one file because all three target the same new code path.

3. `tests/integration/test_agent_investigator_tool_use.py` — End-to-end investigator propose_fix with mocked Anthropic. Separate from the unit tests because it exercises the full investigator runner + mocked SDK, not just the parser or tool_use method.

**Modified files:**

4. `src/dazzle/agent/core.py` — the bulk of the changes.

5. `src/dazzle/fitness/investigator/tools_write.py` — schema tightening only.

6. `src/dazzle/fitness/investigator/runner.py` — one line to flip `use_tool_calls=True`.

7. `CHANGELOG.md` — one new entry under `[Unreleased]`.

---

## Task 1: Bracket counter helper `_extract_first_json_object`

**Files:**
- Create: `tests/unit/test_agent_parser.py`
- Modify: `src/dazzle/agent/core.py` (add `_extract_first_json_object` module-level function above class definitions)

- [ ] **Step 1.1: Write the failing tests**

Create `tests/unit/test_agent_parser.py` with the bracket counter test class. This includes all 9 bracket-counter tests.

```python
"""Tests for the DazzleAgent text-protocol parser and bracket counter helper.

Covers:
- _extract_first_json_object bracket counter (9 tests)
- _parse_action three-tier fallback (14 tests, added in task 2)
- Cycle 147 prose-before-JSON regression (1 test, added in task 3)
"""

from dazzle.agent.core import _extract_first_json_object


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
        assert surrounding == " {\"b\": 2}"

    def test_extract_no_object(self) -> None:
        json_str, surrounding = _extract_first_json_object("no braces here")
        assert json_str is None
        assert surrounding == "no braces here"

    def test_extract_unbalanced(self) -> None:
        """Missing closing brace — no balanced object found."""
        json_str, surrounding = _extract_first_json_object('{"a": 1')
        assert json_str is None
        assert surrounding == '{"a": 1'
```

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
pytest tests/unit/test_agent_parser.py -v
```
Expected: ImportError — `_extract_first_json_object` doesn't exist yet.

- [ ] **Step 1.3: Implement the bracket counter**

Open `src/dazzle/agent/core.py`. Add the new function after the imports (around line 28), before `class AgentTool`:

```python
def _extract_first_json_object(text: str) -> tuple[str | None, str]:
    """Find the first balanced JSON object in a string.

    Scans ``text`` for the first ``{...}`` whose braces are balanced,
    respecting string literals and escape sequences. Returns
    ``(json_substring, surrounding_text)`` where ``surrounding_text`` is
    ``text`` with the extracted substring removed. If no balanced object
    is found, returns ``(None, text)`` unchanged.

    Handles:
        - Nested braces
        - String literals (braces inside ``"..."`` are treated as characters)
        - Escape sequences inside strings (``\\"``, ``\\\\``)

    The intent is to pull a JSON action object out of a response that may
    contain free-form prose before, after, or around it — e.g. the
    prose-before-JSON pattern from cycle 147 where Claude 4.6 emitted
    ``"I'll start by exploring. {\\"action\\": \\"navigate\\"}"``.
    """
    start = -1
    depth = 0
    in_string = False
    escape_next = False

    for i, ch in enumerate(text):
        if escape_next:
            # Previous char was a backslash; skip this char regardless.
            escape_next = False
            continue

        if in_string:
            if ch == "\\":
                escape_next = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    end = i + 1
                    json_substring = text[start:end]
                    surrounding = text[:start] + text[end:]
                    return json_substring, surrounding

    return None, text
```

- [ ] **Step 1.4: Run tests to verify they pass**

```bash
pytest tests/unit/test_agent_parser.py -v
```
Expected: 9 passed.

- [ ] **Step 1.5: Lint and type check**

```bash
ruff check src/dazzle/agent/core.py tests/unit/test_agent_parser.py --fix
ruff format src/dazzle/agent/core.py tests/unit/test_agent_parser.py
mypy src/dazzle/agent --ignore-missing-imports
```
Expected: all pass, no errors.

- [ ] **Step 1.6: Commit**

```bash
git add src/dazzle/agent/core.py tests/unit/test_agent_parser.py
git commit -m "$(cat <<'EOF'
feat(agent): add _extract_first_json_object bracket counter helper

Module-level helper that scans a string for the first balanced JSON
object, respecting string literals and escape sequences. Returns the
extracted substring and whatever text surrounds it.

This is the core primitive for the parser robustness fix (bug 5a —
prose-before-JSON parse failures). Task 2 will refactor _parse_action
to use this helper as its tier-2 fallback.

9 unit tests cover: simple object, nested, prose before/after/around,
brace-in-string, escaped-quote, multiple-objects-takes-first, no object,
unbalanced.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Refactor `_parse_action` to three-tier fallback

**Files:**
- Modify: `src/dazzle/agent/core.py` — replace existing `_parse_action` method (currently lines 421-462)
- Modify: `tests/unit/test_agent_parser.py` — add `TestParseAction` test class

- [ ] **Step 2.1: Write the failing tests**

Add to `tests/unit/test_agent_parser.py` below the existing `TestBracketCounter` class:

```python
from unittest.mock import AsyncMock, MagicMock

from dazzle.agent.core import AgentTool, DazzleAgent
from dazzle.agent.models import ActionType, PageState


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
        import json as _json
        assert _json.loads(action.value) == {"path": "/foo"}
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
        response = (
            "```json\n"
            '{"action": "click", "target": "#foo", "reasoning": "found"}\n'
            "```"
        )
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
        import json as _json
        assert _json.loads(action.value) == {"nested": {"key": "val"}}

    def test_parse_json_with_string_containing_braces(self) -> None:
        """Bracket counter respects string literals — braces inside strings don't count."""
        agent = _make_agent()
        response = (
            '{"action": "type", "target": "#input", "value": "hello {world}", '
            '"reasoning": "test"}'
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
            '{"action": "tool", "target": "nonexistent_tool", '
            '"value": {}, "reasoning": "bad"}'
        )
        action = agent._parse_action(response, tool_registry={"read_file": _tool()})
        # Parser accepts it as a tool action (target validation happens later in
        # _execute_tool via tool_registry lookup). But if you prefer strict
        # upfront validation, the parser returns DONE/failure.
        # Matching the more defensible strict behaviour:
        assert action.type == ActionType.DONE
        assert action.success is False
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
pytest tests/unit/test_agent_parser.py::TestParseActionTier1 tests/unit/test_agent_parser.py::TestParseActionTier2 tests/unit/test_agent_parser.py::TestParseActionTier3 -v
```
Expected: most tests fail because the current parser doesn't handle prose-before-JSON and doesn't preserve prose in reasoning, and doesn't strictly validate tool names.

- [ ] **Step 2.3: Replace `_parse_action` in `src/dazzle/agent/core.py`**

Find the existing `_parse_action` method (currently around lines 421-462) and replace it with the three-tier implementation below. Also delete the old `re` import usage in `_parse_action` — the bracket counter replaces the regex fallback.

```python
    def _parse_action(
        self,
        response: str,
        tool_registry: dict[str, AgentTool],
    ) -> AgentAction:
        """Parse an LLM text response into an AgentAction.

        Three-tier fallback for robustness against prose-before-JSON outputs
        (bug 5a, cycle 147):

        1. ``json.loads(response)`` — fast path for well-behaved output.
        2. ``_extract_first_json_object(response)`` — bracket-counting extraction
           for responses with prose surrounding a balanced JSON object. The
           surrounding prose is preserved in the action's reasoning field
           (reasoning-preservation principle: the raw LLM output is a
           reward/feedback corpus, not a presentation layer).
        3. No balanced JSON found — return ``AgentAction(type=DONE,
           success=False, reasoning=<diagnostic>)``. The outer loop treats
           DONE with success=False as a terminal failure.

        On valid parse but invalid action type or unknown tool target, returns
        a DONE/failure sentinel with a diagnostic reasoning string. The error
        path never raises — the outer loop expects a valid AgentAction every
        time.
        """
        surrounding_prose = ""

        # Tier 1: fast path — valid JSON already
        try:
            data = json.loads(response)
        except (json.JSONDecodeError, ValueError):
            # Tier 2: extract balanced JSON via bracket counter
            json_substring, surrounding_prose = _extract_first_json_object(response)
            if json_substring is None:
                # Tier 3: nothing to parse
                logger.warning(
                    "Parser failed to extract any JSON object from response: %s",
                    response[:200],
                )
                return AgentAction(
                    type=ActionType.DONE,
                    success=False,
                    reasoning=f"Failed to extract action. Full response: {response[:2000]}",
                )
            try:
                data = json.loads(json_substring)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(
                    "Parser extracted JSON substring but json.loads failed: %s, substring: %s",
                    e,
                    json_substring[:200],
                )
                return AgentAction(
                    type=ActionType.DONE,
                    success=False,
                    reasoning=f"Extracted JSON was invalid: {json_substring[:2000]}",
                )
            logger.debug(
                "Parser tier 2 extraction succeeded with %d chars of surrounding prose",
                len(surrounding_prose),
            )

        # Build reasoning — preserve both the structured reasoning field and
        # any surrounding prose from tier 2. The prose goes in raw, with a
        # [PROSE] marker so downstream analysis can distinguish the two
        # sources.
        structured_reasoning = str(data.get("reasoning", ""))
        prose_trimmed = surrounding_prose.strip()
        if prose_trimmed:
            reasoning = (
                f"{structured_reasoning} [PROSE]: {prose_trimmed}".strip()
            )
        else:
            reasoning = structured_reasoning

        action_str = data.get("action", "done")

        # Tool invocation — validate target exists in registry
        if action_str == "tool":
            target = data.get("target")
            if target not in tool_registry:
                logger.info("Parser: unknown tool target %r", target)
                return AgentAction(
                    type=ActionType.DONE,
                    success=False,
                    reasoning=f"Unknown tool: {target}. Available: {list(tool_registry.keys())}",
                )
            value = data.get("value", {})
            value_str = json.dumps(value) if isinstance(value, dict) else value
            return AgentAction(
                type=ActionType.TOOL,
                target=target,
                value=value_str,
                reasoning=reasoning,
            )

        # Page action — validate action_str is a known ActionType
        try:
            action_type = ActionType(action_str)
        except ValueError:
            logger.info("Parser: unknown action type %r", action_str)
            return AgentAction(
                type=ActionType.DONE,
                success=False,
                reasoning=f"Unknown action: {action_str}",
            )

        return AgentAction(
            type=action_type,
            target=data.get("target"),
            value=data.get("value"),
            reasoning=reasoning,
            success=data.get("success", True),
        )
```

Also, at the top of `core.py`, delete the `import re` line (line 16) since the regex-based markdown fence handling is replaced by the bracket counter. If other code in `core.py` uses `re`, leave the import. Check with:

```bash
grep -n "^import re\|^from re\| re\." src/dazzle/agent/core.py
```

If only line 16 uses `re`, delete it. If other uses exist, leave it.

- [ ] **Step 2.4: Run tests to verify they pass**

```bash
pytest tests/unit/test_agent_parser.py -v
```
Expected: all 23 tests pass (9 bracket counter + 3 tier 1 + 7 tier 2 + 4 tier 3).

- [ ] **Step 2.5: Run the existing agent test suite to check for regressions**

```bash
pytest tests/unit/test_agent_core.py -v
```
Expected: all existing tests still pass. The parser refactor changes behaviour on malformed inputs (previously returned DONE/failure, still does) and preserves prose (new behaviour, additive), so existing tests that assume well-formed JSON should be unaffected.

- [ ] **Step 2.6: Lint and type check**

```bash
ruff check src/dazzle/agent/core.py tests/unit/test_agent_parser.py --fix
ruff format src/dazzle/agent/core.py tests/unit/test_agent_parser.py
mypy src/dazzle/agent --ignore-missing-imports
```
Expected: all pass.

- [ ] **Step 2.7: Commit**

```bash
git add src/dazzle/agent/core.py tests/unit/test_agent_parser.py
git commit -m "$(cat <<'EOF'
feat(agent): three-tier fallback parser fixes prose-before-JSON bug

Refactor _parse_action to handle Claude 4.6's frequent prose-before-JSON
output pattern (bug 5a from cycle 147).

Tier 1: json.loads on the whole response — fast path for well-behaved
        output. Unchanged behaviour.
Tier 2: _extract_first_json_object bracket counter — extract the first
        balanced {...} from any position in the response. Surrounding
        prose is preserved in the action's reasoning field with a
        [PROSE] marker. This is the fix for bug 5a.
Tier 3: no balanced JSON found — return AgentAction(DONE, success=False)
        with a diagnostic reasoning. The outer loop treats this as a
        terminal failure.

Reasoning preservation principle: the raw LLM output is a
reward/feedback corpus for downstream evaluation tasks, not a
presentation layer. The parser never discards the model's prose; it
just structures the action extraction.

Also adds strict upfront validation for tool targets and action types:
unknown tool names and unknown action strings now return DONE/failure
at parse time with a clear diagnostic, instead of deferring to
_execute_tool.

23 new tests cover tiers 1/2/3 (3 + 7 + 4) plus the 9 bracket counter
unit tests from task 1.

Deletes the dead regex markdown-fence extraction — the bracket counter
finds objects inside fences directly.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Cycle 147 regression test

**Files:**
- Modify: `tests/unit/test_agent_parser.py` — add `TestCycle147Regression` class

- [ ] **Step 3.1: Write the failing test (it will actually pass already, but document the regression)**

Append to `tests/unit/test_agent_parser.py`:

```python
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
```

- [ ] **Step 3.2: Run the regression test**

```bash
pytest tests/unit/test_agent_parser.py::TestCycle147Regression -v
```
Expected: PASS (task 2's parser refactor already handles this).

- [ ] **Step 3.3: Lint**

```bash
ruff check tests/unit/test_agent_parser.py --fix
ruff format tests/unit/test_agent_parser.py
```

- [ ] **Step 3.4: Commit**

```bash
git add tests/unit/test_agent_parser.py
git commit -m "$(cat <<'EOF'
test(agent): add cycle 147 prose-preamble regression test

Locks in the fix for bug 5a with a test using the exact prose+JSON
pattern captured from cycle 147's stagnation logs. Before task 2's
parser refactor, this pattern caused DazzleAgent to return DONE/failure
on step 1 and terminate the mission. After the refactor, the parser
extracts the navigate action and preserves the prose preamble in the
reasoning field.

This test exists specifically as a cycle 147 reproduction and should
not be removed without updating dev_docs/ux-log.md cycle 147 entry
and the DazzleAgent parser contract.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add `use_tool_calls` kwarg to `DazzleAgent`

**Files:**
- Modify: `src/dazzle/agent/core.py` — extend `DazzleAgent.__init__`
- Create: `tests/unit/test_agent_tool_use.py` — new test file

- [ ] **Step 4.1: Write the failing test**

Create `tests/unit/test_agent_tool_use.py`:

```python
"""Tests for the DazzleAgent tool-use code path.

Covers:
- use_tool_calls kwarg on __init__ (3 tests)
- Three-way branch in _decide + MCP sampling warning latch (3 tests)
- _decide_via_anthropic_tools implementation (8 tests)
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
```

- [ ] **Step 4.2: Run tests to verify they fail**

```bash
pytest tests/unit/test_agent_tool_use.py::TestUseToolCallsKwarg -v
```
Expected: AttributeError — `_use_tool_calls` and `_tool_use_warned` don't exist yet.

- [ ] **Step 4.3: Extend `DazzleAgent.__init__`**

Open `src/dazzle/agent/core.py`. Find `DazzleAgent.__init__` (around line 93-110). Add the new kwarg and initialise the attributes.

Current signature (for reference):
```python
def __init__(
    self,
    observer,
    executor,
    model: str = "claude-sonnet-4-20250514",
    api_key: str | None = None,
    mcp_session: Any = None,
):
    self._observer = observer
    self._executor = executor
    self._model = model
    self._api_key = api_key
    self._mcp_session = mcp_session
    ...
```

New signature:
```python
def __init__(
    self,
    observer,
    executor,
    model: str = "claude-sonnet-4-20250514",
    api_key: str | None = None,
    mcp_session: Any = None,
    use_tool_calls: bool = False,
):
    self._observer = observer
    self._executor = executor
    self._model = model
    self._api_key = api_key
    self._mcp_session = mcp_session
    self._use_tool_calls = use_tool_calls
    self._tool_use_warned = False  # one-shot warning latch for MCP+tool_calls path
    ...
```

Keep all the other initialisation (self._client, self._history, etc.) unchanged.

- [ ] **Step 4.4: Run tests to verify they pass**

```bash
pytest tests/unit/test_agent_tool_use.py::TestUseToolCallsKwarg -v
```
Expected: 3 passed.

- [ ] **Step 4.5: Lint and type check**

```bash
ruff check src/dazzle/agent/core.py tests/unit/test_agent_tool_use.py --fix
ruff format src/dazzle/agent/core.py tests/unit/test_agent_tool_use.py
mypy src/dazzle/agent --ignore-missing-imports
```
Expected: all pass.

- [ ] **Step 4.6: Commit**

```bash
git add src/dazzle/agent/core.py tests/unit/test_agent_tool_use.py
git commit -m "$(cat <<'EOF'
feat(agent): add use_tool_calls kwarg to DazzleAgent

Opt-in flag that signals "prefer Anthropic native tool use when the SDK
path is active." Defaults to False — all existing call sites are
unchanged. Missions that need structured tool outputs (currently just
the investigator's propose_fix) will set it to True in task 8.

Also adds the _tool_use_warned latch that task 5 will use to emit a
one-shot warning when use_tool_calls=True is combined with an
mcp_session (MCP sampling is text-only, so tool use cannot be delivered
on that path and we fall back to the robust text parser).

3 new unit tests cover the kwarg default, explicit-true, and latch
initialisation.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Three-way branch in `_decide` + MCP sampling warning

**Files:**
- Modify: `src/dazzle/agent/core.py` — update `_decide` method
- Modify: `tests/unit/test_agent_tool_use.py` — add `TestDecideBranching` class

- [ ] **Step 5.1: Write the failing tests**

Append to `tests/unit/test_agent_tool_use.py`:

```python
class TestDecideBranching:
    """Three-way branch logic in _decide."""

    @pytest.mark.asyncio
    async def test_mcp_session_with_tool_calls_logs_warning_once(
        self, caplog
    ) -> None:
        """use_tool_calls=True + mcp_session → one-shot warning, falls back to text."""
        import logging
        caplog.set_level(logging.WARNING, logger="dazzle.agent.core")

        # Mock MCP session that returns a simple JSON action text
        session = MagicMock()
        session.create_message = AsyncMock(
            return_value=MagicMock(
                content=MagicMock(text='{"action": "done", "reasoning": "ok"}')
            )
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
        first_warning_count = sum(
            1 for r in caplog.records if "use_tool_calls" in r.message
        )

        await agent._decide(mission, state, tool_registry={})
        total_warning_count = sum(
            1 for r in caplog.records if "use_tool_calls" in r.message
        )

        assert first_warning_count == 1
        assert total_warning_count == 1  # latch prevents second warning

    @pytest.mark.asyncio
    async def test_mcp_session_without_tool_calls_no_warning(
        self, caplog
    ) -> None:
        """use_tool_calls=False + mcp_session → no warning, existing behaviour."""
        import logging
        caplog.set_level(logging.WARNING, logger="dazzle.agent.core")

        session = MagicMock()
        session.create_message = AsyncMock(
            return_value=MagicMock(
                content=MagicMock(text='{"action": "done", "reasoning": "ok"}')
            )
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

        warning_count = sum(
            1 for r in caplog.records if "use_tool_calls" in r.message
        )
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
```

- [ ] **Step 5.2: Run tests to verify they fail**

```bash
pytest tests/unit/test_agent_tool_use.py::TestDecideBranching -v
```
Expected: AttributeError or similar — `_decide_via_anthropic_tools` doesn't exist, `_decide` doesn't branch on `use_tool_calls`.

- [ ] **Step 5.3: Add a stub `_decide_via_anthropic_tools` method**

Add this stub to `DazzleAgent` (near `_decide_via_anthropic`, around line 267). Task 6 will replace the body with a real implementation.

```python
    def _decide_via_anthropic_tools(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tool_registry: dict[str, AgentTool],
    ) -> tuple[AgentAction, int]:
        """Request a completion via Anthropic SDK with native tool use.

        STUB — real implementation lands in task 6. Raises NotImplementedError
        so any accidental production invocation fails loudly before task 6.
        """
        raise NotImplementedError(
            "_decide_via_anthropic_tools stub — implement in task 6"
        )
```

- [ ] **Step 5.4: Update `_decide` with the three-way branch**

Find `_decide` (around line 241-265). Replace it with:

```python
    async def _decide(
        self,
        mission: Mission,
        state: PageState,
        tool_registry: dict[str, AgentTool],
    ) -> tuple[AgentAction, str, str, int]:
        """
        Get the next action from the LLM.

        Three-way dispatch:
        - MCP sampling (mcp_session is not None) → text protocol via _decide_via_sampling
        - SDK + use_tool_calls=True → native tool use via _decide_via_anthropic_tools
        - SDK + use_tool_calls=False → text protocol via _decide_via_anthropic (default)

        When use_tool_calls=True is combined with an mcp_session, the agent logs a
        one-shot warning (via _tool_use_warned latch) and falls back to the MCP
        sampling text path. MCP sampling is text-only and cannot deliver native
        tool use.

        Returns:
            (action, prompt_text, response_text, tokens_used)
        """
        system_prompt = self._build_system_prompt(mission, tool_registry)
        messages = self._build_messages(state)

        prompt_text = f"## System\n{system_prompt[:500]}...\n\n{state.to_prompt()}"

        if self._mcp_session is not None:
            # Path γ: MCP sampling + text protocol
            if self._use_tool_calls and not self._tool_use_warned:
                logger.warning(
                    "use_tool_calls=True requested but agent is running on MCP "
                    "sampling path which does not support native tool use. "
                    "Falling back to text protocol. The robust text parser will "
                    "still handle simple tool invocations, but complex nested "
                    "payloads may be unreliable."
                )
                self._tool_use_warned = True
            response_text, tokens = await self._decide_via_sampling(system_prompt, messages)
            action = self._parse_action(response_text, tool_registry)
        elif self._use_tool_calls:
            # Path β: SDK + native tool use
            action, tokens = self._decide_via_anthropic_tools(
                system_prompt, messages, tool_registry
            )
            response_text = action.reasoning  # reasoning IS the response on this path
        else:
            # Path α: SDK + text protocol (existing default)
            response_text, tokens = self._decide_via_anthropic(system_prompt, messages)
            action = self._parse_action(response_text, tool_registry)

        return action, prompt_text, response_text, tokens
```

- [ ] **Step 5.5: Run tests to verify they pass**

```bash
pytest tests/unit/test_agent_tool_use.py::TestDecideBranching -v
```
Expected: 3 passed. The third test (`test_sdk_with_tool_calls_dispatches_to_tools_path`) passes because the stub method is mocked in the test.

- [ ] **Step 5.6: Run the existing agent test suite**

```bash
pytest tests/unit/test_agent_core.py -v
```
Expected: all existing tests still pass. The `_decide` branch is backwards compatible: if `use_tool_calls=False` (default), the code path is exactly what it was before.

- [ ] **Step 5.7: Lint and type check**

```bash
ruff check src/dazzle/agent/core.py tests/unit/test_agent_tool_use.py --fix
ruff format src/dazzle/agent/core.py tests/unit/test_agent_tool_use.py
mypy src/dazzle/agent --ignore-missing-imports
```

- [ ] **Step 5.8: Commit**

```bash
git add src/dazzle/agent/core.py tests/unit/test_agent_tool_use.py
git commit -m "$(cat <<'EOF'
feat(agent): three-way branch in _decide for tool-use dispatch

_decide now dispatches to one of three paths:
- MCP sampling + text protocol (existing, mcp_session present)
- SDK + native tool use (new, mcp_session=None and use_tool_calls=True)
- SDK + text protocol (existing default, mcp_session=None and
  use_tool_calls=False)

When use_tool_calls=True is combined with an mcp_session (which is
text-only), a one-shot warning is logged via the _tool_use_warned latch
and the agent falls back to the MCP sampling text path. The robust
text parser from task 2 handles any JSON output that comes through.

_decide_via_anthropic_tools is added as a stub that raises
NotImplementedError. Task 6 replaces the stub with the real
implementation. The stub exists now so the branch logic can be tested
in isolation.

3 new unit tests cover: one-shot warning latch, no-warning when
use_tool_calls=False, and dispatch-to-tools-path when use_tool_calls=True.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Implement `_decide_via_anthropic_tools`

**Files:**
- Modify: `src/dazzle/agent/core.py` — replace stub with real implementation
- Modify: `tests/unit/test_agent_tool_use.py` — add `TestDecideViaAnthropicTools` class

- [ ] **Step 6.1: Write the failing tests**

Append to `tests/unit/test_agent_tool_use.py`:

```python
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

    def _make_agent_with_mock_client(
        self, mock_response: MagicMock
    ) -> DazzleAgent:
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
            tool_use_blocks=[
                {"name": "read_file", "input": {"path": "/foo"}}
            ],
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
        ignored_logs = [
            r for r in caplog.records if "ignored" in r.message.lower()
        ]
        assert len(ignored_logs) == 1

    def test_tool_use_builds_tools_from_schema(self) -> None:
        """Only tools with a non-empty schema should appear in tools=[...]."""
        # The existing AgentTool has a required schema field. For this test,
        # we verify that the agent uses each tool's schema as its input_schema.
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

        # Verify the client was called with tools=[...]
        call_args = agent._client.messages.create.call_args
        tools_arg = call_args.kwargs.get("tools")
        assert tools_arg is not None
        assert len(tools_arg) == 1
        assert tools_arg[0]["name"] == "read_file"
        assert tools_arg[0]["description"] == tool.description
        assert tools_arg[0]["input_schema"] == tool.schema

    def test_tool_use_input_serialised_to_string(self) -> None:
        """tool_use.input arrives as a dict; agent serialises to string for _execute_tool compat."""
        import json as _json
        nested_input = {
            "fixes": [
                {"file_path": "a.py", "diff": "foo", "rationale": "r", "confidence": 0.9}
            ],
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
```

- [ ] **Step 6.2: Run tests to verify they fail**

```bash
pytest tests/unit/test_agent_tool_use.py::TestDecideViaAnthropicTools -v
```
Expected: all 8 fail with `NotImplementedError` (the stub from task 5).

- [ ] **Step 6.3: Replace the stub with the real implementation**

Find the stub `_decide_via_anthropic_tools` in `src/dazzle/agent/core.py` and replace it with:

```python
    def _decide_via_anthropic_tools(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tool_registry: dict[str, AgentTool],
    ) -> tuple[AgentAction, int]:
        """Request a completion via Anthropic SDK with native tool use.

        Builds the ``tools=[...]`` parameter from tool_registry entries
        using each tool's ``schema`` field as the ``input_schema``. Sends
        the request. Collects text content blocks into reasoning. Takes
        the first ``tool_use`` content block as the action. If no
        tool_use block is present (model emitted text only), returns a
        DONE sentinel with the text as reasoning.

        This is the path that fixes bug 5b: nested JSON payloads arrive
        as structured ``block.input`` dicts and are never routed through
        a stringified-JSON-in-JSON encoding.

        Single-action-per-step contract: if the response contains
        multiple tool_use blocks, the first is used and the rest are
        logged at INFO level and discarded. Parallelism is explicitly
        out of scope (continuity over speed).
        """
        # Build tools=[...] from every tool in the registry. Every tool already
        # has a schema (required field on AgentTool), so all tools are eligible.
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.schema,
            }
            for tool in tool_registry.values()
        ]

        client = self._get_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=2000,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )

        # Extract token usage
        tokens = 0
        if hasattr(response, "usage"):
            tokens = (response.usage.input_tokens or 0) + (
                response.usage.output_tokens or 0
            )

        # Process content blocks: collect all text blocks as reasoning,
        # take the first tool_use block as the action.
        text_blocks: list[str] = []
        tool_use_block: Any = None
        ignored_tool_blocks: list[str] = []

        for block in response.content:
            if block.type == "text":
                text_blocks.append(block.text)
            elif block.type == "tool_use":
                if tool_use_block is None:
                    tool_use_block = block
                else:
                    ignored_tool_blocks.append(block.name)

        if ignored_tool_blocks:
            logger.info(
                "_decide_via_anthropic_tools: ignored %d additional tool_use blocks: %s",
                len(ignored_tool_blocks),
                ignored_tool_blocks,
            )

        reasoning = "\n".join(text_blocks).strip()

        if tool_use_block is None:
            # Model emitted text only → treat as done/stuck
            return (
                AgentAction(
                    type=ActionType.DONE,
                    success=False,
                    reasoning=reasoning or "Model emitted no tool_use block",
                ),
                tokens,
            )

        return (
            AgentAction(
                type=ActionType.TOOL,
                target=tool_use_block.name,
                value=json.dumps(tool_use_block.input),
                reasoning=reasoning,
            ),
            tokens,
        )
```

- [ ] **Step 6.4: Run tests to verify they pass**

```bash
pytest tests/unit/test_agent_tool_use.py -v
```
Expected: all 11 tests pass (3 kwarg + 3 branching + 8 tool_use implementation).

- [ ] **Step 6.5: Run the existing agent test suite**

```bash
pytest tests/unit/test_agent_core.py tests/unit/test_agent_parser.py tests/unit/test_agent_tool_use.py -v
```
Expected: all pass.

- [ ] **Step 6.6: Lint and type check**

```bash
ruff check src/dazzle/agent/core.py tests/unit/test_agent_tool_use.py --fix
ruff format src/dazzle/agent/core.py tests/unit/test_agent_tool_use.py
mypy src/dazzle/agent --ignore-missing-imports
```

- [ ] **Step 6.7: Commit**

```bash
git add src/dazzle/agent/core.py tests/unit/test_agent_tool_use.py
git commit -m "$(cat <<'EOF'
feat(agent): implement _decide_via_anthropic_tools for native tool use

Replaces the task 5 NotImplementedError stub with the real
implementation. This is the code path that fixes bug 5b (nested JSON
in tool values).

The method:
1. Builds tools=[...] from tool_registry entries, using each tool's
   existing schema field as Anthropic's input_schema parameter.
2. Calls client.messages.create with tools=[...]. Anthropic's API
   parses the model's tool_use output against the schema — invalid
   shapes are caught at the API boundary, not in our code.
3. Processes response content blocks: collects text blocks into
   reasoning (reasoning-preservation principle from the spec), takes
   the first tool_use block as the action, logs any additional
   tool_use blocks at INFO level and discards them (single-action-
   per-step contract, continuity over speed).
4. If no tool_use block is present, returns a DONE sentinel with
   text as reasoning. The outer loop treats this as a terminal
   "model is done/stuck" signal.
5. Serialises tool_use.input (dict) to json.dumps(...) before storing
   in AgentAction.value, preserving backwards compatibility with
   _execute_tool which deserialises via json.loads.

8 new unit tests cover every branch: happy path with text + tool_use,
multiple text blocks concatenated, text-only (no tool_use), empty
response, multiple tool_use blocks (takes first, logs rest), schema
wiring to tools=[...], nested input serialisation round-trip, and
token usage reporting.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Tighten investigator `propose_fix` schema for Anthropic validation

**Files:**
- Modify: `src/dazzle/fitness/investigator/tools_write.py` — tighten the schema

- [ ] **Step 7.1: Read the current schema**

Read `src/dazzle/fitness/investigator/tools_write.py` lines 142-170 to see the current `propose_fix` schema. It defines `fixes` as `{"type": "array"}` with no item constraints. Anthropic's tool use validation will accept this, but it provides no structural guidance to the model — the model can emit fixes with arbitrary shapes and the failures land in the Python handler's KeyError / TypeError path (which triggers the `_block_and_record` blocked-artefact flow).

The tightened schema constrains the `fixes` items so Anthropic's API-side validation catches malformed fixes before they reach the handler.

- [ ] **Step 7.2: Write the tightened schema constant**

Open `src/dazzle/fitness/investigator/tools_write.py`. Above the `_propose_fix_tool` function definition (around line 25), add a module-level constant:

```python
# Tightened JSON Schema for Anthropic tool use (see propose_fix below).
# The `fixes` array items are fully constrained so Anthropic's API-side
# validation catches malformed proposals before they reach the handler.
# When this schema is used with tool use (DazzleAgent(use_tool_calls=True)),
# the model literally cannot emit a fix missing file_path, diff, rationale,
# or confidence — the API rejects it at the content-block level.
PROPOSE_FIX_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "fixes",
        "rationale",
        "overall_confidence",
        "verification_plan",
        "alternatives_considered",
        "investigation_log",
    ],
    "properties": {
        "fixes": {
            "type": "array",
            "description": "Concrete file-level changes to apply.",
            "items": {
                "type": "object",
                "required": ["file_path", "diff", "rationale", "confidence"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to modify, relative to repo root.",
                    },
                    "line_range": {
                        "type": "array",
                        "description": "Optional [start_line, end_line] for the target region.",
                        "items": {"type": "integer"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "diff": {
                        "type": "string",
                        "description": "Unified diff or replacement text for this fix.",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Why this specific change is correct.",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Per-fix confidence in [0.0, 1.0].",
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                },
            },
        },
        "rationale": {
            "type": "string",
            "description": "Overall explanation of the proposed fix.",
        },
        "overall_confidence": {
            "type": "number",
            "description": "Overall confidence in the proposal in [0.0, 1.0].",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "verification_plan": {
            "type": "string",
            "description": "How to verify the fix works (test command, manual check, etc.).",
        },
        "alternatives_considered": {
            "type": "array",
            "description": "Other fixes that were considered and rejected.",
            "items": {"type": "string"},
        },
        "investigation_log": {
            "type": "string",
            "description": "Raw transcript of the investigation steps.",
        },
    },
}
```

- [ ] **Step 7.3: Use the constant in the tool definition**

Find the `return AgentTool(...)` call at the end of `_propose_fix_tool` (around line 141-170). Replace the inline `schema={...}` with a reference to `PROPOSE_FIX_SCHEMA`:

```python
    return AgentTool(
        name="propose_fix",
        description=(
            "Terminal: write a structured Proposal to disk and end the mission. "
            "Call this only when you have a concrete fix to propose."
        ),
        schema=PROPOSE_FIX_SCHEMA,
        handler=handler,
    )
```

Delete the old inline schema dict.

- [ ] **Step 7.4: Run the existing investigator test suite**

```bash
pytest tests/unit/fitness/test_investigator_tools.py tests/unit/fitness/test_investigator_tools_write.py -v 2>&1 | tail -30
```
Expected: all existing tests pass. The schema shape change is additive — it's strictly more constrained, so any valid existing input still validates.

Note: if those test files don't exist at those exact paths, find them with:
```bash
find tests -name "*investigator*" 2>&1 | head
```
and run whichever test file covers `propose_fix`.

- [ ] **Step 7.5: Lint and type check**

```bash
ruff check src/dazzle/fitness/investigator/tools_write.py --fix
ruff format src/dazzle/fitness/investigator/tools_write.py
mypy src/dazzle/fitness --ignore-missing-imports
```

- [ ] **Step 7.6: Commit**

```bash
git add src/dazzle/fitness/investigator/tools_write.py
git commit -m "$(cat <<'EOF'
refactor(investigator): tighten propose_fix schema for Anthropic tool use

Extract the propose_fix JSON Schema into a module-level PROPOSE_FIX_SCHEMA
constant and fully constrain the shape of the `fixes` array items. Each
fix is now required to have file_path (string), diff (string), rationale
(string), and confidence (number in [0, 1]). The optional line_range is
constrained to a 2-element array of integers.

When this schema is used with Anthropic's native tool use
(DazzleAgent(use_tool_calls=True) in task 8), the API validates the
model's tool_use.input against the schema before the response is
returned. Invalid shapes — missing file_path, wrong confidence range,
malformed line_range — are caught at the API boundary, not in the
Python handler's KeyError/TypeError path.

This removes the nested-JSON-encoding reliability problem that blocked
the investigator from completing propose_fix on the text protocol
(bug 5b).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Flip `use_tool_calls=True` in investigator runner + integration test

**Files:**
- Modify: `src/dazzle/fitness/investigator/runner.py` — one-line change
- Create: `tests/integration/test_agent_investigator_tool_use.py` — new integration test

- [ ] **Step 8.1: Write the failing integration test**

Create `tests/integration/test_agent_investigator_tool_use.py`:

```python
"""Integration test: investigator can emit propose_fix via Anthropic tool use.

This is the end-to-end proof that the task 1-7 changes solve bug 5b —
the investigator's nested-JSON propose_fix payload is no longer routed
through a stringified-JSON-in-JSON encoding, but arrives as a
structured tool_use block.

The test mocks the Anthropic SDK client but exercises the real
DazzleAgent code path, the real _decide_via_anthropic_tools
implementation, and the real investigator propose_fix handler. The
only thing faked is the remote LLM.
"""

import json as _json
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.agent.core import AgentTool, DazzleAgent, Mission
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
        import asyncio
        result = asyncio.run(
            agent._execute_tool(propose_fix_tool, action_value)
        )

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
```

- [ ] **Step 8.2: Run the test to verify it fails (or passes, depending on state)**

```bash
pytest tests/integration/test_agent_investigator_tool_use.py -v
```
Expected: **the test passes already!** Because tasks 1-7 implemented everything needed. The test exists to LOCK IN the end-to-end behaviour — it's a regression test, not a TDD driver. If it fails, something in tasks 1-7 is broken.

If the test passes, proceed to step 8.3 which is the actual "flip the runner" change.

- [ ] **Step 8.3: Flip `use_tool_calls=True` in the investigator runner**

Open `src/dazzle/fitness/investigator/runner.py`. Find the `DazzleAgent(...)` constructor call (around line 211). Add `use_tool_calls=True` to it.

Before:
```python
agent = DazzleAgent(
    observer,
    executor,
    model=model,
    api_key=api_key,
)
```

After:
```python
agent = DazzleAgent(
    observer,
    executor,
    model=model,
    api_key=api_key,
    use_tool_calls=True,  # bug 5b fix — use native tool use for propose_fix
)
```

Note: verify the actual surrounding constructor arguments before editing. Use:
```bash
grep -n "DazzleAgent(" src/dazzle/fitness/investigator/runner.py
```
to find the exact line. The ordering of kwargs may differ from the example above; add `use_tool_calls=True` at the end, before the closing paren.

- [ ] **Step 8.4: Run the full agent + investigator test suite**

```bash
pytest tests/unit/test_agent_core.py tests/unit/test_agent_parser.py tests/unit/test_agent_tool_use.py tests/integration/test_agent_investigator_tool_use.py -v
pytest tests/unit/fitness/ -v 2>&1 | tail -30
```
Expected: all pass. The investigator unit tests may exercise the runner — if they use mocked DazzleAgents they'll be unaffected; if they exercise the real DazzleAgent with fake Anthropic clients, they may need a small update to pass `use_tool_calls=True`.

If any investigator test fails because it doesn't handle `use_tool_calls=True`, it's either:
- Using a real (unmocked) Anthropic client (shouldn't, but check) — skip or mark expensive
- Not providing a mocked tool_use response — update its mock to return a `ToolUseBlock`

Handle minor updates as needed without scope creep.

- [ ] **Step 8.5: Lint and type check**

```bash
ruff check src/dazzle/fitness/investigator/runner.py tests/integration/test_agent_investigator_tool_use.py --fix
ruff format src/dazzle/fitness/investigator/runner.py tests/integration/test_agent_investigator_tool_use.py
mypy src/dazzle/fitness --ignore-missing-imports
mypy src/dazzle/agent --ignore-missing-imports
```

- [ ] **Step 8.6: Commit**

```bash
git add src/dazzle/fitness/investigator/runner.py tests/integration/test_agent_investigator_tool_use.py
git commit -m "$(cat <<'EOF'
feat(investigator): enable native tool use for propose_fix

Flip use_tool_calls=True on the investigator runner's DazzleAgent
construction. Combined with task 7's tightened PROPOSE_FIX_SCHEMA,
this means the investigator's terminal action now arrives as a
structured tool_use content block with its nested fixes array intact,
instead of a stringified JSON-in-JSON encoding that Claude 4.6 got
wrong reliably.

Bug 5b is now fixed for the investigator's motivating case.

Integration test (tests/integration/test_agent_investigator_tool_use.py)
covers:
- End-to-end propose_fix via _decide_via_anthropic_tools with a fully
  populated nested fixes array (line_range, confidence, multiple fixes)
- Verification that the JSON round-trip preserves the exact structure
- Verification that Anthropic is called with tools=[{input_schema: ...}]
  carrying the full PROPOSE_FIX_SCHEMA constraints
- Handler execution: after _execute_tool deserialises action.value,
  the propose_fix handler receives kwargs for every required field

The test uses mocked Anthropic and mocked investigator handlers, so it
runs fast and deterministically in CI without an API key or a real
example app.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Final verification and CHANGELOG

**Files:**
- Modify: `CHANGELOG.md` — new entry under `[Unreleased]`

- [ ] **Step 9.1: Run the full target test suite**

```bash
pytest tests/unit/test_agent_core.py tests/unit/test_agent_parser.py tests/unit/test_agent_tool_use.py tests/integration/test_agent_investigator_tool_use.py -v
```
Expected: all pass. Count should be existing test_agent_core.py count + 24 (parser) + 11 (tool_use) + 2 (integration) = 37 new tests.

- [ ] **Step 9.2: Run the broader related test suite for regressions**

```bash
pytest tests/unit/test_agent_core.py tests/unit/test_agent_parser.py tests/unit/test_agent_tool_use.py tests/unit/test_agent_discovery.py tests/unit/fitness/ tests/integration/test_agent_investigator_tool_use.py -v 2>&1 | tail -40
```
Expected: all pass.

- [ ] **Step 9.3: Run full lint and type check gate**

```bash
ruff check src/ tests/ --fix
ruff format src/ tests/
mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp --ignore-missing-imports --exclude 'eject'
mypy src/dazzle_back/ --ignore-missing-imports
```
Expected: all pass, no errors.

- [ ] **Step 9.4: Add CHANGELOG entry**

Open `CHANGELOG.md`. Under the `## [Unreleased]` heading (which should currently be empty after the v0.54.5 ship in the previous session), add:

```markdown
## [Unreleased]

### Fixed
- **DazzleAgent bug 5a (prose-before-JSON parse failure).** Claude 4.6
  frequently emits reasoning prose before JSON action blocks. The strict
  `json.loads` parser returned DONE/failure on any prose prefix, killing
  missions at step 1 (cycle 147's EXPLORE stagnation was caused by this).
  `_parse_action` is refactored as a three-tier fallback: (1) try
  `json.loads` on the whole response, (2) extract the first balanced
  JSON object via a new `_extract_first_json_object` bracket counter
  and preserve the surrounding prose in the action's `reasoning` field,
  (3) return a DONE sentinel with diagnostic if no balanced JSON found.
  Fixes bug 5a on all text-protocol paths (direct SDK and MCP sampling).

### Added
- **DazzleAgent `use_tool_calls` kwarg.** Opt-in flag that routes agent
  decisions through Anthropic's native tool use API when running on the
  direct SDK path. Fixes bug 5b (nested-JSON-in-tool-values encoding)
  for tools with nested input shapes. When combined with an
  `mcp_session`, logs a one-shot warning and falls back to the text
  protocol (MCP sampling is text-only). Currently enabled only for the
  investigator's `propose_fix` terminal action; all other missions
  keep the default `use_tool_calls=False` and use the now-robust text
  parser.
- **Investigator `propose_fix` native tool use.** The investigator
  runner now constructs `DazzleAgent(use_tool_calls=True)`, and the
  `propose_fix` schema is extracted into a module-level
  `PROPOSE_FIX_SCHEMA` constant with full item constraints on the
  `fixes` array (required `file_path`, `diff`, `rationale`,
  `confidence` on each fix). Anthropic's API enforces the shape at the
  tool_use boundary, eliminating the stringified-JSON-in-string
  reliability problem.

### Agent Guidance
- **Authoring new agent tools:** every `AgentTool` already has a
  required `schema` field. For tools used on the text protocol, the
  schema is informational (appears in the system prompt). For tools
  used with `use_tool_calls=True`, the schema becomes Anthropic's
  `input_schema` and is enforced at the API boundary. When a tool has
  a nested input structure (arrays of objects, etc.), tighten the
  schema's item constraints and flip `use_tool_calls=True` on the
  agent — the text protocol's nested-JSON encoding is unreliable
  under Claude 4.6 (bug 5b).
- **Reasoning preservation principle:** the raw LLM output (prose
  preambles, scratch notes, the JSON's `reasoning` field, text blocks
  on the tool-use path) all land in `AgentAction.reasoning` with a
  `[PROSE]` marker where appropriate. Downstream analysis tasks can
  extract human-readable justifications from this corpus later. Do
  not strip prose from the reasoning field — it is signal, not noise.
```

- [ ] **Step 9.5: Commit the CHANGELOG update**

```bash
git add CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs(changelog): bug 5a parser fix + bug 5b tool use opt-in

Record the DazzleAgent robust parser refactor and the optional
Anthropic tool use code path under [Unreleased]. These unblock
autonomous cycle operation past the cycle 188 valley.

Agent guidance section documents the new tool-authoring contract
(use_tool_calls=True for nested schemas) and the reasoning-preservation
principle.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 9.6: Final clean-worktree check**

```bash
git status
```
Expected: clean working tree, no unstaged changes.

```bash
git log --oneline -10
```
Expected: 9 commits added by this plan (tasks 1-9) plus whatever was there before.

---

## Self-review

After completing all 9 tasks, verify the following checklist holds:

**Spec coverage:**
- [x] Section 1 (Goal) — fixes bug 5a and bug 5b, ships infrastructure + investigator migration. Covered by tasks 1-8.
- [x] Section 2 (Design philosophy) — continuity, reasoning preservation, economics. All three principles land in code comments.
- [x] Section 4.1 (parser refactor) — task 2.
- [x] Section 4.2 (`_extract_first_json_object`) — task 1.
- [x] Section 4.3 (`_decide` three-way branch) — task 5.
- [x] Section 4.4 (`_decide_via_anthropic_tools`) — task 6.
- [x] Section 5.1 (`AgentTool.input_schema`) — N/A, deviation documented at plan top; existing `schema` field is used.
- [x] Section 5.5 (prompt hardening) — N/A, deviation documented at plan top; already in the existing prompt.
- [x] Section 8 (testing) — 37 new tests across tasks 1-8.
- [x] Section 8.5 (cycle 147 regression test) — task 3.
- [x] Section 9.1 (investigator schema) — task 7.
- [x] Section 9.2 (no migration of other missions) — no task; default `use_tool_calls=False` unchanged for other missions.
- [x] Section 12 (success criteria) — tasks 2, 3, 6, 8 exercise the specific criteria; task 9 runs mypy and ruff.

**Type consistency:** verified — `AgentTool.schema` used consistently; `AgentAction.value` is `str` throughout; `tool_use_block.input` is `dict`; `json.dumps` / `json.loads` round-trip preserves data.

**No placeholders:** each step has actual code or exact commands.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-14-dazzle-agent-robust-parser-and-tool-use-plan.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration in this session. Uses the `superpowers:subagent-driven-development` skill. Good for 9 discrete tasks with well-defined boundaries.

2. **Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review.

**Which approach?**
