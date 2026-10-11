# Closed-system AI cognition: governed `AIJob` subjects (#1454)

**Status:** Design approved (2026-06-22), ready for implementation plan.
**Issue:** #1454 (aegismark lens). **Builds on:** #1448/#1455 (`poly_ref` + scope + create probe), ADR-0042.
**Disposition:** Large — framework-schema change + a closed-surface invariant. Spec saved; #1454 stays open for the implementation plan.

---

## 1. The principle

**Dazzle AI cognition is a closed, governed system. Every AI call is declared through exactly two surfaces, and every call carries a typed, auditable, scope-able subject. There is no unaudited AI path by construction.**

The failure mode this exists to prevent — AI work accreting as out-of-framework, unaudited, uncontrolled background scripts — has a precise signature in this codebase: **an `AIJob` with no subject.** A subjectless AI call is one the framework executed but cannot attribute, scope, or govern; each one is a step toward "skip the framework, write a script." So the invariant is structural, not aspirational: **you cannot invoke AI cognition without going through a subject-bearing surface, and you cannot persist an `AIJob` without a subject.**

This is a non-obvious enterprise-architecture pattern; it ships with an explainer (ADR + `docs/architecture/`) — see §8.

## 2. The two declared surfaces (and the one we remove)

| Surface | How declared | `AIJob.subject` |
|---------|--------------|-----------------|
| **Trigger-driven** | `llm_intent` with `trigger.on_entity: X` | the entity `X` (`subject[X]`) |
| **Process/task-driven** | `process` step `kind: llm_intent` | the **run referent** (§5) |
| ~~Bare/ad-hoc~~ | ~~`POST /execute/{intent_name}`~~ | **removed** (§4) |

The two surfaces are the *only* app-facing ways to invoke AI. The direct executor (`LLMIntentExecutor.execute`) becomes **internal plumbing** both surfaces call through — never reachable from app DSL or a generic HTTP route.

## 3. `AIJob.subject` becomes a required `poly_ref`

The framework-injected `AIJob` entity drops the stringly-typed `entity_type: str(200)` + `entity_id: str(200)` pair and gains:

```
subject: poly_ref [ <derived target set> ] required
  → subject_type text not null + subject_id uuid not null
```

- **Required, not nullable** — the no-NULL invariant (§1). Every persisted `AIJob` names a subject.
- **Target set is derived at link time, never authored** (§5).
- **Scope-able uniformly** via the #1448 selector — `subject[Manuscript].uploaded_by = current_user`, `subject[JobRun].started_by = current_user` — one mechanism, two referent kinds. The teacher-sees-their-cohort's-AI-cost case (#1448's motivation) and the marking-run-cost case both fall out.

Clean break (ADR-0003): old columns removed, all read/write sites updated, schema regenerated. This changes the injected `AIJob` schema for **every** `llm_config` app — see §7.

## 4. Removing the bare path (`POST /execute/{intent_name}`)

`llm_routes.py`'s `execute_intent` route (and the `IntentExecuteRequest`/`AsyncJobResponse` shapes it serves, if unused elsewhere) is **deleted**. Rationale: it runs an arbitrary intent with arbitrary input and **no subject** — the script-accretion surface. Apps invoke AI only via (a) an entity trigger or (b) a process `llm_intent` step.

