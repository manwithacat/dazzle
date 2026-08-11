"""Post-5.8 Goal B conversation — contact_manager relationship notes on Home."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/contact_manager/dsl/app.dsl"
NOTE_SEEDS = ROOT / "examples/contact_manager/demo_data/ContactNote.jsonl"


def test_contact_note_display_field_is_body() -> None:
    text = APP.read_text()
    assert "entity ContactNote" in text
    assert "display_field: body" in text
    assert "body: text required" in text


def test_home_declares_live_conversation_spine() -> None:
    text = APP.read_text()
    assert "workspace home" in text
    assert "live_conversation:" in text
    assert "source: ContactNote" in text
    assert "conversation: count(ContactNote)" in text
    # Conversation remains on Home focus (after dual attention — command_density).
    assert "live_conversation" in text
    assert "focus:" in text and "live_conversation" in text.split("workspace home", 1)[1]
    # Goal B interesting_product: hero live threads use Message/Bubble chrome
    # (not queue meta) after the HTTP CONVERSATION wire-up.
    block = text.split("workspace home", 1)[1]
    region = block.split("live_conversation:", 1)[1][:400]
    assert "display: conversation" in region
    assert "source: ContactNote" in region


def test_contact_detail_discussion_uses_conversation_chrome() -> None:
    """Contact hub Discussion is Message/Bubble trail (not queue meta) — cycle 1899."""
    text = APP.read_text()
    assert 'surface contact_detail "Contact Detail"' in text
    block = text.split('surface contact_detail "Contact Detail"', 1)[1]
    block = block.split("surface contact_create", 1)[0]
    related = block.split('related discussion "Discussion"', 1)[1][:240]
    assert "display: conversation" in related
    assert "show: ContactNote" in related
    assert "columns: body, author, created_at" in related
    assert "display: queue" not in related


def test_contact_note_seeds_have_domain_true_crm_copy() -> None:
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    for row in rows:
        body = str(row.get("body") or "")
        assert len(body) >= 24, body
        assert " " in body
