# Graph Algorithms (Phase 4) — Design Spec

**Date:** 2026-03-22
**Status:** Approved
**Issue:** #619
**Depends on:** Phase 1–3 (parser, serializer, neighborhood endpoint)

## Problem

Phases 1–3 give Dazzle graph declaration, serialization, and traversal. But users building graph-heavy apps (knowledge graphs, dependency trackers, recommendation engines) need computed graph properties: shortest paths, connected components, centrality scores. Today they'd write this in application code or export to a separate graph DB.

## Scope

Optional graph algorithm endpoints, powered by NetworkX, that operate on the graph declared in the DSL. These are read-only computed views — no mutations, no new storage.

## Candidate Algorithms

| Algorithm | Use case | Complexity | NetworkX function |
|-----------|----------|------------|-------------------|
| Shortest path | "How are these two nodes connected?" | O(V + E) | `nx.shortest_path()` |
| Connected components | "Which nodes are isolated?" | O(V + E) | `nx.connected_components()` |
| PageRank | "Which nodes are most important?" | O(V + E × iterations) | `nx.pagerank()` |
| Degree centrality | "Which nodes have the most connections?" | O(V + E) | `nx.degree_centrality()` |
| Topological sort | DAGs only — "What order should these run in?" | O(V + E) | `nx.topological_sort()` |

### YAGNI filter

Start with **shortest path** and **connected components** only. These cover the most common user questions ("how are X and Y related?" and "are there disconnected clusters?"). PageRank and centrality are power features that can be added later if demand materializes. Topological sort only applies when `acyclic: true`.

## Proposed Endpoints

```
GET /{nodes}/{id}/graph/shortest-path?to={target_id}&format=cytoscape
GET /{nodes}/graph/components?format=cytoscape
```

### Shortest path
- Returns the path (ordered list of nodes + connecting edges) between two nodes
- Uses `graph_edge.weight_field` for weighted shortest path if available (Dijkstra), unweighted BFS otherwise
- Respects scope — only traverses visible edges/nodes
- 404 if either node not found, 200 with empty path if no path exists

### Connected components
- Returns all components as separate subgraphs
- Each component is a list of node IDs
- Useful for detecting orphaned data or isolated clusters
- Response includes component sizes for quick triage

## Architecture

### Graph materialization

The algorithms need an in-memory NetworkX graph. Two approaches:

**A) On-demand materialization (recommended for v1):**
- When an algorithm endpoint is hit, load the full graph into memory (all nodes + edges, scoped)
- Build a `nx.DiGraph()` or `nx.Graph()` depending on `directed`
- Run the algorithm
- Discard the graph after the response

Simple, no caching complexity, but O(V + E) per request. Acceptable for graphs under ~100K nodes. For larger graphs, add caching later.

**B) Cached materialization (future):**
- Materialize on first request, cache with TTL
- Invalidate on edge/node mutations via the event system (v0.18.0) — Dazzle already knows when entities change, so cache invalidation is "edge or node entity mutated → drop the cached `nx.Graph`." This is the kind of thing that's hard in general but trivial when the framework owns the full stack from DSL to runtime.
- More complex, needed only for large graphs or frequent algorithm calls

### Dependency

NetworkX would be an optional dependency (`pip install dazzle-dsl[graph]`). Algorithm endpoints only register if NetworkX is importable. No runtime impact for apps that don't use graph algorithms.

```toml
# pyproject.toml
[project.optional-dependencies]
graph = ["networkx>=3.0"]
```

## Scope enforcement

Two layers of scoping:

**Authorization scope** (from `permit:` / `scope:` blocks): Same as Phase 3 — the graph is built from scoped queries. Users only see paths and components within their authorized subset. This means two users may get different shortest paths or different component counts, which is correct behavior.

**Domain scope** (from query filters): Algorithm endpoints accept the same filter parameters as list endpoints (`?filter[work_id]=uuid` or bare `?work_id=uuid` when the field is in the filter list). This is critical for apps where the graph is logically partitioned — e.g., Penny Dreadful where each Work has its own independent node graph. The materialization query includes these filters alongside scope predicates, so the algorithm operates on the correct subgraph.

Both layers compose: authorization scope limits what the user can see, domain filters select which partition to analyze. The materialized `nx.Graph` reflects both.

For cached materialization, the cache key includes the domain filter values — `(entity_name, frozenset(filters))` — so each partition gets its own cached graph.

## Implementation notes

- Start with on-demand materialization (approach A) — no caching
- Penny Dreadful is the first consumer — they need domain-scoped algorithms (per-work graphs)
- NetworkX as optional extra: `pip install dazzle-dsl[graph]`
- Endpoints only register when NetworkX is importable — zero cost for apps that don't use it

## References

- [NetworkX Algorithms](https://networkx.org/documentation/stable/reference/algorithms/index.html)
- [NetworkX Graph Types](https://networkx.org/documentation/stable/reference/classes/index.html)
- Phase 1–3 specs in this directory
