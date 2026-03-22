"""Integration tests for graph algorithm endpoints (#619 Phase 4)."""

import pytest

try:
    import networkx as nx  # noqa: F401

    HAS_NX = True
except ImportError:
    HAS_NX = False

pytestmark = pytest.mark.skipif(not HAS_NX, reason="networkx not installed")

from dazzle.core.ir import GraphEdgeSpec, GraphNodeSpec  # noqa: E402
from dazzle_back.runtime.graph_algorithms import connected_components, shortest_path  # noqa: E402
from dazzle_back.runtime.graph_materializer import GraphMaterializer  # noqa: E402
from dazzle_back.runtime.graph_serializer import GraphSerializer  # noqa: E402


class TestShortestPathPipeline:
    """Full materialize -> algorithm -> serialize pipeline."""

    def test_shortest_path_cytoscape(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt", type_field="kind")
        gn = GraphNodeSpec(edge_entity="Edge", display="title")
        nodes = [
            {"id": "a", "title": "Start"},
            {"id": "b", "title": "Middle"},
            {"id": "c", "title": "End"},
            {"id": "d", "title": "Detour"},
        ]
        edges = [
            {"id": "e1", "src": "a", "tgt": "b", "kind": "direct"},
            {"id": "e2", "src": "b", "tgt": "c", "kind": "direct"},
            {"id": "e3", "src": "a", "tgt": "d", "kind": "indirect"},
        ]
        m = GraphMaterializer(graph_edge=ge)
        g = m.build(nodes, edges)
        result = shortest_path(g, source="a", target="c")
        assert result["path"] == ["a", "b", "c"]
        assert result["length"] == 2

        path_ids = set(result["path"])
        path_nodes = [n for n in nodes if n["id"] in path_ids]
        path_edges = [e for e in edges if e["src"] in path_ids and e["tgt"] in path_ids]
        serializer = GraphSerializer(graph_edge=ge, graph_node=gn)
        cyto = serializer.to_cytoscape(path_edges, path_nodes)
        assert cyto["stats"]["nodes"] == 3
        assert cyto["stats"]["edges"] == 2

    def test_weighted_shortest_path(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt", weight_field="cost")
        nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        edges = [
            {"id": "e1", "src": "a", "tgt": "b", "cost": 1},
            {"id": "e2", "src": "b", "tgt": "c", "cost": 1},
            {"id": "e3", "src": "a", "tgt": "c", "cost": 10},
        ]
        m = GraphMaterializer(graph_edge=ge)
        g = m.build(nodes, edges)
        result = shortest_path(g, source="a", target="c", weighted=True)
        assert result["path"] == ["a", "b", "c"]
        assert result["weight"] == 2

    def test_no_path_exists(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        nodes = [{"id": "a"}, {"id": "b"}]
        m = GraphMaterializer(graph_edge=ge)
        g = m.build(nodes, [])
        result = shortest_path(g, source="a", target="b")
        assert result["path"] == []
        assert result["length"] is None


class TestComponentsPipeline:
    """Full materialize -> components -> serialize pipeline."""

    def test_multiple_components(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt", directed=False)
        nodes = [
            {"id": "a", "title": "A"},
            {"id": "b", "title": "B"},
            {"id": "c", "title": "C"},
            {"id": "d", "title": "D"},
        ]
        edges = [
            {"id": "e1", "src": "a", "tgt": "b"},
            {"id": "e2", "src": "c", "tgt": "d"},
        ]
        m = GraphMaterializer(graph_edge=ge)
        g = m.build(nodes, edges)
        result = connected_components(g)
        assert result["count"] == 2
        assert len(result["components"][0]) == 2

    def test_domain_scoped_graph(self) -> None:
        """Simulate domain scoping -- only nodes/edges for one work."""
        ge = GraphEdgeSpec(source="src", target="tgt")
        work1_nodes = [{"id": "n1", "work_id": "w1"}, {"id": "n2", "work_id": "w1"}]
        work1_edges = [{"id": "e1", "src": "n1", "tgt": "n2", "work_id": "w1"}]
        m = GraphMaterializer(graph_edge=ge)
        g = m.build(work1_nodes, work1_edges)
        result = connected_components(g)
        assert result["count"] == 1
        assert set(result["components"][0]) == {"n1", "n2"}


class TestDomainFiltering:
    """Domain-scope filter extraction."""

    def test_extract_domain_filters(self) -> None:
        from unittest.mock import MagicMock

        from dazzle_back.runtime.route_generator import _extract_domain_filters

        request = MagicMock()
        request.query_params = {"work_id": "w1", "format": "cytoscape", "extra": "ignored"}
        filters = _extract_domain_filters(request, filter_fields=["work_id"])
        assert filters == {"work_id": "w1"}
        assert "format" not in filters
        assert "extra" not in filters

    def test_bracket_filter_syntax(self) -> None:
        from unittest.mock import MagicMock

        from dazzle_back.runtime.route_generator import _extract_domain_filters

        request = MagicMock()
        request.query_params = {"filter[work_id]": "w1"}
        filters = _extract_domain_filters(request, filter_fields=["work_id"])
        assert filters == {"work_id": "w1"}

    def test_no_filter_fields(self) -> None:
        from unittest.mock import MagicMock

        from dazzle_back.runtime.route_generator import _extract_domain_filters

        request = MagicMock()
        request.query_params = {"work_id": "w1"}
        filters = _extract_domain_filters(request, filter_fields=None)
        assert filters == {}
