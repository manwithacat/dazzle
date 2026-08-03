"""Cycle 1645 — grid-cell drill open discovery (action-card / dashboard parity)."""

from __future__ import annotations

from dazzle.render.fragment.ingest.emit import drill_anchor_open_attrs
from dazzle.render.fragment.primitives.data import GridCell, GridRegion
from dazzle.render.fragment.renderer import FragmentRenderer


def test_drill_anchor_open_attrs_grid_kind() -> None:
    attrs = drill_anchor_open_attrs("/app/ticket/t-9", kind="grid")
    assert "data-dz-grid-drill" in attrs
    assert 'data-dz-open-entity="Ticket"' in attrs
    assert 'data-dz-open-via="id"' in attrs
    assert 'data-dz-open-chain="/app/ticket/t-9"' in attrs
    assert 'data-dz-open-hops="1"' in attrs
    assert "Open Ticket" in attrs


def test_grid_cell_drill_stamps_open_discovery() -> None:
    html = FragmentRenderer().render(
        GridRegion(
            cells=(
                GridCell(
                    title="Login broken",
                    fields=(("Status", "open"),),
                    drill_url="/app/ticket/t-42",
                ),
            )
        )
    )
    assert 'href="/app/ticket/t-42"' in html
    assert "data-dz-grid-drill" in html
    assert 'data-dz-open-entity="Ticket"' in html
    assert 'data-dz-open-via="id"' in html
    assert 'data-dz-open-chain="/app/ticket/t-42"' in html
    assert 'data-dz-open-hops="1"' in html
    assert "Open Ticket" in html
    assert "Login broken" in html


def test_grid_cell_without_drill_has_no_open_attrs() -> None:
    html = FragmentRenderer().render(GridRegion(cells=(GridCell(title="Static card", fields=()),)))
    assert "data-dz-grid-drill" not in html
    assert "data-dz-open-entity" not in html
    assert "data-dz-open-chain" not in html
    assert html.count("dz-grid-cell") >= 1


def test_grid_list_path_entity_label() -> None:
    html = FragmentRenderer().render(
        GridRegion(cells=(GridCell(title="All invoices", drill_url="/app/invoice?status=overdue"),))
    )
    assert 'data-dz-open-entity="Invoice"' in html
    assert 'data-dz-open-chain="/app/invoice?status=overdue"' in html
