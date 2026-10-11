# Graph Semantics in Dazzle DSL — Design Spec

**Date:** 2026-03-22
**Status:** Draft
**Issue:** #619
**Scope:** Formal graph model declarations in the DSL, graph-shaped API serialization, neighborhood queries

## Problem

Dazzle's DSL captures entity relationships via `ref` and `has_many` fields, but has no way to declare that a set of entities forms a graph. Projects like Penny Dreadful hand-write ~500 lines of graph API code (Cytoscape.js serialization, neighborhood queries, compound mutations) that the framework could generate if it knew which entities are nodes and which are edges.

The gap isn't in domain modeling — the DSL already captures the full domain. It's in formal semantics: the framework can't distinguish "Order has many LineItems" (hierarchy) from "Node has many NodeEdge" (graph) without an explicit declaration.

## Decision: Backend Graph Semantics, Not Frontend Graph Rendering

Graph declarations are a **backend/DSL concern**. The framework:
- Parses and validates graph structure at `dazzle validate` time
- Generates graph-shaped API responses (`?format=cytoscape|d3|raw`)
- Provides neighborhood query endpoints

The framework does **not** render graph UIs. Frontend visualization is left to users via the existing JS island pattern (`data-island`). Users choose their own graph library (Cytoscape.js, D3, Vis.js, etc.) and mount it as an island consuming the graph API.

## Graph Model

Dazzle adopts **directed property multigraphs** as the formal model, aligning with the industry standard used by Neo4j, Memgraph, AWS Neptune, and NetworkX.

| Property | Definition |
|----------|-----------|
| **Nodes** | Entities — carry typed properties (fields), identity (pk), access control (permit/scope) |
| **Edges** | Entities with a `graph_edge:` declaration — carry source/target refs, optional type discriminator, and their own properties |
| **Directed** | Edges have a source and target. Undirected semantics modeled as bidirectional pairs. |
| **Multi** | Multiple edges between the same node pair are allowed, distinguished by type or identity |
| **Property** | Both nodes and edges carry arbitrary typed fields — this maps naturally to the existing entity field system |

Storage is unchanged: nodes are tables, edges are junction tables with two FK columns. The `graph_edge:` declaration is a formal annotation layer on top of existing entities.

Graph declarations are **optional and additive**. An entity with `ref` fields works exactly as it does today. Adding `graph_edge:` declares formal graph semantics without changing storage or CRUD behavior. This mirrors how `permit:` and `scope:` are optional — you don't need them for an app to work, but when you add them, the framework does more for you.

## DSL Syntax

### Edge Entity (the core declaration)

```dsl
entity NodeEdge "Edge":
  id: uuid pk
  source_node: ref Node required
  target_node: ref Node required
  relationship: enum[sequel,fork,reference,adaptation]
  weight: int optional
  created_at: datetime auto_add

  graph_edge:
    source: source_node          # required: which ref field is the source
    target: target_node          # required: which ref field is the target
    type: relationship           # optional: field that discriminates edge types
    weight: importance           # optional: numeric field for weighted algorithms
    directed: true               # optional: default true
    acyclic: false               # optional: default false (true = DAG enforcement)
```

### Node Entity (optional annotation)

```dsl
entity Node "Node":
  id: uuid pk
  title: str(200) required
  content: text

  graph_node:
    edges: NodeEdge              # which edge entity connects these nodes
    display: title               # which field to use as the node label
```

### Field Reference

**`graph_edge:` fields:**

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `source` | yes | — | Name of a `ref` field on this entity — the edge's origin node |
| `target` | yes | — | Name of a `ref` field on this entity — the edge's destination node |
| `type` | no | — | Name of a field (typically `enum`) that discriminates edge types |
| `weight` | no | — | Name of a numeric field (`int`, `decimal`) for weighted graph algorithms |
| `directed` | no | `true` | Whether the edge is directed. `false` means bidirectional traversal. |
| `acyclic` | no | `false` | When `true`, the validator checks for potential cycles. Useful for DAGs. |

**`graph_node:` fields:**

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `edges` | yes | — | Name of the edge entity that connects these nodes |
| `display` | no | standard fallback chain | Field to use as the node label in graph serialization |

### Heterogeneous Graphs

Source and target can reference different entity types:

```dsl
entity AuthorWork "Author-Work Link":
  author: ref Author required
  work: ref Work required
  role: enum[creator,editor,contributor]

  graph_edge:
    source: author
    target: work
    type: role
```

This creates a bipartite graph — authors and works as different node types, connected by typed edges.

## Validation Rules

### Hard Errors (block app startup)

| Rule | Error message |
|------|---------------|
| `source:` or `target:` missing on `graph_edge:` | `graph_edge: requires both source and target fields` |
| `source:` / `target:` field doesn't exist on entity | `graph_edge source 'x' is not a field on EntityName` |
| `source:` / `target:` field isn't a `ref` type | `graph_edge source must be a ref field, got 'str'` |
| `weight:` field doesn't exist | `graph_edge weight 'x' is not a field on EntityName` |
| `weight:` field isn't numeric | `graph_edge weight must be int or decimal` |
| `type:` field doesn't exist | `graph_edge type 'x' is not a field on EntityName` |
| `graph_node: edges:` references non-existent entity | `graph_node edges 'X' is not a defined entity` |
| `graph_node: edges:` entity has no `graph_edge:` block | `graph_node edges 'X' does not declare graph_edge:` |

### Warnings (non-blocking, advisory)

