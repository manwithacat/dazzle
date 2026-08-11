"""Post-5.8 Goal B conversation — hr_records people notes on staff desks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/hr_records/dsl/app.dsl"
NOTE_SEEDS = ROOT / "examples/hr_records/demo_data/PersonNote.jsonl"


def test_person_note_display_field_is_body() -> None:
    text = APP.read_text()
    assert "entity PersonNote" in text
    assert "display_field: body" in text
    assert "body: text required" in text


def test_staff_desks_declare_live_conversation_spine() -> None:
    text = APP.read_text()
    assert "workspace staff_directory" in text
    assert "workspace my_team" in text
    assert "live_conversation:" in text
    assert "source: PersonNote" in text
    assert "conversation: count(PersonNote)" in text
    # Cycle 1837/1838: notes trail after dual attention + documents, still in focus.
    assert "live_conversation" in text
    assert (
        "focus: media_shelf, headcount, current_staff, recent_starters, composition, live_conversation"
        in text
    )


def test_person_detail_discussion_uses_conversation_chrome() -> None:
    """Person hub Discussion is Message/Bubble trail (not queue meta) — cycle 1899."""
    text = APP.read_text()
    assert 'surface person_detail "Person"' in text
    block = text.split('surface person_detail "Person"', 1)[1]
    block = block.split("surface person_create", 1)[0]
    related = block.split('related discussion "Discussion"', 1)[1]
    related = related.split("related ", 1)[0][:200]
    assert "display: conversation" in related
    assert "show: PersonNote" in related
    assert "columns: body, author, created_at" in related
    assert "display: queue" not in related


def test_person_note_seeds_have_domain_true_hr_copy() -> None:
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    for row in rows:
        body = str(row.get("body") or "")
        assert len(body) >= 24, body
        assert " " in body
