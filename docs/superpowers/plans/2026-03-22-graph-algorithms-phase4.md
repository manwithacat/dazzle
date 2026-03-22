# Graph Algorithms (Phase 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Shortest path and connected components endpoints on graph_node entities, powered by NetworkX, with domain-scoped graph materialization.

**Architecture:** A `GraphMaterializer` loads nodes + edges from the DB into an `nx.Graph` (filtered by domain scope + auth scope). Algorithm handler functions operate on the materialized graph and return results via `GraphSerializer`. Endpoints only register when NetworkX is importable.

**Tech Stack:** Python 3.12, NetworkX >= 3.0 (optional extra), PostgreSQL, FastAPI, existing `NeighborhoodQueryBuilder` for SQL, existing `GraphSerializer` for output formatting.

**Spec:** `docs/superpowers/specs/2026-03-22-graph-algorithms-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle_back/runtime/graph_materializer.py` | Create | Load nodes + edges from DB into `nx.Graph`/`nx.DiGraph`, with filter support |
| `src/dazzle_back/runtime/graph_algorithms.py` | Create | Shortest path + connected components on materialized graph |
| `src/dazzle_back/runtime/route_generator.py` | Modify | Register algorithm endpoints on graph_node entities |
| `src/dazzle_back/runtime/server.py` | Modify | Pass filter_fields to algorithm route registration |
| `pyproject.toml` | Modify | Add `graph` optional extra with networkx |
| `tests/unit/test_graph_materializer.py` | Create | Unit tests for materializer |
| `tests/unit/test_graph_algorithms.py` | Create | Unit tests for algorithm functions |

---

### Task 1: Optional NetworkX Dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add graph extra to pyproject.toml**

In `pyproject.toml`, add after the `lsp` extra:

```toml
graph = [
    "networkx>=3.0",
]
```

- [ ] **Step 2: Install the extra**

Run: `pip install -e ".[graph]"`
Expected: NetworkX installed.

- [ ] **Step 3: Verify import**

