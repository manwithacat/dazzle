# Observability Guide

How to watch a running Dazzle application: the `/_dazzle/*` internal
endpoint surface, the event subsystem operational API, the job lifecycle,
metrics, and local tracing with `dazzle perf`.

**Companion reading:** [Operations guide](operations.md) covers
infrastructure concerns (connection pools, migrations, backups). This
guide covers what to watch once the application is running.

---

## 1. Overview

Dazzle exposes a runtime operational surface via the `/_dazzle/*` prefix.
Every endpoint below is served by the same FastAPI process as the
application — no sidecar or separate management port required.

### Endpoint inventory

| Endpoint | Method | Purpose | Gating |
|---|---|---|---|
| `/_dazzle/health` | GET | DB connectivity + timestamp | None (all environments) |
| `/_dazzle/live` | GET | Kubernetes liveness probe | None (all environments) |
| `/_dazzle/ready` | GET | Kubernetes readiness probe | None (all environments) |
| `/_dazzle/stats` | GET | Per-entity row counts + uptime | None (all environments) |
| `/_dazzle/spec` | GET | Loaded spec summary (entity/surface names, endpoint count) | None (all environments) |
| `/_dazzle/entity/{name}` | GET | Entity schema + sample rows | None (all environments) |
| `/_dazzle/tables` | GET | All DB tables + row counts | None (all environments) |
| `/_dazzle/audit/logs` | GET | Audit trail query (filterable) | Admin auth required |
| `/_dazzle/audit/logs/{entity}/{id}` | GET | Audit trail for one record | Admin auth required |
| `/_dazzle/audit/stats` | GET | Aggregated audit statistics | Admin auth required |
| `/_dazzle/events/status` | GET | Event system summary | None (all environments) |
| `/_dazzle/events/topics` | GET | Topic list with event counts | None (all environments) |
| `/_dazzle/events/topics/{topic}` | GET | Events in a topic (paginated) | None (all environments) |
| `/_dazzle/events/event/{id}` | GET | Full detail for one event | None (all environments) |
| `/_dazzle/events/consumers` | GET | Consumer groups + lag | None (all environments) |
| `/_dazzle/events/outbox` | GET | Transactional outbox stats + recent entries | None (all environments) |
| `/_dazzle/events/dlq` | GET | Dead-letter queue contents | None (all environments) |
| `/_dazzle/events/dlq/{event_id}/replay` | POST | Re-queue one DLQ event | None (all environments) |
| `/_dazzle/metrics` | GET | Prometheus scrape endpoint (text exposition) | None (all environments) |
| `/_dazzle/approvals/pending` | GET | Pending approvals per `ApprovalSpec` block | None; only when `approval` blocks declared |
| `/_dazzle/integrations/{name}/retries` | GET | Recent retry attempts (in-process, volatile) | None; only when `integration` blocks declared |

**Gating note:** The `/_dazzle/*` debug and event endpoints are
registered unconditionally — there is no `DAZZLE_ENV`-based removal
of those routes in production. The audit endpoints require an
authenticated superuser (`is_superuser=True` on the user record).
The `/_dazzle/audit/*` endpoints return HTTP 401 when no auth context
is present and HTTP 403 when the authenticated user is not a superuser.

In production deployments, protect the `/_dazzle/*` surface (except
`/health`, `/live`, `/ready`) at your load balancer or ingress — do not
expose entity, tables, events, or spec endpoints to public traffic.

**Additional system endpoints (no `/_dazzle/` prefix):**

| Endpoint | Purpose |
|---|---|
| `/health` | App-level summary (name, version, DSL hash, uptime) — production-safe |
| `/spec` | Full AppSpec JSON dump — restrict in production |
| `/db-info` | Database URL (masked), table list, migration summary |
| `/_diagnostics` | Admin-only diagnostics (auth required, admin role) |

### `dazzle perf` — local on-demand tracing

