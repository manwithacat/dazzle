# Graph Features

Dazzle has first-class support for property graphs — data models where entities form nodes and their relationships form edges. Graph semantics are declared directly in the DSL, and the runtime exposes traversal, algorithm, and visualization endpoints automatically.

There are two distinct graph systems in Dazzle:

- **DSL property graphs** — your application data as a graph (e.g. social networks, knowledge graphs, org charts). Declared with `graph_edge:` and `graph_node:` on entities. The runtime generates REST endpoints for traversal and algorithms.
- **Knowledge Graph (MCP)** — a framework-level graph that indexes your DSL artefacts (entities, surfaces, stories, personas, workspaces) and framework concepts. Queried via the `graph` MCP tool by agents working on your project.

## DSL Property Graphs

### Declaring an edge entity

Any entity can become a graph edge by adding a `graph_edge:` block. The entity must have two `ref` fields — one pointing to the source node and one to the target node.

```dsl
entity Friendship "Friendship":
  id: uuid pk
  from_person: ref Person required
  to_person: ref Person required
  since: date optional
  strength: int optional

  graph_edge:
    source: from_person
    target: to_person
    weight: strength
    directed: false
```

The `graph_edge:` block tells the runtime that rows in this table are edges in a graph. The runtime then generates graph-aware API endpoints for any node entity that references this edge entity.

#### `graph_edge:` properties

| Property | Required | Default | Description |
|----------|----------|---------|-------------|
| `source` | yes | — | ref field on this entity pointing to the source node |
| `target` | yes | — | ref field on this entity pointing to the target node |
| `type` | no | — | enum or str field used as an edge type discriminator |
| `weight` | no | — | numeric field (int, decimal, or float) used as edge weight in algorithm endpoints |
| `directed` | no | `true` | whether edges have direction; `false` creates an undirected graph |
| `acyclic` | no | `false` | advisory — documented intent; not enforced at the database level |

### Annotating a node entity

Add `graph_node:` to an entity to declare it as a node in a graph. This is optional but recommended — it tells the runtime which edge entity connects nodes of this type, and unlocks the `/graph` neighborhood endpoint.

```dsl
entity Person "Person":
  id: uuid pk
  name: str(100) required
  bio: text optional

  graph_node:
    edges: Friendship
    display: name
```

#### `graph_node:` properties

| Property | Required | Default | Description |
|----------|----------|---------|-------------|
| `edges` | yes | — | the edge entity (must declare `graph_edge:`) |
| `display` | no | — | field used as the node label in visualization formats |

### Heterogeneous graphs

An edge entity can connect nodes of different types. The validator will emit a warning so you know the graph is heterogeneous, but this is fully supported.

```dsl
entity ContentLink "Content Link":
  id: uuid pk
  source_article: ref Article required
  target_topic: ref Topic required
  relevance: decimal(3,2) optional

  graph_edge:
    source: source_article
    target: target_topic
    weight: relevance
    directed: true
```

### Edge type discrimination

Use an enum field as the `type` discriminator when your graph has multiple kinds of edges:

```dsl
entity DocumentEdge "Document Edge":
  id: uuid pk
  from_doc: ref Document required
  to_doc: ref Document required
  kind: enum[references,extends,supersedes,related] required
  created_at: datetime

  graph_edge:
    source: from_doc
    target: to_doc
    type: kind
    directed: true
```

The serializer includes a `type` field on each edge in the API response, which Cytoscape.js and D3 consumers can use for edge styling.

### Validation

Run `dazzle validate` after adding graph declarations. Errors that will be reported:

- `source` or `target` field does not exist on the entity
- `source` or `target` field is not a `ref` type
- `type` field does not exist on the entity
- `weight` field does not exist or is not numeric (int, decimal, or float)
- `graph_node: edges` references an entity that does not declare `graph_edge:`
- `graph_node: display` references a field that does not exist

Warnings (non-fatal):

- Heterogeneous graph: source and target ref different entity types
- Edge entity has no access control
- `acyclic: true` — cycles are only detectable in seed data, not enforced at the DB level

The linter (`dazzle lint`) will also suggest adding `graph_edge:` to entities with two or more ref fields pointing to the same entity, and suggest `graph_node:` on entities targeted by edge declarations.

---

## Runtime API Endpoints

When a node entity has `graph_node:`, the runtime registers additional HTTP endpoints alongside the standard CRUD routes. Paths follow the same pattern as the entity's list route (e.g. if your `Person` entity is served at `/persons`, the graph endpoint is at `/persons/{id}/graph`).

### Neighborhood traversal

```
GET /{entity-path}/{id}/graph?depth=1&format=cytoscape
```

Returns all nodes and edges reachable from the given node within `depth` hops. The seed node is always included even if it has no connections.

**Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `depth` | `1` | Hops to traverse (1–3) |
| `format` | `cytoscape` | Response format: `cytoscape`, `d3`, or `raw` |

