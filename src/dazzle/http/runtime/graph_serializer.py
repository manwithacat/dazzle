"""Graph-shaped API response serializer (#619 Phase 2).

Transforms flat entity lists into Cytoscape.js or D3 force-graph JSON.
Pure data transformation — no DB access, no request handling.
"""

from typing import Any

from dazzle.core.ir import GraphEdgeSpec, GraphNodeSpec

_LABEL_FALLBACK_FIELDS = ("title", "name", "label")


class GraphSerializer:
    """Serialize edge + node records into graph visualization formats."""

    def __init__(
        self,
        graph_edge: GraphEdgeSpec,
        graph_node: GraphNodeSpec | None = None,
    ) -> None:
        self._ge = graph_edge
        self._gn = graph_node

    def _node_label(self, node: dict[str, Any]) -> str:
        if self._gn and self._gn.display:
            val = node.get(self._gn.display)
            if val is not None:
                return str(val)
        for field in _LABEL_FALLBACK_FIELDS:
            val = node.get(field)
            if val is not None:
                return str(val)
        return str(node.get("id", ""))

    def _edge_data(self, edge: dict[str, Any]) -> dict[str, Any]:
        data = dict(edge)
        data["source"] = edge.get(self._ge.source)
        data["target"] = edge.get(self._ge.target)
        if self._ge.type_field and self._ge.type_field in edge:
            data["type"] = edge[self._ge.type_field]
        if self._ge.weight_field and self._ge.weight_field in edge:
            data["weight"] = edge[self._ge.weight_field]
        return data

    def _node_data(self, node: dict[str, Any]) -> dict[str, Any]:
        data = dict(node)
        data["label"] = self._node_label(node)
        return data

    def to_cytoscape(
        self, edges: list[dict[str, Any]], nodes: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Return Cytoscape.js elements JSON."""
        elements: list[dict[str, Any]] = []
        for node in nodes:
            elements.append({"group": "nodes", "data": self._node_data(node)})
        for edge in edges:
            elements.append({"group": "edges", "data": self._edge_data(edge)})
        return {
            "elements": elements,
            "stats": {"nodes": len(nodes), "edges": len(edges)},
        }

    def to_d3(self, edges: list[dict[str, Any]], nodes: list[dict[str, Any]]) -> dict[str, Any]:
        """Return D3 force-graph JSON."""
        return {
            "nodes": [self._node_data(node) for node in nodes],
            "links": [self._edge_data(edge) for edge in edges],
        }
