# DD-010: Process-step AI executor (`llm_intent` steps inside a `process`) — parked until a consumer runs AI work as a process step

```yaml
id: DD-010
status: PARKED
issues: [1454, 1457]
adrs: [0043, 0057]
decided: 2026-10-13
decided_at_sha: 7879465836d4c38ded550e9c564f1a7d7d29d9e8
parent: flense-programme
```

## One-line intent

`http/runtime/process_executor.py` (a linear, checkpointed executor for
`llm_intent` / `service` / `condition` process steps that writes the governed
`ProcessRun` row ADR-0043 makes the `AIJob` subject) was never mounted: no
route, subsystem or process adapter constructed `ProcessExecutor`, ADR-0043
records it as "not yet request-mounted", and no consumer declares an
`llm_intent` step inside a `process`. Flense ship O (ADR-0057) deletes it.

## Plan (what we already concluded)

Restore `http/runtime/process_executor.py` and its two test modules
(`tests/unit/test_process_executor.py`, `tests/unit/test_process_run_executor.py`)
from the commit this DD was parked at (the original #417 design, "Layer 3" of
`docs/plans/2026-03-09-llm-async-event-queue-design.md`, is at the same commit),
then wire it where the live process runtime dispatches steps rather than as a
second runtime:

- The live dispatcher is `core/process/step_executor._dispatch_step`
  (service, human_task, wait, send, query, foreach). An `llm_intent` step
  today falls through to its "Unknown step kind" warning. The forced change
  adds an `llm_intent` arm there that calls `LLMIntentExecutor.execute` with
  `subject_type="ProcessRun"` and `subject_id=<run id>`, so the ADR-0043
  subject guarantee (every AI call names a scope-able subject) holds.
- The governed `ProcessRun` entity (injected when a process has an
  `llm_intent` step; `db/virtual.is_virtual_entity` treats it as real when
  it carries `started_by`) is the row the step writes; the restored executor's
  `_start_process_run` / `_finish_process_run` show the shape.
- Checkpoint replay (`ProcessContext.checkpoints`) maps onto the step state
  the Postgres process adapter already persists; do not add a second
  checkpoint store.
- Counter-priors: no generic `POST /execute/{intent}` route (ADR-0043,
  `tests/unit/test_no_bare_llm_route.py`); no AI call without a subject.

## Reopen when (consumer force)

1. **Named consumer** — a consumer declares a `process` with an `llm_intent`
   step (candidates: pennydreadful's story intents run as an editorial
   pipeline; AegisMark marking as a multi-step process).
2. **Evidence of host workaround** — a consumer calling `llm_executor`
   from a service step or app code to get AI work inside a process.
3. **Acceptance that unblocks** — the consumer's process runs its
   `llm_intent` step on the live process adapter, the `AIJob` row names the
   `ProcessRun` as subject, and `subject[ProcessRun].started_by = current_user`
   scopes the jobs in that consumer's CI.

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on every linked issue with the consumer + this DD path.
3. Implement against the plan above; open child issues if the plan splits.
4. When shipped, set `status: DONE` and close issues.

## Already shipped (do not re-litigate)

- ADR-0043 closed-system AI cognition: `llm_executor` and `llm_queue` require
  a subject; LLM triggers (`llm_trigger.py`) supply one and are live.
- The `llm_intent` step kind still parses (`StepKind.LLM_INTENT`) and the
  governed `ProcessRun` entity is still injected; only the executor is parked.

## Explicitly out of scope until force

- Parallel or branching AI steps, retries beyond the process retry policy,
  a separate AI process runtime.

## Trail

| Date | Event |
|------|--------|
| 2026-10-13 | Parked (this DD); `process_executor.py` removed in flense ship O |
