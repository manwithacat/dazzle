"""Post-5.8 Goal B document — contact_manager engagement-letter composition."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/contact_manager/dsl/app.dsl"
SIGNING = ROOT / "examples/contact_manager/dsl/signing.dsl"
DOC_SEEDS = ROOT / "examples/contact_manager/demo_data/EngagementLetter.jsonl"


def _home_block() -> str:
    text = APP.read_text()
    start = text.index('workspace home "Home":')
    end = text.index('workspace contacts "Contacts":', start)
    return text[start:end]


def test_engagement_letter_entity_is_document_composition() -> None:
    text = SIGNING.read_text()
    assert 'entity EngagementLetter "Engagement Letter"' in text
    assert "display_field: scope_summary" in text
    assert "scope_summary: text required" in text
    assert "status: enum[draft,sent,signed,void]=draft" in text


def test_home_declares_composition_after_dual_attention() -> None:
    """Goal B document: composition on Home after favourites before notes trail."""
    block = _home_block()
    assert "composition:" in block
    assert "source: EngagementLetter" in block
    assert "documents: count(EngagementLetter)" in block
    assert "action: engagement_letter_detail" in block
    # Order: dual attention (favourites) → documents → conversation
    assert block.index("favourite_contacts:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")
    assert (
        "focus: media_shelf, directory_stats, engagement_docs, favourite_contacts, composition, "
        "live_conversation, practice_context" in block
    )


def test_engagement_letter_list_dual_open_and_contact_hub() -> None:
    text = APP.read_text() + "\n" + SIGNING.read_text()
    assert 'surface engagement_letter_list "Engagement letters"' in text
    assert "open: EngagementLetter via id | Contact via contact" in text
    assert 'surface engagement_letter_detail "Engagement letter"' in text
    assert 'related engagements "Engagement letters"' in text
    assert "show: EngagementLetter" in text


def test_engagement_letter_seeds_are_domain_true_titles() -> None:
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 12, "Goal B document expects composition lines across contacts"
    statuses = set()
    for row in rows:
        title = str(row["scope_summary"])
        assert len(title) >= 16, title
        assert " " in title, f"scope_summary should be human prose, not slug: {title}"
        assert str(row["id"]).startswith("e7000000-")
        assert row.get("contact")
        assert len(str(row.get("party") or "")) >= 3
        statuses.add(row["status"])
    assert statuses >= {"draft", "sent"}
