# ADR-0030 — PostgreSQL Capability Admission: Rubric and Scored Catalogue

**Status:** Accepted (2026-06-01 — ratified after the adversarial pass below; the rubric is durable, the catalogue is a living document).
**Issue:** #1330 (proposal). Spun off concrete bug #1321 (DECIMAL/MONEY stored as float).
**Relates:** ADR-0008 (PostgreSQL-only — the premise), ADR-0009 (predicate algebra — *where the DB-side-logic prohibition actually lives*), ADR-0015 (TigerBeetle ledgers — owns the conservation/double-entry case), ADR-0017 (migrations via Alembic — *governs the channel, not the construct; see Revision note*), ADR-0025 (entity-level authorization), ADR-0028 (guarded transactional actions), ADR-0029 (atomic flows as the transactional-intent substrate), ADR-0031 (flow-level aggregate invariants — owns the non-ledger conservation remainder as a distinct `invariant:` construct)

## Revision note (2026-06-01)

The first version of this ADR was authored by an external reviewer without access to the codebase and asked the Dazzle agent to validate it adversarially. That pass found three framing errors that this revision corrects; they are recorded here because the *errors* are instructive:

1. **The "Open question" was malformed.** It asked whether ADR-0017 prohibits "DB-side logic per se" or "hand-rolled DB-side logic." **ADR-0017 prohibits neither.** Read in full, 0017 governs the *channel* by which schema changes are applied (Alembic revisions, not raw `ALTER` at startup); it is silent on CHECK vs. trigger vs. PL/pgSQL. The prohibition on *unanalyzable imperative DB-side logic* is real but lives in **ADR-0009 (algebra-visibility)** and **ADR-0029 invariant 8**, and is already captured by the analysability criterion below — so the original "Gate G" was not a separate lever; it was redundant. (ADR-0029 line 29 repeats the same misattribution — "a hand-rolled trigger, itself an ADR-0017 violation"; that line should be corrected to cite ADR-0009/0029-inv-8.) The original "first agent task" is therefore deleted, not answered.
2. **C1/C2 had the causality backwards.** They required the construct be "reconstructible into the IR" and "round-trippable (AppSpec → SQL → re-extracted IR) losslessly." Dazzle has **no SQL→IR re-extraction** — generation is strictly one-way (IR → SQLAlchemy `MetaData` → Alembic; metadata is always canonical). Taken literally, *every* construct including `NOT NULL` failed C2. The round-trip framing imports a bidirectional-sync / schema-reflection model (an ORM reflecting a legacy DB) that does not describe Dazzle: the IR is the source of truth and SQL is a forward-only projection. The criterion is reformulated below as **forward-derivability**, which is the property that actually matters and is actually testable.
3. **One Tier-B recommendation contradicted a shipped decision.** The original "Recommended" SSI/`SERIALIZABLE` mechanism for ADR-0029 invariant 4, with a runtime retry loop, is exactly the isolation-level path **struck in #1316** (it conflicts with atomic's no-compensation, single-shot model on a pooled connection). It is demoted to Tier C here, re-admissible only via its own ADR with the reset + whole-flow-retry plumbing specified.

The rubric *concept* (a falsifiable, feature-independent admission test; catalogue disposable, rubric durable) survived the pass and is retained. The criteria are reduced from "five-plus-a-gate" to **four genuinely independent ones plus two mechanical sub-checks**, and a criterion ADR-0017 actually implies — **migration-evolvability** — is added (it demotes Postgres `ENUM`).

## Decision

Dazzle targets PostgreSQL exclusively (ADR-0008). That is a constraint to **exploit**: single-platform support lets the compiler emit Postgres-specific constructs unconditionally, with no portability layer to water them down. This ADR defines **which Postgres constructs Dazzle may compile to**, via a durable **admission rubric** and a disposable **scored catalogue**.

The governing principle, carried from ADR-0029, is the separation of **decision/logic** from **enforcement/consistency**:

> Dazzle compiles its analysable, agent-authored model **to** Postgres-specific SQL and generated declarative constructs that exploit the engine. It does **not** relocate decision logic, orchestration, or invariant *evaluation* **into** procedural server-side code.