`dazzle perf trace` runs a single instrumented request sequence and writes
a self-contained SQLite trace file. It is a local developer tool — it
requires the `perf` optional dependency (`pip install -e ".[perf]"`) and
does not export to a collector. See [section 5](#5-metrics-traces-and-logs)
and [`docs/reference/perf-observability.md`](../reference/perf-observability.md)
for full usage.

---

## 2. Health and Readiness

### `GET /_dazzle/health` — system health

Checks database connectivity and returns the current timestamp.

**Verified live output** (`examples/invoice_ops`, v0.71.105):

```json
{
  "status": "ok",
  "database": "ok",
  "timestamp": "2026-05-22T00:39:48.447744"
}
```

| Field | Values | Meaning |
|---|---|---|
| `status` | `"ok"` / `"degraded"` | `"degraded"` when the DB `SELECT 1` fails |
| `database` | `"ok"` / `"error: database unreachable"` | Raw DB check result |
| `timestamp` | ISO 8601 | Server-local time at check |

**Use for:** general-purpose health checks, monitoring pings.

### `GET /_dazzle/live` — liveness probe

Returns `{"alive": true}` unconditionally. The process being alive to
respond is the only invariant tested.

**Verified live output:**
```json
{"alive": true}
```

**Use for:** Kubernetes liveness probe. A failed liveness probe triggers
a container restart. Point it at `/_dazzle/live`.

### `GET /_dazzle/ready` — readiness probe

Checks database connectivity. Returns `ready: true` only when a `SELECT 1`
succeeds.

**Verified live output (healthy):**
```json
{"ready": true, "database": "ok", "reason": null}
```

**When degraded:**
```json
{"ready": false, "database": "error", "reason": "database unreachable"}
```

**Use for:** Kubernetes readiness probe and load-balancer health checks.
A pod failing readiness is removed from rotation until its DB connection
recovers. Point at `/_dazzle/ready`.

### `GET /_dazzle/stats` — runtime statistics

Returns per-entity row counts and server uptime. Useful for confirming
that seed data loaded and that the application has been up for the
expected duration.

**Verified live output** (fresh `invoice_ops` boot, 10 s uptime):
```json
{
  "app_name": "invoice_ops",
  "app_description": "Invoice Ops",
  "uptime_seconds": 10.776894,
  "entities": [
    {"name": "Tenant", "count": 0, "has_fts": false},
    {"name": "Invoice", "count": 0, "has_fts": false},
    {"name": "Supplier", "count": 1, "has_fts": false}
  ],
  "total_records": 0
}
```

`has_fts: true` indicates the entity has a full-text search table.

### `GET /health` — app-level summary

A lighter endpoint at the root (no `/_dazzle/` prefix) that includes the
framework version and a short DSL hash:

```json
{
  "status": "healthy",
  "app": "invoice_ops",
  "version": "0.71.105",
  "dsl_hash": "91442ed9",
  "uptime_seconds": 10.8
}
```

Use `dsl_hash` to confirm which DSL revision is running — it is the first
8 hex chars of the SHA-256 of the serialised AppSpec.

---

## 3. The Event Subsystem Operationally

The event subsystem endpoints are under `/_dazzle/events/*`. They respond
whether the broker is Redis-backed or PostgreSQL-backed. When the event
framework is not running (e.g., no broker configured), all endpoints
return empty/inactive responses rather than errors.

**Infrastructure note:** `/_dazzle/events/*` endpoints reflect the event
bus broker in use. The default broker for apps without `REDIS_URL` is a
PostgreSQL-backed bus — the subsystem still starts and all endpoints are
functional. A Redis-backed bus is used when `REDIS_URL` is set; the
operational surface is identical.

### `GET /_dazzle/events/status` — event system summary

**Verified live output** (`invoice_ops`, PostgreSQL broker):
```json
{
  "running": true,
  "broker_type": "PostgresBus",
  "topics_count": 0,
  "consumers_count": 0,
  "outbox_pending": 0,
  "dlq_count": 0
}
```

`running: false` means the event framework did not start — check startup
logs for `WARNING: Process manager requires REDIS_URL` or similar.

When the event bus is a Redis-backed broker, `broker_type` will be the
class name of the Redis bus implementation.

### `GET /_dazzle/events/topics` — topic list

**Verified live output:**
```json
{
  "topics": [],
  "total_events": 0
}
```

Each topic entry carries: `name`, `event_count`, `consumer_groups`,
`dlq_count`, `oldest_event`, `newest_event`.

In `invoice_ops`, the `invoice_events` topic appears here once events have
been published. If `invoice_events` is missing, no `InvoiceSubmitted` /
`InvoiceApproved` / `InvoicePaid` events have reached the bus yet.

### `GET /_dazzle/events/consumers` — consumer groups and lag

**Verified live output:**
```json
{"consumers": []}
```

Each consumer entry carries:

```json
{
  "group_id": "invoice-processor",
  "topic": "invoice_events",
  "last_sequence": 1420,
  "lag": 3
}
```

`lag` is the number of events the consumer has not yet processed
(bus sequence − consumer's `last_sequence`). A non-zero lag is normal
under load; a steadily growing lag indicates a stuck consumer.

**Diagnosing a stuck consumer:**

1. `GET /_dazzle/events/consumers` — identify the group with growing lag.
2. `GET /_dazzle/events/topics/{topic}` — inspect recent events in the
   topic; look for one event type that correlates with the lag start.
3. `GET /_dazzle/events/event/{event_id}` — read the full payload of the
   problematic event.
4. Check application logs for exceptions from the consumer's handler.
5. If the event is unprocessable, it will eventually exhaust retries and
   land in the DLQ — see [DLQ section below](#dead-letter-queue).

### `GET /_dazzle/events/outbox` — transactional outbox

The transactional outbox is the mechanism that guarantees events are
published atomically with the database write that produced them. An
application writes to the outbox row in the same DB transaction as the
entity change; a background relay then publishes to the bus.

**Verified live output:**
```json
{
  "stats": {
    "pending": 0,
    "publishing": 0,
    "published": 0,
    "failed": 0,
    "oldest_pending": null
  },
  "recent_entries": []
}
```

**Outbox pipeline states:**

| State | Meaning |
|---|---|
| `pending` | Written to outbox, not yet picked up by the relay |
| `publishing` | Relay has picked it up, attempting bus publish |
| `published` | Successfully delivered to the event bus |
| `failed` | Relay publish failed; will be retried |

**Diagnosing a backed-up outbox:**

- High `pending` count with a very old `oldest_pending`: the relay
  background task is not running. Check startup logs for `Outbox publisher
  started`; if missing, the event framework did not initialise. Restart
  the application.
- High `failed` count: the event bus is unreachable. Check `REDIS_URL`
  (if Redis-backed) or the PostgreSQL connection (if PostgreSQL-backed).
- `publishing` items that never progress to `published`: the relay started
  a publish but the process crashed mid-flight. These become `failed` on
  next startup and are retried.

### Dead-letter queue

The DLQ holds events that a consumer could not process after exhausting
its retry budget.

**`GET /_dazzle/events/dlq`** — list DLQ entries:

**Verified live output:**
```json
{"entries": [], "total": 0}
```

Each entry carries: `event_id`, `topic`, `group_id`, `reason_code`,
`reason_message`, `attempts`, `created_at`.

**`POST /_dazzle/events/dlq/{event_id}/replay`** — replay a DLQ event:

```bash
curl -X POST "/_dazzle/events/dlq/{event_id}/replay?group_id=invoice-processor"
```

The `group_id` query parameter is required — it specifies which consumer
group should receive the replayed event. A successful replay removes the
event from the DLQ and re-queues it for processing. Response:

```json
{"success": true, "message": "Event abc123 replayed successfully"}
```

Or on failure: `{"success": false, "error": "Event abc123 not found in DLQ"}`.

---

## 4. Jobs Operationally

### Job lifecycle

Every `job:` block in the DSL generates a `JobRun` entity that tracks
execution. The lifecycle is:

```
queued → running → completed
                 → failed          (retriable failure; re-enqueued)
                 → failed          (exhausted retries, no dead_letter:)
                 → dead_letter     (exhausted retries + dead_letter: declared)
```

The `JobRun` entity is inspectable via the standard entity API
(`GET /api/jobruns`, or via `/_dazzle/entity/JobRun` in dev).

### `retry: N` maps to `max_attempts`

A job declared as:

```dsl
job send_notification "Send Notification":
  retry: 3
```

is processed with `max_attempts = retry + 1 = 4`. The worker
(`src/dazzle/http/runtime/job_worker.py`) computes this as:

```python
max_attempts = max(1, getattr(spec, "retry", 0) + 1)
```

The first run is attempt 1; retries are attempts 2, 3, 4. After attempt
4 the job is terminal.

### `dead_letter: <Entity>` routing

When a job declares `dead_letter: FailedNotification`, exhausted jobs
write `status="dead_letter"` on the `JobRun` row instead of `"failed"`.
The `dead_letter:` entity (e.g., `FailedNotification`) is where the
application should persist its own record of the failure for operator
review — this is a DSL-level routing declaration, not automatic entity
creation. The `JobRun.status` is the runtime signal; your `FailedNotification`
entity and its handler are application code.

### Inspecting `JobRun` records

```bash
# All terminal-failed runs
GET /api/jobruns?status=dead_letter

# One specific run
GET /api/jobruns/{job_run_id}
```

`JobRun` fields: `job_name`, `status`, `attempt_number`, `started_at`,
`finished_at`, `duration_ms`, `error_message`.

### Honest gap: `retry_backoff:` is not enforced

The DSL accepts a `retry_backoff:` keyword on job definitions. **At
runtime, this field is currently ignored.** Failed jobs are re-enqueued
immediately without any delay between attempts.

The comment in `src/dazzle/http/runtime/job_worker.py` (line ~184):

```python
# The cycle-7 retry-backoff sleep would go here when the timer is
# wired; cycle 4 just re-enqueues immediately.
```

This is a known gap (#1191). Until it is implemented, if
exponential-backoff between job retries is required, implement the delay
in the job handler itself.

Note that process-step `retry:`/`backoff:` is *not* a workaround here.
The process-step `RetryConfig` IR is consumed only by the optional
Temporal and Celery adapters (`src/dazzle/core/process/temporal_adapter.py`,
`celery_tasks.py`); the default Dazzle runtime process executor
(`EventBusProcessAdapter` + `step_executor.py`, whose `max_retries`
parameter is documented "Not used directly here") does not apply
backoff between process-step retries either.

### No `/_dazzle/jobs` operational endpoints

The event subsystem has a rich `/_dazzle/events/*` surface. Jobs do not
have an equivalent — job state is inspectable only via the `JobRun` entity
API (#1193).

---

## 5. Metrics, Traces, and Logs

### `dazzle perf` — local on-demand tracing

`dazzle perf` captures a single trace run using OpenTelemetry instrumentation
and writes it to `.dazzle/perf/<run-id>.db`. It is designed for local
diagnosis, not production telemetry. No external collector is required.

Install:
```bash
pip install -e ".[perf]"
```

Basic trace:
```bash
dazzle perf trace --url /invoices --duration 10
```

With authentication:
```bash
dazzle perf trace --url /invoices --duration 10 \
  --login finance@example.test:password123
```

Read findings:
```bash
dazzle perf report                 # Markdown output
dazzle perf report --format json   # for programmatic use
dazzle perf list                   # past runs
dazzle perf show --run <id>        # span tree
```

What `dazzle perf` instruments automatically: FastAPI requests, psycopg
SQL queries, asyncio tasks. Dazzle's own hot paths are also manually
spanned: `dsl.parse`, `predicate.compile`, `aggregate.build_sql`,
`region.render`, `fragment.emit`.

See [`docs/reference/perf-observability.md`](../reference/perf-observability.md)
for complete reference including authenticated traces and MCP usage.

### `MetricsEmitter` → Redis stream

When `REDIS_URL` is configured, Dazzle emits runtime metrics to a Redis
stream at `dazzle:metrics:stream`. The emitter is fire-and-forget — it
never blocks request handling. If Redis is unavailable, metrics are
silently dropped.

**Stream key:** `dazzle:metrics:stream`

**Event shape** (each Redis stream entry):
```
name=http_requests_total
value=1.0
ts=1716337200.123
tags={"method":"GET","path":"/invoices","status":"200","instance":"web.1"}
```

**Metrics emitted by the HTTP middleware:**

| Metric name | Type | Description |
|---|---|---|
| `http_requests_total` | counter | One per request; tags: `method`, `path`, `status`, `instance` |
| `http_latency_ms` | timing | Request duration in ms; same tags |
| `http_errors_total` | counter | HTTP 4xx/5xx requests; adds `error_class` tag |

Path values are normalised — UUIDs and numeric IDs are replaced with
`:id` placeholders to avoid cardinality explosion.

**Consuming the stream:**

```python
import redis

r = redis.from_url(REDIS_URL)
for msg_id, fields in r.xread({"dazzle:metrics:stream": "0"}, count=100):
    import json
    tags = json.loads(fields["tags"]) if fields["tags"] else {}
    print(fields["name"], fields["value"], tags)
```

**Integrating a standard observability stack:**

The Redis stream is the integration point for external time-series systems.
A lightweight bridge reads from `dazzle:metrics:stream` and forwards to
your chosen backend:

- **Prometheus:** Scrape `GET /_dazzle/metrics` directly (see below) — no
  bridge needed.
- **Datadog / New Relic / Grafana Cloud:** Read the stream, forward via
  the provider's ingest API or statsd bridge.
- **InfluxDB / TimescaleDB:** Read the stream, insert via line protocol.

### `GET /_dazzle/metrics` — Prometheus scrape endpoint

Dazzle exposes the runtime's `SystemMetricsCollector` snapshot in the
Prometheus text exposition format. Response content-type is
`text/plain; version=0.0.4; charset=utf-8` — the standard pinned by the
Prometheus project. Point any Prometheus-compatible scraper (Prometheus,
VictoriaMetrics, Grafana Agent, OpenTelemetry Collector's `prometheus`
receiver) at this endpoint on the application's HTTP port.

The endpoint always responds with HTTP 200. When the collector is not
wired (telemetry off, test boot, no broker), the body is an empty but
valid Prometheus document — scrapes succeed cleanly with zero series
rather than failing.

Series surfaced today include `dazzle_uptime_seconds`,
`dazzle_component_health{component="..."}`, per-component counters
(suffixed `_total`), gauges, and histograms exported as summaries with
0.5 / 0.95 / 0.99 quantile labels. See
`src/dazzle/http/metrics/system_collector.py` for the full schema.

### OTLP push export

When `DAZZLE_OTEL_ENDPOINT` is set, the framework tracer attaches an
OTLP HTTP span exporter alongside the local SQLite span file —
`dazzle perf` keeps writing to `.dazzle/perf/<run-id>.db`, and every
span is also pushed to the configured collector. The endpoint is the
full URL of an OTLP/HTTP traces ingest, e.g.
`https://otel.example.com/v1/traces`. When the env var is unset the
push path is dormant and behaviour is identical to a pre-#1192 build.

Install the optional extra and point at your collector:

```bash
pip install 'dazzle-dsl[observability]'
export DAZZLE_OTEL_ENDPOINT=https://otel.example.com/v1/traces
```

Typical destinations:

- **Grafana Cloud (Tempo):** `https://otlp-gateway-<region>.grafana.net/otlp/v1/traces`
- **Datadog (Agent OTLP receiver):** `http://<agent-host>:4318/v1/traces`
- **Jaeger (built-in OTLP HTTP):** `http://<jaeger-host>:4318/v1/traces`

If `DAZZLE_OTEL_ENDPOINT` is set but the `observability` extra is not
installed, the tracer logs a single WARNING naming the missing extra
and continues with the local SQLite exporter — boot never crashes on
a missing exporter dependency.

### Structured logs

Dazzle logs to stdout in structured form. Log lines are tagged with
`[dazzle]` for filtering. Key log patterns to watch in production:

| Pattern | Meaning |
|---|---|
| `Connection pool opened (min=2, max=10)` | DB pool started successfully |
| `WARNING: Process manager requires REDIS_URL. Skipping` | Job/process system not started |
| `WARNING: JWT_SECRET not set` | Sessions will not survive restart |
| `Outbox publisher started` | Event outbox relay is running |
| `Event framework started` | Event subsystem is operational |
| `JobRun update failed for ... — continuing` | DB blip during job tracking; job continues |
| `DLQ replay failed for event ...` | Replay attempt failed; check bus connectivity |

---

## 6. Approval Queues and Integration Retries (#1194)

### `GET /_dazzle/approvals/pending` — pending approvals per block

`approval:` blocks in the DSL declare maker-checker approval gates (as in
`invoice_ops`'s `StandardApproval` and `HighValueApproval`). For each
declared `ApprovalSpec`, this endpoint returns the count of rows whose
driving entity has `trigger_field = trigger_value` — i.e. the rows
currently awaiting that approval — plus a sample of their primary-key
ids.

```bash
GET /_dazzle/approvals/pending?limit=20
```

```json
{
  "approvals": [
    {
      "name": "StandardApproval",
      "entity": "Invoice",
      "trigger_field": "status",
      "trigger_value": "submitted",
      "count": 4,
      "sample_ids": ["inv-1", "inv-2", "inv-3", "inv-4"]
    }
  ],
  "total_pending": 4,
  "limit": 20
}
```

The `limit` query param caps `sample_ids` per approval block (default 20,
max 100); the `count` is always the full pending total. The endpoint is
registered only when the AppSpec actually declares `approval` blocks. If
a declared block references an entity with no registered CRUD service,
its summary includes a non-null `error` field rather than 500-ing the
whole response.

### `GET /_dazzle/integrations/{name}/retries` — recent retry attempts

`integration:` blocks (such as `payment_provider` in `invoice_ops`)
support automatic retry on transient errors via `async_retrying_request`
in `MappingExecutor`. This endpoint surfaces each retry attempt's
outcome — attempt number, status code or transient error, the next
backoff delay, and whether the attempt succeeded.

```bash
GET /_dazzle/integrations/payment_provider/retries?limit=50
```

```json
{
  "integration": "payment_provider",
  "events": [
    {
      "integration": "payment_provider",
      "mapping": "charge_card",
      "attempt": 3,
      "max_attempts": 3,
      "status_code": 200,
      "error": null,
      "backoff_seconds": null,
      "succeeded": true,
      "last_attempt_at": "2026-05-23T10:42:11.123456+00:00"
    }
  ],
  "total": 3,
  "limit": 50,
  "volatile": true
}
```

Events are returned newest-first up to `limit` (default 50, max 200). An
unknown integration name returns 404; the endpoint is registered only
when `integration` blocks are declared.

#### Volatility — IN-PROCESS, RESETS ON RESTART

The retry events backing this endpoint live in a process-local
accumulator (the `volatile: true` flag in the response is a load-bearing
signal of this). The accumulator caps each integration at 100 entries
(FIFO, oldest drop first) and is **not** persisted to `ops_db`. Every
restart of the app process drops the full retry history.

That trade-off is deliberate: the surface exists for in-flight and
recent-restart inspection only. For durable retry history use the
integration provider's own logs, or wait for a future persistent-retry
feature. Do not build operational alerting against this endpoint's
contents — alert on the DLQ (`/_dazzle/events/dlq`), the JobRun status
distribution (`/_dazzle/jobs`), or your integration provider's logs
instead.

---

## 7. Worked Example — `invoice_ops` in Production

`examples/invoice_ops` is a production-grade accounts-payable system:
10 entities, maker-checker approval, a full HLESS event model
(`invoice_events` topic, six event types), and a settlement process
(`settle_invoice`) that calls the `payment_provider` integration.

### Which endpoints answer "is settlement healthy?"

For an operator watching a running `invoice_ops` instance, settlement
health maps directly to the event and job surfaces:

**1. Is the event bus running and are events flowing?**

```bash
GET /_dazzle/events/status
# Expect: "running": true, "broker_type": "PostgresBus" (or RedisBackedBus)
```

**2. Is the `invoice_events` topic publishing?**

```bash
GET /_dazzle/events/topics
# Look for "invoice_events" in the topics list.
# "event_count" should grow as invoices are submitted and approved.
```

**3. Is the outbox relay current?**

```bash
GET /_dazzle/events/outbox
# Healthy: {"pending": 0, "published": <n>, "failed": 0}
# Concern: "pending" or "failed" non-zero and growing
```

A growing `pending` count on the outbox means events are being written
to the DB but not reaching the bus — the outbox relay has stalled.
Check for `Outbox publisher started` in the startup logs; if absent,
restart the application.

**4. Is the settlement process completing?**

The `settle_invoice` process executes when `Invoice.status` transitions
to `approved`. Since there are no `/_dazzle/jobs/*` endpoints (gap noted
in [section 4](#4-jobs-operationally)), inspect `JobRun` records via the
entity API:

```bash
# Recent failed or dead-lettered settlement runs
GET /api/jobruns?job_name=settle_invoice&status=dead_letter
GET /api/jobruns?job_name=settle_invoice&status=failed
```

A cluster of `dead_letter` entries for `settle_invoice` means the
`payment_provider` integration is failing persistently — check the mock
scenario (in dev: `dazzle mock status`) or the live integration logs.

**5. Are consumers keeping up?**

```bash
GET /_dazzle/events/consumers
# Look for the invoice_events consumer group.
# "lag": 0 = current. A growing lag = consumer is behind.
```

The `InvoiceStatusView` projection (declared in `events.dsl`) is the
primary consumer of `invoice_events`. If its lag is non-zero and growing,
status projections are stale — the Invoice list will show outdated statuses
until the consumer catches up.

**6. Is settlement deadlocked on approval?**

```bash
# How many invoices are waiting for approval?
GET /api/invoices?status=submitted
```

`StandardApproval` requires quorum 1; `HighValueApproval` (invoices above
the tenant approval threshold) requires quorum 2. If invoices are stuck in
`submitted`, check that approver-role users exist for the tenant and have
been notified.

### What a healthy `invoice_ops` dashboard looks like

| Check | Endpoint | Healthy value |
|---|---|---|
| Event bus running | `/_dazzle/events/status` | `running: true` |
| Outbox clean | `/_dazzle/events/outbox` | `pending: 0, failed: 0` |
| Consumer current | `/_dazzle/events/consumers` | `lag: 0` for `invoice_events` |
| No DLQ events | `/_dazzle/events/dlq` | `total: 0` |
| DB reachable | `/_dazzle/ready` | `ready: true` |
| No stuck settlements | Entity API | `status=dead_letter` count: 0 |

---

*Related: [Operations guide](operations.md) ·
[Performance observability](../reference/perf-observability.md) ·
[Agent workflow guide](agent-workflow.md) ·
[Migrations reference](../reference/migrations.md)*
