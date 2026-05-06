"""RefPicker primitive — Phase 2A's typed REF-field building block."""

import pytest

from dazzle.render.fragment import URL
from dazzle.render.fragment.primitives.forms import RefPicker


def test_ref_picker_minimal_construction() -> None:
    rp = RefPicker(name="assigned_to", label="Assigned", ref_api=URL("/user"))
    assert rp.name == "assigned_to"
    assert rp.label == "Assigned"
    assert rp.ref_api.value == "/user"
    assert rp.required is False
    assert rp.initial_value == ""
    assert rp.initial_label == ""


def test_ref_picker_with_initial_selection() -> None:
    rp = RefPicker(
        name="assigned_to",
        label="Assigned",
        ref_api=URL("/user"),
        required=True,
        initial_value="00000000-0000-0000-0000-000000000001",
        initial_label="Alice",
    )
    assert rp.required is True
    assert rp.initial_label == "Alice"


def test_ref_picker_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="non-empty name"):
        RefPicker(name="", label="X", ref_api=URL("/a"))


def test_ref_picker_rejects_empty_label() -> None:
    with pytest.raises(ValueError, match="non-empty label"):
        RefPicker(name="x", label="", ref_api=URL("/a"))


def test_ref_picker_is_frozen() -> None:
    rp = RefPicker(name="x", label="X", ref_api=URL("/a"))
    with pytest.raises((AttributeError, TypeError)):
        rp.name = "y"  # type: ignore[misc]
