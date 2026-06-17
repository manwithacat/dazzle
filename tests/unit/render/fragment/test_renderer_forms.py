"""Renderer support for FormStack/Field/Combobox/Submit."""

from dazzle.render.fragment import URL, Combobox, Field, FormStack, Submit
from dazzle.render.fragment.renderer import FragmentRenderer


def test_render_form_stack_post_emits_hx_post() -> None:
    """v0.66.141: POST forms emit `hx-post` for htmx-driven submission
    matching the legacy `components/form.html` contract — the RBAC
    contract checker requires `hx-post` on the `<form>` element
    (cf. `_check_create_form` in `testing/ux/contract_checker.py`)."""
    r = FragmentRenderer()
    fs = FormStack(
        action=URL("/tasks/create"),
        fields=(Field(name="title", label="Title", required=True),),
    )
    out = r.render(fs)
    assert 'hx-post="/tasks/create"' in out
    assert 'hx-target="body"' in out
    assert 'hx-swap="innerHTML"' in out
    # htmx 4: json-enc dropped — POST goes url-encoded, the server's tolerant
    # body parser handles it (no hx-ext needed).
    assert 'hx-ext="json-enc"' not in out
    # Old plain-form attrs must NOT appear on POST/PUT — the RBAC
    # checker is strict on hx-post.
    assert 'action="/tasks/create"' not in out
    assert 'method="POST"' not in out


def test_render_form_stack_put_emits_hx_put() -> None:
    """EDIT-mode forms use `hx-put` (matches the legacy form template's
    `hx-{{ "put" if form.method == "put" else "post" }}` branching)."""
    r = FragmentRenderer()
    fs = FormStack(
        action=URL("/tasks/123"),
        fields=(Field(name="title", label="Title"),),
        method="PUT",
    )
    out = r.render(fs)
    assert 'hx-put="/tasks/123"' in out


def test_render_form_stack_get_keeps_action_method() -> None:
    """GET forms (rare — search forms etc.) keep the legacy
    `action`/`method` shape — no htmx for full-page navigations."""
    r = FragmentRenderer()
    fs = FormStack(
        action=URL("/search"),
        fields=(Field(name="q", label="Query"),),
        method="GET",
    )
    out = r.render(fs)
    assert 'action="/search"' in out
    assert 'method="GET"' in out
    assert "hx-post" not in out


def test_render_form_stack_emits_data_dazzle_form_attrs_when_set() -> None:
    """`entity_name` + `mode` emit `data-dazzle-form="<entity>"`
    + `data-dazzle-form-mode="<create|edit>"` for the RBAC checker."""
    r = FragmentRenderer()
    fs = FormStack(
        action=URL("/contacts"),
        fields=(Field(name="name", label="Name"),),
        entity_name="Contact",
        mode="create",
    )
    out = r.render(fs)
    assert 'data-dazzle-form="Contact"' in out
    assert 'data-dazzle-form-mode="create"' in out


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
