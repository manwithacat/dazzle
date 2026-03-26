"""Tests for GraphSerializer — Cytoscape.js and D3 force-graph formats (#619)."""

import pytest

from dazzle.core.ir import GraphEdgeSpec, GraphNodeSpec
from dazzle_back.runtime.graph_serializer import GraphSerializer

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def edge_spec() -> GraphEdgeSpec:
    return GraphEdgeSpec(source="source_id", target="target_id")


@pytest.fixture()
def edge_spec_typed() -> GraphEdgeSpec:
    return GraphEdgeSpec(
        source="source_id",
        target="target_id",
        type_field="rel_type",
    )


@pytest.fixture()
def edge_spec_weighted() -> GraphEdgeSpec:
    return GraphEdgeSpec(
        source="source_id",
        target="target_id",
        weight_field="strength",
    )


@pytest.fixture()
def edge_spec_full() -> GraphEdgeSpec:
    return GraphEdgeSpec(
        source="source_id",
        target="target_id",
        type_field="rel_type",
        weight_field="strength",
    )


@pytest.fixture()
def node_spec() -> GraphNodeSpec:
    return GraphNodeSpec(edge_entity="StoryLink", display="headline")


@pytest.fixture()
def sample_nodes() -> list[dict]:
    return [
        {"id": "n1", "title": "Chapter 1", "color": "red"},
        {"id": "n2", "title": "Chapter 2", "color": "blue"},
    ]


@pytest.fixture()
def sample_edges() -> list[dict]:
    return [
        {"id": "e1", "source_id": "n1", "target_id": "n2"},
    ]


# ---------------------------------------------------------------------------
# TestCytoscapeFormat
# ---------------------------------------------------------------------------


class TestCytoscapeFormat:
    def test_basic_cytoscape(
        self, edge_spec: GraphEdgeSpec, sample_edges: list[dict], sample_nodes: list[dict]
    ) -> None:
        s = GraphSerializer(graph_edge=edge_spec)
        result = s.to_cytoscape(edges=sample_edges, nodes=sample_nodes)

        assert result["stats"] == {"nodes": 2, "edges": 1}
        elements = result["elements"]
        assert len(elements) == 3

        node_elements = [e for e in elements if e["group"] == "nodes"]
        edge_elements = [e for e in elements if e["group"] == "edges"]
        assert len(node_elements) == 2
        assert len(edge_elements) == 1

        # Check source/target mapping
        e_data = edge_elements[0]["data"]
        assert e_data["source"] == "n1"
        assert e_data["target"] == "n2"

        # Check node labels (fallback to title)
        labels = {n["data"]["label"] for n in node_elements}
        assert labels == {"Chapter 1", "Chapter 2"}

    def test_edge_type_field(self, edge_spec_typed: GraphEdgeSpec) -> None:
        edges = [{"id": "e1", "source_id": "n1", "target_id": "n2", "rel_type": "sequel"}]
        s = GraphSerializer(graph_edge=edge_spec_typed)
        result = s.to_cytoscape(edges=edges, nodes=[])
        e_data = result["elements"][0]["data"]
        assert e_data["type"] == "sequel"

    def test_edge_weight_field(self, edge_spec_weighted: GraphEdgeSpec) -> None:
        edges = [{"id": "e1", "source_id": "n1", "target_id": "n2", "strength": 5}]
        s = GraphSerializer(graph_edge=edge_spec_weighted)
        result = s.to_cytoscape(edges=edges, nodes=[])
        e_data = result["elements"][0]["data"]
        assert e_data["weight"] == 5

    def test_empty_input(self, edge_spec: GraphEdgeSpec) -> None:
        s = GraphSerializer(graph_edge=edge_spec)
        result = s.to_cytoscape(edges=[], nodes=[])
        assert result == {"elements": [], "stats": {"nodes": 0, "edges": 0}}

    def test_label_fallback_chain(self, edge_spec: GraphEdgeSpec) -> None:
        s = GraphSerializer(graph_edge=edge_spec)

        # title wins
        node_title = {"id": "1", "title": "T", "name": "N", "label": "L"}
        result = s.to_cytoscape(edges=[], nodes=[node_title])
        assert result["elements"][0]["data"]["label"] == "T"

        # name wins when no title
        node_name = {"id": "2", "name": "N", "label": "L"}
        result = s.to_cytoscape(edges=[], nodes=[node_name])
        assert result["elements"][0]["data"]["label"] == "N"

        # label field wins when no title/name
        node_label = {"id": "3", "label": "L"}
        result = s.to_cytoscape(edges=[], nodes=[node_label])
        assert result["elements"][0]["data"]["label"] == "L"

        # id fallback
        node_id_only = {"id": "4"}
        result = s.to_cytoscape(edges=[], nodes=[node_id_only])
        assert result["elements"][0]["data"]["label"] == "4"

    def test_display_field_overrides_fallback(
        self, edge_spec: GraphEdgeSpec, node_spec: GraphNodeSpec
    ) -> None:
        nodes = [{"id": "n1", "title": "Ignored", "headline": "Breaking News"}]
        s = GraphSerializer(graph_edge=edge_spec, graph_node=node_spec)
        result = s.to_cytoscape(edges=[], nodes=nodes)
        assert result["elements"][0]["data"]["label"] == "Breaking News"

    def test_all_entity_fields_included(self, edge_spec_full: GraphEdgeSpec) -> None:
        nodes = [{"id": "n1", "title": "Ch1", "color": "red", "page_count": 42}]
        edges = [
            {
                "id": "e1",
                "source_id": "n1",
                "target_id": "n2",
                "rel_type": "sequel",
                "strength": 5,
                "metadata": "extra",
            }
        ]
        s = GraphSerializer(graph_edge=edge_spec_full)
        result = s.to_cytoscape(edges=edges, nodes=nodes)

        n_data = result["elements"][0]["data"]
        assert n_data["color"] == "red"
        assert n_data["page_count"] == 42

        e_data = result["elements"][1]["data"]
        assert e_data["metadata"] == "extra"


