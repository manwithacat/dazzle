"""Post-5.8 Goal B conversation — domain_join_co team notes on home/board."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = ROOT / "examples/domain_join_co/dsl/domain.dsl"
NOTE_SEEDS = ROOT / "examples/domain_join_co/dsl/seeds/demo_data/AnnouncementNote.jsonl"


def test_announcement_note_display_field_is_body() -> None:
    text = DOMAIN.read_text()
    assert "entity AnnouncementNote" in text
    assert "display_field: body" in text
    assert "body: text required" in text


def test_home_and_announce_declare_live_conversation() -> None:
    text = DOMAIN.read_text()
    assert "workspace home" in text
    assert "workspace announce" in text
    assert "live_conversation:" in text
    assert "source: AnnouncementNote" in text
    # Metrics honesty: nested count(AnnouncementNote) was ship-lying as 0 —
    # conversation proof is the trail, not a zeroed metric tile.
    assert "conversation: count(AnnouncementNote)" not in text
    assert "announcements: count(Announcement)" in text or "posts: count(Announcement)" in text
    # Goal B interesting_product (cycle 1822): hero live threads use
    # Message/Bubble chrome (not queue meta) after CONVERSATION wire-up.
    for name in ("home", "announce"):
        marker = f'workspace {name} "'
        start = text.index(marker)
        rest = text[start + 1 :]
        nxt = rest.find("\nworkspace ")
        block = text[start : start + 1 + nxt] if nxt != -1 else text[start:]
        region = block.split("live_conversation:", 1)[1][:400]
        assert "display: conversation" in region, name
        assert "source: AnnouncementNote" in region


def test_announcement_note_seeds_have_domain_true_copy() -> None:
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    for row in rows:
        body = str(row.get("body") or "")
        assert len(body) >= 24, body
        assert " " in body


def test_announcement_detail_discussion_uses_conversation_chrome() -> None:
    """Announcement hub Discussion is Message/Bubble trail (not queue meta) — cycle 1899."""
    # Prefer domain.dsl surfaces (announcement hub).
    root = Path(__file__).resolve().parents[2]
    domain = root / "examples/domain_join_co/dsl/domain.dsl"
    text = domain.read_text()
    assert 'surface announcement_detail "Announcement"' in text
    block = text.split('surface announcement_detail "Announcement"', 1)[1]
    block = block.split("surface announcement_note_list", 1)[0]
    related = block.split('related discussion "Discussion"', 1)[1][:240]
    assert "display: conversation" in related
    assert "show: AnnouncementNote" in related
    assert "columns: body, author, created_at" in related
    assert "display: queue" not in related
