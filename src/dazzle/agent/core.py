"""
DazzleAgent: mission-agnostic agent framework.

Give it a mission (system prompt + tools + completion criteria),
an observer (how to see the page), and an executor (how to act).
It runs autonomously until the mission is complete.

This is explicitly a frontier-model-piloted system. Non-deterministic
by design. The agent's effectiveness depends on the quality of its
mission prompt and the model's reasoning capability.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .executor import Executor
from .models import ActionResult, ActionType, AgentAction, PageState, Step
from .observer import Observer
from .transcript import AgentTranscript, Observation

logger = logging.getLogger("dazzle.agent.core")


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


# =============================================================================
# Mission Definition
# =============================================================================


@dataclass
class AgentTool:
    """A tool the agent can invoke beyond page actions."""

    name: str
    description: str
    schema: dict[str, Any]
    handler: Callable[..., Any]


# Type alias for completion check function
CompletionFn = Callable[[AgentAction, list[Step]], bool]


def _default_completion(action: AgentAction, history: list[Step]) -> bool:
    """Default: stop when agent says DONE."""
    return action.type == ActionType.DONE


# ---------------------------------------------------------------------------
# Builtin page actions as native SDK tools (use_tool_calls=True path)
#
# Before cycle 194: DazzleAgent's tool-use path exposed mission tools as
# native Anthropic tools but left page actions (navigate/click/type/...) as
# text-protocol JSON instructions in the system prompt. The LLM, obediently
# emitting a navigate action as text, left the tool-use path with a
# text-only response which was treated as DONE, stopping the agent after
# 1 step. See dev_docs/ux-log.md cycle 193 for the full diagnosis.
#
# Cycle 194 fix: declare page actions as synthetic SDK tools so the
# tools=[...] parameter carries the full action contract uniformly. The
# LLM selects one via a tool_use block, and _tool_use_to_action routes
# builtin names back to the appropriate ActionType. Mission tools coexist
# in the same list — name collisions are resolved by giving builtin names
# priority (enforced in _tool_use_to_action).
# ---------------------------------------------------------------------------

_BUILTIN_ACTION_NAMES: frozenset[str] = frozenset(
    {"navigate", "click", "type", "select", "scroll", "wait", "assert", "done"}
)


def _builtin_action_tools() -> list[dict[str, Any]]:
    """Return the page-action tool schemas in SDK-ready shape."""
    return [
        {
            "name": "navigate",
            "description": (
                "Navigate the browser to a URL or server-relative path "
                "(e.g. '/app/contacts'). Use to explore new pages."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Absolute URL or server-relative path",
                    },
                    "reasoning": {"type": "string"},
                },
                "required": ["target"],
            },
        },
        {
            "name": "click",
            "description": "Click an element matching the given CSS selector.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "CSS selector"},
                    "reasoning": {"type": "string"},
                },
                "required": ["target"],
            },
        },
        {
            "name": "type",
            "description": "Type text into an input element matching the given CSS selector.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "CSS selector"},
                    "value": {"type": "string", "description": "Text to type"},
                    "reasoning": {"type": "string"},
                },
                "required": ["target", "value"],
            },
        },
        {
            "name": "select",
            "description": "Choose an option from a <select> element.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "CSS selector"},
                    "value": {"type": "string", "description": "Option value or label"},
                    "reasoning": {"type": "string"},
                },
                "required": ["target", "value"],
            },
        },
        {
            "name": "scroll",
            "description": "Scroll the page to reveal more content.",
            "input_schema": {
                "type": "object",
                "properties": {"reasoning": {"type": "string"}},
            },
        },
        {
            "name": "wait",
            "description": "Wait for an element to appear before continuing.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "CSS selector"},
                    "reasoning": {"type": "string"},
                },
                "required": ["target"],
            },
        },
        {
            "name": "assert",
            "description": "Assert that a condition or element is present on the page.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "What to check (selector or description)",
                    },
                    "reasoning": {"type": "string"},
                },
                "required": ["target"],
            },
        },
        {
            "name": "done",
            "description": (
                "Signal that the mission is complete or cannot proceed further. "
                "Use only when all goals are met or progress is impossible."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "success": {
                        "type": "boolean",
                        "description": "Whether the mission succeeded",
                    },
                    "reasoning": {"type": "string", "description": "Summary"},
                },
            },
        },
    ]


def _tool_use_to_action(block: Any, reasoning: str) -> AgentAction:
    """Convert an SDK tool_use block to an ``AgentAction``.

    Builtin page-action names (navigate/click/type/...) map to the
    matching ``ActionType``. All other tool names route to
    ``ActionType.TOOL`` with the block's input serialised as the action's
    ``value``, matching the text-protocol path's shape so
    ``_execute_tool`` can consume it unchanged.

    ``reasoning`` is taken from the tool input when present (LLMs often
    include it in their input payload), otherwise from the caller's
    aggregated text blocks.
    """
    name = block.name
    inputs: dict[str, Any] = dict(block.input) if block.input else {}
    action_reasoning = inputs.pop("reasoning", None) or reasoning

    if name in _BUILTIN_ACTION_NAMES:
        if name == "done":
            return AgentAction(
                type=ActionType.DONE,
                reasoning=action_reasoning,
                success=bool(inputs.get("success", True)),
            )
        return AgentAction(
            type=ActionType(name),
            target=inputs.get("target"),
            value=inputs.get("value"),
            reasoning=action_reasoning,
        )

    # Mission tool — serialise remaining inputs as the value so
    # _execute_tool's existing handler dispatch works unchanged.
    return AgentAction(
        type=ActionType.TOOL,
        target=name,
        value=json.dumps(inputs),
        reasoning=action_reasoning,
    )


# Truncation limits for compressed history rendering (keeps LLM prompt bounded).
_HISTORY_TARGET_MAX_LEN = 40
_HISTORY_MSG_MAX_LEN = 60


def _format_history_line(step: Step) -> str:
    """Render one history step for the LLM's compressed history (cycle 197).

    Reads the cycle-197 ActionResult fields (from_url, to_url,
    state_changed, console_errors_during_action) and renders a line
    that makes state-change status unmissable. Falls back to the legacy
    message format when state_changed is None (tool/HTTP/anonymous paths).
    """
    s = f"{step.step_number}. {step.action.type.value}"
    if step.action.target:
        s += f": {step.action.target[:_HISTORY_TARGET_MAX_LEN]}"
    r = step.result
    if r.error:
        s += f" (ERROR: {r.error[:_HISTORY_MSG_MAX_LEN]})"
    elif r.state_changed is False:
        loc = f"still at {r.to_url}" if r.to_url else "no state change"
        s += f" -> NO state change ({loc})"
    elif r.state_changed is True and r.from_url and r.to_url and r.from_url != r.to_url:
        s += f" -> navigated {r.from_url} → {r.to_url}"
    elif r.state_changed is True:
        s += " -> state changed"
    elif r.message:
        s += f" -> {r.message[:_HISTORY_MSG_MAX_LEN]}"
    if r.console_errors_during_action:
        n = len(r.console_errors_during_action)
        first = r.console_errors_during_action[0][:_HISTORY_MSG_MAX_LEN]
        suffix = "s" if n > 1 else ""
        s += f" [+{n} console error{suffix}: {first}]"
    return s


def _is_stuck(history: list[Step], window: int = 3) -> bool:
    """True iff the last `window` steps all have state_changed=False.

    state_changed=None (tool actions, HTTP path) does NOT count as a
    no-op — tool invocations are legitimate progress even though they
    don't touch the page.
    """
    if len(history) < window:
        return False
    recent = history[-window:]
    return all(s.result.state_changed is False for s in recent)


@dataclass
class Mission:
    """
    What the agent should accomplish.

    A mission is the complete specification for an agent run:
    the system prompt, available tools, completion criteria, and budget.
    """

    name: str
    system_prompt: str
    tools: list[AgentTool] = field(default_factory=list)
    completion_criteria: CompletionFn = _default_completion
    max_steps: int = 30
    token_budget: int = 100_000
    context: dict[str, Any] = field(default_factory=dict)
    start_url: str | None = None


# =============================================================================
# DazzleAgent
# =============================================================================


class DazzleAgent:
    """
    Mission-agnostic agent. Give it a mission, it runs autonomously.

    The agent loop:
    1. Observe current page state
    2. Send state + history to LLM for a decision
    3. Execute the decided action (page action or tool invocation)
    4. Record the step
    5. Check completion criteria
    6. Repeat
    """

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(
        self,
        observer: Observer,
        executor: Executor,
        model: str | None = None,
        api_key: str | None = None,
        mcp_session: Any = None,
        use_tool_calls: bool = False,
    ):
        self._observer = observer
        self._executor = executor
        self._model = model or self.DEFAULT_MODEL
        self._api_key = api_key
        self._mcp_session = mcp_session
        self._use_tool_calls = use_tool_calls
        self._tool_use_warned = False  # one-shot warning latch for MCP+tool_calls path
        self._client: Any = None
        self._history: list[Step] = []
        self._tokens_used = 0

    def _get_client(self) -> Any:
        """Get or create Anthropic client."""
        if self._client is None:
            try:
                import anthropic

                if self._api_key:
                    self._client = anthropic.Anthropic(api_key=self._api_key)
                else:
                    self._client = anthropic.Anthropic()
            except ImportError:
                raise RuntimeError(
                    "anthropic package required for agent. Install with: pip install anthropic"
                )
        return self._client

    async def run(
        self,
        mission: Mission,
        on_step: Callable[[int, Step], None] | None = None,
    ) -> AgentTranscript:
        """
        Execute a mission. Returns full transcript.

        Args:
            mission: The mission specification
            on_step: Optional callback invoked after each step with (step_number, step)

        Returns:
            AgentTranscript with all steps and observations
        """
        self._history = []
        self._tokens_used = 0
        start_time = datetime.now()

        transcript = AgentTranscript(
            mission_name=mission.name,
            model=self._model,
            metadata=mission.context,
        )

        # Navigate to starting point if specified
        if mission.start_url:
            try:
                await self._observer.navigate(mission.start_url)
            except Exception as e:
                transcript.outcome = "error"
                transcript.error = f"Failed to navigate to {mission.start_url}: {e}"
                transcript.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                return transcript

        # Build tool registry for the mission
        tool_registry = {t.name: t for t in mission.tools}

        # Agent loop
        for step_num in range(mission.max_steps):
            step_start = datetime.now()

            # Check token budget
            if self._tokens_used >= mission.token_budget:
                transcript.outcome = "budget_exceeded"
                break

            # 1. Observe
            try:
                state = await self._observer.observe()
            except Exception as e:
                logger.warning("Observer error at step %s: %s", step_num + 1, e)
                transcript.outcome = "error"
                transcript.error = f"Observer error: {e}"
                break

            # 2. Decide
            try:
                action, prompt_text, response_text, step_tokens = await self._decide(
                    mission, state, tool_registry
                )
                self._tokens_used += step_tokens
            except Exception as e:
                logger.warning("LLM error at step %s: %s", step_num + 1, e)
                transcript.outcome = "error"
                transcript.error = f"LLM error at step {step_num + 1}: {e}"
                break

            # 3. Execute
            if action.type == ActionType.TOOL and action.target in tool_registry:
                # Mission-specific tool invocation
                result = await self._execute_tool(tool_registry[action.target], action.value)
                # Check if tool produced observations
                if result.data.get("observation"):
                    transcript.add_observation(Observation(**result.data["observation"]))
            else:
                result = await self._executor.execute(action)

            # 4. Record
            step = Step(
                state=state,
                action=action,
                result=result,
                step_number=step_num + 1,
                duration_ms=(datetime.now() - step_start).total_seconds() * 1000,
                prompt_text=prompt_text,
                response_text=response_text,
                tokens_used=step_tokens,
            )
            self._history.append(step)
            transcript.steps.append(step)

            # Notify caller of progress
            if on_step is not None:
                try:
                    on_step(step_num + 1, step)
                except Exception:
                    pass  # Never let callback errors break the agent loop

            # 5. Check completion
            if mission.completion_criteria(action, self._history):
                transcript.outcome = "completed"
                break

            # Small delay between steps
            await asyncio.sleep(0.3)
        else:
            # Loop exhausted without completion
            if transcript.outcome == "pending":
                transcript.outcome = "max_steps"

        transcript.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        transcript.tokens_used = self._tokens_used
        return transcript

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

        # Build prompt text for transcript (without image data)
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

        Note on ``response_text`` for the transcript: the caller in
        ``_decide`` sets ``response_text = action.reasoning`` on this
        path because the reasoning field contains the concatenated
        text content blocks from the response — this IS the model's
        raw textual output on the tool-use path. The structured
        tool_use block is separately captured as the action itself.
        """
        # Builtin page actions come first so if a mission tool ever collides
        # with one (e.g. a mission declares its own `click`), the builtin wins
        # by SDK-tool-list order. Routing in _tool_use_to_action double-checks
        # the name against _BUILTIN_ACTION_NAMES so this is belt + braces.
        tools: list[dict[str, Any]] = _builtin_action_tools()
        builtin_names = _BUILTIN_ACTION_NAMES
        for tool in tool_registry.values():
            if tool.name in builtin_names:
                logger.warning(
                    "mission tool name %r collides with a builtin page action; "
                    "the builtin will take precedence in tool_use routing",
                    tool.name,
                )
                continue
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.schema,
                }
            )

        client = self._get_client()
        create_kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 2000,
            "system": system_prompt,
            "messages": messages,
            "tools": tools,
        }

        response = client.messages.create(**create_kwargs)

        # Extract token usage
        tokens = 0
        if hasattr(response, "usage"):
            tokens = (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)

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

        return (_tool_use_to_action(tool_use_block, reasoning), tokens)

    def _decide_via_anthropic(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
    ) -> tuple[str, int]:
        """Request a completion via the Anthropic SDK (direct API key)."""
        client = self._get_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=800,
            system=system_prompt,
            messages=messages,
        )

        tokens = 0
        if hasattr(response, "usage"):
            tokens = (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)

        response_text = response.content[0].text.strip()
        return response_text, tokens

    async def _decide_via_sampling(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
    ) -> tuple[str, int]:
        """Request a completion via MCP sampling (host-provided LLM).

        This is used when running inside an MCP server (e.g. Claude Code)
        where no API key is available. The host client provides completions
        through the MCP sampling protocol.
        """
        from mcp.types import SamplingMessage, TextContent

        sampling_messages: list[SamplingMessage] = []
        for msg in messages:
            content = msg["content"]
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                # Extract text parts, skip images (MCP sampling is text-only)
                text_parts = [p["text"] for p in content if p.get("type") == "text"]
                text = "\n".join(text_parts)
            else:
                text = str(content)

            sampling_messages.append(
                SamplingMessage(
                    role=msg["role"],
                    content=TextContent(type="text", text=text),
                )
            )

        result = await self._mcp_session.create_message(
            messages=sampling_messages,
            max_tokens=800,
            system_prompt=system_prompt,
        )

        # Extract text from the response
        if hasattr(result.content, "text"):
            response_text = result.content.text.strip()
        else:
            response_text = str(result.content).strip()

        # MCP sampling doesn't report token usage
        return response_text, 0

    def _build_system_prompt(
        self,
        mission: Mission,
        tool_registry: dict[str, AgentTool],
    ) -> str:
        """Build the full system prompt from mission + tools.

        Under ``use_tool_calls=True`` (SDK native tool use), page actions
        and mission tools are carried by the SDK ``tools=[...]`` parameter,
        not by text instructions. The system prompt is kept to the
        mission description plus a terse nudge to use tool calls. This
        prevents the cycle-193 bug where the text-protocol action
        reference caused the model to emit navigation as text JSON,
        leaving the tool-use path with no tool_use block.

        Under ``use_tool_calls=False`` (legacy text-protocol path), the
        system prompt includes the full text-protocol action reference
        unchanged.
        """
        parts = [mission.system_prompt]

        if self._use_tool_calls:
            # Native tool-use path: tools list is the contract. No text
            # instructions needed — explicit brief reminder only.
            parts.append(
                "\n## How to act\n"
                "Use the provided tools to navigate, interact with, and inspect the "
                "page, and to record mission-specific findings. Each step must "
                "invoke exactly one tool. When the mission is complete or no "
                "further progress is possible, invoke the `done` tool."
            )
            return "\n".join(parts)

        # Text-protocol path (legacy): include the full action reference.
        if tool_registry:
            parts.append("\n## Mission-Specific Tools")
            parts.append("In addition to page actions, you can invoke these tools:\n")
            for tool in tool_registry.values():
                parts.append(f"- **{tool.name}**: {tool.description}")
                if tool.schema.get("properties"):
                    props = tool.schema["properties"]
                    params = ", ".join(f"{k}: {v.get('type', 'any')}" for k, v in props.items())
                    parts.append(f"  Parameters: {params}")
            parts.append(
                '\nTo invoke a tool, use: {"action": "tool", "target": "tool_name", '
                '"value": "{...tool args as JSON...}", "reasoning": "why"}'
            )

        parts.append("""
## Available Page Actions
Respond with a JSON object for one of these actions:

1. click   - {"action": "click", "target": "selector", "reasoning": "why"}
2. type    - {"action": "type", "target": "selector", "value": "text", "reasoning": "why"}
3. select  - {"action": "select", "target": "selector", "value": "option", "reasoning": "why"}
4. navigate - {"action": "navigate", "target": "/path", "reasoning": "why"}
5. scroll  - {"action": "scroll", "reasoning": "why"}
6. wait    - {"action": "wait", "target": "selector", "reasoning": "why"}
7. assert  - {"action": "assert", "target": "what to check", "reasoning": "why"}
8. done    - {"action": "done", "success": true/false, "reasoning": "summary"}

## CRITICAL OUTPUT FORMAT
Respond with ONLY a single JSON object. No text before or after.
Do NOT use markdown code blocks. Your entire response must be parseable as JSON.""")

        return "\n".join(parts)

    def _build_messages(self, state: PageState) -> list[dict[str, Any]]:
        """Build conversation messages from history + current state."""
        messages: list[dict[str, Any]] = []

        # Add compressed history
        if self._history:
            history_text = "## Previous Actions\n"
            # Show last 5 steps
            for step in self._history[-5:]:
                line = f"{step.step_number}. {step.action.type.value}"
                if step.action.target:
                    line += f": {step.action.target[:40]}"
                if step.result.error:
                    line += f" (ERROR: {step.result.error[:60]})"
                elif step.result.message:
                    line += f" -> {step.result.message[:60]}"
                history_text += line + "\n"

            messages.append({"role": "user", "content": history_text})
            messages.append(
                {"role": "assistant", "content": "I understand. What's the current state?"}
            )

        # Add current state
        content: list[dict[str, Any]] = []

        if state.screenshot_b64:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": state.screenshot_b64,
                    },
                }
            )

        content.append({"type": "text", "text": state.to_prompt()})
        messages.append({"role": "user", "content": content})

        return messages

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
            # Guard: JSON must be an object, not an array/string/number
            if not isinstance(data, dict):
                raise ValueError(f"JSON root is not an object: {type(data).__name__}")
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
                if not isinstance(data, dict):
                    logger.warning(
                        "Parser: tier 2 extracted JSON but root is not an object: %s",
                        type(data).__name__,
                    )
                    return AgentAction(
                        type=ActionType.DONE,
                        success=False,
                        reasoning=f"Extracted JSON root is not an object: {json_substring[:2000]}",
                    )
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
            reasoning = f"{structured_reasoning} [PROSE]: {prose_trimmed}".strip()
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
            value_str = value if isinstance(value, str) else json.dumps(value)
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

    async def _execute_tool(
        self,
        tool: AgentTool,
        value: str | None,
    ) -> ActionResult:
        """Execute a mission-specific tool."""
        try:
            args = json.loads(value) if value else {}
            result = tool.handler(**args)
            # Handle async tool handlers
            if asyncio.iscoroutine(result):
                result = await result

            return ActionResult(
                message=f"Tool {tool.name}: {json.dumps(result)[:200]}",
                data=result if isinstance(result, dict) else {"result": result},
            )
        except Exception as e:
            return ActionResult(
                message=f"Tool {tool.name} failed",
                error=str(e),
            )
