# Dazzle by Design

> **Best Before:** 2026-11-05 (review every six months).
> **Last reviewed:** 2026-05-05.
> **Invalidated by:** any change to ADRs [0002](adr/0002-mcp-cli-boundary.md), [0004](adr/0004-dsl-agent-first.md), [0006](adr/0006-frozen-ir.md), [0007](adr/0007-rbac-three-layers.md), [0009](adr/0009-predicate-algebra.md), [0010](adr/0010-permit-scope-separation.md), [0011](adr/0011-ssr-htmx.md), or to the public surface listed in `docs/api-surface/`. If any of those move, this document is suspect until re-read.

This is a *philosophical* onboarding doc, not a reference. It assumes you are a working software engineer joining as a Dazzle contributor and want to understand **why what exists, exists** — fast enough that you can read and review code with the right priors. Mechanics live in `docs/reference/`, ADRs live in `docs/adr/`, and the public API surface is pinned under `docs/api-surface/`. This doc connects them.

---

## What Dazzle is

Dazzle is a DSL-first toolkit for building applications from high-level specifications. You write a `.dsl` file describing entities, surfaces (UI views), workspaces (navigable groupings), processes (state machines), and authorisation rules. The parser produces a frozen, immutable intermediate representation (the AppSpec). A runtime then executes that IR directly: FastAPI routes, HTMX-rendered templates, scope-aware Postgres queries, RBAC enforcement, OpenAPI/AsyncAPI specs, an MCP server, demo data, audit trail, compliance evidence — all derived from the same model, with no parallel object graph and no generated source tree to maintain.

Dazzle is **not** a code generator that scaffolds a project you then edit. The DSL is the artefact you maintain; the runtime materialises behaviour from it on every boot. Generated code exists (OpenAPI clients, fixture data, etc.), but never as the place where your business logic lives.

---

## The operating model

### Agent-first, human-readable

Dazzle's primary consumer is an AI agent — a Claude Code session, a Dazzle MCP client, the autonomous `/improve` loop. Humans read and review the DSL, but agents are the population that writes most of it ([ADR-0004](adr/0004-dsl-agent-first.md)). This single decision drives nearly every other one in the system:

- **Precision over ergonomics.** When agents are the writer, terseness loses to formal precision. `as: persona_name` beats an inferred `for:` clause; explicit FK paths beat magic. Ambiguity is a bug.
- **Clean breaks over compat shims.** ([ADR-0003](adr/0003-clean-breaks.md)) Agents update all callers in the same commit. Backwards-compatibility wrappers exist to spare humans the diff; agents don't need that mercy.
- **Frozen IR.** ([ADR-0006](adr/0006-frozen-ir.md)) Once parsed, the AppSpec is immutable. Agents reasoning about a fixed structure beats agents reasoning about a graph that mutates under them.
- **Static analysis everywhere.** Scope predicates type-check against the FK graph at `dazzle validate` time. Surface fidelity, story coverage, RBAC matrices, API surface — all validated before the runtime ever boots.

You will sometimes hear this phrased as "the DSL is for AI." That's directionally right but shorthand. The fuller claim is that **the DSL is a formal model the runtime executes and agents reason over** — humans review the model, agents primarily author it, and the runtime is the model's only consumer at runtime.

### DSL → IR → runtime

```
.dsl files
   │  parse  (src/dazzle/core/dsl_parser_impl/)
   ▼
AppSpec (frozen Pydantic IR — src/dazzle/core/ir/)
   │  link  (FK graph, scope predicate compilation, persona binding)
   ▼
validated AppSpec
   │
   ├─→ Runtime (src/dazzle/http/, src/dazzle/page/)  — FastAPI + typed Fragments + HTMX
   ├─→ Specs   (src/dazzle/specs/)                — OpenAPI, AsyncAPI
   ├─→ MCP     (src/dazzle/mcp/)                  — knowledge, validation, queries
   ├─→ LSP     (src/dazzle/lsp/)                  — editor diagnostics
   └─→ Generated artefacts                        — clients, demo data, fixtures
```

The IR is the contract. Anything downstream that needs to know about the app reads the same IR. There is no "true" parallel representation in Python objects, ORM models, or migration files — those are *projections* of the IR.

### MCP / CLI boundary

There is one architectural seam worth internalising before reading any tool code: **MCP is for stateless reads, CLI is for process and writes** ([ADR-0002](adr/0002-mcp-cli-boundary.md)). An agent in a conversation calls `dsl validate` over MCP and gets an answer in milliseconds. An agent that wants to run migrations or generate a release artefact uses the CLI, which can take minutes and stream output without blocking the conversation. The boundary keeps long-running work out of the agent's chat loop and keeps MCP tools cheap to call.

---

## The core abstractions, and why each exists

The DSL has two dozen constructs (full list in `CLAUDE.md`). The shortlist below covers the ones whose *purpose* is non-obvious from name alone.

