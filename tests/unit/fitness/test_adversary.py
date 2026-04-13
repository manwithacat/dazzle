"""Tests for adversary (v1 task 9).

Structural independence: the adversary must see only DSL stories, never
spec.md. These tests assert on the ``Mock.complete`` call_args to verify
the user prompt contains no spec-file references.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

from dazzle.fitness.adversary import synthesize_from_stories
from dazzle.fitness.spec_extractor import Capability


class _StoryStub:
    def __init__(self, id: str, title: str, persona: str, steps: list[str]) -> None:
        self.id = id
        self.title = title
        self.persona = persona
        self.steps = steps


def test_adversary_receives_only_stories() -> None:
    stories = [
        _StoryStub("s1", "Triage new ticket", "support_agent", ["open queue"]),
        _StoryStub("s2", "Resolve with notes", "support_agent", ["click resolve"]),
    ]
    fake_llm = Mock()
    fake_llm.complete.return_value = json.dumps(
        [
            {"capability": "triage", "persona": "support_agent"},
            {"capability": "resolve", "persona": "support_agent"},
        ]
    )

    caps = synthesize_from_stories(stories, llm=fake_llm)

    assert len(caps) == 2
    assert isinstance(caps[0], Capability)
    assert caps[0].capability == "triage"
    assert fake_llm.complete.called

    # Structural independence: user prompt must NOT mention spec.md
    call = fake_llm.complete.call_args
    user_prompt = call.kwargs["user_prompt"]
    system_prompt = call.kwargs["system_prompt"]
    assert "spec.md" not in user_prompt
    assert "spec.md" not in system_prompt
    assert "Triage new ticket" in user_prompt


def test_adversary_handles_empty_story_list() -> None:
    fake_llm = Mock()
    caps = synthesize_from_stories([], llm=fake_llm)
    assert caps == []
    fake_llm.complete.assert_not_called()
