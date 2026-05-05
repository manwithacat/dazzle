"""Tests for interactive primitives — Button, Link, Interactive, InlineEdit.

Includes the Toolbar primary-action invariant test, which lives here because
it requires Button to construct."""

import pytest

from dazzle.render.fragment.errors import CardSafetyError, HtmxBindingError
from dazzle.render.fragment.htmx import URL, TargetSelector
from dazzle.render.fragment.primitives.containers import Toolbar
from dazzle.render.fragment.primitives.content import Text
from dazzle.render.fragment.primitives.interactive import (
    Button,
    InlineEdit,
    Interactive,
    Link,
)

# === Button ===


def test_button_basic() -> None:
    b = Button(label="Save")
    assert b.label == "Save"
    assert b.variant == "secondary"


def test_button_htmx_get_requires_target() -> None:
    with pytest.raises(HtmxBindingError, match="needs hx_target"):
        Button(label="Refresh", hx_get=URL("/refresh"))


def test_button_htmx_get_with_target() -> None:
    b = Button(
        label="Refresh",
        hx_get=URL("/refresh"),
        hx_target=TargetSelector("#region-task_list-main"),
    )
    assert b.hx_get is not None


def test_button_rejects_both_get_and_post() -> None:
    with pytest.raises(HtmxBindingError, match="cannot have both"):
        Button(
            label="Confused",
            hx_get=URL("/g"),
            hx_post=URL("/p"),
            hx_target=TargetSelector("#x"),
        )


def test_button_visibility_default() -> None:
    b = Button(label="Save")
    assert b.visibility == "visible"


# === Toolbar primary-action invariant ===


def test_toolbar_first_action_cannot_be_hidden() -> None:
    """Replaces find_hidden_primary_actions scanner."""
    visible = Button(label="Save", variant="primary")
    hidden = Button(label="Save", variant="primary", visibility="hidden")

    Toolbar(label="ok", actions=(visible,))  # fine

    with pytest.raises(CardSafetyError, match="primary action cannot be hidden"):
        Toolbar(label="bad", actions=(hidden, visible))


# === Link ===


def test_link_basic() -> None:
    link = Link(label="Open", href=URL("/items/42"))
    assert link.label == "Open"
    assert str(link.href) == "/items/42"


# === Interactive wrapper ===


def test_interactive_wraps_child() -> None:
    inner = Text("clickable card")
    iw = Interactive(
        child=inner,
        hx_get=URL("/details/42"),
        hx_target=TargetSelector("#detail-pane"),
    )
    assert iw.child is inner


def test_interactive_requires_target() -> None:
    with pytest.raises(HtmxBindingError, match="needs hx_target"):
        Interactive(child=Text("x"), hx_get=URL("/x"))


# === InlineEdit ===


def test_inline_edit_field_required() -> None:
    ie = InlineEdit(field_name="title", value="Hello")
    assert ie.field_name == "title"
