"""Post-5.8 Goal B conversation — design_studio critique trail on review desks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/design_studio/dsl/app.dsl"
FEEDBACK_SEEDS = ROOT / "examples/design_studio/dsl/seeds/demo_data/Feedback.jsonl"
ASSET_SEEDS = ROOT / "examples/design_studio/dsl/seeds/demo_data/Asset.jsonl"
BRAND_SEEDS = ROOT / "examples/design_studio/dsl/seeds/demo_data/Brand.jsonl"
# STABLE_PERSONA_USER_IDS — designer + admin (cycle 1716 acceptance seed pin)
_DESIGNER = "a1000000-0000-4000-8000-00000000000b"
_ADMIN = "a1000000-0000-4000-8000-000000000003"


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


def test_asset_and_brand_seeds_set_created_by_for_creator_hub() -> None:
    """Acceptance dig cycle 1716: blank Created By killed User triple-open on Media Grid.

    Asset list open is ``Asset via id | Brand via brand | User via created_by``;
    brand list dual-opens User via created_by. Seeds must pin stable persona ids.
    """
    assets = [json.loads(line) for line in ASSET_SEEDS.read_text().splitlines() if line.strip()]
    brands = [json.loads(line) for line in BRAND_SEEDS.read_text().splitlines() if line.strip()]
    assert len(assets) >= 8
    assert len(brands) >= 4
    allowed = {_DESIGNER, _ADMIN}
    for row in assets:
        assert row.get("created_by") in allowed, row.get("name")
    for row in brands:
        assert row.get("created_by") in allowed, row.get("name")
    # At least one designer-authored asset so Media Grid shows a real name, not —
    assert any(r.get("created_by") == _DESIGNER for r in assets)
