# ADR-0013: Unified Knowledge Graph

**Status:** Accepted
**Date:** 2026-02-07

## Context

Dazzle's MCP layer originally maintained three independent knowledge systems:

1. **Semantic KB** — TOML-backed concept definitions (DSL constructs, patterns, best practices)
2. **Inference KB** — TOML-backed inference rules mapping observations to DSL suggestions
3. **Project KG** — Per-project SQLite graph of entities, surfaces, stories, and their relationships

These three systems evolved independently and accumulated duplication and inconsistency:

1. **Three query paths** — MCP tools had to fan out across all three systems for a single concept lookup
2. **Stale data** — No versioning meant framework knowledge could drift from the TOML source files
3. **No aliases** — Concept names had to match exactly; synonyms and alternate forms failed silently
4. **Isolation bug** — Switching projects left the previous project's KG in memory

## Decision

Merge all three knowledge systems into a **single per-project `KnowledgeGraph`**. TOML files remain as the authoritative source for framework knowledge, seeded into the unified graph at startup.

### Architecture

```
TOML seed files (framework knowledge)
        ↓
  ensure_seeded(graph)  ← version key check
        ↓
KnowledgeGraph (SQLite)
  ├── entities  (~179 seeded)
  ├── relations (~250 seeded)
  └── aliases   (~160 seeded)
        ↑
  Project artefacts (entities, surfaces, stories, etc.)
```

### Key Design Points

- **`ensure_seeded()`** checks a `seed_meta` version key before seeding. Stale seeds are cleared and re-seeded atomically. Incrementing the version in `seed.py` is the only action needed to refresh all running instances.
- **Aliases table** maps alternate names and synonyms to canonical entity IDs. `resolve_alias()` is called before every concept lookup.
- **`reinit_knowledge_graph(project_root)`** closes and reopens the SQLite DB when `select_project()` switches context, eliminating the cross-project isolation bug.
- **TOML fallback** preserved in `semantics_kb/__init__.py` and `inference.py` during transition; KG is tried first.

### New Entity Type Prefixes

| Prefix | Meaning |
|--------|---------|
| `inference:` | Inference rule node |
| `concept:` | Framework concept from semantic KB |
| (no prefix) | Project artefact (entity, surface, story, …) |

## Consequences

### Positive

- Single query path for all concept and inference lookups
- Aliases enable flexible concept resolution without exact naming
- Version key ensures consistency across sessions and deployments
- Project switching is safe — no cross-project data leakage
- Framework knowledge is auditable and diffable as TOML in version control

### Negative

- `ensure_seeded()` adds ~20 ms to cold startup when seed version changes
- TOML seed files must be kept consistent with `seed.py` version bumps
- SQLite per-project means one DB file per project directory

### Neutral

- Three legacy KB modules remain as thin facades routing to the unified KG
- `graph` MCP tool gains `concept`, `inference`, and `related` operations using the same store
- 42 new tests cover seed integrity, concept lookup, and inference lookup

## Alternatives Considered

### 1. Keep Three Separate Systems

Continue maintaining semantic KB, inference KB, and project KG independently.

**Rejected:** Duplication grows over time. Fan-out queries are fragile. No cross-system reasoning possible.

### 2. Runtime-Built KGs Without Seed Data

Build the KG entirely from project artefacts; no framework knowledge pre-seeded.

**Rejected:** Framework concepts (DSL constructs, best practices) are not derivable from project artefacts alone. MCP tools need framework knowledge to advise on gaps.

### 3. No Seed Versioning

Seed on every startup unconditionally.

**Rejected:** Startup latency and unnecessary churn. Version key approach seeds only when content changes.

## Implementation

Core files: `src/dazzle/mcp/knowledge_graph/seed.py` (seeding), `src/dazzle/mcp/knowledge_graph/store.py` (aliases, seed_meta), `src/dazzle/mcp/state.py` (init + reinit). Tests: `tests/unit/test_kg_seed.py`, `tests/unit/test_kg_concept_lookup.py`, `tests/unit/test_kg_inference_lookup.py`.
