"""
SQLite-backed Knowledge Graph storage.

Schema:
- entities: id (prefixed), type, name, metadata (JSON), timestamps
- relations: source_id, target_id, relation_type, metadata (JSON), timestamps

Uses recursive CTEs for graph traversal (paths, neighborhoods).
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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


class KnowledgeGraph:
    """
    SQLite-backed knowledge graph with graph traversal.

    Designed for efficient queries via indexes and recursive CTEs.
    Thread-safe via connection-per-call pattern.
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
            """
            )
            conn.commit()
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
    # Graph Traversal
    # =========================================================================

    def find_paths(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5,
        relation_types: list[str] | None = None,
    ) -> list[PathResult]:
        """
        Find all paths between two entities using recursive CTE.

        Args:
            source_id: Starting entity
            target_id: Ending entity
            max_depth: Maximum path length
            relation_types: Filter by relation types (None = all)
        """
        type_filter = ""
        params: list[Any] = [source_id, target_id, max_depth]

        if relation_types:
            placeholders = ",".join("?" * len(relation_types))
            type_filter = f"AND r.relation_type IN ({placeholders})"
            params = [source_id] + relation_types + [target_id, max_depth]

        # Recursive CTE for path finding
        query = f"""
            WITH RECURSIVE paths(current, target, path, relations, depth) AS (
                -- Base case: start from source
                SELECT
                    r.target_id,
                    ?,
                    r.source_id || ',' || r.target_id,
                    r.relation_type,
                    1
                FROM relations r
                WHERE r.source_id = ? {type_filter}

                UNION ALL

                -- Recursive case: extend path
                SELECT
                    r.target_id,
                    p.target,
                    p.path || ',' || r.target_id,
                    p.relations || ',' || r.relation_type,
                    p.depth + 1
                FROM paths p
                JOIN relations r ON r.source_id = p.current
                WHERE p.depth < ?
                  AND p.path NOT LIKE '%' || r.target_id || '%'
                  {type_filter}
            )
            SELECT path, relations, depth
            FROM paths
            WHERE current = target
            ORDER BY depth
            LIMIT 10
        """

        # Adjust params for the query structure
        if relation_types:
            params = [target_id, source_id] + relation_types + [max_depth] + relation_types
        else:
            params = [target_id, source_id, max_depth]

        conn = self._get_connection()
        try:
            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                path_ids = row["path"].split(",")
                rel_types = row["relations"].split(",")
                results.append(
                    PathResult(
                        source=source_id,
                        target=target_id,
                        path=path_ids,
                        relations=rel_types,
                        length=row["depth"],
                    )
                )
            return results
        finally:
            self._close_connection(conn)

    def get_neighbourhood(
        self,
        entity_id: str,
        depth: int = 1,
        relation_types: list[str] | None = None,
        direction: str = "both",
    ) -> dict[str, Any]:
        """
        Get the neighborhood of an entity (entities within N hops).

        Args:
            entity_id: Center entity
            depth: How many hops to traverse
            relation_types: Filter by relation types
            direction: "outgoing", "incoming", or "both"

        Returns:
            Dict with 'center', 'entities', 'relations' keys
        """
        visited_ids: set[str] = {entity_id}
        all_relations: list[Relation] = []
        frontier = {entity_id}

        for _ in range(depth):
            next_frontier: set[str] = set()
            for eid in frontier:
                relations = self.get_relations(
                    entity_id=eid,
                    relation_type=relation_types[0]
                    if relation_types and len(relation_types) == 1
                    else None,
                    direction=direction,
                )
                for rel in relations:
                    # Filter by relation types if multiple specified
                    if relation_types and rel.relation_type not in relation_types:
                        continue
                    all_relations.append(rel)
                    # Add neighbors to next frontier
                    neighbor = rel.target_id if rel.source_id == eid else rel.source_id
                    if neighbor not in visited_ids:
                        next_frontier.add(neighbor)
                        visited_ids.add(neighbor)
            frontier = next_frontier

        # Fetch entity details
        entities = []
        for eid in visited_ids:
            entity = self.get_entity(eid)
            if entity:
                entities.append(entity)

        return {
            "center": entity_id,
            "entities": entities,
            "relations": all_relations,
        }

    def get_dependents(
        self,
        entity_id: str,
        relation_types: list[str] | None = None,
        transitive: bool = False,
        max_depth: int = 5,
    ) -> list[Entity]:
        """
        Get entities that depend on this entity (incoming relations).

        Args:
            entity_id: Target entity
            relation_types: Filter by relation types (default: all)
            transitive: Include transitive dependents
            max_depth: Max depth for transitive search
        """
        if not transitive:
            relations = self.get_relations(
                entity_id=entity_id,
                direction="incoming",
            )
            if relation_types:
                relations = [r for r in relations if r.relation_type in relation_types]

            entity_ids = {r.source_id for r in relations}
            return [e for eid in entity_ids if (e := self.get_entity(eid))]

        # Transitive: use recursive traversal
        visited: set[str] = set()
        frontier = {entity_id}

        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for eid in frontier:
                relations = self.get_relations(entity_id=eid, direction="incoming")
                if relation_types:
                    relations = [r for r in relations if r.relation_type in relation_types]
                for rel in relations:
                    if rel.source_id not in visited and rel.source_id != entity_id:
                        visited.add(rel.source_id)
                        next_frontier.add(rel.source_id)
            frontier = next_frontier

        return [e for eid in visited if (e := self.get_entity(eid))]

    def get_dependencies(
        self,
        entity_id: str,
        relation_types: list[str] | None = None,
        transitive: bool = False,
        max_depth: int = 5,
    ) -> list[Entity]:
        """
        Get entities this entity depends on (outgoing relations).

        Args:
            entity_id: Source entity
            relation_types: Filter by relation types
            transitive: Include transitive dependencies
            max_depth: Max depth for transitive search
        """
        if not transitive:
            relations = self.get_relations(
                entity_id=entity_id,
                direction="outgoing",
            )
            if relation_types:
                relations = [r for r in relations if r.relation_type in relation_types]

            entity_ids = {r.target_id for r in relations}
            return [e for eid in entity_ids if (e := self.get_entity(eid))]

        # Transitive: use recursive traversal
        visited: set[str] = set()
        frontier = {entity_id}

        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for eid in frontier:
                relations = self.get_relations(entity_id=eid, direction="outgoing")
                if relation_types:
                    relations = [r for r in relations if r.relation_type in relation_types]
                for rel in relations:
                    if rel.target_id not in visited and rel.target_id != entity_id:
                        visited.add(rel.target_id)
                        next_frontier.add(rel.target_id)
            frontier = next_frontier

        return [e for eid in visited if (e := self.get_entity(eid))]

    # =========================================================================
    # DSL Adjacency
    # =========================================================================

    def compute_adjacency(self, node_a: str, node_b: str, max_distance: int = 2) -> int:
        """
        Compute the shortest distance between two graph nodes.

        Used by the discovery engine to enforce the "two-step adjacency"
        rule: proposed features must be within 2 hops of existing artefacts.

        Args:
            node_a: First entity ID (e.g., "entity:Task")
            node_b: Second entity ID (e.g., "surface:task_list")
            max_distance: Maximum hops to search (default 2)

        Returns:
            Distance: 0=same, 1=direct, 2=two-step, -1=unreachable within max_distance
        """
        if node_a == node_b:
            return 0

        # Try forward direction
        paths = self.find_paths(node_a, node_b, max_depth=max_distance)
        if paths:
            return paths[0].length

        # Try reverse direction (graph is directed, adjacency is conceptually undirected)
        paths = self.find_paths(node_b, node_a, max_depth=max_distance)
        if paths:
            return paths[0].length

        return -1

    def persona_capability_map(self, persona_id: str) -> dict[str, list[Entity]]:
        """
        Build a capability map for a persona: what can they access?

        Queries the graph neighbourhood from the persona node to find
        reachable workspaces, surfaces, and entities.

        Args:
            persona_id: Persona node ID (e.g., "persona:teacher")

        Returns:
            Dict with 'workspaces', 'surfaces', 'entities' keys,
            each containing a list of reachable Entity nodes.
        """
        hood = self.get_neighbourhood(persona_id, depth=2)
        entities = hood["entities"]

        return {
            "workspaces": [e for e in entities if e.entity_type == "dsl_workspace"],
            "surfaces": [e for e in entities if e.entity_type == "dsl_surface"],
            "entities": [e for e in entities if e.entity_type == "dsl_entity"],
            "stories": [e for e in entities if e.entity_type == "dsl_story"],
        }

    # =========================================================================
    # Query Interface
    # =========================================================================

    def query(
        self,
        text: str,
        entity_types: list[str] | None = None,
        limit: int = 20,
    ) -> list[Entity]:
        """
        Search entities by name/metadata text.

        Args:
            text: Search text (matches name or metadata)
            entity_types: Filter by entity types
            limit: Max results
        """
        conditions = ["(name LIKE ? OR metadata LIKE ?)"]
        params: list[Any] = [f"%{text}%", f"%{text}%"]

        if entity_types:
            placeholders = ",".join("?" * len(entity_types))
            conditions.append(f"entity_type IN ({placeholders})")
            params.extend(entity_types)

        params.append(limit)

        conn = self._get_connection()
        try:
            rows = conn.execute(
                f"""
                SELECT * FROM entities
                WHERE {" AND ".join(conditions)}
                ORDER BY updated_at DESC
                LIMIT ?
            """,
                params,
            ).fetchall()
            return [Entity.from_row(row) for row in rows]
        finally:
            self._close_connection(conn)

    def query_sql(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        """
        Execute raw SQL query (read-only).

        Args:
            sql: SQL query (must be SELECT)
            params: Query parameters

        Returns:
            List of result dicts
        """
        sql_upper = sql.strip().upper()
        if not sql_upper.startswith("SELECT"):
            raise ValueError("Only SELECT queries allowed")

        conn = self._get_connection()
        try:
            rows = conn.execute(sql, params or []).fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_connection(conn)

    # =========================================================================
    # Stats
    # =========================================================================

    def get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        conn = self._get_connection()
        try:
            entity_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            relation_count = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]

            type_counts = conn.execute(
                "SELECT entity_type, COUNT(*) as count FROM entities GROUP BY entity_type"
            ).fetchall()

            rel_type_counts = conn.execute(
                "SELECT relation_type, COUNT(*) as count FROM relations GROUP BY relation_type"
            ).fetchall()

            return {
                "entity_count": entity_count,
                "relation_count": relation_count,
                "entity_types": {row["entity_type"]: row["count"] for row in type_counts},
                "relation_types": {row["relation_type"]: row["count"] for row in rel_type_counts},
            }
        finally:
            self._close_connection(conn)

    # =========================================================================
    # Alias Management
    # =========================================================================

    def create_alias(self, alias: str, canonical_id: str) -> None:
        """Create an alias mapping to a canonical entity ID."""
        conn = self._get_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO aliases (alias, canonical_id) VALUES (?, ?)",
                (alias, canonical_id),
            )
            conn.commit()
        finally:
            self._close_connection(conn)

    def resolve_alias(self, alias: str) -> str | None:
        """Resolve an alias to its canonical entity ID, or None if not found."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT canonical_id FROM aliases WHERE alias = ?", (alias,)
            ).fetchone()
            return row["canonical_id"] if row else None
        finally:
            self._close_connection(conn)

    def clear_aliases(self) -> int:
        """Delete all aliases. Returns number deleted."""
        conn = self._get_connection()
        try:
            cursor = conn.execute("DELETE FROM aliases")
            conn.commit()
            return cursor.rowcount
        finally:
            self._close_connection(conn)

    # =========================================================================
    # Seed Metadata
    # =========================================================================

    def set_seed_meta(self, key: str, value: str) -> None:
        """Set a seed metadata key-value pair."""
        conn = self._get_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO seed_meta (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()
        finally:
            self._close_connection(conn)

    def get_seed_meta(self, key: str) -> str | None:
        """Get a seed metadata value by key."""
        conn = self._get_connection()
        try:
            row = conn.execute("SELECT value FROM seed_meta WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None
        finally:
            self._close_connection(conn)

    # =========================================================================
    # Bulk Operations
    # =========================================================================

    def delete_by_metadata_key(self, key: str, value: str) -> int:
        """Delete all entities where metadata contains key=value. Returns count deleted."""
        conn = self._get_connection()
        try:
            # Use JSON extraction to match metadata field
            cursor = conn.execute(
                "DELETE FROM entities WHERE json_extract(metadata, ?) = ?",
                (f"$.{key}", value),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            self._close_connection(conn)

    # =========================================================================
    # Concept & Inference Lookup (for unified KG queries)
    # =========================================================================

    def lookup_concept(self, term: str) -> Entity | None:
        """
        Look up a concept or pattern by name, checking aliases first.

        Args:
            term: Concept name (e.g., "entity", "wizard", "crud")

        Returns:
            Entity if found (concept or pattern), None otherwise
        """
        normalized = term.lower().replace(" ", "_").replace("-", "_")

        # Try alias resolution first
        canonical_id = self.resolve_alias(normalized)
        if canonical_id:
            entity = self.get_entity(canonical_id)
            if entity:
                return entity

        # Try direct concept lookup
        entity = self.get_entity(f"concept:{normalized}")
        if entity:
            return entity

        # Try pattern lookup
        entity = self.get_entity(f"pattern:{normalized}")
        if entity:
            return entity

        return None

    def lookup_inference_matches(
        self,
        query: str,
        limit: int = 20,
    ) -> list[Entity]:
        """
        Find inference entries whose triggers match the query.

        Searches inference entities by matching query words against
        the triggers stored in metadata.

        Args:
            query: Search text
            limit: Maximum results

        Returns:
            List of matching inference entities
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        # Get all inference entities
        inference_entities = self.list_entities(entity_type="inference", limit=500)

        matches: list[Entity] = []
        for entity in inference_entities:
            triggers = entity.metadata.get("triggers", [])
            if not triggers:
                continue

            # Check trigger matching (same logic as _matches_triggers)
            matched = False
            for trigger in triggers:
                trigger_lower = trigger.lower()
                if trigger_lower in query_lower:
                    matched = True
                    break
                trigger_words = set(trigger_lower.split())
                if query_words & trigger_words:
                    matched = True
                    break

            if matched:
                matches.append(entity)
                if len(matches) >= limit:
                    break

        return matches

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

    # =========================================================================
    # Telemetry
    # =========================================================================

    def log_tool_invocation(
        self,
        *,
        tool_name: str,
        operation: str | None = None,
        argument_keys: list[str] | None = None,
        project_path: str | None = None,
        success: bool = True,
        error_message: str | None = None,
        result_size: int | None = None,
        duration_ms: float,
    ) -> None:
        """
        Log a single MCP tool invocation.

        Args:
            tool_name: Consolidated tool name (e.g. "dsl", "story").
            operation: Operation within the tool (e.g. "validate").
            argument_keys: JSON-serializable list of argument key names (never values).
            project_path: Active project path at call time.
            success: Whether the call succeeded.
            error_message: Truncated error message on failure.
            result_size: Length of the result string in characters.
            duration_ms: Wall-clock duration in milliseconds.
        """
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO tool_invocations
                    (tool_name, operation, argument_keys, project_path,
                     success, error_message, result_size, duration_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tool_name,
                    operation,
                    json.dumps(argument_keys) if argument_keys else None,
                    project_path,
                    1 if success else 0,
                    error_message,
                    result_size,
                    duration_ms,
                    time.time(),
                ),
            )
            conn.commit()
        finally:
            self._close_connection(conn)

    def get_tool_invocations(
        self,
        limit: int = 50,
        tool_name_filter: str | None = None,
        since: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve recent tool invocations.

        Args:
            limit: Max rows to return.
            tool_name_filter: Filter to a specific tool name.
            since: Only return invocations after this Unix timestamp.

        Returns:
            List of invocation dicts ordered by created_at DESC.
        """
        conditions: list[str] = []
        params: list[Any] = []

        if tool_name_filter:
            conditions.append("tool_name = ?")
            params.append(tool_name_filter)
        if since is not None:
            conditions.append("created_at >= ?")
            params.append(since)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        conn = self._get_connection()
        try:
            rows = conn.execute(
                f"SELECT * FROM tool_invocations {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_connection(conn)

    def get_tool_stats(self) -> dict[str, Any]:
        """
        Aggregate telemetry statistics.

        Returns:
            Dict with total_calls and by_tool breakdown including
            call_count, error_count, avg_duration_ms, max_duration_ms,
            first_call, and last_call per tool.
        """
        conn = self._get_connection()
        try:
            total = conn.execute("SELECT COUNT(*) FROM tool_invocations").fetchone()[0]
            rows = conn.execute(
                """
                SELECT
                    tool_name,
                    COUNT(*) AS call_count,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS error_count,
                    AVG(duration_ms) AS avg_duration_ms,
                    MAX(duration_ms) AS max_duration_ms,
                    MIN(created_at) AS first_call,
                    MAX(created_at) AS last_call
                FROM tool_invocations
                GROUP BY tool_name
                ORDER BY call_count DESC
                """
            ).fetchall()
            by_tool = [
                {
                    "tool_name": row["tool_name"],
                    "call_count": row["call_count"],
                    "error_count": row["error_count"],
                    "avg_duration_ms": round(row["avg_duration_ms"], 2),
                    "max_duration_ms": round(row["max_duration_ms"], 2),
                    "first_call": row["first_call"],
                    "last_call": row["last_call"],
                }
                for row in rows
            ]
            return {"total_calls": total, "by_tool": by_tool}
        finally:
            self._close_connection(conn)


def _get_dazzle_version() -> str:
    """Get the current Dazzle version string."""
    try:
        from dazzle._version import get_version

        return get_version()
    except Exception:
        return "unknown"
