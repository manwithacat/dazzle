# Observability Guide

How to watch a running Dazzle application: the `/_dazzle/*` internal
endpoint surface, the event subsystem operational API,
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
| `/_dazzle/live` | GET | Liveness probe | None (all environments) |
| `/_dazzle/ready` | GET | Readiness probe | None (all environments) |
| `/_dazzle/stats` | GET | Per-entity row counts + uptime | None (all environments) |
| `/_dazzle/spec` | GET | Loaded spec summary (entity/surface names, endpoint count) | None (all environments) |
| `/_dazzle/entity/{name}` | GET | Entity schema + sample rows | None (all environments) |
| `/_dazzle/tables` | GET | All DB tables + row counts | None (all environments) |
| `/_dazzle/audit/logs` | GET | Audit trail query (filterable) | Admin auth required |
| `/_dazzle/audit/logs/{entity}/{id}` | GET | Audit trail for one record | Admin auth required |
| `/_dazzle/audit/stats` | GET | Aggregated audit statistics | Admin auth required |
| `/_dazzle/integrations/{name}/retries` | GET | Recent retry attempts (in-process, volatile) | None; only when `integration` blocks declared |

**Gating note:** The `/_dazzle/*` debug endpoints are
registered unconditionally — there is no `DAZZLE_ENV`-based removal
of those routes in production. The audit endpoints require an
authenticated superuser (`is_superuser=True` on the user record).
The `/_dazzle/audit/*` endpoints return HTTP 401 when no auth context
is present and HTTP 403 when the authenticated user is not a superuser.

In production deployments, protect the `/_dazzle/*` surface (except
`/health`, `/live`, `/ready`) at your load balancer or ingress — do not
expose entity, tables, or spec endpoints to public traffic.

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
does not export to a collector. See [section 4](#4-metrics-traces-and-logs)
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

**Use for:** liveness probe. A failed liveness probe triggers
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

**Use for:** readiness probe and load-balancer health checks.
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

The event framework starts in every app. With `REDIS_URL` set it runs on
Redis Streams: auth lifecycle events (`auth.user.registered` and siblings),
process events from the `EventBusProcessAdapter`, and handlers registered with
`EventFramework.register_handler` (deduplicated per consumer group through the
`_dazzle_event_inbox` table). Without `REDIS_URL` the bus is the null tier:
publishes are accepted and dropped and registered handlers never fire. The
startup log line `Event framework started` names the tier (`redis` or `null`)
and the bus type.

`EventFramework.health_check()` returns the tier, the bus type, whether the
outbox publisher is running, the consumer count and the outbox depth; with
Redis it also reports `redis_connected` and the topic count. Inspect the Redis
streams and their consumer groups with `redis-cli` (`XINFO GROUPS <topic>`).

There is no HTTP event inspector. The unauthenticated `/_dazzle/events/*`
explorer, the PostgreSQL and in-memory buses and the `/_ops/sse/events` live
push were parked in flense ship AR; see
[DD-006](../decisions/DD-006-events-dsl.md).

---

## 4. Metrics, Traces, and Logs

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
| `WARNING: Process manager requires REDIS_URL. Skipping` | Process system not started |
| `WARNING: JWT_SECRET not set` | Sessions will not survive restart |
| `Outbox publisher started` | Event outbox relay is running |
| `Event framework started` | Event subsystem is operational |
| `DLQ replay failed for event ...` | Replay attempt failed; check bus connectivity |

---

## 5. Integration Retries (#1194)


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
contents — alert on your integration provider's logs instead.

---

## 6. Worked Example — `invoice_ops` in Production

`examples/invoice_ops` is an accounts-payable system: maker-checker
approval and a settlement process (`settle_invoice`) that calls the
`payment_provider` integration.

### Which checks answer "is settlement healthy?"

**1. Is the app up and the database reachable?**

```bash
GET /_dazzle/ready
# Expect: "ready": true
```

**2. Is the settlement process completing?**

The `settle_invoice` process executes when `Invoice.status` transitions
to `approved`. Inspect its runs in the `process_runs` table
(`status`, `error`, `current_step`); a cluster of
failed runs means the `payment_provider` integration is failing
persistently — check the mock scenario (in dev: the `mock` MCP tool)
or the live integration logs and `/_dazzle/integrations/payment_provider/retries`.

**3. Is settlement deadlocked on approval?**

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
| DB reachable | `/_dazzle/ready` | `ready: true` |
| Integration retries quiet | `/_dazzle/integrations/payment_provider/retries` | no recent failures |
| No stuck settlements | Entity API | `status=dead_letter` count: 0 |

---

*Related: [Operations guide](operations.md) ·
[Performance observability](../reference/perf-observability.md) ·
[Agent workflow guide](agent-workflow.md) ·
[Migrations reference](../reference/migrations.md)*