### `entity`
A row type and its constraints. Compiles to a Postgres table via Alembic ([ADR-0017](adr/0017-schema-migrations-via-alembic.md)). The novelty is that an entity is also a *node in the FK graph* used by the predicate algebra (see `scope`) and by the chart compiler. This is why entities are not just "tables we generate" — they are the typed substrate on which all later analysis runs.

### `surface`
A UI view bound to an entity in a particular mode (list, detail, form, dashboard, report). Surfaces matter more than entities for determining behaviour: the *(Entity, Surface, Persona)* triple is the atomic unit of verifiable behaviour ([ADR-0019](adr/0019-surface-triple-as-atomic-unit.md)). Two apps with identical entities can ship completely different products by having different surface compositions, so audits, fidelity checks, and trial scenarios all index on surfaces rather than entities.

### `permit` and `scope`
Authorisation is two layers, never one ([ADR-0010](adr/0010-permit-scope-separation.md)):

- **`permit:`** — coarse role-based gate. "Teachers may *list* manuscripts." Pure RBAC, no field conditions allowed.
- **`scope:`** — row-level predicate. "Teachers may list manuscripts *whose school = current_user.school*." This compiles to a 6-type predicate algebra ([ADR-0009](adr/0009-predicate-algebra.md)) and is statically validated against the FK graph: if you reference a column, the link phase verifies it exists and is reachable.

Mixing them is forbidden because they are evaluated in different places (route-level gate vs query-level filter) and because a clean separation is what lets the matrix verifier ([ADR-0007](adr/0007-rbac-three-layers.md)) check "every persona × every entity × every surface" combinatorially. RBAC has three layers — static matrix at validate time, dynamic verifier at runtime, append-only audit trail at exec time — and they reinforce each other; no single layer is trusted alone.

