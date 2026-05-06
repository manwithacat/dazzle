"""Adapter: REF fields map to RefPicker (Plan 14)."""

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
