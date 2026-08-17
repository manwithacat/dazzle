"""Leftover date_from / date_to must not invent an empty window (cycle 2186).

``?date_from=zzz`` / ``?date_to=not-a-date`` used to ride
``{date_field}__gte`` / ``__lte`` and invent an empty collection.
Valid YYYY-MM-DD still windows. Rest is unbounded (omit). Live in
support_tickets ``open_queue`` ``date_field: created_at``. Distinct
from leftover ``as_of`` (oral #49), DateRangePicker companion
parse-invent (oral #42), and leftover temporal echo (oral #67).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.workspace_region_fetch import _apply_leftover_honest_date_window
from dazzle.render.fragment import URL, DateRangePicker, FragmentRenderer
from dazzle.render.fragment.renderer._render_interactive import leftover_honest_iso_date

_HELPER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "render"
    / "fragment"
    / "renderer"
    / "_render_interactive.py"
)
_FETCH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "workspace_region_fetch.py"
)
_RENDER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "workspace_region_render.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "support_tickets" / "dsl" / "app.dsl"
_CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "hatchi-maxchi"
    / "contracts"
    / "date_range.py"
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("zzz", ""),
        ("2abc", ""),
        ("not-a-date", ""),
        ("2026-13-01", ""),
        ("2026/06/20", ""),
        ("", ""),
        (None, ""),
        ("  ", ""),
        ("2026-06-20", "2026-06-20"),
        (" 2026-01-01 ", "2026-01-01"),
    ],
    ids=[
        "window-leftover-named",
        "window-leftover-suffix",
        "window-leftover-words",
        "window-leftover-month",
        "window-leftover-slashes",
        "window-empty",
        "window-none",
        "window-whitespace",
        "window-valid",
        "window-valid-padded",
    ],
)
def test_leftover_honest_iso_date_does_not_invent(raw: object, expected: str) -> None:
    assert leftover_honest_iso_date(raw) == expected


def test_fetch_omits_leftover_window() -> None:
    req = SimpleNamespace(query_params={"date_from": "zzz", "date_to": "not-a-date"})
    assert _apply_leftover_honest_date_window(req, "created_at", None) is None
    assert _apply_leftover_honest_date_window(req, "created_at", {"status": "open"}) == {
        "status": "open"
    }


def test_fetch_rides_valid_window() -> None:
    req = SimpleNamespace(query_params={"date_from": "2026-01-01", "date_to": "2026-06-30"})
    assert _apply_leftover_honest_date_window(req, "created_at", None) == {
        "created_at__gte": "2026-01-01",
        "created_at__lte": "2026-06-30",
    }


def test_fetch_one_bound_leftover_does_not_invent_pair() -> None:
    req = SimpleNamespace(query_params={"date_from": "2026-01-01", "date_to": "zzz"})
    assert _apply_leftover_honest_date_window(req, "created_at", None) == {
        "created_at__gte": "2026-01-01",
    }
    req = SimpleNamespace(query_params={"date_from": "ghost", "date_to": "2026-06-30"})
    assert _apply_leftover_honest_date_window(req, "created_at", None) == {
        "created_at__lte": "2026-06-30",
    }


def test_fetch_skips_when_date_field_absent() -> None:
    req = SimpleNamespace(query_params={"date_from": "2026-01-01"})
    assert _apply_leftover_honest_date_window(req, "", None) is None


def test_picker_leftover_bounds_restore_empty() -> None:
    html = FragmentRenderer().render(
        DateRangePicker(
            endpoint=URL("/app/x"),
            region_name="r",
            date_from="zzz",
            date_to="not-a-date",
        )
    )
    assert 'value="zzz"' not in html
    assert 'value="not-a-date"' not in html
    assert 'name="date_from"' in html
    assert 'name="date_to"' in html


def test_picker_valid_bounds_still_ride() -> None:
    html = FragmentRenderer().render(
        DateRangePicker(
            endpoint=URL("/app/x"),
            region_name="r",
            date_from="2026-06-01",
            date_to="2026-06-30",
        )
    )
    assert 'value="2026-06-01"' in html
    assert 'value="2026-06-30"' in html


def test_helper_source_pins_window_leftover() -> None:
    src = _HELPER.read_text(encoding="utf-8")
    assert "def leftover_honest_iso_date" in src
    assert "date_from" in src
    assert "Cycle 2186" in src


def test_fetch_source_pins_window_leftover() -> None:
    src = _FETCH.read_text(encoding="utf-8")
    assert "def _apply_leftover_honest_date_window" in src
    assert "leftover_honest_iso_date" in src
    assert 'qparams.get("date_from")' in src
    assert 'out[f"{date_field}__gte"] = date_from' in src


def test_render_source_pins_window_leftover() -> None:
    src = _RENDER.read_text(encoding="utf-8")
    assert "leftover_honest_iso_date" in src
    assert 'query_params.get("date_from"' in src
    assert 'query_params.get("date_to"' in src


def test_live_support_tickets_open_queue_date_window() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert "date_range" in src
    assert "date_field: created_at" in src
    assert "open_queue:" in src


def test_date_range_contract_pins_window_leftover() -> None:
    src = _CONTRACT.read_text(encoding="utf-8")
    assert "_leftover_honest_iso_date" in src
    assert "cycle 2186" in src.lower() or "Cycle 2186" in src
