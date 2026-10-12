"""Cycle 1643 — list-path entity labels for open discovery."""

from __future__ import annotations

from dazzle.render.fragment.region._row_links import entity_label_from_detail_url


def test_entity_label_list_and_detail_paths() -> None:
    assert entity_label_from_detail_url("/app/user/u-9") == "User"
    assert entity_label_from_detail_url("/app/payment-attempt/x") == "Payment Attempt"
    assert entity_label_from_detail_url("/app/ticket") == "Ticket"
    assert entity_label_from_detail_url("/app/invoices?status=pending") == "Invoices"
    assert entity_label_from_detail_url("/app/supplier_bank_account/1") == "Supplier Bank Account"
    assert entity_label_from_detail_url("") == "Related"
    assert entity_label_from_detail_url("#") == "Related"
