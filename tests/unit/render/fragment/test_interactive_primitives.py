"""Tests for interactive primitives — Button, Link, Interactive, InlineEdit.

Includes the Toolbar primary-action invariant test, which lives here because
it requires Button to construct. Attribute emission for these fields is pinned
in test_renderer_interactive.py."""

from collections.abc import Callable

import pytest

from dazzle.render.fragment.errors import CardSafetyError, HtmxBindingError
from dazzle.render.fragment.htmx import URL, TargetSelector
from dazzle.render.fragment.primitives.containers import Toolbar
from dazzle.render.fragment.primitives.content import Text
from dazzle.render.fragment.primitives.interactive import Button, Interactive


@pytest.mark.parametrize(
    ("ctor", "match"),
    [
        # An hx-* request without a target renders useless HTML.
        pytest.param(
            lambda: Button(label="Refresh", hx_get=URL("/refresh")),
            "needs hx_target",
            id="button.get_without_target",
        ),
        pytest.param(
            lambda: Button(label="X", hx_put=URL("/p")),
            "needs hx_target",
            id="button.put_without_target",
        ),
        pytest.param(
            lambda: Interactive(child=Text("x"), hx_get=URL("/x")),
            "needs hx_target",
            id="interactive.get_without_target",
        ),
        # At most one of get/post/put may be set.
        pytest.param(
            lambda: Button(
                label="Confused",
                hx_get=URL("/g"),
                hx_post=URL("/p"),
                hx_target=TargetSelector("#x"),
            ),
            "more than one",
            id="button.get_and_post",
        ),
        pytest.param(
            lambda: Button(
                label="X", hx_put=URL("/p"), hx_post=URL("/q"), hx_target=TargetSelector("#t")
            ),
            "more than one",
            id="button.put_and_post",
        ),
    ],
)
def test_rejects_invalid_htmx_binding(ctor: Callable[[], object], match: str) -> None:
    with pytest.raises(HtmxBindingError, match=match):
        ctor()


@pytest.mark.parametrize(
    "ctor",
    [
        pytest.param(
            lambda: Button(
                label="Refresh",
                hx_get=URL("/refresh"),
                hx_target=TargetSelector("#region-task_list-main"),
            ),
            id="button.get_with_target",
        ),
        # Phase 4B.1.d: hx_put lets QUEUE transition buttons use the primitive.
        pytest.param(
            lambda: Button(
                label="Approve", hx_put=URL("/api/items/42"), hx_target=TargetSelector("#q")
            ),
            id="button.put_with_target",
        ),
        pytest.param(
            lambda: Interactive(
                child=Text("clickable card"),
                hx_get=URL("/details/42"),
                hx_target=TargetSelector("#detail-pane"),
            ),
            id="interactive.get_with_target",
        ),
    ],
)
def test_accepts_targeted_htmx_binding(ctor: Callable[[], object]) -> None:
    ctor()


def test_button_defaults() -> None:
    """Pre-Phase-4B.1.d Buttons carry no hx_put / hx_vals / hx_ext."""
    b = Button(label="Save")
    assert (b.variant, b.visibility, b.hx_put, b.hx_vals, b.hx_ext) == (
        "secondary",
        "visible",
        None,
        "",
        (),
    )


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        pytest.param({"hx_confirm": "Sure?", "hx_confirm_variant": "danger"}, "invalid", id="bad"),
        pytest.param({"hx_confirm_variant": "destructive"}, "requires hx_confirm", id="orphan"),
    ],
)
def test_button_rejects_bad_confirm_variant(kwargs: dict[str, str], match: str) -> None:
    """#1795: the dz-confirm accept variant is one of the HM confirm set and
    only meaningful alongside hx-confirm."""
    with pytest.raises(ValueError, match=match):
        Button(label="X", hx_post=URL("/p"), hx_target=TargetSelector("body"), **kwargs)  # type: ignore[arg-type]


def test_toolbar_first_action_cannot_be_hidden() -> None:
    """Replaces find_hidden_primary_actions scanner."""
    visible = Button(label="Save", variant="primary")
    hidden = Button(label="Save", variant="primary", visibility="hidden")

    Toolbar(label="ok", actions=(visible,))  # fine

    with pytest.raises(CardSafetyError, match="primary action cannot be hidden"):
        Toolbar(label="bad", actions=(hidden, visible))
