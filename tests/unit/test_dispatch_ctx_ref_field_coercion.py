"""Issue #1027 (v0.66.129): regression test for the RefPicker EDIT
mode dict-stringification bug.

In EDIT mode, the form loader eagerly expands ref fields into the
full related-record dict (e.g. `{"id": "<uuid>", "name": "...", ...}`).
The pre-fix code uniformly forwarded `initial_values.get(fname)` as
`entry["value"]`, so the adapter's REF branch put the dict into
`RefPicker.initial_value` and `str()` of that dict landed in
`data-selected-value`.

Fix: at the ctx-build boundary, when the field is a ref (i.e.
`ref_api` is set), coerce dict → `id` and lift a display field into
`initial_label` so the dropdown reads something while the lazy fetch
resolves."""

from __future__ import annotations

from dazzle.back.runtime.page_routes import _build_dispatch_ctx
from dazzle.render.context import FieldContext, FormContext


class _RenderCtx:
    def __init__(self, form: FormContext) -> None:
        self.form = form
        self.detail = None
        self.table = None


def _ref_field(name: str = "assigned_to") -> FieldContext:
    return FieldContext(
        name=name,
        label="Assigned To",
        type="ref",
        ref_entity="Contact",
        ref_api="/contacts",
    )


def test_ref_field_dict_value_coerced_to_id() -> None:
    """When the loader provides an eagerly-expanded related-record
    dict, `entry["value"]` carries the bare FK UUID — not the dict."""
    form = FormContext(
        entity_name="Task",
        title="Edit Task",
        action_url="/tasks/123",
        method="PUT",
        mode="edit",
        fields=[_ref_field()],
        initial_values={
            "assigned_to": {
                "id": "d492d76b-dcbe-42ac-86a1-a99342340946",
                "first_name": "Test",
                "last_name": "User",
                "email": "test@example.com",
            }
        },
    )
    ctx = _build_dispatch_ctx(_RenderCtx(form), object())
    fields = ctx["fields"]
    assert len(fields) == 1
    assigned = fields[0]
    assert assigned["value"] == "d492d76b-dcbe-42ac-86a1-a99342340946"
    assert assigned["ref_api"] == "/contacts"


def test_ref_field_dict_lifts_display_field_into_initial_label() -> None:
    """Display field fallback chain: __display__ → name → title →
    label → email → code. The dropdown shows this while the lazy
    fetch resolves the option list."""
    form = FormContext(
        entity_name="Task",
        title="Edit Task",
        action_url="/tasks/123",
        method="PUT",
        mode="edit",
        fields=[_ref_field()],
        initial_values={"assigned_to": {"id": "abc", "email": "alice@example.com"}},
    )
    fields = _build_dispatch_ctx(_RenderCtx(form), object())["fields"]
    assert fields[0]["initial_label"] == "alice@example.com"


def test_ref_field_scalar_value_passes_through_unchanged() -> None:
    """If the loader provides the bare FK scalar (not a dict), the
    coercion is a no-op."""
    form = FormContext(
        entity_name="Task",
        title="t",
        action_url="/x",
        method="PUT",
        mode="edit",
        fields=[_ref_field()],
        initial_values={"assigned_to": "bare-uuid-value"},
    )
    fields = _build_dispatch_ctx(_RenderCtx(form), object())["fields"]
    assert fields[0]["value"] == "bare-uuid-value"
    assert "initial_label" not in fields[0]


def test_non_ref_field_dict_value_not_coerced() -> None:
    """Coercion only applies when `ref_api` is set on the field. A
    non-ref field that happens to receive a dict (unusual but
    possible for JSON payloads) should not get the FK-id treatment."""
    json_field = FieldContext(name="payload", label="Payload", type="text")
    form = FormContext(
        entity_name="X",
        title="t",
        action_url="/x",
        method="PUT",
        mode="edit",
        fields=[json_field],
        initial_values={"payload": {"id": "shouldnt-extract", "data": 123}},
    )
    fields = _build_dispatch_ctx(_RenderCtx(form), object())["fields"]
    assert fields[0]["value"] == {"id": "shouldnt-extract", "data": 123}


def test_ref_field_dict_with_only_id_emits_no_initial_label() -> None:
    """Bare {"id": ...} dict yields the FK scalar but no
    initial_label — the dropdown will show the UUID briefly until
    the lazy fetch resolves the human-readable label."""
    form = FormContext(
        entity_name="Task",
        title="t",
        action_url="/x",
        method="PUT",
        mode="edit",
        fields=[_ref_field()],
        initial_values={"assigned_to": {"id": "uuid-only"}},
    )
    fields = _build_dispatch_ctx(_RenderCtx(form), object())["fields"]
    assert fields[0]["value"] == "uuid-only"
    assert "initial_label" not in fields[0]
