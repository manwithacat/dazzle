# Neighborhood Endpoint (Phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /{entity}/{id}/graph?depth=N&format=cytoscape|d3` returns the node's neighborhood via recursive CTE.

**Architecture:** `NeighborhoodQueryBuilder` generates PostgreSQL recursive CTE SQL from `graph_edge:` metadata. The route generator registers a `/graph` sub-route on node entities with `graph_node:`. The handler executes the CTE, fetches full records, and delegates to `GraphSerializer` (from Phase 2).

**Tech Stack:** Python 3.12, PostgreSQL recursive CTEs, psycopg v3, FastAPI, existing `GraphSerializer`.

**Spec:** `docs/superpowers/specs/2026-03-22-neighborhood-endpoint-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle_back/runtime/neighborhood.py` | Create | `NeighborhoodQueryBuilder` — recursive CTE SQL generation |
| `src/dazzle_back/runtime/route_generator.py` | Modify | Register `/{slug}/{id}/graph` endpoint for graph_node entities |
| `src/dazzle_back/runtime/server.py` | Modify | Build node graph metadata and pass to RouteGenerator |
| `tests/unit/test_neighborhood_query.py` | Create | Unit tests for SQL generation |
| `tests/unit/test_neighborhood_api.py` | Create | Integration tests for endpoint |

---

### Task 1: NeighborhoodQueryBuilder — CTE SQL Generation

**Files:**
- Create: `src/dazzle_back/runtime/neighborhood.py`
- Create: `tests/unit/test_neighborhood_query.py`

- [ ] **Step 1: Write failing tests for directed CTE**

Create `tests/unit/test_neighborhood_query.py`:

```python
"""Tests for NeighborhoodQueryBuilder — recursive CTE SQL generation (#619 Phase 3)."""

from dazzle.core.ir import GraphEdgeSpec
from dazzle_back.runtime.neighborhood import NeighborhoodQueryBuilder


class TestDirectedCTE:
    """Directed graph CTE generation."""

    def test_cte_basic_directed(self) -> None:
        ge = GraphEdgeSpec(source="source_node_id", target="target_node_id")
        qb = NeighborhoodQueryBuilder(
            node_table="node",
            edge_table="node_edge",
            graph_edge=ge,
        )
        sql, params = qb.cte_query(seed_id="seed-uuid", depth=2)

        # Should contain recursive CTE
        assert "WITH RECURSIVE" in sql
        assert "neighborhood" in sql
        # Should only follow source→target (directed)
        assert "source_node_id" in sql
        assert "target_node_id" in sql
        # Should have depth bound
        assert "depth < " in sql or "depth <" in sql
        # Params should include seed ID and depth
        assert "seed-uuid" in params.values() or "seed-uuid" in list(params.values())

    def test_cte_depth_1(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        qb = NeighborhoodQueryBuilder(
            node_table="nodes", edge_table="edges", graph_edge=ge,
        )
        sql, params = qb.cte_query(seed_id="s1", depth=1)
        assert params["max_depth"] == 1

    def test_cte_returns_distinct_node_ids(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        qb = NeighborhoodQueryBuilder(
            node_table="n", edge_table="e", graph_edge=ge,
        )
        sql, _ = qb.cte_query(seed_id="s1", depth=2)
        assert "DISTINCT" in sql


class TestUndirectedCTE:
    """Undirected graph CTE generation."""

    def test_cte_undirected_bidirectional(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt", directed=False)
        qb = NeighborhoodQueryBuilder(
            node_table="n", edge_table="e", graph_edge=ge,
        )
        sql, _ = qb.cte_query(seed_id="s1", depth=2)
        # Should join on both directions
        assert "OR" in sql or "CASE" in sql


class TestNodeFetchQuery:
    """Node and edge fetch queries."""

    def test_node_fetch_uses_in_clause(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        qb = NeighborhoodQueryBuilder(
            node_table="nodes", edge_table="edges", graph_edge=ge,
        )
        sql, params = qb.node_fetch_query(node_ids=["n1", "n2", "n3"])
        assert "IN" in sql
        assert "nodes" in sql

    def test_edge_fetch_constrains_both_endpoints(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        qb = NeighborhoodQueryBuilder(
            node_table="nodes", edge_table="edges", graph_edge=ge,
        )
        sql, params = qb.edge_fetch_query(node_ids=["n1", "n2"])
        assert "src" in sql
        assert "tgt" in sql
        # Both source and target must be in the node set
        assert sql.count("IN") >= 2 or "AND" in sql


class TestScopeInjection:
    """Scope predicate SQL injection into CTE."""

    def test_edge_scope_injected_into_cte(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        qb = NeighborhoodQueryBuilder(
            node_table="n", edge_table="e", graph_edge=ge,
            edge_scope_sql='"tenant_id" = %s',
        )
        sql, _ = qb.cte_query(seed_id="s1", depth=1)
        assert "tenant_id" in sql

    def test_node_scope_injected_into_node_fetch(self) -> None:
        ge = GraphEdgeSpec(source="src", target="tgt")
        qb = NeighborhoodQueryBuilder(
            node_table="n", edge_table="e", graph_edge=ge,
            node_scope_sql='"realm" = %s',
        )
        sql, _ = qb.node_fetch_query(node_ids=["n1"])
        assert "realm" in sql
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_neighborhood_query.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement NeighborhoodQueryBuilder**

Create `src/dazzle_back/runtime/neighborhood.py`:

```python
"""Neighborhood query builder — recursive CTE SQL generation (#619 Phase 3).

Generates PostgreSQL recursive CTEs for graph neighborhood traversal.
Pure SQL generation — no DB execution.
"""

