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
    with pytest.raises(HtmxBindingError, match="more than one"):
        Button(
            label="Confused",
            hx_get=URL("/g"),
            hx_post=URL("/p"),
            hx_target=TargetSelector("#x"),
        )


def test_button_visibility_default() -> None:
    b = Button(label="Save")
    assert b.visibility == "visible"


# === Phase 4B.1.d — hx_put / hx_vals / hx_ext extensions ===


def test_button_hx_put_with_target_is_valid() -> None:
    """Phase 4B.1.d added `hx_put` so QUEUE state-transition buttons can
    be expressed without specialising the primitive."""
    b = Button(
        label="Approve",
        hx_put=URL("/api/items/42"),
        hx_target=TargetSelector("#region-queue"),
    )
    assert b.hx_put is not None


def test_button_rejects_both_put_and_post() -> None:
    """At most one of get/post/put may be set — same invariant as before
    the put extension, generalised to three methods."""
    with pytest.raises(HtmxBindingError, match="more than one"):
        Button(
            label="X",
            hx_put=URL("/p"),
            hx_post=URL("/q"),
            hx_target=TargetSelector("#t"),
        )


def test_button_rejects_put_without_target() -> None:
    """hx_put without hx_target is the same anti-pattern as hx_get/post
    without target — the rendered HTML would be useless."""
    with pytest.raises(HtmxBindingError, match="needs hx_target"):
        Button(label="X", hx_put=URL("/p"))


def test_button_carries_hx_vals_payload_string() -> None:
    """hx_vals is a string (typically JSON) the runtime sends with the
    request. Empty string default = no hx-vals attribute."""
    b = Button(
        label="Approve",
        hx_put=URL("/x"),
        hx_target=TargetSelector("#t"),
        hx_vals='{"status": "approved"}',
    )
    assert b.hx_vals == '{"status": "approved"}'


def test_button_carries_hx_ext_extension_tuple() -> None:
    """hx_ext is a tuple of HTMX extension names (e.g. json-enc).
    Empty tuple default = no hx-ext attribute."""
    b = Button(
        label="X",
        hx_post=URL("/x"),
        hx_target=TargetSelector("#t"),
        hx_ext=("json-enc",),
    )
    assert b.hx_ext == ("json-enc",)


def test_button_default_hx_extensions_are_empty() -> None:
    """Backward compat — pre-Phase-4B.1.d Buttons have no hx_put,
    no hx_vals, and no hx_ext."""
    b = Button(label="X")
    assert b.hx_put is None
    assert b.hx_vals == ""
    assert b.hx_ext == ()


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
