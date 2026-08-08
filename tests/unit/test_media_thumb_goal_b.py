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
