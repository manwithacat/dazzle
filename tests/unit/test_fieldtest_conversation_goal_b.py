"""Post-5.8 Goal B conversation — fieldtest_hub issue notes on ops/triage desks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/fieldtest_hub/dsl/app.dsl"
NOTE_SEEDS = ROOT / "examples/fieldtest_hub/dsl/seeds/demo_data/IssueNote.jsonl"


def test_issue_note_display_field_is_body() -> None:
    text = APP.read_text()
    assert "entity IssueNote" in text
    assert "display_field: body" in text
    assert "body: text required" in text


def test_ops_and_triage_declare_live_conversation_spine() -> None:
    text = APP.read_text()
    assert "workspace manager_ops" in text
    assert "workspace issue_triage" in text
    assert "live_conversation:" in text
    assert "source: IssueNote" in text
    assert "conversation: count(IssueNote)" in text
    assert "focus: live_conversation" in text


def test_issue_note_seeds_have_domain_true_field_copy() -> None:
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    for row in rows:
        body = str(row.get("body") or "")
        assert len(body) >= 24, body
        assert " " in body
