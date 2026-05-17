"""#1130: typed ``Script`` and ``Stylesheet`` Fragment primitives.

Custom renderers used to emit client-side JS by stuffing
``<script>`` tags into ``RawHTML`` — bypassing the framework's
attribute-escaping AND any CSP-nonce policy in force. These tests
pin the typed-primitive replacement: safe rendering, mutual-
exclusion validation, CSP nonce injection, and ``</script>``
injection-resistance.
"""

from __future__ import annotations

import pytest

from dazzle.render.fragment import (
    FragmentRenderer,
    RenderContext,
    Script,
    Stylesheet,
)

# ---------------------------------------------------------------------------
# Validation — exactly one of src/body (Script) / href/body (Stylesheet)
# ---------------------------------------------------------------------------


def test_script_rejects_both_src_and_body() -> None:
    with pytest.raises(ValueError, match="exactly one of src= or body="):
        Script(src="/x.js", body="console.log(1)")


def test_script_rejects_neither_src_nor_body() -> None:
    with pytest.raises(ValueError, match="exactly one of src= or body="):
        Script()


def test_stylesheet_rejects_both_href_and_body() -> None:
    with pytest.raises(ValueError, match="exactly one of href= or body="):
        Stylesheet(href="/x.css", body="body{}")


def test_stylesheet_rejects_neither_href_nor_body() -> None:
    with pytest.raises(ValueError, match="exactly one of href= or body="):
        Stylesheet()


def test_script_rejects_non_str_src() -> None:
    with pytest.raises(TypeError, match="Script.src expects str"):
        Script(src=42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Script — emit shape
# ---------------------------------------------------------------------------


def _render(fragment) -> str:
    return FragmentRenderer().render(fragment)


def test_script_with_src_emits_type_and_src_attributes() -> None:
    out = _render(Script(src="/static/app.js"))
    assert 'type="module"' in out
    assert 'src="/static/app.js"' in out
    assert out.endswith("</script>")


def test_script_with_body_inlines_content() -> None:
    out = _render(Script(body="console.log('hello');"))
    assert "console.log('hello');" in out
    assert "<script " in out
    assert "</script>" in out


def test_script_escapes_src_attribute_value() -> None:
    """A renderer that interpolates user input into Script(src=...)
    should be safe against attribute-context injection. The HTML
    escaper handles quotes + &/<."""
    out = _render(Script(src='/x.js" onerror="alert(1)'))
    assert 'onerror="alert(1)"' not in out
    assert "&quot;" in out


def test_script_inline_body_escapes_close_script_tag() -> None:
    """``</script>`` inside a JS string literal must not prematurely
    end the script element. Escape to ``<\\/script>`` which JS
    parses identically but the HTML tokenizer ignores."""
    out = _render(Script(body="var s = '</script>';"))
    assert "</script>'" not in out
    assert "<\\/script>" in out


def test_script_defer_and_async_flags() -> None:
    out = _render(Script(src="/x.js", defer=True, async_=True))
    assert "defer" in out
    assert "async" in out


# ---------------------------------------------------------------------------
# CSP nonce — primitive + context fallback
# ---------------------------------------------------------------------------


def test_script_emits_explicit_nonce() -> None:
    out = _render(Script(body="x", nonce="abc123"))
    assert 'nonce="abc123"' in out


def test_script_inherits_nonce_from_render_context() -> None:
    """Per-primitive nonce=None + ctx.csp_nonce set → primitive picks
    up the context nonce. The path projects-on-strict-CSP land on
    when they thread the nonce through middleware."""
    out = FragmentRenderer().render(
        Script(body="x"),
        ctx=RenderContext(csp_nonce="from-ctx"),
    )
    assert 'nonce="from-ctx"' in out


def test_script_no_nonce_when_neither_set() -> None:
    out = _render(Script(body="x"))
    assert "nonce=" not in out


def test_script_explicit_nonce_wins_over_context() -> None:
    """An explicit nonce on the primitive wins over the context nonce
    — primitives that need a one-off override (e.g. per-fragment
    isolation) shouldn't be steamrollered by the request-level
    default."""
    out = FragmentRenderer().render(
        Script(body="x", nonce="explicit"),
        ctx=RenderContext(csp_nonce="from-ctx"),
    )
    assert 'nonce="explicit"' in out
    assert "from-ctx" not in out


# ---------------------------------------------------------------------------
# Stylesheet — emit shape
# ---------------------------------------------------------------------------


def test_stylesheet_with_href_emits_link_tag() -> None:
    out = _render(Stylesheet(href="/static/app.css"))
    assert out == '<link rel="stylesheet" href="/static/app.css">'


def test_stylesheet_with_body_emits_style_tag() -> None:
    out = _render(Stylesheet(body=".x { color: red; }"))
    assert out == "<style>.x { color: red; }</style>"


def test_stylesheet_media_attr_emitted_when_non_default() -> None:
    out = _render(Stylesheet(href="/print.css", media="print"))
    assert 'media="print"' in out


def test_stylesheet_media_attr_omitted_when_default_all() -> None:
    out = _render(Stylesheet(href="/x.css"))
    assert "media=" not in out


def test_stylesheet_escapes_href_value() -> None:
    out = _render(Stylesheet(href='/x.css" onerror="alert(1)'))
    # The literal substring "onerror=" can still appear inside the
    # escaped attribute value — what matters is that the surrounding
    # `"` is HTML-escaped to `&quot;` so it doesn't break out of the
    # attribute context. Pin that escape, not absence of the literal.
    assert '" onerror=' not in out
    assert "&quot;" in out


def test_stylesheet_escapes_close_style_tag_in_inline_body() -> None:
    out = _render(Stylesheet(body=".x{content:'</style>'}"))
    assert "</style>'" not in out
    assert "<\\/style>" in out


# ---------------------------------------------------------------------------
# Frozen-dataclass invariants
# ---------------------------------------------------------------------------


def test_script_is_frozen() -> None:
    s = Script(body="x")
    with pytest.raises((AttributeError, Exception)):
        s.body = "y"  # type: ignore[misc]


def test_stylesheet_is_frozen() -> None:
    s = Stylesheet(body="x")
    with pytest.raises((AttributeError, Exception)):
        s.body = "y"  # type: ignore[misc]
