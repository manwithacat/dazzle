"""
Knowledge Graph query mixin — path finding, neighbourhood traversal, search.

Provides graph traversal capabilities via recursive CTEs and
iterative BFS, plus text search and raw SQL query support.
"""

from __future__ import annotations

from typing import Any

from .models import Entity, PathResult, Relation


class KnowledgeGraphQuery:
    """Mixin providing path-finding, neighbour queries, and search."""

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

        conn = self._get_connection()  # type: ignore[attr-defined]
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
            self._close_connection(conn)  # type: ignore[attr-defined]

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
                relations = self.get_relations(  # type: ignore[attr-defined]
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
            entity = self.get_entity(eid)  # type: ignore[attr-defined]
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
            relations = self.get_relations(  # type: ignore[attr-defined]
                entity_id=entity_id,
                direction="incoming",
            )
            if relation_types:
                relations = [r for r in relations if r.relation_type in relation_types]

            entity_ids = {r.source_id for r in relations}
            return [e for eid in entity_ids if (e := self.get_entity(eid))]  # type: ignore[attr-defined]

        # Transitive: use recursive traversal
        visited: set[str] = set()
        frontier = {entity_id}

        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for eid in frontier:
                relations = self.get_relations(entity_id=eid, direction="incoming")  # type: ignore[attr-defined]
                if relation_types:
                    relations = [r for r in relations if r.relation_type in relation_types]
                for rel in relations:
                    if rel.source_id not in visited and rel.source_id != entity_id:
                        visited.add(rel.source_id)
                        next_frontier.add(rel.source_id)
            frontier = next_frontier

        return [e for eid in visited if (e := self.get_entity(eid))]  # type: ignore[attr-defined]

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
            relations = self.get_relations(  # type: ignore[attr-defined]
                entity_id=entity_id,
                direction="outgoing",
            )
            if relation_types:
                relations = [r for r in relations if r.relation_type in relation_types]

            entity_ids = {r.target_id for r in relations}
            return [e for eid in entity_ids if (e := self.get_entity(eid))]  # type: ignore[attr-defined]

        # Transitive: use recursive traversal
        visited: set[str] = set()
        frontier = {entity_id}

        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for eid in frontier:
                relations = self.get_relations(entity_id=eid, direction="outgoing")  # type: ignore[attr-defined]
                if relation_types:
                    relations = [r for r in relations if r.relation_type in relation_types]
                for rel in relations:
                    if rel.target_id not in visited and rel.target_id != entity_id:
                        visited.add(rel.target_id)
                        next_frontier.add(rel.target_id)
            frontier = next_frontier

        return [e for eid in visited if (e := self.get_entity(eid))]  # type: ignore[attr-defined]

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

        conn = self._get_connection()  # type: ignore[attr-defined]
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
            self._close_connection(conn)  # type: ignore[attr-defined]

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

        conn = self._get_connection()  # type: ignore[attr-defined]
        try:
            rows = conn.execute(sql, params or []).fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_connection(conn)  # type: ignore[attr-defined]

    # =========================================================================
    # Stats
    # =========================================================================

    def get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        conn = self._get_connection()  # type: ignore[attr-defined]
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
            self._close_connection(conn)  # type: ignore[attr-defined]
