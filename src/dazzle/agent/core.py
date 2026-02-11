"""
DazzleAgent: mission-agnostic agent framework.

Give it a mission (system prompt + tools + completion criteria),
an observer (how to see the page), and an executor (how to act).
It runs autonomously until the mission is complete.

This is explicitly a frontier-model-piloted system. Non-deterministic
by design. The agent's effectiveness depends on the quality of its
mission prompt and the model's reasoning capability.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .executor import Executor
from .models import ActionResult, ActionType, AgentAction, PageState, Step
from .observer import Observer
from .transcript import AgentTranscript, Observation

logger = logging.getLogger("dazzle.agent.core")


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
    ):
        self._observer = observer
        self._executor = executor
        self._model = model or self.DEFAULT_MODEL
        self._api_key = api_key
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
                logger.warning(f"Observer error at step {step_num + 1}: {e}")
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
                logger.warning(f"LLM error at step {step_num + 1}: {e}")
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

        Returns:
            (action, prompt_text, response_text, tokens_used)
        """
        system_prompt = self._build_system_prompt(mission, tool_registry)
        messages = self._build_messages(state)

        # Build prompt text for transcript (without image data)
        prompt_text = f"## System\n{system_prompt[:500]}...\n\n{state.to_prompt()}"

        client = self._get_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=800,
            system=system_prompt,
            messages=messages,
        )

        # Track token usage
        tokens = 0
        if hasattr(response, "usage"):
            tokens = (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)

        response_text = response.content[0].text.strip()
        action = self._parse_action(response_text, tool_registry)

        return action, prompt_text, response_text, tokens

    def _build_system_prompt(
        self,
        mission: Mission,
        tool_registry: dict[str, AgentTool],
    ) -> str:
        """Build the full system prompt from mission + tools."""
        parts = [mission.system_prompt]

        # Add tool descriptions if any
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

        # Add action reference
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
        """Parse LLM response into an AgentAction."""
        try:
            # Handle markdown code blocks
            if "```" in response:
                match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
                if match:
                    response = match.group(1)

            data = json.loads(response)
            action_str = data.get("action", "done")

            # Handle tool actions
            if action_str == "tool":
                return AgentAction(
                    type=ActionType.TOOL,
                    target=data.get("target"),
                    value=json.dumps(data.get("value", {}))
                    if isinstance(data.get("value"), dict)
                    else data.get("value"),
                    reasoning=data.get("reasoning", ""),
                )

            action_type = ActionType(action_str)
            return AgentAction(
                type=action_type,
                target=data.get("target"),
                value=data.get("value"),
                reasoning=data.get("reasoning", ""),
                success=data.get("success", True),
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse action: {e}, response: {response[:200]}")
            return AgentAction(
                type=ActionType.DONE,
                success=False,
                reasoning=f"Failed to parse LLM response: {response[:100]}",
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
