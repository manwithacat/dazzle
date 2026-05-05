"""Renderer support for Button/Link/Interactive/InlineEdit + Toolbar.

Tests the typed-htmx-field -> hx-* attribute emission path."""

from dazzle.render.fragment import (
    URL,
    Button,
    HxTrigger,
    InlineEdit,
    Interactive,
    Link,
    TargetSelector,
    Text,
    Toolbar,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def test_render_button_label() -> None:
    r = FragmentRenderer()
    out = r.render(Button(label="Save", variant="primary"))
    assert "Save" in out
    assert "dz-button--variant-primary" in out


def test_render_button_with_htmx_get() -> None:
    r = FragmentRenderer()
    btn = Button(
        label="Refresh",
        hx_get=URL("/refresh"),
        hx_target=TargetSelector("#region-task_list-main"),
        hx_swap="innerHTML",
    )
    out = r.render(btn)
    assert 'hx-get="/refresh"' in out
    assert 'hx-target="#region-task_list-main"' in out
    assert 'hx-swap="innerHTML"' in out


def test_render_button_with_htmx_post_and_confirm() -> None:
    r = FragmentRenderer()
    btn = Button(
        label="Delete",
        variant="danger",
        hx_post=URL("/tasks/42/delete"),
        hx_target=TargetSelector("closest tr"),
        hx_swap="delete",
        hx_confirm="Are you sure?",
    )
    out = r.render(btn)
    assert 'hx-post="/tasks/42/delete"' in out
    assert 'hx-confirm="Are you sure?"' in out


def test_render_button_visibility_hidden_class() -> None:
    r = FragmentRenderer()
    out = r.render(Button(label="Maybe", visibility="hidden"))
    assert "dz-button--visibility-hidden" in out


def test_render_button_no_htmx_no_hx_attrs() -> None:
    """A button without htmx fields must not emit hx-* attributes."""
    r = FragmentRenderer()
    out = r.render(Button(label="Plain"))
    assert "hx-" not in out


def test_render_link() -> None:
    r = FragmentRenderer()
    out = r.render(Link(label="Open", href=URL("/items/42")))
    assert 'href="/items/42"' in out
    assert "Open" in out


def test_render_interactive_wrapper() -> None:
    r = FragmentRenderer()
    iw = Interactive(
        child=Text("clickable area"),
        hx_get=URL("/details/42"),
        hx_target=TargetSelector("#detail-pane"),
        hx_trigger=HxTrigger("click"),
    )
    out = r.render(iw)
    assert 'hx-get="/details/42"' in out
    assert 'hx-trigger="click"' in out
    assert "clickable area" in out


def test_render_inline_edit() -> None:
    r = FragmentRenderer()
    out = r.render(InlineEdit(field_name="title", value="Original", placeholder="Enter title"))
    assert "Original" in out
    assert 'data-field="title"' in out


def test_render_toolbar_with_actions() -> None:
    """Toolbar emit lives here because it needs Button to render."""
    r = FragmentRenderer()
    out = r.render(
        Toolbar(
            label="Actions",
            actions=(Button(label="New", variant="primary"),),
        )
    )
    assert "dz-toolbar" in out
    assert "New" in out