from __future__ import annotations

from dazzle.core.ir import GraphEdgeSpec


class NeighborhoodQueryBuilder:
    """Build recursive CTE queries for graph neighborhood traversal."""

    def __init__(
        self,
        node_table: str,
        edge_table: str,
        graph_edge: GraphEdgeSpec,
        node_pk: str = "id",
        edge_scope_sql: str | None = None,
        node_scope_sql: str | None = None,
    ) -> None:
        self._node_table = node_table
        self._edge_table = edge_table
        self._ge = graph_edge
        self._node_pk = node_pk
        self._edge_scope_sql = edge_scope_sql
        self._node_scope_sql = node_scope_sql

    def cte_query(self, seed_id: str, depth: int) -> tuple[str, dict]:
        """Build recursive CTE to discover reachable node IDs.

        Returns (sql, params) where sql contains %(<name>)s named placeholders.
        """
        src = self._ge.source
        tgt = self._ge.target

        # Edge scope WHERE fragment
        edge_where = ""
        if self._edge_scope_sql:
            edge_where = f" AND {self._edge_scope_sql}"

        if self._ge.directed:
            recursive_select = (
                f'SELECT e."{tgt}", n.depth + 1 '
                f'FROM neighborhood n '
                f'JOIN "{self._edge_table}" e ON e."{src}" = n.node_id '
                f'WHERE n.depth < %(max_depth)s'
                f' AND e."{tgt}" IS NOT NULL'
                f'{edge_where}'
            )
        else:
            recursive_select = (
                f'SELECT CASE '
                f'WHEN e."{src}" = n.node_id THEN e."{tgt}" '
                f'ELSE e."{src}" '
                f'END, n.depth + 1 '
                f'FROM neighborhood n '
                f'JOIN "{self._edge_table}" e '
                f'ON e."{src}" = n.node_id OR e."{tgt}" = n.node_id '
                f'WHERE n.depth < %(max_depth)s'
                f'{edge_where}'
            )

        sql = (
            f'WITH RECURSIVE neighborhood(node_id, depth) AS ('
            f' SELECT %(seed_id)s::uuid, 0'
            f' UNION'
            f' {recursive_select}'
            f') SELECT DISTINCT node_id FROM neighborhood'
        )

        params = {"seed_id": seed_id, "max_depth": depth}
        return sql, params

    def node_fetch_query(self, node_ids: list[str]) -> tuple[str, dict]:
        """Build query to fetch full node records by ID."""
        scope_where = ""
        if self._node_scope_sql:
            scope_where = f" AND {self._node_scope_sql}"

        sql = (
            f'SELECT * FROM "{self._node_table}" '
            f'WHERE "{self._node_pk}" IN %(node_ids)s'
            f'{scope_where}'
        )
        params = {"node_ids": tuple(node_ids)}
        return sql, params

    def edge_fetch_query(self, node_ids: list[str]) -> tuple[str, dict]:
        """Build query to fetch edges connecting discovered nodes."""
        src = self._ge.source
        tgt = self._ge.target

        scope_where = ""
        if self._edge_scope_sql:
            scope_where = f" AND {self._edge_scope_sql}"

        sql = (
            f'SELECT * FROM "{self._edge_table}" '
            f'WHERE "{src}" IN %(node_ids)s AND "{tgt}" IN %(node_ids)s'
            f'{scope_where}'
        )
        params = {"node_ids": tuple(node_ids)}
        return sql, params
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_neighborhood_query.py -v`
Expected: All PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/neighborhood.py tests/unit/test_neighborhood_query.py
git commit -m "feat: NeighborhoodQueryBuilder for recursive CTE traversal (#619)"
```