### `process`, `transaction`, `story`, `rhythm`
- **`process`** — state machine over an entity (`draft → submitted → approved`). States are plain strings.
- **`transaction`** — atomic write spanning multiple entities (the "unit of work" you'd otherwise express imperatively).
- **`story`** — persona narrative ("As a teacher I want to mark a manuscript reviewed"). Stories compile down to surface coverage and test scaffolds.
- **`rhythm`** — recurring or scheduled cadence ("daily 9am: digest unread comments"). Lifts cron out of process bodies and into the model.

These exist because *imperative business logic is the part of an app that can't be statically analysed*, and Dazzle aggressively pushes that work into declarative constructs the linker and verifier can see. If you find yourself reaching for raw Python to express domain behaviour, the right move is usually to find the construct that already covers it — not to bypass the model.

### `aggregate` / chart regions
A bar chart, pivot table, or KPI tile compiles to **one** scope-aware `Repository.aggregate` call which runs **one** `GROUP BY` SQL query (`docs/reference/reports.md`). No N+1, no enumeration phase, no possibility for the bucket list to diverge from the counts. This is the same pattern as scope: declarative spec → compiled SQL → no imperative escape hatch in the middle.

---

## What we deliberately don't do

The clearest way to understand Dazzle is by what it refuses to ship that comparable systems do.

### No ORM
Django, Rails, Prisma, SQLAlchemy, TypeORM all give you a row-as-object layer with identity maps, lazy loading, and unit-of-work semantics. Dazzle uses raw SQL via psycopg2.

The reason: an ORM conflates schema declaration, query construction, row-to-object mapping, migration management, and boundary validation into one package. Dazzle does most of those jobs — schema via DSL, migrations via Alembic, queries via `aggregate` and scope-compiled SQL, boundary validation via Pydantic DTOs — but deliberately omits row-to-object mapping. The omitted piece is the part that creates a parallel object graph, which is also the part that hides data access behind attribute reads (N+1 surprises, lazy-load lifecycle bugs, the `n+1.attribute_error_in_template` debugging session). The DSL is the model; the runtime executes it; there is no second source of truth to drift from. An ORM is a Python-language ergonomics tool, not a relational requirement — Codd's relational model has no notion of one.

### No SPA
React, Vue, Svelte, Next.js, Remix all assume a JS application that fetches JSON from your backend. Dazzle uses **server-rendered typed Fragments + HTMX** for interactivity ([ADR-0011](adr/0011-ssr-htmx.md), [ADR-0023](adr/0023-template-emission-patterns.md)). Surfaces declare `render: fragment` in DSL; the runtime emits HTML from a frozen-dataclass primitive tree, no Jinja2 dependency (retired #1042 / v0.67.92).

The reason: Dazzle generates UI from the model. SPAs are a poor fit because they want a rich client-side state machine that diverges from the server's. With server-side rendering, every UI surface is just a function of the (Entity, Surface, Persona) triple plus current row state, which is exactly what the model already describes. Interactivity that *does* need client state uses Alpine.js with carefully scoped patterns ([ADR-0022](adr/0022-alpine-bindings-vs-idiomorph.md)).

### No SQLite
Many frameworks ship SQLite as the development default. Dazzle is PostgreSQL-only ([ADR-0008](adr/0008-postgresql-only.md)).

The reason: scope predicates use Postgres-specific subquery shapes; FTS uses `tsvector`; aggregate uses Postgres `GROUP BY` semantics. A SQLite path would require either a feature subset or a translation layer; either choice creates a class of bugs where dev passes and prod fails. The cost (Docker postgres on dev) is paid once; the avoided cost (silent dialect divergence) compounds.

### No singletons
FastAPI codebases routinely grow module-level globals: a database session, a cache client, a settings object. Dazzle uses a `RuntimeServices` dataclass attached to `app.state` and passed via dependency injection ([ADR-0005](adr/0005-runtime-services.md)).

The reason: singletons make tests fight import order, make multi-tenant runtime impossible, and hide dependency edges. Explicit `RuntimeServices` is mildly more verbose and dramatically more honest.

### No backwards-compatibility shims (pre-1.0)
Most frameworks accumulate aliases, deprecation warnings, and "old way / new way" doc pages for years. Dazzle does clean breaks ([ADR-0003](adr/0003-clean-breaks.md)).

The reason: agents are the primary consumer, and an agent updating all callers in one commit is cheaper than every reader re-learning the version-skewed surface. Pre-v1.0 we explicitly trade migration friction for surface clarity. Post-v1.0 this changes.

### No imperative escape hatch (and the awkward part)
The closest thing Dazzle has to "drop down to raw code" is `service` and `transaction` constructs that wrap Python functions with a typed contract. There is *not currently* a clean construct for ad-hoc reads that don't fit `aggregate`'s shape — those tend to land as raw psycopg2 calls inside service bodies. This is a known gap; the framing under consideration is a `query` construct that names its inputs, outputs, entities-touched, and personas-allowed, so the *envelope* of the unmodelled work is statically analysable even if the body remains raw SQL.

The principle worth holding when you write the rare bit of raw SQL: you are stepping outside the part of the system the linker and verifier can see. Make the radius small, keep the shape explicit, and prefer pulling the work back into a modelled construct as soon as the shape stabilises.

### No knowledge-system sprawl
Dazzle had three knowledge systems (semantic KB, inference KB, project KG). It now has one ([ADR-0013](adr/0013-unified-knowledge-graph.md)) — a per-project graph seeded from TOML, with project artefacts merged in. Plurality of overlapping knowledge sources turned out to be a correctness hazard, not a flexibility win.

---

## How to navigate the codebase

| You want to… | Read first |
|---|---|
| Understand the DSL grammar | `docs/reference/grammar.md` |
| Add a DSL construct | `CLAUDE.md` § "Extending" + the parser mixin pattern in `src/dazzle/core/dsl_parser_impl/` |
| Understand a runtime behaviour | Find the surface in IR (`src/dazzle/core/ir/`) → trace through `dazzle_http` route → check `scope` predicate compilation |
| Audit the public API | `docs/api-surface/` (five baselines, drift-tested) |
| Decide if a change needs an ADR | If it would change a "What we deliberately don't do" answer above: yes |
| Understand an architectural choice | `docs/adr/INDEX.md` |
| Run autonomous improvement | `/improve` (driver picks lane) — see `CLAUDE.md` § "Autonomous Improvement Loop" |
| Cross-check against industry conventions | This doc + the relevant ADR |

The single most useful habit when contributing: **before writing code, find the IR types involved and read them.** The IR is small, stable, and frozen — it tells you the shape of the world the runtime sees. Most "I don't know how to do this in Dazzle" questions resolve in five minutes once the IR is in your head.

---

## What this document is not

It is not a reference. It will be wrong about a method signature within weeks. The reference docs and the `dazzle inspect api` baselines are authoritative for mechanics; this doc is authoritative for *intent*. If they disagree, the reference wins for what the code does and this doc wins for what the code is trying to be — and one of them needs updating.

It is also not a roadmap. Where Dazzle is going lives in `ROADMAP.md` and the open issues. Here we describe only the system as it stands.

---

## A short reading list

If you have an hour, read in this order:

1. This document.
2. [ADR-0004](adr/0004-dsl-agent-first.md) (agent-first DSL) and [ADR-0010](adr/0010-permit-scope-separation.md) (permit vs scope) — the two decisions that most shape day-to-day code.
3. `docs/reference/grammar.md` — the grammar at a glance.
4. `examples/simple_task/` — a complete app in ~100 lines of DSL.
5. `src/dazzle/core/ir/__init__.py` — the IR shape, listed in one place.

After that, you are oriented enough to read review comments and contribute meaningfully. The rest is breadth, and breadth comes from reading the ADR index end to end.
