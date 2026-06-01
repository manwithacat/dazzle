# ADR-0032 — Lifecycle Transition → Atomic Flow Seam

**Status:** Accepted 2026-06-01 — **implemented (Slices A+B)** (#1319). Slice A (surface): `invoke_flow` IR + parser + validator + the `execute_atomic_flow_on_conn` seam + a state-machine fixture (v0.80.79). Slice B (shared-transaction hot-path): `repository.update(conn=...)` connection-injection, `CRUDService.update` interception (`_update_with_invoke` runs the status write + the flow on one connection), `AuthContext` threaded through `route_generator._core`, `access_specs`/`fk_graph` wired onto each service via `set_invoke_context`, `AtomicFlowError → 403/400`, fail-closed without a principal. Real-PG-verified atomicity (commit-together / roll-back-together) and adversarially reviewed (hot-path non-regression + atomicity confirmed sound; three findings fixed). **v1 limits:** invoke is rejected at validate time on `auto` transitions (no principal — service-principal deferred) and on soft-delete / temporal / subtype-polymorphic entities (the shared read-back is a plain SELECT). ADR-0020 remains Proposed; the transition runtime exists regardless.
**Issue:** #1319 (proposal). The seam flagged open in both ADR-0029 and ADR-0020.
**Relates:** ADR-0020 (lifecycle evidence predicates / state-machine transitions — owns the source transition + its guard; this ADR is the effect hand-off), ADR-0029 (atomic flows as the transactional-intent substrate — the invoked effect; invariants 1/2/6), ADR-0028 (guarded transactional actions), ADR-0009 (predicate algebra — the per-step scope the effect rows are enforced against), #1313 (per-step scope-enforced atomic create/update — the effect machinery, shipped v0.80.67–.77).

## Decision

A lifecycle / state-machine **transition** may carry a multi-row side-effect by **synchronously invoking a named atomic flow inside the transition's own database transaction**. The entity's status write and the invoked flow's steps commit together or roll back together — true atomicity. This is the hand-off ADR-0029 anticipated: the **process owns the transition and its guard**; when the transition fires, it **invokes an atomic** that carries the multi-row effect, each step scope-enforced (#1313).

A transition-with-effects is therefore *one atomic intent*: "move the entity to state Y **and** write these effect rows, or do neither." Routing the effect through `atomic` (rather than ad-hoc handler writes) is meaningful precisely because it is atomic with the status change and each effect row is scope-guarded and analyzable.

## Binding & DSL

A transition declares an `invoke:` effect referencing an atomic flow by name, with an **explicit input map** (illustrative — refined during implementation):

```dsl
transition submitted -> fulfilled:
  guard: ...                                  # ADR-0020 owns this
  invoke fulfil_order(order: self, warehouse: input.warehouse)
```

- `self` resolves to the **transitioning entity row**.
- Remaining flow inputs map from transition-supplied values (the `input.*` of the transition action).
- Input binding is **explicit**, not convention/auto-bound by name: it is analyzable (the validator checks every *required* flow input is bound, and that bound values type-match), and it avoids the name-collision ambiguity of auto-binding. This matches the agent-first "precision over ergonomics" DSL philosophy (ADR-0004).

## Division of responsibility (with ADR-0020)

| Concern | Owner | Gate |
|---------|-------|------|
| *May this transition fire?* | the process / state machine (ADR-0020 evidence predicate / state-machine guard) | the transition guard |
| *Is each effect row permitted for the principal?* | the invoked atomic flow (#1313) | per-step `scope: create:` / `scope: update:` |

Both apply in one transaction. A flow per-step **scope denial rolls back the whole transition** — the status stays unchanged, IDOR-shaped (fail-closed, ADR-0029 invariant 6). The transition guard and the flow scope are *complementary*, not redundant: the guard decides the state change; the scope decides the effect rows; neither subsumes the other.

## Principal

The invoked flow runs as the **triggering user**; each effect step's scope keys are derived from that principal (ADR-0029 invariant 1 — never from the payload).

A transition with **no user principal** — fired by a schedule or a background process — that invokes a **scope-enforced** atomic flow is a **link/validate-time error**. You cannot have an unauthenticated guarded effect, and the framework will not silently create an unscoped write path (consistent with the codebase's standing refusal to do so — cf. the #1317 strict-audit null-principal handling, which records rather than drops, but does not bypass scope). The author must make the transition user-triggered, or the effect must use a different mechanism.

The **system / service-principal** story — a declared service identity with its own scope grants, so a *scheduled* transition-with-effects can run guarded — is a real future need but a larger surface (declaring the identity, granting it scope, auditing it). It is **explicitly deferred** to a follow-up ADR.

## Transaction wiring

For an `invoke:`-bound effect, the transition runtime opens **one transaction** spanning the entity status `UPDATE` and the invoked flow's steps, committing on clean exit and rolling back on any failure (the atomic executor's existing transaction-context behaviour, extended to enclose the status write). This **replaces today's post-commit best-effort model** (`TransitionEffectRunner` firing effects via an `on_updated` callback after commit) **for invoke-bound flows specifically**; the existing post-commit/async effects path remains for genuinely-decoupled effects.

The triggering principal's `AuthContext` + the per-entity access-specs + FK graph must be threaded from the transition execution path into `execute_atomic_flow` — ADR-0029's implementation findings note these are **not** middleware-exposed in the transition path today, so wiring that through is part of the work (a non-HTTP invocation entry point for the executor, which already accepts `auth_context`/`access_specs`/`fk_graph`).

## The `hless` alternative (documented, out of scope)

For genuinely **decoupled, eventually-consistent** downstream effects — notifications, read-model projections, cross-bounded-context fan-out — the right shape is the transition emitting an `hless` event that a flow (or other subscriber) reacts to in its **own** transaction. That is deliberately **not** atomic with the transition: the status commits, and the effect happens later (with its own retry / dead-letter). This ADR does **not** route the guarded transition-with-effects through `hless`, because the async path reintroduces the compensation/partial-failure problem ADR-0029 exists to avoid for schema-local atomic intent. The two mechanisms are complementary: `invoke:` for atomic schema-local effects, `hless` for decoupled downstream reactions.

## Alternatives considered

1. **Async via `hless` event for the guarded effect.** Rejected for this seam (see above): not atomic with the transition; reintroduces compensation. Retained for decoupled effects.
2. **Synchronous but separate transaction** (today's post-commit `on_transition` model). Rejected: forfeits the atomicity that is the entire reason to route the effect through `atomic` — the status could commit while the effect fails, leaving a half-applied transition with no compensation.
3. **Auto-bind flow inputs by name** from the transitioning entity. Rejected: magic, ambiguous on name collisions, harder to analyze; explicit binding is the agent-first choice.
4. **Run system-triggered transition effects unscoped.** Rejected: creates an unscoped write path (security smell); validate-time rejection + a deferred service-principal story is the fail-closed choice.

## Honest limits / explicitly deferred

- **System / service principal** for scheduled (no-user) transitions-with-effects — deferred to its own ADR (identity declaration, scope grants, audit).
- **Multiple `invoke:`s per transition** / ordering between them — v1 is one invoked flow per transition; multiple effects compose later (or via one flow with multiple steps).
- **Re-entrancy** (an invoked flow whose steps themselves trigger transitions that invoke flows) — out of scope; the validator should reject or bound it rather than allow unbounded nesting.
- This ADR depends on **ADR-0020 reaching Accepted** for the transition-guard half; it is written to be confirmed *jointly* with ADR-0020.

## Implementation sketch (gated on acceptance + ADR-0020 confirmation)

1. **IR** — a transition `invoke` effect: `{flow_name, input_bindings: {flow_input → source (self | transition input | literal)}}`, on the transition/`StateTransitionSpec`.
2. **Parser** — the `invoke <flow>(<bindings>)` clause on a transition.
3. **Validator** — flow exists; every required flow input bound; bound types match; `self` resolves to the transitioning entity; **reject** an `invoke` of a scope-enforced flow from a transition with no user-principal path.
4. **Runtime** — a non-HTTP `execute_atomic_flow` entry point invoked from the transition runner inside the status-write transaction, threading the triggering `AuthContext` / access-specs / FK graph; replace the post-commit path for invoke-bound effects.
5. **Analysis surface** — project transition→flow invocations into the `rbac/` matrix / api-surface so the effect grant path is visible (ADR-0029 invariant 8).
6. **Verification** — real-Postgres tests: transition + effect commit together; a flow scope denial rolls the transition back (status unchanged); a no-principal transition invoking a guarded flow fails at validate time.

## Consequences

- **Positive:** a guarded, atomic, analyzable transition-with-effects — the status change and its multi-row consequences succeed or fail as one unit, each effect row scope-enforced; a clean division with ADR-0020 (guard vs effect-scope); an explicit boundary between atomic (`invoke:`) and decoupled (`hless`) effects.
- **Negative / risks:** threading the principal/access-specs into the transition path is new wiring (ADR-0029 flagged it absent); replacing the post-commit effect model for invoke-bound flows is a behaviour change to the transition runtime; scheduled transitions-with-effects are blocked until the deferred service-principal ADR lands — an accepted limitation for v1.
