# ADR-0042 — `poly_ref`: the realized polymorphic-ref escape hatch

**Status:** Accepted (#1448)
**Issue:** #1448 (AegisMark lens)
**Supersedes (in part):** ADR-0027 — realizes its pre-committed escape hatch
**Builds on:** ADR-0009 (predicate algebra), #1447 (RLS app-layer degradation)

## Decision

Dazzle ships a typed `poly_ref` field primitive and a `field[Type].path`
scope-path selector, enabling **declarative, statically-validated, scope-composable**
polymorphic references. This **realizes the escape hatch ADR-0027 pre-committed** —
it is not a reversal of it.

```dsl
entity AIJob "AI gateway audit record":
  id: uuid pk
  subject: poly_ref [CohortAssessment, Manuscript]   # → subject_type text + subject_id uuid

  permit: read as: teacher
  scope:  read: subject[CohortAssessment].uploaded_by = current_user  as: teacher
  permit: read as: admin
  scope:  read: all  as: admin
```

## Why this is ADR-0027 firing, not reversing it

ADR-0027 closed the `polymorphic_ref:` keyword **"now or planned"** but explicitly
pre-committed the shape and the trigger:

> "If a future use case appears that genuinely requires polymorphic association
> *after surviving the four-question interrogation*… the implementation shape is
> pre-committed to an explicit-discriminator block with a visible discriminator
> field and an exhaustive targets list. **Build it when the interrogation fails,
> not before.**"

That event has now occurred. **AegisMark** — named in ADR-0027 as a consumer that
"models around it" — hit `AIJob` (the AI-gateway audit entity): an entity that
*references* one of several domain entities (a cohort assessment, a manuscript)
and must be **visible to the non-admin persona who owns the referenced entity**.

The four-question interrogation (ADR-0027) on `AIJob`:
1. **UI-driven?** No — a real scope-by-reference need, not rendering convenience.
2. **Event, not reference?** This is the close one, and it *passes*: `AIJob` is an
   audit/gateway event entity, exactly ADR-0027's Q2 case where the `(type, id)`
   pair is **already sanctioned** ("acceptable in an event-stream entity because
   events don't need referential integrity"). The new need is not the pair — it's
   making the *already-sanctioned* pair **scope-composable**.
3. **Junction in disguise?** No — not N:M.
4. **TPT?** No — `AIJob` is not an IS-A of its subjects; the payload (cost, tokens)
   is identical regardless of subject type.

Mutex refs (the ≤3 residue) don't fit: the gateway references an open, growing set
of subject types. So the interrogation fails as designed, the issue was filed
(#1448), and the pre-committed shape is built.

## How it resolves ADR-0027's three contracts

ADR-0027 flagged three contracts the naive pattern breaks. The typed primitive
addresses each:

- **Scope composition (the load-bearing one).** ADR-0027: "RBAC scope rules can't
  traverse a `(type, id)` pair… the predicate algebra is built on typed traversal;
  polymorphic FKs are an opaque hole in it." The `field[Type]` **branch selector
  closes the hole**: it names the target at authoring time, so the predicate
  compiles to a normal typed subquery rooted on that target —
  `subject_type = 'CohortAssessment' AND subject_id IN (SELECT id FROM cohort_assessment WHERE <sub>)`.
  The hole is no longer opaque; each branch is a statically-validated typed path.
- **Referential integrity.** Still no single multi-table FK (impossible in SQL).
  But the targets are validated at link time (must exist + be **uuid-pk**), the
  discriminator is a real visible column (`subject_type`), and `subject_id` is a
  real `uuid` (no text cast). This is the same integrity posture ADR-0027 already
  sanctioned for event-stream entities — now made declarative.
- **JOIN queries.** Per-branch typed subqueries; the planner sees through each
  selected branch. Cross-branch is repeated scope rules (boolean-OR union), not
  application-side dispatch.

## Deviation from ADR-0027's pre-committed surface

ADR-0027 sketched a `polymorphic_ref:` *block* with an explicit `discriminator:`
field. The shipped surface is a `poly_ref name [T1, T2]` *field*. The deviation is
deliberate and stays faithful to ADR-0027's two hard rejections:

- **Not `ref X | Y | Z` union sugar** (0027's outright rejection): `poly_ref` is a
  distinct keyword, never an overload of `ref`.
- **Discriminator stays visible and queryable** (0027's objection to hidden
  discriminators): the field expands to a real `name_type text` column an author
  can filter on directly; it is not hidden.

The field form is terser than a block and composes with the existing field-modifier
grammar (`required`, etc.); the exhaustive `targets:` list is the `[T1, T2]` bracket.

## Traceability gate (the price of the primitive)

Per the Model-Driven Failure-Modes rubric, a model abstraction is acceptable only
if its runtime is traceable back to the DSL. `poly_ref` ships **with** the
`dazzle db explain-scope <Entity> <verb>` oracle, which prints the predicate tree,
the compiled app-layer WHERE, and the RLS policy body (or the #1447 degradation
reason + verdict). A human can't hand-author the type-guarded subquery but can
verify it in one command.

## Scope (MVP) and non-goals

- **Supported:** `read` / `list` / `delete` scopes; targets must be uuid-pk;
  multi-branch via repeated rules; app-layer + RLS-policy compilation with #1447
  degradation; the `explain-scope` oracle.
- **Non-goals (rejected loudly, not silently):** `create` / `update` poly scopes
  (raise `E_POLY_VERB_UNSUPPORTED` at validate time — they need a payload-time
  probe; the motivating gateway creates rows as admin); nullable `poly_ref`;
  non-uuid-pk targets; poly_ref on subtype tables; cross-branch aggregate scoping;
  the framework-`AIJob` adoption (needs app-derived dynamic target sets — follow-on).

## Consequences

- ADR-0027 is **superseded in part**: its blanket "now or planned" closure is
  replaced by "closed except via the validated typed `poly_ref` construct."
- The `W_LOOKS_POLYMORPHIC` warning now names `poly_ref` as the preferred
  declarative fix for a hand-rolled `*_type` enum + `*_id` uuid pair.
- `poly_ref` is now a Counter-Prior **safe construct**: the catalogued
  `polymorphic-associations` pathology has a sanctioned, scope-safe escape.
