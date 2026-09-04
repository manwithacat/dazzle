"""Cycle 1719 — create CTAs stamp open-discovery attrs (list/empty/related)."""

from __future__ import annotations

from dazzle.render.fragment import CreateButton, FragmentRenderer
from dazzle.render.fragment.htmx import URL
from dazzle.render.fragment.primitives import DataListScroll, Table
from dazzle.render.fragment.renderer import FragmentRenderer as FR
from dazzle.render.open_discovery import create_cta_open_attrs, open_hop_label


def test_open_hop_label_create_via() -> None:
    assert open_hop_label("Ticket", "create") == "Create Ticket"
    assert open_hop_label("User", "new") == "Create User"
    assert open_hop_label("Task", "id") == "Open Task"
    assert open_hop_label("User", "assigned_to") == "Open User via Assigned To"


def test_create_cta_open_attrs_app_create_path() -> None:
    attrs = create_cta_open_attrs("/app/ticket/create")
    assert "data-dz-create-drill" in attrs
    assert 'data-dz-open-via="create"' in attrs
    assert 'data-dz-open-entity="Ticket"' in attrs
    assert 'data-dz-open-chain="/app/ticket/create"' in attrs
    assert "Create Ticket" in attrs


def test_create_cta_open_attrs_skips_placeholder() -> None:
    assert create_cta_open_attrs("#") == ""
    assert create_cta_open_attrs("") == ""
    assert create_cta_open_attrs("/marketing") == ""


def test_create_button_stamps_open_discovery() -> None:
    html = FragmentRenderer().render(
        CreateButton(
            href=URL("/app/ticket/create"),
            entity_name="Ticket",
            entity_title="Ticket",
        )
    )
    assert 'data-dazzle-action="Ticket.create"' in html
    assert "data-dz-create-drill" in html
    assert 'data-dz-open-via="create"' in html
    assert 'data-dz-open-entity="Ticket"' in html
    assert 'data-dz-open-chain="/app/ticket/create"' in html
    assert "Create Ticket" in html
    assert "New Ticket" in html


def test_create_button_non_app_href_skips_open() -> None:
    html = FragmentRenderer().render(CreateButton(href=URL("/x"), entity_name="Thing"))
    assert "data-dz-create-drill" not in html
    assert "data-dz-open-entity" not in html


def test_table_empty_action_stamps_open_discovery() -> None:
    html = FR().render(
        DataListScroll(
            table=Table(
                columns=("Name",),
                rows=(),
                skeleton=True,
                hx_endpoint="/api/ticket",
                caption="Tickets",
            ),
            table_id="ticket",
            page_size=25,
            aria_label="Tickets",
            empty_title="No tickets",
            empty_description="Create one to start.",
            empty_action_href="/app/ticket/create",
            empty_action_label="New Ticket",
        )
    )
    assert "data-dz-create-drill" in html
    assert 'data-dz-open-via="create"' in html
    assert 'data-dz-open-entity="Ticket"' in html
    assert "Create Ticket" in html
    assert "New Ticket" in html