The neighborhood query uses a PostgreSQL `WITH RECURSIVE` CTE. For directed graphs, traversal follows edge direction (source → target). For undirected graphs, traversal follows either direction.

**Cytoscape.js format** (`format=cytoscape`):

```json
{
  "elements": [
    {"group": "nodes", "data": {"id": "abc", "label": "Alice", "name": "Alice"}},
    {"group": "nodes", "data": {"id": "def", "label": "Bob", "name": "Bob"}},
    {"group": "edges", "data": {"source": "abc", "target": "def", "strength": 5}}
  ],
  "stats": {"nodes": 2, "edges": 1}
}
```

**D3 force-graph format** (`format=d3`):

```json
{
  "nodes": [{"id": "abc", "label": "Alice"}, {"id": "def", "label": "Bob"}],
  "links": [{"source": "abc", "target": "def", "strength": 5}]
}
```

**Raw format** (`format=raw`): returns `{"nodes": [...], "edges": [...]}` with unmodified DB row dicts.

### Shortest path

Requires the `networkx` optional dependency (`pip install dazzle-dsl[graph]`).

```
GET /{entity-path}/{id}/graph/shortest-path?to={target_id}&weighted=false&format=cytoscape
```

Finds the shortest path between two nodes. Returns the nodes and edges that form the path, plus a `shortest_path` summary object.

**Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `to` | required | Target node UUID |
| `weighted` | `false` | If `true`, uses the `weight` field on edges (requires `weight` in `graph_edge:`) |
| `format` | `cytoscape` | Response format: `cytoscape`, `d3`, or `raw` |

**Example response** (`format=raw`):

```json
{
  "path": ["abc", "xyz", "def"],
  "length": 2,
  "weight": 12.5
}
```

When no path exists, `path` is `[]` and `length` is `null`.

### Connected components

```
GET /{entity-path}/graph/components?format=raw
```

Partitions all nodes into connected groups. Useful for detecting isolated subgraphs — users, documents, or topics with no links to the rest of the graph.

For directed graphs, uses weak connectivity (ignores edge direction when determining components).

**Example response:**

```json
{
  "count": 3,
  "components": [
    ["abc", "def", "xyz"],
    ["ghi"],
    ["jkl", "mno"]
  ]
}
```

Components are returned sorted by size, largest first.

### List with graph format

The standard list endpoint also accepts a `format` parameter on edge entities:

```
GET /{edge-entity-path}?format=cytoscape
GET /{edge-entity-path}?format=d3
```

This returns all edges as a graph payload, useful for rendering the full graph without starting from a specific seed node.

---

## Domain-Scoped Graphs

Graph endpoints respect the entity's `filter_fields` configuration. You can scope a graph query to a specific domain partition by passing filter parameters:

```
GET /persons/{id}/graph?school_id=abc123&depth=2&format=cytoscape
```

The filter is applied to the edge table's WHERE clause before traversal begins. Only edges matching the filter are included, and only reachable nodes through those edges appear in the result.

This means each tenant or domain context gets an isolated view of the graph — a school sees only connections within its own data, even on a shared edge table.

---

## Graph MCP Tool

The `graph` MCP tool operates on the **Knowledge Graph** — the framework-level graph that indexes your project's DSL artefacts. It is separate from the runtime property graph API described above.

The knowledge graph is populated automatically when the MCP server starts. It contains nodes for every entity, surface, story, process, persona, workspace, and service in your DSL, plus framework concepts seeded from the Dazzle knowledge base.

### Operations

#### `query` — search for nodes

Search the graph by text. Matches against node names and metadata.

```json
{"operation": "query", "text": "invoice", "entity_types": ["dsl_entity"], "limit": 10}
```

`entity_types` filter accepts: `dsl_entity`, `dsl_surface`, `dsl_story`, `dsl_process`, `dsl_persona`, `dsl_workspace`, `concept`, `inference`.

#### `neighbourhood` — explore around a node

Get all nodes within N hops of a starting node.

```json
{"operation": "neighbourhood", "entity_id": "entity:Invoice", "depth": 2}
```

Entity IDs use prefixed notation: `entity:Name`, `surface:name`, `persona:name`, `workspace:name`, `story:name`.

`depth` defaults to 1. Relation types can be filtered with `relation_types` (e.g. `["uses", "acts_as"]`).

#### `dependencies` — what does X depend on?

```json
{"operation": "dependencies", "entity_id": "surface:invoice_list", "transitive": false}
```

Returns nodes that `entity_id` has outgoing relations to. Set `transitive: true` for full transitive closure (up to 5 hops by default).

#### `dependents` — what depends on X?

```json
{"operation": "dependents", "entity_id": "entity:Invoice", "transitive": true}
```

Returns nodes with incoming relations pointing to `entity_id`.