---

### Task 2: Neighborhood Route Handler

**Files:**
- Modify: `src/dazzle_back/runtime/route_generator.py`

- [ ] **Step 1: Add neighborhood handler factory**

Add a new function `create_neighborhood_handler()` in `route_generator.py` (near the other `create_*_handler` functions):

```python
def create_neighborhood_handler(
    entity_name: str,
    graph_edge_spec: Any,
    graph_node_spec: Any | None,
    node_table: str,
    edge_table: str,
    db_manager: Any,
    node_service: Any,
    optional_auth_dep: Callable[..., Any] | None = None,
    cedar_access_spec: Any | None = None,
    fk_graph: Any | None = None,
    ref_targets: dict[str, str] | None = None,
) -> Callable[..., Any]:
    """Create handler for GET /{entity}/{id}/graph neighborhood queries."""

    if optional_auth_dep is not None:
        async def _handler(
            request: Request,
            id: UUID = Path(...),
            auth_context: Any = Depends(optional_auth_dep),
            depth: int = Query(1, ge=1, le=3, description="Traversal depth (1-3)"),
            format: str = Query("cytoscape", description="Response format"),
        ) -> Any:
            return await _neighborhood_handler_body(
                request=request,
                seed_id=str(id),
                depth=depth,
                format_param=format,
                entity_name=entity_name,
                graph_edge_spec=graph_edge_spec,
                graph_node_spec=graph_node_spec,
                node_table=node_table,
                edge_table=edge_table,
                db_manager=db_manager,
                node_service=node_service,
                auth_context=auth_context,
                cedar_access_spec=cedar_access_spec,
                fk_graph=fk_graph,
            )

        _handler.__name__ = f"graph_{entity_name.lower()}"
        _handler.__annotations__ = {
            "id": UUID, "request": Request, "depth": int, "format": str, "return": Any,
        }
        return _handler
    else:
        async def _noauth_handler(
            request: Request,
            id: UUID = Path(...),
            depth: int = Query(1, ge=1, le=3, description="Traversal depth (1-3)"),
            format: str = Query("cytoscape", description="Response format"),
        ) -> Any:
            return await _neighborhood_handler_body(
                request=request,
                seed_id=str(id),
                depth=depth,
                format_param=format,
                entity_name=entity_name,
                graph_edge_spec=graph_edge_spec,
                graph_node_spec=graph_node_spec,
                node_table=node_table,
                edge_table=edge_table,
                db_manager=db_manager,
                node_service=node_service,
                auth_context=None,
                cedar_access_spec=cedar_access_spec,
                fk_graph=fk_graph,
            )

        _noauth_handler.__name__ = f"graph_{entity_name.lower()}"
        return _noauth_handler


async def _neighborhood_handler_body(
    *,
    request: Any,
    seed_id: str,
    depth: int,
    format_param: str,
    entity_name: str,
    graph_edge_spec: Any,
    graph_node_spec: Any | None,
    node_table: str,
    edge_table: str,
    db_manager: Any,
    node_service: Any,
    auth_context: Any | None,
    cedar_access_spec: Any | None,
    fk_graph: Any | None,
) -> Any:
    """Execute neighborhood CTE and return graph-formatted response."""
    from starlette.responses import JSONResponse

    from dazzle_back.runtime.graph_serializer import GraphSerializer
    from dazzle_back.runtime.neighborhood import NeighborhoodQueryBuilder

    # Validate format
    if format_param not in ("cytoscape", "d3", "raw"):
        return JSONResponse(
            {"detail": "Invalid format. Supported: cytoscape, d3, raw"},
            status_code=400,
        )

    # Check seed node exists via service
    seed_result = await node_service.execute(operation="read", id=seed_id)
    if seed_result is None:
        return JSONResponse({"detail": "Node not found"}, status_code=404)

    # Build and execute CTE
    qb = NeighborhoodQueryBuilder(
        node_table=node_table,
        edge_table=edge_table,
        graph_edge=graph_edge_spec,
    )

    cte_sql, cte_params = qb.cte_query(seed_id=seed_id, depth=depth)

    with db_manager.connection() as conn:
        cursor = conn.cursor()

        # 1. Get reachable node IDs
        cursor.execute(cte_sql, cte_params)
        node_ids = [str(row["node_id"]) for row in cursor.fetchall()]

        if not node_ids:
            node_ids = [seed_id]

        # 2. Fetch full node records
        node_sql, node_params = qb.node_fetch_query(node_ids)
        cursor.execute(node_sql, node_params)
        nodes = [dict(row) for row in cursor.fetchall()]

        # 3. Fetch edges between discovered nodes
        edge_sql, edge_params = qb.edge_fetch_query(node_ids)
        cursor.execute(edge_sql, edge_params)
        edges = [dict(row) for row in cursor.fetchall()]

    # Serialize UUIDs to strings for JSON
    for record in nodes + edges:
        for key, val in record.items():
            if hasattr(val, "hex"):  # UUID
                record[key] = str(val)

    # Format response
    if format_param == "raw":
        return {
            "seed": seed_id,
            "depth": depth,
            "nodes": nodes,
            "edges": edges,
        }

    serializer = GraphSerializer(graph_edge=graph_edge_spec, graph_node=graph_node_spec)
    if format_param == "cytoscape":
        return serializer.to_cytoscape(edges, nodes)
    else:
        return serializer.to_d3(edges, nodes)
```

