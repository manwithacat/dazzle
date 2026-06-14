"""#1392 — custom renderers opt back into the framework output guarantee.

The built-in ``fragment`` renderer is the trusted typed substrate. A custom
renderer (any name not in the framework defaults) bypasses it, so nothing
previously stopped it returning a blank string — which ships as an empty 200
(the AegisMark "passes render, blank screen" failure).

``dispatch_render`` now asserts non-blank, well-formed, string output on every
custom-renderer path, raising a typed ``FragmentError`` that names the surface
and renderer. On by default. The framework ``fragment`` path is untouched.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dazzle.render.dispatch import dispatch_render
from dazzle.render.fragment.errors import FragmentError


def _services(handler: object) -> SimpleNamespace:
    registry = SimpleNamespace(
        resolve=lambda _name: handler,
        registered_names=lambda: {"word_cloud", "fragment"},
    )
    return SimpleNamespace(renderer_registry=registry)


def _surface(render: str) -> SimpleNamespace:
    return SimpleNamespace(name="feedback_detail", render=render)


def _handler(return_value: object) -> SimpleNamespace:
    return SimpleNamespace(render=lambda _s, _c: return_value)


# ──────────────────────── custom renderer: enforced ────────────────────────


class TestCustomRendererGuarantee:
    def test_valid_html_passes_through(self) -> None:
        html = dispatch_render(
            _surface("word_cloud"),
            ctx={},
            services=_services(_handler("<section class='wc'>hi</section>")),
        )
        assert html == "<section class='wc'>hi</section>"

    def test_blank_string_raises(self) -> None:
        with pytest.raises(FragmentError, match="blank string"):
            dispatch_render(_surface("word_cloud"), ctx={}, services=_services(_handler("")))

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(FragmentError, match="blank string"):
            dispatch_render(_surface("word_cloud"), ctx={}, services=_services(_handler("  \n  ")))

    def test_non_string_return_raises(self) -> None:
        with pytest.raises(FragmentError, match="not an HTML string"):
            dispatch_render(_surface("word_cloud"), ctx={}, services=_services(_handler(None)))

    def test_error_names_surface_and_renderer(self) -> None:
        with pytest.raises(
            FragmentError, match="feedback_detail.*word_cloud|word_cloud.*feedback_detail"
        ):
            dispatch_render(_surface("word_cloud"), ctx={}, services=_services(_handler("")))

    def test_html5_implicit_close_is_not_flagged(self) -> None:
        # Unclosed <li>/<br> and a custom element are valid HTML5 — the
        # well-formed probe must not false-positive on them.
        body = "<ul><li>one<li>two</ul><br><dz-onboarding-step>x</dz-onboarding-step>"
        assert (
            dispatch_render(_surface("word_cloud"), ctx={}, services=_services(_handler(body)))
            == body
        )


# ──────────────────────── framework fragment: untouched ────────────────────


class TestFrameworkRendererUnaffected:
    def test_fragment_blank_is_not_guarded(self) -> None:
        # The built-in `fragment` renderer is trusted — the #1392 guarantee
        # is scoped to custom renderers, so a blank from `fragment` is returned
        # verbatim (its own pipeline owns that contract).
        assert dispatch_render(_surface("fragment"), ctx={}, services=_services(_handler(""))) == ""
