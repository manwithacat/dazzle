"""Workspace enum FilterBar must not dump snake_case (oral #147)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_columns import (
    _field_to_entity_column,
    build_entity_columns,
    build_surface_columns,
    enum_filter_options,
)
from dazzle.http.runtime.workspace_csv import _csv_typed_cell
from dazzle.http.runtime.workspace_region_computes import compute_filter_columns_and_active
from dazzle.render.fragment import URL, FilterBar, FilterColumn, FragmentRenderer
from dazzle.render.fragment.format_cell import format_cell
from dazzle.render.fragment.renderer._render_interactive import leftover_honest_catalog_id


def test_enum_filter_options_are_clerk_labels() -> None:
    assert enum_filter_options(["open", "in_progress", "on_track"]) == [
        ("open", "Open"),
        ("in_progress", "In Progress"),
        ("on_track", "On Track"),
    ]
    assert format_cell("in_progress", "badge") == "In Progress"


def test_enum_filter_options_leftover_stays_put() -> None:
    assert enum_filter_options(["zzz", "in_progress"]) == [
        ("zzz", "zzz"),
        ("in_progress", "In Progress"),
    ]


def test_ticket_list_status_filter_is_in_progress_not_token() -> None:
    spec = load_project(Path("examples/support_tickets"))
    ticket = spec.get_entity("Ticket")
    assert ticket is not None
    surf = next(s for s in spec.surfaces if s.name == "ticket_list")
    cols = build_surface_columns(ticket, surf, spec.enums)
    status = next(c for c in cols if c["key"] == "status")
    assert status["type"] == "badge"
    assert status["filterable"] is True
    assert status["filter_options"] == [
        ("open", "Open"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]
    labels = [lab for _, lab in status["filter_options"]]
    assert "In Progress" in labels
    assert "in_progress" not in labels


def test_entity_enum_column_filter_is_clerk_label() -> None:
    spec = load_project(Path("examples/support_tickets"))
    ticket = spec.get_entity("Ticket")
    assert ticket is not None
    status = next(f for f in ticket.fields if f.name == "status")
    col = _field_to_entity_column(status, ticket, spec.enums)
    assert col is not None
    assert col["filter_options"] == [
        ("open", "Open"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]
    sla = next(c for c in build_entity_columns(ticket, spec.enums) if c["key"] == "sla_state")
    assert ("on_track", "On Track") in sla["filter_options"]
    assert "on_track" not in [lab for _, lab in sla["filter_options"]]


def test_enum_filter_query_values_stay_tokens() -> None:
    columns = [
        {
            "key": "status",
            "label": "Status",
            "filterable": True,
            "filter_options": enum_filter_options(["open", "in_progress"]),
        }
    ]
    _, active = compute_filter_columns_and_active(columns, {"filter_status": "in_progress"})
    assert active["status"] == "in_progress"
    _, leftover = compute_filter_columns_and_active(columns, {"filter_status": "zzz"})
    assert "status" not in leftover
    known = ("open", "in_progress")
    assert leftover_honest_catalog_id("zzz", known, "", allow_empty_rest=True) == ""
    assert leftover_honest_catalog_id("in_progress", known, "", allow_empty_rest=True) == (
        "in_progress"
    )


def test_enum_filter_html_is_in_progress_not_token() -> None:
    html = FragmentRenderer().render(
        FilterBar(
            endpoint=URL("/app/workspaces/ticket_queue"),
            region_name="open_queue",
            columns=(
                FilterColumn(
                    key="status",
                    label="Status",
                    options=tuple(enum_filter_options(["open", "in_progress", "resolved"])),
                ),
            ),
        )
    )
    assert 'value="in_progress"' in html
    assert ">In Progress<" in html
    assert ">Open<" in html
    assert ">in_progress<" not in html


def test_csv_badge_still_humanizes_tuple_filter_options() -> None:
    col = {
        "key": "status",
        "type": "badge",
        "filter_options": enum_filter_options(["open", "in_progress"]),
    }
    assert _csv_typed_cell("in_progress", col) == "In Progress"
    assert _csv_typed_cell("zzz", col) == "zzz"


def test_enum_filter_leftover_html_stays_put() -> None:
    html = FragmentRenderer().render(
        FilterBar(
            endpoint=URL("/app/workspaces/ticket_queue"),
            region_name="open_queue",
            columns=(
                FilterColumn(
                    key="status",
                    label="Status",
                    options=tuple(enum_filter_options(["zzz", "in_progress"])),
                ),
            ),
        )
    )
    assert 'value="zzz"' in html
    assert ">zzz<" in html
    assert ">In Progress<" in html
    assert ">in_progress<" not in html
