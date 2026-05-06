"""Adapter: REF/UUID/JSON field mapping (Plan 14 + Plan 15)."""

from dazzle.render.fragment.primitives.forms import Field, RefPicker
from dazzle_back.runtime.renderers.fragment_adapter import _field_to_primitive


def test_ref_field_with_ref_api_produces_refpicker() -> None:
    """A field_dict with kind='ref' and a ref_api string produces a
    RefPicker — the adapter's typed REF branch."""
    primitive = _field_to_primitive(
        {
            "name": "assigned_to",
            "label": "Assigned",
            "kind": "ref",
            "ref_api": "/user",
            "required": True,
            "value": "abc-123",
            "initial_label": "Alice",
        }
    )
    assert isinstance(primitive, RefPicker)
    assert primitive.name == "assigned_to"
    assert primitive.ref_api.value == "/user"
    assert primitive.required is True
    assert primitive.initial_value == "abc-123"
    assert primitive.initial_label == "Alice"


def test_ref_field_without_ref_api_falls_back_to_text_field() -> None:
    """A REF field where ref_api wasn't threaded through (e.g. older
    runtime path) falls back to a plain text Field — graceful, not
    an exception."""
    primitive = _field_to_primitive(
        {
            "name": "assigned_to",
            "label": "Assigned",
            "kind": "ref",
        }
    )
    assert isinstance(primitive, Field)


def test_uuid_field_produces_readonly_text_field() -> None:
    """UUID fields render as readonly text — system-assigned, visible
    but not editable. Plan 15 closure."""
    primitive = _field_to_primitive(
        {
            "name": "external_id",
            "label": "External ID",
            "kind": "uuid",
            "value": "00000000-0000-0000-0000-000000000abc",
        }
    )
    assert isinstance(primitive, Field)
    assert primitive.kind == "text"
    assert primitive.readonly is True
    assert primitive.initial_value == "00000000-0000-0000-0000-000000000abc"


def test_json_field_produces_textarea() -> None:
    """JSON fields render as a textarea with the str-coerced value."""
    primitive = _field_to_primitive(
        {
            "name": "metadata",
            "label": "Metadata",
            "kind": "json",
            "value": '{"key": "value"}',
        }
    )
    assert isinstance(primitive, Field)
    assert primitive.kind == "textarea"
    assert primitive.initial_value == '{"key": "value"}'


def test_json_field_with_dict_value_is_serialised() -> None:
    """If the backend hands a dict/list rather than a string, the adapter
    serialises it. Defensive — most paths str-coerce upstream."""
    primitive = _field_to_primitive(
        {
            "name": "metadata",
            "label": "Metadata",
            "kind": "json",
            "value": {"key": "value", "n": 42},
        }
    )
    assert isinstance(primitive, Field)
    assert primitive.kind == "textarea"
    # JSON-formatted output should contain the key:value pair
    assert "key" in primitive.initial_value
    assert "value" in primitive.initial_value
