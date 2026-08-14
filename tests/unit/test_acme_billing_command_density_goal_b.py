"""Post-5.8 Goal B command_density — acme_billing multi-panel billing desk."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SURFACES = ROOT / "examples/acme_billing/dsl/surfaces.dsl"

BILLING_FOCUS = (
    "focus: invoice_packets, portfolio_metrics, subscription_lines, usage_lines, soft_dunning, hard_collections, "
    "open_invoices, sensitive_flags, dunning_board, composition, live_conversation"
)


def _billing_block() -> str:
    text = SURFACES.read_text()
    start = text.index('workspace billing "Acme Billing":')
    end = text.index('workspace my_work "My Work":', start)
    return text[start:end]


def test_billing_declares_dual_attention_before_conversation() -> None:
    """Peer billing homes put ≥2 attention panels above the note trail."""
    block = _billing_block()
    assert "portfolio_metrics:" in block
    assert "open_invoices:" in block
    assert "sensitive_flags:" in block
    assert "dunning_board:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    # Order: packets → metrics → line-kind dual queues → dunning stages → dual
    # attention → dunning board → composition → conversation (region markers).
    assert block.index("\n  invoice_packets:\n") < block.index("portfolio_metrics:")
    assert block.index("portfolio_metrics:") < block.index("\n  subscription_lines:\n")
    assert block.index("\n  subscription_lines:\n") < block.index("\n  usage_lines:\n")
    assert block.index("\n  usage_lines:\n") < block.index("\n  soft_dunning:\n")
    assert block.index("\n  soft_dunning:\n") < block.index("\n  hard_collections:\n")
    assert block.index("\n  hard_collections:\n") < block.index("\n  open_invoices:\n")
    assert block.index("\n  open_invoices:\n") < block.index("\n  sensitive_flags:\n")
    assert block.index("\n  sensitive_flags:\n") < block.index("\n  dunning_board:\n")
    assert block.index("\n  dunning_board:\n") < block.index("\n  composition:\n")
    assert block.index("\n  composition:\n") < block.index("\n  live_conversation:\n")


def test_billing_caps_attention_for_fold_share() -> None:
    block = _billing_block()
    assert "limit: 4" in block
    # Goal B media invoice_packets leads; line-kind density + dual attention trail.
    assert BILLING_FOCUS in block
    assert "Multi-panel" in block or "multi-panel" in block.lower()


def test_billing_metrics_count_open_sensitive_and_conversation() -> None:
    block = _billing_block()
    assert "open_books: count(Invoice where sensitive != true)" in block
    assert "sensitive: count(Invoice where sensitive = true)" in block
    assert "in_dunning: count(Invoice where dunning_state != none)" in block
    assert "conversation: count(InvoiceNote)" in block
    assert "filter: sensitive != true" in block
    assert "filter: sensitive = true" in block


def _invoices_home_block() -> str:
    text = SURFACES.read_text()
    start = text.index('workspace invoices_home "Invoices":')
    end = text.index('workspace team_home "Team":', start)
    return text[start:end]


def test_invoices_home_dual_attention_before_conversation() -> None:
    """Cycle 1937 peer-pack: invoice desk puts open + dunning above the note trail."""
    block = _invoices_home_block()
    assert "invoice_pulse:" in block
    assert "open_bills:" in block
    assert "dunning_queue:" in block
    assert "live_conversation:" in block
    # Order: pulse → open books → dunning pressure → conversation.
    assert block.index("invoice_pulse:") < block.index("open_bills:")
    assert block.index("open_bills:") < block.index("dunning_queue:")
    assert block.index("dunning_queue:") < block.index("live_conversation:")
    assert "filter: sensitive != true" in block
    assert "filter: dunning_state != none" in block
    assert "group_by: dunning_state" in block
    assert "Multi-panel" in block or "multi-panel" in block.lower()
    assert "focus: invoice_pulse, open_bills, dunning_queue, live_conversation" in block


def test_invoices_home_pulse_counts_dunning_and_open_books() -> None:
    block = _invoices_home_block()
    assert "open_books: count(Invoice where sensitive != true)" in block
    assert "in_dunning: count(Invoice where dunning_state != none)" in block
    assert "sensitive: count(Invoice where sensitive = true)" in block
    assert "conversation: count(InvoiceNote)" in block
    # Caps keep dual attention + conversation sharing the fold.
    assert "limit: 8" in block
    assert "limit: 12" in block
    assert "limit: 6" in block