| Rule | Warning |
|------|---------|
| Source/target ref different entity types | `Heterogeneous graph: source refs Node, target refs Work` |
| `acyclic: true` with no runtime enforcement | `acyclic declared but cycles only detected in seed data` |
| Edge entity has no `permit:` block | `Edge entity 'X' has no access control` |
| `graph_node:` without `display:` | `graph_node has no display field — labels use default fallback` |

### Lint Hints (suggestions for agents)

| Pattern | Suggestion |
|---------|------------|
| Entity has 2+ `ref` fields to same entity, no `graph_edge:` | `Entity 'X' looks like a graph edge — consider adding graph_edge:` |
| `graph_edge:` exists but target entity has no `graph_node:` | `'EdgeEntity' targets 'Node' — consider adding graph_node: for discoverability` |

## IR Types

```python
class GraphEdgeSpec(BaseModel):
    """Formal graph edge declaration on an entity."""
    source: str                      # field name (must be ref type)
    target: str                      # field name (must be ref type)
    type_field: str | None = None    # optional edge type discriminator
    weight_field: str | None = None  # optional weight for algorithms
    directed: bool = True
    acyclic: bool = False
    model_config = ConfigDict(frozen=True)

class GraphNodeSpec(BaseModel):
    """Optional graph node annotation on an entity."""
    edge_entity: str                 # name of the edge entity
    display: str | None = None       # field for node labels
    model_config = ConfigDict(frozen=True)
```

Attached to `EntitySpec` as optional fields:
```python
class EntitySpec(BaseModel):
    ...
    graph_edge: GraphEdgeSpec | None = None
    graph_node: GraphNodeSpec | None = None
```

## Backend API

### Graph Serialization (`?format=` parameter)

Any list endpoint for an entity with `graph_edge:` gains a `format` query parameter:

```
GET /nodeedges?format=cytoscape    → Cytoscape.js JSON
GET /nodeedges?format=d3           → D3 force-graph JSON
GET /nodeedges?format=raw          → Standard flat array (default)
```

**Cytoscape format:**
```json
{
  "elements": [
    { "group": "nodes", "data": { "id": "uuid-1", "label": "Chapter 1", "status": "draft" } },
    { "group": "edges", "data": { "id": "edge-1", "source": "uuid-1", "target": "uuid-2", "type": "sequel" } }
  ],
  "stats": { "nodes": 15, "edges": 14 }
}
```

**D3 format:**
```json
{
  "nodes": [{ "id": "uuid-1", "label": "Chapter 1", "group": "draft" }],
  "links": [{ "source": "uuid-1", "target": "uuid-2", "type": "sequel" }]
}
```

The serializer reads `graph_edge:` metadata at startup to map fields to the format's expected shape. Scope and permit rules apply — the serializer only includes nodes/edges the requesting user is authorized to see.

### Neighborhood Endpoint

```
GET /nodes/{id}/graph?depth=1&format=cytoscape
```

Returns the node + all edges + connected nodes within N hops. Bounded by `depth` parameter (max 3 by default, configurable). Scope and permit rules apply to every node and edge in the result.

### What Stays the Same

- CRUD endpoints unchanged — `POST /nodeedges` still creates an edge as a normal entity
- Scope/permit enforcement unchanged — graph endpoints inherit the entity's access rules
- Pagination unchanged — `?page=1&page_size=50` works on graph endpoints

### What's New

| Component | Description |
|-----------|-------------|
| `GraphSerializer` | Runtime class: transforms flat entity lists into Cytoscape/D3 JSON |
| `_build_neighborhood_query` | Recursive FK join query bounded by depth |
| `format` parameter | Registered on list handlers when entity has graph metadata |

## Knowledge Base Integration

New runtime contract entry in `semantics_kb/runtime.toml`:

```toml
[concepts.graph_semantics]
category = "Runtime Contract"
definition = "Formal graph declarations on entities..."
implemented_by = [
    {fn = "GraphSerializer.to_cytoscape", purpose = "..."},
    {fn = "GraphSerializer.to_d3", purpose = "..."},
]
```

New inference trigger: when the KB detects an entity with 2+ ref fields to the same target, suggest `graph_edge:`.

## Phased Delivery

| Phase | Scope | Value |
|-------|-------|-------|
| **Phase 1** | Parser + IR + Validator | DSL can express graphs. `dazzle validate` checks correctness. Lint suggests graph patterns. No runtime changes. |
| **Phase 2** | Graph serializer + `?format=` | API endpoints serve Cytoscape/D3 JSON. Penny Dreadful deletes 500 lines of hand-written code. |
| **Phase 3** | Neighborhood endpoint | `GET /nodes/{id}/graph?depth=N` with scoped traversal. |
| **Phase 4** (future) | Graph algorithms | Shortest path, connected components, PageRank via optional NetworkX integration. |

Phase 1 is pure DSL — no runtime risk. Phase 2 is the payoff. Phase 3 is the power feature. Phase 4 is aspirational.

## References

- [Property graph — Wikipedia](https://en.wikipedia.org/wiki/Property_graph)
- [NetworkX Graph Types](https://networkx.org/documentation/stable/reference/classes/index.html)
- [Neo4j Graph Data Modeling](https://neo4j.com/docs/getting-started/data-modeling/tutorial-data-modeling/)
- [GraphQL is Not a Graph Database — Apollo](https://www.apollographql.com/blog/what-is-a-graph-database-why-graphql-is-not-a-graph-database)
- [AWS Graph Data Modelling](https://aws-samples.github.io/aws-dbs-refarch-graph/src/graph-data-modelling/)
