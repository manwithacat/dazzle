"""List/queue email and phone cells must be tappable (oral #173)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.ir.fields import FieldTypeKind
from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_columns import (
    build_surface_columns,
    field_kind_to_col_type,
)
from dazzle.http.runtime.workspace_csv import _csv_cell
from dazzle.page.converters.template_compiler import _field_type_to_column_type
from dazzle.render.channel_cell import (
    clerk_email_cell_html,
    clerk_email_display,
    clerk_email_href,
    clerk_phone_cell_html,
    clerk_phone_display,
    clerk_phone_href,
    email_field_name,
    phone_field_name,
)
from dazzle.render.fragment.format_cell import format_cell
from dazzle.render.fragment.region._shared import _render_typed_value
from dazzle.render.fragment.renderer._data_row import _render_cell_display


def _contact_fields():
    spec = load_project(Path("examples/contact_manager"))
    contact = spec.get_entity("Contact")
    assert contact is not None
    email = next(f for f in contact.fields if f.name == "email")
    phone = next(f for f in contact.fields if f.name == "phone")
    surface = next(s for s in spec.surfaces if s.name == "contact_list")
    return spec, contact, email, phone, surface


def test_contact_list_email_and_phone_are_channel_cells() -> None:
    spec, contact, email, phone, surface = _contact_fields()
    assert email.type.kind == FieldTypeKind.EMAIL
    assert email_field_name("email")
    assert phone_field_name("phone")
    assert field_kind_to_col_type(email, contact) == "email"
    assert field_kind_to_col_type(phone, contact) == "phone"
    assert _field_type_to_column_type(email, "email") == "email"
    assert _field_type_to_column_type(phone, "phone") == "phone"
    columns = build_surface_columns(contact, surface, spec.enums)
    assert next(c for c in columns if c["key"] == "email")["type"] == "email"
    assert next(c for c in columns if c["key"] == "phone")["type"] == "phone"


def test_channel_name_heuristics_do_not_map_counts_or_channel_enum() -> None:
    assert email_field_name("contact_email")
    assert email_field_name("signatory_email")
    assert not email_field_name("email_count")
    assert not email_field_name("email_verified")
    assert phone_field_name("mobile")
    assert phone_field_name("work_phone")
    assert not phone_field_name("channel")
    assert not phone_field_name("megaphone")


def test_clerk_email_split_leftover_and_empty() -> None:
    mailbox = "ruth.griffiths@northwind.example"
    assert clerk_email_href(mailbox) == f"mailto:{mailbox}"
    assert clerk_email_display(mailbox) == mailbox
    assert clerk_email_href("zzz") is None
    assert clerk_email_display("zzz") == "zzz"
    assert clerk_email_href("") is None
    assert clerk_email_display("") == ""
    assert clerk_email_href("not-an-email") is None
    assert clerk_email_href("javascript:alert(1)") is None
    assert format_cell(mailbox, "email") == mailbox
    assert format_cell("zzz", "email") == "zzz"


def test_clerk_phone_split_leftover_and_empty() -> None:
    number = "+44 20 7946 0936"
    assert clerk_phone_href(number) == "tel:+442079460936"
    assert clerk_phone_display(number) == number
    assert clerk_phone_href("02079460936") == "tel:02079460936"
    assert clerk_phone_href("zzz") is None
    assert clerk_phone_display("zzz") == "zzz"
    assert clerk_phone_href("") is None
    assert clerk_phone_display("") == ""
    assert clerk_phone_href("javascript:alert(1)") is None
    assert clerk_phone_href("12") is None
    assert format_cell(number, "phone") == number
    assert format_cell("zzz", "phone") == "zzz"


def test_list_html_renders_mailto_and_tel_not_dead_text() -> None:
    mailbox = "ruth.griffiths@northwind.example"
    email_html = _render_cell_display({"key": "email", "label": "Email", "type": "email"}, mailbox)
    assert "mailto:ruth.griffiths@northwind.example" in email_html
    assert 'class="dz-channel-link dz-channel-link--email"' in email_html
    assert mailbox in email_html
    leftover_email = _render_cell_display({"key": "email", "type": "email"}, "zzz")
    assert "zzz" in leftover_email
    assert "mailto:" not in leftover_email
    assert clerk_email_cell_html("") == ""
    assert _render_cell_display({"key": "email", "type": "email"}, "") == "—"

    number = "+44 20 7946 0936"
    phone_html = _render_cell_display({"key": "phone", "label": "Phone", "type": "phone"}, number)
    assert "tel:+442079460936" in phone_html
    assert 'class="dz-channel-link dz-channel-link--phone"' in phone_html
    assert number in phone_html
    leftover_phone = _render_cell_display({"key": "phone", "type": "phone"}, "zzz")
    assert "zzz" in leftover_phone
    assert "tel:" not in leftover_phone
    assert clerk_phone_cell_html("") == ""
    assert _render_cell_display({"key": "phone", "type": "phone"}, "") == "—"


def test_workspace_typed_value_renders_channel_links() -> None:
    mailbox = "ruth.griffiths@northwind.example"
    frag = _render_typed_value(
        {"email": mailbox},
        {"key": "email", "label": "Email", "type": "email"},
    )
    html = getattr(frag, "html", str(frag))
    assert "mailto:" in html
    leftover = _render_typed_value({"email": "zzz"}, {"key": "email", "type": "email"})
    leftover_html = getattr(leftover, "html", str(leftover))
    assert "zzz" in leftover_html
    assert "mailto:" not in leftover_html

    number = "+44 20 7946 0936"
    phone_frag = _render_typed_value(
        {"phone": number},
        {"key": "phone", "label": "Phone", "type": "phone"},
    )
    phone_html = getattr(phone_frag, "html", str(phone_frag))
    assert "tel:+442079460936" in phone_html


def test_csv_channel_is_plain_text_not_html() -> None:
    mailbox = "ruth.griffiths@northwind.example"
    email_col = {"key": "email", "label": "Email", "type": "email"}
    assert _csv_cell({"email": mailbox}, email_col) == mailbox
    assert _csv_cell({"email": "zzz"}, email_col) == "zzz"
    assert _csv_cell({"email": ""}, email_col) == ""
    number = "+44 20 7946 0936"
    phone_col = {"key": "phone", "label": "Phone", "type": "phone"}
    assert _csv_cell({"phone": number}, phone_col) == number
    assert _csv_cell({"phone": "zzz"}, phone_col) == "zzz"