#### `paths` — find a route between two nodes

```json
{"operation": "paths", "source_id": "persona:accountant", "target_id": "entity:Payment"}
```

Returns up to 10 shortest paths. Each path includes the node ID sequence and the relation type sequence. Uses a recursive CTE — paths are capped at 5 hops by default.

#### `concept` — look up a framework concept

```json
{"operation": "concept", "name": "state_machine"}
```

Looks up a seeded framework concept by name or alias. Returns the concept's type, metadata, and canonical ID.

#### `inference` — find patterns matching a description

```json
{"operation": "inference", "text": "user uploads a file", "limit": 5}
```

Finds inference pattern entries whose trigger phrases match the query text. Used by agents to discover what DSL constructs are applicable in a given situation.

#### `topology` — derive project structure

```json
{"operation": "topology"}
```

Returns the project topology derived from the current DSL: entity reference graph, surface-to-entity mapping, workspace composition, and dead construct detection (entities with no surfaces, entities with surfaces but no workspace).

To focus on a single entity:

```json
{"operation": "topology", "entity": "Invoice"}
```

Returns what surfaces show it, which workspaces include it, and which other entities reference it.

#### `triggers` — show what fires on an entity event

```json
{"operation": "triggers", "entity": "Order", "event": "created"}
```

Returns all LLM intents and processes that are triggered when the named entity event fires. Useful for understanding the automation chain attached to an event. `event` accepts `created`, `updated`, or `deleted`.

#### `export` / `import` — snapshot and restore

```json
{"operation": "export"}
```

Returns the full project-specific KG data (not the seeded framework knowledge) as a JSON object. Use this to snapshot and restore KG state across environments.

```json
{"operation": "import", "data": {...}, "mode": "merge"}
```

Loads KG data from a JSON object. `mode` is `merge` (additive upsert, the default) or `replace` (wipe project data and load fresh).

You can also pass `file_path` instead of `data` to import from a file.

#### `stats` — graph summary

```json
{"operation": "stats"}
```

Returns total entity count, relation count, and breakdowns by entity type and relation type. Useful for understanding what the KG contains.

#### `populate` — refresh from source

```json
{"operation": "populate", "root_path": "/path/to/project"}
```

Re-indexes the project from the DSL files on disk. Normally called automatically on MCP startup and project selection. Call manually if you have made changes that have not been picked up.

### Entity ID format

KG entity IDs use a prefix convention:

| Prefix | Example |
|--------|---------|
| `entity:` | `entity:Invoice` |
| `surface:` | `surface:invoice_list` |
| `persona:` | `persona:accountant` |
| `workspace:` | `workspace:finance` |
| `story:` | `story:record_payment` |
| `process:` | `process:payment_approval` |
| `concept:` | `concept:state_machine` |
| `inference:` | `inference:file_upload` |

### Relation types

The built-in DSL relation types:

| Type | Meaning |
|------|---------|
| `uses` | Surface or workspace uses an entity |
| `acts_as` | Story actor is a persona |
| `scopes` | Story scopes to an entity |
| `process_implements` | Process implements a story |
| `invokes` | Process step invokes a service |
| `has_subprocess` | Process step starts a subprocess |
| `human_task_on` | Process step presents a surface |
| `navigates_to` | Experience step navigates to a surface |
| `allows_persona` | Workspace or surface allows a persona |
| `denies_persona` | Workspace or surface denies a persona |
| `default_workspace` | A persona's default workspace |
| `region_source` | Workspace region is sourced from an entity |
| `related_concept` | Framework concept relates to another concept |
| `suggests_for` | Inference entry suggests for a concept |

---

## Installation

NetworkX is an optional dependency required for the shortest-path and connected-components endpoints:

```bash
pip install dazzle-dsl[graph]
```

Without it, the neighborhood endpoint and list-with-format still work. The algorithm endpoints (`/graph/shortest-path`, `/graph/components`) return 501 if NetworkX is not installed.

---

## Complete example

A social graph where people follow each other, with mutual-follow edges weighted by interaction count:

```dsl
entity Follow "Follow":
  id: uuid pk
  follower: ref Person required
  followed: ref Person required
  interaction_count: int optional

  graph_edge:
    source: follower
    target: followed
    weight: interaction_count
    directed: true

entity Person "Person":
  id: uuid pk
  username: str(50) required
  display_name: str(100) optional

  graph_node:
    edges: Follow
    display: display_name
```

This generates (assuming `Person` is served at `/persons` and `Follow` at `/follows`):

- `GET /persons/{id}/graph?depth=2&format=cytoscape` — who does this person follow, and who do those people follow?
- `GET /persons/{id}/graph/shortest-path?to={other_id}&weighted=true` — weighted shortest social path between two people
- `GET /persons/graph/components` — isolated clusters in the social graph
- `GET /follows?format=d3` — the full follow graph for force-directed rendering
