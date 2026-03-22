"""Neighborhood query builder — recursive CTE SQL generation (#619 Phase 3).

Generates PostgreSQL recursive CTEs for graph neighborhood traversal.
Pure SQL generation — no DB execution.
"""

from __future__ import annotations

from dazzle.core.ir import GraphEdgeSpec


class NeighborhoodQueryBuilder:
    """Build recursive CTE queries for graph neighborhood traversal."""

    def __init__(
        self,
        node_table: str,
        edge_table: str,
        graph_edge: GraphEdgeSpec,
        node_pk: str = "id",
        edge_scope_sql: str | None = None,
        node_scope_sql: str | None = None,
    ) -> None:
        self._node_table = node_table
        self._edge_table = edge_table
        self._ge = graph_edge
        self._node_pk = node_pk
        self._edge_scope_sql = edge_scope_sql
        self._node_scope_sql = node_scope_sql

    def cte_query(self, seed_id: str, depth: int) -> tuple[str, dict[str, object]]:
        """Generate a recursive CTE that discovers reachable node IDs.

        Returns ``(sql, params)`` with ``%(name)s`` named placeholders.
        """
        src = self._ge.source
        tgt = self._ge.target
        edge_where = f" AND {self._edge_scope_sql}" if self._edge_scope_sql else ""

        if self._ge.directed:
            recursive_select = (
                f'SELECT e."{tgt}", n.depth + 1 '
                f"FROM neighborhood n "
                f'JOIN "{self._edge_table}" e ON e."{src}" = n.node_id '
                f"WHERE n.depth < %(max_depth)s"
                f' AND e."{tgt}" IS NOT NULL'
                f"{edge_where}"
            )
        else:
            recursive_select = (
                f"SELECT CASE "
                f'WHEN e."{src}" = n.node_id THEN e."{tgt}" '
                f'ELSE e."{src}" '
                f"END, n.depth + 1 "
                f"FROM neighborhood n "
                f'JOIN "{self._edge_table}" e '
                f'ON e."{src}" = n.node_id OR e."{tgt}" = n.node_id '
                f"WHERE n.depth < %(max_depth)s"
                f"{edge_where}"
            )

        sql = (
            f"WITH RECURSIVE neighborhood(node_id, depth) AS ("
            f" SELECT %(seed_id)s::uuid, 0"
            f" UNION"
            f" {recursive_select}"
            f") SELECT DISTINCT node_id FROM neighborhood"
        )
        return sql, {"seed_id": seed_id, "max_depth": depth}

    def node_fetch_query(self, node_ids: list[str]) -> tuple[str, dict[str, object]]:
        """Generate a query to fetch nodes by ID."""
        scope_where = f" AND {self._node_scope_sql}" if self._node_scope_sql else ""
        sql = (
            f'SELECT * FROM "{self._node_table}" '
            f'WHERE "{self._node_pk}" IN %(node_ids)s'
            f"{scope_where}"
        )
        return sql, {"node_ids": tuple(node_ids)}

    def edge_fetch_query(self, node_ids: list[str]) -> tuple[str, dict[str, object]]:
        """Generate a query to fetch edges between the given nodes."""
        src = self._ge.source
        tgt = self._ge.target
        scope_where = f" AND {self._edge_scope_sql}" if self._edge_scope_sql else ""
        sql = (
            f'SELECT * FROM "{self._edge_table}" '
            f'WHERE "{src}" IN %(node_ids)s AND "{tgt}" IN %(node_ids)s'
            f"{scope_where}"
        )
        return sql, {"node_ids": tuple(node_ids)}
