"""
Knowledge Graph data models.

Contains all dataclasses used across the knowledge graph module:
entities, relations, path results, and activity events.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActivityEvent:
    """Parameters for logging an activity event, replacing 14 individual parameters."""

    session_id: str
    event_type: str
    tool: str
    operation: str | None = None
    success: bool | None = None
    duration_ms: float | None = None
    error: str | None = None
    warnings: int = 0
    progress_current: int | None = None
    progress_total: int | None = None
    message: str | None = None
    level: str = "info"
    context_json: str | None = None
    source: str = "mcp"


@dataclass
class Entity:
    """A node in the knowledge graph."""

    id: str  # Prefixed: file:, module:, concept:, decision:
    entity_type: str  # Inferred from prefix or explicit
    name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Entity:
        """Create entity from database row."""
        return cls(
            id=row["id"],
            entity_type=row["entity_type"],
            name=row["name"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@dataclass
class Relation:
    """An edge in the knowledge graph."""

    source_id: str
    target_id: str
    relation_type: str  # imports, defines, depends_on, calls, implements, etc.
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Relation:
        """Create relation from database row."""
        return cls(
            source_id=row["source_id"],
            target_id=row["target_id"],
            relation_type=row["relation_type"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
        )


@dataclass
class PathResult:
    """A path between two entities."""

    source: str
    target: str
    path: list[str]  # List of entity IDs
    relations: list[str]  # List of relation types
    length: int
