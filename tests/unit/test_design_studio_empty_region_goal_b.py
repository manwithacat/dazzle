"""Post-5.8 Goal B empty_region_honesty — design_studio secondary desks (cycle 1856)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/design_studio/dsl/app.dsl"


def _workspace_block(name: str) -> str:
    text = APP.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        for alt in ("\nsurface ", "\nentity ", "\naction ", "\nledger "):
            a = rest.find(alt)
            if a != -1:
                return text[start : start + 1 + a]
        return text[start:]
    return text[start : start + 1 + nxt]


def test_publish_desk_omits_trail_and_status_bar() -> None:
    """Publish pressure: pulse + dual queues — not trail/bar thrash."""
    block = _workspace_block("publish_desk")
    assert "publish_pulse:" in block
    assert "approved_queue:" in block
    assert "published_gallery:" in block
    assert "publish_trail:" not in block
    assert "status_mix:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_draft_studio_omits_twin_gallery_trail_and_bar() -> None:
    """Draft pressure: one queue + metrics — not twin gallery / trail / type bar."""
    block = _workspace_block("draft_studio")
    assert "draft_pulse:" in block
    assert "draft_queue:" in block
    assert "draft_gallery:" not in block
    assert "draft_trail:" not in block
    assert "type_mix:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_review_pipeline_omits_twin_gallery_trail_and_bar() -> None:
    """Review pipeline: one queue + metrics — not twin gallery / trail / type bar."""
    block = _workspace_block("review_pipeline")
    assert "review_pulse:" in block
    assert "review_queue:" in block
    assert "review_gallery:" not in block
    assert "review_trail:" not in block
    assert "type_mix:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_active_campaigns_omits_twin_grid_trail_and_bar() -> None:
    """Active campaigns: pulse + one queue — not twin grid / trail / status bar."""
    block = _workspace_block("active_campaigns")
    assert "campaign_pulse:" in block
    assert "active_queue:" in block
    assert "active_grid:" not in block
    assert "campaign_trail:" not in block
    assert "status_mix:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_feedback_desk_omits_note_timeline_and_status_bar() -> None:
    """Feedback: pulse + conversation + in-review queue — not twin timeline/bar."""
    block = _workspace_block("feedback_desk")
    assert "feedback_pulse:" in block
    assert "live_conversation:" in block
    assert "assets_in_review:" in block
    assert "note_timeline:" not in block
    assert "asset_status_mix:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_brand_desk_omits_trail_and_campaign_mix() -> None:
    """Brand desk: media + logo + campaigns — not asset trail / campaign bar thrash."""
    block = _workspace_block("brand_desk")
    assert "asset_media:" in block
    assert "brand_media:" in block
    assert "campaign_queue:" in block
    assert "asset_trail:" not in block
    assert "campaign_mix:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_asset_catalog_hosts_bar_and_timeline_coverage() -> None:
    """Hero prune must not leave bar_chart/timeline fleet-uncovered (DAM catalog)."""
    block = _workspace_block("asset_catalog")
    assert "media_grid:" in block
    assert "status_mix:" in block
    assert "recent_activity:" in block
    assert "display: bar_chart" in block
    assert "display: timeline" in block
