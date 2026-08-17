"""Leftover REST ?filter[zzz]= must not invent empty (cycle 2193).

Page leftover-honest ``filter[key]`` already exists (``_parse_list_filters``
/ oral #48). REST ``list_handlers`` still copied raw ``filter[zzz]`` into
``gated_list`` / ``repo.list`` and invented empty via fail-closed unknown
column. Valid entity / DSL filter fields ride; leftover keys restore
unfiltered (omit). Oral #74 — not another FastAPI ``?sort=`` clone
(oral #73) and not another ``filter_<enum>`` fetch clone (oral #72).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.page_routes import leftover_honest_list_filters

_PAGE_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
)
_LIST = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "handlers"
    / "list_handlers.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "support_tickets" / "dsl" / "app.dsl"

_ALLOWED = frozenset({"id", "title", "status", "priority", "created_at"})


@pytest.mark.parametrize(
    ("params", "filter_fields", "expected"),
    [
        ({"filter[zzz]": "Ada"}, None, {}),
        ({"filter[ghost]": "1"}, None, {}),
        ({"filter[2abc]": "open"}, None, {}),
        ({"filter[not-a-field]": "x"}, None, {}),
        ({"filter[]": "x"}, None, {}),
        ({"filter[status]": "open"}, None, {"status": "open"}),
        ({"filter[priority]": "high"}, None, {"priority": "high"}),
        (
            {"filter[zzz]": "Ada", "filter[status]": "open"},
            None,
            {"status": "open"},
        ),
        ({"filter[status__gte]": "b"}, None, {"status__gte": "b"}),
        ({"filter[ghost__gte]": "b"}, None, {}),
        ({"status": "open"}, ["status"], {"status": "open"}),
        ({"ghost": "Ada"}, ["status"], {}),
        ({"filter[zzz]": "Ada", "status": "open"}, ["status"], {"status": "open"}),
        ({"sort": "zzz", "filter[title]": "Invoice"}, None, {"title": "Invoice"}),
        ({}, None, {}),
        (None, None, {}),
    ],
    ids=[
        "bracket-leftover-named",
        "bracket-leftover-ghost",
        "bracket-leftover-suffix",
        "bracket-leftover-words",
        "bracket-empty-key",
        "bracket-valid-status",
        "bracket-valid-priority",
        "bracket-leftover-plus-valid",
        "bracket-valid-lookup",
        "bracket-leftover-lookup",
        "bare-valid-declared",
        "bare-undeclared",
        "bare-plus-leftover-bracket",
        "sort-junk-plus-valid-filter",
        "empty-params",
        "none-params",
    ],
)
def test_leftover_honest_list_filters_does_not_invent(
    params: dict[str, str] | None,
    filter_fields: list[str] | None,
    expected: dict[str, str],
) -> None:
    query = params if params is not None else SimpleNamespace()
    assert (
        leftover_honest_list_filters(query, allowed=_ALLOWED, filter_fields=filter_fields)
        == expected
    )


def test_helper_source_pins_list_filter_leftover() -> None:
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "def leftover_honest_list_filters" in src
    assert "filter[zzz]" in src
    assert "invent empty via fail-closed" in src


def test_list_handler_source_pins_filter_leftover() -> None:
    src = _LIST.read_text(encoding="utf-8")
    assert "leftover_honest_list_filters(" in src
    assert "entity_known_sort_fields(" in src
    assert "filters[key[7:-1]] = value" not in src


def test_live_support_tickets_ticket_filter_fields() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert 'entity Ticket "Support Ticket":' in src
    assert "status: enum[open,in_progress,resolved,closed]=open" in src
    assert "priority: enum[low,medium,high,critical]=medium" in src
