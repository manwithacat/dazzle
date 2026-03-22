# Graph Serializer (Phase 2) — Design Spec

**Date:** 2026-03-22
**Status:** Draft
**Issue:** #619
**Depends on:** Phase 1 (parser + IR + validator) — shipped in v0.45.2
**Scope:** Graph-shaped API responses via `?format=cytoscape|d3` on edge entity list endpoints

## Problem

Phase 1 gave the DSL the ability to declare graph semantics (`graph_edge:`, `graph_node:`), but the runtime doesn't use that metadata yet. Projects like Penny Dreadful hand-write ~500 lines of Cytoscape.js serialization code that the framework could generate automatically.

## Decision: Edge-Centric Serialization

The `?format=` parameter is only supported on list endpoints for entities with `graph_edge:`. The serializer:

1. Takes edge items from the normal paginated list query
2. Extracts unique node IDs from source/target ref fields
3. Batch-fetches those nodes (respecting scope/permit)
4. Assembles into Cytoscape or D3 format

Node entity endpoints are unaffected. `?format=raw` or no format param returns the standard flat list.

## Components

### GraphSerializer

A pure function class in `src/dazzle_back/runtime/graph_serializer.py`. No DB access, no request handling — just data transformation.

**Input:**
- `edges`: list of dicts (edge entity records from the list query)
- `graph_edge`: `GraphEdgeSpec` from the IR (source/target/type_field/weight_field)
- `nodes`: list of dicts (node entity records, batch-fetched)
- `graph_node`: `GraphNodeSpec | None` from the IR (display field)

**Output:** dict in Cytoscape or D3 format.

**Interface:**

```python
class GraphSerializer:
    def __init__(self, graph_edge: GraphEdgeSpec, graph_node: GraphNodeSpec | None = None):
        ...

    def to_cytoscape(self, edges: list[dict], nodes: list[dict]) -> dict:
        ...

    def to_d3(self, edges: list[dict], nodes: list[dict]) -> dict:
        ...
```

### Route Generator Integration

In `_list_handler_body()` in `src/dazzle_back/runtime/route_generator.py`, after the list query returns and before content negotiation:

1. Check `format` query param
2. If `format` is `cytoscape` or `d3` and entity has `graph_edge:`:
   - Extract node IDs from source/target ref fields in returned edges, grouped by target entity type
   - For each target entity type, look up its service and batch-fetch nodes via `service.execute(operation="list", filters={"id__in": node_ids})` with `page_size` set high enough to cover all referenced IDs
   - For **heterogeneous graphs** (source refs `Author`, target refs `Work`), this means two separate fetches — one per entity type. All fetched nodes are merged into a single nodes array.
   - Call `GraphSerializer.to_cytoscape()` or `.to_d3()`
   - Return result directly (bypasses normal content negotiation)
3. If `format` is set but entity has no `graph_edge:`: return 400
4. If `format` is an unrecognized value: return 400

The `graph_edge` and `graph_node` IR specs are passed to `create_list_handler()` at route generation time (read from the IR `EntitySpec`).

**Scope and authorization on node fetch:** Each node entity's fetch uses the requesting user's scope/permit rules. If a user can see an edge but not its target node, the edge still appears in the output (with its source/target IDs), but the node is omitted from the nodes array. This is intentional — filtering edges based on node visibility would leak information about which hidden nodes exist. The graph shows the authorized subset; consumers should handle missing node references gracefully (both Cytoscape.js and D3 do this natively).

## Response Shapes

### Cytoscape (`?format=cytoscape`)

```json
{
  "elements": [
    {
      "group": "nodes",
      "data": { "id": "uuid-1", "label": "Chapter 1", "status": "draft", ...fields }
    },
    {
      "group": "edges",
      "data": { "id": "edge-1", "source": "uuid-1", "target": "uuid-2", "type": "sequel", ...fields }
    }
  ],
  "stats": { "nodes": 15, "edges": 14 }
}
```

### D3 (`?format=d3`)

```json
{
  "nodes": [{ "id": "uuid-1", "label": "Chapter 1", ...fields }],
  "links": [{ "source": "uuid-1", "target": "uuid-2", "type": "sequel", ...fields }]
}
```

### Field Mapping

| Output field | Source |
|-------------|--------|
| Node `id` | Node entity primary key value |
| Node `label` | `graph_node.display` field value, falling back to: `title` → `name` → `label` → `id` |
| Edge `id` | Edge entity primary key value |
| Edge `source` | Value of the field named in `graph_edge.source` |
| Edge `target` | Value of the field named in `graph_edge.target` |
| Edge `type` | Value of the field named in `graph_edge.type_field` (omitted if not set) |
| Edge `weight` | Value of the field named in `graph_edge.weight_field` (omitted if not set) |
| All other fields | Included in the `data` dict as-is |

### Pagination

Graph format responses are paginated by edges. Page 2 returns edges 21–40 and only the nodes referenced by those edges. The `stats` object reflects the visible page, not the full graph. Standard `page` and `page_size` params apply.

## Error Handling

| Condition | Response |
|-----------|----------|
| `?format=foo` (invalid value) | 400 `{"detail": "Invalid format. Supported: cytoscape, d3, raw"}` |
| `?format=cytoscape` on entity without `graph_edge:` | 400 `{"detail": "Entity 'Task' does not declare graph_edge:"}` |
| Node entity service not found | 500 (shouldn't happen with valid DSL) |
| FK orphan (edge refs node that doesn't exist) | Edge appears with node ID; node omitted from nodes array |
| Scope hides a node | Edge appears; node omitted (graph shows only authorized subset) |
| Zero edges | Format structure with empty arrays and `stats: { nodes: 0, edges: 0 }` |

## What Stays the Same

- CRUD endpoints unchanged — `POST /nodeedges` still creates an edge as a normal entity
- Scope/permit enforcement unchanged — node fetch inherits the node entity's access rules
- Pagination unchanged — `?page=1&page_size=50` works on graph endpoints
- No format param → standard flat paginated list (backward compatible)

## Testing

### Unit Tests (GraphSerializer — pure data transformation)

- Cytoscape format output shape
- D3 format output shape
- Label fallback chain (display → title → name → label → id)
- Edge type field mapping (present and absent)
- Weight field inclusion
- Empty input (zero edges, zero nodes)
- Heterogeneous graph (different source/target entity types)
- All entity fields included in data dict

### Integration Tests (route generator)

- `?format=cytoscape` on edge entity returns correct shape
- `?format=d3` on edge entity returns correct shape
- `?format=raw` returns standard paginated list
- `?format=foo` returns 400
- `?format=cytoscape` on non-graph entity returns 400
- No format param returns standard paginated list (backward compat)
- Pagination works with format param

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle_back/runtime/graph_serializer.py` | Create | GraphSerializer class — pure data transformation |
| `src/dazzle_back/runtime/route_generator.py` | Modify | Wire format param, node fetch, serializer call |
| `tests/unit/test_graph_serializer.py` | Create | Unit tests for GraphSerializer |
| `tests/unit/test_graph_api.py` | Create | Integration tests for format param on list endpoints |
