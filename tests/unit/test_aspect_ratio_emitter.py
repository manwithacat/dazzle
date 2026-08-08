"""aspect-ratio hyperpart emitter — unit pins (cycle 1758).

Field/media compose: logo_url/preview_url/photo_url thumbs mount
``.dz-aspect-ratio``. Fragment path: ``AspectRatio`` primitive.
"""

from __future__ import annotations

from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot
from dazzle.render.cell_chrome import _render_media_thumb_html
from dazzle.render.fragment import AspectRatio, FragmentRenderer, RawHTML, Text


def test_aspect_ratio_emit_mounts_dz_spine() -> None:
    html = FragmentRenderer().render(
        AspectRatio(
            child=Text("16:9"),
            ratio="16/9",
            width="10rem",
            aria_label="16:9 frame",
        )
    )
    assert 'class="dz-aspect-ratio"' in html
    assert 'data-dz-ratio="16/9"' in html
    assert 'style="width: 10rem"' in html
    assert 'aria-label="16:9 frame"' in html
    assert "16:9" in html


def test_aspect_ratio_presets() -> None:
    for ratio in ("1/1", "4/3", "16/9", "21/9"):
        html = FragmentRenderer().render(AspectRatio(child=Text("x"), ratio=ratio))  # type: ignore[arg-type]
        assert f'data-dz-ratio="{ratio}"' in html


def test_media_thumb_compose_uses_aspect_ratio() -> None:
    url = "https://placehold.co/96x96/0F172A/F8FAFC/png?text=AR"
    html = _render_media_thumb_html(url, alt="Asset")
    assert 'class="dz-aspect-ratio"' in html
    assert 'data-dz-ratio="1/1"' in html
    assert "dz-media-thumb" in html
    assert url in html


def test_aspect_ratio_with_raw_img_child() -> None:
    child = RawHTML('<img src="https://placehold.co/1.png" alt="x" />')
    html = FragmentRenderer().render(AspectRatio(child=child, ratio="4/3", width="8rem"))
    assert 'class="dz-aspect-ratio"' in html
    assert 'data-dz-ratio="4/3"' in html
    assert "<img " in html


def test_dsl_shapes_aspect_ratio_live() -> None:
    snap = shapes_snapshot()
    planned = set(snap.get("planned_ids") or [])
    assert "aspect-ratio" not in planned
    assert snap["next_planned"] != "aspect-ratio"
    assert snap["live"] >= 67
