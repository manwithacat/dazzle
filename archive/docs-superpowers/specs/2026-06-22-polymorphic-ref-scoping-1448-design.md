# Declarative scoping for polymorphic platform-entity refs (`poly_ref`) — #1448

**Status:** Design approved (2026-06-22), ready for implementation plan.
**Issue:** #1448 (aegismark lens). **Author:** brainstormed with James Barlow.
**Disposition:** Large — new DSL primitive. Spec saved; #1448 stays open until shipped.

---

## 1. Problem

Framework platform entities that use a **polymorphic reference** — a `entity_type: str`
discriminator plus an `entity_id: str` holding a foreign entity's id as *text* — cannot
be **declaratively scoped** to non-admin roles. The DSL scope grammar supports only FK
paths (`fk.field = current_user.attr`) and junction `via`/`not via`; a polymorphic
`text → uuid` join gated on a discriminator column is neither. So a custom view over such
an entity can only be scoped **admin-only** (can't serve the role that needs it) or
**`all`** (a cross-tenant data leak). There is no secure middle, which blocks
de-CRUD'ing custom renderers onto declarative + `refresh:`-able regions for scoped roles.

### Concrete case (the dogfood)

`AIJob` (the AI-gateway audit entity) records `entity_type='CohortAssessment'` +
`entity_id=<cohort uuid as text>`. We want an "AI cost for this cohort" region — a
declarative `list`/`summary` over `AIJob` filtered to one cohort, with `refresh:` —
visible to the **teacher who uploaded the cohort**, replacing a custom poll renderer.
`CohortAssessment` is uploader-scoped (`read: uploaded_by = current_user as: teacher`).
The correct `AIJob` scope is *"`entity_id` is a `CohortAssessment` I'm allowed to read."*

### Why this is worth a primitive, not a bolt-on

- **It's a recurring platform shape**, not a one-off: audit logs, AI jobs, attachments,
  comments, notifications — the classic polymorphic-association targets. The cost
  amortises immediately.
- **`polymorphic-associations` is already a catalogued counter-prior** (`docs/counter-priors/`).
  Raw `entity_type`/`entity_id` is officially a *pathology* in this codebase. The typed
  primitive is the framework converting a catalogued anti-pattern into a safe construct —
  the prior-correction substrate doing exactly what it's for.
- **It scores *better* than a bolt-on on the framework's own Model-Driven Failure-Modes
  rubric** (`docs/architecture/model-driven-failure-modes.md`):
  - *Q4 (trace runtime → DSL):* a typed edge the FK graph understands is more traceable
    than a `poly(...)` predicate the FK graph **cannot validate** (it models 1:1 edges only).
  - *Q5 (preserve Postgres/auth/RLS semantics):* a bolt-on poly predicate is *more* likely
    to hit the #1447 degrade-to-app-layer path — i.e. push enforcement out of the database.
    A native edge gives the RLS compiler a real edge to reason about, keeping the policy
    *in Postgres*.
  - *Q3 (live detector):* the FK-graph validator + scope-runtime PG tests are already-live
    gates the primitive plugs into; the bolt-on partly escapes them.

## 2. Design intent: **traceability**

The load-bearing principle, and the answer to "when is model complexity too complex in the
era of agentic coding?":

> **A model abstraction is "too complex" exactly when its runtime behaviour cannot be
> traced back to the DSL by a competent engineer — regardless of who authored it.**

Authoring difficulty is a red herring in an agentic world; *traceability* is the invariant
the 4GL/MDE/CASE generation lost. `poly_ref` is acceptable **iff** it ships with a live
traceability oracle (§7). A human can't hand-author the type-guarded subquery, but with the
oracle they can read and verify it in one command. The oracle is the **price of the
primitive**, in the same spec — not a deferred nice-to-have.

## 3. The storage insight ("typed" deletes the cast)

Option-1-style bolt-ons needed `entity_id::uuid` casts everywhere because `entity_id` is
`text`. A typed `poly_ref` **owns its columns** and stores the id as a real `uuid`:

```dsl
poly_ref target [CohortAssessment, Manuscript]   # one logical field
```
generates:
```
target_type text not null     -- discriminator: target entity name (e.g. 'CohortAssessment')
target_id   uuid not null     -- real uuid column — NO cast, ever
```

**Constraint:** every poly_ref target entity must be **uuid-pk** (the Dazzle default). This
single constraint removes the cast at the source — the counter-prior pathology was *born*
from the stringly-typed `text` id.

Nullability: `poly_ref target [...]` is required (`not null` both columns) by default;
`poly_ref? target [...]` (optional) generates nullable columns and is matched by the usual
null-handling. (Both columns share nullability — a poly_ref is present or absent atomically.)

## 4. Surface grammar — a type-selected path

The scope is a normal FK path *through a chosen branch* of the polymorphic edge:

```dsl
entity AIJob "AI gateway audit record":
  id: uuid pk
  cost_usd: decimal
  poly_ref target [CohortAssessment, Manuscript]

  permit: read as: teacher
  scope:  read: target[CohortAssessment].uploaded_by = current_user  as: teacher

  permit: read as: school_admin
  scope:  read: all  as: school_admin
```

- `target[CohortAssessment]` **selects the branch**; `.uploaded_by` is then a real,
  FK-graph-validatable path on `CohortAssessment`.
- **Multi-branch visibility** (a persona who can see several target types) is expressed as
  **multiple scope rules** for that persona — the existing boolean-OR composite already
  unions same-persona rules. *No extra grammar for the multi-type case.*
- A **bare `target.x`** (selector omitted) on a poly_ref field is a **validation error**
  (ambiguous → forces explicit discrimination). Safety by construction.
- The post-selector tail is an ordinary scope path/expression, so depth-N paths
  (`target[CohortAssessment].school.trust_id = current_user.trust`) and the existing
  comparison/boolean forms compose unchanged.

### Why `target[Type].path` over `target is Type and …`

`target[Type]` keeps the discriminator and the join **atomic and unambiguous** — the parser
binds the selector to exactly the path that follows, and the FK graph validates
`Type.path` as one resolvable edge. An `is Type and …` form splits the guard from the join
into two loosely-coupled clauses an author can mismatch (guard on one type, path on
another), and scatters the load-bearing discriminator — the exact failure the
regular-vs-irregular dispatch lesson (#1444) warns against. `[Type]` reads as
"the CohortAssessment branch of target," which is precisely the semantics.

## 5. IR & parser

### 5.1 IR (`src/dazzle/core/ir/`)

- **Field kind**: new `poly_ref` field type carrying `target_entities: list[str]`
  (declaration order preserved; used for validation + discriminator literals). Models in the
  field-spec module alongside the existing `ref`/`belongs_to` kinds.
- **Predicate node** (`predicates.py`): add `PolyPathCheck` to the `ScopePredicate` union:
  ```
  PolyPathCheck:
    kind: Literal["poly_path"]
    field: str            # the poly_ref field name, e.g. "target"
    type_field: str       # derived: f"{field}_type"
    type_value: str       # selected branch, e.g. "CohortAssessment"
    id_field: str         # derived: f"{field}_id"
    target_entity: str    # == type_value (the resolved entity)
    sub: ScopePredicate   # the post-selector predicate, rooted on target_entity
  ```
  It is a *thin* node: it compiles down to the existing ExistsCheck/subquery shape (§6), so
  no new SQL-emission strategy — only the type-guard `AND` and the `id_field IN (...)` wrapper.

### 5.2 Parser (`src/dazzle/core/dsl_parser_impl/entity.py`)

- **Field declaration**: parse `poly_ref <name> [ T1, T2, ... ]` (and `poly_ref?` optional).
  New `TokenType.POLY_REF`. The `[ ... ]` target list reuses the bracket/comma machinery.
  No regex (ADR-0024).
- **Scope path selector**: in the scope-condition path parser, when the head identifier
  resolves to a poly_ref field, accept a `[ TypeIdent ]` selector before the `.` tail.
  Build a `PolyPathCheck` whose `sub` is produced by recursing the normal path/expression
  parser **rooted on `target_entity`**. Omitting the selector on a poly_ref head → parse/validate error.

## 6. App-layer compiler (`src/dazzle/http/runtime/predicate_compiler.py`)

`_compile_poly_path_check(node, ctx)` emits (param mode):

```sql
"target_type" = %s            -- bound to literal node.type_value
AND "target_id" IN (
  SELECT "id" FROM <target_table>
  WHERE <compiled node.sub>   -- reuses existing path/column/exists/value compilers
)
```

- No cast on `target_id` (it is `uuid`). The discriminator literal binds as an ordinary `%s`.
- `node.sub` is compiled by the **existing** `_compile_predicate_impl` dispatch — runtime
  markers (`CurrentUserRef`, `UserAttrRef`, `CurrentTenantRef`, create-scope `PayloadFieldRef`)
  all work unchanged inside the subquery.
- Create-scope (payload-probe) and update-destination revalidation: the poly form participates
  via the same machinery — on create/update the probe resolves `target_type`/`target_id` from
  the payload and runs the type-guarded subquery (#1311/#1312 path).

## 7. RLS policy compiler + #1447 degradation (`src/dazzle/http/runtime/rls_schema.py`)

Policy mode emits the param-free, GUC-based form:

```sql
"target_type" = 'CohortAssessment'
AND "target_id" IN (
  SELECT id FROM cohort_assessment
  WHERE uploaded_by = current_setting('dazzle.user_id', true)::uuid
)
```

- **RLS-expressible** when `node.sub` is RLS-expressible (a normal target scope usually is).
  The discriminator is an inlined SQL literal via the existing `_inline_sql_literal`.
- **Degrades via #1447** when `node.sub` is *not* RLS-expressible (dotted-junction binding,
  unresolvable GUC cast, entity-column target). Reuses the **already-shipped** machinery
  (`compile_predicate_policy` raises `ValueError` → permissive-within-tenant policy + app-layer
  enforcement; the `tenant_fence` still denies cross-tenant rows). No new degradation path —
  the poly node just flows through the existing try/except in `build_rls_scope_policy_ddl`.

## 8. FK-graph & validation (`src/dazzle/core/ir/fk_graph.py` + validators)

- **Conditional edges**: a `poly_ref target [A, B]` registers branch edges
  `(Entity, "target", type="A") → A` and `(..., type="B") → B`. `resolve_segment` learns to
  resolve a `field[Type]` selector to the branch target entity, then resolves the tail on it.
- **Static validation** (`dazzle validate`):
  1. every declared target entity exists and is **uuid-pk** (else `E_POLY_TARGET_NOT_UUID_PK`);
  2. the selected branch in a scope path is one of the declared targets
     (`E_POLY_BRANCH_UNDECLARED`);
  3. the post-selector tail resolves on that target via the normal FK-graph path validator;
  4. a poly_ref head **without** a `[Type]` selector in a scope path is an error
     (`E_POLY_SELECTOR_REQUIRED`).
- Each `scope:` still requires its matching `permit:` + `as:` (unchanged invariant).

## 9. Traceability oracle — `dazzle db explain-scope` (REQUIRED, this spec)

New CLI (sibling of `dazzle db explain-aggregate`):

```
dazzle db explain-scope <Entity> <verb> [--persona P] [--mode app|rls|both]
```

For each scope rule on `<Entity>.<verb>` (optionally filtered to persona `P`), print:
1. the **parsed predicate tree** (pretty-printed IR);
2. the compiled **app-layer WHERE** with runtime markers shown symbolically
   (`:current_user`, `:payload.target_id`, …);
3. the compiled **RLS policy DDL** body, **or** the #1447 degradation note + the exact
   reason string;
4. a one-line **expressibility verdict** per rule (`RLS` | `app-layer (degraded: <reason>)`).

This is the live detector that makes `poly_ref` pass the failure-modes rubric. It is also
generically useful for *every* scope form (it just renders whatever predicate compiled),
so it is not poly-specific scaffolding.

## 10. AIJob dogfood adoption (clean break — no shims)

`AIJob` migrates from `entity_type: str` + `entity_id: str` to a single
`poly_ref target [CohortAssessment, Manuscript, ...]` (target list = the real set the audit
records reference). Clean break per ADR-0003 — old columns removed, all read/write sites
updated in the same change, schema regenerated via Alembic (`dazzle db revision` /
`dazzle db upgrade`, ADR-0017). No back-compat columns, no dual-read. The teacher-facing
"AI cost for this cohort" region is then a declarative `list`/`summary` with `refresh:`,
retiring its custom poll renderer (the original aegismark motivation).

## 11. Testing (proof obligations)

- **Unit** — parse → IR (`poly_ref` field + `PolyPathCheck`); selector-required + uuid-pk +
  undeclared-branch validation errors; app-compile SQL shape; RLS-compile policy body **and**
  the degradation path; oracle output snapshot.
- **Integration (real Postgres)** — new fixture (extend `fixtures/scope_runtime` or add
  `fixtures/poly_scope`) with a poly_ref entity + per-type scope. Prove against live PG
  (`tests/integration/test_scope_runtime_pg.py` pattern):
  - teacher **sees** own-cohort `AIJob` rows;
  - teacher **does not** see peers' cohort rows (in-scope discriminator, out-of-scope subject);
  - teacher **does not** see Manuscript-typed rows (out-of-scope discriminator);
  - admin (`all`) sees everything within tenant; nothing leaks cross-tenant (tenant_fence).
- **Drift/docs** — grammar.md + DSL Quick Reference scope-forms list updated; counter-prior
  `polymorphic-associations` cross-links the safe `poly_ref` construct; CHANGELOG `Added` +
  an `Agent Guidance` note (when to reach for `poly_ref`, the selector-required rule, the
  oracle).

## 12. Non-goals (explicit; no silent caps)

- **Cross-type aggregate scoping** (one rule spanning multiple branches in a single
  aggregate) — deferred; multi-branch is repeated rules for now.
- **Non-uuid-pk targets** — explicitly unsupported (the constraint that deletes the cast).
- **Back-compat for raw `entity_type`/`entity_id`** — none; clean break.
- **Mixed-pk-type polymorphic refs** — out of scope.

## 13. Failure-modes rubric sign-off (CLAUDE.md gate)

1. *Which failure mode does this risk?* — 4GL "abstraction too complex to trace" / hidden
   semantics. 2. *Detector?* — FK-graph validation + `explain-scope` oracle + scope-runtime PG
   tests. 3. *Live?* — yes (validation runs at `dazzle validate`; oracle is a one-command read;
   PG tests gate CI). 4. *Trace runtime → DSL?* — yes, via the oracle. 5. *Preserve PG/auth/RLS
   semantics?* — yes; native RLS policy, app-layer only via the audited #1447 degrade path.
   The primitive may be marketed as a safe pattern **only once the oracle ships with it**.

## 14. Build sequence (for the implementation plan)

1. IR: `poly_ref` field kind + `PolyPathCheck` node (+ helpers).
2. Parser: field decl + `[Type]` scope-path selector (new `TokenType.POLY_REF`).
3. FK graph: conditional branch edges + `field[Type]` segment resolution.
4. Validation: the four `E_POLY_*` checks.
5. App compiler: `_compile_poly_path_check` (type-guard + uuid `IN` subquery).
6. RLS compiler: policy-mode emission + degrade-path coverage.
7. Oracle: `dazzle db explain-scope`.
8. Fixture + unit + real-PG integration tests.
9. AIJob dogfood adoption (clean break) + the teacher region retiring the poll renderer.
10. Docs/grammar/counter-prior/CHANGELOG + drift gates.
