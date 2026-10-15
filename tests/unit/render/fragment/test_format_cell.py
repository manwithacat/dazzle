"""#1470 Phase 1 — pure cell formatter (inference table).

Renders a stored value to a display string by the column's declared kind
(plus the Python value type for numeric rounding). No I/O. The http fragment
adapter calls this in place of the old str()-coerce stub, retiring the
UUID/float/bool/enum raw-value leak class across every grid.
"""

import datetime as dt

import pytest

from dazzle.render.fragment.format_cell import ResolvedFormat, format_cell


@pytest.mark.parametrize(
    ("value", "column_kind", "fmt", "arg", "expected"),
    [
        # The currency OVERRIDE treats the value as major units (as-is), unlike
        # the money-type inference path (minor units / 100).
        pytest.param(1234.56, "text", "currency", "GBP", "£1,234.56", id="currency-gbp"),
        pytest.param(1000, "text", "currency", "USD", "$1,000.00", id="currency-usd"),
        pytest.param(0.5, "text", "percent", "1", "50.0%", id="percent-ratio-1dp"),
        pytest.param(0.137, "text", "percent", None, "14%", id="percent-default-0dp"),
        pytest.param(1234.56, "text", "round", "1", "1,234.6", id="round-1dp"),
        pytest.param(1234.0, "text", "round", "0", "1,234", id="round-0dp"),
        pytest.param("hi", "text", "upper", None, "HI", id="upper"),
        pytest.param("HI", "text", "lower", None, "hi", id="lower"),
        pytest.param("in_review", "text", "title_case", None, "In Review", id="title-case"),
        pytest.param(True, "text", "yes_no", None, "Yes", id="yes-no"),
        pytest.param(
            "00000000-0000-0000-0000-000000000001",
            "text",
            "raw",
            None,
            "00000000-0000-0000-0000-000000000001",
            id="raw",
        ),
        pytest.param("Acme Ltd", "text", "display_name", None, "Acme Ltd", id="display-name"),
        pytest.param(dt.date(2026, 6, 24), "text", "date", "iso", "2026-06-24", id="date-iso"),
        pytest.param(dt.date(2026, 6, 24), "text", "date", "long", "24 June 2026", id="date-long"),
        # kind="bool" would infer Yes/No, but the override forces raw.
        pytest.param(True, "bool", "raw", None, "True", id="override-wins-over-inference"),
    ],
)
def test_override(value, column_kind, fmt, arg, expected):
    assert format_cell(value, column_kind, override=ResolvedFormat(fmt, arg)) == expected


@pytest.mark.parametrize(
    "value,kind,kw,expected",
    [
        (None, "text", {}, ""),  # None → blank
        ("", "text", {}, ""),  # empty → blank
        (0, "text", {}, "0"),  # zero is NOT blanked
        (True, "bool", {}, "Yes"),
        (False, "bool", {}, "No"),
        (True, "text", {}, "Yes"),  # bool value → Yes/No even in a generic column
        ("ACTIVE", "badge", {}, "Active"),  # enum token → Title Case
        ("in_review", "badge", {}, "In Review"),
        (3.14159, "text", {}, "3.14"),  # float → 2dp (value-type keyed)
        (10.0, "text", {}, "10.00"),
        (42, "text", {}, "42"),  # int → as-is
        ("Acme Ltd", "ref", {}, "Acme Ltd"),  # FK value already a name
        (12345, "currency", {"currency_code": "GBP"}, "£123.45"),  # minor units → currency
        (12345, "currency", {"currency_code": "XYZ"}, "123.45 XYZ"),  # unknown symbol → code suffix
        # format_cell returns RAW strings — the renderer escapes at emit time,
        # so pre-escaping here would double-encode (see the render-path test).
        ("<script>", "text", {}, "<script>"),
        ("a & b", "badge", {}, "A & B"),
    ],
)
def test_inference(value, kind, kw, expected):
    assert format_cell(value, kind, **kw) == expected


@pytest.mark.parametrize(
    ("value", "present", "absent"),
    [
        pytest.param(dt.datetime(2026, 6, 24, 9, 30), ("2026", "Jun"), ("T",), id="datetime"),
        pytest.param(dt.date(2026, 6, 24), ("2026", "Jun"), (), id="date"),
        pytest.param("2026-06-24T09:30:00", ("2026",), ("T",), id="iso-string-datetime"),
    ],
)
def test_date_column_renders_friendly_not_iso(value, present, absent):
    out = format_cell(value, "date")
    assert all(s in out for s in present), out
    assert not any(s in out for s in absent), out


def test_ref_dict_uses_display_not_str_dict() -> None:
    """#1615: related tables pass hydrated FK dicts — never str(dict) in UI."""
    raw = {
        "id": "a9a9826a-5708-4dfd-87e1-38cbd08e8964",
        "first_name": "Demo",
        "last_name": "Chen",
        "email": "customer@test.local",
        "__display__": "customer@test.local",
    }
    out = format_cell(raw, "ref")
    assert out == "customer@test.local"
    assert "{" not in out and "id" not in out
    # Without __display__, fall back to name heuristics
    out2 = format_cell(
        {"id": "x", "first_name": "Ada", "last_name": "Lovelace"},
        "ref",
    )
    assert out2 == "Ada Lovelace"
    assert "id" not in out2


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
