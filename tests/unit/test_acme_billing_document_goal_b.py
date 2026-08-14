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
    # Peer-pack document grain (cycle 1904): tax + plan on composition lines
    assert "tax_code: str(20) optional" in text
    assert "plan_name: str(80) optional" in text
    # Cycle 2069: Stripe/Chargebee line-kind composition grain
    assert "line_kind: enum[subscription, usage, one_time, credit]=one_time" in text
    # Invoice number is the document title for refs
    assert "display_field: number" in text
    # Peer-pack dunning state on the invoice header
    assert "dunning_state: enum[none, reminder_1, reminder_2, final, collections]=none" in text


def test_billing_workspace_declares_composition_queue() -> None:
    text = SURFACES.read_text()
    assert "workspace billing" in text
    assert "composition:" in text
    assert "source: LineItem" in text
    assert 'related lines "Line items"' in text
    assert "show: LineItem" in text
    assert "columns: description, quantity, unit_amount, tax_code, plan_name, line_kind" in text
    # Cycle 1904 peer-pack: dunning board + in_dunning metric above conversation
    assert "dunning_board:" in text
    assert "group_by: dunning_state" in text
    assert "in_dunning: count(Invoice where dunning_state != none)" in text
    block_start = text.index('workspace billing "Acme Billing":')
    rest = text[block_start + 1 :]
    nxt = rest.find("\nworkspace ")
    block = text[block_start : block_start + 1 + nxt] if nxt != -1 else text[block_start:]
    # Region markers only (\n  name:\n) — bare soft_dunning:/subscription_lines:
    # also appear as portfolio_metrics aggregate keys earlier in the block.
    assert block.index("\n  soft_dunning:\n") < block.index("\n  hard_collections:\n")
    assert block.index("\n  hard_collections:\n") < block.index("\n  open_invoices:\n")
    # Cycle 2069: line-kind dual queues ABOVE dunning stages for fold OCR.
    assert block.index("\n  invoice_packets:\n") < block.index("portfolio_metrics:")
    assert block.index("portfolio_metrics:") < block.index("\n  subscription_lines:\n")
    assert block.index("\n  subscription_lines:\n") < block.index("\n  usage_lines:\n")
    assert block.index("\n  usage_lines:\n") < block.index("\n  soft_dunning:\n")
    assert block.index("\n  dunning_board:\n") < block.index("\n  composition:\n")
    assert block.index("\n  composition:\n") < block.index("\n  live_conversation:\n")
    assert (
        "focus: invoice_packets, portfolio_metrics, subscription_lines, usage_lines, soft_dunning, hard_collections, "
        "open_invoices, sensitive_flags, dunning_board, composition, live_conversation" in block
    )


def test_line_item_seeds_are_domain_true_descriptions() -> None:
    rows = [json.loads(line) for line in LINE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 12, "Goal B document expects composition lines across invoices"
    tax_codes = set()
    plans = set()
    for row in rows:
        desc = str(row["description"])
        assert len(desc) >= 12, desc
        assert " " in desc, f"line description should be human prose, not slug: {desc}"
        assert int(row["quantity"]) >= 1
        assert int(row["unit_amount"]) > 0
        # Invoice.jsonl uses 00000005- / 00000006- prefixes; LineItem uses 00000009-
        assert row["invoice"].startswith("0000000")
        assert str(row["id"]).startswith("00000009-")
        # Peer-pack tax + plan grain on every seed line
        assert row.get("tax_code"), f"missing tax_code on {row['id']}"
        assert row.get("plan_name"), f"missing plan_name on {row['id']}"
        assert row.get("line_kind") in {
            "subscription",
            "usage",
            "one_time",
            "credit",
        }, row
        tax_codes.add(row["tax_code"])
        plans.add(row["plan_name"])
    assert len(tax_codes) >= 3, tax_codes
    assert len(plans) >= 4, plans
    kinds = {r.get("line_kind") for r in rows}
    assert "subscription" in kinds and "usage" in kinds and "one_time" in kinds, kinds
    assert sum(1 for r in rows if r.get("line_kind") == "subscription") >= 4
    assert sum(1 for r in rows if r.get("line_kind") == "usage") >= 2


def test_invoice_seeds_include_dunning_mix() -> None:
    inv_path = ROOT / "examples/acme_billing/dsl/seeds/demo_data/Invoice.jsonl"
    rows = [json.loads(line) for line in inv_path.read_text().splitlines() if line.strip()]
    states = {r.get("dunning_state", "none") for r in rows}
    assert "none" in states
    assert states & {"reminder_1", "reminder_2", "final", "collections"}, states
    assert any(r.get("dunning_state") not in (None, "none") for r in rows)


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


def test_billing_dunning_stage_density() -> None:
    """Cycle 2053: Stripe/Chargebee soft vs hard dunning document queues.

    Recipe dunning_stage_density — not dunning_board-only re-stack.
    """
    text = SURFACES.read_text()
    start = text.index('workspace billing "Acme Billing":')
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    block = text[start : start + 1 + nxt] if nxt != -1 else text[start:]
    assert "\n  soft_dunning:\n" in block
    assert "\n  hard_collections:\n" in block
    soft = block.split("\n  soft_dunning:\n", 1)[1].split("\n  hard_collections:", 1)[0]
    assert "source: Invoice" in soft
    assert "dunning_state = reminder_1" in soft
    assert "dunning_state = reminder_2" in soft
    assert "display: queue" in soft
    hard = block.split("\n  hard_collections:\n", 1)[1].split("\n  open_invoices:", 1)[0]
    assert "dunning_state = final" in hard
    assert "dunning_state = collections" in hard
    assert "display: queue" in hard
    assert (
        "soft_dunning: count(Invoice where dunning_state = reminder_1 or dunning_state = reminder_2)"
        in block
    )
    assert (
        "hard_collections: count(Invoice where dunning_state = final or dunning_state = collections)"
        in block
    )
    assert block.index("portfolio_metrics:") < block.index("\n  soft_dunning:\n")
    assert block.index("\n  soft_dunning:\n") < block.index("\n  hard_collections:\n")
    assert block.index("\n  hard_collections:\n") < block.index("dunning_board:")


def test_billing_line_kind_density() -> None:
    """Cycle 2069: Stripe/Chargebee subscription vs usage document queues.

    Recipe line_kind_density — not dunning_stage_density re-stack.
    """
    text = SURFACES.read_text()
    start = text.index('workspace billing "Acme Billing":')
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    block = text[start : start + 1 + nxt] if nxt != -1 else text[start:]
    assert "\n  subscription_lines:\n" in block
    assert "\n  usage_lines:\n" in block
    sub = block.split("\n  subscription_lines:\n", 1)[1].split("\n  usage_lines:", 1)[0]
    assert "source: LineItem" in sub
    assert "line_kind = subscription" in sub
    assert "display: queue" in sub
    usage = block.split("\n  usage_lines:\n", 1)[1].split("\n  composition:", 1)[0]
    assert "source: LineItem" in usage
    assert "line_kind = usage" in usage
    assert "display: queue" in usage
    assert "subscription_lines: count(LineItem where line_kind = subscription)" in block
    assert "usage_lines: count(LineItem where line_kind = usage)" in block
    assert block.index("portfolio_metrics:") < block.index("\n  subscription_lines:\n")
    assert block.index("\n  subscription_lines:\n") < block.index("\n  usage_lines:\n")
    assert block.index("\n  usage_lines:\n") < block.index("\n  soft_dunning:\n")
    assert block.index("\n  usage_lines:\n") < block.index("\n  composition:\n")
