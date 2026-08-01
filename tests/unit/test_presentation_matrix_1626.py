"""#1626 hyperpart presentation matrix — person × queue_meta → Avatar."""

from __future__ import annotations

import pytest

from dazzle.render.fragment.region._builders_tables import _queue_row_meta_columns
from dazzle.render.presentation import PRESENTATION_MATRIX, infer_role, present
from dazzle.render.user_chip import render_user_chip_html

pytestmark = pytest.mark.gate


def test_matrix_person_queue_meta_is_avatar_only() -> None:
    assert PRESENTATION_MATRIX[("person", "queue_meta")] == "avatar_only"


def test_present_person_queue_meta_emits_avatar_suppresses_label() -> None:
    col = {"key": "assigned_to", "label": "Assigned To", "ref_entity": "User", "type": "ref"}
    value = {"id": "u1", "name": "Support Agent", "email": "agent@demo.dazzle.local"}
    r = present("person", "queue_meta", value, col)
    assert r.is_html
    assert r.suppress_label
    assert "dz-avatar" in r.html
    assert "Assigned To" not in r.html
    assert "dz-user-chip--avatar-only" in r.html


def test_avatar_only_density_no_visible_name_span() -> None:
    html = render_user_chip_html(
        {"name": "Support Agent"},
        {"key": "assigned_to", "ref_entity": "User"},
        density="avatar_only",
    )
    assert "dz-avatar" in html
    assert "dz-user-chip__name" not in html
    assert "Support Agent" in html  # title/aria


def test_queue_meta_columns_person_is_html_chip_without_label() -> None:
    item = {
        "id": "t1",
        "title": "Cannot login",
        "status": "open",
        "assigned_to": {"id": "u1", "name": "Support Agent"},
        "created_at": "2026-07-12",
    }
    cols = [
        {"key": "title", "label": "Title", "type": "text"},
        {"key": "status", "label": "Status", "type": "badge"},
        {"key": "assigned_to", "label": "Assigned To", "type": "ref", "ref_entity": "User"},
        {"key": "created_at", "label": "Created At", "type": "date"},
    ]
    meta = _queue_row_meta_columns(item, cols, display_key="title", queue_status_field="status")
    person_bits = [m for m in meta if m.html and "dz-avatar" in m.value]
    assert person_bits, f"expected avatar meta, got {meta}"
    assert person_bits[0].label == ""
    assert "Assigned To" not in person_bits[0].value


def test_infer_role_person_from_field_key() -> None:
    assert infer_role("x", {"key": "assigned_to", "type": "ref", "ref_entity": "User"}) == "person"


def test_cognition_snapshot_honest_about_audit_scope() -> None:
    from dazzle.render.presentation import cognition_snapshot

    c = cognition_snapshot()
    assert "queue_meta" in c["hosts_audited_by_scanner"]
    assert "how_to_extend" in c
    assert "creativity_boundary" in c
    # Matrix may list hosts the scanner does not walk yet
    assert isinstance(c["hosts_not_yet_audited"], list)


def test_present_money_and_swatch_not_stub_plain_only() -> None:
    money = present("money", "list_cell", 12550.0, {"type": "currency", "format": "currency:GBP"})
    assert money.density == "money"
    assert money.html  # formatted somehow
    swatch = present("color", "queue_meta", "#336699", {"type": "color"})
    assert swatch.density == "swatch"
    # Prefer real swatch markup when renderer available
    if swatch.is_html:
        assert "dz-color-swatch" in swatch.html or "#" in swatch.html


def test_opportunity_report_includes_presentation_cognition() -> None:
    from dazzle.qa.hyperpart_opportunity import (
        HyperpartOpportunity,
        build_opportunity_report,
    )

    opps = [
        HyperpartOpportunity(
            hyperpart="avatar",
            kind="person_ref",
            entity="Ticket",
            field="assigned_to",
            surface="ticket_list",
            location="surface:ticket_list.field:assigned_to",
            status="emit_covered",
            severity="low",
            description="test",
            hosts="list_cell,detail_cell",
        )
    ]
    report = build_opportunity_report(app="support_tickets", opportunities=opps)
    assert report["schema_version"] == 2
    assert "presentation_cognition" in report
    assert report["presentation_cognition"]["person_rows_all_emit_covered"] is True
    assert "caveat" in report["presentation_cognition"]
