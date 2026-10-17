"""Post-5.8 Goal B media — image thumbs + palette types on entity columns."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.workspace_columns import (
    build_entity_columns,
    field_kind_to_col_type,
)
from dazzle.render.cell_chrome import (
    _render_media_thumb_html,
    _safe_media_image_url,
    related_card_media_and_text,
)


def test_safe_media_url_accepts_placehold() -> None:
    url = "https://placehold.co/128x128/0F172A/F59E0B/png?text=NW"
    assert _safe_media_image_url(url) == url


def test_safe_media_url_rejects_javascript_and_http() -> None:
    assert _safe_media_image_url("javascript:alert(1)") is None
    assert _safe_media_image_url("http://placehold.co/1.png") is None
    assert _safe_media_image_url("https://evil.example/x.png") is None


def test_media_thumb_html_emits_img() -> None:
    url = "https://placehold.co/64x64/111111/FFFFFF/png?text=A"
    html = _render_media_thumb_html(url, alt="Acme brand")
    assert "dz-media-thumb" in html
    assert 'src="https://placehold.co/64x64/111111/FFFFFF/png?text=A"' in html
    assert "data-dz-media-thumb" in html
    assert 'alt="Acme brand"' in html
    # dual-lock aspect-ratio media frame (field/media compose path)
    assert 'class="dz-aspect-ratio"' in html
    assert 'data-dz-ratio="1/1"' in html
    assert "data-dz-media-frame" in html


@pytest.mark.parametrize(
    ("label", "alt"),
    [
        pytest.param("Photo Url", "Photo", id="schema-label-photo-url"),
        pytest.param("photo_url", "Photo", id="field-name-photo-url"),
        pytest.param("Logo Url", "Photo", id="schema-label-logo-url"),
        pytest.param("Hana Design Lead", "Hana Design Lead", id="human-label-kept"),
    ],
)
def test_media_thumb_alt_sanitizes_schema_field_labels(label: str, alt: str) -> None:
    """Cycle 1951: alt must not dump 'Photo Url' schema labels on team cards."""
    html = _render_media_thumb_html(
        "https://placehold.co/64x64/111111/FFFFFF/png?text=A", alt=label
    )

    assert f'alt="{alt}"' in html
    if label != alt:
        assert label not in html


def test_field_kind_palette_and_logo_names() -> None:
    logo = SimpleNamespace(name="logo_url", type=SimpleNamespace(kind="url"))
    color = SimpleNamespace(name="primary_color", type=SimpleNamespace(kind="str"))
    assert field_kind_to_col_type(logo) == "image"
    assert field_kind_to_col_type(color) == "color"


def test_related_card_preview_url_is_thumb_not_title() -> None:
    """Related status_cards must not dump preview_url as primary (oral #135)."""
    url = "https://placehold.co/320x200/0F172A/F59E0B/png?text=NW+LOGO+v3"
    thumb, texts = related_card_media_and_text((url, "Primary logo (SVG)", "3"))
    assert "dz-media-thumb" in thumb
    assert url in thumb
    assert url not in texts
    assert texts[0] == "Primary logo (SVG)"
    assert "3" in texts


def test_related_card_leftover_url_stays_put() -> None:
    thumb, texts = related_card_media_and_text(("zzz", "Primary logo (SVG)", "3"))
    assert thumb == ""
    assert texts[0] == "zzz"
    assert "Primary logo (SVG)" in texts


def test_related_card_off_allowlist_url_stays_put() -> None:
    url = "https://evil.example/creative.png"
    thumb, texts = related_card_media_and_text((url, "Primary logo (SVG)"))
    assert thumb == ""
    assert texts[0] == url


def test_detail_display_type_promotes_media_keys() -> None:
    """VIEW form kinds (url/text) must still thumb/swatch on detail hubs."""
    from dazzle.http.runtime.renderers.fragment_adapter import _detail_display_type

    assert (
        _detail_display_type({"key": "logo_url", "kind": "text", "value": "https://x"}) == "image"
    )
    assert (
        _detail_display_type({"key": "preview_url", "kind": "url", "value": "https://x"}) == "image"
    )
    assert (
        _detail_display_type({"key": "primary_color", "kind": "text", "value": "#111111"})
        == "color"
    )
    assert _detail_display_type({"key": "notes", "kind": "textarea", "value": "hi"}) == "text"


def test_detail_field_value_emits_media_thumb() -> None:
    from dazzle.http.runtime.renderers.fragment_adapter import _detail_field_value
    from dazzle.render.fragment import FragmentRenderer, RawHTML

    url = "https://placehold.co/128x128/1C1917/EA580C/png?text=AW"
    frag = _detail_field_value({"key": "logo_url", "kind": "text", "label": "Logo", "value": url})
    assert isinstance(frag, RawHTML)
    html = FragmentRenderer().render(frag)
    assert "dz-media-thumb" in html
    assert url in html
    assert 'class="dz-aspect-ratio"' in html


def test_fitness_repr_fields_drive_entity_fallback_columns() -> None:
    """Cycle 1925: fitness.repr_fields projects card columns (not raw schema dump)."""
    from types import SimpleNamespace

    def _field(name: str, kind: str = "str") -> SimpleNamespace:
        return SimpleNamespace(
            name=name,
            type=SimpleNamespace(kind=kind, enum_values=None, ref_entity=None, currency_code=None),
        )

    user = SimpleNamespace(
        name="User",
        fields=[
            _field("id", "uuid"),
            _field("email"),
            _field("name"),
            _field("role", "enum"),
            _field("department"),
            _field("photo_url"),
            _field("is_active", "bool"),
        ],
        state_machine=None,
        fitness=SimpleNamespace(repr_fields=["name", "role", "department"]),
    )
    # photo_url is image by name heuristic even if kind is str; injected only
    # for card-like displays (#1792 U5 — list displays: test_list_columns_1792).
    cols = build_entity_columns(user, media_thumbs=True)
    keys = [c["key"] for c in cols]
    assert "photo_url" in keys  # media inject
    assert "name" in keys
    assert "role" in keys
    assert "department" in keys
    assert "email" not in keys
    assert "is_active" not in keys


def test_fitness_repr_fields_skip_column_economy_truncation() -> None:
    """Cycle 1929: economy must not drop ticket_number from 7-field fitness repr."""
    from types import SimpleNamespace

    def _field(name: str, kind: str = "str") -> SimpleNamespace:
        return SimpleNamespace(
            name=name,
            type=SimpleNamespace(kind=kind, enum_values=None, ref_entity=None, currency_code=None),
        )

    ticket = SimpleNamespace(
        name="Ticket",
        fields=[
            _field("id", "uuid"),
            _field("ticket_number"),
            _field("title"),
            _field("status", "enum"),
            _field("priority", "enum"),
            _field("sla_state", "enum"),
            _field("category", "enum"),
            _field("assigned_to", "ref"),
        ],
        state_machine=None,
        fitness=SimpleNamespace(
            repr_fields=[
                "ticket_number",
                "title",
                "status",
                "priority",
                "sla_state",
                "category",
                "assigned_to",
            ]
        ),
    )
    keys = [c["key"] for c in build_entity_columns(ticket)]
    assert keys[0] == "ticket_number"
    assert "title" in keys
    assert len(keys) >= 7


def test_support_tickets_ticket_repr_includes_ticket_number() -> None:
    """#1304 agent_tickets queues must keep AAA-001 identity in fitness projection."""

    text = Path("examples/support_tickets/dsl/app.dsl").read_text(encoding="utf-8")
    start = text.index('entity Ticket "Support Ticket"')
    block = text[start : text.index("entity Comment")]
    assert "ticket_number" in block.split("repr_fields:")[1].split("]")[0]


def test_simple_task_user_repr_excludes_admin_schema_on_roster() -> None:
    """agency_lead: team_roster/by_department use fitness chips, not Photo Url dump."""

    text = Path("examples/simple_task/dsl/app.dsl").read_text(encoding="utf-8")
    start = text.index('entity User "Team Member"')
    block = text[start : text.index('entity Task "Task"')]
    line = block.split("repr_fields:")[1].split("\n")[0]
    assert "name" in line and "role" in line and "department" in line
    assert "photo_url" not in line and "email" not in line and "is_active" not in line
