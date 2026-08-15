"""Post-5.8 Goal B document — design_studio brief/guide composition."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/design_studio/dsl/app.dsl"
DOC_SEEDS = ROOT / "examples/design_studio/dsl/seeds/demo_data/DesignDocument.jsonl"


def _studio_dashboard_block() -> str:
    text = APP.read_text()
    start = text.index('workspace studio_dashboard "Studio Dashboard":')
    end = text.index('workspace asset_catalog "Asset Catalog":', start)
    return text[start:end]


def _review_desk_block() -> str:
    text = APP.read_text()
    start = text.index('workspace review_desk "Review Desk":')
    end = text.index('workspace campaign_desk "Campaigns":', start)
    return text[start:end]


def test_design_document_entity_is_document_composition() -> None:
    text = APP.read_text()
    assert 'entity DesignDocument "Design Document"' in text
    assert "display_field: headline" in text
    assert "headline: str(200) required" in text
    assert (
        "doc_kind: enum[brief, brand_guide, art_direction, creative_spec, decision]=brief" in text
    )
    assert "status: enum[draft, published, archived]=draft" in text
    assert "draft -> published:" in text
    assert "published -> archived:" in text


def test_studio_dashboard_declares_composition_after_dual_attention() -> None:
    """Goal B document: composition on Studio Dashboard before critique trail."""
    block = _studio_dashboard_block()
    assert "composition:" in block
    assert "source: DesignDocument" in block
    assert "documents: count(DesignDocument)" in block
    assert "action: design_document_detail" in block
    # Order: dual attention → documents → conversation
    assert block.index("draft_pressure:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")
    assert (
        "focus: media_shelf, portfolio, review_pressure, draft_pressure, composition, "
        "live_conversation" in block
    )


def test_review_desk_declares_composition_after_dual_attention() -> None:
    block = _review_desk_block()
    assert "composition:" in block
    assert "source: DesignDocument" in block
    assert "documents: count(DesignDocument)" in block
    assert block.index("draft_queue:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")
    assert "focus: review_pixels, approved_pixels, awaiting_review, draft_queue" in block


def test_design_document_list_dual_open_and_brand_hub() -> None:
    text = APP.read_text()
    assert 'surface design_document_list "Design Documents"' in text
    assert "open: DesignDocument via id | Brand via brand" in text
    assert 'surface design_document_detail "Design Document"' in text
    assert 'related documents "Documents"' in text
    assert "show: DesignDocument" in text


def test_design_document_seeds_are_domain_true_headlines() -> None:
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 12, "Goal B document expects composition lines across brands"
    kinds = set()
    statuses = set()
    for row in rows:
        headline = str(row["headline"])
        assert len(headline) >= 16, headline
        assert " " in headline, f"headline should be human prose, not slug: {headline}"
        assert str(row["brand"]).startswith("4d000000-")
        assert str(row["id"]).startswith("5f000000-")
        assert len(str(row.get("body") or "")) >= 24
        kinds.add(row["doc_kind"])
        statuses.add(row["status"])
    assert kinds >= {"brief", "brand_guide", "art_direction", "creative_spec", "decision"}
    assert statuses >= {"draft", "published"}
