# Neighborhood Endpoint (Phase 3) — Design Spec

**Date:** 2026-03-22
**Status:** Draft
**Issue:** #619
**Depends on:** Phase 1 (parser + IR), Phase 2 (graph serializer) — shipped in v0.45.3
**Scope:** `GET /{nodes}/{id}/graph?depth=N&format=cytoscape|d3` — scoped neighborhood traversal via recursive CTE

## Problem

Phase 2 serves graph-shaped responses from edge entity list endpoints, but there's no way to ask "show me everything connected to this node within N hops." Users must manually fetch edges, extract IDs, and re-fetch — the exact multi-round-trip pattern the framework should eliminate.

## Decision: Recursive CTE on PostgreSQL

Neighborhood traversal uses a PostgreSQL recursive CTE, built deterministically from the DSL's `graph_edge:` and `graph_node:` declarations. The CTE:

- Traverses the graph in a single query (vs. N round-trips for iterative fetch)
- Handles cycle detection automatically via `UNION` (deduplicates visited nodes)
- Injects scope predicates into the CTE's WHERE clauses (same predicate algebra used by list endpoints)
- Respects `directed: true|false` from the `graph_edge:` spec

SQLite fallback: iterative fetch using existing `CRUDService.execute()`. Same interface, slower for high fan-out graphs.

## Endpoint

```
GET /{nodes}/{id}/graph?depth=1&format=cytoscape
```

