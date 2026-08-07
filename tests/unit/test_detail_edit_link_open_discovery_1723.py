"""Cycle 1723 — detail chrome Edit/Create Link open-discovery (not VIEW ref hop).

Row pencil (1721) already stamps ``data-dz-update-drill``. Detail VIEW primary
Edit is a ``Link`` via ``fragment_adapter._build_detail_actions``; before this
cycle ``_emit_link`` treated ``/app/<entity>/<id>/edit`` as a generic ref drill
(``data-dz-ref-link-drill`` + ``Open {Entity}``), which misled attr-first agents.
"""

from __future__ import annotations

from dazzle.render.fragment.htmx import URL
from dazzle.render.fragment.primitives.interactive import Link
from dazzle.render.fragment.renderer import FragmentRenderer


def test_detail_edit_link_stamps_update_drill() -> None:
    html = FragmentRenderer().render(
        Link(
            label="Edit",
            href=URL("/app/ticket/t-9/edit"),
            data_action="Ticket.edit",
        )
    )
    assert "dz-link" in html
    assert 'data-dazzle-action="Ticket.edit"' in html
    assert "data-dz-update-drill" in html
    assert 'data-dz-open-via="edit"' in html
    assert 'data-dz-open-entity="Ticket"' in html
    assert 'data-dz-open-chain="/app/ticket/t-9/edit"' in html
    assert "Edit Ticket" in html
    # Must not look like a VIEW / FK ref hop
    assert "data-dz-ref-link-drill" not in html
    assert "Open Ticket" not in html


def test_detail_edit_link_path_alone_without_data_action() -> None:
    """Path ending in /edit is enough even without data_action."""
    html = FragmentRenderer().render(Link(label="Edit", href=URL("/app/user/u-1/edit")))
    assert "data-dz-update-drill" in html
    assert 'data-dz-open-via="edit"' in html
    assert "Edit User" in html
    assert "data-dz-ref-link-drill" not in html


def test_view_primary_create_link_stamps_create_drill() -> None:
    """EX-048 action_primary may swap VIEW chrome to a create CTA Link."""
    html = FragmentRenderer().render(
        Link(
            label="New Ticket",
            href=URL("/app/ticket/create"),
            data_action="Ticket.primary",
        )
    )
    assert "data-dz-create-drill" in html
    assert 'data-dz-open-via="create"' in html
    assert 'data-dz-open-entity="Ticket"' in html
    assert "Create Ticket" in html
    assert "data-dz-ref-link-drill" not in html
    assert "data-dz-update-drill" not in html


def test_ref_detail_link_still_view_open() -> None:
    """Non-edit entity detail Links keep ref-link VIEW hop grammar."""
    html = FragmentRenderer().render(Link(label="INV-100", href=URL("/app/invoice/inv-100")))
    assert "data-dz-ref-link-drill" in html
    assert 'data-dz-open-via="id"' in html
    assert "Open Invoice" in html
    assert "data-dz-update-drill" not in html
    assert "data-dz-create-drill" not in html


def test_edit_data_action_with_query_string() -> None:
    html = FragmentRenderer().render(
        Link(
            label="Edit",
            href=URL("/app/ticket/t-2/edit?focus=title"),
            data_action="Ticket.edit",
        )
    )
    assert "data-dz-update-drill" in html
    assert 'data-dz-open-via="edit"' in html
    assert "Edit Ticket" in html
