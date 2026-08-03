"""Post-5.8 Goal B document — acme_billing invoice line composition."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTITIES = ROOT / "examples/acme_billing/dsl/entities.dsl"
SURFACES = ROOT / "examples/acme_billing/dsl/surfaces.dsl"
LINE_SEEDS = ROOT / "examples/acme_billing/dsl/seeds/demo_data/LineItem.jsonl"


def test_line_item_entity_is_document_composition() -> None:
    text = ENTITIES.read_text()
    assert 'entity LineItem "Line Item"' in text
    assert "display_field: description" in text
    assert "unit_amount: int required" in text
    # Invoice number is the document title for refs
    assert "display_field: number" in text


def test_billing_workspace_declares_composition_queue() -> None:
    text = SURFACES.read_text()
    assert "workspace billing" in text
    assert "composition:" in text
    assert "source: LineItem" in text
    assert 'related lines "Line items"' in text
    assert "show: LineItem" in text


def test_line_item_seeds_are_domain_true_descriptions() -> None:
    rows = [json.loads(line) for line in LINE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 12, "Goal B document expects composition lines across invoices"
    for row in rows:
        desc = str(row["description"])
        assert len(desc) >= 12, desc
        assert " " in desc, f"line description should be human prose, not slug: {desc}"
        assert int(row["quantity"]) >= 1
        assert int(row["unit_amount"]) > 0
        # Invoice.jsonl uses 00000005- / 00000006- prefixes; LineItem uses 00000009-
        assert row["invoice"].startswith("0000000")
        assert str(row["id"]).startswith("00000009-")


def test_demo_personas_bind_domain_user_org() -> None:
    """org_owner@demo must resolve current_user.org → Acme Corp (empty-desk trap)."""
    users = ROOT / "examples/acme_billing/dsl/seeds/demo_data/User.jsonl"
    rows = [json.loads(line) for line in users.read_text().splitlines() if line.strip()]
    by_email = {r["email"]: r for r in rows}
    acme = "0a000000-0000-4000-8000-000000000001"
    for email in (
        "org_owner@demo.dazzle.local",
        "auditor@demo.dazzle.local",
        "project_member@demo.dazzle.local",
        "external_contractor@demo.dazzle.local",
        "admin@demo.dazzle.local",
    ):
        assert email in by_email, f"missing domain User for demo persona {email}"
        assert by_email[email]["org"] == acme, email
    # STABLE dual-identity for admin + auditor
    assert by_email["admin@demo.dazzle.local"]["id"] == "a1000000-0000-4000-8000-000000000003"
    assert by_email["auditor@demo.dazzle.local"]["id"] == "a1000000-0000-4000-8000-000000000009"
