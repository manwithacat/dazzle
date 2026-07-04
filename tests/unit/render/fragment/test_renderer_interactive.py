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
    assert 'class="dz-button"' in out
    assert 'data-dz-variant="primary"' in out


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
    assert " hidden>" in out or " hidden " in out  # native hidden attribute


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


# === Phase 4B.1.d — Button hx_put / hx_vals / hx_ext rendering ===


def test_render_button_with_hx_put_emits_attribute() -> None:
    r = FragmentRenderer()
    out = r.render(
        Button(
            label="Approve",
            hx_put=URL("/api/items/42"),
            hx_target=TargetSelector("#region-queue"),
        )
    )
    assert 'hx-put="/api/items/42"' in out


def test_render_button_with_hx_vals_emits_single_quoted_attribute() -> None:
    """hx-vals is wrapped in single quotes so internal JSON double
    quotes don't need escaping."""
    r = FragmentRenderer()
    out = r.render(
        Button(
            label="Set",
            hx_post=URL("/x"),
            hx_target=TargetSelector("#t"),
            hx_vals='{"status": "approved"}',
        )
    )
    assert 'hx-vals=\'{"status": "approved"}\'' in out


def test_render_button_with_hx_ext_emits_comma_joined_extensions() -> None:
    """Multiple HTMX extensions are joined with commas in the rendered
    `hx-ext` attribute."""
    r = FragmentRenderer()
    out = r.render(
        Button(
            label="X",
            hx_post=URL("/x"),
            hx_target=TargetSelector("#t"),
            hx_ext=("json-enc", "morph"),
        )
    )
    assert 'hx-ext="json-enc,morph"' in out


def test_render_button_queue_transition_shape() -> None:
    """The full queue transition button shape: PUT + JSON payload +
    json-enc extension + target swap. Mirrors the legacy queue.html
    template's inline action button."""
    r = FragmentRenderer()
    out = r.render(
        Button(
            label="Mark resolved",
            hx_put=URL("/api/queue/42"),
            hx_target=TargetSelector("#region-tickets"),
            hx_swap="innerHTML",
            hx_vals='{"status": "resolved"}',
            hx_ext=("json-enc",),
        )
    )
    assert 'hx-put="/api/queue/42"' in out
    assert 'hx-target="#region-tickets"' in out
    assert 'hx-swap="innerHTML"' in out
    assert 'hx-ext="json-enc"' in out
    assert "hx-vals=" in out
    assert "Mark resolved" in out
