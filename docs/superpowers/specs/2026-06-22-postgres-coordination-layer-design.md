# Postgres-backed coordination layer: making Redis optional

**Status:** Design (brainstormed 2026-06-22), ready for implementation plan.
**Builds on:** #1457 (Celery removal), #1454 (governed `ProcessRun` as a real table), ADR-0008 (Postgres-only runtime).
**Disposition:** Large — three subsystems + docs + a load-test harness. One spec, phased; Phase 1 is the first implementation plan.

---

## 1. The principle

**Dazzle's runtime should require nothing but Postgres.** Today every subsystem honours that (ADR-0008) *except* deferred/coordinated execution — the process layer hard-requires Redis (or Temporal), and the cross-dyno job queue + event delivery reach for Redis too. This makes the *process layer the lone ADR-0008 violator*: a documented DSL feature (`process`, `schedule`, `job`) silently doesn't run across worker dynos unless the operator bolts on external infra.

The goal is to make **Redis a pure opt-in accelerator** — never a hard requirement — by giving every coordination subsystem a Postgres-backed implementation that becomes the default. An app with a `DATABASE_URL` (which every Dazzle app has) gets working processes, jobs, and schedules with zero extra infra. Teams that already run Redis or Temporal opt into them for scale.

This is the same instinct that removed Celery (#1457): collapse the runtime onto one datastore unless there's a measured reason not to.

## 2. What requires Redis today (the closure target)

| Subsystem | Redis today | After this work |
|---|---|---|
| API cache (`http/runtime/api_cache.py`) | optional ("disabled if empty") | unchanged — already opt-in |
| Event bus (`http/events/`) | one impl among many; `PostgresBus` exists | **Postgres default** |
| Job queue (`http/runtime/job_queue.py`) | `InMemoryJobQueue` default; Redis for cross-dyno | **`PgJobQueue` for cross-dyno** |
| Process execution (`core/process/`) | **`EventBusProcessAdapter` requires `REDIS_URL`**; factory raises without Redis/Temporal | **`PostgresProcessAdapter` default** |

The process adapter is the only subsystem that *mandates* Redis; the others already degrade. Closing all three makes Redis fully optional.

## 3. The substrate decision: "C with a shared lease primitive"

Rejected alternatives (see brainstorm): (A) one generic polymorphic `pg_work_queue` god-table; (B) per-domain queue tables + shared claim helper; (C) lean on `PostgresBus` transport with no queue table.

**Chosen:** the **state tables *are* the queues** (C), with the claim/lease logic as **one shared, tested primitive** (the part of B worth keeping). The decisive rule, from the prior art:

> **`LISTEN/NOTIFY` is never the durability mechanism — the table is.**

- **Durability** = the state table, polled with `WHERE status='pending' AND deliver_at <= now()` + `FOR UPDATE SKIP LOCKED` + a lease. Always catches everything, including missed notifies and delayed work.
- **`NOTIFY`** (via the existing `PostgresBus`) = a *best-effort* latency hint so workers skip the poll interval for sub-second pickup. Losing one just defers to the next poll.
- There is **no separate backlog table** — `process_runs`/`process_tasks`/`job_messages` carry the queue columns directly. C "devolves to B" only if you mistakenly make the bus durable; we never do.

### 3.1 Prior art this rests on (not greenfield)

- **`SELECT … FOR UPDATE SKIP LOCKED`** (Postgres 9.5+) — the concurrent-consumer primitive (Marco Slot/Citus; Brandur Leach, *"Transactionally-staged job drains in Postgres"*).
- **Visibility-timeout / lease** for at-least-once on crash — Amazon SQS's model; formally a *lease* (Gray & Cheriton, 1989). Reference impl: **pgmq** (Tembo).
- **LISTEN/NOTIFY + SKIP LOCKED + poll fallback** — exactly **graphile-worker** (Node) and **Solid Queue** (Rails 7.1 default; 37signals' Redis→Postgres move). Also **Oban** (Elixir), **River** (Go), **Que/GoodJob** (Ruby).
- **Transactional outbox** (Richardson; Brandur) — a genuine *advantage over Redis*: a step can mutate domain data **and** enqueue follow-on work in **one transaction**, eliminating the dual-write lost-work window.
- **At-least-once + idempotency** ("exactly-once delivery is impossible"). Dazzle already has the idempotency substrate: `step_executor` does **checkpoint replay — completed steps are skipped on restart**. A re-claimed run hands straight back to that path.

## 4. The foundational primitive: `claim_due_work()`

One reusable claim/lease helper, parameterised by table, used by both the process adapter and the job queue. Sketch (contract, not final SQL):

```python
# dazzle/core/coordination/claim.py  (new, framework-level)
@dataclass(frozen=True)
class Lease:
    row_id: str
    lease_expires_at: datetime  # for heartbeat/renewal of long steps

async def claim_due_work(
    conn,                # a Postgres connection/transaction
    *,
    table: str,          # "process_runs" | "job_messages" | ...
    worker_id: str,      # opaque dyno/worker identity, for observability
    lease_seconds: int,  # visibility timeout
    batch: int = 1,      # claim up to N due rows
) -> list[Lease]:
    """Atomically claim up to `batch` due rows from `table`.

    Due = status='pending' AND deliver_at <= now()
          (OR status='claimed' AND lease_expires_at <= now())  # reclaim crashed
    Sets status='claimed', claimed_by=worker_id, claimed_at=now(),
    lease_expires_at=now()+lease_seconds. Uses FOR UPDATE SKIP LOCKED so
    concurrent workers never block each other. Returns the claimed leases.
    """
```

Companions: `renew_lease(conn, table, row_id, lease_seconds)` (heartbeat for long steps), `complete_work(conn, table, row_id)` (status='done' or archive-then-delete to bound churn), `fail_work(conn, table, row_id, error, *, retry_at|terminal)`. Lease/visibility-timeout semantics and the reclaim-expired-lease branch are the **one genuinely novel, footgun-prone** piece — it gets its own unit tests + a concurrency test (N workers, one queue, assert no double-claim, assert crashed-lease reclaim).

### 4.1 The worker loop (`dazzle worker`)

Extends the existing worker entrypoint (`cli/worker.py` / `http/runtime/job_worker.py`):

```
loop:
  rows = claim_due_work(table, worker_id, lease_seconds, batch)   # durable floor
  for each: execute via step_executor (idempotent, checkpoint-replay); complete/fail
  if no rows: wait on PostgresBus NOTIFY OR poll_interval, whichever first   # latency hint
  periodically: renew_lease for in-flight long steps
```

Connection discipline (see §7 boundary): **one shared LISTEN connection** per worker; a **bounded claim pool**; pgbouncer-friendly. Worker count × connections must stay under the Postgres connection budget.

## 5. Schema (framework-managed, Alembic per ADR-0017)

Framework runtime tables (not app-scoped — like auth tables / `JobRun`), each carrying the queue columns:

- `process_runs` — run state: `id uuid pk, process_name, status, current_step, step_outputs jsonb, deliver_at, claimed_by, claimed_at, lease_expires_at, attempts, started_by, started_at, finished_at, error_message, created_at`. (Supersedes the Redis `ProcessStateStore` for the Postgres backend.)
- `process_tasks` — human-task / step rows with their own `deliver_at` for timeouts.
- `job_messages` — the cross-dyno `JobQueue` backlog (`job_name, payload jsonb` + queue columns).

**Open reconciliation (resolve in Phase 1):** the #1454 app-facing `ProcessRun` IR entity (RBAC-scoped governance/AIJob-subject, in the *app* schema) vs. this framework `process_runs` runtime table. Recommendation: keep them **separate layers** — the framework table drives execution; the executor writes the app `ProcessRun` as the governance projection (as #1454 Task 4 already does via `_process_run_service`). They may unify later, but the app-schema/framework-schema + RBAC boundary argues for keeping them distinct now. Confirm against the #1454 wiring before building.

## 6. Delayed & scheduled work

`deliver_at` is the universal mechanism: human-task timeouts, `schedule`/cron fires, and retry backoff all set a future `deliver_at`; the same `claim_due_work()` poll picks them up when due. No Beat, no separate scheduler — the cron publisher becomes a lightweight loop that inserts due `schedule.trigger` rows (or computes next-fire on claim). This replaces `eventbus_adapter`'s Redis cron loop.

## 7. The throughput boundary (a required deliverable, not an afterthought)

The Postgres backend is honest only if it documents where it stops. Limiting factors, in the order they bite:

1. **Postgres connection budget — the *first* limit on Heroku.** `worker_dynos × conns_per_worker` hits low tier caps (hobby ~20) before throughput does. Mitigation baked into the design: shared LISTEN connection, bounded claim pool, pgbouncer-friendly.
2. **Table churn / autovacuum.** High complete/enqueue rates bloat the queue tables. Mitigation: archive-then-delete completed rows (pgmq pattern), time-partitioning.
3. **Sustained throughput.** Field numbers: graphile-worker / Solid Queue / pgmq do **low-thousands of jobs/sec** on a modest primary; business-app rates run orders of magnitude under that.
4. **Dispatch latency floor.** NOTIFY → sub-second; polling adds the interval. Not for <100ms guaranteed dispatch.
5. **Long-running steps** hold leases / tie up workers (capacity, not throughput).

**"How to judge you've crossed it"** (the guide's checklist of *observable* signals): queue depth climbing despite added dynos (throughput-bound); autovacuum lag / queue-table bloat (churn-bound); p95 dispatch latency over SLA with NOTIFY on (latency-bound); Postgres connection saturation (connection-bound, Heroku); high lock-wait on the claim query (contention-bound).

**Escalation path = the justification.** Because it stays a swappable `ProcessAdapter` / `JobQueue` / `EventBus` behind unchanged interfaces, crossing the boundary is a config flip to Redis `EventBus` (pub/sub throughput) or Temporal (large-scale long-running orchestration) — **no lock-in**. The design earns the default precisely because the exit is cheap.

**Numbers must be measured, not guessed:** a **load-test harness** (enqueue N/sec, M workers; measure drain rate, p95 latency, connection count, vacuum behaviour across Heroku Postgres tiers) is a deliverable. The guide's thresholds come from it, with reproducible methodology.

## 8. Auto-detect / default flip

New precedence in `factory.py` (and the `JobQueue`/`EventBus` selectors): **Postgres first when `DATABASE_URL` is present** → EventBus when `REDIS_URL` is set and explicitly chosen → Temporal when configured. Net: processes/jobs/schedules work out-of-the-box; Redis/Temporal become explicit opt-ins. Clean break on the "no backend available → raise" behaviour (it can no longer happen with a database present).

## 9. Deliverables

- **Code:** `claim_due_work()` + lease primitive (`core/coordination/`); `PostgresProcessAdapter`; `PgJobQueue`; `PostgresBus` as the default event bus; `dazzle worker` loop; Alembic migrations for the runtime tables; auto-detect flip.
- **ADR** — "Postgres-backed coordination; Redis/Temporal opt-in" (decision, trade-offs, ADR-0008 tie-in, escalation path).
- **Architecture guide** — `docs/architecture/process-coordination.md`: the Business-App-vs-throughput boundary, the observable-signals checklist, the escalation path.
- **Load-test harness** + the measured thresholds feeding the guide.

## 10. Phasing (each phase a shippable unit; Phase 1 = first plan)

1. **Phase 1 — Lease primitive + `PostgresProcessAdapter`.** `claim_due_work()` + lease helpers (unit + concurrency tests); `process_runs`/`process_tasks` tables (Alembic); the adapter wired to `step_executor` + checkpoint replay + `PostgresBus` NOTIFY; `dazzle worker` runs processes; auto-detect prefers Postgres for processes. Resolve the §5 reconciliation. Proves the claim/lease pattern on the highest-value surface.
2. **Phase 2 — `PgJobQueue`.** The `JobQueue` protocol's cross-dyno implementation on `job_messages` reusing the Phase-1 primitive; schedules/cron on `deliver_at`.
3. **Phase 3 — Default flip + demotion + docs.** Postgres becomes the default event bus + process + job backend; EventBus(Redis)/Temporal demote to opt-in; ADR + architecture guide + load-test + measured thresholds.

## 11. Testing (proof obligations)

- **Unit** — `claim_due_work` due-selection, lease set, reclaim-expired-lease; `complete/fail/renew`.
- **Concurrency (real PG)** — N workers on one queue: no double-claim (SKIP LOCKED), crashed-worker lease reclaim, no lost work, exactly-one-effective execution via checkpoint replay.
- **Outbox (real PG)** — step domain-write + next-work enqueue commit atomically; rollback drops both.
- **Latency** — NOTIFY wakes a worker sub-second; with NOTIFY disabled, polling still drains (durability floor).
- **Integration** — a `process` with a human-task timeout + a `schedule` run end-to-end on Postgres only (no `REDIS_URL`).
- **Load-test** — the §7 harness.

## 12. Non-goals

- Replacing Redis where it's already optional (api_cache) or removing the Redis/Temporal adapters (they stay, opt-in).
- High-frequency / sub-100ms-dispatch workloads (that's the documented escalation path).
- Exactly-once delivery (impossible; we do at-least-once + idempotent replay).
- Distributed transactions across external services (outbox covers the Postgres-local case only).

## 13. Failure-modes rubric sign-off (CLAUDE.md gate)

1. *Failure mode risked:* the catalogued "abstraction hides a load-bearing runtime semantic" — a queue that silently loses or double-runs work. 2. *Detector:* the concurrency + outbox + latency real-PG tests + the load-test harness. 3. *Live?* yes — CI real-PG tests; the lease/reclaim invariants are asserted, not assumed. 4. *Trace runtime → DSL?* yes — a `process`/`job`/`schedule` construct maps to rows in named tables a competent engineer can inspect (`SELECT … FROM process_runs`); no opaque broker state. 5. *Preserve semantics?* yes — durability in Postgres (transactional, inspectable), at-least-once + idempotent replay, swappable adapters preserve the Redis/Temporal exits. Marketable as the default coordination substrate once the load-test thresholds are published and the boundary guide ships.
