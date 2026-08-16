"""List leftover sort / filter / q must not invent a fetch (cycle 2164).

Leftover URL junk (``sort=2abc``, ``sort=zzz``, ``dir=zzz``,
``filter[2abc]``, ``filter[zzz]``) used to raise in the list fetch;
``_handle_table``'s bare ``except Exception`` invented an empty table
(loading/empty theater). Leftover ``q`` (dz-grid search / REST alias)
used to be dropped, inventing the unfiltered collection. Empty /
invalid / unknown restores the server default; known fields still
sort/filter; ``q`` is search. Not leftover page (2162 isdigit window)
and not leftover-scalar refuse.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.page_routes import (
    _list_known_fields,
    _parse_list_dir,
    _parse_list_filters,
    _parse_list_search,
    _parse_list_sort,
)

_PAGE_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
)

_ALLOWED = frozenset({"id", "title", "status", "created_at"})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2abc", "created_at"),
        ("zzz", "created_at"),
        ("1e2", "created_at"),
        ("", "created_at"),
        (None, "created_at"),
        ("  ", "created_at"),
        ("-zzz", "created_at"),
        ("title", "title"),
        ("-title", "title"),
        ("created_at", "created_at"),
        ("status", "status"),
        ("id", "id"),
    ],
    ids=[
        "sort-leftover-suffix",
        "sort-leftover-named",
        "sort-leftover-scientific",
        "sort-empty",
        "sort-none",
        "sort-whitespace",
        "sort-leftover-minus",
        "sort-valid-title",
        "sort-valid-minus-stripped",
        "sort-valid-default",
        "sort-valid-status",
        "sort-valid-id",
    ],
)
def test_parse_list_sort_leftover_does_not_invent(raw: object, expected: str) -> None:
    assert _parse_list_sort(raw, default="created_at", allowed=_ALLOWED) == expected


@pytest.mark.parametrize(
    ("raw", "default", "expected"),
    [
        ("zzz", "asc", "asc"),
        ("2abc", "desc", "desc"),
        ("1e2", "asc", "asc"),
        ("", "desc", "desc"),
        (None, "asc", "asc"),
        ("ASC", "desc", "asc"),
        ("desc", "asc", "desc"),
        ("ascending", "asc", "asc"),
    ],
    ids=[
        "dir-leftover-named",
        "dir-leftover-suffix",
        "dir-leftover-scientific",
        "dir-empty",
        "dir-none",
        "dir-valid-asc",
        "dir-valid-desc",
        "dir-leftover-word",
    ],
)
def test_parse_list_dir_leftover_does_not_invent(raw: object, default: str, expected: str) -> None:
    assert _parse_list_dir(raw, default=default) == expected


def test_parse_list_search_honors_q_alias() -> None:
    assert _parse_list_search(None, "substation") == "substation"
    assert _parse_list_search("title-q", "ignored") == "title-q"
    assert _parse_list_search("", "  leftover  ") == "leftover"
    assert _parse_list_search("", "   ") is None
    assert _parse_list_search(None, None) is None


def test_parse_list_filters_drops_leftover_keys() -> None:
    params = {
        "filter[2abc]": "1",
        "filter[zzz]": "Ada",
        "filter[status]": "open",
        "filter[status__gte]": "b",
        "filter[title]": "Invoice",
        "sort": "zzz",
    }
    assert _parse_list_filters(params, allowed=_ALLOWED) == {
        "status": "open",
        "status__gte": "b",
        "title": "Invoice",
    }


def test_list_known_fields_includes_columns_and_default() -> None:
    table = SimpleNamespace(
        columns=[SimpleNamespace(key="title"), SimpleNamespace(key="status")],
        default_sort_field="created_at",
        search_fields=["title", "body"],
    )
    assert _list_known_fields(table) == frozenset({"id", "title", "status", "created_at", "body"})


def test_handle_table_uses_leftover_honest_query() -> None:
    """``_handle_table`` must not pass raw leftover sort/q into the fetch."""
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "sort=_list_sort" in src
    assert "direction=_list_dir" in src
    assert "search=_list_search" in src
    assert "filters=_list_filters or None" in src
    assert '_parse_list_search(_qparams.get("search"), _qparams.get("q"))' in src
    assert 'sort=api_params.get("sort")' not in src
    assert 'search=api_params.get("search")' not in src
    assert "invent an empty collection" in src or "invented an empty table" in src
    assert "unfiltered collection" in src
