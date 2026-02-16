"""
Protocol defining the store interface that KG mixins depend on.

Mixins (KnowledgeGraphQuery, KnowledgeGraphMetadata, KnowledgeGraphActivity)
call _get_connection() and _close_connection() on ``self``. This protocol
captures that contract so mypy can verify it without ``# type: ignore``.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Protocol

from .models import Entity, PathResult, Relation


class KGStoreProtocol(Protocol):
    """Methods that KG mixins expect the concrete store to provide."""

    def _get_connection(self) -> sqlite3.Connection: ...

    def _close_connection(self, conn: sqlite3.Connection) -> None: ...

    def get_entity(self, entity_id: str) -> Entity | None: ...

    def get_relations(
        self,
        entity_id: str | None = None,
        relation_type: str | None = None,
        direction: str = "both",
    ) -> list[Relation]: ...

    def list_entities(
        self,
        entity_type: str | None = None,
        name_pattern: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Entity]: ...

    def find_paths(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
        relation_types: list[str] | None = None,
    ) -> list[PathResult]: ...

    def get_neighbourhood(
        self,
        entity_id: str,
        depth: int = 1,
        relation_types: list[str] | None = None,
        direction: str = "both",
    ) -> dict[str, Any]: ...

    def resolve_alias(self, alias: str) -> str | None: ...
