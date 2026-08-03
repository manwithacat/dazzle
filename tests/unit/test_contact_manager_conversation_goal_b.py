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
    assert "focus: live_conversation" in text


def test_contact_note_seeds_have_domain_true_crm_copy() -> None:
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    for row in rows:
        body = str(row.get("body") or "")
        assert len(body) >= 24, body
        assert " " in body
