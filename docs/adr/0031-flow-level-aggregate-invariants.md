# ADR-0031 — Flow-Level Aggregate Invariants for Atomic Flows

**Status:** Accepted 2026-06-01 (brainstormed + accepted same day; implementation tracked by #1318, IR-first per the staged convention).
**Issue:** #1318 (proposal). Follow-up to ADR-0029, which descoped cross-step aggregate invariants to this ADR.
**Relates:** ADR-0009 (predicate algebra — kept closed + row-scoped; this construct sits *beside* it, not inside it), ADR-0015 (TigerBeetle ledgers — owns the literal double-entry / conserved-quantity case; this construct is the non-ledger remainder), ADR-0017 (no DB-side logic — the invariant is enforced in the app's flow transaction, not a DB trigger/CHECK), ADR-0028 (guarded transactional actions), ADR-0029 (atomic flows as the transactional-intent substrate; invariants 5/6/8), #1316 (scope-parent `FOR SHARE` TOCTOU hardening — the lock philosophy this reuses; SERIALIZABLE struck there), #1306 (a prior decline of opening the closed algebra — the precedent this ADR honours).

## Decision

Admit a **distinct, flow-level `invariant:` construct** on the `atomic` block — **not** a seventh ADR-0009 predicate type. An atomic flow MAY declare one or more *aggregate invariants* that MUST hold at commit; if any fails, the whole flow rolls back (fail-closed, ADR-0029 invariant 6).

This is the categorically-different "aggregate over a set" shape that ADR-0009 deliberately cannot express. ADR-0009's six predicate types are all **row-scoped** — they compile to a per-row `WHERE` filter. An aggregate (`sum`/`count` over a set, compared to a bound) is a `HAVING`-shaped, set-level assertion. Rather than break ADR-0009's row-scoped invariant by adding a non-row-scoped member — and re-open the closed-algebra question that #1306 settled — the aggregate invariant lives in its **own construct** with its **own** fail-closed + validate-time-reject hardening. ADR-0009 stays closed and uniformly row-scoped; flow invariants and scope predicates remain conceptually distinct.

## What it expresses (v1)

A flow invariant is five declared, introspectable parts:

1. an **aggregate function** — `sum` or `count`,
2. a **target entity + field** (the field is omitted for `count`),
3. a **row-filter predicate** defining the set — this **reuses the existing ADR-0009 algebra** (`ColumnCheck` / `UserAttrCheck` / `PathCheck` / `BoolComposite` / …), anchored to a flow input or an above-created row,
4. a **comparison operator** — `=`, `<=`, `>=`, `<`, `>`,
5. a **right-hand bound** — a literal (`= 0`, `>= 2`, `<= 1000`) **or** a field on a flow-anchor row (`<= input.budget.total`).

Illustrative DSL (subject to refinement during implementation):

```dsl
atomic post_journal "Post a balanced journal entry":
  permit:
    execute: role(accountant)
  input txn: ref Transaction required
  ...

  # Conservation over the non-ledger remainder: this transaction's postings net to zero.
  invariant: sum(Posting.amount where transaction = input.txn) = 0

atomic allocate "Allocate against a budget":
  permit:
    execute: role(planner)
  input budget: ref Budget required
  ...

  # Dynamic cap against a related limit.
  invariant: sum(Allocation.amount where budget = input.budget) <= input.budget.total

atomic add_approver "Add an approver":
  ...
  # Quorum / cardinality.
  invariant: count(Approver where request = input.request) >= 2
```

The motivating shapes this covers: **conservation** (`sum = 0`), **fixed caps / quorums** (`<= 1000`, `>= 2`), and **dynamic caps against a related field** (`<= Budget.total`).

## Semantics & enforcement

- **When:** after all of the flow's steps have executed, **before** the flow transaction commits, on the flow's **own connection, in-transaction** (so the invariant sees this flow's just-written rows plus the committed baseline). One `SELECT <agg> … WHERE <filter>` per invariant.
- **Failure → rollback-all.** A failed invariant raises and the `atomic` executor's existing transaction context rolls the whole flow back (ADR-0029 invariant 6, fail-closed). The error is shaped like other flow denials — no internal SQL/aggregate value leaked beyond what the contract allows.
- **The set ranges over the full related set,** not only flow-touched rows: `sum(Posting.amount where transaction = input.txn)` includes pre-existing postings of that transaction, which is exactly what a conservation/cap check requires.

### Concurrency — the crux

An in-transaction aggregate check is only a *guarantee* if two concurrent flows mutating the same set cannot both pass. Under READ COMMITTED each flow is blind to the other's uncommitted rows, so two `allocate` flows on the same budget could each see the cap satisfied and both commit, busting it.

**Resolution (consistent with #1316, which struck the SERIALIZABLE hatch):** before computing the aggregate, take a row lock — `SELECT … FOR UPDATE` — on the invariant's **anchor row**: the single row the filter pins (the `Transaction`, the `Budget`). Two flows whose invariant ranges over the same set then **serialize** on that anchor row; the second computes its aggregate only after the first commits, seeing the first's rows. This makes row-anchored caps and conservation sound without SERIALIZABLE. Lock acquisition uses the same deterministic ordering as the #1316 scope-parent locks (entity name, then PK) so an atomic flow that takes both scope-parent and invariant-anchor locks cannot deadlock.

## Boundaries (load-bearing)

- **ADR-0015 — ledgers own true conservation.** Literal double-entry / conserved-quantity *money* domains stay in `ledger` / `transaction` (TigerBeetle, storage-level `debits = credits`, unbypassable). This construct is the **non-ledger remainder**: bounded caps, quorums, cardinality, and single-set sums over the general relational schema. It guards the **flow boundary, not storage**, so it is *bypassable by definition* — a direct `INSERT` outside an atomic flow is not subject to it. The ADR states this plainly: do **not** reach for a flow invariant to enforce financial conservation that has a real ledger home; reach for it for the general-LOB remainder a ledger would be overkill for.
- **ADR-0017 — no DB-side logic.** The invariant is enforced in the application's flow transaction (an explicit `SELECT` + comparison in the executor), **not** a Postgres trigger or `CHECK` constraint. It is declared in the DSL and analyzable, the opposite of opaque DB-side logic.
- **ADR-0029 invariant 8 — analyzability.** The invariant is a **declared, introspectable** predicate, surfaced to the same analysis layers as everything else (`rbac/` matrix, `testing/` conformance, the api-surface / specs audit), never imperative handler code. This is the whole reason it is a construct and not a hand-written postcondition: an unanalyzable "`CHECK` with extra steps" would re-open the hole ADR-0028 closed.

## Alternatives considered

1. **Admit `AggregateCheck` as a 7th ADR-0009 predicate type.** Rejected: it breaks ADR-0009's defining property (every predicate is a row-scoped `WHERE` filter), re-opens the closed-algebra question #1306 settled, and conflates "which rows can this principal see" (scope) with "does this set satisfy a bound" (invariant) — two different jobs.
2. **Decline entirely; keep conservation in the ledger and everything else as a DB `CHECK`.** Rejected for the general case: a `CHECK` can't express a cross-row aggregate against a dynamic related bound (`<= Budget.total`) without DB-side logic (ADR-0017), and ledgers are overkill (and wrong-shaped) for non-money caps/quorums. Declining leaves a real, recurring LOB need (allocation caps, approval quorums) with no analyzable home.
3. **SERIALIZABLE isolation for invariant-bearing flows.** Rejected: struck in #1316 — Dazzle's pooled READ COMMITTED runtime has no per-transaction isolation API, and the serialization-failure retry it requires conflicts with the no-compensation, single-shot atomic model.
4. **Post-commit check + compensating rollback.** Rejected: atomic flows have *no compensation* by definition (ADR-0029) — an invariant must be checked *before* commit, inside the transaction, or it isn't a guarantee.

## Honest limits / explicitly deferred (v1)

- **Aggregate functions** beyond `sum` / `count` (`min` / `max` / `avg`) — deferred until a concrete need.
- **Arithmetic / multi-term RHS expressions** (`<= budget.total - budget.committed`) — deferred; v1 RHS is a literal or a single anchor-row field.
- **Unanchored / global aggregates** (a sum with no single anchor row to lock — e.g. a tenant-wide cap with no parent row) — there is no single row to `FOR UPDATE`, so the concurrency guarantee does not hold. v1 **rejects** such invariants at validate time rather than silently shipping an unsound check; an advisory-lock mechanism for them is a possible follow-up.
- **Cross-entity aggregates** (an invariant spanning more than one target entity in one expression) — deferred; v1 is one aggregate over one entity's set.
- **Richer `where` filters.** v1 implements the set-defining filter as a bounded **conjunction of `<column> = (input.<name> | literal)` equalities** (`FlowInvariant.raw_filter`), enforced by building the `WHERE` SQL directly from those terms (input/literal values resolved against the flow inputs at runtime). This covers the motivating anchored aggregates. A full ADR-0009 `ScopePredicate`-compiled filter (FK paths, `EXISTS`, boolean composition) is a deliberately-deferred extension — v1 carries no compiled `filter_predicate` field (it would be permanently unread; YAGNI).

## Implementation sketch (gated on acceptance)

IR-first, mirroring the staged convention used across #1313–#1317:

1. **IR** — a `FlowInvariant` type (`agg_fn`, `entity`, `field`, `filter_predicate` [reuses the ADR-0009 predicate IR], `op`, `rhs` [literal | anchor-field ref]) + `AtomicFlowSpec.invariants: list[FlowInvariant]`.
2. **Parser** — an `invariant:` clause on the `atomic` block.
3. **Validator** — reject probe-impossible filters, unanchored aggregates (no lockable anchor), unknown entity/field, and type-mismatched bounds at link time (validate-time-reject, per #1306's hardening bar).
4. **Compiler** — compile the filter to the existing predicate-compiler SQL; assemble the `SELECT <agg> … WHERE <filter>` and resolve the RHS.
5. **Executor** — after the step loop, before commit: `FOR UPDATE` the anchor row(s) in deterministic order, run each invariant's aggregate `SELECT`, compare, and raise → rollback on failure.
6. **Analysis surface** — project flow invariants into the `rbac/` matrix view and the api-surface / conformance lenses so the declared guarantee is visible (ADR-0029 invariant 8).
7. **Verification** — real-Postgres tests in the `scope_runtime` family: in-bounds commits; out-of-bounds rolls back (incl. the pre-existing-rows case); and a concurrency test that two flows on the same anchor serialize and the cap holds.

## Consequences

- **Positive:** an analyzable home for the LOB aggregate-constraint remainder (caps, quorums, conservation-where-a-ledger-is-overkill); ADR-0009 stays closed and row-scoped; the guarantee is sound under concurrency via the established anchor-lock pattern; the boundary with the ledger is explicit, so this doesn't become "a worse TigerBeetle".
- **Negative / risks:** a new construct + its own hardening surface to specify and maintain; the anchor-lock adds contention on hot anchor rows (the Budget, the Transaction) — acceptable for the correctness it buys, and bounded to flows that actually declare an invariant; the bypassable-at-the-boundary nature must be communicated clearly so authors don't mistake it for storage-level enforcement.
