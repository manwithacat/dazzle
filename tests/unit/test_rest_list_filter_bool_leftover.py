"""Leftover REST ?filter[is_active]=zzz must not invent empty (cycle 2197).

leftover include_closed already exists (cycle 2168) and restores
False default. REST ``list_handlers`` still landed leftover BOOL
VALUES on known ``is_active`` keys in ``gated_list`` / ``repo.list``
and invented empty / the inactive-only slice. Valid true/false
tokens ride; leftover restores unfiltered (omit). Oral #78 —
not another GET list date VALUE (oral #77).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.page_routes import (
    entity_bool_filter_fields,
    leftover_honest_filter_bool,
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

_ALLOWED = frozenset({"id", "title", "status", "is_active", "is_starred"})
_SPEC = SimpleNamespace(
    fields=[
        SimpleNamespace(name="id"),
        SimpleNamespace(name="title"),
        SimpleNamespace(name="status"),
        SimpleNamespace(name="is_active", type=SimpleNamespace(kind="bool")),
        SimpleNamespace(name="is_starred", type=SimpleNamespace(kind="boolean")),
    ]
)


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"filter[is_active]": "zzz"}, {}),
        ({"filter[is_active]": "ghost"}, {}),
        ({"filter[is_active]": "maybe"}, {}),
        ({"filter[is_active]": "true"}, {"is_active": "true"}),
        ({"filter[is_active]": "false"}, {"is_active": "false"}),
        ({"filter[is_active]": "1"}, {"is_active": "1"}),
        ({"filter[is_active]": "0"}, {"is_active": "0"}),
        ({"filter[is_starred]": "zzz"}, {}),
        ({"filter[is_starred]": "yes"}, {"is_starred": "yes"}),
        (
            {"filter[is_active]": "zzz", "filter[title]": "Invoice"},
            {"title": "Invoice"},
        ),
        (
            {"filter[is_active]": "true", "filter[title]": "Invoice"},
            {"is_active": "true", "title": "Invoice"},
        ),
        ({"is_active": "zzz"}, {}),
        ({"is_active": "false"}, {"is_active": "false"}),
        ({}, {}),
        (None, {}),
    ],
    ids=[
        "bracket-leftover-active",
        "bracket-leftover-ghost",
        "bracket-leftover-maybe",
        "bracket-valid-true",
        "bracket-valid-false",
        "bracket-valid-one",
        "bracket-valid-zero",
        "bracket-leftover-starred",
        "bracket-valid-yes",
        "bracket-leftover-plus-title",
        "bracket-valid-plus-title",
        "bare-leftover-active",
        "bare-valid-false",
        "empty-params",
        "none-params",
    ],
)
def test_leftover_honest_list_filter_bool_values_do_not_invent(
    params: dict[str, str] | None,
    expected: dict[str, str],
) -> None:
    query = params if params is not None else SimpleNamespace()
    assert (
        leftover_honest_list_filters(
            query,
            allowed=_ALLOWED,
            filter_fields=["is_active", "is_starred", "title"],
            entity_spec=_SPEC,
        )
        == expected
    )


def test_entity_bool_filter_fields_reads_spec() -> None:
    assert entity_bool_filter_fields(_SPEC) == frozenset({"is_active", "is_starred"})
    assert entity_bool_filter_fields(None) == frozenset()
    assert entity_bool_filter_fields(SimpleNamespace()) == frozenset()
    assert entity_bool_filter_fields(SimpleNamespace(fields=[SimpleNamespace(name="title")])) == (
        frozenset()
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("zzz", ""),
        ("ghost", ""),
        ("maybe", ""),
        ("", ""),
        (None, ""),
        ("true", "true"),
        ("FALSE", "FALSE"),
        ("1", "1"),
        ("0", "0"),
        ("yes", "yes"),
        ("no", "no"),
        (True, "true"),
        (False, "false"),
    ],
    ids=[
        "junk",
        "ghost",
        "maybe",
        "empty",
        "none",
        "true",
        "false-upper",
        "one",
        "zero",
        "yes",
        "no",
        "py-true",
        "py-false",
    ],
)
def test_leftover_honest_filter_bool_does_not_invent(raw: object, expected: str) -> None:
    assert leftover_honest_filter_bool(raw) == expected


def test_helper_source_pins_list_filter_bool_leftover() -> None:
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "def leftover_honest_list_filters" in src
    assert "def entity_bool_filter_fields" in src
    assert "_parse_list_filter_bool_values" in src
    assert "filter[is_active]=zzz" in src
    assert "leftover_honest_filter_bool" in src


def test_list_handler_source_pins_filter_bool_leftover() -> None:
    src = _LIST.read_text(encoding="utf-8")
    assert "leftover_honest_list_filters(" in src
    assert "filter[is_active]=zzz" in src


def test_live_support_tickets_user_is_active() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert 'entity User "User":' in src or "entity User" in src
    assert "is_active: bool" in src
