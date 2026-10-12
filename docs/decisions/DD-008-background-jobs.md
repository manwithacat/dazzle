# DD-008: `job` construct and `dazzle worker` — parked until AegisMark retires Heroku Scheduler

```yaml
id: DD-008
status: PARKED
issues: [953, 989, 991, 992, 1190, 1191, 1193, 1490]
adrs: [0057, 0003]
decided: 2026-10-12
decided_at_sha: 2de583aa741ecc4dfad1f369f6c773fa12f99966
parent: flense-programme
```

## One-line intent

No consumer declares a `job`. Flense ship F (ADR-0057) removes the construct,
the `JobRun` system entity and admin surface, the queue (in-memory and
Redis), worker, scheduler, cron matcher, trigger wiring, `/_dazzle/jobs`
explorer and the `dazzle worker` CLI. `schedule` (cyfuture uses eight) is
kept: it runs through the process adapter, not the job worker.

## Plan (what we already concluded)

Restore from the commit this DD was parked at
(`2de583aa741ecc4dfad1f369f6c773fa12f99966`):

```dsl
job cohort_analysis "Nightly cohort analysis":
  schedule: cron("0 2 * * *")
  run: app.jobs.cohort:run
  retry: 3
  retry_backoff: exponential
  dead_letter: CohortAnalysisFailure
  timeout: 10m

job thumbnail_render "Generate thumbnail":
  trigger: on_create Manuscript when source_pdf is_set
  run: app.jobs.thumbs:render
```

- `JobRun` is a linker-injected platform entity (one row per invocation,
  `job_name` discriminator, status, attempt, timings) with an admin LIST
  surface; the scheduler reads `status` to skip running jobs.
- Queue backing follows `REDIS_URL` (Redis list) else in-memory; the worker
  honours `retry_backoff` (capped) and routes exhausted runs to
  `dead_letter`.
- `dazzle validate` statically checks that each `run: module:fn` resolves
  (#1490).
- `dazzle worker` also hosted the daily **retention sweep** for `JobRun`
  and for `audit on X: retention: Nd` (`http/runtime/retention*.py`).
  Since the worker exited when no job was declared, that sweep never ran
  for any consumer; `dazzle validate` now says so for any audit that
  declares `retention:`. Restore the sweep with the worker.
- Counter-priors: no ad-hoc threads or `asyncio.create_task` loops in app
  code for scheduled work; no second scheduler beside `schedule`.

## Reopen when (consumer force)

1. **Named consumer** — AegisMark's SP-1 plan
   (`docs/superpowers/specs/2026-06-21-sp1-tenancy-rls-foundation-design.md`)
   replaces Heroku Scheduler (`cohort_analysis`) with a `worker` dyno running
   `dazzle worker`.
2. **Evidence of host workaround** — the Heroku Scheduler entry itself.
3. **Acceptance that unblocks** — AegisMark's `cohort_analysis` runs from a
   `job` in its CI, writes a `JobRun`, and retries with backoff.

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on every linked issue with the consumer + this DD path.
3. Implement against the plan above; open child issues if the plan splits.
4. When shipped, set `status: DONE` and close issues.

## Already shipped (do not re-litigate)

- `schedule` + the process adapter (Postgres / Redis / Temporal) for
  cron-driven process steps.
- Process-step `retry` backoff (`core/process/step_executor.py`).

## Explicitly out of scope until force

- Job priorities, fan-out/fan-in, per-tenant queues, a jobs dashboard.

## Trail

| Date | Event |
|------|--------|
| 2026-10-12 | Parked (this DD); `job` and `dazzle worker` removed in flense ship F |
