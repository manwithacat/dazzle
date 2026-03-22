"""Integration tests for ?format= parameter on graph edge entities (#619 Phase 2)."""

from dazzle.core.ir import GraphEdgeSpec, GraphNodeSpec
from dazzle_back.runtime.graph_serializer import GraphSerializer


class TestFormatRoundTrip:
    """Full edge + node -> format JSON round-trips."""

    def test_cytoscape_full_graph(self) -> None:
        """Penny Dreadful-style graph with type + weight fields."""
        ge = GraphEdgeSpec(
            source="source_node",
            target="target_node",
            type_field="relationship",
            weight_field="importance",
        )
        gn = GraphNodeSpec(edge_entity="NodeEdge", display="title")
        s = GraphSerializer(graph_edge=ge, graph_node=gn)

        edges = [
            {
                "id": "e1",
                "source_node": "n1",
                "target_node": "n2",
                "relationship": "sequel",
                "importance": 5,
                "created_at": "2026-01-01",
            },
            {
                "id": "e2",
                "source_node": "n2",
                "target_node": "n3",
                "relationship": "fork",
                "importance": 3,
                "created_at": "2026-01-02",
            },
        ]
        nodes = [
            {"id": "n1", "title": "Chapter 1", "status": "published"},
            {"id": "n2", "title": "Chapter 2", "status": "draft"},
            {"id": "n3", "title": "Chapter 3", "status": "draft"},
        ]

        result = s.to_cytoscape(edges, nodes)

        assert result["stats"] == {"nodes": 3, "edges": 2}
        assert len(result["elements"]) == 5

        # Verify node labels
        node_labels = {
            e["data"]["id"]: e["data"]["label"] for e in result["elements"] if e["group"] == "nodes"
        }
        assert node_labels == {
            "n1": "Chapter 1",
            "n2": "Chapter 2",
            "n3": "Chapter 3",
        }

        # Verify edge mapping
        edge_e1 = next(
            e for e in result["elements"] if e["group"] == "edges" and e["data"]["id"] == "e1"
        )
        assert edge_e1["data"]["source"] == "n1"
        assert edge_e1["data"]["target"] == "n2"
        assert edge_e1["data"]["type"] == "sequel"
        assert edge_e1["data"]["weight"] == 5

    def test_d3_full_graph(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt", type_field="kind")
        gn = GraphNodeSpec(edge_entity="Edge", display="name")
        s = GraphSerializer(graph_edge=ge, graph_node=gn)

        edges = [{"id": "e1", "src": "n1", "tgt": "n2", "kind": "link"}]
        nodes = [
            {"id": "n1", "name": "Alpha"},
            {"id": "n2", "name": "Beta"},
        ]

        result = s.to_d3(edges, nodes)

        assert len(result["nodes"]) == 2
        assert len(result["links"]) == 1
        assert result["nodes"][0]["label"] == "Alpha"
        assert result["links"][0]["type"] == "link"
        assert result["links"][0]["source"] == "n1"
        assert result["links"][0]["target"] == "n2"


class TestHeterogeneousGraph:
    """Bipartite/heterogeneous graph support."""

    def test_bipartite_graph(self) -> None:
        """Different source and target entity types (Author -> Work)."""
        ge = GraphEdgeSpec(source="author", target="work", type_field="role")
        s = GraphSerializer(graph_edge=ge)

        edges = [
            {"id": "aw1", "author": "a1", "work": "w1", "role": "creator"},
        ]
        nodes = [
            {"id": "a1", "name": "Jane Austen"},
            {"id": "w1", "title": "Pride and Prejudice"},
        ]

        result = s.to_cytoscape(edges, nodes)
        assert result["stats"] == {"nodes": 2, "edges": 1}

        labels = {
            e["data"]["id"]: e["data"]["label"] for e in result["elements"] if e["group"] == "nodes"
        }
        # Different fallback: name for Author, title for Work
        assert labels["a1"] == "Jane Austen"
        assert labels["w1"] == "Pride and Prejudice"


class TestEdgeCases:
    """Edge cases and graceful degradation."""

    def test_missing_nodes_scope_filtered(self) -> None:
        """Edges reference nodes not in the nodes list (scope-filtered out)."""
        ge = GraphEdgeSpec(source="src", target="tgt")
        s = GraphSerializer(graph_edge=ge)

        edges = [{"id": "e1", "src": "n1", "tgt": "n2"}]
        nodes = [{"id": "n1", "title": "Visible"}]  # n2 hidden by scope

        result = s.to_cytoscape(edges, nodes)
        assert result["stats"] == {"nodes": 1, "edges": 1}
        edge_data = next(e["data"] for e in result["elements"] if e["group"] == "edges")
        assert edge_data["target"] == "n2"  # Edge still references hidden node

    def test_null_source_target(self) -> None:
        """Edge with null FK values."""
        ge = GraphEdgeSpec(source="src", target="tgt")
        s = GraphSerializer(graph_edge=ge)

        edges = [{"id": "e1", "src": None, "tgt": "n1"}]
        nodes = [{"id": "n1"}]

        result = s.to_cytoscape(edges, nodes)
        assert result["stats"]["edges"] == 1
        edge_data = next(e["data"] for e in result["elements"] if e["group"] == "edges")
        assert edge_data["source"] is None
        assert edge_data["target"] == "n1"

    def test_self_loop(self) -> None:
        """Edge where source == target (self-referencing node)."""
        ge = GraphEdgeSpec(source="src", target="tgt")
        s = GraphSerializer(graph_edge=ge)

        edges = [{"id": "e1", "src": "n1", "tgt": "n1"}]
        nodes = [{"id": "n1", "title": "Self"}]

        result = s.to_cytoscape(edges, nodes)
        assert result["stats"] == {"nodes": 1, "edges": 1}
        edge_data = next(e["data"] for e in result["elements"] if e["group"] == "edges")
        assert edge_data["source"] == "n1"
        assert edge_data["target"] == "n1"

    def test_no_type_no_weight(self) -> None:
        """Edge entity with no type_field or weight_field configured."""
        ge = GraphEdgeSpec(source="src", target="tgt")
        s = GraphSerializer(graph_edge=ge)

        edges = [{"id": "e1", "src": "n1", "tgt": "n2"}]
        nodes = [{"id": "n1"}, {"id": "n2"}]

        result = s.to_cytoscape(edges, nodes)
        edge_data = next(e["data"] for e in result["elements"] if e["group"] == "edges")
        assert "type" not in edge_data
        assert "weight" not in edge_data
