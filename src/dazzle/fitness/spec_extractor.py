"""Spec extractor — reads spec.md and produces Capability records.

Pass 2a-A of the Agent-Led Fitness Methodology: extracts discrete
jobs-to-be-done from ``spec.md`` via the LLM facade. No DSL access — the
spec_extractor only sees the spec text. Structural independence from the
adversary is enforced by input-scoping at construction time.

LLM interface: uses a sync ``_LlmClient`` Protocol that matches
``dazzle.llm.LLMAPIClient.complete(system_prompt, user_prompt)``. Tests
pass a ``unittest.mock.Mock`` — the engine (Task 19) is the only caller
that instantiates the real client.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Capability:
    """One capability asserted in the spec (persona + action).

    ``capability`` is a short imperative phrase ("triage incoming ticket").
    ``persona`` is the role name from the spec ("support_agent"). Both are
    compared case-insensitively downstream.
    """

    capability: str
    persona: str


class _LlmClient(Protocol):
    """Minimal protocol matching ``dazzle.llm.LLMAPIClient.complete``."""

    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


_SYSTEM_PROMPT = """You are an analyst reading a product spec. Extract the \
discrete jobs-to-be-done (capabilities) this spec describes, and the persona \
who performs each.

Return ONLY a JSON array. Each element must be:
  {"capability": "<short verb phrase>", "persona": "<role name>"}

DO NOT include any other commentary — no prose, no code fences, no keys other \
than "capability" and "persona"."""


def extract_spec_capabilities(spec_path: Path, llm: _LlmClient) -> list[Capability]:
    """Extract capabilities from a spec.md file.

    Malformed JSON, non-list responses, and items missing required fields
    are silently dropped; the caller treats empty output as "no signal".
    """
    user_prompt = spec_path.read_text()
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
