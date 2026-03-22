"""Tests for graph_edge: and graph_node: DSL constructs (Phase 1 — #619)."""

from pathlib import Path

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.validator import validate_graph_declarations


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


def _parse(dsl: str) -> ir.AppSpec:
    """Parse DSL text and link into an AppSpec."""
    from dazzle.core.linker import build_appspec

    mod_name, app_name, app_title, app_config, uses, fragment = parse_dsl(dsl, Path("test.dsl"))
    module = ir.ModuleIR(
        name=mod_name,
        file=Path("test.dsl"),
        uses=uses,
        app_name=app_name,
        app_title=app_title,
        app_config=app_config,
        fragment=fragment,
    )
    return build_appspec([module], mod_name)


class TestGraphEdgeParsing:
    """Parser recognizes graph_edge: blocks."""

    def test_basic_graph_edge(self) -> None:
        dsl = """
module test
app g "G"

entity Node "Node":
  id: uuid pk
  title: str(200) required

entity NodeEdge "Edge":
  id: uuid pk
  source_node: ref Node required
  target_node: ref Node required
  relationship: enum[sequel,fork,reference]
  weight: int optional

  graph_edge:
    source: source_node
    target: target_node
    type: relationship
    weight: weight
"""
        appspec = _parse(dsl)
        edge_entity = next(e for e in appspec.domain.entities if e.name == "NodeEdge")
        ge = edge_entity.graph_edge
        assert ge is not None
        assert ge.source == "source_node"
        assert ge.target == "target_node"
        assert ge.type_field == "relationship"
        assert ge.weight_field == "weight"
        assert ge.directed is True
        assert ge.acyclic is False

    def test_graph_edge_with_booleans(self) -> None:
        dsl = """
module test
app g "G"

entity Node "Node":
  id: uuid pk

entity Edge "Edge":
  id: uuid pk
  src: ref Node required
  tgt: ref Node required

  graph_edge:
    source: src
    target: tgt
    directed: false
    acyclic: true
"""
        appspec = _parse(dsl)
        edge_entity = next(e for e in appspec.domain.entities if e.name == "Edge")
        ge = edge_entity.graph_edge
        assert ge is not None
        assert ge.directed is False
        assert ge.acyclic is True

    def test_graph_edge_minimal(self) -> None:
        dsl = """
module test
app g "G"

entity Node "Node":
  id: uuid pk

entity Edge "Edge":
  id: uuid pk
  src: ref Node required
  tgt: ref Node required

  graph_edge:
    source: src
    target: tgt
"""
        appspec = _parse(dsl)
        edge_entity = next(e for e in appspec.domain.entities if e.name == "Edge")
        ge = edge_entity.graph_edge
        assert ge is not None
        assert ge.source == "src"
        assert ge.target == "tgt"
        assert ge.type_field is None
        assert ge.weight_field is None


class TestGraphNodeParsing:
    """Parser recognizes graph_node: blocks."""

    def test_graph_node_with_display(self) -> None:
        dsl = """
module test
app g "G"

entity Node "Node":
  id: uuid pk
  title: str(200) required

  graph_node:
    edges: NodeEdge
    display: title

entity NodeEdge "Edge":
  id: uuid pk
  src: ref Node required
  tgt: ref Node required

  graph_edge:
    source: src
    target: tgt
"""
        appspec = _parse(dsl)
        node_entity = next(e for e in appspec.domain.entities if e.name == "Node")
        gn = node_entity.graph_node
        assert gn is not None
        assert gn.edge_entity == "NodeEdge"
        assert gn.display == "title"

    def test_graph_node_edges_only(self) -> None:
        dsl = """
module test
app g "G"

entity Node "Node":
  id: uuid pk

  graph_node:
    edges: NodeEdge

entity NodeEdge "Edge":
  id: uuid pk
  src: ref Node required
  tgt: ref Node required

  graph_edge:
    source: src
    target: tgt
"""
        appspec = _parse(dsl)
        node_entity = next(e for e in appspec.domain.entities if e.name == "Node")
        gn = node_entity.graph_node
        assert gn is not None
        assert gn.edge_entity == "NodeEdge"
        assert gn.display is None


# =============================================================================
# Helpers for validation tests
# =============================================================================


def _make_entity(
    name: str,
    fields: list[ir.FieldSpec] | None = None,
    graph_edge: ir.GraphEdgeSpec | None = None,
    graph_node: ir.GraphNodeSpec | None = None,
) -> ir.EntitySpec:
    """Helper to build a minimal entity."""
    default_fields = [
        ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
    ]
    return ir.EntitySpec(
        name=name,
        fields=fields or default_fields,
        graph_edge=graph_edge,
        graph_node=graph_node,
    )


