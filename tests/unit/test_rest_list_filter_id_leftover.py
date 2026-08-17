"""Leftover REST ?filter[id]=zzz must not invent empty (cycle 2195).

leftover_honest_entity_id already exists (oral #71). REST
``list_handlers`` still landed leftover UUID VALUES on known
``id`` / REF keys in ``gated_list`` / ``repo.list`` and invented
empty via fail-closed UUID match. Valid UUIDs ride; leftover
restores unfiltered (omit). Oral #76 — not another GET list
filter-enum VALUE (oral #75).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.page_routes import (
    entity_id_filter_fields,
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

_ALLOWED = frozenset({"id", "title", "status", "assigned_to", "created_at"})
_RID = "12345678-1234-5678-1234-567812345678"
_SPEC = SimpleNamespace(
    fields=[
        SimpleNamespace(name="id"),
        SimpleNamespace(name="title"),
        SimpleNamespace(name="status"),
        SimpleNamespace(name="assigned_to", type=SimpleNamespace(kind="ref")),
        SimpleNamespace(name="created_at"),
    ]
)


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"filter[id]": "zzz"}, {}),
        ({"filter[id]": "ghost"}, {}),
        ({"filter[id]": "not-a-uuid"}, {}),
        ({"filter[id]": _RID}, {"id": _RID}),
        ({"filter[assigned_to]": "zzz"}, {}),
        ({"filter[assigned_to]": _RID}, {"assigned_to": _RID}),
        (
            {"filter[id]": "zzz", "filter[title]": "Invoice"},
            {"title": "Invoice"},
        ),
        (
            {"filter[id]": _RID, "filter[title]": "Invoice"},
            {"id": _RID, "title": "Invoice"},
        ),
        ({"id": "zzz"}, {}),
        ({"id": _RID}, {"id": _RID}),
        ({}, {}),
        (None, {}),
    ],
    ids=[
        "bracket-leftover-id",
        "bracket-leftover-ghost",
        "bracket-leftover-words",
        "bracket-valid-id",
        "bracket-leftover-ref",
        "bracket-valid-ref",
        "bracket-leftover-plus-title",
        "bracket-valid-plus-title",
        "bare-leftover-id",
        "bare-valid-id",
        "empty-params",
        "none-params",
    ],
)
def test_leftover_honest_list_filter_id_values_do_not_invent(
    params: dict[str, str] | None,
    expected: dict[str, str],
) -> None:
    query = params if params is not None else SimpleNamespace()
    assert (
        leftover_honest_list_filters(
            query,
            allowed=_ALLOWED,
            filter_fields=["id", "assigned_to", "title"],
            entity_spec=_SPEC,
        )
        == expected
    )


def test_entity_id_filter_fields_reads_spec() -> None:
    assert entity_id_filter_fields(_SPEC) == frozenset({"id", "assigned_to"})
    assert entity_id_filter_fields(None) == frozenset({"id"})
    assert entity_id_filter_fields(SimpleNamespace()) == frozenset({"id"})
    assert entity_id_filter_fields(
        SimpleNamespace(fields=[SimpleNamespace(name="title")])
    ) == frozenset({"id"})


def test_helper_source_pins_list_filter_id_leftover() -> None:
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "def leftover_honest_list_filters" in src
    assert "def entity_id_filter_fields" in src
    assert "_parse_list_filter_entity_id_values" in src
    assert "filter[id]=zzz" in src
    assert "leftover_honest_entity_id" in src


def test_list_handler_source_pins_filter_id_leftover() -> None:
    src = _LIST.read_text(encoding="utf-8")
    assert "leftover_honest_list_filters(" in src
    assert "filter[id]=zzz" in src


def test_live_support_tickets_ticket_id_and_ref() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert 'entity Ticket "Support Ticket":' in src
    assert "assigned_to: ref User" in src
    assert "created_by: ref User required" in src
