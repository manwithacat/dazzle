# Graph Serializer (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Edge entity list endpoints serve Cytoscape/D3 JSON when `?format=cytoscape|d3` is passed.

**Architecture:** A pure `GraphSerializer` class handles data transformation. The route generator passes graph metadata to the list handler at route-build time. When format is requested, the handler fetches referenced nodes and delegates to the serializer.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2. Uses existing `CRUDService.execute()` for node fetches.

**Spec:** `docs/superpowers/specs/2026-03-22-graph-serializer-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle_back/runtime/graph_serializer.py` | Create | `GraphSerializer` — pure data transformation (edges + nodes → Cytoscape/D3 JSON) |
| `src/dazzle_back/runtime/route_generator.py` | Modify | Pass graph metadata to list handler; add format branching in `_list_handler_body()` |
| `src/dazzle_back/runtime/server.py` | Modify | Build `entity_graph_specs` dict from IR and pass to `RouteGenerator` |
| `tests/unit/test_graph_serializer.py` | Create | Unit tests for `GraphSerializer` |
| `tests/unit/test_graph_format_api.py` | Create | Integration tests for `?format=` parameter |

---

### Task 1: GraphSerializer — Cytoscape Format

**Files:**
- Create: `src/dazzle_back/runtime/graph_serializer.py`
- Test: `tests/unit/test_graph_serializer.py`

- [ ] **Step 1: Write failing tests for Cytoscape serialization**

Create `tests/unit/test_graph_serializer.py`:

```python
"""Tests for GraphSerializer — graph-shaped API responses (#619 Phase 2)."""

from dazzle_back.runtime.graph_serializer import GraphSerializer
from dazzle.core.ir import GraphEdgeSpec, GraphNodeSpec


class TestCytoscapeFormat:
    """GraphSerializer.to_cytoscape() output."""

    def test_basic_cytoscape(self) -> None:
        ge = GraphEdgeSpec(source="source_node", target="target_node")
        gn = GraphNodeSpec(edge_entity="Edge", display="title")
        s = GraphSerializer(graph_edge=ge, graph_node=gn)

        edges = [
            {"id": "e1", "source_node": "n1", "target_node": "n2", "label": "link"},
        ]
        nodes = [
            {"id": "n1", "title": "Node 1"},
            {"id": "n2", "title": "Node 2"},
        ]

        result = s.to_cytoscape(edges, nodes)

        assert "elements" in result
        assert "stats" in result
        assert result["stats"] == {"nodes": 2, "edges": 1}

        node_elements = [e for e in result["elements"] if e["group"] == "nodes"]
        edge_elements = [e for e in result["elements"] if e["group"] == "edges"]
        assert len(node_elements) == 2
        assert len(edge_elements) == 1

        # Check node data
        n1 = next(e for e in node_elements if e["data"]["id"] == "n1")
        assert n1["data"]["label"] == "Node 1"

        # Check edge data
        e1 = edge_elements[0]
        assert e1["data"]["id"] == "e1"
        assert e1["data"]["source"] == "n1"
        assert e1["data"]["target"] == "n2"

    def test_edge_type_field(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt", type_field="kind")
        s = GraphSerializer(graph_edge=ge)

        edges = [{"id": "e1", "src": "n1", "tgt": "n2", "kind": "sequel"}]
        nodes = [{"id": "n1"}, {"id": "n2"}]

        result = s.to_cytoscape(edges, nodes)
        edge_data = result["elements"][2]["data"]  # nodes first, then edges
        assert edge_data["type"] == "sequel"

    def test_edge_weight_field(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt", weight_field="importance")
        s = GraphSerializer(graph_edge=ge)

        edges = [{"id": "e1", "src": "n1", "tgt": "n2", "importance": 5}]
        nodes = [{"id": "n1"}, {"id": "n2"}]

        result = s.to_cytoscape(edges, nodes)
        edge_data = result["elements"][2]["data"]
        assert edge_data["weight"] == 5

    def test_empty_input(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        s = GraphSerializer(graph_edge=ge)

        result = s.to_cytoscape([], [])
        assert result["elements"] == []
        assert result["stats"] == {"nodes": 0, "edges": 0}

    def test_label_fallback_chain(self) -> None:
        """Falls back through title → name → label → id."""
        ge = GraphEdgeSpec(source="src", target="tgt")
        s = GraphSerializer(graph_edge=ge)

        # No display field, no graph_node — use fallback
        nodes_title = [{"id": "n1", "title": "By Title"}]
        nodes_name = [{"id": "n1", "name": "By Name"}]
        nodes_label = [{"id": "n1", "label": "By Label"}]
        nodes_id_only = [{"id": "n1"}]

        for nodes, expected in [
            (nodes_title, "By Title"),
            (nodes_name, "By Name"),
            (nodes_label, "By Label"),
            (nodes_id_only, "n1"),
        ]:
            result = s.to_cytoscape([], nodes)
            node_data = result["elements"][0]["data"]
            assert node_data["label"] == expected, f"Expected {expected}"

    def test_display_field_overrides_fallback(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        gn = GraphNodeSpec(edge_entity="Edge", display="custom_name")
        s = GraphSerializer(graph_edge=ge, graph_node=gn)

        nodes = [{"id": "n1", "title": "Wrong", "custom_name": "Right"}]
        result = s.to_cytoscape([], nodes)
        assert result["elements"][0]["data"]["label"] == "Right"

    def test_all_entity_fields_included(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        s = GraphSerializer(graph_edge=ge)

        edges = [{"id": "e1", "src": "n1", "tgt": "n2", "color": "red", "weight": 3}]
        nodes = [{"id": "n1", "status": "active", "score": 42}]

        result = s.to_cytoscape(edges, nodes)
        node_data = result["elements"][0]["data"]
        assert node_data["status"] == "active"
        assert node_data["score"] == 42

        edge_data = result["elements"][1]["data"]
        assert edge_data["color"] == "red"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_graph_serializer.py::TestCytoscapeFormat -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement GraphSerializer**

Create `src/dazzle_back/runtime/graph_serializer.py`:

```python
"""Graph-shaped API response serializer (#619 Phase 2).

Transforms flat entity lists into Cytoscape.js or D3 force-graph JSON.
Pure data transformation — no DB access, no request handling.
"""