Enforcement that the door stays shut:
- **`LLMIntentExecutor.execute` / the queue `submit` require subject context** (a `(subject_type, subject_id)` pair). A call without it raises — fail-loud at the call site, never a NULL `AIJob` row. The trigger dispatcher and the process-step executor both supply it; there is no other caller.
- A `test_no_*` guard asserts no route mounts a generic intent-execution endpoint (so it can't silently return).

> **Open verification for the plan:** confirm no current consumer (examples, AegisMark, tests) depends on `POST /execute/{intent_name}` as a real feature vs. a demo. If a legitimate "operator runs an intent" need exists, it routes through a process (giving it a `JobRun` subject), not a bare endpoint.

## 5. The run referent for process/task AI

A process `llm_intent` step's subject is the **run** executing it — a uuid-pk, RBAC-scoped framework entity, so `poly_ref` targets it and scope composes (`subject[<Run>].started_by = current_user`).

`JobRun` (`linker.py:1083`, injected when jobs are present) is the candidate. The plan must resolve:
- **Is a process `llm_intent` step's execution recorded as a `JobRun` row (uuid pk, in the app Postgres), or in a separate process-instance store?** `poly_ref` requires the referent be a uuid-pk entity in the app schema.
  - *If `JobRun` (or an injected `ProcessRun`) is that entity:* the process-step executor sets `subject = (that entity, run_id)`; the entity joins `AIJob.subject`'s target set whenever any process has an `llm_intent` step.
  - *If process runs live outside the app schema:* either (a) inject a uuid-pk `ProcessRun` app entity for AI-bearing processes (recommended — it makes runs first-class + scope-able, serving the governance goal directly), or (b) fall back to the process's **anchor entity** as the subject. (a) is preferred; it's the same move that made `AIJob` first-class.
- The run entity needs a scope anchor (`started_by` / initiating user, or the tenant/cohort it operates within) so `subject[Run].<anchor> = current_user` is expressible.

## 6. Link-time target derivation

A pure function over the linked `AppSpec`, injected into `AIJob.subject.poly_targets`:

```
targets = { t.on_entity for intent in appspec.llm_intents for t in intent.triggers if t.on_entity }
if any(step.kind == LLM_INTENT for process in appspec.processes for step in process.steps):
    targets |= { <run referent entity name> }   # §5
```

- Deterministic, order-stable (sorted).
- Targets validated by the #1448 rules (exist, uuid-pk).
- If `llm_config` is present but `targets` is empty (LLM configured, no triggers/steps yet), `AIJob` is still injected; with a required subject and no legal target, that's a **validation error** (`E_AIJOB_NO_SUBJECT_SURFACE`) telling the author to declare a trigger or process step — fail-loud, not a silent unusable entity.

## 7. Migration / blast radius

- The injected `AIJob` schema changes for **every** `llm_config` app: `entity_type`/`entity_id` → `subject_type`/`subject_id` (required). Clean break (ADR-0003), Alembic-regenerated (ADR-0017).
- Runtime write sites updated in the same change: `llm_trigger` (entity → subject), the process-step executor (run → subject), `_record_job` / `llm_queue.submit` (subject required, threaded from the caller).
- Historical `AIJob` rows with NULL `entity_type`/`entity_id` (the old process/direct paths): a greenfield clean break drops/recreates; document that downstream apps re-migrate. No back-compat columns.

## 8. Documentation (post-implementation, required)

The pattern isn't recognisable without enterprise-architecture context, so the deliverable includes:
- **An ADR** — "Closed-system AI cognition: every AI call has a governed subject" — the invariant, the two surfaces, why the bare path is removed, the subject-as-governance-unit principle.
- **A `docs/architecture/` explainer** — the founder/agent-facing narrative: declare AI via a trigger or a process step; audit, cost, and RBAC are derived consequences; there is no third path.
- **Agent Guidance** (CHANGELOG) — "to add AI cognition, declare an `llm_intent` trigger on an entity or an `llm_intent` process step; never a bare call. The AI audit trail (`AIJob`) scopes by the subject automatically."

## 9. Testing (proof obligations)

- **Unit** — target derivation (trigger `on_entity` ∪ run referent); `AIJob` injected with a required `poly_ref subject`; the empty-target validation error; the executor/queue raising on missing subject; the no-generic-execute-route guard.
- **Integration (real Postgres)** — (a) a trigger AI job → `subject = entity`, scoped to the entity's owner; (b) a process `llm_intent` step AI job → `subject = run referent`, scoped to the run's initiator; (c) every persisted `AIJob` has a non-null subject (the invariant); (d) no bare-execute route is mounted.

## 10. Non-goals

- Multi-subject AI jobs (one call about several entities) — single subject per call.
- Per-token / streaming sub-call attribution — the `AIJob` is the unit.
- Migrating historical NULL-subject rows to inferred subjects — clean break.

## 11. Failure-modes rubric sign-off (CLAUDE.md gate)

1. *Failure mode risked:* the catalogued "AI as ungoverned side-scripts." 2. *Detector:* the required-subject schema + the no-generic-route guard + the executor subject-assertion. 3. *Live?* yes — schema-enforced (NOT NULL), boot/validate guards, CI test. 4. *Trace runtime → DSL?* yes — `dazzle db explain-scope AIJob <verb>` shows the subject scope; the subject names the declaring surface. 5. *Preserve semantics?* yes — RBAC composes through the subject's own scope (entity or run); no side-channel. The pattern may be marketed as the safe AI-integration pattern once the invariant is schema-enforced + documented.

## 12. Build sequence (for the plan)

1. `AIJob` injection: `subject` required `poly_ref` (drop `entity_type`/`entity_id`) + the link-time target-derivation function (§6) + the empty-surface validation error.
2. Resolve & wire the run referent (§5) — likely inject/confirm a uuid-pk `ProcessRun` (or use `JobRun`) with a scope anchor; process-step executor sets `subject = (run, id)`.
3. Trigger path: set `subject` from `on_entity` (rename from entity_type/entity_id).
4. Remove `POST /execute/{intent_name}`; make `executor.execute`/`queue.submit` require subject; add the no-generic-route guard.
5. Real-PG integration proof (trigger + process + invariant + no-route).
6. ADR + architecture explainer + CHANGELOG Agent Guidance.
7. Drift/baselines: ir-types, api-surface (route removed), docs-drift, regenerate AIJob `expected/` references in examples.
