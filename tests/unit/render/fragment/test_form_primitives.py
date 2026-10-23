"""Tests for form primitives — FormStack, Field, Combobox, Submit."""

import pytest

from dazzle.render.fragment.htmx import URL
from dazzle.render.fragment.primitives.forms import Combobox, Field, FormStack, Submit, SwitchField


def test_form_stack_requires_action() -> None:
    fs = FormStack(action=URL("/tasks/create"), fields=(Field(name="title", label="Title"),))
    assert fs.action is not None
    assert fs.method == "POST"


def test_form_stack_rejects_no_fields() -> None:
    with pytest.raises(ValueError, match="at least one field"):
        FormStack(action=URL("/x"), fields=())


def test_form_stack_accepts_submit_only_action_form() -> None:
    """#1844: a one-button action form has a submit and no fields."""
    fs = FormStack(action=URL("/x"), fields=(), submit=Submit(label="Turn off"))
    assert fs.fields == ()


def test_field_required() -> None:
    f = Field(name="title", label="Title")
    assert f.required is False
    assert f.kind == "text"


def test_field_invalid_kind() -> None:
    with pytest.raises(ValueError, match="invalid field kind"):
        Field(name="title", label="Title", kind="moonbeam")  # type: ignore[arg-type]


def test_combobox_options_required() -> None:
    with pytest.raises(ValueError, match="at least one option"):
        Combobox(name="status", label="Status", options=())


def test_combobox_option_pairs() -> None:
    c = Combobox(
        name="status",
        label="Status",
        options=(("open", "Open"), ("closed", "Closed")),
    )
    assert len(c.options) == 2


def test_submit_label_required() -> None:
    s = Submit(label="Save changes")
    assert s.label == "Save changes"


@pytest.mark.parametrize(
    "primitive",
    [
        Field(name="active", label="Active", kind="checkbox", initial_value="true"),
        SwitchField(name="active", label="Active", initial_value="true"),
    ],
    ids=["checkbox", "switch"],
)
def test_checkbox_posts_false_when_unticked(primitive: object) -> None:
    """#1848 follow-up: an unticked checkbox posts nothing, so a hidden `false`
    precedes it; the ticked box comes later and its value wins."""
    from dazzle.render.fragment import FragmentRenderer

    html = FragmentRenderer().render(primitive)
    hidden = html.index('<input type="hidden" name="active" value="false">')
    assert hidden < html.index('type="checkbox"')
