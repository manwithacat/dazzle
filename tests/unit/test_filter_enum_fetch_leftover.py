"""Leftover filter_<enum> must not invent empty via fetch (cycle 2190).

Picker restore All already exists (oral #69 /
``compute_filter_columns_and_active``). ``workspace_region_fetch`` still
applied raw ``filters[field]=param_val``, so leftover junk (``zzz``,
``ghost``) invented an empty collection while the picker showed All.
Valid declared options ride. Rest is All (omit). Live support_tickets
``Ticket.status``. Oral #72 — not another picker-catalog sibling.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.http.runtime.workspace_region_fetch import (
    _apply_leftover_honest_filter_enums,
)

_FETCH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "workspace_region_fetch.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "support_tickets" / "dsl" / "app.dsl"

_COLUMNS = [
    {
        "key": "status",
        "label": "Status",
        "filterable": True,
        "filter_options": ["open", "in_progress", "resolved", "closed"],
    },
    {
        "key": "title",
        "label": "Title",
        "filterable": False,
    },
]


def test_fetch_omits_leftover_filter_enum() -> None:
    req = SimpleNamespace(query_params={"filter_status": "zzz"})
    assert _apply_leftover_honest_filter_enums(req, None, _COLUMNS) is None
    assert _apply_leftover_honest_filter_enums(req, {"priority": "high"}, _COLUMNS) == {
        "priority": "high"
    }
    req = SimpleNamespace(query_params={"filter_status": "ghost"})
    assert _apply_leftover_honest_filter_enums(req, None, _COLUMNS) is None
    req = SimpleNamespace(query_params={"filter_status": "not-a-status"})
    assert _apply_leftover_honest_filter_enums(req, None, _COLUMNS) is None


def test_fetch_rides_valid_filter_enum() -> None:
    req = SimpleNamespace(query_params={"filter_status": "resolved"})
    assert _apply_leftover_honest_filter_enums(req, None, _COLUMNS) == {"status": "resolved"}
    assert _apply_leftover_honest_filter_enums(req, {"priority": "high"}, _COLUMNS) == {
        "priority": "high",
        "status": "resolved",
    }


def test_fetch_absent_filter_enum_stays_unbound() -> None:
    req = SimpleNamespace(query_params={})
    assert _apply_leftover_honest_filter_enums(req, None, _COLUMNS) is None
    assert _apply_leftover_honest_filter_enums(req, {"priority": "high"}, _COLUMNS) == {
        "priority": "high"
    }
    assert (
        _apply_leftover_honest_filter_enums(SimpleNamespace(query_params=None), None, _COLUMNS)
        is None
    )
    assert _apply_leftover_honest_filter_enums(SimpleNamespace(), None, _COLUMNS) is None


def test_fetch_non_enum_filter_still_applies() -> None:
    req = SimpleNamespace(query_params={"filter_title": "Ada"})
    assert _apply_leftover_honest_filter_enums(req, None, _COLUMNS) == {"title": "Ada"}


def test_fetch_source_pins_filter_enum_leftover() -> None:
    src = _FETCH.read_text(encoding="utf-8")
    assert "def _apply_leftover_honest_filter_enums" in src
    assert "compute_filter_columns_and_active" in src
    assert "filters = _apply_leftover_honest_filter_enums(" in src
    assert "filters[field_name] = param_val" not in src


def test_live_support_tickets_status_enum() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert "status: enum[open,in_progress,resolved,closed]=open" in src
    assert "open_queue:" in src
    assert "source: Ticket" in src