from __future__ import annotations

from dazzle.core.ir import GraphEdgeSpec, GraphNodeSpec

# Fallback fields for node labels when no display field is configured
_LABEL_FALLBACK_FIELDS = ("title", "name", "label")


class GraphSerializer:
    """Serialize edge + node records into graph visualization formats."""

    def __init__(
        self,
        graph_edge: GraphEdgeSpec,
        graph_node: GraphNodeSpec | None = None,
    ) -> None:
        self._ge = graph_edge
        self._gn = graph_node

    def _node_label(self, node: dict) -> str:
        """Extract the display label for a node."""
        if self._gn and self._gn.display:
            val = node.get(self._gn.display)
            if val is not None:
                return str(val)
        for field in _LABEL_FALLBACK_FIELDS:
            val = node.get(field)
            if val is not None:
                return str(val)
        return str(node.get("id", ""))

    def _edge_data(self, edge: dict) -> dict:
        """Build the data dict for an edge element."""
        data = dict(edge)
        # Map source/target to standard keys
        data["source"] = edge.get(self._ge.source)
        data["target"] = edge.get(self._ge.target)
        if self._ge.type_field and self._ge.type_field in edge:
            data["type"] = edge[self._ge.type_field]
        if self._ge.weight_field and self._ge.weight_field in edge:
            data["weight"] = edge[self._ge.weight_field]
        return data

    def _node_data(self, node: dict) -> dict:
        """Build the data dict for a node element."""
        data = dict(node)
        data["label"] = self._node_label(node)
        return data

    def to_cytoscape(self, edges: list[dict], nodes: list[dict]) -> dict:
        """Serialize to Cytoscape.js JSON format."""
        elements: list[dict] = []
        for node in nodes:
            elements.append({"group": "nodes", "data": self._node_data(node)})
        for edge in edges:
            elements.append({"group": "edges", "data": self._edge_data(edge)})
        return {
            "elements": elements,
            "stats": {"nodes": len(nodes), "edges": len(edges)},
        }

    def to_d3(self, edges: list[dict], nodes: list[dict]) -> dict:
        """Serialize to D3 force-graph JSON format."""
        d3_nodes = [self._node_data(node) for node in nodes]
        d3_links = [self._edge_data(edge) for edge in edges]
        return {"nodes": d3_nodes, "links": d3_links}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_graph_serializer.py::TestCytoscapeFormat -v`
Expected: All PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/graph_serializer.py tests/unit/test_graph_serializer.py
git commit -m "feat: GraphSerializer with Cytoscape format (#619)"
```

