"""Post-5.8 Goal B media — invoice_ops teammate headshot shelf (cycle 1885)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTITIES = ROOT / "examples/invoice_ops/dsl/entities.dsl"
SURFACES = ROOT / "examples/invoice_ops/dsl/surfaces.dsl"
USER_SEEDS = ROOT / "examples/invoice_ops/dsl/seeds/demo_data/User.jsonl"


def _workspace_block(name: str) -> str:
    text = SURFACES.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_user_entity_declares_photo_url() -> None:
    text = ENTITIES.read_text()
    assert 'entity User "User"' in text
    assert "photo_url: url" in text
    # Shared finance_ops media shelf needs list/read for AP roles
    assert "role(requester)" in text
    assert "role(finance)" in text


def test_finance_ops_media_shelf_first() -> None:
    """Goal B media: teammate headshots win the Finance Operations fold before metrics."""
    block = _workspace_block("finance_ops")
    assert "media_shelf:" in block
    assert "source: User" in block
    assert "display: grid" in block
    assert "filter: department != null and photo_url != null" in block
    assert "sort: created_at desc" in block
    assert block.index("media_shelf:") < block.index("ops_metrics:")
    assert block.index("media_shelf:") < block.index("document_pulse:")
    assert block.index("media_shelf:") < block.index("composition:")
    assert (
        "focus: media_shelf, ops_metrics, document_pulse, composition, awaiting_approval, "
        "ready_to_pay, line_composition, live_conversation" in block
    )


def test_user_seeds_have_https_photo_urls() -> None:
    rows = [json.loads(line) for line in USER_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 8
    with_photo = [r for r in rows if r.get("photo_url")]
    assert len(with_photo) >= 8, "Goal B media expects headshots across the AP roster"
    for r in with_photo:
        url = str(r["photo_url"])
        assert url.startswith("https://"), url
        assert "placehold.co" in url
