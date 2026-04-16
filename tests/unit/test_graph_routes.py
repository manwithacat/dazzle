"""Tests for parent-scoped graph endpoints (#781)."""

import json
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from starlette.testclient import TestClient

from dazzle.core.ir import GraphEdgeSpec, GraphNodeSpec


class _Repo:
    """Minimal async repo for routing tests."""

    def __init__(self, items: list[dict[str, Any]]) -> None:
        self._items = items

    async def read(self, id: str) -> dict[str, Any] | None:
        return next((i for i in self._items if str(i.get("id")) == str(id)), None)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        items = self._items
        if filters:
            for key, val in filters.items():
                if key.endswith("__in"):
                    field = key[:-4]
                    allowed = {str(v) for v in val}
                    items = [i for i in items if str(i.get(field)) in allowed]
                else:
                    items = [i for i in items if str(i.get(key)) == str(val)]
        return {"items": items, "total": len(items), "page": page, "page_size": page_size}


def _field(name: str, *, ref_entity: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        type=SimpleNamespace(
            ref_entity=ref_entity,
            kind=SimpleNamespace(value="ref" if ref_entity else "str"),
        ),
    )


def _entity(name: str, fields: list[Any]) -> SimpleNamespace:
    return SimpleNamespace(name=name, fields=fields)


def _mount(router: Any) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _specs_for_parent() -> tuple[list[Any], dict[str, Any]]:
    node_entity = _entity(
        "Node",
        [_field("id"), _field("title"), _field("work_id", ref_entity="Work")],
    )
    edge_entity = _entity(
        "NodeEdge",
        [_field("id"), _field("source", ref_entity="Node"), _field("target", ref_entity="Node")],
    )
    work_entity = _entity("Work", [_field("id"), _field("title")])

    graph_edge = GraphEdgeSpec(source="source", target="target")
    graph_node = GraphNodeSpec(edge_entity="NodeEdge", display="title", parent_field="work_id")
    specs = {
        "Node": {
            "graph_edge": graph_edge,
            "graph_node": graph_node,
            "node_table": "Node",
            "edge_table": "NodeEdge",
        }
    }
    entities = [node_entity, edge_entity, work_entity]
    return entities, specs


class TestBuildParentGraphRoutes:
    def test_returns_none_without_parent_field(self) -> None:
        from dazzle_back.runtime.graph_routes import build_parent_graph_routes

        graph_edge = GraphEdgeSpec(source="source", target="target")
        graph_node = GraphNodeSpec(edge_entity="NodeEdge", display="title")
        specs = {
            "Node": {
                "graph_edge": graph_edge,
                "graph_node": graph_node,
                "node_table": "Node",
                "edge_table": "NodeEdge",
            }
        }
        router = build_parent_graph_routes(specs, entities=[], repositories={})
        assert router is None

    def test_returns_none_without_repos(self) -> None:
        from dazzle_back.runtime.graph_routes import build_parent_graph_routes

        entities, specs = _specs_for_parent()
        router = build_parent_graph_routes(specs, entities=entities, repositories={})
        assert router is None

    def test_returns_router_when_configured(self) -> None:
        from dazzle_back.runtime.graph_routes import build_parent_graph_routes

        entities, specs = _specs_for_parent()
        repos = {
            "Work": _Repo([]),
            "Node": _Repo([]),
            "NodeEdge": _Repo([]),
        }
        router = build_parent_graph_routes(specs, entities=entities, repositories=repos)
        assert router is not None


