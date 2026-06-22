# Postgres Coordination — Phase 1: lease primitive + PostgresProcessAdapter

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `process`/`schedule` workflows run across worker dynos on Postgres alone (no Redis), via a bespoke `claim_due_work()` lease primitive and a `PostgresProcessAdapter` that auto-selects when `DATABASE_URL` is present.

**Architecture:** "State tables are the queues." `process_runs`/`process_tasks` carry queue columns (`status`, `deliver_at`, `claimed_by`, `lease_expires_at`, `attempts`); a single shared `claim_due_work()` (SELECT … FOR UPDATE SKIP LOCKED + lease) claims due rows; `LISTEN/NOTIFY` is a best-effort latency hint over the durable polled table. A **sync** `PgProcessStateStore` is a drop-in for the Redis `ProcessStateStore`; `PostgresProcessAdapter` mirrors `EventBusProcessAdapter` (async methods wrap the sync store/executor via `asyncio.to_thread`). Step execution reuses `step_executor`, hardened with checkpoint-skip for at-least-once safety.

**Tech Stack:** Python 3.12+, psycopg3 (sync conns + LISTEN/NOTIFY), Pydantic IR, pytest (unit + real-PG). Spike-validated (`dev_docs/2026-06-22-pg-coordination-spike-findings.md`).

## Global Constraints

- **State tables are the durable queue; `NOTIFY` is never durability — only a latency hint.** Every consume path must work with NOTIFY disabled (poll floor).
- **At-least-once + idempotent replay.** A re-claimed run re-enters `step_executor`, which must **skip steps whose output is already in `run.context`** (Task 4). Non-idempotent re-execution is a defect.
- **`PgProcessStateStore` is a SYNC drop-in for `ProcessStateStore`** — identical method names/signatures (see `src/dazzle/core/process/process_state.py`), backed by Postgres. The adapter wraps sync calls in `asyncio.to_thread`, exactly as `EventBusProcessAdapter` does.
- **`claim_due_work()` takes a connection** (no driver import in the primitive) so it's reusable by Phase-2 jobs and layer-clean.
- **Framework tables via dual-write** — boot-time `CREATE TABLE IF NOT EXISTS` (mirror `ensure_dazzle_params_table`, `src/dazzle/http/runtime/migrations.py:127`) **and** a guarded Alembic migration (ADR-0017). Keep both in sync (the authstore-parity rule).
- **psycopg3 only** (ADR-0008); no Redis required for the Postgres path.
- **Connection discipline:** one shared LISTEN connection per worker; bounded claim connections (the Heroku connection-budget boundary, spec §7).
- **`ProcessRun`/`ProcessTask` are Pydantic `BaseModel`s** (`src/dazzle/core/process/adapter.py:51-91`) — serialise via `.model_dump(mode="json")`, rehydrate via `Model(**row)`.
- Reconciliation (spec §5): the framework `process_runs` table (execution state) is **separate** from the #1454 app `ProcessRun` IR entity (RBAC-scoped governance/AIJob subject). The adapter does NOT write the app entity; that stays the executor's governance projection from #1454. Confirm no collision in Task 2.
- Pre-ship gate = `pytest -m "not e2e"` from repo root + the real-PG tests with `TEST_DATABASE_URL`/`DATABASE_URL` set; ruff, mypy, lint-imports. Ship discipline: `/bump patch`, `ruff format` touched files before commit.

---

### Task 1: The `claim_due_work` lease primitive

**Files:**
- Create: `src/dazzle/core/coordination/__init__.py`
- Create: `src/dazzle/core/coordination/claim.py`
- Test: `tests/unit/test_claim_due_work.py` (real-PG; skips without `TEST_DATABASE_URL`/`DATABASE_URL`)

**Interfaces:**
- Produces: `QUEUE_COLUMNS_DDL: str` (the shared column set + index, parameterised by table name via `queue_columns_ddl(table)`); `claim_due_work(conn, *, table, worker, lease_seconds, batch=1) -> list[str]`; `renew_lease(conn, *, table, row_id, lease_seconds) -> None`; `complete_work(conn, *, table, row_id) -> None`; `fail_work(conn, *, table, row_id, error, retry_at=None, max_attempts=5) -> str` (returns `"retry"` or `"dead"`).
- Consumed by Tasks 3, 5 (process) and Phase 2 (jobs).

