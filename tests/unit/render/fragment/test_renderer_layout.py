"""Tests for renderer support of layout primitives."""

from dazzle.render.fragment import Grid, Row, Split, Stack, Text
from dazzle.render.fragment.renderer import FragmentRenderer


def test_render_stack_with_two_children() -> None:
    r = FragmentRenderer()
    out = r.render(Stack(children=(Text("a"), Text("b"))))
    # Each Text emits one <span class="dz-text ..."> element.
    assert out.count('<span class="dz-text') == 2
    assert "dz-stack" in out
    assert "dz-stack--gap-md" in out


def test_render_row_alignment() -> None:
    r = FragmentRenderer()
    out = r.render(Row(children=(Text("x"),), align="center"))
    assert "dz-row--align-center" in out


def test_render_split() -> None:
    r = FragmentRenderer()
    out = r.render(Split(start=Text("L"), end=Text("R"), ratio="1:2"))
    assert "dz-split--ratio-1_2" in out
    # start and end each emit one Text span.
    assert out.count('<span class="dz-text') == 2


def test_render_grid_columns_class() -> None:
    r = FragmentRenderer()
    out = r.render(Grid(children=(Text("x"),), columns=4))
    assert "dz-grid--columns-4" in out
