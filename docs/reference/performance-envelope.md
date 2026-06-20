# Performance envelope

Where the Dazzle runtime is fast, where it degrades, and by how much — measured
on a reproducible benchmark rather than estimated.

This page reports the results of the SP6 benchmark (evaluator briefing #9). The
harness is committed at
[`benchmarks/`](https://github.com/manwithacat/dazzle/tree/main/benchmarks); the
raw numbers cited here come from
[`benchmarks/results/results.md`](https://github.com/manwithacat/dazzle/blob/main/benchmarks/results/results.md)
and `results.json`.

## Scope & method

The benchmark boots [`examples/invoice_ops`](https://github.com/manwithacat/dazzle/tree/main/examples/invoice_ops)
— a multi-tenant invoice app with six entity tables and a `tenant_id` scope
predicate on every surface — against a pre-seeded PostgreSQL database and
measures four representative probes:

| Probe | What it calls | What it isolates |
|---|---|---|
| `list` | `GET /invoices` | Scope-filtered paginated list (full auth + predicate path) |
| `read` | `GET /invoices/{id}` | Single-row primary-key lookup with tenant scope check |
| `search` | `GET /invoices?q=<term>` | `LIKE`-based search within tenant scope |
| `aggregate` | `Repository.aggregate` | Raw `GROUP BY status` SQL (no HTTP overhead) |

**Run parameters** (from `results.json`):

- **Host:** `mini`, **PostgreSQL:** 17.9 (Homebrew)
- **Tenants:** 3 — the minimum that forces the planner to evaluate the
  `tenant_id` predicate at ~33% selectivity rather than eliding it
- **Iterations:** 200 timed calls per probe (first 10 discarded as warm-up);
  p50 / p95 / p99 reported

**In-process measurement.** The app is booted in-process via the Dazzle ASGI
test transport — there is no network hop. This is deliberate: it measures the
framework's request path (auth, scope-predicate compile, repository, SQL,
response marshaling) without the variance of an external HTTP layer. Real
deployments add network latency on top of these numbers.

**Two schema configs.** Every probe is run against two schemas:

- **`default`** — the framework-generated schema exactly as
  `src/dazzle/http/runtime/sa_schema.py` emits it: primary-key indexes, FK
  *constraints*, and unique constraints. No index on `tenant_id` or FK columns.
- **`indexed`** — the `default` schema plus
  [`benchmarks/indexes.sql`](https://github.com/manwithacat/dazzle/blob/main/benchmarks/indexes.sql):
  single-column b-tree indexes on every `tenant_id` column and every FK column.

Comparing the two answers a concrete question: *does adding the obvious indexes
change the latency?*

## The operating envelope

Latency in milliseconds. Scale is invoices **per tenant**; with 3 tenants the
`Invoice` table holds 3× that many rows (the 1,000,000 row = 3,000,000 total
`Invoice` rows).

### `list` — `GET /invoices`

| Scale | `default` p50 | `default` p95 | `default` p99 | `indexed` p50 | `indexed` p95 | `indexed` p99 |
|---|---|---|---|---|---|---|
| 1,000 | 15.0 | 16.6 | 23.5 | 14.1 | 16.4 | 22.8 |
| 10,000 | 15.8 | 18.3 | 27.2 | 15.0 | 17.9 | 23.9 |
| 100,000 | 26.5 | 29.4 | 34.4 | 23.1 | 26.2 | 32.0 |
| 1,000,000 | 79.8 | 84.9 | 87.8 | 79.9 | 84.9 | 86.9 |

### `read` — `GET /invoices/{id}`

| Scale | `default` p50 | `default` p95 | `default` p99 | `indexed` p50 | `indexed` p95 | `indexed` p99 |
|---|---|---|---|---|---|---|
| 1,000 | 16.9 | 21.2 | 26.5 | 15.9 | 18.8 | 22.1 |
| 10,000 | 15.8 | 19.2 | 22.9 | 16.1 | 19.2 | 24.3 |
| 100,000 | 16.2 | 18.5 | 24.1 | 16.1 | 19.2 | 24.8 |
| 1,000,000 | 16.1 | 18.7 | 24.5 | 17.5 | 18.6 | 23.0 |

### `search` — `GET /invoices?q=<term>`

| Scale | `default` p50 | `default` p95 | `default` p99 | `indexed` p50 | `indexed` p95 | `indexed` p99 |
|---|---|---|---|---|---|---|
| 1,000 | 14.2 | 16.7 | 17.4 | 14.2 | 16.2 | 23.1 |
| 10,000 | 15.8 | 18.7 | 24.1 | 15.4 | 19.2 | 23.3 |
| 100,000 | 26.7 | 29.3 | 33.7 | 22.9 | 25.8 | 32.1 |
| 1,000,000 | 80.2 | 83.9 | 87.9 | 79.1 | 84.0 | 85.4 |

### `aggregate` — `Repository.aggregate` (`GROUP BY status`)

| Scale | `default` p50 | `default` p95 | `default` p99 | `indexed` p50 | `indexed` p95 | `indexed` p99 |
|---|---|---|---|---|---|---|
| 1,000 | 2.5 | 2.9 | 3.0 | 2.7 | 3.0 | 3.2 |
| 10,000 | 6.3 | 7.3 | 10.3 | 6.2 | 7.2 | 7.6 |
| 100,000 | 20.3 | 21.3 | 22.0 | 20.3 | 21.4 | 22.3 |
| 1,000,000 | 141.4 | 143.2 | 144.5 | 140.4 | 142.0 | 142.4 |

## Where it degrades

Two findings, both honest and both load-bearing.

### 1. The runtime degrades roughly linearly with dataset size

Three of the four probes climb with row count:

- **`list`** p95: ~17 ms (1k) → ~18 ms (10k) → ~29 ms (100k) → ~85 ms (1M).
- **`search`** p95: ~17 ms → ~19 ms → ~29 ms → ~84 ms — the same curve.
- **`aggregate`** p95: ~3 ms → ~7 ms → ~21 ms → ~143 ms — steeper, because it
  scans the whole table.
- **`read`** is the exception: flat at ~18–21 ms p95 at *every* scale. A
  single-row lookup on the primary key does not degrade — the PK index Dazzle
  already emits is doing its job.

So the practical envelope: for an entity in the **tens of thousands of rows per
tenant** range, scope-filtered list and search stay comfortably under ~30 ms
p95. At **a million rows per tenant** (3M total) the same calls reach ~85 ms and
a full-table aggregate reaches ~143 ms. These are healthy numbers for a single
request, but they grow with the data, and the framework emits no index that
arrests the growth.

### 2. Single-column `tenant_id` / FK indexes do **not** change this

The `indexed` config — single-column b-tree indexes on every `tenant_id` and FK
column — is **within measurement noise of `default` at every scale**. At 1M
invoices per tenant the two configs are effectively identical: `list` p95 84.9
vs 84.9, `search` 83.9 vs 84.0, `aggregate` 143.2 vs 142.0. The small apparent
gap at 100k (`list` 29.4 vs 26.2) is timing noise — it vanishes at 1M where the
signal is 10× larger.

Why the single-column indexes don't help is part structural certainty, part
honest open question.

**Structurally certain:**

- **`search`** matches with a leading-wildcard `LIKE '%term%'`. A plain b-tree
  cannot serve a leading-wildcard pattern under any conditions, so the
  `tenant_id` b-tree in the `indexed` config is simply irrelevant to it.
- **`aggregate`** is a full-table `GROUP BY status` — it reads every row by
  definition, so no single-column index changes its cost.
- **`read`** is a primary-key lookup, already served optimally by the PK index
  Dazzle emits — which is why it stays flat at every scale.
- A `list` surface that applies a default sort (`ORDER BY created_at DESC LIMIT
  n`) needs an index *ordered by* `created_at`; a single-column `tenant_id`
  index cannot satisfy that ordering, and Dazzle emits no `created_at` index.

**Honest open question:** for the scope-filtered `list` and `search` probes the
benchmark establishes the *outcome* — a single-column `tenant_id` b-tree does
not move end-to-end p95 at any scale — but not a complete per-component cost
breakdown. Isolated `EXPLAIN` of individual sub-queries shows plan-level
differences that do not translate into the measured request latency, and the
single-threaded harness does not attribute the remaining wall-clock. The
load-bearing claim here is the measured outcome, not a mechanism.

One factor that *is* clear: the benchmark runs **3 tenants**, so `tenant_id`
matches ~⅓ of the table — low selectivity, where an index earns little. An app
with hundreds of tenants has a far more selective predicate and would benefit
more from indexing it; the benchmark deliberately measures the low-tenant-count
case.

### The real lever

The fix for a sorted `list` path is a **composite `(tenant_id, created_at)`
index** — one index that covers both the scope predicate and the sort, so the
planner can serve `WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT n`
straight from the index with no sort node. For `search`, the lever is a PostgreSQL full-text
(`tsvector` + GIN) index, not a plain b-tree. Neither is what
`benchmarks/indexes.sql` contains, and — more importantly — neither is what the
framework's schema builder generates today. This gap is tracked as
[issue #1202](https://github.com/manwithacat/dazzle/issues/1202).

Until the schema builder closes that gap, an app expecting large per-tenant
tables should add the composite index by hand via an Alembic migration
([ADR-0017](../adr/INDEX.md)).

## Boot & surface complexity

`examples/invoice_ops` has 7 entities and ~24 entity/surface definitions and
boots in-process for every benchmark cell with no measurable warm-up penalty —
the first 10 probe iterations are discarded and the p50/p99 spread stays tight,
which means boot and schema reflection complete well before the timed window.
The benchmark does not isolate a dedicated boot-time-vs-entity-count number; for
runtime tracing of boot phases and slow framework stages, use `dazzle perf`
(see [Performance observability](perf-observability.md)).

## What is not benchmarked

The envelope above covers single-request read latency on one entity. It does
**not** cover:

- **Write / `INSERT` throughput** — the harness seeds via PostgreSQL `COPY` and
  only times reads. Insert and update latency under load is unmeasured.
- **Concurrent-user capacity** — the harness is single-threaded; it issues one
  request at a time. It says nothing about throughput under N concurrent
  clients, connection-pool saturation, or lock contention.
- **Events per day / workflow executions per day** — the event subsystem, job
  loop, and process executor are not exercised. See the
  [Observability Guide](../guides/observability.md) for their operational
  surface.
- **JOIN-heavy multi-table queries** — all four probes are single-table-dominant
  on `Invoice`. The `indexed` config includes FK-column indexes, but because no
  probe exercises a multi-table JOIN, the value of FK indexes for JOIN paths is
  **not measured here**. An app with heavy relational fan-out should benchmark
  its own JOIN paths before drawing conclusions.

Do not over-read the envelope: it is a clean, reproducible baseline for
scope-filtered single-entity reads, not a capacity model for a whole
deployment.

## Reproducing it

The benchmark is fully reproducible. See
[`benchmarks/README.md`](https://github.com/manwithacat/dazzle/blob/main/benchmarks/README.md)
for prerequisites and the full sweep command. In short:

```bash
createdb dazzle_invoice_ops_bench
python -m benchmarks.run                      # full sweep, all scales, both configs
python -m benchmarks.run --scales 1000        # fast smoke test
```

Results are written to `benchmarks/results/results.json` and `results.md`.

**Companion reading:** [Performance observability](perf-observability.md) covers
`dazzle perf` local tracing for diagnosing a slow path in your own app; the
[Scaling Guide](../guides/scaling.md) covers production infrastructure
configuration.
