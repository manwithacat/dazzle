"""1d raw-data honesty — the shared cell core humanises every type (#1491).

Before this, detail views fed the cell core FORM-input types
(`checkbox`/`datetime`/`number`/`select`/`textarea`) it didn't recognise, so it
leaked raw `True` / ISO timestamps / full-precision floats / mangled JSON. The
fix reconciles form→display types at the detail seam and gives the core
`datetime`/`number`/`json` branches + a dict/float-aware default.
"""

from __future__ import annotations

import datetime as dt

import pytest

from dazzle.http.runtime.renderers.fragment_adapter import _detail_field_value
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.renderer._data_row import _json_summary, _render_cell_display

_RAW_FLOAT = 0.8850441412520064


def _detail(kind: str, value: object) -> str:
    return FragmentRenderer().render(_detail_field_value({"kind": kind, "value": value}))


# Aware UTC datetimes keep the date stable across CI host TZ; the wall-clock
# part may follow the host TZ, so only a human ":" time component is required.
@pytest.mark.parametrize(
    ("kind", "value", "present", "absent"),
    [
        pytest.param("checkbox", True, [], ["True"], id="checkbox_icon_not_raw_true"),
        pytest.param(
            "datetime",
            dt.datetime(2026, 6, 30, 3, 1, 29, tzinfo=dt.UTC),
            ["Jun 2026", ":"],
            ["2026-06-30T"],
            id="datetime_humanised_with_time",
        ),
        pytest.param("number", _RAW_FLOAT, ["0.89"], [str(_RAW_FLOAT)], id="number_rounds_float"),
        pytest.param("select", "open", ["dz-badge", "Open"], [], id="select_renders_badge"),
        pytest.param(
            "textarea",
            {"currency": "GBP", "amount": 500},
            ["currency: GBP", "amount: 500"],
            [],
            id="json_dict_summarised_not_collapsed_to_one_value",
        ),
    ],
)
def test_detail_seam_humanises_form_typed_values(
    kind: str, value: object, present: list[str], absent: list[str]
) -> None:
    """The main leak: form-input types reaching the detail view."""
    html = _detail(kind, value)
    for fragment in present:
        assert fragment in html
    for fragment in absent:
        assert fragment not in html


@pytest.mark.parametrize(
    ("col_type", "value", "present", "absent"),
    [
        pytest.param(
            "datetime",
            dt.datetime(2026, 1, 2, 9, 5, tzinfo=dt.UTC),
            ["Jan 2026", ":"],
            ["2026-01-02T"],
            id="datetime_unpadded_day",
        ),
        pytest.param("number", _RAW_FLOAT, ["0.89"], [str(_RAW_FLOAT)], id="number_rounds"),
        pytest.param("json", {"a": 1, "b": 2}, ["a: 1", "b: 2"], [], id="json_summary"),
        pytest.param(
            "text",
            {"currency": "GBP", "amount": 500},
            ["currency: GBP", "amount: 500"],
            [],
            id="text_default_summarises_dict",
        ),
        pytest.param(
            "text", _RAW_FLOAT, ["0.89"], [str(_RAW_FLOAT)], id="text_default_rounds_float"
        ),
    ],
)
def test_cell_core_humanises(
    col_type: str, value: object, present: list[str], absent: list[str]
) -> None:
    """The shared cell core (also used by list rows)."""
    out = _render_cell_display({"type": col_type}, value)
    for fragment in present:
        assert fragment in out
    for fragment in absent:
        assert fragment not in out


@pytest.mark.parametrize(
    ("col_type", "value"),
    [
        pytest.param("number", None, id="number_null_not_zero"),
        pytest.param("number", "", id="number_blank_not_zero"),
        pytest.param("json", None, id="json_null_not_None"),
        pytest.param("datetime", None, id="datetime_null"),
    ],
)
def test_cell_core_null_renders_dash(col_type: str, value: object) -> None:
    """Regression: a null list cell must not fabricate "0" or leak "None"."""
    assert _render_cell_display({"type": col_type}, value) == "—"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param({"a": 1, "b": 2}, "a: 1 · b: 2", id="dict"),
        pytest.param([1, 2, 3], "1, 2, 3", id="list"),
        pytest.param(
            {str(i): i for i in range(6)}, "0: 0 · 1: 1 · 2: 2 · 3: 3 · …", id="dict_truncated"
        ),
        pytest.param([1, 2, 3, 4, 5, 6], "1, 2, 3, 4, …", id="list_truncated"),
    ],
)
def test_json_summary(value: object, expected: str) -> None:
    assert _json_summary(value) == expected