class TestParentGraphEndpoint:
    def _build(
        self, works: list[dict[str, Any]], nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> TestClient:
        from dazzle_back.runtime.graph_routes import build_parent_graph_routes

        entities, specs = _specs_for_parent()
        repos = {
            "Work": _Repo(works),
            "Node": _Repo(nodes),
            "NodeEdge": _Repo(edges),
        }
        router = build_parent_graph_routes(specs, entities=entities, repositories=repos)
        assert router is not None
        return _mount(router)

    def test_returns_cytoscape_default(self) -> None:
        works = [{"id": "w1", "title": "Work 1"}]
        nodes = [
            {"id": "n1", "title": "Node 1", "work_id": "w1"},
            {"id": "n2", "title": "Node 2", "work_id": "w1"},
            {"id": "n3", "title": "Out of scope", "work_id": "w2"},
        ]
        edges = [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n3"},  # Crosses boundary
        ]

        client = self._build(works, nodes, edges)
        response = client.get("/api/works/w1/graph")
        assert response.status_code == 200
        body = json.loads(response.content)

        assert body["parent"] == {"entity": "Work", "id": "w1"}
        assert body["node_entity"] == "Node"
        assert body["stats"]["nodes"] == 2
        assert body["stats"]["edges"] == 1  # e2 excluded because n3 is out of scope

        elements = body["elements"]
        node_ids = {e["data"]["id"] for e in elements if e["group"] == "nodes"}
        assert node_ids == {"n1", "n2"}
        labels = {e["data"]["label"] for e in elements if e["group"] == "nodes"}
        assert labels == {"Node 1", "Node 2"}
        edge_ids = {e["data"]["id"] for e in elements if e["group"] == "edges"}
        assert edge_ids == {"e1"}

    def test_d3_format(self) -> None:
        works = [{"id": "w1"}]
        nodes = [{"id": "n1", "title": "A", "work_id": "w1"}]
        edges: list[dict[str, Any]] = []

        client = self._build(works, nodes, edges)
        response = client.get("/api/works/w1/graph", params={"format": "d3"})
        body = json.loads(response.content)
        assert "nodes" in body
        assert "links" in body
        assert body["nodes"][0]["id"] == "n1"

    def test_raw_format(self) -> None:
        works = [{"id": "w1"}]
        nodes = [{"id": "n1", "title": "A", "work_id": "w1"}]
        edges: list[dict[str, Any]] = []

        client = self._build(works, nodes, edges)
        response = client.get("/api/works/w1/graph", params={"format": "raw"})
        body = json.loads(response.content)
        assert body == {
            "parent": {"entity": "Work", "id": "w1"},
            "nodes": [{"id": "n1", "title": "A", "work_id": "w1"}],
            "edges": [],
        }

    def test_404_when_parent_missing(self) -> None:
        client = self._build([], [], [])
        response = client.get("/api/works/missing/graph")
        assert response.status_code == 404

    def test_400_on_invalid_format(self) -> None:
        works = [{"id": "w1"}]
        client = self._build(works, [], [])
        response = client.get("/api/works/w1/graph", params={"format": "xml"})
        assert response.status_code == 400

    def test_empty_graph_returns_empty_elements(self) -> None:
        works = [{"id": "w1"}]
        client = self._build(works, [], [])
        response = client.get("/api/works/w1/graph")
        body = json.loads(response.content)
        assert body["stats"] == {"nodes": 0, "edges": 0}
        assert body["elements"] == []


class TestGraphNodeSpecParentField:
    def test_parent_field_defaults_to_none(self) -> None:
        spec = GraphNodeSpec(edge_entity="E")
        assert spec.parent_field is None

    def test_parent_field_stored(self) -> None:
        spec = GraphNodeSpec(edge_entity="E", parent_field="work_id")
        assert spec.parent_field == "work_id"


class TestGraphNodeParser:
    """The parser accepts `parent: <ref_field>` inside graph_node: blocks."""

    def _parse(self, entity_body: str) -> Any:
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl

        dsl = f"""
module testapp
app testapp "Test"

entity Work "Work":
  id: uuid pk
  title: str(200) required

entity NodeEdge "Edge":
  id: uuid pk
  source: ref Node required
  target: ref Node required
  graph_edge:
    source: source
    target: target

entity Node "Node":
  id: uuid pk
  title: str(200) required
  work_id: ref Work required
{entity_body}
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        return next(e for e in fragment.entities if e.name == "Node")

    def test_parent_field_parsed(self) -> None:
        node = self._parse(
            "  graph_node:\n    edges: NodeEdge\n    display: title\n    parent: work_id\n"
        )
        assert node.graph_node is not None
        assert node.graph_node.parent_field == "work_id"

    def test_omitted_parent_field_is_none(self) -> None:
        node = self._parse("  graph_node:\n    edges: NodeEdge\n    display: title\n")
        assert node.graph_node is not None
        assert node.graph_node.parent_field is None