---

### Task 2: GraphSerializer — D3 Format

**Files:**
- Modify: `tests/unit/test_graph_serializer.py`

- [ ] **Step 1: Write failing tests for D3 serialization**

Append to `tests/unit/test_graph_serializer.py`:

```python
class TestD3Format:
    """GraphSerializer.to_d3() output."""

    def test_basic_d3(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        gn = GraphNodeSpec(edge_entity="Edge", display="title")
        s = GraphSerializer(graph_edge=ge, graph_node=gn)

        edges = [{"id": "e1", "src": "n1", "tgt": "n2"}]
        nodes = [
            {"id": "n1", "title": "Node 1"},
            {"id": "n2", "title": "Node 2"},
        ]

        result = s.to_d3(edges, nodes)
        assert "nodes" in result
        assert "links" in result
        assert len(result["nodes"]) == 2
        assert len(result["links"]) == 1

        assert result["nodes"][0]["label"] == "Node 1"
        assert result["links"][0]["source"] == "n1"
        assert result["links"][0]["target"] == "n2"

    def test_d3_type_field(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt", type_field="relationship")
        s = GraphSerializer(graph_edge=ge)

        edges = [{"id": "e1", "src": "n1", "tgt": "n2", "relationship": "sequel"}]
        nodes = []

        result = s.to_d3(edges, nodes)
        assert result["links"][0]["type"] == "sequel"

    def test_d3_empty(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        s = GraphSerializer(graph_edge=ge)

        result = s.to_d3([], [])
        assert result == {"nodes": [], "links": []}

    def test_d3_all_fields_included(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        s = GraphSerializer(graph_edge=ge)

        edges = [{"id": "e1", "src": "n1", "tgt": "n2", "extra": "data"}]
        nodes = [{"id": "n1", "custom": "value"}]

        result = s.to_d3(edges, nodes)
        assert result["nodes"][0]["custom"] == "value"
        assert result["links"][0]["extra"] == "data"
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/unit/test_graph_serializer.py -v`
Expected: All PASSED (D3 was already implemented in Task 1).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_graph_serializer.py
git commit -m "test: D3 format serialization tests (#619)"
```

---

### Task 3: Wire Graph Metadata into RouteGenerator

**Files:**
- Modify: `src/dazzle_back/runtime/route_generator.py` (add `entity_graph_specs` param)
- Modify: `src/dazzle_back/runtime/server.py` (build and pass `entity_graph_specs`)

- [ ] **Step 1: Add `entity_graph_specs` to RouteGenerator**

In `src/dazzle_back/runtime/route_generator.py`:

Add to `RouteGenerator.__init__()` parameter list (after `fk_graph`):

```python
        entity_graph_specs: dict[str, tuple[Any, Any | None]] | None = None,
```

Add to `__init__` body (after `self.fk_graph = fk_graph`):

```python
        self.entity_graph_specs = entity_graph_specs or {}
```

In the LIST route generation section (around line 2124), pass graph specs to `create_list_handler`:

```python
            _graph_spec = self.entity_graph_specs.get(entity_name or "")
```

Add `graph_spec=_graph_spec` to the `create_list_handler()` call.

Add `graph_spec` parameter to `create_list_handler()` signature:

```python
    graph_spec: tuple[Any, Any | None] | None = None,
```

- [ ] **Step 2: Build entity_graph_specs in server.py**

In `src/dazzle_back/runtime/server.py`, before the `RouteGenerator(...)` call, build the graph specs dict from the IR:

```python
        # Build graph metadata for edge entities (#619 Phase 2)
        entity_graph_specs: dict[str, tuple] = {}
        for ir_entity in self._appspec.domain.entities:
            if ir_entity.graph_edge is not None:
                # Find graph_node spec for the target entity (if any)
                source_field = next(
                    (f for f in ir_entity.fields if f.name == ir_entity.graph_edge.source), None
                )
                target_field = next(
                    (f for f in ir_entity.fields if f.name == ir_entity.graph_edge.target), None
                )
                # Collect graph_node specs for referenced entities
                node_specs: dict[str, Any] = {}
                for ref_field in (source_field, target_field):
                    if ref_field and ref_field.type.ref_entity:
                        ref_name = ref_field.type.ref_entity
                        ref_ent = next(
                            (e for e in self._appspec.domain.entities if e.name == ref_name), None
                        )
                        if ref_ent and ref_ent.graph_node:
                            node_specs[ref_name] = ref_ent.graph_node
                entity_graph_specs[ir_entity.name] = (ir_entity.graph_edge, node_specs)
