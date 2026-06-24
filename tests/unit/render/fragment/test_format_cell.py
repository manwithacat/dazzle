"""#1470 Phase 1 — pure cell formatter (inference table).

Renders a stored value to a display string by the column's declared kind
(plus the Python value type for numeric rounding). No I/O. The http fragment
adapter calls this in place of the old str()-coerce stub, retiring the
UUID/float/bool/enum raw-value leak class across every grid.
"""

import datetime as dt

import pytest

from dazzle.render.fragment.format_cell import ResolvedFormat, format_cell


def _ov(value, kind, arg=None, currency_code=""):
    return format_cell(
        value, "text", currency_code=currency_code, override=ResolvedFormat(kind, arg)
    )


def test_override_currency_major_units():
    # The currency OVERRIDE on a decimal/float treats the value as major units
    # (as-is), unlike the money-type inference path (minor units / 100).
    assert _ov(1234.56, "currency", "GBP") == "£1,234.56"
    assert _ov(1000, "currency", "USD") == "$1,000.00"


def test_override_percent():
    assert _ov(0.5, "percent", "1") == "50.0%"  # ratio → percent, 1 dp
    assert _ov(0.137, "percent") == "14%"  # default 0 dp, rounded


def test_override_round():
    assert _ov(1234.56, "round", "1") == "1,234.6"
    assert _ov(1234.0, "round", "0") == "1,234"


def test_override_case():
    assert _ov("hi", "upper") == "HI"
    assert _ov("HI", "lower") == "hi"
    assert _ov("in_review", "title_case") == "In Review"


def test_override_yes_no_and_raw():
    assert _ov(True, "yes_no") == "Yes"
    assert _ov("00000000-0000-0000-0000-000000000001", "raw") == (
        "00000000-0000-0000-0000-000000000001"
    )


def test_override_display_name():
    assert _ov("Acme Ltd", "display_name") == "Acme Ltd"


def test_override_date_iso_and_long():
    import datetime as _dt

    assert _ov(_dt.date(2026, 6, 24), "date", "iso") == "2026-06-24"
    assert _ov(_dt.date(2026, 6, 24), "date", "long") == "24 June 2026"


def test_override_wins_over_inference():
    # kind="bool" would infer Yes/No, but the override forces raw.
    assert format_cell(True, "bool", override=ResolvedFormat("raw")) == "True"


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


def test_returns_raw_unescaped():
    # format_cell returns RAW strings — the renderer escapes at emit time, so
    # pre-escaping here would double-encode (& → &amp;amp;). See the render-path
    # single-escape regression test below.
    assert format_cell("<script>", "text") == "<script>"
    assert format_cell("a & b", "badge") == "A & B"


def test_bool_value_in_text_column():
    # A bool value renders Yes/No even if the column kind is generic.
    assert format_cell(True, "text") == "Yes"


def test_render_path_escapes_exactly_once():
    """Regression guard for the double-escape class: format_cell returns RAW and
    the renderer escapes once. A special-char cell must appear escaped exactly
    once in the final HTML (not `&amp;amp;`)."""
    from dazzle.render.fragment.primitives.data import Table
    from dazzle.render.fragment.renderer import FragmentRenderer

    cell = format_cell("a & <b>", "text")  # raw: "a & <b>"
    html = FragmentRenderer().render(Table(columns=("c",), rows=((cell,),)))
    assert "a &amp; &lt;b&gt;" in html  # escaped once by the renderer
    assert "&amp;amp;" not in html and "&amp;lt;" not in html  # not double-escaped
