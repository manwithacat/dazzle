"""Integration tests for neighborhood endpoint (#619 Phase 3)."""

from dazzle.core.ir import GraphEdgeSpec, GraphNodeSpec
from dazzle_back.runtime.graph_serializer import GraphSerializer
from dazzle_back.runtime.neighborhood import NeighborhoodQueryBuilder


class TestNeighborhoodPipeline:
    """Full CTE → fetch → serialize pipeline."""

    def test_directed_cte_then_serialize(self) -> None:
        """CTE SQL shape + serializer produce valid Cytoscape output."""
        ge = GraphEdgeSpec(source="source_id", target="target_id", type_field="kind")
        gn = GraphNodeSpec(edge_entity="Edge", display="title")

        qb = NeighborhoodQueryBuilder(
            node_table="chapter",
            edge_table="chapter_edge",
            graph_edge=ge,
        )
        cte_sql, cte_params = qb.cte_query(seed_id="ch1", depth=2)
        assert "WITH RECURSIVE" in cte_sql
        assert cte_params["seed_id"] == "ch1"
        assert cte_params["max_depth"] == 2

        # Simulate fetched data
        nodes = [
            {"id": "ch1", "title": "Chapter 1"},
            {"id": "ch2", "title": "Chapter 2"},
            {"id": "ch3", "title": "Chapter 3"},
        ]
        edges = [
            {"id": "e1", "source_id": "ch1", "target_id": "ch2", "kind": "sequel"},
            {"id": "e2", "source_id": "ch2", "target_id": "ch3", "kind": "sequel"},
        ]

        serializer = GraphSerializer(graph_edge=ge, graph_node=gn)
        result = serializer.to_cytoscape(edges, nodes)
        assert result["stats"] == {"nodes": 3, "edges": 2}
        labels = {
            e["data"]["id"]: e["data"]["label"] for e in result["elements"] if e["group"] == "nodes"
        }
        assert labels == {
            "ch1": "Chapter 1",
            "ch2": "Chapter 2",
            "ch3": "Chapter 3",
        }

    def test_undirected_cte_shape(self) -> None:
        ge = GraphEdgeSpec(source="a", target="b", directed=False)
        qb = NeighborhoodQueryBuilder(
            node_table="node",
            edge_table="link",
            graph_edge=ge,
        )
        sql, _ = qb.cte_query(seed_id="n1", depth=1)
        assert "CASE" in sql or "OR" in sql

    def test_depth_bounds(self) -> None:
        ge = GraphEdgeSpec(source="s", target="t")
        qb = NeighborhoodQueryBuilder(
            node_table="n",
            edge_table="e",
            graph_edge=ge,
        )
        for d in (1, 2, 3):
            _, params = qb.cte_query(seed_id="x", depth=d)
            assert params["max_depth"] == d

    def test_raw_format_structure(self) -> None:
        """Raw format returns seed + depth + flat lists."""
        result = {
            "seed": "n1",
            "depth": 1,
            "nodes": [{"id": "n1", "title": "Root"}],
            "edges": [],
        }
        assert result["seed"] == "n1"
        assert result["depth"] == 1
        assert len(result["nodes"]) == 1
        assert len(result["edges"]) == 0

    def test_scope_injection_in_cte(self) -> None:
        ge = GraphEdgeSpec(source="s", target="t")
        qb = NeighborhoodQueryBuilder(
            node_table="n",
            edge_table="e",
            graph_edge=ge,
            edge_scope_sql='"org_id" = %s',
            node_scope_sql='"visible" = %s',
        )
        cte_sql, _ = qb.cte_query(seed_id="x", depth=2)
        assert "org_id" in cte_sql

        node_sql, _ = qb.node_fetch_query(node_ids=["x"])
        assert "visible" in node_sql

    def test_cycle_prevention_via_union(self) -> None:
        """UNION (not UNION ALL) prevents infinite cycles."""
        ge = GraphEdgeSpec(source="s", target="t")
        qb = NeighborhoodQueryBuilder(
            node_table="n",
            edge_table="e",
            graph_edge=ge,
        )
        sql, _ = qb.cte_query(seed_id="x", depth=3)
        assert " UNION " in sql
        assert "UNION ALL" not in sql

    def test_empty_neighborhood(self) -> None:
        """Isolated node with no edges."""
        ge = GraphEdgeSpec(source="s", target="t")
        gn = GraphNodeSpec(edge_entity="E", display="name")
        serializer = GraphSerializer(graph_edge=ge, graph_node=gn)

        nodes = [{"id": "lonely", "name": "Alone"}]
        result = serializer.to_cytoscape([], nodes)
        assert result["stats"] == {"nodes": 1, "edges": 0}
        assert result["elements"][0]["data"]["label"] == "Alone"

    def test_d3_neighborhood(self) -> None:
        """D3 format from neighborhood data."""
        ge = GraphEdgeSpec(source="from_id", target="to_id")
        gn = GraphNodeSpec(edge_entity="Link", display="label")
        serializer = GraphSerializer(graph_edge=ge, graph_node=gn)

        nodes = [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]
        edges = [{"id": "e1", "from_id": "a", "to_id": "b"}]
        result = serializer.to_d3(edges, nodes)

        assert len(result["nodes"]) == 2
        assert len(result["links"]) == 1
        assert result["links"][0]["source"] == "a"

    def test_self_loop(self) -> None:
        """Node with edge to itself."""
        ge = GraphEdgeSpec(source="src", target="tgt")
        serializer = GraphSerializer(graph_edge=ge)

        nodes = [{"id": "n1", "title": "Self"}]
        edges = [{"id": "e1", "src": "n1", "tgt": "n1"}]
        result = serializer.to_cytoscape(edges, nodes)
        assert result["stats"] == {"nodes": 1, "edges": 1}
        edge_data = next(e["data"] for e in result["elements"] if e["group"] == "edges")
        assert edge_data["source"] == "n1"
        assert edge_data["target"] == "n1"
