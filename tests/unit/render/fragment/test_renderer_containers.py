"""Renderer support for Surface/Card/Region/Drawer/Modal/Tabs.

Toolbar emit lands in Task 21 alongside Button, since Toolbar's actions
are typed as `tuple[object, ...]` but realistically contain Buttons whose
emit needs htmx attribute handling.
"""

from dazzle.render.fragment import (
    Card,
    Drawer,
    Heading,
    Modal,
    Region,
    Surface,
    Tabs,
    Text,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def test_render_card_body_only() -> None:
    r = FragmentRenderer()
    out = r.render(Card(body=Text("contents")))
    assert "dz-card" in out
    assert 'class="dz-text' in out
    assert "dz-card__header" not in out


def test_render_card_with_all_slots() -> None:
    r = FragmentRenderer()
    out = r.render(
        Card(
            header=Heading("Title", level=3),
            body=Text("body"),
            footer=Text("foot"),
        )
    )
    assert "dz-card__header" in out
    assert "dz-card__body" in out
    assert "dz-card__footer" in out


def test_render_surface_with_header() -> None:
    r = FragmentRenderer()
    out = r.render(
        Surface(
            header=Heading("Tasks"),
            body=Text("content"),
        )
    )
    assert "dz-surface" in out
    assert "dz-surface__header" in out


def test_render_region_kind_class() -> None:
    r = FragmentRenderer()
    out = r.render(Region(kind="list", body=Text("rows")))
    assert "dz-region" in out
    assert "dz-region--kind-list" in out


def test_render_tabs() -> None:
    r = FragmentRenderer()
    out = r.render(Tabs(tabs=(("a", Text("A")), ("b", Text("B")))))
    assert "dz-tabs" in out
    assert out.count('class="dz-text') == 2


def test_render_drawer_side_class() -> None:
    r = FragmentRenderer()
    out = r.render(Drawer(body=Text("contents"), side="left"))
    assert "dz-drawer--side-left" in out


def test_render_modal_size_class() -> None:
    r = FragmentRenderer()
    out = r.render(Modal(body=Text("contents"), size="lg"))
    assert "dz-modal--size-lg" in out
