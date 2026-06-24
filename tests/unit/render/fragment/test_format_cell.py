"""#1470 Phase 1 — pure cell formatter (inference table).

Renders a stored value to a display string by the column's declared kind
(plus the Python value type for numeric rounding). No I/O. The http fragment
adapter calls this in place of the old str()-coerce stub, retiring the
UUID/float/bool/enum raw-value leak class across every grid.
"""

import datetime as dt

import pytest

from dazzle.render.fragment.format_cell import format_cell


@pytest.mark.parametrize(
    "value,kind,kw,expected",
    [
        (None, "text", {}, ""),  # None → blank
        ("", "text", {}, ""),  # empty → blank
        (0, "text", {}, "0"),  # zero is NOT blanked
        (True, "bool", {}, "Yes"),
        (False, "bool", {}, "No"),
        ("ACTIVE", "badge", {}, "Active"),  # enum token → Title Case
        ("in_review", "badge", {}, "In Review"),
        (3.14159, "text", {}, "3.14"),  # float → 2dp (value-type keyed)
        (10.0, "text", {}, "10.00"),
        (42, "text", {}, "42"),  # int → as-is
        ("Acme Ltd", "ref", {}, "Acme Ltd"),  # FK value already a name
        (12345, "currency", {"currency_code": "GBP"}, "£123.45"),  # minor units → currency
        (12345, "currency", {"currency_code": "XYZ"}, "123.45 XYZ"),  # unknown symbol → code suffix
    ],
)
def test_inference(value, kind, kw, expected):
    assert format_cell(value, kind, **kw) == expected


def test_datetime_friendly():
    out = format_cell(dt.datetime(2026, 6, 24, 9, 30), "date")
    assert "2026" in out and "Jun" in out and "T" not in out  # friendly, not ISO


def test_date_friendly():
    out = format_cell(dt.date(2026, 6, 24), "date")
    assert "2026" in out and "Jun" in out


def test_iso_string_datetime_parsed():
    out = format_cell("2026-06-24T09:30:00", "date")
    assert "2026" in out and "T" not in out


def test_escaping_no_double_escape():
    # esc once: < > & escaped, and NOT re-escaped through the date/badge paths.
    assert format_cell("<script>", "text") == "&lt;script&gt;"
    assert format_cell("a & b", "badge") == "A &amp; B"


def test_bool_value_in_text_column():
    # A bool value renders Yes/No even if the column kind is generic.
    assert format_cell(True, "text") == "Yes"
