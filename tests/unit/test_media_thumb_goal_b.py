"""Post-5.8 Goal B media — image thumbs + palette types on entity columns."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.http.runtime.workspace_columns import (
    build_entity_columns,
    field_kind_to_col_type,
)
from dazzle.render.cell_chrome import (
    _render_media_thumb_html,
    _safe_media_image_url,
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
    html = _render_media_thumb_html(url, alt="Logo")
    assert "dz-media-thumb" in html
    assert 'src="https://placehold.co/64x64/111111/FFFFFF/png?text=A"' in html
    assert "data-dz-media-thumb" in html
    # dual-lock aspect-ratio media frame (field/media compose path)
    assert 'class="dz-aspect-ratio"' in html
    assert 'data-dz-ratio="1/1"' in html
    assert "data-dz-media-frame" in html


def test_field_kind_palette_and_logo_names() -> None:
    logo = SimpleNamespace(name="logo_url", type=SimpleNamespace(kind="url"))
    color = SimpleNamespace(name="primary_color", type=SimpleNamespace(kind="str"))
    assert field_kind_to_col_type(logo) == "image"
    assert field_kind_to_col_type(color) == "color"


def test_design_studio_brand_entity_columns_media() -> None:
    spec = load_project_appspec(Path("examples/design_studio"))
    brand = next(e for e in spec.domain.entities if e.name == "Brand")
    by = {c["key"]: c["type"] for c in build_entity_columns(brand)}
    assert by["logo_url"] == "image"
    assert by["primary_color"] == "color"
    assert by["secondary_color"] == "color"


def test_design_studio_asset_preview_column() -> None:
    spec = load_project_appspec(Path("examples/design_studio"))
    asset = next(e for e in spec.domain.entities if e.name == "Asset")
    by = {c["key"]: c["type"] for c in build_entity_columns(asset)}
    assert by.get("preview_url") == "image"


def test_asset_seeds_have_preview_urls() -> None:
    path = Path("examples/design_studio/dsl/seeds/demo_data/Asset.jsonl")
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    assert len(lines) >= 8
    import json

    with_preview = 0
    for ln in lines:
        row = json.loads(ln)
        pu = str(row.get("preview_url") or "")
        if pu.startswith("https://placehold.co/"):
            with_preview += 1
    assert with_preview >= 8


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

    from dazzle.http.runtime.workspace_columns import build_entity_columns

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
    # photo_url is image by name heuristic even if kind is str
    cols = build_entity_columns(user)
    keys = [c["key"] for c in cols]
    assert "photo_url" in keys  # media inject
    assert "name" in keys
    assert "role" in keys
    assert "department" in keys
    assert "email" not in keys
    assert "is_active" not in keys


def test_prefer_fitness_repr_helper_documents_card_like_displays() -> None:
    """CARD_LIKE helper remains for shape docs; fitness is authoritative when set (1928)."""
    from dazzle.http.runtime.workspace_columns import prefer_fitness_repr_for_display

    assert prefer_fitness_repr_for_display("grid") is True
    assert prefer_fitness_repr_for_display("media_shelf") is True
    # Helper still classifies queue as non-card; route_builder uses fitness for queues too.
    assert prefer_fitness_repr_for_display("queue") is False


def test_support_tickets_ticket_repr_includes_ticket_number() -> None:
    """#1304 agent_tickets queues must keep AAA-001 identity in fitness projection."""
    from pathlib import Path

    text = Path("examples/support_tickets/dsl/app.dsl").read_text(encoding="utf-8")
    start = text.index('entity Ticket "Support Ticket"')
    block = text[start : text.index("entity Comment")]
    assert "ticket_number" in block.split("repr_fields:")[1].split("]")[0]


def test_fieldtest_device_repr_includes_serial_number() -> None:
    """Device queues must keep unique serial in fitness projection (cycle 1928)."""
    from pathlib import Path

    text = Path("examples/fieldtest_hub/dsl/app.dsl").read_text(encoding="utf-8")
    start = text.index('entity Device "Device"')
    block = text[start : text.index("entity Tester")]
    assert "serial_number" in block.split("repr_fields:")[1].split("]")[0]


def test_simple_task_user_repr_excludes_admin_schema_on_roster() -> None:
    """agency_lead: team_roster/by_department use fitness chips, not Photo Url dump."""
    from pathlib import Path

    text = Path("examples/simple_task/dsl/app.dsl").read_text(encoding="utf-8")
    start = text.index('entity User "Team Member"')
    block = text[start : text.index('entity Task "Task"')]
    line = block.split("repr_fields:")[1].split("\n")[0]
    assert "name" in line and "role" in line and "department" in line
    assert "photo_url" not in line and "email" not in line and "is_active" not in line
