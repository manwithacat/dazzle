# invoice_ops Benchmark (SP6)

Reproducible latency benchmarks for `examples/invoice_ops` across two schema
configurations and three dataset scales.

---

## What it measures — and why

Dazzle's runtime compiles `scope:` rules into SQL predicates at request time.
Every list or read call for a multi-tenant surface appends a
`WHERE tenant_id = $1` clause (and, for FK join paths, additional `JOIN`
conditions).  At low row counts the planner chooses sequential scans and
latency is flat.  At production scale, whether those columns are indexed
determines whether the planner can use an index range scan or must read every
row.

This benchmark isolates two variables:

| Variable | Values |
|---|---|
| **Dataset scale** | 1,000 / 10,000 / 100,000 invoices per tenant |
| **Schema config** | `default` (framework schema only) vs `indexed` (+ `indexes.sql`) |

Four probes are measured:

| Probe | What it calls | What it isolates |
|---|---|---|
| `list` | `GET /invoices` | Scope-filtered paginated list (full auth + predicate path) |
| `read` | `GET /invoices/{id}` | Single-row PK lookup with tenant scope check |
| `search` | `GET /invoices?q=<term>` | FTS / ILIKE scan within tenant scope |
| `aggregate` | `Repository.aggregate` | Raw `GROUP BY status` SQL (no HTTP overhead) |

**`default`** uses the framework-generated schema: primary-key indexes and
unique constraints only.  `tenant_id` columns and FK join columns are
unindexed.

**`indexed`** applies `benchmarks/indexes.sql` on top of the default schema.
That file adds `CREATE INDEX IF NOT EXISTS ix_bench_*` for every `tenant_id`
column and every FK join path used by the invoice_ops surfaces.

The comparison between the two configs quantifies the index impact at each
scale — giving a data-driven answer to "does adding these indexes to production
actually matter?".

---

## Prerequisites

1. **PostgreSQL 17** running locally.

2. **Create the bench database** (once):

   ```bash
   createdb dazzle_invoice_ops_bench
   ```

3. **Dazzle installed in editable mode** with all extras:

   ```bash
   pip install -e ".[dev,llm,mcp]"
   ```

   The benchmark imports `dazzle` internals directly (`load_target_metadata`,
   `Repository`, `_build_asgi_app`) so it must run inside the Dazzle venv.

---

## How to run

### Full sweep (all three scales, both configs)

```bash
python -m benchmarks.run
```

This runs six measurement cells (3 scales × 2 configs).  Expected runtime on a
MacBook Pro M-series with a local PostgreSQL:

| Scale | Approximate time per cell | Notes |
|---|---|---|
| 1,000 | ~30 s | Includes seeding, ANALYZE, 200 iterations × 4 probes |
| 10,000 | ~45 s | Seeding takes ~5 s at this scale |
| 100,000 | ~2–4 min | Seeding ~30–60 s; planner differences are most visible here |

Total wall time for the default sweep: roughly **10–20 minutes**.

### Smoke test (1k scale only — fast)

```bash
python -m benchmarks.run --scales 1000
```

Completes in under two minutes.  Good for verifying the harness is wired up
correctly before committing time to the full sweep.

### Custom scales

```bash
python -m benchmarks.run --scales 1000,10000
```

Comma-separated list of invoices-per-tenant values.  **1,000,000 is
best-effort**: seeding alone requires several minutes and approximately 16 GB
of free RAM.  Specify it explicitly with `--scales 1000000` if you want it.

### Override the database URL

```bash
python -m benchmarks.run --db postgresql://localhost/my_bench_db --scales 1000
```

### Increase iteration count (for tighter percentiles)

```bash
python -m benchmarks.run --scales 1000 --iterations 500
```

---

## Target application

`examples/invoice_ops` — a multi-tenant invoice management app with supplier
relationships, line items, and payment attempts.  It has six entity tables and
uses `tenant_id` scope predicates on every surface.

The benchmark boots `invoice_ops` in-process (no external HTTP server required)
using the Dazzle ASGI test transport.  The `dazzle_invoice_ops_bench` database
is seeded fresh at the start of each scale/config cell.

---

## Tenant count

Fixed at **3 tenants**.  This is the minimum that makes `tenant_id` predicate
filtering statistically meaningful:

- 1 tenant: the planner can skip the scope filter (it matches all rows).
- 2 tenants: even 50/50 split — the planner may elide the filter via a
  bitmap-heap scan shortcut.
- 3 tenants: ~33% selectivity forces the planner to evaluate the scope
  predicate, which is the runtime behaviour this benchmark targets.

---

## Index management between runs

The runner guarantees clean transitions between the `default` and `indexed`
configs:

1. **Before a `default` cell**: every `ix_bench_*` index is explicitly
   `DROP INDEX IF EXISTS`-ed.  `seed.py`'s `TRUNCATE + COPY` does not drop
   indexes, so this explicit drop is required to prevent a prior `indexed` run
   from leaking its indexes into a subsequent `default` measurement.

2. **Before an `indexed` cell**: `indexes.sql` is applied via psycopg
   (`CREATE INDEX IF NOT EXISTS` — safe to run repeatedly).

3. **After either transition**: `ANALYZE` is executed so the query planner has
   fresh statistics at the new scale and index state.

Before each cell's `seed()`, the runner also terminates any lingering
connections to the bench DB. The prior cell's in-process `measure()` can
leave a connection `idle in transaction`; without clearing it, the next
cell's `TRUNCATE` would deadlock on the locks it holds. The sweep runner owns
the bench DB exclusively, so this is safe — **do not run the sweep against a
database other processes are using.**

---

## Results

Results are written to `benchmarks/results/` after each full sweep:

| File | Contents |
|---|---|
| `results.json` | Full structured data: header (timestamp, host, PostgreSQL version, tenants, iterations) + `results[scale][config][probe][percentiles]` |
| `results.md` | Human-readable Markdown tables — one section per probe, rows = scales, columns = `default` vs `indexed` p50/p95/p99 |

The `results/` directory is tracked in git (via `.gitkeep`).  The result
files themselves are not committed automatically — re-running the sweep
overwrites them.  Commit `results.json` / `results.md` deliberately when you
want to snapshot a baseline (e.g. the full-scale production sweep).

---

## Individual tools

Each benchmark module is also runnable standalone:

```bash
# Seed only (e.g. to inspect the data before measuring)
python -m benchmarks.seed \
    --db postgresql://localhost/dazzle_invoice_ops_bench \
    --tenants 3 --invoices-per-tenant 1000

# Measure only (against an already-seeded DB)
python -m benchmarks.measure \
    --db postgresql://localhost/dazzle_invoice_ops_bench

# Apply indexes manually
psql postgresql://localhost/dazzle_invoice_ops_bench \
    -f benchmarks/indexes.sql
```

---

**Companion reading:** `docs/guides/observability.md` covers the runtime
operational surface.  `docs/guides/scaling.md` covers infrastructure
configuration for production deployments.
