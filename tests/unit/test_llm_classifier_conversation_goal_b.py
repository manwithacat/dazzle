"""Post-5.8 Goal B conversation — llm_ticket_classifier AI reply spine."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/llm_ticket_classifier/dsl/app.dsl"
CLASS_SEEDS = ROOT / "examples/llm_ticket_classifier/dsl/seeds/demo_data/TicketClassification.jsonl"


def test_classification_display_field_is_suggested_response() -> None:
    text = APP.read_text()
    assert "entity TicketClassification" in text
    assert "display_field: suggested_response" in text


def test_support_dashboard_declares_live_ai_replies() -> None:
    text = APP.read_text()
    assert "workspace support_dashboard" in text
    assert "live_ai_replies:" in text
    assert "source: TicketClassification" in text
    # Agent default desk also carries the conversation strip
    assert "workspace ticket_management" in text


def test_classification_seeds_have_domain_true_suggested_replies() -> None:
    rows = [json.loads(line) for line in CLASS_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 6
    for row in rows:
        reply = str(row.get("suggested_response") or "")
        assert len(reply) >= 24, reply
        assert " " in reply
