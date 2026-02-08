"""
PostgreSQL full-text search backend.

Uses tsvector, tsquery, and GIN indexes for text search.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dazzle_back.runtime.query_builder import quote_identifier


@dataclass
class PostgresFTSBackend:
    """PostgreSQL full-text search using tsvector/tsquery/GIN."""

    _language: str = "english"

    def _build_tsvector_expr(self, fields: list[str]) -> str:
        """Build a tsvector expression combining multiple columns."""
        parts = []
        for field in fields:
            col = quote_identifier(field)
            parts.append(f"to_tsvector('{self._language}', COALESCE({col}, ''))")
        return " || ' ' || ".join(parts)

    def create_fts_index(
        self,
        conn: Any,
        entity_name: str,
        searchable_fields: list[str],
    ) -> None:
        """Create GIN index for full-text search on an entity table."""
        table = quote_identifier(entity_name)
        tsvector_expr = self._build_tsvector_expr(searchable_fields)
        index_name = f"idx_{entity_name}_fts"

        cursor = conn.cursor()
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS {quote_identifier(index_name)} "
            f"ON {table} USING GIN(({tsvector_expr}))"
        )
        conn.commit()

    def search(
        self,
        conn: Any,
        entity_name: str,
        query: str,
        searchable_fields: list[str],
        fields: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[str], int]:
        """
        Search for entities matching query.

        Returns:
            Tuple of (list of matching IDs, total count).
        """
        table = quote_identifier(entity_name)

        # Determine which fields to search
        search_fields = fields if fields else searchable_fields
        valid_fields = [f for f in search_fields if f in searchable_fields]
        if not valid_fields:
            valid_fields = searchable_fields

        tsvector_expr = self._build_tsvector_expr(valid_fields)
        tsquery = f"plainto_tsquery('{self._language}', %s)"

        cursor = conn.cursor()

        # Count total matches
        cursor.execute(
            f"SELECT COUNT(*) FROM {table} WHERE ({tsvector_expr}) @@ {tsquery}",
            (query,),
        )
        row = cursor.fetchone()
        total = row[0] if isinstance(row, (tuple, list)) else row.get("count", 0)

        # Fetch IDs ranked by relevance
        cursor.execute(
            f'SELECT "id", ts_rank(({tsvector_expr}), {tsquery}) AS rank '
            f"FROM {table} "
            f"WHERE ({tsvector_expr}) @@ {tsquery} "
            f"ORDER BY rank DESC "
            f"LIMIT %s OFFSET %s",
            (query, query, limit, offset),
        )
        rows = cursor.fetchall()
        ids = []
        for r in rows:
            if isinstance(r, dict):
                ids.append(r["id"])
            else:
                ids.append(r[0])

        return ids, total

    def search_with_snippets(
        self,
        conn: Any,
        entity_name: str,
        query: str,
        searchable_fields: list[str],
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Search with highlighted snippets using ts_headline."""
        table = quote_identifier(entity_name)
        tsvector_expr = self._build_tsvector_expr(searchable_fields)
        tsquery = f"plainto_tsquery('{self._language}', %s)"

        # Build snippet columns using ts_headline
        snippet_cols = []
        for field in searchable_fields:
            col = quote_identifier(field)
            snippet_alias = quote_identifier(f"{field}_snippet")
            snippet_cols.append(
                f"ts_headline('{self._language}', COALESCE({col}, ''), "
                f"{tsquery}, "
                f"'StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=15') "
                f"AS {snippet_alias}"
            )
        snippet_str = ", ".join(snippet_cols)

        # Parameter count: ts_rank has 1 tsquery (%s), each ts_headline
        # has 1 tsquery (%s), WHERE has 1 tsquery (%s), LIMIT has 1 (%s).
        # Total = 1 (ts_rank) + n_fields (ts_headline) + 1 (WHERE) + 1 (LIMIT)
        n_fields = len(searchable_fields)
        params: tuple[Any, ...] = (
            query,  # ts_rank tsquery
            *((query,) * n_fields),  # one for each ts_headline
            query,  # WHERE clause tsquery
            limit,
        )

        cursor = conn.cursor()
        cursor.execute(
            f'SELECT "id", ts_rank(({tsvector_expr}), {tsquery}) AS rank, '
            f"{snippet_str} "
            f"FROM {table} "
            f"WHERE ({tsvector_expr}) @@ {tsquery} "
            f"ORDER BY rank DESC "
            f"LIMIT %s",
            params,
        )

        results = []
        for row in cursor.fetchall():
            if isinstance(row, dict):
                results.append(dict(row))
            else:
                result: dict[str, Any] = {"id": row[0], "rank": row[1]}
                for i, field in enumerate(searchable_fields):
                    result[f"{field}_snippet"] = row[2 + i]
                results.append(result)

        return results

    def rebuild_index(
        self,
        conn: Any,
        entity_name: str,
        searchable_fields: list[str],
    ) -> int:
        """
        Rebuild is a no-op for PostgreSQL — GIN indexes auto-maintain.

        Returns the current row count.
        """
        table = quote_identifier(entity_name)
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        row = cursor.fetchone()
        return row[0] if isinstance(row, (tuple, list)) else row.get("count", 0)
