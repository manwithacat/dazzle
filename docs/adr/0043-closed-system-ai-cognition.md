# ADR-0043 — Closed-system AI cognition: every AI call has a governed subject

**Status:** Accepted (#1454)
**Issue:** #1454
**Builds on:** ADR-0042 (`poly_ref` + scope selectors, #1448/#1455), ADR-0003 (clean breaks), ADR-0017 (Alembic), ADR-0008 (PostgreSQL-only)

## Decision

Dazzle AI cognition is a **closed, governed system**. Every AI call is declared
through exactly two surfaces, and every call carries a typed, auditable,
scope-able subject. There is no unaudited AI path by construction.

The invariant is structural, not aspirational: **you cannot invoke AI cognition
without going through a subject-bearing surface, and you cannot persist an
`AIJob` without a subject.**

## Context and problem

The failure mode this exists to prevent has a precise signature: **an `AIJob`
with no subject.** A subjectless AI call is one the framework executed but
cannot attribute, scope, or govern. Each such call is a step toward "skip the
framework, write a script" — AI work accreting as out-of-framework, unaudited
background jobs.

Before this decision, the framework offered three ways to invoke AI:

| Path | Subject | Risk |
|------|---------|------|
| `llm_intent` trigger on an entity | stringly-typed `entity_type`/`entity_id` columns | nullable, ungoverned |
| Process step `kind: llm_intent` | none | no attribution possible |
| `POST /execute/{intent_name}` | none | arbitrary intent, no subject — the script-accretion surface |

The `POST /execute/{intent_name}` route was the most dangerous surface: it ran
an arbitrary intent with arbitrary input and no subject. It was removed.

## The two declared surfaces (the only app-facing AI paths)

| Surface | How declared | `AIJob.subject` |
|---------|--------------|-----------------|
| **Trigger-driven** | `llm_intent` with `trigger.on_entity: X` (+ `on_event:`, `input_map:`) | the entity `X` |
| **Process/task-driven** | a `process` step with `llm_intent: <name>` (+ `input_map:`) | the **ProcessRun** executing it |

The direct executor (`llm_executor.execute`) and queue (`llm_queue.submit`)
become internal plumbing both surfaces call through — not reachable from app
DSL or a generic HTTP route.

## `AIJob.subject` — required `poly_ref`

The framework-injected `AIJob` entity drops the stringly-typed
`entity_type: str(200)` + `entity_id: str(200)` pair (clean break, ADR-0003)
and gains a required `poly_ref` field:

```
subject: poly_ref [ <derived target set> ] required
  → subject_type text NOT NULL + subject_id uuid NOT NULL
```

- **Required, not nullable.** No NULL invariant: every persisted `AIJob` names a subject.
- **Target set derived at link time, never authored.** A pure linker function
  over the linked `AppSpec` computes:

  ```python
  targets = sorted(
      {t.on_entity for intent in appspec.llm_intents for t in intent.triggers if t.on_entity}
      | ({"ProcessRun"} if any process has an llm_intent step else set())
  )
  ```

  Targets are validated by the ADR-0042 rules (must exist, must be uuid-pk).

- **Scope-composable uniformly** via the ADR-0042 selector:
  - `subject[EntityName].owner_field = current_user` (trigger surface)
  - `subject[ProcessRun].started_by = current_user` (process surface)

  One mechanism, two referent kinds. Verify with
  `dazzle db explain-scope AIJob <verb>`.

## Removing the bare path

`llm_routes.py`'s `execute_intent` route and the `IntentExecuteRequest`/
`IntentExecuteResponse`/`AsyncJobResponse` models it used are **deleted**.
A guard test (`tests/unit/test_no_bare_llm_route.py`) asserts the route stays
gone. The executor and queue raise `ValueError` on a missing or empty subject —
fail-loud at the call site, never a NULL `AIJob` row.

## ProcessRun — the run referent

A process `llm_intent` step's subject is a **`ProcessRun`** — a
framework-injected, uuid-pk, `started_by`-anchored entity persisted as a real
PostgreSQL table (ADR-0008). It is injected into the app schema whenever any
process has an `llm_intent` step. A user-declared `ProcessRun` entity in the
same app raises a collision `LinkError` at validate time (the governed one wins).

The `started_by` anchor makes scope composition expressible:
`subject[ProcessRun].started_by = current_user` — the run's initiating user
gates access to the AI jobs it produced.

Note: the process-step AI executor (`http/runtime/process_executor.py`) is not
yet request-mounted (pre-existing limitation). Follow-on #1457 tracks the
celery process backend deprecation.

## Fail-loud enforcement

- `llm_queue.submit` and `llm_executor.execute` raise `ValueError` on a missing
  or empty subject. The trigger dispatcher and process-step executor are the
  only callers; both supply a subject.
- Validation error `E_AIJOB_NO_SUBJECT_SURFACE` fires when `llm_config` is
  present but no trigger or process declares a subject surface — fail-loud, not
  a silent unusable entity.
- `tests/unit/test_no_bare_llm_route.py` asserts no route mounts a generic
  intent-execution endpoint.

## Migration / blast radius

This changes the injected `AIJob` schema for **every `llm_config` app**:
`entity_type`/`entity_id` are dropped; `subject_type`/`subject_id` (both NOT
NULL) are added. Clean break per ADR-0003; Alembic-managed per ADR-0017. No
back-compat columns; downstream apps regenerate migrations.

Historical `AIJob` rows with NULL subject columns are not migrated to inferred
subjects — this is a greenfield clean break.

## Consequences

- **Every AI call is auditable and scope-able** by construction. Audit, cost,
  and RBAC are derived consequences of the subject — not additional work.
- The `poly_ref` target set grows automatically as more `llm_intent` triggers or
  process steps are added; no manual maintenance.
- `ProcessRun` becomes a first-class framework entity, making process runs
  scope-able and queryable by initiating user.
- The `POST /execute/{intent_name}` surface is permanently gone; apps that need
  operator-initiated AI route through a process step, gaining a `ProcessRun`
  subject.
- Known follow-on: process-step AI executor not yet request-mounted (#1457).

## Failure-modes rubric sign-off (CLAUDE.md gate)

1. **Failure mode risked:** the catalogued "AI as ungoverned side-scripts" — AI
   work that accretes outside the framework's attributable, scopeable, auditable
   model.
2. **Detector:** the required-subject schema (NOT NULL), the no-generic-route
   guard (`test_no_bare_llm_route.py`), and the executor/queue subject assertion
   (`ValueError` on missing subject).
3. **Live?** Yes — schema-enforced (NOT NULL columns + required `poly_ref`
   validation), boot/validate guard (`E_AIJOB_NO_SUBJECT_SURFACE`), CI test.
4. **Trace runtime → DSL?** Yes — `dazzle db explain-scope AIJob <verb>` shows
   the subject scope; the `subject_type` discriminator names the declaring
   surface (entity name or `ProcessRun`).
5. **Preserve semantics?** Yes — RBAC composes through the subject's own scope
   (entity's access rules or process run's `started_by` anchor); no side-channel.

This pattern may be described as the safe AI-integration pattern for Dazzle apps
now that the invariant is schema-enforced, guard-tested, and documented.

## Related

- [ADR-0042](0042-poly-ref-scoping.md) — `poly_ref` primitive + scope selectors
- [ADR-0027](0027-no-polymorphic-ref.md) — the interrogation that poly_ref realizes
- [ADR-0003](0003-clean-breaks.md) — clean breaks; no compat shims
- [ADR-0017](0017-schema-migrations-via-alembic.md) — all schema changes via Alembic
- [ADR-0008](0008-postgresql-only.md) — PostgreSQL is the sole database
