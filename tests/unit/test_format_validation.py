"""#1470 Phase 2 Task 5 — validate field `format:` kind + kind/type compatibility."""

from dazzle.core.ir.fields import FieldTypeKind
from dazzle.core.validation.surfaces import _format_kind_error


def test_unknown_kind_errors() -> None:
    assert _format_kind_error("bogus", FieldTypeKind.STR) is not None


def test_currency_on_str_is_mismatch() -> None:
    assert _format_kind_error("currency", FieldTypeKind.STR) is not None


def test_currency_on_money_ok() -> None:
    assert _format_kind_error("currency", FieldTypeKind.MONEY) is None


def test_currency_on_float_ok() -> None:
    assert _format_kind_error("currency", FieldTypeKind.FLOAT) is None


def test_percent_on_int_ok() -> None:
    assert _format_kind_error("percent", FieldTypeKind.INT) is None


def test_display_name_on_ref_ok() -> None:
    assert _format_kind_error("display_name", FieldTypeKind.REF) is None


def test_display_name_on_str_is_mismatch() -> None:
    assert _format_kind_error("display_name", FieldTypeKind.STR) is not None


def test_date_on_datetime_ok() -> None:
    assert _format_kind_error("date", FieldTypeKind.DATETIME) is None


def test_relative_on_str_is_mismatch() -> None:
    assert _format_kind_error("relative", FieldTypeKind.STR) is not None


def test_title_case_applies_to_any_type() -> None:
    assert _format_kind_error("title_case", FieldTypeKind.STR) is None
    assert _format_kind_error("upper", FieldTypeKind.INT) is None
    assert _format_kind_error("raw", FieldTypeKind.UUID) is None
    assert _format_kind_error("yes_no", FieldTypeKind.BOOL) is None
