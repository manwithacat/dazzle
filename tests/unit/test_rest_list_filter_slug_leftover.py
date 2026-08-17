"""Leftover REST ?filter[slug]=ab must not invent empty (cycle 2201).

leftover-honest url VALUES already exist (oral #81). REST
``list_handlers`` still landed leftover SLUG VALUES on known
``slug`` keys in ``gated_list`` / ``repo.list`` and invented
empty. Valid slugs ride via ``validate_slug``; leftover
restores unfiltered (omit). ``zzz`` / ``ghost`` are valid
slugs (length ≥3 lowercase) and ride. Oral #82 — not another
GET list url VALUE (oral #81).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.page_routes import (
    entity_slug_filter_fields,
    leftover_honest_filter_slug,
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
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "domain_join_co" / "dsl" / "domain.dsl"

_ALLOWED = frozenset({"id", "title", "status", "slug", "handle"})
_SPEC = SimpleNamespace(
    fields=[
        SimpleNamespace(name="id"),
        SimpleNamespace(name="title"),
        SimpleNamespace(name="status"),
        SimpleNamespace(name="slug", type=SimpleNamespace(kind="slug")),
        SimpleNamespace(name="handle", type=SimpleNamespace(kind="slug")),
    ]
)


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"filter[slug]": "ab"}, {}),
        ({"filter[slug]": "ZZZ"}, {}),
        ({"filter[slug]": "foo--bar"}, {}),
        ({"filter[slug]": "not a slug"}, {}),
        ({"filter[slug]": "-foo"}, {}),
        ({"filter[slug]": "foo_bar"}, {}),
        ({"filter[slug]": "zzz"}, {"slug": "zzz"}),
        ({"filter[slug]": "ghost"}, {"slug": "ghost"}),
        ({"filter[slug]": "acme"}, {"slug": "acme"}),
        ({"filter[slug]": "domain-join"}, {"slug": "domain-join"}),
        ({"filter[handle]": "ab"}, {}),
        ({"filter[handle]": "workspace1"}, {"handle": "workspace1"}),
        (
            {"filter[slug]": "ab", "filter[title]": "Invoice"},
            {"title": "Invoice"},
        ),
        (
            {"filter[slug]": "acme", "filter[title]": "Invoice"},
            {"slug": "acme", "title": "Invoice"},
        ),
        ({"slug": "ab"}, {}),
        ({"slug": "acme"}, {"slug": "acme"}),
        ({}, {}),
        (None, {}),
    ],
    ids=[
        "bracket-leftover-short",
        "bracket-leftover-upper",
        "bracket-leftover-double-hyphen",
        "bracket-leftover-spaces",
        "bracket-leftover-leading-hyphen",
        "bracket-leftover-underscore",
        "bracket-valid-zzz",
        "bracket-valid-ghost",
        "bracket-valid-acme",
        "bracket-valid-hyphenated",
        "bracket-leftover-handle",
        "bracket-valid-handle",
        "bracket-leftover-plus-title",
        "bracket-valid-plus-title",
        "bare-leftover-slug",
        "bare-valid-slug",
        "empty-params",
        "none-params",
    ],
)
def test_leftover_honest_list_filter_slug_values_do_not_invent(
    params: dict[str, str] | None,
    expected: dict[str, str],
) -> None:
    query = params if params is not None else SimpleNamespace()
    assert (
        leftover_honest_list_filters(
            query,
            allowed=_ALLOWED,
            filter_fields=["slug", "handle", "title"],
            entity_spec=_SPEC,
        )
        == expected
    )


def test_entity_slug_filter_fields_reads_spec() -> None:
    assert entity_slug_filter_fields(_SPEC) == frozenset({"slug", "handle"})
    assert entity_slug_filter_fields(None) == frozenset()
    assert entity_slug_filter_fields(SimpleNamespace()) == frozenset()
    assert entity_slug_filter_fields(SimpleNamespace(fields=[SimpleNamespace(name="title")])) == (
        frozenset()
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ab", ""),
        ("ZZZ", ""),
        ("foo--bar", ""),
        ("not a slug", ""),
        ("-foo", ""),
        ("foo_bar", ""),
        ("", ""),
        (None, ""),
        ("zzz", "zzz"),
        ("ghost", "ghost"),
        ("acme", "acme"),
        ("domain-join", "domain-join"),
        (True, ""),
        (False, ""),
    ],
    ids=[
        "short",
        "upper",
        "double-hyphen",
        "spaces",
        "leading-hyphen",
        "underscore",
        "empty",
        "none",
        "zzz-rides",
        "ghost-rides",
        "acme",
        "hyphenated",
        "py-true",
        "py-false",
    ],
)
def test_leftover_honest_filter_slug_does_not_invent(raw: object, expected: str) -> None:
    assert leftover_honest_filter_slug(raw) == expected


def test_helper_source_pins_list_filter_slug_leftover() -> None:
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "def leftover_honest_list_filters" in src
    assert "def entity_slug_filter_fields" in src
    assert "filter[slug]=ab" in src
    assert "leftover_honest_filter_slug" in src
    assert "validate_slug" in src


def test_list_handler_source_pins_filter_slug_leftover() -> None:
    src = _LIST.read_text(encoding="utf-8")
    assert "leftover_honest_list_filters(" in src
    assert "filter[slug]=ab" in src


def test_live_domain_join_co_workspace_slug() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert 'entity Workspace "Workspace":' in src
    assert "slug: slug required" in src