- [ ] **Step 1: Write the failing real-PG test**

```python
# tests/unit/test_claim_due_work.py
import os, uuid, concurrent.futures
import pytest

pytestmark = pytest.mark.postgres
_PG = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.mark.skipif(not _PG, reason="needs real Postgres (TEST_DATABASE_URL/DATABASE_URL)")
def test_no_double_claim_and_reclaim():
    import psycopg
    from dazzle.core.coordination.claim import (
        queue_columns_ddl, claim_due_work, complete_work,
    )
    tbl = f"claim_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(_PG, autocommit=True) as c:
        c.execute(f"CREATE TABLE {tbl} (id uuid PRIMARY KEY, {queue_columns_ddl(tbl)})")
    try:
        with psycopg.connect(_PG, autocommit=True) as c, c.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {tbl} (id, deliver_at) VALUES (%s, now())",
                [(str(uuid.uuid4()),) for _ in range(300)],
            )

        def drain(wid):
            got = []
            conn = psycopg.connect(_PG)
            try:
                while True:
                    ids = claim_due_work(conn, table=tbl, worker=f"w{wid}", lease_seconds=30, batch=10)
                    if not ids:
                        break
                    for i in ids:
                        complete_work(conn, table=tbl, row_id=i)
                    got += ids
            finally:
                conn.close()
            return got

        claimed = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            for f in [ex.submit(drain, i) for i in range(4)]:
                claimed += f.result()
        assert len(claimed) == 300 and len(set(claimed)) == 300  # no double-claim
    finally:
        with psycopg.connect(_PG, autocommit=True) as c:
            c.execute(f"DROP TABLE IF EXISTS {tbl}")
```

