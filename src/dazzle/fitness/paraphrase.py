"""Paraphrase subsystem skeleton (v1 task 18).

v1 ships the interface only; the full founder-facing UX (``story_review``
+ ``spec_revision`` loop) lands in v1.1. Having the skeleton in place now
lets the corrector route ``spec_stale`` findings through paraphrase
without blocking on the UX wiring.

LLM interface: sync ``_LlmClient`` Protocol mirroring
``dazzle.llm.LLMAPIClient.complete(system_prompt, user_prompt)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from dazzle.fitness.models import Finding

ParaphraseKind = Literal["story_review", "spec_revision"]


@dataclass(frozen=True)
class ParaphraseRequest:
    """A prompt-ready paraphrase request for founder-facing UX."""

    kind: ParaphraseKind
    prompt: str
    target_finding_id: str | None


class _LlmClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


_STORY_PARAPHRASE_SYSTEM_PROMPT = (
    "Paraphrase user stories in plain English, using NO technical or "
    "framework vocabulary. Start the paraphrase with 'When...' or 'You "
    "want to...'. Return only the paraphrase — no prose commentary."
)


def build_spec_revision_prompt(finding: Finding) -> ParaphraseRequest:
    """Build a Recognition-not-Generation prompt for a spec_stale finding.

    Pure Python — no LLM call. The corrector's ``spec_stale`` path hands
    the resulting ``ParaphraseRequest`` to the UX layer (v1.1) which then
    walks the founder through confirm / reject / correct.
    """
    prompt = (
        "Based on how the app is being used, it looks like you actually want:\n\n"
        f"  {finding.capability_ref}\n\n"
        f"Your spec currently implies: {finding.expected}\n\n"
        "Should the spec be updated to reflect the observed behaviour? "
        "Answer with 'confirm', 'reject', or a one-line correction."
    )
    return ParaphraseRequest(
        kind="spec_revision",
        prompt=prompt,
        target_finding_id=finding.id,
    )


def paraphrase_story(story: Any, llm: _LlmClient) -> str:
    """Generate a plain-English paraphrase of a DSL story for founder review."""
    title = getattr(story, "title", "(untitled)")
    steps = getattr(story, "steps", [])
    steps_str = "\n".join(f"  - {s}" for s in steps)

    user_prompt = f"Story: {title}\nSteps:\n{steps_str}\n"
    return llm.complete(
        system_prompt=_STORY_PARAPHRASE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
