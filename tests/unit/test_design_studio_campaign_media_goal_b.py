"""Post-5.8 Goal B media — design_studio Campaigns desk creative wall."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/design_studio/dsl/app.dsl"
ASSET_SEEDS = ROOT / "examples/design_studio/dsl/seeds/demo_data/Asset.jsonl"


def _campaign_desk_block() -> str:
    text = APP.read_text()
    start = text.index('workspace campaign_desk "Campaigns":')
    end = text.index('workspace feedback_desk "Feedback":', start)
    return text[start:end]


def test_campaign_desk_creatives_grid_wins_fold() -> None:
    """Peer campaign tools put creative pixels above schedule meta."""
    block = _campaign_desk_block()
    assert "\n  campaign_creatives:" in block
    assert "filter: campaign != null" in block
    assert "display: grid" in block
    assert "\n  campaign_pulse:" in block
    assert "\n  active_queue:" in block
    # Order: media wall → metrics → schedule (not chart theater first).
    assert block.index("\n  campaign_creatives:") < block.index("\n  campaign_pulse:")
    assert block.index("\n  campaign_pulse:") < block.index("\n  active_queue:")
    assert "campaign_mix:" not in block
    assert "bar_chart" not in block


def test_campaign_desk_ux_focus_media_first() -> None:
    block = _campaign_desk_block()
    assert "focus: campaign_creatives, campaign_pulse, active_queue, all_campaigns" in block
    assert "media" in block.lower() or "creatives" in block.lower()
    shelf = block.split("campaign_creatives:", 1)[1][:400]
    assert "source: Asset" in shelf
    assert "action: asset_detail" in shelf
    assert "limit: 10" in shelf


def test_campaign_hub_related_assets_show_preview() -> None:
    text = APP.read_text()
    start = text.index('surface campaign_detail "Campaign Detail":')
    end = text.index('surface feedback_create "Add Feedback":', start)
    hub = text[start:end]
    assert 'related assets "Campaign assets":' in hub
    assert "display: status_cards" in hub
    assert "preview_url" in hub


def test_asset_seeds_assign_campaign_creatives() -> None:
    lines = [ln for ln in ASSET_SEEDS.read_text().splitlines() if ln.strip()]
    rows = [json.loads(ln) for ln in lines]
    with_campaign = [r for r in rows if r.get("campaign")]
    assert len(with_campaign) >= 8, "Goal B media expects campaign-linked creatives for the wall"
    for r in with_campaign:
        pu = str(r.get("preview_url") or "")
        assert pu.startswith("https://placehold.co/"), r.get("name")
