"""Post-5.8 Goal B conversation — design_studio critique trail on review desks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/design_studio/dsl/app.dsl"
FEEDBACK_SEEDS = ROOT / "examples/design_studio/dsl/seeds/demo_data/Feedback.jsonl"


def test_feedback_display_field_is_comment() -> None:
    text = APP.read_text()
    assert "entity Feedback" in text
    assert "display_field: comment" in text
    assert "comment: text required" in text


def test_review_desk_declares_live_conversation_spine() -> None:
    text = APP.read_text()
    assert "workspace review_desk" in text
    assert "live_conversation:" in text
    assert "source: Feedback" in text
    # Metrics include conversation count so buyer pressure is visible
    assert "conversation: count(Feedback)" in text
    # Studio home also carries the trail (designer default desk)
    assert "workspace studio_dashboard" in text


def test_feedback_seeds_have_domain_true_critique_copy() -> None:
    rows = [json.loads(line) for line in FEEDBACK_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 8
    for row in rows:
        comment = str(row.get("comment") or "")
        assert len(comment) >= 24, comment
        assert " " in comment
