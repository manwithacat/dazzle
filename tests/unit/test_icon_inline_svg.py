"""Icon primitive + data-lucide sites render inline SVG from the registry."""

from dazzle.render.fragment import Icon
from dazzle.render.fragment.icon_html import lucide_icon_html
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(fragment: object) -> str:
    return FragmentRenderer().render(fragment)  # type: ignore[arg-type]


def test_known_icon_renders_inline_svg() -> None:
    html = lucide_icon_html("search", cls="dz-icon")
    assert "<svg" in html and 'viewBox="0 0 24 24"' in html
    assert 'stroke="currentColor"' in html
    assert "data-lucide" not in html
    assert 'aria-hidden="true"' in html


def test_unknown_icon_falls_back_to_client_hydration() -> None:
    html = lucide_icon_html("definitely-not-an-icon", cls="dz-icon")
    assert "<svg" not in html
    assert 'data-lucide="definitely-not-an-icon"' in html


def test_unknown_icon_name_is_escaped() -> None:
    html = lucide_icon_html('x" onmouseover="alert(1)', cls="dz-icon")
    assert 'onmouseover="alert' not in html
    assert "&quot;" in html


def test_icon_primitive_emits_registry_svg() -> None:
    html = _render(Icon(name="settings", size="sm"))
    assert html.startswith('<span class="dz-icon dz-icon--size-sm"')
    assert "<svg" in html


def test_icon_primitive_unknown_name_keeps_fallback() -> None:
    html = _render(Icon(name="no-such-glyph", size="md"))
    assert 'data-lucide="no-such-glyph"' in html
