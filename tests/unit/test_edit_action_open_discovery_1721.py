"""Cycle 1721 — row edit pencil stamps open-discovery attrs (VIEW/create parity)."""

from __future__ import annotations

from dazzle.render.fragment.primitives import RowCapabilities
from dazzle.render.fragment.renderer._data_row import render_data_row
from dazzle.render.open_discovery import edit_action_open_attrs, open_hop_label


def test_open_hop_label_edit_via() -> None:
    assert open_hop_label("Ticket", "edit") == "Edit Ticket"
    assert open_hop_label("User", "edit") == "Edit User"
    assert open_hop_label("Task", "id") == "Open Task"
    assert open_hop_label("Ticket", "create") == "Create Ticket"


def test_edit_action_open_attrs_app_edit_path() -> None:
    attrs = edit_action_open_attrs("/app/ticket/t-9/edit")
    assert "data-dz-update-drill" in attrs
    assert 'data-dz-open-via="edit"' in attrs
    assert 'data-dz-open-entity="Ticket"' in attrs
    assert 'data-dz-open-chain="/app/ticket/t-9/edit"' in attrs
    assert "Edit Ticket" in attrs
    assert 'data-dz-open-role="primary"' in attrs


def test_edit_action_open_attrs_skips_placeholder() -> None:
    assert edit_action_open_attrs("#") == ""
    assert edit_action_open_attrs("") == ""
    assert edit_action_open_attrs("/tasks/abc/edit") == ""  # non-/app/


def test_data_row_edit_pencil_stamps_open_discovery() -> None:
    html = render_data_row(
        [{"key": "title", "type": "str"}],
        {"id": "t-9", "title": "Ship edit open"},
        RowCapabilities(drill=True, update=True),
        detail_url_template="/app/ticket/{id}",
        entity_name="Ticket",
        api_endpoint="/api/tickets",
    )
    assert 'data-dazzle-action="Ticket.edit"' in html
    assert 'href="/app/ticket/t-9/edit"' in html
    assert "data-dz-update-drill" in html
    assert 'data-dz-open-via="edit"' in html
    assert 'data-dz-open-entity="Ticket"' in html
    assert 'data-dz-open-chain="/app/ticket/t-9/edit"' in html
    assert "Edit Ticket" in html
    # VIEW primary still present
    assert 'data-dazzle-action="Ticket.view"' in html
    assert 'data-dz-open-label="Open Ticket"' in html or 'title="Open Ticket"' in html


def test_data_row_edit_non_app_path_skips_open() -> None:
    """Characterization paths (/tasks/…) keep legacy aria; no open stamp."""
    html = render_data_row(
        [{"key": "name", "type": "str"}],
        {"id": "abc-123", "name": "Ada"},
        RowCapabilities(drill=True, update=True),
        detail_url_template="/tasks/{id}",
        entity_name="Task",
        api_endpoint="/api/tasks",
    )
    assert 'href="/tasks/abc-123/edit"' in html
    assert 'data-dazzle-action="Task.edit"' in html
    assert "data-dz-update-drill" not in html
    assert 'aria-label="Edit Ada"' in html or "aria-label=" in html


def test_data_row_no_edit_when_update_denied() -> None:
    html = render_data_row(
        [{"key": "title", "type": "str"}],
        {"id": "t-1", "title": "Read only"},
        RowCapabilities(drill=True, update=False),
        detail_url_template="/app/ticket/{id}",
        entity_name="Ticket",
        api_endpoint="/api/tickets",
    )
    assert "Ticket.edit" not in html
    assert "data-dz-update-drill" not in html
    assert 'data-dazzle-action="Ticket.view"' in html
