"""Cycle 1606 — queue drill dual-open discovery attrs (table-row parity)."""

from __future__ import annotations

from dazzle.render.fragment.ingest import QueueRow, render_queue_row


def test_queue_drill_stamps_dual_open_discovery_attrs() -> None:
    html = render_queue_row(
        QueueRow(
            title="Refund request — Acme",
            drill_url="/app/ticket/t-42",
            date_html='<span class="dz-queue-row-date">2h left</span>',
        )
    )
    assert "data-dz-queue-drill" in html
    assert 'href="/app/ticket/t-42"' in html
    # Primary hop (title link)
    assert 'data-dz-open-role="primary"' in html
    assert 'data-dz-open-hop="0"' in html
    assert 'data-dz-open-via="id"' in html
    assert 'data-dz-open-entity="Ticket"' in html
    assert 'data-dz-open-label="Open Ticket"' in html
    assert 'aria-label="Open Ticket"' in html
    assert 'title="Open Ticket"' in html
    # Row-level single-hop chain (agent attr-first discovery)
    assert 'data-dz-open-chain="/app/ticket/t-42"' in html
    assert 'data-dz-open-chain-via="id"' in html
    assert 'data-dz-open-hops="1"' in html
    assert 'data-dz-open-chain-label="Open Ticket"' in html
    assert 'data-dz-open-chain-entity="Ticket"' in html


def test_queue_without_drill_has_no_open_attrs() -> None:
    html = render_queue_row(QueueRow(title="No drill"))
    assert "data-dz-open-" not in html
    assert "data-dz-queue-drill" not in html
