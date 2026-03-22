"""Tests for graph_edge: and graph_node: DSL constructs (Phase 1 — #619)."""

from dazzle.core import ir


class TestGraphIRTypes:
    """GraphEdgeSpec and GraphNodeSpec construction."""

    def test_graph_edge_spec_defaults(self) -> None:
        spec = ir.GraphEdgeSpec(source="source_node", target="target_node")
        assert spec.source == "source_node"
        assert spec.target == "target_node"
        assert spec.type_field is None
        assert spec.weight_field is None
        assert spec.directed is True
        assert spec.acyclic is False

    def test_graph_edge_spec_full(self) -> None:
        spec = ir.GraphEdgeSpec(
            source="src",
            target="tgt",
            type_field="relationship",
            weight_field="importance",
            directed=False,
            acyclic=True,
        )
        assert spec.type_field == "relationship"
        assert spec.weight_field == "importance"
        assert spec.directed is False
        assert spec.acyclic is True

    def test_graph_edge_spec_frozen(self) -> None:
        spec = ir.GraphEdgeSpec(source="a", target="b")
        try:
            spec.source = "c"  # type: ignore[misc]
            assert False, "should be frozen"
        except Exception:
            pass

    def test_graph_node_spec(self) -> None:
        spec = ir.GraphNodeSpec(edge_entity="NodeEdge", display="title")
        assert spec.edge_entity == "NodeEdge"
        assert spec.display == "title"

    def test_graph_node_spec_display_optional(self) -> None:
        spec = ir.GraphNodeSpec(edge_entity="NodeEdge")
        assert spec.display is None

    def test_entity_spec_graph_fields_default_none(self) -> None:
        entity = ir.EntitySpec(
            name="Foo",
            fields=[ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID))],
        )
        assert entity.graph_edge is None
        assert entity.graph_node is None
