"""Post-5.8 Goal B document — support_tickets SLA waiver composition."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/support_tickets/dsl/app.dsl"
SIGNING = ROOT / "examples/support_tickets/dsl/signing.dsl"
WAIVER_SEEDS = ROOT / "examples/support_tickets/dsl/seeds/demo_data/SlaWaiver.jsonl"


def test_sla_waiver_entity_is_document_composition() -> None:
    text = SIGNING.read_text()
    assert 'entity SlaWaiver "SLA Waiver"' in text
    assert "display_field: breach_summary" in text
    assert "breach_summary: text required" in text
    assert "status: enum[draft,sent,signed,void]=draft" in text
    assert "signable: true" in text


def test_hero_desks_declare_composition_queue() -> None:
    """Goal B document: composition on manager_ops + ticket_queue (not only list surface)."""
    text = APP.read_text()
    assert "workspace manager_ops" in text
    assert "workspace ticket_queue" in text
    assert "composition:" in text
    assert "source: SlaWaiver" in text
    assert "documents: count(SlaWaiver)" in text
    assert 'related waivers "SLA waivers"' in text
    assert "show: SlaWaiver" in text

    manager = text.split("workspace manager_ops", 1)[1].split("workspace agent_dashboard", 1)[0]
    assert "composition:" in manager
    assert "source: SlaWaiver" in manager
    assert "documents: count(SlaWaiver)" in manager
    assert manager.index("unassigned_queue:") < manager.index("composition:")
    assert manager.index("composition:") < manager.index("live_conversation:")

    queue = text.split("workspace ticket_queue", 1)[1].split("workspace manager_ops", 1)[0]
    assert "composition:" in queue
    assert "source: SlaWaiver" in queue
    assert "documents: count(SlaWaiver)" in queue


def test_sla_waiver_list_dual_open_declared() -> None:
    text = SIGNING.read_text()
    assert 'surface sla_waiver_list "SLA Waivers"' in text
    assert "open: SlaWaiver via id | Ticket via ticket" in text
    assert 'surface sla_waiver_detail "SLA Waiver"' in text


def test_sla_waiver_seeds_are_domain_true_document_titles() -> None:
    rows = [json.loads(line) for line in WAIVER_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 12, "Goal B document expects composition lines across tickets"
    statuses = set()
    for row in rows:
        title = str(row["breach_summary"])
        assert len(title) >= 16, title
        assert " " in title, f"breach_summary should be human prose, not slug: {title}"
        assert str(row["ticket"]).startswith("c3000000-")
        assert str(row["id"]).startswith("e8000000-")
        assert len(str(row["waiver_terms"])) >= 24
        statuses.add(row["status"])
    assert statuses >= {"draft", "sent", "signed"}