def _make_appspec(entities: list[ir.EntitySpec]) -> ir.AppSpec:
    """Helper to build a minimal AppSpec."""
    return ir.AppSpec(
        name="test",
        title="Test",
        domain=ir.DomainSpec(entities=entities),
        surfaces=[],
    )


class TestGraphValidationErrors:
    """Hard errors that block app startup."""

    def test_source_field_not_found(self) -> None:
        entity = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt"),
        )
        node = _make_entity("Node")
        errors, _ = validate_graph_declarations(_make_appspec([node, entity]))
        assert any("source 'src' is not a field on Edge" in e for e in errors)

    def test_target_field_not_found(self) -> None:
        entity = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt"),
        )
        node = _make_entity("Node")
        errors, _ = validate_graph_declarations(_make_appspec([node, entity]))
        assert any("target 'tgt' is not a field on Edge" in e for e in errors)

    def test_source_not_ref_type(self) -> None:
        entity = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(name="src", type=ir.FieldType(kind=ir.FieldTypeKind.STR)),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt"),
        )
        node = _make_entity("Node")
        errors, _ = validate_graph_declarations(_make_appspec([node, entity]))
        assert any("source must be a ref field, got 'str'" in e for e in errors)

    def test_target_not_ref_type(self) -> None:
        entity = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(name="tgt", type=ir.FieldType(kind=ir.FieldTypeKind.STR)),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt"),
        )
        node = _make_entity("Node")
        errors, _ = validate_graph_declarations(_make_appspec([node, entity]))
        assert any("target must be a ref field, got 'str'" in e for e in errors)

    def test_weight_field_not_found(self) -> None:
        entity = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt", weight_field="importance"),
        )
        node = _make_entity("Node")
        errors, _ = validate_graph_declarations(_make_appspec([node, entity]))
        assert any("weight 'importance' is not a field on Edge" in e for e in errors)

    def test_weight_field_not_numeric(self) -> None:
        entity = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(name="importance", type=ir.FieldType(kind=ir.FieldTypeKind.STR)),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt", weight_field="importance"),
        )
        node = _make_entity("Node")
        errors, _ = validate_graph_declarations(_make_appspec([node, entity]))
        assert any("weight must be int or decimal" in e for e in errors)

    def test_type_field_not_found(self) -> None:
        entity = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt", type_field="kind"),
        )
        node = _make_entity("Node")
        errors, _ = validate_graph_declarations(_make_appspec([node, entity]))
        assert any("type 'kind' is not a field on Edge" in e for e in errors)

    def test_graph_node_edges_nonexistent_entity(self) -> None:
        node = _make_entity(
            "Node",
            graph_node=ir.GraphNodeSpec(edge_entity="FakeEdge"),
        )
        errors, _ = validate_graph_declarations(_make_appspec([node]))
        assert any("edges 'FakeEdge' is not a defined entity" in e for e in errors)

    def test_graph_node_edges_entity_has_no_graph_edge(self) -> None:
        edge = _make_entity("EdgeEntity")  # no graph_edge
        node = _make_entity(
            "Node",
            graph_node=ir.GraphNodeSpec(edge_entity="EdgeEntity"),
        )
        errors, _ = validate_graph_declarations(_make_appspec([node, edge]))
        assert any("does not declare graph_edge:" in e for e in errors)

    def test_graph_node_display_field_not_found(self) -> None:
        edge = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt"),
        )
        node = _make_entity(
            "Node",
            graph_node=ir.GraphNodeSpec(edge_entity="Edge", display="nonexistent"),
        )
        errors, _ = validate_graph_declarations(_make_appspec([node, edge]))
        assert any("display 'nonexistent' is not a field on Node" in e for e in errors)

    def test_valid_graph_no_errors(self) -> None:
        node = _make_entity(
            "Node",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(name="title", type=ir.FieldType(kind=ir.FieldTypeKind.STR)),
            ],
            graph_node=ir.GraphNodeSpec(edge_entity="Edge", display="title"),
        )
        edge = _make_entity(
            "Edge",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="src",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
                ir.FieldSpec(
                    name="tgt",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Node"),
                ),
            ],
            graph_edge=ir.GraphEdgeSpec(source="src", target="tgt"),
        )
        errors, _ = validate_graph_declarations(_make_appspec([node, edge]))
        assert errors == []
