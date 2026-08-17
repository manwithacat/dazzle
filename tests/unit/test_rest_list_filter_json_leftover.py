"""Leftover REST ?filter[preferences]=zzz must not invent empty (cycle 2203).

leftover-honest file VALUES already exist (oral #83). REST
``list_handlers`` still landed leftover JSON VALUES on known
``preferences`` keys in ``gated_list`` / ``repo.list`` and invented
empty. Valid JSON rides; leftover restores unfiltered (omit).
Oral #84 — not another GET list file VALUE (oral #83).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.page_routes import (
    entity_json_filter_fields,
    leftover_honest_filter_json,
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

_ALLOWED = frozenset({"id", "title", "status", "preferences", "settings"})
_SPEC = SimpleNamespace(
    fields=[
        SimpleNamespace(name="id"),
        SimpleNamespace(name="title"),
        SimpleNamespace(name="status"),
        SimpleNamespace(name="preferences", type=SimpleNamespace(kind="json")),
        SimpleNamespace(name="settings", type=SimpleNamespace(kind="json")),
    ]
)
_THEME = '{"theme":"dark"}'
_LIST_JSON = '["a","b"]'


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"filter[preferences]": "zzz"}, {}),
        ({"filter[preferences]": "ghost"}, {}),
        ({"filter[preferences]": "not-json"}, {}),
        ({"filter[preferences]": "foo"}, {}),
        ({"filter[preferences]": "{theme:dark}"}, {}),
        ({"filter[preferences]": _THEME}, {"preferences": _THEME}),
        ({"filter[preferences]": _LIST_JSON}, {"preferences": _LIST_JSON}),
        ({"filter[preferences]": "null"}, {"preferences": "null"}),
        ({"filter[preferences]": "true"}, {"preferences": "true"}),
        ({"filter[preferences]": "42"}, {"preferences": "42"}),
        ({"filter[settings]": "zzz"}, {}),
        ({"filter[settings]": "{}"}, {"settings": "{}"}),
        (
            {"filter[preferences]": "zzz", "filter[title]": "Ada"},
            {"title": "Ada"},
        ),
        (
            {"filter[preferences]": _THEME, "filter[title]": "Ada"},
            {"preferences": _THEME, "title": "Ada"},
        ),
        ({"preferences": "zzz"}, {}),
        ({"preferences": _THEME}, {"preferences": _THEME}),
        ({}, {}),
        (None, {}),
    ],
    ids=[
        "bracket-leftover-json",
        "bracket-leftover-ghost",
        "bracket-leftover-phrase",
        "bracket-leftover-bare-token",
        "bracket-leftover-js-object",
        "bracket-valid-object",
        "bracket-valid-array",
        "bracket-valid-null",
        "bracket-valid-true",
        "bracket-valid-number",
        "bracket-leftover-settings",
        "bracket-valid-empty-object",
        "bracket-leftover-plus-title",
        "bracket-valid-plus-title",
        "bare-leftover-json",
        "bare-valid-json",
        "empty-params",
        "none-params",
    ],
)
def test_leftover_honest_list_filter_json_values_do_not_invent(
    params: dict[str, str] | None,
    expected: dict[str, str],
) -> None:
    query = params if params is not None else SimpleNamespace()
    assert (
        leftover_honest_list_filters(
            query,
            allowed=_ALLOWED,
            filter_fields=["preferences", "settings", "title"],
            entity_spec=_SPEC,
        )
        == expected
    )


def test_entity_json_filter_fields_reads_spec() -> None:
    assert entity_json_filter_fields(_SPEC) == frozenset({"preferences", "settings"})
    assert entity_json_filter_fields(None) == frozenset()
    assert entity_json_filter_fields(SimpleNamespace()) == frozenset()
    assert entity_json_filter_fields(SimpleNamespace(fields=[SimpleNamespace(name="title")])) == (
        frozenset()
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("zzz", ""),
        ("ghost", ""),
        ("not-json", ""),
        ("foo", ""),
        ("{theme:dark}", ""),
        ("", ""),
        (None, ""),
        (_THEME, _THEME),
        (_LIST_JSON, _LIST_JSON),
        ("null", "null"),
        ("true", "true"),
        ("42", "42"),
        ("{}", "{}"),
        (True, ""),
        (False, ""),
    ],
    ids=[
        "junk",
        "ghost",
        "phrase",
        "bare-token",
        "js-object",
        "empty",
        "none",
        "object",
        "array",
        "null",
        "true",
        "number",
        "empty-object",
        "py-true",
        "py-false",
    ],
)
def test_leftover_honest_filter_json_does_not_invent(raw: object, expected: str) -> None:
    assert leftover_honest_filter_json(raw) == expected


def test_helper_source_pins_list_filter_json_leftover() -> None:
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "def leftover_honest_list_filters" in src
    assert "def entity_json_filter_fields" in src
    assert "filter[preferences]=zzz" in src
    assert "leftover_honest_filter_json" in src


def test_list_handler_source_pins_filter_json_leftover() -> None:
    src = _LIST.read_text(encoding="utf-8")
    assert "leftover_honest_list_filters(" in src
    assert "filter[preferences]=zzz" in src


def test_live_simple_task_user_preferences_json() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert "preferences: json" in src
