"""Graph materializer — DB records → NetworkX graph (#619 Phase 4)."""

from __future__ import annotations

from typing import Any

try:
    import networkx as nx

    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None  # type: ignore[assignment]

from dazzle.core.ir import GraphEdgeSpec


class GraphMaterializer:
    """Builds a NetworkX graph from database node/edge records."""

    def __init__(self, graph_edge: GraphEdgeSpec) -> None:
        if not HAS_NETWORKX:
            raise RuntimeError(
                "networkx is required for graph algorithms. "
                "Install with: pip install dazzle-dsl[graph]"
            )
        self._ge = graph_edge

    def build(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> Any:
        """Materialize a NetworkX graph from node and edge record dicts."""
        g: Any = nx.DiGraph() if self._ge.directed else nx.Graph()
        for node in nodes:
            node_id = str(node["id"])
            attrs = {k: v for k, v in node.items() if k != "id"}
            g.add_node(node_id, **attrs)
        for edge in edges:
            source = str(edge[self._ge.source])
            target = str(edge[self._ge.target])
            attrs = {
                k: v for k, v in edge.items() if k not in ("id", self._ge.source, self._ge.target)
            }
            if self._ge.weight_field and self._ge.weight_field in edge:
                attrs["weight"] = edge[self._ge.weight_field]
            g.add_edge(source, target, **attrs)
        return g
