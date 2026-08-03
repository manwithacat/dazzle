"""Cycle 1643 — action-card open discovery + list-path entity labels."""

from __future__ import annotations

from dazzle.render.fragment.ingest import ActionCard, render_action_card
from dazzle.render.fragment.region._row_links import entity_label_from_detail_url


def test_entity_label_list_and_detail_paths() -> None:
    assert entity_label_from_detail_url("/app/user/u-9") == "User"
    assert entity_label_from_detail_url("/app/payment-attempt/x") == "Payment Attempt"
    assert entity_label_from_detail_url("/app/ticket") == "Ticket"
    assert entity_label_from_detail_url("/app/invoices?status=pending") == "Invoices"
    assert entity_label_from_detail_url("/app/supplier_bank_account/1") == "Supplier Bank Account"
    assert entity_label_from_detail_url("") == "Related"
    assert entity_label_from_detail_url("#") == "Related"


def test_action_card_app_url_stamps_open_discovery() -> None:
    html = render_action_card(
        ActionCard(
            label="Overdue invoices", tone="warning", url="/app/invoice?status=overdue", count=3
        )
    )
    assert 'href="/app/invoice?status=overdue"' in html
    assert 'data-dz-open-entity="Invoice"' in html
    assert 'data-dz-open-via="id"' in html
    assert 'data-dz-open-chain="/app/invoice?status=overdue"' in html
    assert 'data-dz-open-hops="1"' in html
    assert "Open Invoice" in html
    assert "data-dz-action-card" in html


def test_action_card_detail_url_stamps_open_discovery() -> None:
    html = render_action_card(
        ActionCard(label="Open ticket", tone="accent", url="/app/ticket/t-42")
    )
    assert 'data-dz-open-entity="Ticket"' in html
    assert 'data-dz-open-chain="/app/ticket/t-42"' in html


def test_action_card_fragment_url_skips_open_discovery() -> None:
    html = render_action_card(ActionCard(label="Placeholder", tone="neutral", url="#"))
    assert 'href="#"' in html
    assert "data-dz-open-entity" not in html
    assert "data-dz-open-chain" not in html


def test_action_card_static_div_no_open_attrs() -> None:
    html = render_action_card(ActionCard(label="Nothing else today", tone="neutral"))
    assert html.startswith("<div ")
    assert "data-dz-open-entity" not in html