```

Pass `entity_graph_specs=entity_graph_specs` to `RouteGenerator(...)`.

- [ ] **Step 3: Verify no regressions**

Run: `pytest tests/unit/test_graph_serializer.py tests/unit/test_parser.py -x -q`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_back/runtime/route_generator.py src/dazzle_back/runtime/server.py
git commit -m "feat: wire graph metadata from IR into route generator (#619)"
```

---

### Task 4: Format Parameter Handling in List Handler

**Files:**
- Modify: `src/dazzle_back/runtime/route_generator.py` (`_list_handler_body` and `create_list_handler`)

- [ ] **Step 1: Add format branching in _list_handler_body**

In `_list_handler_body()`, add the graph format handling. This goes **after** the post-filtering block (after line 1485) and **before** the browser navigation check (before line 1487).

Add these parameters to `_list_handler_body()` signature:

```python
    graph_spec: tuple[Any, Any | None] | None = None,
    all_services: dict[str, Any] | None = None,
```

Add the format handling block:

```python
    # Graph format serialization (#619 Phase 2)
    format_param = request.query_params.get("format")
    if format_param and format_param != "raw":
        from starlette.responses import JSONResponse

        if format_param not in ("cytoscape", "d3"):
            return JSONResponse(
                {"detail": "Invalid format. Supported: cytoscape, d3, raw"},
                status_code=400,
            )
        if graph_spec is None:
            return JSONResponse(
                {"detail": f"Entity '{entity_name}' does not declare graph_edge:"},
                status_code=400,
            )

        from dazzle_back.runtime.graph_serializer import GraphSerializer

        graph_edge_spec, node_specs = graph_spec
        serializer = GraphSerializer(graph_edge=graph_edge_spec)

        # Extract items as dicts
        items = result.get("items", []) if isinstance(result, dict) else []
        edge_dicts = []
        for item in items:
            if hasattr(item, "model_dump"):
                edge_dicts.append(item.model_dump(mode="json"))
            elif isinstance(item, dict):
                edge_dicts.append(item)

        # Collect node IDs grouped by entity type
        node_ids_by_entity: dict[str, set[str]] = {}
        for edge in edge_dicts:
            for field_name in (graph_edge_spec.source, graph_edge_spec.target):
                ref_id = edge.get(field_name)
                if ref_id is None:
                    continue
                # Determine which entity this field refs
                # Use entity_ref_targets to find the target entity name
                ref_entity = (ref_targets or {}).get(field_name, "")
                if ref_entity:
                    node_ids_by_entity.setdefault(ref_entity, set()).add(str(ref_id))

        # Batch-fetch nodes per entity type
        all_nodes: list[dict] = []
        for ref_entity_name, ids in node_ids_by_entity.items():
            node_service = (all_services or {}).get(ref_entity_name)
            if node_service is None:
                continue
            try:
                node_result = await node_service.execute(
                    operation="list",
                    page=1,
                    page_size=len(ids),
                    filters={"id__in": list(ids)},
                )
                node_items = node_result.get("items", []) if isinstance(node_result, dict) else []
                for item in node_items:
                    if hasattr(item, "model_dump"):
                        all_nodes.append(item.model_dump(mode="json"))
                    elif isinstance(item, dict):
                        all_nodes.append(item)
            except Exception:
                pass  # Node fetch failure — edges still returned, nodes omitted

        # Pick the right graph_node spec for the serializer
        # For homogeneous graphs, use the single node spec
        # For heterogeneous, the serializer uses the first available
        gn_spec = None
        if isinstance(node_specs, dict) and node_specs:
            gn_spec = next(iter(node_specs.values()))
        serializer = GraphSerializer(graph_edge=graph_edge_spec, graph_node=gn_spec)

        if format_param == "cytoscape":
            return serializer.to_cytoscape(edge_dicts, all_nodes)
        else:
            return serializer.to_d3(edge_dicts, all_nodes)
```

Also pass `all_services=self.services` from `create_list_handler()` closure where `_list_handler_body` is called. The `self` here refers to the RouteGenerator — but since `create_list_handler` is a standalone function, pass `services` as a parameter.

Update `create_list_handler()` to accept and forward:

```python
    all_services: dict[str, Any] | None = None,
```

