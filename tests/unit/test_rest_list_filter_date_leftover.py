"""Leftover REST ?filter[created_at]=zzz must not invent empty (cycle 2196).

leftover_honest_iso_date already exists (oral #70). REST
``list_handlers`` still landed leftover DATE VALUES on known
``created_at`` / ``due_date`` keys in ``gated_list`` / ``repo.list``
and invented empty via fail-closed date match. Valid ISO dates /
datetimes ride; leftover restores unfiltered (omit). Oral #77 —
not another GET list filter[id] VALUE (oral #76).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.page_routes import (
    entity_date_filter_fields,
    leftover_honest_filter_datetime,
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
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "simple_task" / "dsl" / "app.dsl"

_ALLOWED = frozenset({"id", "title", "status", "created_at", "due_date"})
_DAY = "2026-07-01"
_DT = "2026-07-01T09:00:00"
_SPEC = SimpleNamespace(
    fields=[
        SimpleNamespace(name="id"),
        SimpleNamespace(name="title"),
        SimpleNamespace(name="status"),
        SimpleNamespace(name="created_at", type=SimpleNamespace(kind="datetime")),
        SimpleNamespace(name="due_date", type=SimpleNamespace(kind="date")),
    ]
)


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"filter[created_at]": "zzz"}, {}),
        ({"filter[created_at]": "ghost"}, {}),
        ({"filter[created_at]": "not-a-date"}, {}),
        ({"filter[created_at]": _DAY}, {"created_at": _DAY}),
        ({"filter[created_at]": _DT}, {"created_at": _DT}),
        ({"filter[due_date]": "zzz"}, {}),
        ({"filter[due_date]": _DAY}, {"due_date": _DAY}),
        ({"filter[due_date]": _DT}, {}),
        (
            {"filter[created_at]": "zzz", "filter[title]": "Invoice"},
            {"title": "Invoice"},
        ),
        (
            {"filter[created_at]": _DAY, "filter[title]": "Invoice"},
            {"created_at": _DAY, "title": "Invoice"},
        ),
        ({"created_at": "zzz"}, {}),
        ({"created_at": _DAY}, {"created_at": _DAY}),
        ({}, {}),
        (None, {}),
    ],
    ids=[
        "bracket-leftover-created",
        "bracket-leftover-ghost",
        "bracket-leftover-words",
        "bracket-valid-date",
        "bracket-valid-datetime",
        "bracket-leftover-due",
        "bracket-valid-due",
        "bracket-datetime-on-date",
        "bracket-leftover-plus-title",
        "bracket-valid-plus-title",
        "bare-leftover-created",
        "bare-valid-created",
        "empty-params",
        "none-params",
    ],
)
def test_leftover_honest_list_filter_date_values_do_not_invent(
    params: dict[str, str] | None,
    expected: dict[str, str],
) -> None:
    query = params if params is not None else SimpleNamespace()
    assert (
        leftover_honest_list_filters(
            query,
            allowed=_ALLOWED,
            filter_fields=["created_at", "due_date", "title"],
            entity_spec=_SPEC,
        )
        == expected
    )


def test_entity_date_filter_fields_reads_spec() -> None:
    assert entity_date_filter_fields(_SPEC) == {
        "created_at": "datetime",
        "due_date": "date",
    }
    assert entity_date_filter_fields(None) == {}
    assert entity_date_filter_fields(SimpleNamespace()) == {}
    assert entity_date_filter_fields(SimpleNamespace(fields=[SimpleNamespace(name="title")])) == {}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("zzz", ""),
        ("ghost", ""),
        ("", ""),
        (None, ""),
        (_DAY, _DAY),
        (_DT, _DT),
        ("2026-07-01T09:00:00Z", "2026-07-01T09:00:00Z"),
    ],
    ids=["junk", "ghost", "empty", "none", "date", "datetime", "zulu"],
)
def test_leftover_honest_filter_datetime_does_not_invent(raw: object, expected: str) -> None:
    assert leftover_honest_filter_datetime(raw) == expected


def test_helper_source_pins_list_filter_date_leftover() -> None:
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "def leftover_honest_list_filters" in src
    assert "def entity_date_filter_fields" in src
    assert "_parse_list_filter_date_values" in src
    assert "filter[created_at]=zzz" in src
    assert "leftover_honest_iso_date" in src


def test_list_handler_source_pins_filter_date_leftover() -> None:
    src = _LIST.read_text(encoding="utf-8")
    assert "leftover_honest_list_filters(" in src
    assert "filter[created_at]=zzz" in src


def test_live_simple_task_created_at_and_due_date() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert 'entity Task "Task":' in src
    assert "due_date: date" in src
    assert "created_at: datetime auto_add" in src
