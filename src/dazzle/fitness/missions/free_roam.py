"""Pass 2b mission builder — free-roam behavioural proxy.

Constructs a real :class:`dazzle.agent.core.Mission` carrying:

1. Persona context in the system prompt
2. High-level intent
3. EXPECT/ACTION/OBSERVE protocol instructions
4. Step budget

The returned Mission is deliberately tool-less at this layer. The fitness
engine is responsible for attaching interlocked tools to the
:class:`DazzleAgent` at construction time; this builder only shapes the
prompt and budget.
"""

from __future__ import annotations

from typing import Any

from dazzle.agent.core import Mission

_SYSTEM_PROMPT_TEMPLATE = """You are acting as a human proxy for the following \
persona: {persona_id}.

Your goal: {intent}

You must follow the EXPECT / ACTION / OBSERVE protocol strictly:

  1. EXPECT — before EVERY tool call, state what you expect to happen in
     natural language. Keep it to one sentence. This is the `expect`
     field on the tool call.
  2. ACTION — then call the tool.
  3. OBSERVE — after the call, observe what actually happened. Compare to
     your expectation. If they differ, that is a signal worth recording.

The system will REJECT tool calls that are not preceded by an `expect`
statement. Do not try to work around this — emit the expectation first.

Step budget: {step_budget}. Use it efficiently.
"""


def build_free_roam_mission(
    persona: Any,
    intent: str,
    step_budget: int,
) -> Mission:
    """Build a free-roam :class:`Mission` for a given persona and intent."""
    persona_id = getattr(persona, "id", None) or getattr(persona, "name", None) or "unknown"
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        persona_id=persona_id,
        intent=intent,
        step_budget=step_budget,
    )
    return Mission(
        name=f"fitness.free_roam.{persona_id}",
        system_prompt=system_prompt,
        tools=[],
        max_steps=step_budget,
        context={"persona_id": persona_id, "intent": intent},
    )
