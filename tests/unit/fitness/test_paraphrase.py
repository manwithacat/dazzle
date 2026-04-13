"""Tests for paraphrase skeleton (v1 task 18)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock

from dazzle.fitness.models import EvidenceEmbedded, Finding
from dazzle.fitness.paraphrase import (
    ParaphraseRequest,
    build_spec_revision_prompt,
    paraphrase_story,
)


def _finding(locus: str) -> Finding:
    return Finding(
        id="F",
        created=datetime(2026, 4, 13, tzinfo=UTC),
        run_id="r",
        cycle=None,
        axis="coverage",
        locus=locus,  # type: ignore[arg-type]
        severity="low",
        persona="agent",
        capability_ref="story:export_csv",
        expected="Spec clause for export_csv",
        observed="No matching spec clause",
        evidence_embedded=EvidenceEmbedded({}, [], []),
        disambiguation=False,
        low_confidence=False,
        status="PROPOSED",
        route="soft",
        fix_commit=None,
        alternative_fix=None,
    )


def test_build_spec_revision_prompt_contains_finding_details() -> None:
    f = _finding(locus="spec_stale")
    request: ParaphraseRequest = build_spec_revision_prompt(f)
    assert isinstance(request, ParaphraseRequest)
    assert "export_csv" in request.prompt
    assert request.kind == "spec_revision"
    assert request.target_finding_id == "F"


def test_paraphrase_story_returns_plain_english_summary() -> None:
    fake_llm = Mock()
    fake_llm.complete.return_value = "When a customer emails, you want to triage quickly."

    class _Story:
        id = "s1"
        title = "triage_ticket"
        steps = ["open queue", "click triage"]

    summary = paraphrase_story(_Story(), llm=fake_llm)

    assert "triage" in summary.lower()
    assert fake_llm.complete.call_count == 1
    # The story details should be present in the user prompt
    call = fake_llm.complete.call_args
    assert "triage_ticket" in call.kwargs["user_prompt"]
