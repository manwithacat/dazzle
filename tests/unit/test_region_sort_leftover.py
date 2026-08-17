"""Leftover workspace/REST ?sort= must not invent empty (cycle 2191).

List leftover-honest sort already exists (``_parse_list_sort`` / oral #48).
``workspace_region_fetch`` and REST ``list_handlers`` still applied raw
FastAPI ``sort``, so leftover junk (``zzz``, ``ghost``) reached
``repo.list`` and invented empty via fail-closed SQL/identifier. Valid
entity fields ride; leftover restores IR / surface / unsorted default.
Oral #73 — not another list-page sort clone.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.page_routes import entity_known_sort_fields, leftover_honest_sort

_PAGE_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
)
_FETCH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "workspace_region_fetch.py"
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

_ALLOWED = frozenset({"id", "title", "status", "created_at", "priority"})


@pytest.mark.parametrize(
    ("raw_sort", "raw_dir", "expected"),
    [
        ("zzz", "asc", (None, "asc")),
        ("ghost", "desc", (None, "desc")),
        ("2abc", "asc", (None, "asc")),
        ("not-a-field", "desc", (None, "desc")),
        ("", "asc", (None, "asc")),
        (None, "asc", (None, "asc")),
        ("  ", "desc", (None, "desc")),
        ("-zzz", "asc", (None, "asc")),
        ("title", "asc", ("title", "asc")),
        ("-title", "desc", ("title", "desc")),
        ("created_at", "zzz", ("created_at", "asc")),
        ("status", "DESC", ("status", "desc")),
        ("priority", "2abc", ("priority", "asc")),
    ],
    ids=[
        "sort-leftover-named",
        "sort-leftover-ghost",
        "sort-leftover-suffix",
        "sort-leftover-words",
        "sort-empty",
        "sort-none",
        "sort-whitespace",
        "sort-leftover-minus",
        "sort-valid-title",
        "sort-valid-minus-stripped",
        "dir-leftover-named",
        "dir-valid-desc",
        "dir-leftover-suffix",
    ],
)
def test_leftover_honest_sort_does_not_invent(
    raw_sort: object, raw_dir: object, expected: tuple[str | None, str]
) -> None:
    assert leftover_honest_sort(raw_sort, raw_dir, allowed=_ALLOWED) == expected


def test_entity_known_sort_fields_includes_spec_and_extra() -> None:
    spec = SimpleNamespace(
        fields=[
            SimpleNamespace(name="title"),
            SimpleNamespace(name="status"),
            SimpleNamespace(name="created_at"),
        ]
    )
    assert entity_known_sort_fields(spec, ["priority", "ticket_number"]) == frozenset(
        {"id", "title", "status", "created_at", "priority", "ticket_number"}
    )
    assert entity_known_sort_fields(None) == frozenset({"id"})
    assert entity_known_sort_fields(SimpleNamespace()) == frozenset({"id"})


def test_fetch_source_pins_region_sort_leftover() -> None:
    src = _FETCH.read_text(encoding="utf-8")
    assert "leftover_honest_sort(" in src
    assert "entity_known_sort_fields(" in src
    assert "search_fields" in src
    assert 'sort_list = [f"-{sort}" if sort_dir == "desc" else sort]' in src


def test_list_handler_source_pins_sort_leftover() -> None:
    src = _LIST.read_text(encoding="utf-8")
    assert "leftover_honest_sort(" in src
    assert "entity_known_sort_fields(" in src
    assert 'sort_list = [f"-{sort}" if dir == "desc" else sort] if sort else None' in src


def test_helper_source_pins_sort_leftover() -> None:
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "def leftover_honest_sort" in src
    assert "def entity_known_sort_fields" in src
    assert "invent empty via fail-closed" in src


def test_live_support_tickets_ticket_sort_fields() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert 'entity Ticket "Support Ticket":' in src
    assert "created_at:" in src
    assert "status: enum[open,in_progress,resolved,closed]=open" in src
    assert "sort: created_at desc" in src
