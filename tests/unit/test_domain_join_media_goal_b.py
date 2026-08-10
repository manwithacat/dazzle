"""Post-5.8 Goal B media — domain_join_co handbook cover wall (novel vs headshot)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = ROOT / "examples/domain_join_co/dsl/domain.dsl"
DOC_SEEDS = ROOT / "examples/domain_join_co/dsl/seeds/demo_data/WorkspaceDocument.jsonl"


def _workspace_block(name: str) -> str:
    text = DOMAIN.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_workspace_document_declares_preview_url() -> None:
    text = DOMAIN.read_text()
    block = text.split('entity WorkspaceDocument "Workspace Document"')[1].split("entity ")[0]
    assert "preview_url: url" in block
    assert "photo_url" not in block


def test_home_handbook_covers_first() -> None:
    """Novel media: handbook document thumbs win fold — not User headshots."""
    block = _workspace_block("home")
    assert "handbook_covers:" in block
    assert "source: WorkspaceDocument" in block
    assert "display: grid" in block
    assert "preview_url != null" in block
    assert "media_shelf:" not in block
    assert "photo_url" not in block
    assert block.index("handbook_covers:") < block.index("team_pulse:")
    assert (
        "focus: handbook_covers, team_pulse, announcement_queue, join_readiness, "
        "composition, live_conversation" in block
    )


def test_announce_handbook_covers_first() -> None:
    block = _workspace_block("announce")
    assert "handbook_covers:" in block
    assert "display: grid" in block
    assert "preview_url != null" in block
    assert "media_shelf:" not in block
    assert block.index("handbook_covers:") < block.index("board_pulse:")
    assert (
        "focus: handbook_covers, board_pulse, feed_queue, join_context, "
        "composition, live_conversation" in block
    )


def test_workspace_document_seeds_have_preview_urls() -> None:
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    with_preview = [r for r in rows if r.get("preview_url")]
    assert len(with_preview) >= 8, "Goal B media expects cover previews on handbooks"
    assert all("placehold.co" in r["preview_url"] for r in with_preview)
