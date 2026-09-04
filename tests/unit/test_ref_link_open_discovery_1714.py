"""Cycle 1714 — person chip + non-person ref Link open discovery."""

from __future__ import annotations

from dazzle.render.fragment.htmx import URL
from dazzle.render.fragment.primitives.interactive import Link
from dazzle.render.fragment.region._shared import _render_typed_value
from dazzle.render.fragment.renderer import FragmentRenderer
from dazzle.render.open_discovery import drill_open_discovery_attrs
from dazzle.render.presentation import present
from dazzle.render.user_chip import wrap_user_chip_link


def test_hub_open_via_param_on_drill_attrs() -> None:
    attrs = drill_open_discovery_attrs("/app/user/u-9", via="assigned_to")
    assert 'data-dz-open-via="assigned_to"' in attrs
    assert 'data-dz-open-entity="User"' in attrs
    assert 'data-dz-open-chain="/app/user/u-9"' in attrs
    assert "Open User via Assigned To" in attrs
    assert 'data-dz-open-chain-via="assigned_to"' in attrs


def test_person_chip_link_stamps_open_discovery() -> None:
    chip = '<span class="dz-user-chip">Ada</span>'
    html = wrap_user_chip_link(
        chip,
        {"name": "Ada", "id": "u-1"},
        {"key": "assigned_to", "ref_route": "/app/user/{id}"},
    )
    assert "dz-user-chip-link" in html
    assert "data-dz-user-chip-drill" in html
    assert 'data-dz-open-entity="User"' in html
    assert 'data-dz-open-via="assigned_to"' in html
    assert 'data-dz-open-chain="/app/user/u-1"' in html
    assert "Open User via Assigned To" in html
    assert 'href="/app/user/u-1"' in html


def test_person_chip_without_route_skips_open() -> None:
    chip = '<span class="dz-user-chip">Ada</span>'
    html = wrap_user_chip_link(chip, {"name": "Ada", "id": "u-1"}, {"key": "author"})
    assert "data-dz-open-entity" not in html
    assert "data-dz-user-chip-drill" not in html


def test_present_person_list_cell_stamps_open_discovery() -> None:
    r = present(
        "person",
        "list_cell",
        {"name": "Ada", "id": "u-7"},
        {"key": "owner", "ref_route": "/app/user/{id}", "ref_entity": "User"},
    )
    assert r.is_html
    assert "data-dz-user-chip-drill" in (r.html or "")
    assert 'data-dz-open-via="owner"' in (r.html or "")
    assert 'data-dz-open-entity="User"' in (r.html or "")


def test_non_person_ref_link_stamps_open_discovery() -> None:
    html = FragmentRenderer().render(Link(label="INV-100", href=URL("/app/invoice/inv-100")))
    assert "dz-link" in html
    assert "data-dz-ref-link-drill" in html
    assert 'data-dz-open-entity="Invoice"' in html
    assert 'data-dz-open-via="id"' in html
    assert 'data-dz-open-chain="/app/invoice/inv-100"' in html
    assert "Open Invoice" in html


def test_nav_home_link_skips_open_discovery() -> None:
    html = FragmentRenderer().render(Link(label="Home", href=URL("/app"), data_action="nav.home"))
    assert "dz-link" in html
    assert "data-dz-open-entity" not in html
    assert "data-dz-ref-link-drill" not in html


def test_region_non_person_ref_emits_link_with_open() -> None:
    frag = _render_typed_value(
        {"project": {"id": "p-1", "__display__": "Alpha"}},
        {
            "type": "ref",
            "key": "project",
            "ref_entity": "Project",
            "ref_route": "/app/project/{id}",
        },
    )
    assert isinstance(frag, Link)
    html = FragmentRenderer().render(frag)
    assert "data-dz-ref-link-drill" in html
    assert 'data-dz-open-entity="Project"' in html
    assert "Alpha" in html


def test_region_person_ref_chip_stamps_open() -> None:
    frag = _render_typed_value(
        {"assigned_to": {"id": "u1", "name": "Ada Lovelace", "__display__": "Ada Lovelace"}},
        {
            "key": "assigned_to",
            "type": "ref",
            "ref_entity": "User",
            "ref_route": "/app/user/{id}",
        },
    )
    assert hasattr(frag, "html")
    assert "data-dz-user-chip-drill" in frag.html
    assert 'data-dz-open-via="assigned_to"' in frag.html
    assert 'data-dz-open-entity="User"' in frag.html
