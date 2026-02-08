"""
Full-text search manager for DNR.

Routes between SQLite FTS5 and PostgreSQL tsvector/GIN backends.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dazzle_back.runtime.fts_postgres import PostgresFTSBackend
from dazzle_back.runtime.query_builder import quote_identifier

if TYPE_CHECKING:
    from dazzle_back.specs.entity import EntitySpec


@dataclass
class FTSConfig:
    """Configuration for FTS on an entity."""

    entity_name: str
    searchable_fields: list[str]
    fts_table_name: str = ""
    tokenizer: str = "porter"  # porter, unicode61, ascii

    def __post_init__(self) -> None:
        if not self.fts_table_name:
            self.fts_table_name = f"{self.entity_name}_fts"


@dataclass
class FTSManager:
    """
    Manages full-text search tables and queries.

    Routes between SQLite FTS5 and PostgreSQL tsvector/GIN backends
    based on the presence of a database_url.
    """

    database_url: str | None = None
    _configs: dict[str, FTSConfig] = field(default_factory=dict)
    _initialized: set[str] = field(default_factory=set)
    _pg_backend: PostgresFTSBackend | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.database_url and self.database_url.startswith("postgres"):
            self._pg_backend = PostgresFTSBackend()

    @property
    def _use_postgres(self) -> bool:
        return self._pg_backend is not None

    def register_entity(
        self,
        entity: EntitySpec,
        searchable_fields: list[str] | None = None,
        tokenizer: str = "porter",
    ) -> FTSConfig | None:
        """
        Register an entity for full-text search.

        Args:
            entity: Entity specification
            searchable_fields: Fields to index (auto-detected if None)
            tokenizer: FTS5 tokenizer (porter, unicode61, ascii)

        Returns:
            FTS configuration, or None if no searchable fields
        """
        from dazzle_back.specs.entity import ScalarType

        # Auto-detect searchable fields if not specified
        if searchable_fields is None:
            searchable_fields = []
            for f in entity.fields:
                if f.type.kind == "scalar" and f.type.scalar_type in (
                    ScalarType.STR,
                    ScalarType.TEXT,
                    ScalarType.RICHTEXT,
                ):
                    searchable_fields.append(f.name)

        if not searchable_fields:
            return None

        config = FTSConfig(
            entity_name=entity.name,
            searchable_fields=searchable_fields,
            tokenizer=tokenizer,
        )
        self._configs[entity.name] = config
        return config

    def get_config(self, entity_name: str) -> FTSConfig | None:
        """Get FTS config for an entity."""
        return self._configs.get(entity_name)

    def is_enabled(self, entity_name: str) -> bool:
        """Check if FTS is enabled for an entity."""
        return entity_name in self._configs

    def create_fts_table(
        self,
        conn: Any,
        entity_name: str,
    ) -> None:
        """
        Create FTS index/table for an entity.

        Uses PostgreSQL GIN indexes or SQLite FTS5 virtual tables
        depending on the configured backend.

        Args:
            conn: Database connection (sqlite3 or psycopg2)
            entity_name: Entity name
        """
        config = self._configs.get(entity_name)
        if not config:
            return

        if entity_name in self._initialized:
            return

        if self._use_postgres:
            assert self._pg_backend is not None
            self._pg_backend.create_fts_index(conn, entity_name, config.searchable_fields)
        else:
            # SQLite FTS5 virtual table
            fields_str = ", ".join(quote_identifier(f) for f in config.searchable_fields)
            fts_table = quote_identifier(config.fts_table_name)
            sql = f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {fts_table}
                USING fts5(
                    "id",
                    {fields_str},
                    tokenize='{config.tokenizer}'
                )
            """
            conn.execute(sql)

            # Create triggers to keep FTS in sync
            self._create_sync_triggers(conn, config)

            conn.commit()

        self._initialized.add(entity_name)

    def _create_sync_triggers(
        self,
        conn: Any,
        config: FTSConfig,
    ) -> None:
        """Create triggers to sync FTS table with main table."""
        entity = config.entity_name
        entity_quoted = quote_identifier(entity)
        fts_table = quote_identifier(config.fts_table_name)
        fields = config.searchable_fields

        # Field list for insert (quoted)
        field_list = ", ".join(quote_identifier(f) for f in fields)
        new_field_list = ", ".join(f"NEW.{quote_identifier(f)}" for f in fields)

        # Insert trigger - for standalone FTS, just insert
        insert_sql = f"""
            CREATE TRIGGER IF NOT EXISTS {entity}_fts_insert
            AFTER INSERT ON {entity_quoted}
            BEGIN
                INSERT INTO {fts_table}("id", {field_list})
                VALUES (NEW."id", {new_field_list});
            END
        """
        conn.execute(insert_sql)

        # Update trigger - delete old, insert new
        update_sql = f"""
            CREATE TRIGGER IF NOT EXISTS {entity}_fts_update
            AFTER UPDATE ON {entity_quoted}
            BEGIN
                DELETE FROM {fts_table} WHERE "id" = OLD."id";
                INSERT INTO {fts_table}("id", {field_list})
                VALUES (NEW."id", {new_field_list});
            END
        """
        conn.execute(update_sql)

        # Delete trigger
        delete_sql = f"""
            CREATE TRIGGER IF NOT EXISTS {entity}_fts_delete
            AFTER DELETE ON {entity_quoted}
            BEGIN
                DELETE FROM {fts_table} WHERE "id" = OLD."id";
            END
        """
        conn.execute(delete_sql)

    def rebuild_index(
        self,
        conn: Any,
        entity_name: str,
    ) -> int:
        """
        Rebuild FTS index from main table.

        Args:
            conn: Database connection (sqlite3 or psycopg2)
            entity_name: Entity name

        Returns:
            Number of rows indexed
        """
        config = self._configs.get(entity_name)
        if not config:
            return 0

        if self._use_postgres:
            assert self._pg_backend is not None
            return self._pg_backend.rebuild_index(conn, entity_name, config.searchable_fields)

        # SQLite FTS5 rebuild
        fts_table = quote_identifier(config.fts_table_name)
        entity_quoted = quote_identifier(entity_name)

        # Clear existing FTS data
        conn.execute(f"DELETE FROM {fts_table}")

        # Rebuild from main table
        fields = config.searchable_fields
        field_list = ", ".join(quote_identifier(f) for f in fields)

        sql = f"""
            INSERT INTO {fts_table}("id", {field_list})
            SELECT "id", {field_list}
            FROM {entity_quoted}
        """
        conn.execute(sql)
        conn.commit()

        # Get count
        cursor = conn.execute(f"SELECT COUNT(*) FROM {fts_table}")
        return int(cursor.fetchone()[0])

    def search(
        self,
        conn: Any,
        entity_name: str,
        query: str,
        fields: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[str], int]:
        """
        Search for entities matching a query.

        Args:
            conn: Database connection (sqlite3 or psycopg2)
            entity_name: Entity name
            query: Search query
            fields: Optional specific fields to search
            limit: Maximum results
            offset: Result offset

        Returns:
            Tuple of (list of matching IDs, total count)
        """
        config = self._configs.get(entity_name)
        if not config:
            return [], 0

        if self._use_postgres:
            assert self._pg_backend is not None
            return self._pg_backend.search(
                conn,
                entity_name,
                query,
                config.searchable_fields,
                fields=fields,
                limit=limit,
                offset=offset,
            )

        # SQLite FTS5 search
        escaped_query = self._escape_query(query)

        # Build field filter if specified
        if fields:
            valid_fields = [f for f in fields if f in config.searchable_fields]
            if valid_fields:
                field_prefix = " OR ".join(f"{f}:{escaped_query}" for f in valid_fields)
                escaped_query = field_prefix

        fts_table = quote_identifier(config.fts_table_name)
        fts_name = config.fts_table_name

        # Count total matches
        count_sql = f"""
            SELECT COUNT(*) FROM {fts_table}
            WHERE {fts_name} MATCH ?
        """
        cursor = conn.execute(count_sql, (escaped_query,))
        total = cursor.fetchone()[0]

        # Get matching IDs
        search_sql = f"""
            SELECT "id" FROM {fts_table}
            WHERE {fts_name} MATCH ?
            ORDER BY rank
            LIMIT ? OFFSET ?
        """
        cursor = conn.execute(search_sql, (escaped_query, limit, offset))
        ids = [row[0] for row in cursor.fetchall()]

        return ids, total

    def search_with_snippets(
        self,
        conn: Any,
        entity_name: str,
        query: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Search with highlighted snippets.

        Args:
            conn: Database connection (sqlite3 or psycopg2)
            entity_name: Entity name
            query: Search query
            limit: Maximum results

        Returns:
            List of dicts with id, rank, and snippets
        """
        config = self._configs.get(entity_name)
        if not config:
            return []

        if self._use_postgres:
            assert self._pg_backend is not None
            return self._pg_backend.search_with_snippets(
                conn,
                entity_name,
                query,
                config.searchable_fields,
                limit=limit,
            )

        # SQLite FTS5 snippets
        escaped_query = self._escape_query(query)

        fts_table = quote_identifier(config.fts_table_name)
        fts_name = config.fts_table_name

        # Build snippet columns - column indexes: 0=id, 1=first field, etc.
        snippet_cols = []
        for i, field_name in enumerate(config.searchable_fields):
            snippet_cols.append(
                f"snippet({fts_name}, {i + 1}, '<mark>', '</mark>', '...', 32) "
                f"AS {quote_identifier(field_name + '_snippet')}"
            )
        snippet_str = ", ".join(snippet_cols)

        sql = f"""
            SELECT "id", rank, {snippet_str}
            FROM {fts_table}
            WHERE {fts_name} MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        cursor = conn.execute(sql, (escaped_query, limit))
        cursor.row_factory = sqlite3.Row  # type: ignore[assignment]

        results = []
        for row in cursor.fetchall():
            result = dict(row)
            results.append(result)

        return results

    def _escape_query(self, query: str) -> str:
        """
        Escape a search query for FTS5.

        Handles special characters and wraps terms.
        """
        # Remove special FTS5 operators for safety
        special_chars = ['"', "'", "(", ")", "*", ":", "^", "-", "+"]
        escaped = query
        for char in special_chars:
            escaped = escaped.replace(char, " ")

        # Split into terms and wrap with quotes for exact matching
        terms = escaped.split()
        if len(terms) == 1:
            return f'"{terms[0]}"'
        else:
            # Use OR for multiple terms
            return " OR ".join(f'"{t}"' for t in terms if t)


# =============================================================================
# Convenience Functions
# =============================================================================


def create_fts_manager(
    entities: list[EntitySpec],
    searchable_entities: dict[str, list[str]] | None = None,
    database_url: str | None = None,
) -> FTSManager:
    """
    Create and configure an FTS manager.

    Args:
        entities: List of entity specs
        searchable_entities: Optional mapping of entity names to searchable fields
                           If None, auto-detects text fields
        database_url: Optional database URL; if postgres://, uses PG backend

    Returns:
        Configured FTSManager
    """
    manager = FTSManager(database_url=database_url)

    for entity in entities:
        fields = searchable_entities.get(entity.name) if searchable_entities else None
        manager.register_entity(entity, searchable_fields=fields)

    return manager


def init_fts_tables(
    conn: Any,
    manager: FTSManager,
    entities: list[EntitySpec],
) -> None:
    """
    Initialize FTS tables for all registered entities.

    Args:
        conn: Database connection (sqlite3 or psycopg2)
        manager: FTS manager
        entities: List of entity specs
    """
    for entity in entities:
        if manager.is_enabled(entity.name):
            manager.create_fts_table(conn, entity.name)
