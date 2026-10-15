"""
SQLite-backed Knowledge Graph storage.

Schema:
- entities: id (prefixed), type, name, metadata (JSON), timestamps
- relations: source_id, target_id, relation_type, metadata (JSON), timestamps

Uses recursive CTEs for graph traversal (paths, neighborhoods).

Method groups are split into mixin classes for maintainability:
- KnowledgeGraphQuery: path finding, adjacency, search
- KnowledgeGraphMetadata: aliases, seed metadata, concept/inference lookup
- KnowledgeGraphActivity: telemetry logging, activity event streaming
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .activity import KnowledgeGraphActivity
from .metadata import KnowledgeGraphMetadata
from .models import Entity, Relation  # Entity/Relation used in this module's body
from .query import KnowledgeGraphQuery

# `KnowledgeGraph` is this module's public surface. The dataclasses (Entity, Relation,
# ActivityEvent, PathResult) live in `.models` — import them from there, not via store.
__all__ = ["KnowledgeGraph"]


class KnowledgeGraph(
    KnowledgeGraphQuery,
    KnowledgeGraphMetadata,
    KnowledgeGraphActivity,
):
    """
    SQLite-backed knowledge graph with graph traversal.

    Designed for efficient queries via indexes and recursive CTEs.
    Thread-safe via connection-per-call pattern.

    Method groups are provided by mixin classes:
    - KnowledgeGraphQuery: path finding, adjacency, search, stats
    - KnowledgeGraphMetadata: aliases, seed metadata, concept/inference lookup
    - KnowledgeGraphActivity: telemetry, activity sessions, event streaming
    """

    # Standard relation types for code analysis
    RELATION_TYPES = {
        "imports": "Module imports another module",
        "defines": "Module defines a symbol (class, function)",
        "calls": "Function calls another function",
        "inherits": "Class inherits from another class",
        "implements": "Class implements an interface/protocol",
        "depends_on": "Generic dependency relationship",
        "contains": "Container relationship (module contains class)",
        "references": "Generic reference relationship",
        "documents": "Documentation relationship",
        "decides": "Decision relates to component",
        # DSL artefact relations
        "uses": "Surface/workspace uses an entity",
        "acts_as": "Story actor is a persona",
        "scopes": "Story scopes to an entity",
        "process_implements": "Process implements a story",
        "invokes": "Process step invokes a service",
        "has_subprocess": "Process step starts a subprocess",
        "human_task_on": "Process step presents a surface",
        "navigates_to": "Experience step navigates to a surface",
        # Subtype polymorphism (#1217 Phase 3(e); #1238 indexes into KG)
        "is_subtype_of": "Polymorphic-child entity points at its base",
        "has_subtype": "Polymorphic-base entity points at each child",
        "allows_persona": "Workspace/surface allows a persona",
        "denies_persona": "Workspace/surface denies a persona",
        "default_workspace": "Persona's default workspace",
        "region_source": "Workspace region sourced from entity",
        # Framework knowledge relations
        "related_concept": "Concept relates to another concept",
        "suggests_for": "Inference entry suggests for a concept",
        "exemplifies": "Pattern exemplifies a concept",
    }

    # Entity type prefixes
    TYPE_PREFIXES = {
        "file:": "file",
        "module:": "module",
        "class:": "class",
        "function:": "function",
        "concept:": "concept",
        "decision:": "decision",
        "pattern:": "pattern",
        "component:": "component",
        "inference:": "inference",
        # DSL artefact prefixes
        "entity:": "dsl_entity",
        "surface:": "dsl_surface",
        "story:": "dsl_story",
        "process:": "dsl_process",
        "persona:": "dsl_persona",
        "workspace:": "dsl_workspace",
        "experience:": "dsl_experience",
        "service:": "dsl_service",
    }

    def __init__(self, db_path: str | Path = ":memory:"):
        """
        Initialize knowledge graph.

        Args:
            db_path: Path to SQLite database, or ":memory:" for in-memory.
        """
        self._db_path = str(db_path)
        self._is_memory = self._db_path == ":memory:"
        # For in-memory DBs, keep a persistent connection to avoid losing data
        self._persistent_conn: sqlite3.Connection | None = None
        if self._is_memory:
            self._persistent_conn = self._create_connection()
        self._init_schema()

    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection with proper settings."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if not self._is_memory:
            conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        if self._is_memory and self._persistent_conn:
            return self._persistent_conn
        return self._create_connection()

    def _close_connection(self, conn: sqlite3.Connection) -> None:
        """Close a connection (but not the persistent one for in-memory DBs)."""
        if not self._is_memory:
            conn.close()

    def _init_schema(self) -> None:
        """Initialize database schema."""
        conn = self._get_connection()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    metadata TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS relations (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    metadata TEXT,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (source_id, target_id, relation_type),
                    FOREIGN KEY (source_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_id) REFERENCES entities(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
                CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
                CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id);
                CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id);
                CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);

                CREATE TABLE IF NOT EXISTS aliases (
                    alias TEXT PRIMARY KEY,
                    canonical_id TEXT NOT NULL,
                    FOREIGN KEY (canonical_id) REFERENCES entities(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_aliases_canonical ON aliases(canonical_id);

                CREATE TABLE IF NOT EXISTS seed_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tool_invocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    operation TEXT,
                    argument_keys TEXT,
                    project_path TEXT,
                    success INTEGER NOT NULL DEFAULT 1,
                    error_message TEXT,
                    result_size INTEGER,
                    duration_ms REAL NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tool_inv_name ON tool_invocations(tool_name);
                CREATE INDEX IF NOT EXISTS idx_tool_inv_created ON tool_invocations(created_at);

                CREATE TABLE IF NOT EXISTS activity_sessions (
                    id TEXT PRIMARY KEY,
                    project_name TEXT,
                    project_path TEXT,
                    dazzle_version TEXT,
                    started_at REAL NOT NULL,
                    ended_at REAL
                );

                CREATE TABLE IF NOT EXISTS activity_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    operation TEXT,
                    ts TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    success INTEGER,
                    duration_ms REAL,
                    error TEXT,
                    warnings INTEGER DEFAULT 0,
                    progress_current INTEGER,
                    progress_total INTEGER,
                    message TEXT,
                    level TEXT DEFAULT 'info',
                    context_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_ae_session ON activity_events(session_id);
                CREATE INDEX IF NOT EXISTS idx_ae_type ON activity_events(event_type);
                CREATE INDEX IF NOT EXISTS idx_ae_created ON activity_events(created_at);
                CREATE INDEX IF NOT EXISTS idx_ae_tool ON activity_events(tool);
            """
            )
            conn.commit()

            # Migration: add source column if missing (existing rows default to 'mcp')
            try:
                conn.execute("ALTER TABLE activity_events ADD COLUMN source TEXT DEFAULT 'mcp'")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists — no-op
        finally:
            self._close_connection(conn)

    def _infer_type(self, entity_id: str) -> str:
        """Infer entity type from ID prefix."""
        for prefix, entity_type in self.TYPE_PREFIXES.items():
            if entity_id.startswith(prefix):
                return entity_type
        return "unknown"

    # =========================================================================
    # Entity CRUD
    # =========================================================================

    def create_entity(
        self,
        entity_id: str,
        name: str,
        entity_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Entity:
        """
        Create or update an entity.

        Args:
            entity_id: Unique ID (preferably prefixed: file:, module:, etc.)
            name: Human-readable name
            entity_type: Type (inferred from prefix if not provided)
            metadata: Additional metadata dict

        Returns:
            Created/updated entity
        """
        now = time.time()
        inferred_type = entity_type or self._infer_type(entity_id)
        meta_json = json.dumps(metadata) if metadata else None

        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO entities (id, entity_type, name, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
            """,
                (entity_id, inferred_type, name, meta_json, now, now),
            )
            conn.commit()
        finally:
            self._close_connection(conn)

        return Entity(
            id=entity_id,
            entity_type=inferred_type,
            name=name,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )

    def get_entity(self, entity_id: str) -> Entity | None:
        """Get an entity by ID."""
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
            return Entity.from_row(row) if row else None
        finally:
            self._close_connection(conn)

    def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity and its relations."""
        conn = self._get_connection()
        try:
            cursor = conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            self._close_connection(conn)

    def list_entities(
        self,
        entity_type: str | None = None,
        name_pattern: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Entity]:
        """
        List entities with optional filtering.

        Args:
            entity_type: Filter by type
            name_pattern: Filter by name (SQL LIKE pattern)
            limit: Max results
            offset: Skip N results
        """
        conditions = []
        params: list[Any] = []

        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)
        if name_pattern:
            conditions.append("name LIKE ?")
            params.append(name_pattern)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])

        conn = self._get_connection()
        try:
            rows = conn.execute(
                f"SELECT * FROM entities {where} ORDER BY name LIMIT ? OFFSET ?",
                params,
            ).fetchall()
            return [Entity.from_row(row) for row in rows]
        finally:
            self._close_connection(conn)

    # =========================================================================
    # Relation CRUD
    # =========================================================================

    def create_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        metadata: dict[str, Any] | None = None,
        create_missing_entities: bool = True,
    ) -> Relation:
        """
        Create a relation between two entities.

        Args:
            source_id: Source entity ID
            target_id: Target entity ID
            relation_type: Type of relation (imports, defines, calls, etc.)
            metadata: Additional metadata
            create_missing_entities: Auto-create entities if they don't exist
        """
        now = time.time()
        meta_json = json.dumps(metadata) if metadata else None

        conn = self._get_connection()
        try:
            # Auto-create missing entities
            if create_missing_entities:
                for eid in [source_id, target_id]:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO entities (id, entity_type, name, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        (eid, self._infer_type(eid), eid, now, now),
                    )

            conn.execute(
                """
                INSERT INTO relations (source_id, target_id, relation_type, metadata, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, relation_type) DO UPDATE SET
                    metadata = excluded.metadata
            """,
                (source_id, target_id, relation_type, meta_json, now),
            )
            conn.commit()
        finally:
            self._close_connection(conn)

        return Relation(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            metadata=metadata or {},
            created_at=now,
        )

    def get_relations(
        self,
        entity_id: str | None = None,
        relation_type: str | None = None,
        direction: str = "both",  # "outgoing", "incoming", "both"
    ) -> list[Relation]:
        """
        Get relations for an entity.

        Args:
            entity_id: Entity to get relations for (None = all relations).
                An empty string is a caller bug, not a synonym for None: it
                used to skip the filter and return every relation in the graph,
                which is how a mistyped lookup in `graph related` served the
                whole knowledge graph as an answer (#1750).
            relation_type: Filter by relation type
            direction: "outgoing" (entity is source), "incoming" (entity is target), "both"
        """
        if entity_id is not None and not entity_id:
            raise ValueError(
                "entity_id must be a non-empty entity id, or None to mean all relations"
            )

        conditions = []
        params: list[Any] = []

        if entity_id:
            if direction == "outgoing":
                conditions.append("source_id = ?")
                params.append(entity_id)
            elif direction == "incoming":
                conditions.append("target_id = ?")
                params.append(entity_id)
            else:  # both
                conditions.append("(source_id = ? OR target_id = ?)")
                params.extend([entity_id, entity_id])

        if relation_type:
            conditions.append("relation_type = ?")
            params.append(relation_type)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        conn = self._get_connection()
        try:
            rows = conn.execute(
                f"SELECT * FROM relations {where} ORDER BY created_at DESC",
                params,
            ).fetchall()
            return [Relation.from_row(row) for row in rows]
        finally:
            self._close_connection(conn)
