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
    assert "workspace engineering_dashboard" in text
    assert "live_conversation:" in text
    assert "source: IssueNote" in text
    assert "conversation: count(IssueNote)" in text
    # Goal B interesting_product: hero live threads use Message/Bubble chrome
    # (not queue meta) after the HTTP CONVERSATION wire-up.
    # Cycle 2059: issue_triage focus is severity media dual first; trail remains.
    for ws in ("engineering_dashboard", "manager_ops", "issue_triage"):
        block = text.split(f"workspace {ws}", 1)[1]
        region = block.split("live_conversation:", 1)[1][:400]
        assert "display: conversation" in region, ws
        assert "source: IssueNote" in region, ws
        if ws != "issue_triage":
            ux = block.split("ux:", 1)[1][:600]
            assert "live_conversation" in ux, ws


def test_issue_detail_discussion_uses_conversation_chrome() -> None:
    """Issue hub Discussion is Message/Bubble trail (not queue meta) — cycle 1899."""
    text = APP.read_text()
    assert 'surface issue_report_detail "Issue Detail"' in text
    block = text.split('surface issue_report_detail "Issue Detail"', 1)[1]
    block = block.split("surface issue_report_create", 1)[0]
    related = block.split('related discussion "Discussion"', 1)[1][:240]
    assert "display: conversation" in related
    assert "show: IssueNote" in related
    assert "columns: body, author, note_kind, created_at" in related
    assert "display: queue" not in related


def test_issue_note_seeds_have_domain_true_field_copy() -> None:
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    for row in rows:
        body = str(row.get("body") or "")
        assert len(body) >= 24, body
        assert " " in body
        assert row.get("note_kind") in ("note", "repro")


def test_issue_triage_note_kind_chrome_not_filter_slice() -> None:
    """Cycle 2084 recipe note_kind_chrome — labels on the existing trail."""
    text = APP.read_text()
    block = text.split("workspace issue_triage", 1)[1].split("workspace firmware_pipeline", 1)[0]
    assert "\n  repro_notes:\n" not in block
    assert "note_kind = repro" not in block
    assert "repro_notes: count(" not in block
    assert "focus: open_pressure, live_conversation, critical_evidence, high_evidence" in block
    assert "\n  live_conversation:\n" in block
    live = block.split("\n  live_conversation:\n", 1)[1].split("\n  critical_evidence:", 1)[0]
    assert "display: conversation" in live
    assert "source: IssueNote" in live
    ent = text.split('entity IssueNote "Issue Note":', 1)[1].split("entity ", 1)[0]
    assert "note_kind: enum[note,repro]=note" in ent
    assert "note_kind_chrome" in ent or "note_kind" in ent
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    assert sum(1 for r in rows if r.get("note_kind") == "repro") >= 3