# ---------------------------------------------------------------------------
# TestD3Format
# ---------------------------------------------------------------------------


class TestD3Format:
    def test_basic_d3(
        self, edge_spec: GraphEdgeSpec, sample_edges: list[dict], sample_nodes: list[dict]
    ) -> None:
        s = GraphSerializer(graph_edge=edge_spec)
        result = s.to_d3(edges=sample_edges, nodes=sample_nodes)

        assert len(result["nodes"]) == 2
        assert len(result["links"]) == 1
        assert result["links"][0]["source"] == "n1"
        assert result["links"][0]["target"] == "n2"
        assert result["nodes"][0]["label"] == "Chapter 1"

    def test_d3_type_field(self, edge_spec_typed: GraphEdgeSpec) -> None:
        edges = [{"id": "e1", "source_id": "n1", "target_id": "n2", "rel_type": "sequel"}]
        s = GraphSerializer(graph_edge=edge_spec_typed)
        result = s.to_d3(edges=edges, nodes=[])
        assert result["links"][0]["type"] == "sequel"

    def test_d3_empty(self, edge_spec: GraphEdgeSpec) -> None:
        s = GraphSerializer(graph_edge=edge_spec)
        result = s.to_d3(edges=[], nodes=[])
        assert result == {"nodes": [], "links": []}

    def test_d3_all_fields_included(self, edge_spec_full: GraphEdgeSpec) -> None:
        nodes = [{"id": "n1", "title": "Ch1", "extra": "val"}]
        edges = [
            {
                "id": "e1",
                "source_id": "n1",
                "target_id": "n2",
                "rel_type": "sequel",
                "strength": 5,
                "metadata": "extra",
            }
        ]
        s = GraphSerializer(graph_edge=edge_spec_full)
        result = s.to_d3(edges=edges, nodes=nodes)

        assert result["nodes"][0]["extra"] == "val"
        assert result["links"][0]["metadata"] == "extra"
        assert result["links"][0]["weight"] == 5
        assert result["links"][0]["type"] == "sequel"
