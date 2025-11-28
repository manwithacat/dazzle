"""
Full-text search manager for DNR.

Provides SQLite FTS5 integration for text search capabilities.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle_dnr_back.specs.entity import EntitySpec, ScalarType


@dataclass
class FTSConfig:
    """Configuration for FTS on an entity."""

    entity_name: str
    searchable_fields: list[str]
    fts_table_name: str = ""
    tokenizer: str = "porter"  # porter, unicode61, ascii

    def __post_init__(self):
        if not self.fts_table_name:
            self.fts_table_name = f"{self.entity_name}_fts"


@dataclass
class FTSManager:
    """
    Manages full-text search tables and queries.

    Uses SQLite FTS5 for efficient text searching.
    """

    _configs: dict[str, FTSConfig] = field(default_factory=dict)
    _initialized: set[str] = field(default_factory=set)

    def register_entity(
        self,
        entity: "EntitySpec",
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
        from dazzle_dnr_back.specs.entity import ScalarType

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
        conn: sqlite3.Connection,
        entity_name: str,
    ) -> None:
        """
        Create FTS5 virtual table for an entity.

        Uses standalone FTS table (not content= external) for simplicity
        and compatibility with manual rebuilds.

        Args:
            conn: SQLite connection
            entity_name: Entity name
        """
        config = self._configs.get(entity_name)
        if not config:
            return

        if entity_name in self._initialized:
            return

        # Create standalone FTS5 virtual table (stores its own content)
        fields_str = ", ".join(config.searchable_fields)
        sql = f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {config.fts_table_name}
            USING fts5(
                id,
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
        conn: sqlite3.Connection,
        config: FTSConfig,
    ) -> None:
        """Create triggers to sync FTS table with main table."""
        entity = config.entity_name
        fts_table = config.fts_table_name
        fields = config.searchable_fields

        # Field list for insert
        field_list = ", ".join(fields)
        new_field_list = ", ".join(f"NEW.{f}" for f in fields)

        # Insert trigger - for standalone FTS, just insert
        insert_sql = f"""
            CREATE TRIGGER IF NOT EXISTS {entity}_fts_insert
            AFTER INSERT ON {entity}
            BEGIN
                INSERT INTO {fts_table}(id, {field_list})
                VALUES (NEW.id, {new_field_list});
            END
        """
        conn.execute(insert_sql)

        # Update trigger - delete old, insert new
        update_sql = f"""
            CREATE TRIGGER IF NOT EXISTS {entity}_fts_update
            AFTER UPDATE ON {entity}
            BEGIN
                DELETE FROM {fts_table} WHERE id = OLD.id;
                INSERT INTO {fts_table}(id, {field_list})
                VALUES (NEW.id, {new_field_list});
            END
        """
        conn.execute(update_sql)

        # Delete trigger
        delete_sql = f"""
            CREATE TRIGGER IF NOT EXISTS {entity}_fts_delete
            AFTER DELETE ON {entity}
            BEGIN
                DELETE FROM {fts_table} WHERE id = OLD.id;
            END
        """
        conn.execute(delete_sql)

    def rebuild_index(
        self,
        conn: sqlite3.Connection,
        entity_name: str,
    ) -> int:
        """
        Rebuild FTS index from main table.

        Args:
            conn: SQLite connection
            entity_name: Entity name

        Returns:
            Number of rows indexed
        """
        config = self._configs.get(entity_name)
        if not config:
            return 0

        # Clear existing FTS data
        conn.execute(f"DELETE FROM {config.fts_table_name}")

        # Rebuild from main table
        fields = config.searchable_fields
        field_list = ", ".join(fields)

        sql = f"""
            INSERT INTO {config.fts_table_name}(id, {field_list})
            SELECT id, {field_list}
            FROM {entity_name}
        """
        conn.execute(sql)
        conn.commit()

        # Get count
        cursor = conn.execute(f"SELECT COUNT(*) FROM {config.fts_table_name}")
        return cursor.fetchone()[0]

    def search(
        self,
        conn: sqlite3.Connection,
        entity_name: str,
        query: str,
        fields: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[str], int]:
        """
        Search for entities matching a query.

        Args:
            conn: SQLite connection
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

        # Escape query for FTS
        escaped_query = self._escape_query(query)

        # Build field filter if specified
        if fields:
            # Filter to only search specified fields
            valid_fields = [f for f in fields if f in config.searchable_fields]
            if valid_fields:
                field_prefix = " OR ".join(f"{f}:{escaped_query}" for f in valid_fields)
                escaped_query = field_prefix
            else:
                escaped_query = escaped_query

        # Count total matches
        count_sql = f"""
            SELECT COUNT(*) FROM {config.fts_table_name}
            WHERE {config.fts_table_name} MATCH ?
        """
        cursor = conn.execute(count_sql, (escaped_query,))
        total = cursor.fetchone()[0]

        # Get matching IDs
        search_sql = f"""
            SELECT id FROM {config.fts_table_name}
            WHERE {config.fts_table_name} MATCH ?
            ORDER BY rank
            LIMIT ? OFFSET ?
        """
        cursor = conn.execute(search_sql, (escaped_query, limit, offset))
        ids = [row[0] for row in cursor.fetchall()]

        return ids, total

    def search_with_snippets(
        self,
        conn: sqlite3.Connection,
        entity_name: str,
        query: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Search with highlighted snippets.

        Args:
            conn: SQLite connection
            entity_name: Entity name
            query: Search query
            limit: Maximum results

        Returns:
            List of dicts with id, rank, and snippets
        """
        config = self._configs.get(entity_name)
        if not config:
            return []

        escaped_query = self._escape_query(query)

        # Build snippet columns - column indexes: 0=id, 1=first field, 2=second field, etc.
        snippet_cols = []
        for i, field in enumerate(config.searchable_fields):
            snippet_cols.append(
                f"snippet({config.fts_table_name}, {i + 1}, '<mark>', '</mark>', '...', 32) AS {field}_snippet"
            )
        snippet_str = ", ".join(snippet_cols)

        sql = f"""
            SELECT id, rank, {snippet_str}
            FROM {config.fts_table_name}
            WHERE {config.fts_table_name} MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        cursor = conn.execute(sql, (escaped_query, limit))
        cursor.row_factory = sqlite3.Row

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
    entities: list["EntitySpec"],
    searchable_entities: dict[str, list[str]] | None = None,
) -> FTSManager:
    """
    Create and configure an FTS manager.

    Args:
        entities: List of entity specs
        searchable_entities: Optional mapping of entity names to searchable fields
                           If None, auto-detects text fields

    Returns:
        Configured FTSManager
    """
    manager = FTSManager()

    for entity in entities:
        fields = searchable_entities.get(entity.name) if searchable_entities else None
        manager.register_entity(entity, searchable_fields=fields)

    return manager


def init_fts_tables(
    conn: sqlite3.Connection,
    manager: FTSManager,
    entities: list["EntitySpec"],
) -> None:
    """
    Initialize FTS tables for all registered entities.

    Args:
        conn: SQLite connection
        manager: FTS manager
        entities: List of entity specs
    """
    for entity in entities:
        if manager.is_enabled(entity.name):
            manager.create_fts_table(conn, entity.name)