A construct is admissible only if it sits on the enforcement side of that line *and* passes the rubric. Crucially — and this is the correction over v1 — "the agent authored it, not the app developer" is **not a separate gate**; it falls out of the analysability criterion: a construct the framework did not emit from the AppSpec is, by definition, not IR-derived, so it fails A1. What *is* a separate, real obligation is **enforcement**: conformance must *flag* any equivalent hand-rolled construct it finds on an author surface (see *Enforcement obligation*).

## The admission rubric

Four **independent criteria** and two **mechanical sub-checks** (cheap tests that bound a criterion). A construct is **Core-admissible** only if it passes all four criteria.

| # | Criterion | Operational (testable) definition | Failure mode excluded |
|---|-----------|-----------------------------------|-----------------------|
| **A1** | **IR-derived & forward-projectable** | There is an IR node the matrix, conformance, and api-surface audit **already understand**, and that node **deterministically projects** to the construct (IR → SQL is total and reproducible). The analysis surfaces read the **IR**, never the emitted SQL. | Effect-at-a-distance; behaviour authored outside the AppSpec; constructs no analysis surface can see. (Subsumes v1's C1, C2, and Gate G — none were independent.) |
| **A2** | **Effect-deterministic** | Same committed inputs produce the same effect/decision, **stable across query plans, collations/locales, float-vs-exact arithmetic, injected-vs-wall-clock time, and conformance replay.** | Plan-, locale-, float-, time-, and sequence-dependent variation (see *Determinism gotchas* — the high-value test fodder). |
| **A3** | **Transactionally contained** | No effect escapes the enclosing transaction; rolls back cleanly; no external I/O, no async delivery. | Side effects that cannot be rolled back (ADR-0029 invariant 7 at feature level). |
| **A4** | **Migration-evolvable** | The construct can be **added, altered, or dropped via an ordinary Alembic migration** (ADR-0017) as the AppSpec evolves, without routinely forcing a non-transactional DDL hazard or a full-table rewrite on a normal spec edit. | Constructs that are cheap to create but migration-hostile as the spec changes — the cost 0017 actually cares about. (New in v2; it is what 0017 *implies*, vs. the logic-prohibition v1 wrongly attributed to it.) |

**Mechanical sub-check N (non-Turing-complete).** Bounded, guaranteed-terminating; no unbounded iteration/recursion, or a static termination bound is provable. This is not a peer criterion — it is the cheapest mechanical means to A1 (a non-terminating construct is not forward-projectable) and A2. Kept named only because recursive CTEs need a named adjudicator.

**Mechanical sub-check P (provenance, for enforcement).** Confirm the construct is emitted by the framework and absent from author surfaces. This does not *admit* a construct (A1 already requires IR-derivation); it is the hook for the *Enforcement obligation* below.

### Relationship between the criteria

- **A1 and A2 are independent.** A construct can be perfectly IR-derived yet non-deterministic in effect (a `CHECK` over a `VOLATILE` function; a `float8` sum).
- **A3 is independent of A1, A2, A4.** `NOTIFY` is IR-derivable, deterministic, and migration-trivial, yet fails A3.
- **A4 is independent of the rest.** Postgres `ENUM` passes A1–A3 cleanly and *fails A4* (see catalogue) — the case that motivates having the criterion at all.

Treat the rubric itself as falsifiable: if a Core-admissible construct can be shown to fail any criterion under some input/plan/locale/migration, it is **demoted**, not excused.

### Enforcement obligation (not an admission criterion)

For every construct Dazzle emits to enforce a scope or invariant, **conformance MUST flag an equivalent construct found on an author-authored surface** (a hand-written route, a hand-edited migration, a `# dazzle:implements` override). This is the real residue of v1's Gate G: not "is it framework-generated" (A1 settles that), but "does the framework *notice* when the author hand-rolls the same thing outside the model." This is the boundary that keeps the analyzable model honest.

## Scored catalogue

Scoring per criterion: ● pass, ◐ conditional (constraint in notes), ○ fail. The **Impl** column is orthogonal to admissibility and records what Dazzle emits **today** (✅ from AppSpec · ⚠️ partial/special-case only · ❌ not emitted) — v1 conflated "admissible in principle" with "shipped," which made an aspirational Tier A read as current capability.

**Verdict tiers:** **A** = Core-admit · **B** = Conditional-admit (admit only under the stated constraint) · **C** = Rejected.

### Tier A — Core-admissible (declarative)

| Construct | A1 | A2 | A3 | A4 | Impl | Notes / constraint |
|-----------|----|----|----|----|------|--------------------|
| `NOT NULL` | ● | ● | ● | ● | ✅ | — |
| `UNIQUE` / **partial** unique index (`WHERE …`) | ● | ● | ● | ● | ✅ | Partial-unique is the SCD-2 "one current row" enforcer (`pg_backend.py:51`, temporal entities, #1223). |
| `FOREIGN KEY` + referential actions (`CASCADE`/`SET NULL`/`RESTRICT`) | ● | ● | ● | ● | ✅ | CASCADE/RESTRICT emitted today. Cascade has **multi-row effect** the agent must model in the IR, not just emit. |
| `CHECK` (over **immutable** expressions only) | ● | ◐ | ● | ● | ❌ | A2 only if the expression calls no `VOLATILE`/`STABLE` function; **NULL caveat** (gotcha 5). No IR `ConstraintKind` for CHECK today — net-new. |
| `GENERATED ALWAYS AS (…) STORED` (immutable expr) | ● | ◐ | ● | ● | ⚠️ | Emitted today **only** for FTS `tsvector` (`search_schema.py:226`); not a general author capability. A2 as for CHECK. **Must not** be the sole derivation of an authorization scope key an app-layer check relies on (recreates the ADR-0028 denormalization spoof; cf. ADR-0029 grey-case 2). |
| `EXCLUDE USING gist (… WITH =, range WITH &&)` | ● | ● | ● | ● | ❌ | The bitemporal enforcer: non-overlapping validity intervals. **Highest-value net-new item** — closes ADR-0029's *temporal* honest-limit at the **storage** layer (unbypassable), not just the flow boundary. |
| `DEFERRABLE INITIALLY DEFERRED` (modifier) | ● | ● | ● | ● | ❌ | Checks at **commit**; lets a flow pass through a transient invalid intermediate state (ADR-0029 multi-step). `use_alter=True` (circular-FK DDL ordering) is **not** this — net-new runtime deferral. |
| Range types (`tstzrange` etc.) | ● | ● | ● | ● | ❌ | Pair with `EXCLUDE`. |
| Domain types with constraints | ● | ● | ● | ● | ❌ | — |
| Non-recursive **data-modifying CTE** (`WITH u AS (UPDATE … RETURNING …) …`) | ● | ◐ | ● | ● | ❌ | Single-statement multi-step atomicity, generable from the manifest. A2 caveat: sub-statements share **one snapshot**; ordering is **only** via data dependency (`RETURNING`→`FROM`). Use for **linear** flows; reject where a later step must read an earlier step's writes. Overlaps the ADR-0029 atomic executor — decide which owns linear-flow generation. |
| Window functions / `LATERAL` (pure) | ● | ● | ● | ● | ⚠️ | For compiling aggregate/correlated scope predicates. |
| `INSERT … ON CONFLICT` (upsert) | ● | ● | ● | ● | ⚠️ | Hand-written in runtime infra today, never emitted from AppSpec. Conflict target must match a real (possibly partial) index; agent must model the predicate (gotcha 6). |

`NUMERIC(p,s)` is **not** listed as a construct — it is the correct default storage for `decimal`/`money` and its absence is a **bug** (#1321: both currently map to `DOUBLE PRECISION`, dropping precision/scale). It is a precondition for A2 on any conservation/aggregate path, not an opt-in capability.

### Tier B — Conditional-admit (pending agent validation against example apps)

| Construct | Verdict basis | Admit only if … |
|-----------|---------------|-----------------|
| `REPEATABLE READ` / `FOR SHARE` / `FOR UPDATE` / `FOR NO KEY UPDATE` | Pessimistic concurrency; declared, deterministic outcome. | The agent can **enumerate** the scope-parent rows to lock; a missed row silently re-opens the TOCTOU. **This is the sanctioned mechanism for ADR-0029 invariant 4** (`FOR SHARE` on attribute-scope parents, deterministic `(table, pk)` lock order — shipped #1316). Junction-membership (`ExistsCheck`) phantoms remain out of scope for share-locks (0029 invariant 4). |
| `MERGE` (PG15+) | Declarative-ish, non-TC. | Validated against example apps — richer `WHEN` semantics than `ON CONFLICT`; agent must prove the IR captures all branches. |
| **Recursive** CTE (`WITH RECURSIVE`) | Borderline N (sub-check). | A **static termination bound** is provable (depth-limited walk over a declared FK hierarchy). Unbounded ⇒ Tier C. *Already emitted* for graph neighborhood (`neighborhood.py`, depth-bounded, SELECT-only) — consistent with this condition. |
| `JSONB` | Shallowly analysable; schema-less by default ⇒ anti-A1. | The shape is **declared** in the AppSpec and validated; never an unconstrained bag. Treat as a typed sub-schema, not an escape hatch. |
| `ENUM` types | Passes A1–A3; **fails A4**. | **Demoted from Tier A (v1).** `ALTER TYPE` to add/reorder/remove values is migration-hostile (value removal near-impossible; not always in-transaction). Emitted as `TEXT` today, which is *more* A4-compliant. Admit a true PG `ENUM` only if the state set is provably append-only over the app's lifetime; otherwise prefer `TEXT` (+ generated `CHECK` once CHECK ships). State-machine state sets are exactly the *evolving* case ⇒ default to `TEXT`. |
| Sequences / `IDENTITY` | Output deterministic per-call but **gaps on rollback** ⇒ fails A2 *for semantic use*. | Used **only** for surrogate keys; **forbidden** in invariant, audit, or any replayed/asserted logic. |
| `now()` / `transaction_timestamp()` | Stable **within** a transaction but not across runs ⇒ fails A2 for replay. | Forbidden in conformance-asserted/replayed paths **unless** sourced from an **injected clock** the harness can pin. `clock_timestamp()` is volatile ⇒ Tier C. |

### Tier C — Rejected

| Construct | Fails | Why rejected |
|-----------|-------|--------------|
| `SERIALIZABLE` (SSI) **+ retry loop** | A3 (operational), and **struck by #1316** | **Demoted from Tier B (v1).** ADR-0029 invariant 4 explicitly struck the isolation-level path: a pooled connection raised to SERIALIZABLE needs explicit reset-on-return and serialization-failure **retry**, which conflicts with atomic's no-compensation, single-shot model. `FOR SHARE` is the supported mechanism. SSI returns only via **its own ADR** specifying the reset + whole-flow-retry plumbing — not as an implicit author one-liner or a "recommended" default. |
| PL/pgSQL **functions** / **procedures** (for logic) | A1, N | Turing-complete, imperative, opaque to the IR. A single-transaction guarantee needs a transaction, not a procedure (ADR-0029). |
| **Triggers** (`BEFORE`/`AFTER`/`INSTEAD OF`) | A1, N | Effect-at-a-distance; the canonical anti-analysable construct. |
| **Deferred constraint triggers** for cross-row invariants (`sum(posting.amount)=0`) | A1, N | **The specific temptation flagged in ADR-0029.** The only storage-level way to enforce a **conservation** invariant (a per-row `CHECK` cannot span a group) — and exactly the hand-rolled imperative DB-side logic the rubric excludes. Conservation stays out of triggers; for true ledgers it lives in **ADR-0015** (`ledger`/`transaction`, storage-level `debits ≤ credits`); for the non-ledger remainder it lives at the flow boundary as **ADR-0031's distinct `invariant:` construct** (#1318) — explicitly *not* a 7th ADR-0009 predicate (the row-scoped algebra stays closed). This row is the boundary that keeps triggers out. |
| `CREATE RULE` (query rewriting) | A1 | Notoriously surprising rewrite semantics. |
| **Advisory locks** | A1 | Effect depends on application convention, invisible to the IR. |
| `NOTIFY` / `LISTEN` | A3 | Async delivery escapes transaction semantics. |
| `dblink` / `postgres_fdw` / FDWs | A3, schema-locality | External resources outside the DSL schema (ADR-0029 clause a/b). |
| `random()` / `gen_random_uuid()` / `clock_timestamp()` (in logic) | A2 | Non-deterministic; forbidden in any asserted/replayed path. If randomness/UUIDs are needed, inject and seed. |
| `COPY` (as logic) | A1, N (as a logic construct) | Bulk-load primitive, not a flow construct. |

## Determinism gotchas (the highest-value adversarial-test fodder for A2)

A2 has more teeth than it appears. Each is a concrete test, not a caveat:

1. **Floating-point summation is non-associative.** `sum()` over `float8` is **plan-order-dependent** — the same conservation check can pass or fail depending on aggregation order. **Conservation/aggregate invariants MUST be computed over `numeric`/`decimal`** — which is why #1321 (decimal→float) is a *correctness* bug, not a nicety. *Test: force a plan change (seq vs index scan); assert the sum is bit-identical.*
2. **Collation/locale-dependent comparison and ordering.** A scope predicate or unique constraint can behave differently across collations. **Pin a deterministic collation** (PG12+ `deterministic = true`) for any column a guard or constraint compares. *Test: run the corpus under two collations; assert identical decisions.*
3. **Sequence gaps on rollback** (Tier B) — surrogate-only, never semantic.
4. **`now()` is stable within a transaction, not across runs** (Tier B) — pin via injected clock for replay.
5. **NULL in `CHECK` passes.** `CHECK (amount > 0)` does **not** reject a NULL `amount` (three-valued logic). Pair every value constraint with `NOT NULL`. *Test: insert NULL into every CHECK-constrained column; assert rejection where intended.*
6. **`ON CONFLICT` target vs partial-index predicate mismatch** silently disables the upsert. *Test: prove the conflict target matches a live index.*

## Adversarial test protocol (per-criterion, per construct, against the example apps)

For each construct at Tier A or B, the agent runs the following and **demotes** on any failure:

1. **A1 (IR-derived & projectable):** produce a behaviour observable in the running example app that is **not derivable from the IR**. Any such behaviour ⇒ fails A1 (or the IR must be extended to capture it). *Note: this is a forward test — "can the analysis surfaces see it from the IR" — not a SQL→IR reconstruction; Dazzle has no re-extraction path and needs none.*
2. **A2 (determinism):** fuzz across (a) forced plan changes, (b) two collations, (c) `float` vs `numeric`, (d) injected vs wall-clock time, (e) rollback-induced sequence gaps; assert identical committed effect/decision.
3. **A3 (containment):** inject a rollback mid-flow; assert **zero** observable effect outside the transaction.
4. **A4 (migration-evolvable):** generate the construct, then apply a realistic spec edit (add/rename/remove a value or column it depends on) and confirm `dazzle db revision` + `upgrade` handles it without manual SQL, a non-transactional hazard, or a full rewrite on a routine edit.
5. **N (non-TC):** static check for unbounded recursion/iteration; for any recursive construct, **prove** a termination bound or reject.
6. **Enforcement (P):** confirm the construct is emitted by the framework and absent from author surfaces; **confirm conformance flags an equivalent hand-rolled construct** on an author surface.
7. **End-to-end, per example app:** for each real scope/invariant the construct enforces, attempt to **violate** it via (a) an **out-of-flow** path (hand-written route / migration / `# dazzle:implements`), (b) a **concurrent interleaving**, (c) a **non-deterministic input** from the gotchas. A successful out-of-flow violation is *expected* for flow-boundary invariants (it documents the ADR-0029 honest limit). A successful violation of a construct claimed **storage-level** (partial-unique, EXCLUDE) is a **defect**.

## Consequences

- **Positive:** a single, falsifiable rubric governs what Dazzle compiles to, decoupled from the feature list, so new Postgres versions are evaluated mechanically. The temporal/compositional families gain **storage-level, unbypassable** enforcement (partial-unique today; EXCLUDE + deferrable as net-new) — narrowing ADR-0029's honest limit for those families while keeping the general relational schema. The criteria are now genuinely independent (no phantom Gate-G dependency), and A4 catches a migration cost the original missed.
- **Negative:** the **conservation** family cannot be storage-enforced without a deferred constraint trigger, which the rubric rejects (A1/N); it stays in ADR-0015 (ledger) or at the flow boundary (ADR-0031's `invariant:`, #1318). Tier-A's net-new members (CHECK, EXCLUDE, DEFERRABLE, ranges, data-modifying CTE, AppSpec-driven ON CONFLICT) are **unimplemented** — admissibility is a design property, not a shipped one; each is its own slice. `numeric`-only arithmetic imposes a type fix (#1321).
- **Neutral:** the catalogue is a **living document**; tiers will move as the corpus is fuzzed. ADR-0029's PostgreSQL-realisation section becomes a **consumer** of this rubric rather than re-deriving it.

## Alternatives Considered

1. **Treat Postgres as a generic SQL target behind a portability layer.** Rejected — discards single-platform support; SSI, EXCLUDE, partial-unique, deferrable constraints, and data-modifying CTEs have no portable equivalent.
2. **Admit PL/pgSQL for "just the hard parts" (the conservation trigger).** Rejected — fails A1/N and re-opens the unanalyzable-DB-logic hole ADR-0028/0029 closed. Conservation stays in ADR-0015 / the algebra by design.
3. **Keep v1's five-criteria-plus-gate framing.** Rejected — C4 and Gate G were not independent (C4 is a means to A1/A2; G is subsumed by A1's IR-derivation requirement), and the round-trip C2 was untestable against a one-way generation pipeline. Over-articulation manufactured a phantom "first task."
4. **Score features ad hoc per use case.** Rejected — a durable rubric is what lets the agent adjudicate *future* features and *demote* current ones; the catalogue is disposable, the rubric is not.

## Open questions (genuine, post-revision)

1. **EXCLUDE/DEFERRABLE vs. the atomic executor (ADR-0029).** Both EXCLUDE (temporal storage-level) and DEFERRABLE (commit-time checks for intermediate states) overlap the atomic flow model. Decide the division of labour: which invariants move to storage (unbypassable, narrowing 0029's honest limit) and which stay at the flow boundary (analyzable, but bypassable out-of-flow). This is the real high-value design question the rubric surfaces — it replaces v1's malformed 0017 question.
2. **Data-modifying CTE vs. atomic executor.** Same overlap for linear-flow generation: does the framework emit a single data-modifying CTE, or sequence statements in the atomic executor's transaction? A2's snapshot/ordering caveat bounds the CTE to linear flows.
3. **`MONEY` storage semantics (feeds #1321).** Should money pin scale by currency code (already carried in the IR), and is the non-ledger money case ever conservation-bearing, or always routed to ADR-0015 ledgers?

## Cross-reference

- **ADR-0029** §"PostgreSQL realisation" to **consume** this rubric: deferrable constraints (intermediate state), generated partial-unique/EXCLUDE (temporal honest-limit), `FOR SHARE` per invariant 4 (**not** SSI — #1316), data-modifying CTEs (linear-flow generation target), and the conservation-trigger rejection. Also: correct line 29's "ADR-0017 violation" to cite ADR-0009 / invariant 8.
- **ADR-0017** governs the *channel* (Alembic), and *implies* criterion A4. It does **not** prohibit DB-side logic; that prohibition is ADR-0009 / ADR-0029 invariant 8.
- **ADR-0015** owns the conservation/double-entry case (storage-level ledgers); the rubric routes conservation there, not to a flow-level invariant for money.
- **#1321** — DECIMAL/MONEY → `NUMERIC` fix; precondition for A2 on any aggregate path.
- **ADR-0031 / #1318** — flow-level aggregate `invariant:` construct (a distinct construct, *not* an ADR-0009 predicate extension); the home for non-ledger conservation/cardinality invariants. Its concurrency stance (`FOR UPDATE` the anchor row; SERIALIZABLE stays struck) matches this rubric's Tier-C SSI demotion.
- `docs/reference/rbac-scope.md` — scope predicates compiling to collation- or float-sensitive comparisons must observe the A2 disciplines (deterministic collation; `numeric`).
