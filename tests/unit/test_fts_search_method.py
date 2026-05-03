"""Tests for #954 cycle 3 — `Repository.fts_search()` SQL shape.

Cycle 2 created the `search_vector` GENERATED column + GIN index.
This cycle adds the query path: a focused method that builds raw
SQL using `websearch_to_tsquery` + `ts_rank`, applies a scope
predicate when supplied, and returns ranked rows.

These tests verify the SQL shape via a stub connection that
captures (sql, params). Real PostgreSQL execution lives in the
PostgreSQL Tests CI job — covered there indirectly via the
search endpoint smoke test.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from dazzle.core.ir.search import SearchField, SearchSpec
from dazzle_back.runtime.repository import Repository

# ---------------------------------------------------------------------------
# Stub connection — captures SQL + returns canned rows
# ---------------------------------------------------------------------------


class _StubCursor:
    def __init__(self, count: int, rows: list[dict[str, Any]]) -> None:
        self._count = count
        self._rows = rows
        self.queries: list[tuple[str, list[Any]]] = []
        self._last_was_count = False

    def execute(self, sql: str, params: list[Any] | tuple[Any, ...]) -> None:
        self.queries.append((sql, list(params)))
        self._last_was_count = "COUNT(*)" in sql

    def fetchone(self) -> Any:
        if self._last_was_count:
            return (self._count,)
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _StubDb:
    placeholder = "%s"

    def __init__(self, count: int = 0, rows: list[dict[str, Any]] | None = None) -> None:
        self.cursor_obj = _StubCursor(count, rows or [])

    @contextmanager
    def connection(self):
        # Mimics psycopg context manager.
        yield SimpleNamespace(cursor=lambda: self.cursor_obj)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _build_repo(
    table_name: str = "Manuscript", count: int = 3, rows: list[dict[str, Any]] | None = None
) -> Repository:
    """Minimal repo wired to the stub DB. The Generic param doesn't matter
    for these tests — fts_search doesn't go through model_class."""
    if rows is None:
        rows = [{"id": "uid-1", "rank": 0.9, "title": "Hello world"}]
    entity = SimpleNamespace(name=table_name, fields=[], computed_fields=[])

    class _M:
        pass

    return Repository(
        db_manager=_StubDb(count=count, rows=rows), entity_spec=entity, model_class=_M
    )


def _spec(tokenizer: str = "english") -> SearchSpec:
    return SearchSpec(
        entity="Manuscript",
        fields=[SearchField(path="title", weight=4)],
        tokenizer=tokenizer,
    )


# ---------------------------------------------------------------------------
# Empty / short-circuit input
# ---------------------------------------------------------------------------


class TestEmptyQuery:
    def test_empty_string_short_circuits(self):
        repo = _build_repo()
        result = asyncio.run(repo.fts_search(_spec(), ""))
        assert result == {"items": [], "total": 0, "page": 1, "page_size": 20}
        # No SQL hit the DB
        assert repo.db.cursor_obj.queries == []

    def test_whitespace_only_short_circuits(self):
        repo = _build_repo()
        result = asyncio.run(repo.fts_search(_spec(), "   "))
        assert result["total"] == 0
        assert repo.db.cursor_obj.queries == []


# ---------------------------------------------------------------------------
# SQL shape
# ---------------------------------------------------------------------------


class TestSqlShape:
    def test_count_then_items_query_pair(self):
        repo = _build_repo(count=3)
        asyncio.run(repo.fts_search(_spec(), "hello"))
        queries = repo.db.cursor_obj.queries
        assert len(queries) == 2
        assert "COUNT(*)" in queries[0][0]
        assert "ORDER BY rank DESC" in queries[1][0]

    def test_uses_websearch_to_tsquery(self):
        # User-friendly query syntax matters — confirms we're not
        # using plainto_tsquery (which doesn't accept "phrases").
        repo = _build_repo()
        asyncio.run(repo.fts_search(_spec(), "hello"))
        items_sql = repo.db.cursor_obj.queries[1][0]
        assert "websearch_to_tsquery" in items_sql

    def test_uses_search_vector_column(self):
        # Must hit the cycle-2 stored column, not rebuild a tsvector each query.
        repo = _build_repo()
        asyncio.run(repo.fts_search(_spec(), "hello"))
        items_sql = repo.db.cursor_obj.queries[1][0]
        assert "search_vector @@" in items_sql

    def test_orders_by_rank_descending(self):
        repo = _build_repo()
        asyncio.run(repo.fts_search(_spec(), "hello"))
        items_sql = repo.db.cursor_obj.queries[1][0]
        assert "ORDER BY rank DESC" in items_sql

    def test_quoted_table_name(self):
        repo = _build_repo(table_name="Manuscript")
        asyncio.run(repo.fts_search(_spec(), "hello"))
        items_sql = repo.db.cursor_obj.queries[1][0]
        assert '"Manuscript"' in items_sql

    def test_query_string_is_parameterised(self):
        # The user-supplied `q` must NEVER appear inline in the SQL —
        # only via the placeholder. This is the SQL-injection guard.
        repo = _build_repo()
        asyncio.run(repo.fts_search(_spec(), "'; DROP TABLE Manuscript; --"))
        for sql, params in repo.db.cursor_obj.queries:
            assert "DROP TABLE" not in sql
            assert "'; DROP TABLE Manuscript; --" in params


