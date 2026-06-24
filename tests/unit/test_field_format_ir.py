"""#1470 Phase 2 Task 3 — FieldFormatSpec IR + SurfaceElement.format attribute."""

from dazzle.core.ir.surfaces import FieldFormatSpec, SurfaceElement


def test_field_format_spec_defaults() -> None:
    f = FieldFormatSpec(kind="percent")
    assert f.kind == "percent"
    assert f.arg is None


def test_field_format_spec_with_arg() -> None:
    f = FieldFormatSpec(kind="currency", arg="GBP")
    assert f.kind == "currency"
    assert f.arg == "GBP"


def test_surface_element_format_default_none() -> None:
    el = SurfaceElement(field_name="x")
    assert el.format is None


def test_surface_element_with_format() -> None:
    el = SurfaceElement(field_name="amount", format=FieldFormatSpec(kind="currency", arg="GBP"))
    assert el.format is not None
    assert el.format.kind == "currency"
    assert el.format.arg == "GBP"
