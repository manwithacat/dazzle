"""Tests for graph algorithm functions (#619 Phase 4)."""

import pytest

try:
    import networkx as nx

    HAS_NX = True
except ImportError:
    HAS_NX = False

pytestmark = pytest.mark.skipif(not HAS_NX, reason="networkx not installed")

from dazzle_back.runtime.graph_algorithms import (  # noqa: E402
    connected_components,
    shortest_path,
)


class TestShortestPath:
    def test_direct_connection(self) -> None:
        g = nx.DiGraph()
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        result = shortest_path(g, source="a", target="c")
        assert result["path"] == ["a", "b", "c"]
        assert result["length"] == 2

    def test_no_path(self) -> None:
        g = nx.DiGraph()
        g.add_node("a")
        g.add_node("b")
        result = shortest_path(g, source="a", target="b")
        assert result["path"] == []
        assert result["length"] is None

    def test_same_node(self) -> None:
        g = nx.DiGraph()
        g.add_node("a")
        result = shortest_path(g, source="a", target="a")
        assert result["path"] == ["a"]
        assert result["length"] == 0

    def test_weighted_path(self) -> None:
        g = nx.DiGraph()
        g.add_edge("a", "b", weight=1)
        g.add_edge("a", "c", weight=10)
        g.add_edge("b", "c", weight=1)
        result = shortest_path(g, source="a", target="c", weighted=True)
        assert result["path"] == ["a", "b", "c"]
        assert result["weight"] == 2

    def test_node_not_found(self) -> None:
        g = nx.DiGraph()
        g.add_node("a")
        result = shortest_path(g, source="a", target="nonexistent")
        assert result["path"] == []
        assert result["error"] == "target node not found in graph"

    def test_undirected_path(self) -> None:
        g = nx.Graph()
        g.add_edge("a", "b")
        result = shortest_path(g, source="b", target="a")
        assert result["path"] == ["b", "a"]


class TestConnectedComponents:
    def test_single_component(self) -> None:
        g = nx.Graph()
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        result = connected_components(g)
        assert result["count"] == 1
        assert set(result["components"][0]) == {"a", "b", "c"}

    def test_multiple_components(self) -> None:
        g = nx.Graph()
        g.add_edge("a", "b")
        g.add_edge("c", "d")
        g.add_node("e")
        result = connected_components(g)
        assert result["count"] == 3
        sizes = sorted([len(c) for c in result["components"]], reverse=True)
        assert sizes == [2, 2, 1]

    def test_empty_graph(self) -> None:
        g = nx.Graph()
        result = connected_components(g)
        assert result["count"] == 0
        assert result["components"] == []

    def test_directed_uses_weak_components(self) -> None:
        g = nx.DiGraph()
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        result = connected_components(g)
        assert result["count"] == 1

    def test_components_sorted_by_size(self) -> None:
        g = nx.Graph()
        g.add_edge("a", "b")
        g.add_edge("a", "c")
        g.add_edge("a", "d")
        g.add_node("e")
        result = connected_components(g)
        assert len(result["components"][0]) > len(result["components"][1])
