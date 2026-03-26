# ADR Index

Architectural Decision Records for the Dazzle project. Agent-scannable: each line is a decision that prevents a wrong proposal.

- [0001](0001-docs-site.md) — MkDocs Material for docs. No wiki, no Docusaurus.
- [0002](0002-mcp-cli-boundary.md) — MCP = stateless reads. CLI = process/writes. Don't block conversation with long ops.
- [0003](0003-clean-breaks.md) — No backward compat before v1.0. Delete freely, never create shims or wrappers.
- [0004](0004-dsl-agent-first.md) — DSL optimized for AI agents. Precision and formal correctness over human ergonomics.
- [0005](0005-runtime-services.md) — RuntimeServices dataclass on app.state. No new module-level singletons.
- [0006](0006-frozen-ir.md) — IR is immutable frozen Pydantic. Never mutate after parse.
- [0007](0007-rbac-three-layers.md) — RBAC: static matrix + dynamic conformance + audit trail. Three independent layers.
- [0008](0008-postgresql-only.md) — PostgreSQL is the sole database. No SQLite code paths.
- [0009](0009-predicate-algebra.md) — Scope rules compile to 6-type predicate algebra. Validated against FK graph at link time.
- [0010](0010-permit-scope-separation.md) — permit = role gate (RBAC). scope = row filter (ABAC). Never mix.
- [0011](0011-ssr-htmx.md) — Server-side Jinja2 + HTMX. No SPA frameworks (React, Vue, etc.).
- [0012](0012-alembic-migrations.md) — Alembic for schema migrations. No hand-rolled migration planners.
- [0013](0013-unified-knowledge-graph.md) — One per-project KG with TOML seed. No separate knowledge systems.
- [0014](0014-no-future-annotations-in-routes.md) — No `from __future__ import annotations` in FastAPI route files. Breaks OpenAPI.
- [0015](0015-tigerbeetle-ledgers.md) — TigerBeetle for double-entry ledgers. Optional dependency, DSL `ledger`/`transaction` constructs.
