# AI cognition in Dazzle

Date: 2026-06-22

This document explains how to add AI to a Dazzle app, what the framework
guarantees, and why there is no "third path."

## The one-sentence rule

**Every AI call in a Dazzle app is declared through a trigger or a process step,
carries a typed subject, and is auditable by construction. There is no other
path.**

This is not a policy or a convention — it is enforced structurally:

- `AIJob.subject` is a required `poly_ref` (NOT NULL). A subjectless AI call
  cannot persist.
- The executor and queue raise `ValueError` on a missing subject. Only the two
  declared surfaces supply one.
- The generic `POST /execute/{intent_name}` endpoint is gone and a guard test
  asserts it stays gone.

The consequence is that audit, cost, and RBAC are derived consequences of the
subject — not additional work. Declare the surface; the framework derives the
rest.

## Surface 1 — trigger-driven

Use this when an AI job should run in response to an entity event.

```dsl
llm_intent classify_manuscript "Classify a manuscript":
  model: gpt_main
  trigger:
    on_entity: Manuscript
    on_event:  submitted
  input_map:
    text: Manuscript.content
  output:
    field: Manuscript.ai_classification
```

What the framework does:

- Injects `AIJob` with `subject_type = 'Manuscript'` and
  `subject_id = <the triggering row's id>`.
- Adds `Manuscript` to `AIJob.subject`'s `poly_ref` target set (derived at
  link time; no manual edit).
- Makes the job scope-able: `subject[Manuscript].owner = current_user`
  lets a persona see only AI jobs on their own manuscripts.

## Surface 2 — process/task-driven

Use this when AI is one step in a multi-step business process.

```dsl
process review_submission "Review a submitted work":
  step extract_metadata:
    kind: llm_intent
    llm_intent: classify_manuscript
    input_map:
      text: submission.content

  step notify_reviewer:
    kind: notify
    ...
```

What the framework does:

- Injects `ProcessRun` (a uuid-pk, `started_by`-anchored entity, persisted as
  a real PostgreSQL table) when any process has an `llm_intent` step.
- Injects `AIJob` with `subject_type = 'ProcessRun'` and
  `subject_id = <the run's id>`.
- Makes the job scope-able: `subject[ProcessRun].started_by = current_user`
  lets a persona see only AI jobs on runs they initiated.

A user-declared `ProcessRun` entity in the same app raises a collision
`LinkError` at validate time — the framework's governed entity wins.

## What the subject gives you automatically

| Concern | How it works |
|---------|-------------|
| **Audit** | Every `AIJob` row names the exact entity or process run that triggered it. |
| **Cost attribution** | Token counts in `AIJob` are filterable by `subject_type` and `subject_id`. |
| **RBAC / scoping** | `subject[Type].field = current_user` uses the ADR-0042 selector — one mechanism, two referent kinds. |
| **Traceability** | `dazzle db explain-scope AIJob <verb>` prints the compiled predicate tree, the app-layer WHERE, and the RLS policy body. |

## Adding a scope rule

```dsl
entity AIJob "AI job audit record":
  # ... (framework-injected; don't redeclare subject)

  permit: read as: author
  scope:  read: subject[Manuscript].created_by = current_user  as: author

  permit: read as: reviewer
  scope:  read: subject[ProcessRun].started_by = current_user  as: reviewer
```

Verify it compiled correctly:

```bash
dazzle db explain-scope AIJob read
```

## What does NOT work (and why)

**A bare Python call to the executor** — `LLMIntentExecutor.execute(...)` —
requires a `(subject_type, subject_id)` pair. Omitting it raises `ValueError`
at call time, not at persist time. This is intentional: the framework should
never write a NULL-subject row.

**A custom route that calls an intent directly** — the `POST /execute/{intent_name}`
endpoint is gone. If an operator needs to trigger an intent, route it through a
process step (which gives it a `ProcessRun` subject).

**An `llm_config` block with no trigger and no process step** — the linker
emits `E_AIJOB_NO_SUBJECT_SURFACE` at validate time. The `AIJob` entity would
have a required subject with an empty target set and no legal value. Declare a
trigger or a process step.

## Known limitations

- The process-step AI executor (`http/runtime/process_executor.py`) is not yet
  request-mounted (pre-existing limitation).
- The celery process backend is being deprecated (#1457).
- `poly_ref` create/update probes are supported on manually-declared entities;
  the framework-injected `AIJob` inherits them automatically.

## Further reading

- [ADR-0043](../adr/0043-closed-system-ai-cognition.md) — the full decision record
- [ADR-0042](../adr/0042-poly-ref-scoping.md) — `poly_ref` primitive and scope selectors
- `dazzle db explain-scope AIJob <verb>` — runtime traceability oracle
