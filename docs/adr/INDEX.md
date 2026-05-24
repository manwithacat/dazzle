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
- [0016](0016-vendor-integration-workflow.md) — API Packs for vendor integration. TOML-driven mocks, webhook testing, DSL generation.
- [0017](0017-schema-migrations-via-alembic.md) — All schema changes via Alembic, including framework entities. No raw DDL at startup.
- [0018](0018-project-local-file-writes.md) — All file writes go to the project directory. Never write to the Python package directory.
- [0019](0019-surface-triple-as-atomic-unit.md) — (Entity, Surface, Persona) triple is the atomic unit of verifiable behaviour.
- [0020](0020-lifecycle-evidence-predicates.md) — Lifecycle evidence predicates are orthogonal to state machines.
- [0021](0021-marketing-via-sitespec.md) — Marketing pages via `sitespec.yaml`. No `# dazzle:route-override` on public paths.
- [0022](0022-alpine-bindings-vs-idiomorph.md) — Don't put Alpine bindings on idiomorph-morphed elements. Server-render or use `x-init` helpers with direct DOM manipulation.
- [0023](0023-template-emission-patterns.md) — Two-pattern template-emission model post-jinja2. Pattern A (framework writes HTML) uses f-strings + `dazzle.render.html.esc`; Pattern B (framework executes user-authored templates) uses `string.Template`. Choice is mechanical: who writes the template.
- [0024](0024-no-regex-in-dsl-parser.md) — No regex for DSL grammar. A regex parsing DSL is a signal for missing grammar, not an end solution. Lexical-shape regex (identifiers, numerics) is fine; matching call shapes / keywords / sub-expressions is not.
- [0025](0025-authorization-is-entity-level.md) — Authorization is entity-level only. Field-level auth is not added; it would break the enumerable role×entity×operation security surface. A field with its own lifecycle is its own entity. Field sensitivity uses `classify`/`pii()`, not `permit:`.
- [0026](0026-subtype-polymorphism-tpt.md) — Subtype polymorphism uses TPT (table-per-type), flat hierarchy, immutable discriminator. Complex, potentially brittle — only justified when all three conditions hold: true IS-A, subtype-specific NOT NULL fields, polymorphic queries genuinely needed.