- Registered on **node** entities that have `graph_node:` (via `graph_node.edge_entity`)
- Not registered on edge entities (those use Phase 2's `?format=` parameter)
- Path uses the node entity's existing URL slug (e.g., `/nodes/{id}/graph`)

### Parameters

| Param | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `depth` | int | 1 | 1–3 (hard cap) | Number of hops from seed node |
| `format` | string | `cytoscape` | `cytoscape\|d3\|raw` | Response format |

### Response

Same shapes as Phase 2 (`GraphSerializer.to_cytoscape()` / `.to_d3()`). The seed node is always included. Stats reflect the visible neighborhood subset.

`?format=raw` returns:
```json
{
  "seed": "uuid-1",
  "depth": 2,
  "nodes": [{ ...node_fields }],
  "edges": [{ ...edge_fields }]
}
```

## Traversal Query (Recursive CTE)

Built deterministically from the DSL at route generation time.

### Directed graph (`directed: true`)

```sql
WITH RECURSIVE neighborhood(node_id, depth) AS (
    -- Base: seed node
    SELECT :seed_id, 0
    UNION
    -- Follow source → target direction only
    SELECT e.target_node_id, n.depth + 1
    FROM neighborhood n
    JOIN node_edge e ON e.source_node_id = n.node_id
    WHERE n.depth < :max_depth
      AND e.target_node_id IS NOT NULL
      -- scope predicates on edge table injected here
)
SELECT DISTINCT node_id FROM neighborhood;
```

### Undirected graph (`directed: false`)

```sql
WITH RECURSIVE neighborhood(node_id, depth) AS (
    SELECT :seed_id, 0
    UNION
    -- Follow both directions
    SELECT CASE
        WHEN e.source_node_id = n.node_id THEN e.target_node_id
        ELSE e.source_node_id
    END, n.depth + 1
    FROM neighborhood n
    JOIN node_edge e ON e.source_node_id = n.node_id OR e.target_node_id = n.node_id
    WHERE n.depth < :max_depth
      -- scope predicates on edge table injected here
)
SELECT DISTINCT node_id FROM neighborhood;
```

### Execution flow

1. **CTE query** → set of reachable node IDs (scoped)
2. **Node fetch** → `SELECT * FROM node_table WHERE id IN (:node_ids)` + node scope predicates
3. **Edge fetch** → `SELECT * FROM edge_table WHERE source IN (:node_ids) AND target IN (:node_ids)` + edge scope predicates
4. **Serialize** → `GraphSerializer.to_cytoscape()` or `.to_d3()`

Three queries total. The heavy traversal is the CTE; the other two are simple IN-clause fetches.

### Scope predicate injection

Scope predicates are compiled from the predicate algebra (same system used by list endpoints). They're injected as additional WHERE clauses:

- **Edge scope** → added to the CTE's recursive step (filters which edges can be traversed)
- **Node scope** → added to the node fetch query (filters which nodes are visible in results)

If a node is reachable via the CTE but hidden by node scope, it's excluded from the response. Edges connecting to hidden nodes are also excluded (unlike Phase 2 where edges to hidden nodes are kept — neighborhood queries should show a consistent subgraph).

## Components

### NeighborhoodQueryBuilder

`src/dazzle_back/runtime/neighborhood.py` — pure SQL generation, no execution.

```python
class NeighborhoodQueryBuilder:
    def __init__(
        self,
        node_table: str,
        edge_table: str,
        graph_edge: GraphEdgeSpec,
        node_pk: str = "id",
        edge_scope_sql: str | None = None,
        node_scope_sql: str | None = None,
    ): ...

    def cte_query(self, seed_id: str, depth: int) -> tuple[str, dict]:
        """Return (SQL, params) for the recursive CTE."""
        ...

    def node_fetch_query(self, node_ids: list[str]) -> tuple[str, dict]:
        """Return (SQL, params) to fetch full node records."""
        ...

    def edge_fetch_query(self, node_ids: list[str]) -> tuple[str, dict]:
        """Return (SQL, params) to fetch edges between discovered nodes."""
        ...
```

### Route registration

In `RouteGenerator`, when generating routes for a node entity with `graph_node:`:

- Register `GET /{slug}/{id}/graph` as a new endpoint
- The handler:
  1. Validates `depth` and `format` params
  2. Checks seed node exists (404 if not, respecting scope)
  3. Builds and executes the CTE via `NeighborhoodQueryBuilder`
  4. Fetches full node and edge records
  5. Serializes via `GraphSerializer`

### SQLite fallback

When the DB backend is SQLite (detected at startup), use iterative fetch instead:

```python
async def _iterative_neighborhood(seed_id, depth, edge_service, ref_targets, all_services):
    visited = {seed_id}
    frontier = {seed_id}
    all_edges = []
    for _ in range(depth):
        # Fetch edges touching frontier nodes
        edges = await edge_service.execute(operation="list", filters={"source__in": list(frontier)})
        # ... extract new node IDs, add to frontier, repeat
    # Fetch all node records
    ...
```

Same interface, same `GraphSerializer` output. Just slower for high fan-out.

## Error Handling

| Condition | Response |
|---|---|
| Seed node not found (or scope-hidden) | 404 `{"detail": "Node not found"}` |
| `depth` < 1 or > 3 | 400 `{"detail": "depth must be between 1 and 3"}` |
| `format` invalid | 400 `{"detail": "Invalid format. Supported: cytoscape, d3, raw"}` |
| Entity has no `graph_node:` | Endpoint not registered — 404 naturally |
| Zero neighbors | Seed node alone in response, empty edges |
| CTE timeout (pathological graph) | 500 with logged warning — PostgreSQL's `statement_timeout` provides the safety net |

## What Stays the Same

- CRUD endpoints unchanged
- Phase 2 `?format=` on edge list endpoints unchanged
- Scope/permit enforcement uses existing predicate algebra
- `GraphSerializer` reused from Phase 2

## Testing

### Unit tests (`NeighborhoodQueryBuilder` — SQL generation)

- Directed CTE includes only source→target join
- Undirected CTE includes bidirectional join
- Depth parameter appears in WHERE clause
- Scope predicate SQL injected correctly
- Node fetch uses IN clause
- Edge fetch constrains both source and target to node set

### Integration tests (with test DB)

- Depth 1: seed + immediate neighbors only
- Depth 2: two-hop traversal includes second-ring nodes
- Depth 3: three-hop traversal
- Self-loop: node with edge to itself
- Directed traversal: only follows source→target
- Undirected traversal: follows both directions
- Cycle detection: A→B→C→A doesn't infinite-loop
- Seed not found → 404
- Invalid depth → 400
- Format parameter works (cytoscape, d3, raw)
- Scope filtering: hidden nodes excluded from neighborhood
- Empty neighborhood: isolated seed node

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle_back/runtime/neighborhood.py` | Create | `NeighborhoodQueryBuilder` — recursive CTE SQL generation |
| `src/dazzle_back/runtime/route_generator.py` | Modify | Register `/{slug}/{id}/graph` endpoint for graph_node entities |
| `src/dazzle_back/runtime/server.py` | Modify | Pass graph metadata for node entities to route generator |
| `tests/unit/test_neighborhood_query.py` | Create | Unit tests for SQL generation |
| `tests/unit/test_neighborhood_api.py` | Create | Integration tests with test DB |
