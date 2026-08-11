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
    # Goal B interesting_product: hero live threads use Message/Bubble chrome
    # (not queue meta) after the HTTP CONVERSATION wire-up.
    for ws in ("workspace command_center", "workspace incident_review"):
        block = text.split(ws, 1)[1]
        region = block.split("live_conversation:", 1)[1][:400]
        assert "display: conversation" in region, ws
        assert "source: IncidentNote" in region


def test_alert_detail_discussion_uses_conversation_chrome() -> None:
    """Alert hub Discussion is Message/Bubble trail (not queue meta) — cycle 1899."""
    text = APP.read_text()
    assert 'surface alert_detail "Alert Detail"' in text
    block = text.split('surface alert_detail "Alert Detail"', 1)[1]
    block = block.split("surface incident_note_list", 1)[0]
    related = block.split('related discussion "Discussion"', 1)[1][:320]
    assert "display: conversation" in related
    assert "show: IncidentNote" in related
    assert "columns: body, author, note_phase, page_channel, created_at" in related
    assert "display: queue" not in related
    # Phase + channel before timestamp (content-first trail, not meta lead).
    assert related.index("body") < related.index("created_at")
    assert related.index("note_phase") < related.index("created_at")
    assert related.index("page_channel") < related.index("created_at")


def test_incident_note_declares_timeline_phase_and_page_channel() -> None:
    """Peer pack conversation upgrade (cycle 1917) — PagerDuty timeline phase + channel."""
    text = APP.read_text()
    block = text.split('entity IncidentNote "Incident Note":', 1)[1].split("entity ", 1)[0]
    assert "note_phase: enum[observe,ack,mitigate,escalate,resolve]=observe" in block
    assert "page_channel: enum[bridge,slack,pager,status_page]=bridge" in block
    fitness = block.split("fitness:", 1)[1].split("\n\n", 1)[0]
    assert "note_phase" in fitness
    assert "page_channel" in fitness


def test_incident_note_surfaces_expose_phase_and_channel() -> None:
    text = APP.read_text()
    for marker in (
        'surface incident_note_list "Incident Notes":',
        'surface incident_note_detail "Incident Note":',
        'surface incident_note_create "Add Incident Note":',
    ):
        assert marker in text
        block = text.split(marker, 1)[1].split("surface ", 1)[0]
        assert "note_phase" in block, marker
        assert "page_channel" in block, marker


def test_incident_note_seeds_have_domain_true_ops_copy() -> None:
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    phases: set[str] = set()
    channels: set[str] = set()
    for row in rows:
        body = str(row.get("body") or "")
        assert len(body) >= 24, body
        assert " " in body
        phase = str(row.get("note_phase") or "observe")
        assert phase in {"observe", "ack", "mitigate", "escalate", "resolve"}, phase
        phases.add(phase)
        channel = str(row.get("page_channel") or "bridge")
        assert channel in {"bridge", "slack", "pager", "status_page"}, channel
        channels.add(channel)
    # Peer pack: lean-in mix — not all observe / bridge.
    assert phases & {"mitigate", "escalate", "resolve", "ack"}
    assert channels - {"bridge"}
