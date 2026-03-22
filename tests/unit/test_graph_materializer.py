"""Tests for GraphMaterializer — DB → NetworkX graph (#619 Phase 4)."""

import pytest

try:
    import networkx as nx

    HAS_NX = True
except ImportError:
    HAS_NX = False

pytestmark = pytest.mark.skipif(not HAS_NX, reason="networkx not installed")

from dazzle.core.ir import GraphEdgeSpec  # noqa: E402
from dazzle_back.runtime.graph_materializer import GraphMaterializer  # noqa: E402


class TestGraphMaterializer:
    def test_directed_graph(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        m = GraphMaterializer(graph_edge=ge)
        nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        edges = [
            {"id": "e1", "src": "a", "tgt": "b"},
            {"id": "e2", "src": "b", "tgt": "c"},
        ]
        g = m.build(nodes, edges)
        assert isinstance(g, nx.DiGraph)
        assert len(g.nodes) == 3
        assert len(g.edges) == 2
        assert g.has_edge("a", "b")
        assert not g.has_edge("b", "a")

    def test_undirected_graph(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt", directed=False)
        m = GraphMaterializer(graph_edge=ge)
        nodes = [{"id": "a"}, {"id": "b"}]
        edges = [{"id": "e1", "src": "a", "tgt": "b"}]
        g = m.build(nodes, edges)
        assert isinstance(g, nx.Graph)
        assert not isinstance(g, nx.DiGraph)
        assert g.has_edge("a", "b")
        assert g.has_edge("b", "a")

    def test_edge_attributes(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt", type_field="kind", weight_field="w")
        m = GraphMaterializer(graph_edge=ge)
        nodes = [{"id": "a"}, {"id": "b"}]
        edges = [{"id": "e1", "src": "a", "tgt": "b", "kind": "sequel", "w": 5}]
        g = m.build(nodes, edges)
        data = g.edges["a", "b"]
        assert data["kind"] == "sequel"
        assert data["weight"] == 5

    def test_node_attributes(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        m = GraphMaterializer(graph_edge=ge)
        nodes = [{"id": "a", "title": "Node A", "status": "active"}]
        g = m.build(nodes, [])
        assert g.nodes["a"]["title"] == "Node A"

    def test_empty_graph(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        m = GraphMaterializer(graph_edge=ge)
        g = m.build([], [])
        assert len(g.nodes) == 0

    def test_self_loop(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        m = GraphMaterializer(graph_edge=ge)
        nodes = [{"id": "a"}]
        edges = [{"id": "e1", "src": "a", "tgt": "a"}]
        g = m.build(nodes, edges)
        assert g.has_edge("a", "a")