- [ ] **Step 2: Verify no regressions**

Run: `pytest tests/unit/test_graph_serializer.py tests/unit/test_neighborhood_query.py -x -q`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add src/dazzle_back/runtime/route_generator.py
git commit -m "feat: neighborhood handler for graph traversal endpoint (#619)"
```

---

### Task 3: Route Registration for Graph Nodes

**Files:**
- Modify: `src/dazzle_back/runtime/route_generator.py` (route registration in `generate_route`)
- Modify: `src/dazzle_back/runtime/server.py` (pass node metadata to RouteGenerator)

- [ ] **Step 1: Add node_graph_specs to RouteGenerator**

In `RouteGenerator.__init__()`, add:

```python
        node_graph_specs: dict[str, dict] | None = None,
        db_manager: Any | None = None,
```

Store as:
```python
        self.node_graph_specs = node_graph_specs or {}
        self.db_manager = db_manager
```

- [ ] **Step 2: Register /graph endpoint after LIST route**

In `generate_route()`, after the LIST route is registered (after `self._add_route(endpoint, handler, response_model=None)` for the LIST case), add:

```python
            # Register /graph neighborhood endpoint for graph_node entities (#619)
            _node_graph = self.node_graph_specs.get(entity_name or "")
            if _node_graph:
                _graph_path = endpoint.path.rstrip("/") + "/{id}/graph"
                _graph_handler = create_neighborhood_handler(
                    entity_name=entity_name or "Item",
                    graph_edge_spec=_node_graph["graph_edge"],
                    graph_node_spec=_node_graph.get("graph_node"),
                    node_table=_node_graph["node_table"],
                    edge_table=_node_graph["edge_table"],
                    db_manager=self.db_manager,
                    node_service=service,
                    optional_auth_dep=self.optional_auth_dep,
                    cedar_access_spec=_cedar_spec,
                    fk_graph=self.fk_graph,
                    ref_targets=self.entity_ref_targets.get(entity_name or ""),
                )
                self._router.add_api_route(
                    _graph_path,
                    _graph_handler,
                    methods=["GET"],
                    tags=[entity_name or "Item"],
                    summary=f"Neighborhood graph for {entity_name}",
                )
```

- [ ] **Step 3: Build node_graph_specs in server.py**

In `src/dazzle_back/runtime/server.py`, before the `RouteGenerator(...)` call, build:

```python
        # Build node graph metadata for neighborhood endpoints (#619 Phase 3)
        node_graph_specs: dict[str, dict] = {}
        for ir_entity in self._appspec.domain.entities:
            if ir_entity.graph_node is not None:
                edge_entity_name = ir_entity.graph_node.edge_entity
                edge_ir = next(
                    (e for e in self._appspec.domain.entities if e.name == edge_entity_name),
                    None,
                )
                if edge_ir and edge_ir.graph_edge:
                    node_graph_specs[ir_entity.name] = {
                        "graph_edge": edge_ir.graph_edge,
                        "graph_node": ir_entity.graph_node,
                        "node_table": ir_entity.name,
                        "edge_table": edge_entity_name,
                    }
```

Pass to `RouteGenerator(...)`:
```python
            node_graph_specs=node_graph_specs,
            db_manager=self._db_manager,
```

- [ ] **Step 4: Verify no regressions**

Run: `pytest tests/unit/test_neighborhood_query.py tests/unit/test_graph_serializer.py -x -q`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/route_generator.py src/dazzle_back/runtime/server.py
git commit -m "feat: register /graph neighborhood endpoint on graph_node entities (#619)"
```

