"""Issue #1029 phase 3 (v0.66.135): regression tests for the LIST
adapter's CreateButton in the surface header.

Pre-fix, the adapter emitted a plain `Link(label="Create X")` —
missing the `data-dazzle-action="<Entity>.create"` attribute the
RBAC contract checker keys off, plus the legacy template's `+`
icon SVG. The button label also didn't match the legacy "New X"
shape.

Fix: new `CreateButton` primitive carrying the full legacy contract
(href + data-dazzle-action + plus-icon SVG + label). Adapter wires
it when both `create_url` and `entity_name` are set."""

from __future__ import annotations

import pytest

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.render.fragment import URL, CreateButton, FragmentRenderer


class _Surface:
    name = "contact_list"
    title = "Contacts"
    mode = SurfaceMode.LIST
    entity_ref = "Contact"


def _ctx(create_url: str = "/contacts/create") -> dict:
    return {
        "items": [{"id": "1", "name": "Alice"}],
        "columns": [{"key": "name", "label": "Name", "type": "text"}],
        "endpoint": "/api/contacts",
        "total": 1,
        "page": 1,
        "page_size": 20,
        "region_name": "contact_table",
        "empty_message": "No contacts yet",
        "create_url": create_url,
        "detail_url_template": "",
    }


def _render_list(ctx: dict) -> str:
    adapter = FragmentSurfaceAdapter()
    return FragmentRenderer().render(adapter._build_list(_Surface(), ctx))


def test_list_emits_create_button_when_url_and_entity_set() -> None:
    """CreateButton appears in the surface header with the legacy
    contract attributes."""
    html = _render_list(_ctx())
    assert 'href="/contacts/create"' in html
    assert 'data-dazzle-action="Contact.create"' in html
    assert 'class="dz-button-primary"' in html


def test_list_create_button_emits_plus_icon_svg() -> None:
    """The 12×12 plus-icon SVG with `d="M6 1v10M1 6h10"` matches
    legacy `filterable_table.html` byte-for-byte."""
    html = _render_list(_ctx())
    assert 'd="M6 1v10M1 6h10"' in html
    assert 'viewBox="0 0 12 12"' in html
    assert 'aria-hidden="true"' in html


def test_list_create_button_default_label_is_new_entity() -> None:
    """Default label is `New {entity_name}` — matches legacy template."""
    html = _render_list(_ctx())
    assert ">" in html
    assert "New Contact" in html
    # Old "Create Contact" label should NOT appear.
    assert "Create Contact" not in html


def test_list_omits_create_button_when_url_missing() -> None:
    """No `create_url` → no CreateButton in the header."""
    html = _render_list(_ctx(create_url=""))
    assert "data-dazzle-action" not in html
    assert "dz-button-primary" not in html


# ── CreateButton primitive direct tests ──


def test_create_button_validates_entity_name() -> None:
    """Empty entity_name raises — needed for the data-dazzle-action
    attribute to round-trip."""
    with pytest.raises(ValueError, match="entity_name"):
        CreateButton(href=URL("/x"), entity_name="")


def test_create_button_custom_label_overrides_default() -> None:
    """When `label` is non-empty, used verbatim — for DSL surfaces
    that declare a custom action_primary label."""
    b = CreateButton(href=URL("/x"), entity_name="Account", label="Add new account")
    html = FragmentRenderer().render(b)
    assert "Add new account" in html
    assert ">New Account<" not in html


def test_create_button_default_label_replaces_underscores() -> None:
    """Multi-word entity names (e.g. `task_assignment`) emit the
    label with underscores replaced by spaces — `New task assignment`."""
    b = CreateButton(href=URL("/x"), entity_name="task_assignment")
    html = FragmentRenderer().render(b)
    assert ">New task assignment<" in html


def test_create_button_data_action_uses_entity_name_verbatim() -> None:
    """`data-dazzle-action` keeps the exact entity_name (case +
    underscores) — the RBAC contract checker matches on the IR-form
    name, not the display form."""
    b = CreateButton(href=URL("/x"), entity_name="task_assignment")
    html = FragmentRenderer().render(b)
    assert 'data-dazzle-action="task_assignment.create"' in html


def test_create_button_escapes_user_supplied_label() -> None:
    """Custom label is escape_attr-protected — a malicious label
    can't break out of the anchor body."""
    b = CreateButton(href=URL("/x"), entity_name="Item", label="</a><script>alert(1)</script>")
    html = FragmentRenderer().render(b)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_create_button_escapes_href_attribute() -> None:
    """URL escapes attribute-context characters."""
    b = CreateButton(href=URL("/x?q=1&r=2"), entity_name="Item")
    html = FragmentRenderer().render(b)
    # `&` in URL becomes `&amp;` inside the href attribute.
    assert "&amp;r=2" in html
