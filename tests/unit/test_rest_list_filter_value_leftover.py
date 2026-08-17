"""Leftover REST ?filter[status]=zzz must not invent empty (cycle 2194).

Page leftover-honest enum values already exist
(``_parse_list_filter_enum_values`` / oral #69). REST
``list_handlers`` still landed leftover VALUES on known keys in
``gated_list`` / ``repo.list`` and invented empty via fail-closed
enum match. Valid declared options ride; leftover restores
unfiltered (omit). Oral #75 — not another GET list ``filter[key]``
parse (oral #74).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.page_routes import (
    entity_enum_filter_options,
    leftover_honest_list_filters,
)

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
_STATUS = ("open", "in_progress", "resolved", "closed")
_PRIORITY = ("low", "medium", "high", "critical")
_ENUMS = {"status": _STATUS, "priority": _PRIORITY}
_SPEC = SimpleNamespace(
    fields=[
        SimpleNamespace(name="id"),
        SimpleNamespace(name="title"),
        SimpleNamespace(name="status", type=SimpleNamespace(enum_values=list(_STATUS))),
        SimpleNamespace(name="priority", type=SimpleNamespace(enum_values=list(_PRIORITY))),
        SimpleNamespace(name="created_at"),
    ]
)


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"filter[status]": "zzz"}, {}),
        ({"filter[status]": "ghost"}, {}),
        ({"filter[status]": "not-a-status"}, {}),
        ({"filter[priority]": "zzz"}, {}),
        ({"filter[status]": "resolved"}, {"status": "resolved"}),
        ({"filter[priority]": "critical"}, {"priority": "critical"}),
        (
            {"filter[status]": "zzz", "filter[title]": "Invoice"},
            {"title": "Invoice"},
        ),
        (
            {"filter[status]": "open", "filter[title]": "Invoice"},
            {"status": "open", "title": "Invoice"},
        ),
        (
            {"filter[status]": "zzz", "filter[priority]": "high"},
            {"priority": "high"},
        ),
        ({"status": "zzz"}, {}),
        ({"status": "in_progress"}, {"status": "in_progress"}),
        ({}, {}),
        (None, {}),
    ],
    ids=[
        "bracket-leftover-status",
        "bracket-leftover-ghost",
        "bracket-leftover-words",
        "bracket-leftover-priority",
        "bracket-valid-status",
        "bracket-valid-priority",
        "bracket-leftover-plus-title",
        "bracket-valid-plus-title",
        "bracket-leftover-status-plus-valid-priority",
        "bare-leftover-status",
        "bare-valid-status",
        "empty-params",
        "none-params",
    ],
)
def test_leftover_honest_list_filter_values_do_not_invent(
    params: dict[str, str] | None,
    expected: dict[str, str],
) -> None:
    query = params if params is not None else SimpleNamespace()
    assert (
        leftover_honest_list_filters(
            query,
            allowed=_ALLOWED,
            filter_fields=["status", "priority"],
            entity_spec=_SPEC,
        )
        == expected
    )
    assert (
        leftover_honest_list_filters(
            query,
            allowed=_ALLOWED,
            filter_fields=["status", "priority"],
            enum_options=_ENUMS,
        )
        == expected
    )


def test_entity_enum_filter_options_reads_spec() -> None:
    assert entity_enum_filter_options(_SPEC) == _ENUMS
    assert entity_enum_filter_options(None) == {}
    assert entity_enum_filter_options(SimpleNamespace()) == {}
    assert entity_enum_filter_options(SimpleNamespace(fields=[SimpleNamespace(name="title")])) == {}


def test_helper_source_pins_list_filter_value_leftover() -> None:
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "def leftover_honest_list_filters" in src
    assert "def entity_enum_filter_options" in src
    assert "_parse_list_filter_enum_values" in src
    assert "filter[status]=zzz" in src


def test_list_handler_source_pins_filter_value_leftover() -> None:
    src = _LIST.read_text(encoding="utf-8")
    assert "leftover_honest_list_filters(" in src
    assert 'entity_spec=getattr(service, "entity_spec", None)' in src


def test_live_support_tickets_ticket_status_enum() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert 'entity Ticket "Support Ticket":' in src
    assert "status: enum[open,in_progress,resolved,closed]=open" in src
    assert "priority: enum[low,medium,high,critical]=medium" in src