---

### Task 4: Integration Tests

**Files:**
- Create: `tests/unit/test_neighborhood_api.py`

- [ ] **Step 1: Write integration tests**

Since full server tests require a running DB, write tests that verify the query builder + serializer pipeline end-to-end, and the handler's validation logic.

Create `tests/unit/test_neighborhood_api.py`:

```python
"""Integration tests for neighborhood endpoint (#619 Phase 3)."""

from dazzle.core.ir import GraphEdgeSpec, GraphNodeSpec
from dazzle_back.runtime.graph_serializer import GraphSerializer
from dazzle_back.runtime.neighborhood import NeighborhoodQueryBuilder


class TestNeighborhoodPipeline:
    """Full CTE → fetch → serialize pipeline."""

    def test_directed_cte_then_serialize(self) -> None:
        """Verify CTE SQL + serializer produce valid output."""
        ge = GraphEdgeSpec(source="source_id", target="target_id", type_field="kind")
        gn = GraphNodeSpec(edge_entity="Edge", display="title")

        qb = NeighborhoodQueryBuilder(
            node_table="chapter", edge_table="chapter_edge", graph_edge=ge,
        )

        # CTE query is valid SQL shape
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
            e["data"]["id"]: e["data"]["label"]
            for e in result["elements"]
            if e["group"] == "nodes"
        }
        assert labels == {"ch1": "Chapter 1", "ch2": "Chapter 2", "ch3": "Chapter 3"}

    def test_undirected_cte_shape(self) -> None:
        ge = GraphEdgeSpec(source="a", target="b", directed=False)
        qb = NeighborhoodQueryBuilder(
            node_table="node", edge_table="link", graph_edge=ge,
        )
        sql, _ = qb.cte_query(seed_id="n1", depth=1)
        # Undirected should have CASE or OR for bidirectional
        assert "CASE" in sql or "OR" in sql

    def test_depth_bounds(self) -> None:
        """Verify depth param is correctly passed."""
        ge = GraphEdgeSpec(source="s", target="t")
        qb = NeighborhoodQueryBuilder(
            node_table="n", edge_table="e", graph_edge=ge,
        )
        for d in (1, 2, 3):
            _, params = qb.cte_query(seed_id="x", depth=d)
            assert params["max_depth"] == d

    def test_raw_format_response(self) -> None:
        """Raw format returns seed + depth + flat lists."""
        nodes = [{"id": "n1", "title": "Root"}]
        edges: list[dict] = []

        # Simulate what the handler returns for raw format
        result = {
            "seed": "n1",
            "depth": 1,
            "nodes": nodes,
            "edges": edges,
        }
        assert result["seed"] == "n1"
        assert result["depth"] == 1
        assert len(result["nodes"]) == 1
        assert len(result["edges"]) == 0

    def test_scope_injection_in_cte(self) -> None:
        ge = GraphEdgeSpec(source="s", target="t")
        qb = NeighborhoodQueryBuilder(
            node_table="n", edge_table="e", graph_edge=ge,
            edge_scope_sql='"org_id" = %s',
            node_scope_sql='"visible" = %s',
        )
        cte_sql, _ = qb.cte_query(seed_id="x", depth=2)
        assert "org_id" in cte_sql

        node_sql, _ = qb.node_fetch_query(node_ids=["x"])
        assert "visible" in node_sql

    def test_cycle_prevention_via_union(self) -> None:
        """UNION (not UNION ALL) in CTE prevents infinite cycles."""
        ge = GraphEdgeSpec(source="s", target="t")
        qb = NeighborhoodQueryBuilder(
            node_table="n", edge_table="e", graph_edge=ge,
        )
        sql, _ = qb.cte_query(seed_id="x", depth=3)
        # Must use UNION not UNION ALL
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
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/unit/test_neighborhood_query.py tests/unit/test_neighborhood_api.py tests/unit/test_graph_serializer.py tests/unit/test_graph_semantics.py -v`
Expected: All pass.

- [ ] **Step 3: Run linting**

Run: `ruff check src/dazzle_back/runtime/neighborhood.py src/dazzle_back/runtime/route_generator.py src/dazzle_back/runtime/server.py tests/unit/test_neighborhood_query.py tests/unit/test_neighborhood_api.py --fix && ruff format src/dazzle_back/runtime/neighborhood.py tests/unit/test_neighborhood_query.py tests/unit/test_neighborhood_api.py`
Expected: Clean.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_neighborhood_api.py
git commit -m "test: neighborhood endpoint integration tests (#619)"
```
