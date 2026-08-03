"""Post-5.8 Goal B conversation — ops_dashboard incident notes on command desks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/ops_dashboard/dsl/app.dsl"
NOTE_SEEDS = ROOT / "examples/ops_dashboard/dsl/seeds/demo_data/IncidentNote.jsonl"


def test_incident_note_display_field_is_body() -> None:
    text = APP.read_text()
    assert "entity IncidentNote" in text
    assert "display_field: body" in text
    assert "body: text required" in text


def test_command_center_declares_live_conversation_spine() -> None:
    text = APP.read_text()
    assert "workspace command_center" in text
    assert "live_conversation:" in text
    assert "source: IncidentNote" in text
    assert "conversation: count(IncidentNote)" in text
    assert "workspace incident_review" in text


def test_incident_note_seeds_have_domain_true_ops_copy() -> None:
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    for row in rows:
        body = str(row.get("body") or "")
        assert len(body) >= 24, body
        assert " " in body
