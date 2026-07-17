"""1d raw-data honesty — the shared cell core humanises every type (#1491).

Before this, detail views fed the cell core FORM-input types
(`checkbox`/`datetime`/`number`/`select`/`textarea`) it didn't recognise, so it
leaked raw `True` / ISO timestamps / full-precision floats / mangled JSON. The
fix reconciles form→display types at the detail seam and gives the core
`datetime`/`number`/`json` branches + a dict/float-aware default.
"""

from __future__ import annotations

import datetime as dt

from dazzle.http.runtime.renderers.fragment_adapter import _detail_field_value
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.renderer._data_row import _json_summary, _render_cell_display


def _detail(kind: str, value: object) -> str:
    return FragmentRenderer().render(_detail_field_value({"kind": kind, "value": value}))


# ── detail seam: form-typed values are humanised (the main leak) ──────────


def test_detail_checkbox_renders_icon_not_raw_true() -> None:
    html = _detail("checkbox", True)
    assert "True" not in html  # → ✓ icon, not the raw bool repr


def test_detail_datetime_humanised_with_time() -> None:
    # Aware UTC so display is stable across CI host TZ; day is unpadded ("30" stays).
    html = _detail("datetime", dt.datetime(2026, 6, 30, 3, 1, 29, tzinfo=dt.UTC))
    assert "2026-06-30T" not in html
    assert "Jun 2026" in html
    # Wall clock may follow host local TZ — only require a human time component.
    assert ":" in html


def test_detail_number_rounds_float() -> None:
    html = _detail("number", 0.8850441412520064)
    assert "0.8850441412520064" not in html
    assert "0.89" in html


def test_detail_select_renders_badge() -> None:
    html = _detail("select", "open")
    assert "dz-badge" in html
    assert "Open" in html


def test_detail_json_dict_is_summarised_not_mangled() -> None:
    # The old path routed a dict through _ref_display_name → a single arbitrary
    # value ("GBP"); now it's a compact key:value summary.
    html = _detail("textarea", {"currency": "GBP", "amount": 500})
    assert "currency: GBP" in html
    assert "amount: 500" in html


# ── cell core branches (also used by list rows) ──────────────────────────


def test_core_datetime_branch() -> None:
    # Humanised form uses unpadded day ("2 Jan …"), not zero-padded "02".
    out = _render_cell_display({"type": "datetime"}, dt.datetime(2026, 1, 2, 9, 5, tzinfo=dt.UTC))
    assert "Jan 2026" in out
    assert "2026-01-02T" not in out
    assert ":" in out


def test_core_number_branch_rounds() -> None:
    assert "0.89" in _render_cell_display({"type": "number"}, 0.8850441412520064)


def test_core_json_branch() -> None:
    out = _render_cell_display({"type": "json"}, {"a": 1, "b": 2})
    assert "a: 1" in out and "b: 2" in out


def test_core_default_summarises_dict_not_ref_mangle() -> None:
    # A dict reaching the text default (e.g. a `text`-typed JSON column) is
    # summarised, not collapsed to one value.
    out = _render_cell_display({"type": "text"}, {"currency": "GBP", "amount": 500})
    assert "amount: 500" in out


def test_core_default_rounds_bare_float() -> None:
    assert "0.89" in _render_cell_display({"type": "text"}, 0.8850441412520064)


def test_core_null_humanised_types_render_dash_not_repr() -> None:
    # Regression: a null list cell must not fabricate "0" (number) or leak
    # "None" (json) — both render the em-dash placeholder.
    assert _render_cell_display({"type": "number"}, None) == "—"
    assert _render_cell_display({"type": "json"}, None) == "—"
    assert _render_cell_display({"type": "datetime"}, None) == "—"
    assert _render_cell_display({"type": "number"}, "") == "—"


# ── json summary helper ───────────────────────────────────────────────────


def test_json_summary_dict_and_list_and_truncation() -> None:
    assert _json_summary({"a": 1, "b": 2}) == "a: 1 · b: 2"
    assert _json_summary([1, 2, 3]) == "1, 2, 3"
    # > max_pairs gets an ellipsis
    assert _json_summary({str(i): i for i in range(6)}).endswith("· …")
    assert _json_summary([1, 2, 3, 4, 5, 6]).endswith(", …")