> Mirror `tests/integration/test_current_tenant_scope_pg.py` for the skip/marker idiom. Add a second test `test_expired_lease_is_reclaimed` (claim with `lease_seconds=1`, don't complete, `time.sleep(1.2)`, re-claim returns the same id) — exactly the spike's `test_lease_reclaim`.

- [ ] **Step 2: Run → FAIL** (`module not found`). `python -m pytest tests/unit/test_claim_due_work.py -q` (needs PG).

- [ ] **Step 3: Implement `claim.py`** (validated by the spike):

```python
# src/dazzle/core/coordination/claim.py
"""Postgres claim/lease primitive — the shared queue mechanism (spec §4).

State tables ARE the queue. `claim_due_work` atomically claims due rows with
FOR UPDATE SKIP LOCKED and a visibility-timeout lease; an expired lease is
reclaimable (crash recovery). Takes a connection — no driver import here, so
it's reusable by both the process adapter and the job queue, and layer-clean.
"""

from __future__ import annotations

from datetime import datetime


def queue_columns_ddl(table: str) -> str:
    """Column set + due-index any queue table carries. `table` names the index."""
    return (
        "status text NOT NULL DEFAULT 'pending', "
        "deliver_at timestamptz NOT NULL DEFAULT now(), "
        "claimed_by text, claimed_at timestamptz, lease_expires_at timestamptz, "
        "attempts int NOT NULL DEFAULT 0, "
        f"payload jsonb NOT NULL DEFAULT '{{}}'::jsonb"
        # caller adds: CREATE INDEX <table>_due ON <table>(deliver_at)
        #              WHERE status IN ('pending','claimed');
    )


_CLAIM = """
WITH due AS (
    SELECT id FROM {table}
    WHERE (status = 'pending' AND deliver_at <= now())
       OR (status = 'claimed' AND lease_expires_at <= now())
    ORDER BY deliver_at
    FOR UPDATE SKIP LOCKED
    LIMIT %(batch)s
)
UPDATE {table} t
SET status='claimed', claimed_by=%(worker)s, claimed_at=now(),
    lease_expires_at = now() + (%(lease)s || ' seconds')::interval,
    attempts = t.attempts + 1
FROM due WHERE t.id = due.id
RETURNING t.id;
"""


def claim_due_work(conn, *, table: str, worker: str, lease_seconds: int, batch: int = 1) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(_CLAIM.format(table=table),
                    {"batch": batch, "worker": worker, "lease": lease_seconds})
        rows = cur.fetchall()
    conn.commit()
    return [str(r[0]) for r in rows]


def renew_lease(conn, *, table: str, row_id: str, lease_seconds: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE {table} SET lease_expires_at = now() + (%s||' seconds')::interval "
            "WHERE id=%s AND status='claimed'", (lease_seconds, row_id))
    conn.commit()


def complete_work(conn, *, table: str, row_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f"UPDATE {table} SET status='done' WHERE id=%s", (row_id,))
    conn.commit()


def fail_work(conn, *, table: str, row_id: str, error: str,
              retry_at: datetime | None = None, max_attempts: int = 5) -> str:
    """Retry (reset to pending with deliver_at=retry_at) until max_attempts, then dead-letter.

    Mirrors PostgresBus's nack/DLQ split (spike 'carry forward'): attempts is the
    discriminator; a row at/over max_attempts goes status='dead'.
    """
    with conn.cursor() as cur:
        cur.execute(f"SELECT attempts FROM {table} WHERE id=%s", (row_id,))
        row = cur.fetchone()
        attempts = (row[0] if row else 0)
        if attempts >= max_attempts:
            cur.execute(f"UPDATE {table} SET status='dead', payload = payload || %s WHERE id=%s",
                        ('{"last_error": ' + _json(error) + "}", row_id))
            outcome = "dead"
        else:
            cur.execute(
                f"UPDATE {table} SET status='pending', deliver_at=%s, "
                "payload = payload || %s WHERE id=%s",
                (retry_at or _now(), '{"last_error": ' + _json(error) + "}", row_id))
            outcome = "retry"
    conn.commit()
    return outcome


def _now() -> datetime:
    from datetime import UTC, datetime as _dt
    return _dt.now(UTC)


def _json(s: str) -> str:
    import json
    return json.dumps(s)
```

> `src/dazzle/core/coordination/__init__.py`: re-export the four functions + `queue_columns_ddl`.

- [ ] **Step 4: Run → PASS** (with PG). Confirm no-double-claim + reclaim.

- [ ] **Step 5: Commit**

```bash
ruff format src/dazzle/core/coordination/ tests/unit/test_claim_due_work.py
git add -A && git commit -m "feat(coordination): claim_due_work lease primitive (SKIP LOCKED + visibility timeout)"
```

---

### Task 2: Framework process-runtime tables (`process_runs`, `process_tasks`)

**Files:**
- Create: `src/dazzle/http/runtime/process_schema.py` (boot-time DDL, mirrors `ensure_dazzle_params_table`)
- Create: `src/dazzle/http/alembic/versions/<rev>_process_runtime_tables.py` (guarded migration)
- Test: `tests/unit/test_process_schema.py` (real-PG: DDL is idempotent + has the queue columns)

**Interfaces:**
- Produces: `ensure_process_tables(conn) -> None` (idempotent `CREATE TABLE IF NOT EXISTS` for `process_runs` + `process_tasks` with `claim.queue_columns_ddl` columns + the due index); table names `process_runs`, `process_tasks`.
- Consumed by Task 3 (store), Task 5 (adapter boot).

- [ ] **Step 1: Write the failing test** — call `ensure_process_tables(conn)` twice (idempotent), then assert `process_runs` has columns `run_id, process_name, status, current_step, context, deliver_at, claimed_by, lease_expires_at, attempts` via `information_schema.columns`.

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `process_schema.py`.** Columns = the `ProcessRun` fields (`adapter.py:51-69`: `run_id, process_name, process_version, dsl_version, status, current_step, inputs jsonb, context jsonb, outputs jsonb, error, idempotency_key, started_at, updated_at, completed_at`) PLUS the queue columns (`deliver_at, claimed_by, claimed_at, lease_expires_at, attempts`). `process_tasks` = `ProcessTask` fields (`adapter.py:72-91`) + queue columns (its `due_at` doubles as the timeout deliver_at). Use `CREATE TABLE IF NOT EXISTS` + `pg_advisory_xact_lock` for boot concurrency (mirror `AuthStore._init_db`, `store.py:2589`). Confirm `process_runs` does NOT collide with the #1454 app `ProcessRun` entity table (different schema/owner — the app entity is `processrun` via entity-slug; this is the framework `process_runs`; verify the generated table names differ, and rename this one to `_dazzle_process_runs` if needed).

- [ ] **Step 4: Add the Alembic migration** — guarded `CREATE TABLE IF NOT EXISTS` mirroring `0001_framework_baseline.py` (idempotence via `sa_inspect(bind).has_table()`), so dev (boot DDL) and prod (Alembic) match.

- [ ] **Step 5: Run → PASS.** Commit `feat(db): process_runs/process_tasks framework tables (dual-write + alembic)`.

---

### Task 3: `PgProcessStateStore` — sync Postgres drop-in for `ProcessStateStore`

**Files:**
- Create: `src/dazzle/core/process/pg_state.py`
- Test: `tests/unit/test_pg_state_store.py` (real-PG)

**Interfaces:**
- Consumes: `ensure_process_tables` (Task 2), `claim_due_work` (Task 1).
- Produces: `class PgProcessStateStore` with **the exact public method set of `ProcessStateStore`** (`process_state.py`): `register_process/get_process_spec`, `register_schedule/get_schedule_spec/list_schedule_specs/set_schedule_last_run`, `save_run/get_run/list_runs/list_runs_by_version/count_active_runs_by_version`, `save_task/get_task/list_tasks`, `save_entity_meta/get_entity_meta`. PLUS `claim_due_runs(worker, lease_seconds, batch) -> list[ProcessRun]` and `mark_run_done(run_id)` / `mark_run_retry(run_id, error)` built on Task 1.

- [ ] **Step 1: Write the failing test** — `save_run(run)` then `get_run(run_id)` round-trips a `ProcessRun` (all fields); `list_runs(status=PENDING)` filters; `claim_due_runs` returns a pending run and marks it claimed (not returned to a second caller).

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `PgProcessStateStore`.** Constructor `__init__(self, dsn: str)`; each method opens a sync `psycopg.connect(dsn)` (or uses an injected conn — accept `conn=None` and self-manage). `save_run` = `INSERT ... ON CONFLICT (run_id) DO UPDATE` with `model_dump(mode="json")` mapped to columns; `get_run` = `SELECT ... WHERE run_id=%s` → `ProcessRun(**row)`. `claim_due_runs` calls `claim_due_work(conn, table="process_runs", ...)` then loads those runs. Representative method (the rest follow this exact pattern — mirror the matching `ProcessStateStore` method's semantics):

```python
def save_run(self, run: ProcessRun) -> None:
    d = run.model_dump(mode="json")
    with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO process_runs
               (run_id, process_name, process_version, dsl_version, status, current_step,
                inputs, context, outputs, error, idempotency_key,
                started_at, updated_at, completed_at, deliver_at)
               VALUES (%(run_id)s,%(process_name)s,%(process_version)s,%(dsl_version)s,
                %(status)s,%(current_step)s,%(inputs)s,%(context)s,%(outputs)s,%(error)s,
                %(idempotency_key)s,%(started_at)s,%(updated_at)s,%(completed_at)s, now())
               ON CONFLICT (run_id) DO UPDATE SET
                status=EXCLUDED.status, current_step=EXCLUDED.current_step,
                context=EXCLUDED.context, outputs=EXCLUDED.outputs, error=EXCLUDED.error,
                updated_at=EXCLUDED.updated_at, completed_at=EXCLUDED.completed_at""",
            {**d, "inputs": Jsonb(d["inputs"]), "context": Jsonb(d["context"]),
             "outputs": Jsonb(d["outputs"])})
        conn.commit()
```

> `from psycopg.types.json import Jsonb`. Every other method maps 1:1 to a `ProcessStateStore` method — implement each against the tables using the same pattern; the existing class is the behavioural spec. Spec data (`register_process`/`get_process_spec`) can persist to a small `process_specs` table or be held in-memory per-process (the adapter re-registers on boot, as EventBus does) — choose in-memory dict to match EventBus behaviour and avoid a third table.

- [ ] **Step 4: Run → PASS.** Commit `feat(process): PgProcessStateStore — sync Postgres drop-in for ProcessStateStore`.

---

### Task 4: Checkpoint-skip in `step_executor` (idempotent replay)

**Files:**
- Modify: `src/dazzle/core/process/step_executor.py` (the step loop, `execute_process_steps` ~line 84-110)
- Test: `tests/unit/test_step_checkpoint_skip.py`

**Interfaces:**
- Consumes: `ProcessRun.context` (per-step outputs).
- Produces: `execute_process_steps` skips a step whose output is already recorded in `run.context` (re-delivery no longer re-runs completed steps).

> **Why (spec correction):** the spec assumed checkpoint replay existed in this executor; it does NOT (the explorer confirmed `step_executor` re-runs all steps). At-least-once delivery (Task 1 reclaim) requires this skip, else a re-claimed run re-executes completed, possibly non-idempotent, steps.

- [ ] **Step 1: Write the failing test** — build a `ProcessRun` whose `context` already has `{"step_a": ...}`; run `execute_process_steps` over a spec `[step_a (records a side-effect), step_b]` with a spy on the side-effect; assert `step_a` is NOT re-executed (skipped), `step_b` runs.

- [ ] **Step 2: Run → FAIL** (step_a re-runs).

- [ ] **Step 3: Implement the skip** in the step loop:

```python
for step in steps:
    step_name = step.get("name", "unknown")
    if step_name in run.context:               # #checkpoint-skip: already produced output
        logger.debug("Skipping completed step %s in run %s (replay)", step_name, run.run_id)
        continue
    run.current_step = step_name
    ...
```

> Caveat to encode in the test: only steps that record output into `run.context` are skippable; a step that legitimately produces no output should still record a sentinel (`run.context[step_name] = {}`) on completion so replay skips it. Add that completion-marker write where `completed_steps.append(step_name)` happens.

- [ ] **Step 4: Run → PASS.** Confirm existing `step_executor` tests still pass: `python -m pytest tests/unit -q -k "step_executor or process"`.

- [ ] **Step 5: Commit** `fix(process): step_executor skips already-completed steps on replay (at-least-once safety)`.

---

### Task 5: `PostgresProcessAdapter`

**Files:**
- Create: `src/dazzle/core/process/postgres_adapter.py`
- Test: `tests/unit/test_postgres_adapter.py` (real-PG)

**Interfaces:**
- Consumes: `PgProcessStateStore` (Task 3), `claim_due_work` (Task 1), `execute_process_steps` (Task 4), `PostgresBus` for NOTIFY wake (`http/events/postgres_bus.py`) — optional, latency-only.
- Produces: `class PostgresProcessAdapter(ProcessAdapter)` implementing all abstract methods (`adapter.py:106-275`); `__init__(self, dsn: str, store: PgProcessStateStore | None = None)`.

> **Template:** `EventBusProcessAdapter` (`eventbus_adapter.py`) is the structural template — copy its method bodies, replacing the Redis store with `PgProcessStateStore` and the Redis event publish/poll with: (a) the durable floor = `store.claim_due_runs(...)` polling in the consumer loop, and (b) the latency hint = a Postgres `NOTIFY process_run` on `start_process`, with the consumer loop waking on `LISTEN process_run` OR the poll interval.

- [ ] **Step 1: Write the failing test** — `adapter.initialize()`; `run_id = await adapter.start_process("p", {...})`; run one consumer tick; assert the run reaches `COMPLETED` and its steps' outputs are in the run. Plus a crash test: claim a run, kill before complete, assert the lease lets a second tick reclaim+finish it exactly once (checkpoint-skip proven via a side-effect spy).

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement the adapter** mirroring `EventBusProcessAdapter`:
  - `start_process`: build `ProcessRun(status=PENDING)`, `store.save_run`, `NOTIFY process_run`. (Idempotency-key check identical to EventBus, `eventbus_adapter.py:150-177`.)
  - consumer loop (`initialize` starts an asyncio task): `runs = await asyncio.to_thread(store.claim_due_runs, worker_id, lease, batch)`; for each, `await asyncio.to_thread(execute_process_steps, store, run, on_task_created=cb)`; `complete`/`fail` via the store. Between batches: `await` whichever of (NOTIFY received on the LISTEN connection) or (poll_interval) fires first. **One shared LISTEN connection.**
  - `on_task_created` callback: write a `process_tasks` row with `due_at` = timeout deliver_at (the same poll picks up timeouts via `check_task_timeout`).
  - scheduler loop: same shape as EventBus (`eventbus_adapter.py:528-563`) — interval/cron → insert a due run.
  - the remaining `ProcessAdapter` methods (`get_run`, `list_runs`, `cancel`/`suspend`/`resume`, tasks, version queries) delegate to the store via `asyncio.to_thread` — 1:1 with the EventBus implementations.

- [ ] **Step 4: Run → PASS** (real-PG, no `REDIS_URL`). Commit `feat(process): PostgresProcessAdapter (claim/lease + NOTIFY-hint over the durable run table)`.

---

### Task 6: Factory wiring + Postgres-first auto-detect

**Files:**
- Modify: `src/dazzle/core/process/factory.py`
- Test: `tests/unit/test_process_factory_postgres.py`

**Interfaces:**
- Consumes: `PostgresProcessAdapter` (Task 5).
- Produces: `BackendType` gains `"postgres"`; `ProcessConfig` gains `postgres: PostgresProcessConfig` (`dsn: str | None`); `_detect_backend` precedence becomes **Temporal → Postgres (if `DATABASE_URL`) → EventBus (if `REDIS_URL`) → error**; `_create_postgres_adapter(config)`.

- [ ] **Step 1: Write the failing test** — `_detect_backend` with `DATABASE_URL` set + no Temporal/Redis returns `"postgres"`; `create_adapter(ProcessConfig(backend="postgres", postgres=PostgresProcessConfig(dsn=_PG)))` returns a `PostgresProcessAdapter`. With `DATABASE_URL` set AND `REDIS_URL` set, Postgres still wins (precedence).

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — add the literal value, the config dataclass, the `elif backend == "postgres": return _create_postgres_adapter(config)` branch (after temporal, before eventbus), the `_create_postgres_adapter` builder (reads `config.postgres.dsn or DATABASE_URL`), and the precedence in `_detect_backend` (insert the `DATABASE_URL → "postgres"` check before the `REDIS_URL → "eventbus"` check). Update the `create_adapter`/`_detect_backend` docstrings.

- [ ] **Step 4: Run → PASS.** Commit `feat(process): factory auto-selects PostgresProcessAdapter when DATABASE_URL present`.

---

### Task 7: `dazzle worker` runs the Postgres process loops

**Files:**
- Modify: `src/dazzle/cli/worker.py` (the `_run_worker` task set, ~line 86)
- Modify: `src/dazzle/http/runtime/subsystems/process.py` / `process_manager.py` if adapter construction happens there (confirm the boot wiring)
- Test: `tests/unit/test_worker_postgres_wiring.py`

**Interfaces:**
- Consumes: `create_adapter` (Task 6), `PostgresProcessAdapter` loops (Task 5).
- Produces: `dazzle worker` boots the auto-detected adapter and runs its consumer + scheduler loops with no `REDIS_URL` when `DATABASE_URL` is present.

- [ ] **Step 1: Write the failing test** — invoke the worker's adapter-construction path with `DATABASE_URL` set, assert it builds a `PostgresProcessAdapter` and calls `initialize()` (which starts the loops). Mirror an existing `cli/worker.py` test.

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — in `_run_worker`, construct the process adapter via `create_adapter(ProcessConfig(...))` (auto-detect) and `await adapter.initialize()`; ensure shutdown stops the loops. The job-queue loop is unchanged (Phase 2 swaps its backend). Remove any `--redis-key`-mandatory assumption for the process path.

- [ ] **Step 4: Run → PASS.** Commit `feat(cli): dazzle worker runs Postgres process loops (no Redis required)`.

---

### Task 8: Real-PG end-to-end integration proof

**Files:**
- Create: `tests/integration/test_pg_coordination_pg.py`

**Interfaces:** Consumes the full Phase-1 stack.

- [ ] **Step 1–3: Add the proof** (mirror `tests/integration/test_current_tenant_scope_pg.py` setup/teardown + marker), no `REDIS_URL` in env:
  - (a) **End-to-end:** start a process with a service step + a human-task step on a `PostgresProcessAdapter`; run the consumer loop; assert it pauses at the task (`WAITING`), `complete_task` resumes it, run reaches `COMPLETED`. All on Postgres.
  - (b) **Crash/at-least-once:** start a run, claim it, simulate worker death (don't complete; let the lease expire), run a second consumer tick; assert the run completes **exactly once** (checkpoint-skip — a service-step side-effect spy fires once).
  - (c) **Concurrency:** N runs, M consumer loops; assert each run executes once (no double-claim) and all reach `COMPLETED`.
  - (d) **NOTIFY-off durability:** disable the NOTIFY path; assert the poll floor still drains all runs.
  - (e) **Schedule:** a `schedule` with a short interval fires a run via `deliver_at`.

Run: `DATABASE_URL=postgresql://localhost:5432/postgres python -m pytest tests/integration/test_pg_coordination_pg.py -v`

- [ ] **Step 4: Commit** `test(integration): #pg-coordination Phase 1 — process execution on Postgres only`.

---

## Self-Review

**Spec coverage (Phase 1 slice of `2026-06-22-postgres-coordination-layer-design.md`):** §3 substrate (state-tables-are-queues) → Tasks 1–3,5. §4 `claim_due_work` + worker loop → Tasks 1,5,7. §5 schema + reconciliation → Task 2. §6 delayed/scheduled work (`deliver_at`) → Tasks 2,5,8e. §8 default-flip (process only; jobs/event-bus are Phases 2–3) → Task 6. §11 testing (unit claim, concurrency, crash/ALO, NOTIFY-off, integration) → Tasks 1,8. Out of Phase 1 (deferred to Phase 2/3, per spec §10): `PgJobQueue`, the event-bus default flip, the ADR + boundary guide + load-test.

**Placeholder scan:** the parity tasks (3, 5) reference "mirror the matching `ProcessStateStore`/`EventBusProcessAdapter` method" rather than transcribing ~40 near-identical methods — this names the exact existing class+method that IS the behavioural spec and shows the representative SQL/structure pattern, which is the correct altitude for drop-in/mirror work, not a deferral of logic. The novel/load-bearing code (claim primitive, checkpoint-skip, factory precedence, schema, integration proofs) is given in full.

**Type consistency:** `claim_due_work(conn, *, table, worker, lease_seconds, batch)` used identically in Tasks 1/3/5. `PgProcessStateStore` method set == `ProcessStateStore` (Task 3) consumed by Task 5. `ProcessRun`/`ProcessTask` Pydantic `model_dump(mode="json")`/`Model(**row)` consistent across Tasks 2/3/5. `BackendType "postgres"` + `PostgresProcessConfig.dsn` consistent across Task 6/7.

**Scope:** one phase, ~8 interlocked tasks producing a working Postgres process backend behind the existing `ProcessAdapter` interface; Phases 2–3 are separate plans.

**Spec correction recorded:** Task 4 implements the checkpoint-skip the spec assumed existed; update spec §3.1/§11 to say Phase 1 *adds* it to `step_executor` (the mounted path).
