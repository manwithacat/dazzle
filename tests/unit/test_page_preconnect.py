"""Page primitive emits font preconnect links (#1042 follow-up).

The typed Page primitive gained a ``font_preconnect`` field as part of
the theme-support restoration. Themes that ship custom fonts declare
the font CDN host via the registry; the resolver flows the list into
``Page.font_preconnect`` and the renderer emits one
``<link rel="preconnect" href="..." crossorigin>`` per origin in
``<head>``.
"""

from __future__ import annotations

from dazzle.render.fragment import Page
from dazzle.render.fragment.escape import RawHTML
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(**overrides: object) -> str:
    defaults: dict[str, object] = {
        "title": "Test",
        "body": RawHTML("<p>body</p>"),
        "css_links": ("/static/dist/dazzle.min.css",),
        "js_scripts": ("/static/dist/dazzle.min.js",),
    }
    defaults.update(overrides)
    return FragmentRenderer().render(Page(**defaults))  # type: ignore[arg-type]


class TestPagePreconnect:
    def test_no_preconnect_when_empty(self) -> None:
        html = _render()
        assert 'rel="preconnect"' not in html

    def test_emits_single_preconnect(self) -> None:
        html = _render(font_preconnect=("https://fonts.googleapis.com",))
        assert '<link rel="preconnect" href="https://fonts.googleapis.com" crossorigin>' in html

    def test_emits_multiple_preconnects_in_order(self) -> None:
        html = _render(
            font_preconnect=(
                "https://fonts.googleapis.com",
                "https://fonts.gstatic.com",
            )
        )
        idx_g = html.index("fonts.googleapis.com")
        idx_s = html.index("fonts.gstatic.com")
        assert idx_g < idx_s, "preconnect order not preserved"

    def test_preconnect_before_stylesheet(self) -> None:
        """Preconnects must land before the framework bundle so the
        TCP+TLS handshake overlaps with stylesheet parsing."""
        html = _render(
            font_preconnect=("https://fonts.googleapis.com",),
            css_links=("/static/dist/dazzle.min.css",),
        )
        preconnect_idx = html.index('rel="preconnect"')
        stylesheet_idx = html.index('rel="stylesheet"')
        assert preconnect_idx < stylesheet_idx

    def test_preconnect_attr_is_escaped(self) -> None:
        html = _render(font_preconnect=('https://"evil.example/',))
        assert '"evil' not in html  # quote was escaped
        assert "&#34;evil" in html or "&quot;evil" in html
