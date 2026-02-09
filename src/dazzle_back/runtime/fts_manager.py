"""
Full-text search manager for DNR.

Uses PostgreSQL tsvector/GIN backend exclusively.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dazzle_back.runtime.fts_postgres import PostgresFTSBackend

if TYPE_CHECKING:
    from dazzle_back.specs.entity import EntitySpec


@dataclass
class FTSConfig:
    """Configuration for FTS on an entity."""

    entity_name: str
    searchable_fields: list[str]
    fts_table_name: str = ""
    tokenizer: str = "porter"  # Retained for API compatibility

    def __post_init__(self) -> None:
        if not self.fts_table_name:
            self.fts_table_name = f"{self.entity_name}_fts"


@dataclass
class FTSManager:
    """
    Manages full-text search indexes and queries.

    Delegates to PostgreSQL tsvector/GIN backend via PostgresFTSBackend.
    """

    database_url: str = ""
    _configs: dict[str, FTSConfig] = field(default_factory=dict)
    _initialized: set[str] = field(default_factory=set)
    _pg_backend: PostgresFTSBackend = field(default_factory=PostgresFTSBackend, init=False)

    def __post_init__(self) -> None:
        self._pg_backend = PostgresFTSBackend()

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
            tokenizer: Retained for API compatibility

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
        Create FTS GIN index for an entity.

        Args:
            conn: psycopg database connection
            entity_name: Entity name
        """
        config = self._configs.get(entity_name)
        if not config:
            return

        if entity_name in self._initialized:
            return

        self._pg_backend.create_fts_index(conn, entity_name, config.searchable_fields)
        self._initialized.add(entity_name)

    def rebuild_index(
        self,
        conn: Any,
        entity_name: str,
    ) -> int:
        """
        Rebuild FTS index from main table.

        Args:
            conn: psycopg database connection
            entity_name: Entity name

        Returns:
            Number of rows indexed
        """
        config = self._configs.get(entity_name)
        if not config:
            return 0

        return self._pg_backend.rebuild_index(conn, entity_name, config.searchable_fields)

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
            conn: psycopg database connection
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

        return self._pg_backend.search(
            conn,
            entity_name,
            query,
            config.searchable_fields,
            fields=fields,
            limit=limit,
            offset=offset,
        )

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
            conn: psycopg database connection
            entity_name: Entity name
            query: Search query
            limit: Maximum results

        Returns:
            List of dicts with id, rank, and snippets
        """
        config = self._configs.get(entity_name)
        if not config:
            return []

        return self._pg_backend.search_with_snippets(
            conn,
            entity_name,
            query,
            config.searchable_fields,
            limit=limit,
        )


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
        database_url: PostgreSQL connection URL

    Returns:
        Configured FTSManager
    """
    manager = FTSManager(database_url=database_url or "")

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
    Initialize FTS indexes for all registered entities.

    Args:
        conn: psycopg database connection
        manager: FTS manager
        entities: List of entity specs
    """
    for entity in entities:
        if manager.is_enabled(entity.name):
            manager.create_fts_table(conn, entity.name)
