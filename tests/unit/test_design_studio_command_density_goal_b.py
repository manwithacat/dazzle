"""Post-5.8 Goal B command_density — design_studio dual attention (cycle 1836)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/design_studio/dsl/app.dsl"


def _workspace_block(name: str, end_marker: str) -> str:
    text = APP.read_text()
    start = text.index(f'workspace {name} "')
    end = text.index(end_marker, start + 1)
    return text[start:end]


def _studio_dashboard_block() -> str:
    return _workspace_block("studio_dashboard", 'workspace asset_catalog "')


def _review_desk_block() -> str:
    return _workspace_block("review_desk", 'workspace campaign_desk "')


def test_studio_dashboard_dual_attention_before_conversation() -> None:
    """Peer creative ops dens put ≥2 pressure queues above critique trail.

    Order: media → metrics → review_pressure → draft_pressure → conversation.
    """
    block = _studio_dashboard_block()
    assert "media_shelf:" in block
    assert "portfolio:" in block
    assert "review_pressure:" in block
    assert "draft_pressure:" in block
    assert "live_conversation:" in block
    assert block.index("media_shelf:") < block.index("portfolio:")
    assert block.index("portfolio:") < block.index("review_pressure:")
    assert block.index("review_pressure:") < block.index("draft_pressure:")
    assert block.index("draft_pressure:") < block.index("live_conversation:")
    assert "Multi-panel" in block or "multi-panel" in block.lower()
    assert (
        "focus: media_shelf, portfolio, review_pressure, draft_pressure, live_conversation" in block
    )


def test_review_desk_dual_attention_before_conversation() -> None:
    """Reviewer home: awaiting + draft dual attention before critique trail."""
    block = _review_desk_block()
    assert "review_load:" in block
    assert "awaiting_review:" in block
    assert "draft_queue:" in block
    assert "live_conversation:" in block
    assert block.index("review_load:") < block.index("awaiting_review:")
    assert block.index("awaiting_review:") < block.index("draft_queue:")
    assert block.index("draft_queue:") < block.index("live_conversation:")
    assert "Multi-panel" in block or "multi-panel" in block.lower()
    assert "focus: review_load, awaiting_review, draft_queue, live_conversation" in block


def test_attention_queues_capped_for_fold_share() -> None:
    studio = _studio_dashboard_block()
    review = _review_desk_block()
    # Tight caps so dual attention shares the above-fold dens with media/metrics.
    assert "limit: 2" in studio
    assert "limit: 3" in studio
    assert "limit: 2" in review
    # Caps on dual attention regions (not only media shelf).
    assert "filter: status = review" in studio
    assert "filter: status = draft" in studio
    assert "filter: status = review" in review
    assert "filter: status = draft" in review