And in the RouteGenerator's LIST branch, pass `all_services=self.services`.

- [ ] **Step 2: Verify existing tests still pass**

Run: `pytest tests/unit/test_parser.py tests/unit/test_graph_serializer.py -x -q`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add src/dazzle_back/runtime/route_generator.py
git commit -m "feat: format parameter handling in list handler (#619)"
```

---

### Task 5: Integration Tests

**Files:**
- Create: `tests/unit/test_graph_format_api.py`

- [ ] **Step 1: Write integration tests**

These tests verify the format parameter works end-to-end by testing the graph format branching logic. Since the full server setup is heavy, test the serializer + format validation logic directly.

Create `tests/unit/test_graph_format_api.py`:

```python
"""Integration tests for ?format= parameter on graph edge entities (#619 Phase 2)."""

from dazzle.core.ir import GraphEdgeSpec, GraphNodeSpec
from dazzle_back.runtime.graph_serializer import GraphSerializer


class TestFormatValidation:
    """Validate format parameter handling."""

    def test_cytoscape_round_trip(self) -> None:
        """Full edge + node → Cytoscape JSON round-trip."""
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
            e["data"]["id"]: e["data"]["label"]
            for e in result["elements"]
            if e["group"] == "nodes"
        }
        assert node_labels == {"n1": "Chapter 1", "n2": "Chapter 2", "n3": "Chapter 3"}

        # Verify edge mapping
        edge_e1 = next(
            e for e in result["elements"]
            if e["group"] == "edges" and e["data"]["id"] == "e1"
        )
        assert edge_e1["data"]["source"] == "n1"
        assert edge_e1["data"]["target"] == "n2"
        assert edge_e1["data"]["type"] == "sequel"
        assert edge_e1["data"]["weight"] == 5

    def test_d3_round_trip(self) -> None:
        """Full edge + node → D3 JSON round-trip."""
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

    def test_heterogeneous_graph(self) -> None:
        """Bipartite graph with different node entity types."""
        ge = GraphEdgeSpec(source="author", target="work", type_field="role")
        s = GraphSerializer(graph_edge=ge)

        edges = [
            {"id": "aw1", "author": "a1", "work": "w1", "role": "creator"},
        ]
        # Nodes from two different entity types merged
        nodes = [
            {"id": "a1", "name": "Jane Austen"},
            {"id": "w1", "title": "Pride and Prejudice"},
        ]

        result = s.to_cytoscape(edges, nodes)
        assert result["stats"] == {"nodes": 2, "edges": 1}

        # Different fallback labels (name vs title)
        labels = {
            e["data"]["id"]: e["data"]["label"]
            for e in result["elements"]
            if e["group"] == "nodes"
        }
        assert labels["a1"] == "Jane Austen"
        assert labels["w1"] == "Pride and Prejudice"

    def test_missing_nodes_graceful(self) -> None:
        """Edges reference nodes not in the nodes list (scope-filtered)."""
        ge = GraphEdgeSpec(source="src", target="tgt")
        s = GraphSerializer(graph_edge=ge)

        edges = [{"id": "e1", "src": "n1", "tgt": "n2"}]
        nodes = [{"id": "n1", "title": "Visible"}]  # n2 is hidden

        result = s.to_cytoscape(edges, nodes)
        assert result["stats"] == {"nodes": 1, "edges": 1}
        # Edge still references n2 even though node isn't in the array
        edge_data = next(
            e["data"] for e in result["elements"] if e["group"] == "edges"
        )
        assert edge_data["target"] == "n2"
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/unit/test_graph_format_api.py -v`
Expected: All PASSED.

- [ ] **Step 3: Run all graph-related tests**

Run: `pytest tests/unit/test_graph_semantics.py tests/unit/test_graph_serializer.py tests/unit/test_graph_format_api.py -v`
Expected: All pass.

- [ ] **Step 4: Run linting**

Run: `ruff check src/dazzle_back/runtime/graph_serializer.py src/dazzle_back/runtime/route_generator.py src/dazzle_back/runtime/server.py tests/unit/test_graph_serializer.py tests/unit/test_graph_format_api.py --fix && ruff format src/dazzle_back/runtime/graph_serializer.py tests/unit/test_graph_serializer.py tests/unit/test_graph_format_api.py`
Expected: Clean.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_graph_format_api.py
git commit -m "test: graph serializer integration tests (#619)"
```
