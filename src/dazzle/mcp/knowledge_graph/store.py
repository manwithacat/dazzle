"""
SQLite-backed Knowledge Graph storage.

Schema:
- entities: id (prefixed), type, name, metadata (JSON), timestamps
- relations: source_id, target_id, relation_type, metadata (JSON), timestamps

Uses recursive CTEs for graph traversal (paths, neighborhoods).

Method groups are split into mixin classes for maintainability:
- KnowledgeGraphQuery: path finding, neighbourhood traversal, search
- KnowledgeGraphMetadata: aliases, seed metadata, concept/inference lookup
- KnowledgeGraphActivity: telemetry logging, activity event streaming
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .activity import KnowledgeGraphActivity
from .metadata import KnowledgeGraphMetadata
from .models import ActivityEvent, Entity, PathResult, Relation
from .query import KnowledgeGraphQuery

# Re-export dataclasses for backward compatibility
__all__ = ["ActivityEvent", "Entity", "KnowledgeGraph", "PathResult", "Relation"]


class KnowledgeGraph(KnowledgeGraphQuery, KnowledgeGraphMetadata, KnowledgeGraphActivity):
    """
    SQLite-backed knowledge graph with graph traversal.

    Designed for efficient queries via indexes and recursive CTEs.
    Thread-safe via connection-per-call pattern.

    Method groups are provided by mixin classes:
    - KnowledgeGraphQuery: path finding, neighbourhood, search, stats
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

    def delete_relation(self, source_id: str, target_id: str, relation_type: str) -> bool:
        """Delete a specific relation."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                DELETE FROM relations
                WHERE source_id = ? AND target_id = ? AND relation_type = ?
            """,
                (source_id, target_id, relation_type),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            self._close_connection(conn)

    def get_relations(
        self,
        entity_id: str | None = None,
        relation_type: str | None = None,
        direction: str = "both",  # "outgoing", "incoming", "both"
    ) -> list[Relation]:
        """
        Get relations for an entity.

        Args:
            entity_id: Entity to get relations for (None = all relations)
            relation_type: Filter by relation type
            direction: "outgoing" (entity is source), "incoming" (entity is target), "both"
        """
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

    # =========================================================================
    # Import / Export
    # =========================================================================

    EXPORT_VERSION = "1.0"

    def export_project_data(self) -> dict[str, Any]:
        """
        Export all non-framework entities and their inter-relations as JSON-serializable dict.

        Framework entities (metadata.source == "framework") are excluded because
        they are always re-seeded on startup.

        Returns:
            Dict with version, metadata, entities, and relations lists.
        """
        conn = self._get_connection()
        try:
            # Collect all non-framework entity IDs
            rows = conn.execute("SELECT * FROM entities ORDER BY id").fetchall()
            project_entities: list[Entity] = []
            project_ids: set[str] = set()
            for row in rows:
                entity = Entity.from_row(row)
                if entity.metadata.get("source") == "framework":
                    continue
                project_entities.append(entity)
                project_ids.add(entity.id)

            # Collect relations where both endpoints are project entities
            rel_rows = conn.execute(
                "SELECT * FROM relations ORDER BY source_id, target_id, relation_type"
            ).fetchall()
            project_relations: list[Relation] = []
            for row in rel_rows:
                rel = Relation.from_row(row)
                if rel.source_id in project_ids and rel.target_id in project_ids:
                    project_relations.append(rel)

            return {
                "version": self.EXPORT_VERSION,
                "exported_at": datetime.now(UTC).isoformat(),
                "dazzle_version": _get_dazzle_version(),
                "entities": [
                    {
                        "id": e.id,
                        "entity_type": e.entity_type,
                        "name": e.name,
                        "metadata": e.metadata,
                        "created_at": e.created_at,
                        "updated_at": e.updated_at,
                    }
                    for e in project_entities
                ],
                "relations": [
                    {
                        "source_id": r.source_id,
                        "target_id": r.target_id,
                        "relation_type": r.relation_type,
                        "metadata": r.metadata,
                        "created_at": r.created_at,
                    }
                    for r in project_relations
                ],
            }
        finally:
            self._close_connection(conn)

    def import_project_data(
        self,
        data: dict[str, Any],
        mode: str = "merge",
    ) -> dict[str, int]:
        """
        Import project data from an export dict.

        Args:
            data: Export dict (must have "version", "entities", "relations").
            mode: "merge" (additive upsert) or "replace" (wipe project data first).

        Returns:
            Stats dict with entities_imported, relations_imported,
            entities_skipped, relations_skipped counts.
        """
        version = data.get("version", "")
        if version != self.EXPORT_VERSION:
            raise ValueError(
                f"Unsupported export version: {version!r} (expected {self.EXPORT_VERSION!r})"
            )

        if mode not in ("merge", "replace"):
            raise ValueError(f"Invalid import mode: {mode!r} (expected 'merge' or 'replace')")

        stats = {
            "entities_imported": 0,
            "relations_imported": 0,
            "entities_skipped": 0,
            "relations_skipped": 0,
        }

        conn = self._get_connection()
        try:
            if mode == "replace":
                # Delete all non-framework entities (cascade deletes their relations)
                conn.execute(
                    "DELETE FROM entities WHERE json_extract(metadata, '$.source') != 'framework'"
                    " OR metadata IS NULL"
                    " OR json_extract(metadata, '$.source') IS NULL"
                )
                conn.commit()

            now = time.time()

            # Import entities
            for ent_data in data.get("entities", []):
                eid = ent_data["id"]
                meta = ent_data.get("metadata", {})

                if mode == "merge":
                    # Check if entity exists
                    existing = conn.execute(
                        "SELECT id FROM entities WHERE id = ?", (eid,)
                    ).fetchone()
                    if existing:
                        # Update existing
                        conn.execute(
                            "UPDATE entities SET name = ?, entity_type = ?, metadata = ?, "
                            "updated_at = ? WHERE id = ?",
                            (
                                ent_data["name"],
                                ent_data["entity_type"],
                                json.dumps(meta) if meta else None,
                                now,
                                eid,
                            ),
                        )
                    else:
                        conn.execute(
                            "INSERT INTO entities (id, entity_type, name, metadata, "
                            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (
                                eid,
                                ent_data["entity_type"],
                                ent_data["name"],
                                json.dumps(meta) if meta else None,
                                now,
                                now,
                            ),
                        )
                else:
                    # Replace mode — always insert
                    conn.execute(
                        "INSERT INTO entities (id, entity_type, name, metadata, "
                        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            eid,
                            ent_data["entity_type"],
                            ent_data["name"],
                            json.dumps(meta) if meta else None,
                            now,
                            now,
                        ),
                    )
                stats["entities_imported"] += 1

            # Import relations
            for rel_data in data.get("relations", []):
                src = rel_data["source_id"]
                tgt = rel_data["target_id"]
                rtype = rel_data["relation_type"]
                meta = rel_data.get("metadata", {})

                if mode == "merge":
                    existing = conn.execute(
                        "SELECT 1 FROM relations WHERE source_id = ? AND target_id = ? "
                        "AND relation_type = ?",
                        (src, tgt, rtype),
                    ).fetchone()
                    if existing:
                        stats["relations_skipped"] += 1
                        continue

                try:
                    conn.execute(
                        "INSERT INTO relations (source_id, target_id, relation_type, "
                        "metadata, created_at) VALUES (?, ?, ?, ?, ?)",
                        (
                            src,
                            tgt,
                            rtype,
                            json.dumps(meta) if meta else None,
                            now,
                        ),
                    )
                    stats["relations_imported"] += 1
                except sqlite3.IntegrityError:
                    stats["relations_skipped"] += 1

            conn.commit()
        finally:
            self._close_connection(conn)

        return stats


def _get_dazzle_version() -> str:
    """Get the current Dazzle version string."""
    try:
        from dazzle._version import get_version

        return get_version()
    except Exception:
        return "unknown"
