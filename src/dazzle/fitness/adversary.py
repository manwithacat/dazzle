"""Adversarial re-reader — Pass 2a-C.

Structural independence: the adversary reads ONLY the DSL story list.
It NEVER sees ``spec.md``, founder intent, or any other context. This
forces the two sensors (spec_extractor + adversary) to be structurally
independent inputs to the Jaccard guardrail in ``independence.py``.

LLM interface mirrors ``spec_extractor``: a sync ``_LlmClient`` Protocol
matching ``dazzle.llm.LLMAPIClient.complete(system_prompt, user_prompt)``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Protocol

from dazzle.fitness.spec_extractor import Capability


class _LlmClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


_SYSTEM_PROMPT = """You are an adversarial re-reader. You have access to ONLY \
this list of user stories — no product brief, no founder intent, nothing else.

Infer what this application is trying to do. What discrete jobs-to-be-done \
(capabilities) do these stories collectively imply? Assume nothing you cannot \
derive from the stories themselves.

Return ONLY a JSON array:
  [{"capability": "<phrase>", "persona": "<role>"}]

No prose, no code fences, no extra keys."""


def _render_stories(stories: Sequence[Any]) -> str:
    lines: list[str] = []
    for s in stories:
        sid = getattr(s, "id", "?")
        title = getattr(s, "title", "(untitled)")
        persona = getattr(s, "persona", "?")
        steps = getattr(s, "steps", [])
        lines.append(f"- [{sid}] {title} (persona={persona})")
        for step in steps:
            lines.append(f"    - {step}")
    return "\n".join(lines)


def synthesize_from_stories(stories: Sequence[Any], llm: _LlmClient) -> list[Capability]:
    """Infer capabilities from a story list alone.

    Returns ``[]`` without calling the LLM when ``stories`` is empty —
    the adversary has nothing to adversarially re-read. Malformed LLM
    output also collapses to ``[]``.
    """
    if not stories:
        return []

    user_prompt = _render_stories(stories)
    response = llm.complete(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )

    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []

    out: list[Capability] = []
    for item in parsed:
        if (
            isinstance(item, dict)
            and isinstance(item.get("capability"), str)
            and isinstance(item.get("persona"), str)
        ):
            out.append(
                Capability(
                    capability=item["capability"],
                    persona=item["persona"],
                )
            )
    return out
