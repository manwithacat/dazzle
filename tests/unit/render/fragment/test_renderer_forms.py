"""Renderer support for FormStack/Field/Combobox/Submit."""

from dazzle.render.fragment import URL, Combobox, Field, FormStack, Submit
from dazzle.render.fragment.renderer import FragmentRenderer


def test_render_form_stack_action_method() -> None:
    r = FragmentRenderer()
    fs = FormStack(
        action=URL("/tasks/create"),
        fields=(Field(name="title", label="Title", required=True),),
    )
    out = r.render(fs)
    assert 'action="/tasks/create"' in out
    assert 'method="POST"' in out


def test_render_field_text() -> None:
    r = FragmentRenderer()
    out = r.render(Field(name="title", label="Title", required=True))
    assert 'name="title"' in out
    assert 'type="text"' in out
    assert "required" in out
    assert "Title" in out


def test_render_field_textarea() -> None:
    r = FragmentRenderer()
    out = r.render(Field(name="body", label="Body", kind="textarea"))
    assert "<textarea" in out


def test_render_combobox_options() -> None:
    r = FragmentRenderer()
    c = Combobox(
        name="status",
        label="Status",
        options=(("open", "Open"), ("closed", "Closed")),
    )
    out = r.render(c)
    assert "<select" in out
    assert 'value="open"' in out
    assert "Open" in out
    assert "Closed" in out


def test_render_submit_default_variant() -> None:
    r = FragmentRenderer()
    out = r.render(Submit(label="Save"))
    assert "Save" in out
    assert 'type="submit"' in out
    assert "dz-submit--variant-primary" in out


def test_render_form_stack_with_submit() -> None:
    r = FragmentRenderer()
    fs = FormStack(
        action=URL("/save"),
        fields=(Field(name="title", label="Title"),),
        submit=Submit(label="Save"),
    )
    out = r.render(fs)
    assert "Save" in out
    assert 'type="submit"' in out
