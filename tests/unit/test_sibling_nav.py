"""Tests for #942 cycle 3 — sibling-URL helper.

Project authors building detail-view pages need prev/next URLs to
navigate sequentially through entities in the user's current scope.
``sibling_urls`` queries the ``Repository`` for the closest row
above / below the current one in sort order, scoped by the same
filter shape ``Repository.list`` accepts.

Tests use a hand-rolled ``_FakeRepo`` so we don't need a live
PostgreSQL connection. The fake mirrors ``Repository.read`` and
``Repository.list`` behaviour just deeply enough to exercise:

- Ascending vs descending sort
- Multiple filter scopes
- First-in-list (no prev) and last-in-list (no next) edges
- Missing current row (returns ``(None, None)``)
- Missing sort-key value on current row (treats as no siblings)
- Custom URL-for callable
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest

from dazzle_back.runtime.sibling_nav import _parse_sort, sibling_urls

# ---------------------------------------------------------------------------
# Fake repository
# ---------------------------------------------------------------------------


@dataclass
class _Row:
    id: UUID
    created_at: int = 0
    cohort_id: str = "default"
    status: str = "open"


class _FakeRepo:
    """Minimal stand-in for ``Repository``. Stores rows in memory;
    implements the subset of ``read`` / ``list`` semantics
    ``sibling_urls`` actually uses (filters with ``__lt`` / ``__gt``,
    sort with optional ``-`` prefix, ``page_size=1`` paged list).

    Real repositories support a much richer surface (joins, search,
    aggregates, pagination); the helper only exercises the slice
    above so faking that slice is sufficient.
    """

    def __init__(self, rows: list[_Row]) -> None:
        self.rows = rows

    async def read(self, id: UUID) -> _Row | None:
        for r in self.rows:
            if r.id == id:
                return r
        return None

    async def list(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "id",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        items = list(self.rows)
        for k, v in (filters or {}).items():
            if "__" in k:
                field, op = k.split("__", 1)
                if op == "lt":
                    items = [r for r in items if getattr(r, field) < v]
                elif op == "gt":
                    items = [r for r in items if getattr(r, field) > v]
                elif op == "lte":
                    items = [r for r in items if getattr(r, field) <= v]
                elif op == "gte":
                    items = [r for r in items if getattr(r, field) >= v]
                else:
                    raise NotImplementedError(f"fake: op {op}")
            else:
                items = [r for r in items if getattr(r, k) == v]

        if sort.startswith("-"):
            items.sort(key=lambda r: getattr(r, sort[1:]), reverse=True)
        elif sort.startswith("+"):
            items.sort(key=lambda r: getattr(r, sort[1:]))
        else:
            items.sort(key=lambda r: getattr(r, sort))

        # Paginate.
        start = (page - 1) * page_size
        return {"items": items[start : start + page_size]}


def _ids(*labels: str) -> dict[str, UUID]:
    """Stable UUIDs for readable test assertions — same label → same UUID."""
    return {label: UUID(int=i + 1) for i, label in enumerate(labels)}


# ---------------------------------------------------------------------------
# Sort parsing
# ---------------------------------------------------------------------------


class TestParseSort:
    def test_bare_field_is_ascending(self) -> None:
        assert _parse_sort("id") == ("id", False)

    def test_minus_prefix_is_descending(self) -> None:
        assert _parse_sort("-created_at") == ("created_at", True)

    def test_plus_prefix_is_ascending(self) -> None:
        assert _parse_sort("+id") == ("id", False)

    def test_empty_defaults_to_id_ascending(self) -> None:
        assert _parse_sort("") == ("id", False)

    def test_whitespace_stripped(self) -> None:
        assert _parse_sort("- created_at ") == ("created_at", True)


# ---------------------------------------------------------------------------
# Helper behaviour
# ---------------------------------------------------------------------------


def _url(uid: Any) -> str:
    return f"/app/x/{uid}"


@pytest.mark.asyncio
class TestSiblingUrls:
    async def test_middle_row_returns_both_prev_and_next(self) -> None:
        ids = _ids("a", "b", "c")
        repo = _FakeRepo(
            [
                _Row(id=ids["a"], created_at=10),
                _Row(id=ids["b"], created_at=20),
                _Row(id=ids["c"], created_at=30),
            ]
        )
        prev_url, next_url = await sibling_urls(
            repo=repo,
            current_id=ids["b"],
            sort="created_at",  # ASC: a, b, c
            url_for=_url,
        )
        assert prev_url == f"/app/x/{ids['a']}"
        assert next_url == f"/app/x/{ids['c']}"

    async def test_descending_sort_swaps_neighbours(self) -> None:
        """With ``sort="-created_at"`` the visual order is c→b→a.
        Prev of b is c (more-recent above); next is a (older below)."""
        ids = _ids("a", "b", "c")
        repo = _FakeRepo(
            [
                _Row(id=ids["a"], created_at=10),
                _Row(id=ids["b"], created_at=20),
                _Row(id=ids["c"], created_at=30),
            ]
        )
        prev_url, next_url = await sibling_urls(
            repo=repo,
            current_id=ids["b"],
            sort="-created_at",
            url_for=_url,
        )
        assert prev_url == f"/app/x/{ids['c']}"
        assert next_url == f"/app/x/{ids['a']}"

    async def test_first_row_has_no_prev(self) -> None:
        ids = _ids("a", "b", "c")
        repo = _FakeRepo(
            [
                _Row(id=ids["a"], created_at=10),
                _Row(id=ids["b"], created_at=20),
                _Row(id=ids["c"], created_at=30),
            ]
        )
        prev_url, next_url = await sibling_urls(
            repo=repo,
            current_id=ids["a"],
            sort="created_at",
            url_for=_url,
        )
        assert prev_url is None
        assert next_url == f"/app/x/{ids['b']}"

    async def test_last_row_has_no_next(self) -> None:
        ids = _ids("a", "b", "c")
        repo = _FakeRepo(
            [
                _Row(id=ids["a"], created_at=10),
                _Row(id=ids["b"], created_at=20),
                _Row(id=ids["c"], created_at=30),
            ]
        )
        prev_url, next_url = await sibling_urls(
            repo=repo,
            current_id=ids["c"],
            sort="created_at",
            url_for=_url,
        )
        assert prev_url == f"/app/x/{ids['b']}"
        assert next_url is None

    async def test_missing_current_returns_both_none(self) -> None:
        repo = _FakeRepo([])
        prev_url, next_url = await sibling_urls(
            repo=repo,
            current_id=uuid4(),
            url_for=_url,
        )
        assert prev_url is None
        assert next_url is None

    async def test_missing_sort_value_returns_both_none(self) -> None:
        """If the current row has ``None`` for the sort key, we
        can't position it in the order — return no siblings rather
        than guess."""

        class NoneSortRow:
            def __init__(self, id: UUID) -> None:
                self.id = id
                self.created_at: int | None = None

        custom_repo = _FakeRepo([])  # placeholder; we monkey-patch read
        the_id = uuid4()

        async def fake_read(_id: UUID) -> Any:
            return NoneSortRow(the_id)

        async def fake_list(**_: Any) -> dict[str, Any]:
            return {"items": []}

        custom_repo.read = fake_read  # type: ignore[method-assign]
        custom_repo.list = fake_list  # type: ignore[method-assign]

        prev_url, next_url = await sibling_urls(
            repo=custom_repo,
            current_id=the_id,
            sort="created_at",
            url_for=_url,
        )
        assert prev_url is None
        assert next_url is None

    async def test_filters_scope_the_sibling_search(self) -> None:
        """Filters limit which rows count as siblings — a manuscript
        in cohort A's prev should only consider cohort A rows, not
        rows from cohort B that happen to have an earlier
        ``created_at``."""
        ids = _ids("a", "b", "c", "d")
        repo = _FakeRepo(
            [
                _Row(id=ids["a"], created_at=10, cohort_id="A"),
                _Row(id=ids["b"], created_at=15, cohort_id="B"),  # different cohort
                _Row(id=ids["c"], created_at=20, cohort_id="A"),  # current
                _Row(id=ids["d"], created_at=25, cohort_id="B"),  # different cohort
            ]
        )
        prev_url, next_url = await sibling_urls(
            repo=repo,
            current_id=ids["c"],
            sort="created_at",
            filters={"cohort_id": "A"},
            url_for=_url,
        )
        # Without the filter prev would be `b` (cohort B); with it,
        # prev is `a` (the only earlier cohort-A row) and next is
        # None (no later cohort-A row).
        assert prev_url == f"/app/x/{ids['a']}"
        assert next_url is None

    async def test_url_for_receives_sibling_id(self) -> None:
        """``url_for`` is invoked with the sibling's id — the
        callback can shape the URL however the project mounts the
        detail surface."""
        ids = _ids("a", "b")
        repo = _FakeRepo(
            [
                _Row(id=ids["a"], created_at=10),
                _Row(id=ids["b"], created_at=20),
            ]
        )

        captured: list[Any] = []

        def capture_url(uid: Any) -> str:
            captured.append(uid)
            return f"/custom/{uid}"

        prev_url, _ = await sibling_urls(
            repo=repo,
            current_id=ids["b"],
            sort="created_at",
            url_for=capture_url,
        )
        assert captured == [ids["a"]]
        assert prev_url == f"/custom/{ids['a']}"

    async def test_default_sort_is_id(self) -> None:
        """No ``sort`` passed ⇒ ``id`` ascending."""
        ids = _ids("low", "mid", "high")
        # Insert in non-id order to confirm sort is by id, not
        # insertion order.
        repo = _FakeRepo(
            [
                _Row(id=ids["high"]),
                _Row(id=ids["mid"]),
                _Row(id=ids["low"]),
            ]
        )
        prev_url, next_url = await sibling_urls(
            repo=repo,
            current_id=ids["mid"],
            url_for=_url,
        )
        assert prev_url == f"/app/x/{ids['low']}"
        assert next_url == f"/app/x/{ids['high']}"

    async def test_dict_row_supported(self) -> None:
        """Some repository configurations (computed fields, eager
        relations) return dicts rather than Pydantic models. The
        helper must read the sort field off either shape."""
        ids = _ids("a", "b", "c")

        async def dict_read(id: UUID) -> dict[str, Any] | None:
            for i, label in enumerate(("a", "b", "c")):
                if ids[label] == id:
                    return {"id": id, "created_at": (i + 1) * 10}
            return None

        async def dict_list(**kwargs: Any) -> dict[str, Any]:
            filters = kwargs.get("filters") or {}
            sort = kwargs.get("sort", "id")
            all_rows = [
                {"id": ids["a"], "created_at": 10},
                {"id": ids["b"], "created_at": 20},
                {"id": ids["c"], "created_at": 30},
            ]
            for k, v in filters.items():
                if "__" in k:
                    field, op = k.split("__", 1)
                    if op == "lt":
                        all_rows = [r for r in all_rows if r[field] < v]
                    elif op == "gt":
                        all_rows = [r for r in all_rows if r[field] > v]
            if sort.startswith("-"):
                all_rows.sort(key=lambda r: r[sort[1:]], reverse=True)
            else:
                all_rows.sort(key=lambda r: r[sort])
            return {"items": all_rows[:1]}

        repo = _FakeRepo([])
        repo.read = dict_read  # type: ignore[method-assign]
        repo.list = dict_list  # type: ignore[method-assign]

        prev_url, next_url = await sibling_urls(
            repo=repo,
            current_id=ids["b"],
            sort="created_at",
            url_for=_url,
        )
        assert prev_url == f"/app/x/{ids['a']}"
        assert next_url == f"/app/x/{ids['c']}"
