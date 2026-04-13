"""Tests for spec_extractor (v1 task 8).

Uses a sync ``Mock`` with ``.complete(system_prompt, user_prompt)`` to match
the real ``dazzle.llm.LLMAPIClient`` facade.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from dazzle.fitness.spec_extractor import Capability, extract_spec_capabilities


def test_extract_returns_capability_list(tmp_path: Path) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text(
        "# Support System\n\n"
        "My team needs to triage tickets quickly.\n"
        "When a customer emails support, the ticket goes to whoever's on rotation.\n"
        "Once resolved, the assignee writes a resolution note.\n"
    )

    fake_llm = Mock()
    fake_llm.complete.return_value = (
        '[{"capability": "triage incoming ticket", "persona": "support_agent"},'
        ' {"capability": "resolve ticket with notes", "persona": "support_agent"}]'
    )

    caps = extract_spec_capabilities(spec, llm=fake_llm)

    assert len(caps) == 2
    assert caps[0] == Capability(capability="triage incoming ticket", persona="support_agent")
    assert caps[1] == Capability(capability="resolve ticket with notes", persona="support_agent")
    assert fake_llm.complete.call_count == 1
    # User prompt should carry the spec text
    call = fake_llm.complete.call_args
    assert "triage tickets" in call.kwargs["user_prompt"]


def test_extract_returns_empty_list_on_malformed_json(tmp_path: Path) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text("irrelevant")

    fake_llm = Mock()
    fake_llm.complete.return_value = "this is not json"

    caps = extract_spec_capabilities(spec, llm=fake_llm)
    assert caps == []