# ---------------------------------------------------------------------------
# Tokenizer handling
# ---------------------------------------------------------------------------


class TestTokenizerInterpolation:
    def test_default_tokenizer_english(self):
        repo = _build_repo()
        asyncio.run(repo.fts_search(_spec("english"), "hello"))
        items_sql = repo.db.cursor_obj.queries[1][0]
        assert "websearch_to_tsquery('english'," in items_sql

    def test_explicit_french_tokenizer(self):
        repo = _build_repo()
        asyncio.run(repo.fts_search(_spec("french"), "bonjour"))
        items_sql = repo.db.cursor_obj.queries[1][0]
        assert "websearch_to_tsquery('french'," in items_sql

    def test_non_alpha_tokenizer_falls_back_safely(self):
        # Defence-in-depth: if a hostile spec slipped a non-alpha
        # tokenizer past cycle 2's validator, the SQL path must
        # still be safe (no injection).
        repo = _build_repo()
        # Bypass Pydantic field validation by using SimpleNamespace.
        spec = SimpleNamespace(
            entity="Manuscript",
            tokenizer="english'; DROP TABLE x;--",
            fields=[],
        )
        asyncio.run(repo.fts_search(spec, "hello"))
        items_sql = repo.db.cursor_obj.queries[1][0]
        # Falls back to english, and definitely no injection.
        assert "DROP TABLE" not in items_sql
        assert "websearch_to_tsquery('english'," in items_sql


# ---------------------------------------------------------------------------
# Scope predicate plumbing
# ---------------------------------------------------------------------------


class TestScopePredicate:
    def test_no_scope_predicate_omits_extra_where(self):
        repo = _build_repo()
        asyncio.run(repo.fts_search(_spec(), "hello"))
        items_sql = repo.db.cursor_obj.queries[1][0]
        # Single WHERE term — no AND clause introduced.
        # (Allows `AND` to appear inside ORDER BY etc.)
        where_clause = items_sql.split("WHERE", 1)[1].split("ORDER BY", 1)[0]
        assert "AND" not in where_clause

    def test_scope_predicate_anded_into_where(self):
        repo = _build_repo()
        scope = ('"school_id" = %s', ["sch-42"])
        asyncio.run(repo.fts_search(_spec(), "hello", scope_predicate=scope))
        items_sql = repo.db.cursor_obj.queries[1][0]
        items_params = repo.db.cursor_obj.queries[1][1]
        assert '"school_id" = %s' in items_sql
        # Param order: q (FTS), q (count's residual), scope param, q again, page_size, offset
        # Just check the scope param made it through.
        assert "sch-42" in items_params

    def test_scope_predicate_applied_to_count_too(self):
        # Pagination metadata must reflect the scoped row count, not
        # the global match count.
        repo = _build_repo(count=2)
        scope = ('"school_id" = %s', ["sch-42"])
        asyncio.run(repo.fts_search(_spec(), "hello", scope_predicate=scope))
        count_sql = repo.db.cursor_obj.queries[0][0]
        assert '"school_id" = %s' in count_sql

    def test_empty_scope_sql_treated_as_none(self):
        # The predicate compiler returns ('', []) for tautologies
        # (no filter needed). Must not blow up the WHERE clause.
        repo = _build_repo()
        asyncio.run(repo.fts_search(_spec(), "hello", scope_predicate=("", [])))
        items_sql = repo.db.cursor_obj.queries[1][0]
        # No spurious AND () in the WHERE clause
        assert "AND ()" not in items_sql


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    def test_default_page_one_size_twenty(self):
        repo = _build_repo(count=100)
        result = asyncio.run(repo.fts_search(_spec(), "hello"))
        assert result["page"] == 1
        assert result["page_size"] == 20
        # Limit + offset land in the items query as the last two params.
        items_params = repo.db.cursor_obj.queries[1][1]
        assert items_params[-2:] == [20, 0]

    def test_explicit_page_offset_calculation(self):
        repo = _build_repo(count=100)
        asyncio.run(repo.fts_search(_spec(), "hello", page=3, page_size=15))
        items_params = repo.db.cursor_obj.queries[1][1]
        # page 3, page_size 15 → offset = 30
        assert items_params[-2:] == [15, 30]

    def test_zero_total_skips_items_query(self):
        # If count returns 0, no need to issue a second query.
        repo = _build_repo(count=0, rows=[])
        result = asyncio.run(repo.fts_search(_spec(), "hello"))
        assert result["total"] == 0
        assert result["items"] == []
        assert len(repo.db.cursor_obj.queries) == 1  # count only


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


class TestResultShape:
    def test_returns_id_rank_and_row_fields(self):
        rows = [
            {"id": "uid-1", "rank": 0.95, "title": "Hello world"},
            {"id": "uid-2", "rank": 0.42, "title": "World peace"},
        ]
        repo = _build_repo(count=2, rows=rows)
        result = asyncio.run(repo.fts_search(_spec(), "hello"))
        assert len(result["items"]) == 2
        assert result["items"][0]["id"] == "uid-1"
        assert result["items"][0]["rank"] == 0.95
        assert result["items"][0]["title"] == "Hello world"
