"""Tests for graph_edge: and graph_node: DSL constructs (Phase 1 — #619)."""

from pathlib import Path

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl


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
