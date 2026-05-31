# ADR-0028 — Guarded Transactional Actions: Compose, Don't Add a Primitive

**Status:** Accepted (v0.80.62)
**Issue:** #1310 (proposal). Decomposes into #1311 (FK-path create-scope, the #1124 v2 unlock), #1312 (update-destination revalidation), and #1313 (extend `atomic` #1228).
**Relates:** ADR-0009 (predicate algebra), ADR-0010 (permit/scope separation), ADR-0025 (entity-level authorization)

## Decision

There is a real class of operation Dazzle's `permit:`/`scope:` model can't secure today: one whose authorization boundary is a **multi-hop FK path on the create/write path**, and/or which is a **multi-step transaction** that must be atomic and auditable (the canonical case: a department-scoped "reassign" that end-dates one row and creates another, guarded on the department of **both** the source and the destination).

Dazzle will **not** address this with a new top-level `action:` primitive, and will **not** introduce guards "evaluated in the handler" outside the predicate algebra. Instead, a guarded transactional action is the **composition** of three pieces, each on an existing trajectory, with the guard expressed as **algebra predicates** (ADR-0009), not imperative handler code:

1. **FK-path authorization on `create` — #1311 (the #1124 v2 unlock).** Lift the depth-1 limit on `scope: create:` via the already-roadmapped payload-time SQL probe, so `scope: create: teaching_group.department = current_user.department` works. This closes the spoofing hole **inside the algebra** — statically validated at link time, visible to the RBAC matrix and conformance.
2. **Re-validate the destination on `update` — #1312.** The update path today checks only the *pre-read of the existing row*; it never validates the *new* FK value the payload moves the row to. Add destination revalidation so an in-scope row cannot be moved **into** a foreign scope.
3. **Extend `atomic` (#1228), don't fork it — #1313.** `atomic` already owns the single-transaction, rollback-all, multi-step executor and route emission. Add (a) non-create step kinds (update / end-date), (b) optional entity binding (`self`), (c) routing of every step through scope enforcement so the FK-path guard applies to each touched entity, (d) an audit record, and (e) wiring `atomic_flows` into `rbac/`, `testing/`, and `specs/` (it is invisible to all three today).

**The security rules below are normative regardless of how the operation is implemented** (DSL `atomic`, a `# dazzle:implements` route override, or hand-written until the above lands).

## The gap (verified against the code, #1310)

Scope enforcement splits by operation:

- `read`/`list`/`update`/`delete` compile the predicate to SQL and **follow FK paths** (`predicate_compiler.py::_compile_path_check` → nested `IN (SELECT …)` subqueries).
- **`create` scope is payload-only and depth-1.** `scope_create_eval.py:113` raises on `PathCheck` depth > 1; the linker rejects FK-path/junction create-scope at link time (`RenderValidationError`). This is the documented #1124 v1 boundary; #1124 v2 (the "payload-time SQL probe") is the deferred unlock.

Two concrete failures follow, both confirmed in the runtime:

- **Denormalize-for-create-scope is spoofable.** Adding a settable `department` column + `scope: create: department = current_user.department` does **not** secure the boundary: `check_create_predicate` reads `payload.get("department")` **verbatim** with no FK-consistency derivation, so a client sends `department=mine` alongside `teaching_group=<foreign-dept class>` and the row lands in the wrong department. (The TOCTOU variant — a *trigger/generated-column* `department` populated after the app-layer check — is real in ordering but **hypothetical for Dazzle-native apps**: the DSL exposes no author-declarable DB-side scope-key derivation; it would require a hand-rolled trigger, itself an ADR-0017 violation. The spoofing argument alone condemns the workaround.)
- **`update`-scope never guards the destination.** There is no `_enforce_update_scope`; the update path pre-reads the *existing* row under the scope predicate, then passes the *new* payload to the service unchecked. A Head of Department whose existing row is in-scope can repoint its FK at another department's class and nothing re-validates the destination.

So neither half of a guarded "move" — the create of the destination, nor the repoint of the source — can be secured by generic CRUD scope today.

## Security rules for a guarded transactional action (normative)

A guarded transactional action **MUST**:

1. **Derive every scope key** (role, tenant/owner/department ids) **from the authenticated principal**, never from the request body. Client-supplied scope keys are spoofable.
2. **Validate the authorization boundary for *every* entity the operation touches** — source *and* destination — not only the row being mutated. (Guarding the source transition but not the destination create is the #1310 hole.)
3. **Execute in a single transaction** with an **optimistic-concurrency guard** (e.g. `is_current = TRUE` + rowcount), so a concurrent change can't interleave.
4. **Fail closed** and **never leak internal error detail** (no stack/SQL in the response; a denied boundary is indistinguishable from a missing row, per the IDOR-avoidance contract in `rbac-scope.md`).

A guarded action **MUST NOT** rely on a denormalized, client-settable scope key to satisfy depth-1 create-scope (spoofable, see above), and **SHOULD NOT** express its guard as imperative handler logic when the predicate algebra (extended per #1124 v2) can express it — keeping the guard in the algebra is what makes it visible to the RBAC matrix, conformance, and the API-surface audit.

## Why not a new `action:` primitive / in-handler guards

1. **It duplicates `atomic` (#1228), whose runtime already shipped.** `atomic` owns the single-transaction, rollback-all, multi-step executor + route emission. A parallel primitive fragments "multi-step transactional operation" into two overlapping constructs.
2. **`action` is already a loaded keyword** (`service`, `integration`, `surface`). An entity-bound `action` block overloads it — parser and agent-instruction cost for no semantic gain (cf. ADR-0027's keyword-overload objection).
3. **In-handler guards regress the predicate algebra (ADR-0009).** Dazzle's authorization is a statically-validated, SQL-compiled, matrix-visible predicate algebra *on purpose*. A guard "evaluated in the handler" re-introduces exactly the ad-hoc, unanalyzable authz the algebra replaced — invisible to the matrix/conformance/api-audit unless hand-wired. The fix for "the algebra can't express FK-path create-scope" is to **extend the algebra (#1124 v2)**, not to escape it.
4. **It bundles two distinct, independently-solvable gaps** (FK-path create authz; multi-step atomic mutation) into one feature, obscuring that each has a cleaner, narrower answer.

## Consequences

- **Positive:** the capability lands within the existing formal model — guards stay statically validated and matrix-visible; no keyword overload; no second "transactional op" construct; the incidental update-destination security gap gets fixed on its own merits.
- **Negative:** the capability is gated on #1124 v2 (FK-path create-scope), which was deferred "until adoption signal" — #1310 *is* that signal, but it is non-trivial (a payload-time SQL probe). Until it lands, projects either denormalize **and** validate FK-consistency server-side, or hand-roll a route that follows the rules above (a `dazzle.back.runtime.guarded_action` helper for the auth + transaction + optimistic-concurrency + fail-closed boilerplate is a reasonable bridge, framed as interim — not the destination).
- **Neutral:** `atomic` becomes the home for guarded multi-entity mutations; its current invisibility to `rbac/`/`testing/`/`specs/` is a pre-existing gap that this work closes.

## Alternatives Considered

1. **A declarative `action:` primitive with in-handler guards (the #1310 proposal, Option A).** Rejected — see "Why not" above: duplicates `atomic`, overloads `action`, escapes the algebra.
2. **Re-parent everything onto the state machine** (model the move as a guarded transition). Rejected — `TransitionGuard.guard_expr` only sees the in-memory row (no DB lookup, only a scalar `current_user`, so it can reach neither the destination's FK path nor `current_user.department`), and transition-effect creates bypass scope enforcement. The state machine is the right model for the *source* transition but is structurally single-row.
3. **Bless denormalization for create-scope.** Rejected — spoofable (verified); documented here as an anti-pattern.

## Implementation status

- **#1311 (FK-path + EXISTS create-scope) — shipped.** `scope: create:`
  now accepts `PathCheck` depth > 1 and `ExistsCheck` / `NotExistsCheck`,
  resolved by a payload-time SQL probe (`scope_create_eval` hybrid walker +
  `predicate_compiler.compile_path_check_probe` /
  `compile_exists_check_probe`, run via `route_generator.build_create_scope_probe`).
  The link-time check now only rejects a pathologically deep FK path
  (> 4 hops). The override path (`policy.check_entity_op`) builds the same
  probe from the entity's service. The guard stays in the algebra (ADR-0009).
- **#1312 (update-destination revalidation)** and **#1313 (extend `atomic`)**
  — pending; both compose with the #1311 probe for their FK-path halves.

## Cross-reference

`docs/reference/rbac-scope.md` documents the create-scope hybrid walker (in-Python simple leaves + payload-time probe for FK-path / EXISTS) and points the denormalization anti-pattern at this ADR as the sanctioned alternative.