Run: `python -c "import networkx; print(networkx.__version__)"`
Expected: 3.x.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add networkx as optional graph extra (#619)"
```

---

### Task 2: GraphMaterializer

**Files:**
- Create: `src/dazzle_back/runtime/graph_materializer.py`
- Create: `tests/unit/test_graph_materializer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_graph_materializer.py`:

```python
"""Tests for GraphMaterializer — DB → NetworkX graph (#619 Phase 4)."""

import pytest

try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False

pytestmark = pytest.mark.skipif(not HAS_NX, reason="networkx not installed")

from dazzle.core.ir import GraphEdgeSpec, GraphNodeSpec
from dazzle_back.runtime.graph_materializer import GraphMaterializer


class TestGraphMaterializer:
    """Build nx.Graph from node + edge dicts."""

    def test_directed_graph(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        m = GraphMaterializer(graph_edge=ge)

        nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        edges = [
            {"id": "e1", "src": "a", "tgt": "b"},
            {"id": "e2", "src": "b", "tgt": "c"},
        ]
        g = m.build(nodes, edges)

        assert isinstance(g, nx.DiGraph)
        assert len(g.nodes) == 3
        assert len(g.edges) == 2
        assert g.has_edge("a", "b")
        assert not g.has_edge("b", "a")  # directed

    def test_undirected_graph(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt", directed=False)
        m = GraphMaterializer(graph_edge=ge)

        nodes = [{"id": "a"}, {"id": "b"}]
        edges = [{"id": "e1", "src": "a", "tgt": "b"}]
        g = m.build(nodes, edges)

        assert isinstance(g, nx.Graph)
        assert not isinstance(g, nx.DiGraph)
        assert g.has_edge("a", "b")
        assert g.has_edge("b", "a")  # undirected

    def test_edge_attributes(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt", type_field="kind", weight_field="w")
        m = GraphMaterializer(graph_edge=ge)

        nodes = [{"id": "a"}, {"id": "b"}]
        edges = [{"id": "e1", "src": "a", "tgt": "b", "kind": "sequel", "w": 5}]
        g = m.build(nodes, edges)

        data = g.edges["a", "b"]
        assert data["kind"] == "sequel"
        assert data["weight"] == 5  # mapped from weight_field

    def test_node_attributes(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        m = GraphMaterializer(graph_edge=ge)

        nodes = [{"id": "a", "title": "Node A", "status": "active"}]
        edges: list[dict] = []
        g = m.build(nodes, edges)

        assert g.nodes["a"]["title"] == "Node A"
        assert g.nodes["a"]["status"] == "active"

    def test_empty_graph(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        m = GraphMaterializer(graph_edge=ge)
        g = m.build([], [])
        assert len(g.nodes) == 0
        assert len(g.edges) == 0

    def test_self_loop(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        m = GraphMaterializer(graph_edge=ge)

        nodes = [{"id": "a"}]
        edges = [{"id": "e1", "src": "a", "tgt": "a"}]
        g = m.build(nodes, edges)
        assert g.has_edge("a", "a")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_graph_materializer.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement GraphMaterializer**

Create `src/dazzle_back/runtime/graph_materializer.py`:

```python
"""Graph materializer — DB records → NetworkX graph (#619 Phase 4).

Builds an in-memory NetworkX graph from node and edge record dicts.
Used by graph algorithm endpoints for computed graph properties.
"""

from __future__ import annotations

from typing import Any

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None  # type: ignore[assignment]

from dazzle.core.ir import GraphEdgeSpec


class GraphMaterializer:
    """Build a NetworkX graph from entity records."""

    def __init__(self, graph_edge: GraphEdgeSpec) -> None:
        if not HAS_NETWORKX:
            raise RuntimeError(
                "networkx is required for graph algorithms. "
                "Install with: pip install dazzle-dsl[graph]"
            )
        self._ge = graph_edge

    def build(self, nodes: list[dict], edges: list[dict]) -> Any:
        """Build nx.DiGraph or nx.Graph from record dicts.

        Args:
            nodes: Node entity records (must have 'id' key)
            edges: Edge entity records (must have source/target fields)

        Returns:
            nx.DiGraph if directed, nx.Graph if undirected
        """
        g = nx.DiGraph() if self._ge.directed else nx.Graph()

        for node in nodes:
            node_id = str(node["id"])
            attrs = {k: v for k, v in node.items() if k != "id"}
            g.add_node(node_id, **attrs)

        src_field = self._ge.source
        tgt_field = self._ge.target

        for edge in edges:
            source = str(edge[src_field])
            target = str(edge[tgt_field])
            attrs = {k: v for k, v in edge.items() if k not in ("id", src_field, tgt_field)}
            # Map weight_field to 'weight' for NetworkX algorithm compatibility
            if self._ge.weight_field and self._ge.weight_field in edge:
                attrs["weight"] = edge[self._ge.weight_field]
            g.add_edge(source, target, **attrs)

        return g
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_graph_materializer.py -v`
Expected: All PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/graph_materializer.py tests/unit/test_graph_materializer.py
git commit -m "feat: GraphMaterializer builds NetworkX graph from records (#619)"
```

---

### Task 3: Graph Algorithm Functions

**Files:**
- Create: `src/dazzle_back/runtime/graph_algorithms.py`
- Create: `tests/unit/test_graph_algorithms.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_graph_algorithms.py`:

```python
"""Tests for graph algorithm functions (#619 Phase 4)."""

import pytest

try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False

pytestmark = pytest.mark.skipif(not HAS_NX, reason="networkx not installed")

from dazzle_back.runtime.graph_algorithms import shortest_path, connected_components


class TestShortestPath:
    """shortest_path() function."""

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
    """connected_components() function."""

    def test_single_component(self) -> None:
        g = nx.Graph()
        g.add_edge("a", "b")
        g.add_edge("b", "c")

        result = connected_components(g)
        assert result["count"] == 1
        assert len(result["components"]) == 1
        assert set(result["components"][0]) == {"a", "b", "c"}

    def test_multiple_components(self) -> None:
        g = nx.Graph()
        g.add_edge("a", "b")
        g.add_edge("c", "d")
        g.add_node("e")  # isolated

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
        """For directed graphs, use weakly connected components."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_graph_algorithms.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement algorithm functions**

Create `src/dazzle_back/runtime/graph_algorithms.py`:

```python
"""Graph algorithm functions (#619 Phase 4).

Pure functions operating on NetworkX graphs. No DB access.
"""

from __future__ import annotations

from typing import Any

try:
    import networkx as nx
except ImportError:
    nx = None  # type: ignore[assignment]


def shortest_path(
    g: Any,
    source: str,
    target: str,
    weighted: bool = False,
) -> dict[str, Any]:
    """Find shortest path between two nodes.

    Args:
        g: NetworkX graph (DiGraph or Graph)
        source: Source node ID
        target: Target node ID
        weighted: If True, use edge 'weight' attribute (Dijkstra)

    Returns:
        Dict with 'path' (list of node IDs), 'length', and optionally 'weight'
    """
    if source not in g:
        return {"path": [], "length": None, "error": "source node not found in graph"}
    if target not in g:
        return {"path": [], "length": None, "error": "target node not found in graph"}

    try:
        if weighted:
            path = nx.shortest_path(g, source, target, weight="weight")
            weight = nx.shortest_path_length(g, source, target, weight="weight")
            return {"path": list(path), "length": len(path) - 1, "weight": weight}
        else:
            path = nx.shortest_path(g, source, target)
            return {"path": list(path), "length": len(path) - 1}
    except nx.NetworkXNoPath:
        return {"path": [], "length": None}


def connected_components(g: Any) -> dict[str, Any]:
    """Find connected components in the graph.

    For directed graphs, uses weakly connected components.

    Returns:
        Dict with 'count' and 'components' (list of node ID lists, sorted by size desc)
    """
    if len(g) == 0:
        return {"count": 0, "components": []}

    if isinstance(g, nx.DiGraph):
        components = list(nx.weakly_connected_components(g))
    else:
        components = list(nx.connected_components(g))

    # Sort by size descending, then convert sets to sorted lists
    components.sort(key=len, reverse=True)
    return {
        "count": len(components),
        "components": [sorted(c) for c in components],
    }
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_graph_algorithms.py -v`
Expected: All PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/graph_algorithms.py tests/unit/test_graph_algorithms.py
git commit -m "feat: shortest_path and connected_components algorithms (#619)"
```

---

### Task 4: Algorithm Endpoint Handlers + Route Registration

**Files:**
- Modify: `src/dazzle_back/runtime/route_generator.py`
- Modify: `src/dazzle_back/runtime/server.py`

- [ ] **Step 1: Add algorithm handler factories to route_generator.py**

Add after `create_neighborhood_handler`, before the `RouteGenerator` class:

```python
def _check_networkx() -> bool:
    """Check if networkx is available."""
    try:
        import networkx  # noqa: F401
        return True
    except ImportError:
        return False


async def _materialize_graph(
    db_manager: Any,
    node_table: str,
    edge_table: str,
    graph_edge_spec: Any,
    filters: dict[str, Any] | None = None,
) -> Any:
    """Load nodes + edges from DB and build a NetworkX graph."""
    from dazzle_back.runtime.graph_materializer import GraphMaterializer

    # Build filter WHERE clause
    filter_sql = ""
    filter_params: dict[str, Any] = {}
    if filters:
        clauses = []
        for i, (key, value) in enumerate(filters.items()):
            param_name = f"filter_{i}"
            clauses.append(f'"{key}" = %({param_name})s')
            filter_params[param_name] = value
        filter_sql = " WHERE " + " AND ".join(clauses)

    src = graph_edge_spec.source
    tgt = graph_edge_spec.target

    with db_manager.connection() as conn:
        cursor = conn.cursor()

        # Fetch edges (with optional filter)
        edge_sql = f'SELECT * FROM "{edge_table}"{filter_sql}'
        cursor.execute(edge_sql, filter_params)
        edges = cursor.fetchall()

        # Collect node IDs from edges
        node_ids: set[str] = set()
        for edge in edges:
            if edge.get(src):
                node_ids.add(str(edge[src]))
            if edge.get(tgt):
                node_ids.add(str(edge[tgt]))

        # Fetch nodes
        nodes = []
        if node_ids:
            node_sql = f'SELECT * FROM "{node_table}" WHERE "id" IN %(node_ids)s'
            cursor.execute(node_sql, {"node_ids": tuple(node_ids)})
            nodes = cursor.fetchall()

    # Stringify UUIDs
    def _stringify(rows: list) -> list[dict]:
        result = []
        for row in rows:
            out = {}
            for k, v in row.items():
                out[k] = str(v) if hasattr(v, "hex") else v
            result.append(out)
        return result

    materializer = GraphMaterializer(graph_edge=graph_edge_spec)
    return materializer.build(_stringify(nodes), _stringify(edges)), _stringify(nodes), _stringify(edges)


def create_shortest_path_handler(
    entity_name: str,
    graph_edge_spec: Any,
    graph_node_spec: Any | None,
    node_table: str,
    edge_table: str,
    db_manager: Any,
    filter_fields: list[str] | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Create handler for GET /{entity}/{id}/graph/shortest-path?to={target_id}."""

    async def _handler(
        request: Request,
        id: UUID = Path(...),
        to: UUID = Query(..., description="Target node ID"),
        format: str = Query("cytoscape", description="Response format"),
        weighted: bool = Query(False, description="Use edge weights"),
    ) -> Any:
        from starlette.responses import JSONResponse

        from dazzle_back.runtime.graph_algorithms import shortest_path
        from dazzle_back.runtime.graph_serializer import GraphSerializer

        if format not in _VALID_GRAPH_FORMATS:
            raise HTTPException(status_code=400, detail=f"Invalid format. Supported: {', '.join(sorted(_VALID_GRAPH_FORMATS))}")

        # Extract domain filters from query params
        filters = _extract_domain_filters(request, filter_fields)

        g, all_nodes, all_edges = await _materialize_graph(
            db_manager, node_table, edge_table, graph_edge_spec, filters,
        )

        result = shortest_path(g, source=str(id), target=str(to), weighted=weighted)

        if format == "raw":
            return JSONResponse(content=result)

        # For cytoscape/d3, return the path subgraph
        path_ids = set(result.get("path", []))
        if not path_ids:
            serializer = GraphSerializer(graph_edge=graph_edge_spec, graph_node=graph_node_spec)
            empty = serializer.to_cytoscape([], []) if format == "cytoscape" else serializer.to_d3([], [])
            empty["shortest_path"] = result
            return JSONResponse(content=empty)

        path_nodes = [n for n in all_nodes if str(n.get("id")) in path_ids]
        path_edges = [
            e for e in all_edges
            if str(e.get(graph_edge_spec.source)) in path_ids
            and str(e.get(graph_edge_spec.target)) in path_ids
        ]

        serializer = GraphSerializer(graph_edge=graph_edge_spec, graph_node=graph_node_spec)
        if format == "cytoscape":
            out = serializer.to_cytoscape(path_edges, path_nodes)
        else:
            out = serializer.to_d3(path_edges, path_nodes)
        out["shortest_path"] = result
        return JSONResponse(content=out)

    _handler.__name__ = f"shortest_path_{entity_name.lower()}"
    return _handler


def create_components_handler(
    entity_name: str,
    graph_edge_spec: Any,
    graph_node_spec: Any | None,
    node_table: str,
    edge_table: str,
    db_manager: Any,
    filter_fields: list[str] | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Create handler for GET /{entity}/graph/components."""

    async def _handler(
        request: Request,
        format: str = Query("raw", description="Response format"),
    ) -> Any:
        from starlette.responses import JSONResponse

        from dazzle_back.runtime.graph_algorithms import connected_components

        if format not in _VALID_GRAPH_FORMATS:
            raise HTTPException(status_code=400, detail=f"Invalid format. Supported: {', '.join(sorted(_VALID_GRAPH_FORMATS))}")

        filters = _extract_domain_filters(request, filter_fields)

        g, all_nodes, all_edges = await _materialize_graph(
            db_manager, node_table, edge_table, graph_edge_spec, filters,
        )

        result = connected_components(g)

        if format == "raw":
            return JSONResponse(content=result)

        # For cytoscape/d3, return full graph with component metadata
        from dazzle_back.runtime.graph_serializer import GraphSerializer

        serializer = GraphSerializer(graph_edge=graph_edge_spec, graph_node=graph_node_spec)
        if format == "cytoscape":
            out = serializer.to_cytoscape(all_edges, all_nodes)
        else:
            out = serializer.to_d3(all_edges, all_nodes)
        out["components"] = result
        return JSONResponse(content=out)

    _handler.__name__ = f"components_{entity_name.lower()}"
    return _handler


def _extract_domain_filters(request: Any, filter_fields: list[str] | None) -> dict[str, Any]:
    """Extract domain-scope filters from query params."""
    filters: dict[str, Any] = {}
    if not filter_fields:
        return filters
    reserved = {"format", "to", "weighted", "depth", "page", "page_size", "sort", "dir", "search", "q"}
    for key, value in request.query_params.items():
        if key in filter_fields and key not in reserved and value:
            filters[key] = value
        elif key.startswith("filter[") and key.endswith("]"):
            field = key[7:-1]
            if field in filter_fields and value:
                filters[field] = value
    return filters
```

- [ ] **Step 2: Register algorithm endpoints in generate_route()**

In the LIST route section of `generate_route()`, after the `/graph` neighborhood endpoint registration, add:

```python
            # Register algorithm endpoints for graph_node entities (#619 Phase 4)
            if _node_graph and _check_networkx():
                _filter_fields_for_graph = self.entity_filter_fields.get(entity_name or "")

                # Shortest path
                _sp_path = endpoint.path.rstrip("/") + "/{id}/graph/shortest-path"
                _sp_handler = create_shortest_path_handler(
                    entity_name=entity_name or "Item",
                    graph_edge_spec=_node_graph["graph_edge"],
                    graph_node_spec=_node_graph.get("graph_node"),
                    node_table=_node_graph["node_table"],
                    edge_table=_node_graph["edge_table"],
                    db_manager=self.db_manager,
                    filter_fields=_filter_fields_for_graph,
                    optional_auth_dep=self.optional_auth_dep,
                )
                self._router.add_api_route(
                    _sp_path, _sp_handler, methods=["GET"],
                    tags=[entity_name or "Item"],
                    summary=f"Shortest path for {entity_name}",
                )

                # Connected components
                _cc_path = endpoint.path.rstrip("/") + "/graph/components"
                _cc_handler = create_components_handler(
                    entity_name=entity_name or "Item",
                    graph_edge_spec=_node_graph["graph_edge"],
                    graph_node_spec=_node_graph.get("graph_node"),
                    node_table=_node_graph["node_table"],
                    edge_table=_node_graph["edge_table"],
                    db_manager=self.db_manager,
                    filter_fields=_filter_fields_for_graph,
                    optional_auth_dep=self.optional_auth_dep,
                )
                self._router.add_api_route(
                    _cc_path, _cc_handler, methods=["GET"],
                    tags=[entity_name or "Item"],
                    summary=f"Connected components for {entity_name}",
                )
```

- [ ] **Step 3: Verify no regressions**

Run: `pytest tests/unit/test_graph_materializer.py tests/unit/test_graph_algorithms.py tests/unit/test_neighborhood_query.py -x -q`
Expected: All pass.

- [ ] **Step 4: Run linting**

Run: `ruff check src/dazzle_back/runtime/graph_materializer.py src/dazzle_back/runtime/graph_algorithms.py src/dazzle_back/runtime/route_generator.py --fix && ruff format src/dazzle_back/runtime/graph_materializer.py src/dazzle_back/runtime/graph_algorithms.py`
Expected: Clean.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/route_generator.py
git commit -m "feat: shortest-path and components algorithm endpoints (#619)"
```

---

### Task 5: Integration Tests

**Files:**
- Create: `tests/unit/test_graph_algo_integration.py`

- [ ] **Step 1: Write integration tests**

Create `tests/unit/test_graph_algo_integration.py`:

```python
"""Integration tests for graph algorithm endpoints (#619 Phase 4)."""

import pytest

try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False

pytestmark = pytest.mark.skipif(not HAS_NX, reason="networkx not installed")

from dazzle.core.ir import GraphEdgeSpec, GraphNodeSpec
from dazzle_back.runtime.graph_algorithms import shortest_path, connected_components
from dazzle_back.runtime.graph_materializer import GraphMaterializer
from dazzle_back.runtime.graph_serializer import GraphSerializer


class TestShortestPathPipeline:
    """Full materialize → algorithm → serialize pipeline."""

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

        # Serialize the path subgraph
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
        edges: list[dict] = []

        m = GraphMaterializer(graph_edge=ge)
        g = m.build(nodes, edges)

        result = shortest_path(g, source="a", target="b")
        assert result["path"] == []
        assert result["length"] is None


class TestComponentsPipeline:
    """Full materialize → components → serialize pipeline."""

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
        assert len(result["components"][1]) == 2

    def test_domain_scoped_graph(self) -> None:
        """Simulate domain scoping — only nodes/edges for one work."""
        ge = GraphEdgeSpec(source="src", target="tgt")

        # Imagine work_id filter was applied before materialization
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
        from dazzle_back.runtime.route_generator import _extract_domain_filters
        from unittest.mock import MagicMock

        request = MagicMock()
        request.query_params = {"work_id": "w1", "format": "cytoscape", "extra": "ignored"}

        filters = _extract_domain_filters(request, filter_fields=["work_id"])
        assert filters == {"work_id": "w1"}
        assert "format" not in filters
        assert "extra" not in filters

    def test_bracket_filter_syntax(self) -> None:
        from dazzle_back.runtime.route_generator import _extract_domain_filters
        from unittest.mock import MagicMock

        request = MagicMock()
        request.query_params = {"filter[work_id]": "w1"}

        filters = _extract_domain_filters(request, filter_fields=["work_id"])
        assert filters == {"work_id": "w1"}

    def test_no_filter_fields(self) -> None:
        from dazzle_back.runtime.route_generator import _extract_domain_filters
        from unittest.mock import MagicMock

        request = MagicMock()
        request.query_params = {"work_id": "w1"}

        filters = _extract_domain_filters(request, filter_fields=None)
        assert filters == {}
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/unit/test_graph_materializer.py tests/unit/test_graph_algorithms.py tests/unit/test_graph_algo_integration.py -v`
Expected: All pass.

- [ ] **Step 3: Run full graph test suite**

Run: `pytest tests/unit/test_graph_semantics.py tests/unit/test_graph_serializer.py tests/unit/test_graph_format_api.py tests/unit/test_neighborhood_query.py tests/unit/test_neighborhood_api.py tests/unit/test_graph_materializer.py tests/unit/test_graph_algorithms.py tests/unit/test_graph_algo_integration.py -q`
Expected: All pass.

- [ ] **Step 4: Run linting**

Run: `ruff check src/dazzle_back/runtime/ tests/unit/test_graph_*.py --fix && ruff format src/dazzle_back/runtime/graph_materializer.py src/dazzle_back/runtime/graph_algorithms.py tests/unit/test_graph_materializer.py tests/unit/test_graph_algorithms.py tests/unit/test_graph_algo_integration.py`
Expected: Clean.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_graph_algo_integration.py
git commit -m "test: graph algorithms integration tests with domain scoping (#619)"
```
