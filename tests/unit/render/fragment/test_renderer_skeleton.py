"""Tests for FragmentRenderer's match-dispatch skeleton."""

import pytest

from dazzle.render.fragment import (
    FragmentError,
    Heading,
    RawHTML,
    RenderContext,
    Slot,
    Text,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def test_render_raw_html_passthrough() -> None:
    r = FragmentRenderer()
    out = r.render(RawHTML("<p>hi</p>"))
    assert out == "<p>hi</p>"


def test_render_text_escapes() -> None:
    r = FragmentRenderer()
    out = r.render(Text("<script>"))
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_render_text_default_tone() -> None:
    r = FragmentRenderer()
    out = r.render(Text("hello"))
    assert "hello" in out
    assert "dz-text" in out


def test_render_heading_level() -> None:
    r = FragmentRenderer()
    out = r.render(Heading("Title", level=2))
    assert out.startswith("<h2")
    assert "Title" in out


def test_render_unfilled_slot_raises() -> None:
    """A Slot that reaches the renderer without a substitution map is a
    programmer error, not user data — fail loudly."""
    r = FragmentRenderer()
    with pytest.raises(FragmentError, match="unfilled slot"):
        r.render(Slot(name="dynamic"))


def test_render_with_explicit_context() -> None:
    r = FragmentRenderer()
    ctx = RenderContext()
    out = r.render(Text("hello"), ctx=ctx)
    assert "hello" in out
