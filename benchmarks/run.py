"""benchmarks/run.py — SP6 sweep runner: scale × schema-config benchmark.

Runs the full invoice_ops benchmark across a matrix of dataset scales and
schema configurations, then writes structured JSON + human-readable Markdown
to ``benchmarks/results/``.

**Scale choices** (invoices per tenant, ``--scales`` override available):

* 1,000   — fast smoke test, always included; useful for CI / local iteration
* 10,000  — mid-range; covers realistic SME workloads
* 100,000 — production-scale stress test; ~5–10 minutes on a laptop

1M is best-effort: seeding alone takes several minutes and may exhaust
available RAM on machines with <16 GB free.  Specify ``--scales 1000000``
explicitly if you want it.

**Tenant count: 3**

Three tenants is the minimum that makes ``tenant_id`` predicate filtering
meaningful.  A single-tenant dataset would let the planner skip the tenant
filter entirely (it'd match all rows and the index would be unused).  Two
tenants produce an even 50 / 50 split that the planner can elide via a
bitmap-heap-scan shortcut.  Three produces the ~33 % selectivity that forces
the planner to actually evaluate the scope predicate, which is the behaviour
we want to measure.

**Schema configurations**

* ``default``  — framework-generated schema only (PK + unique indexes).  FK
  columns and ``tenant_id`` columns are unindexed — sequential scans at scale.
* ``indexed``  — + ``benchmarks/indexes.sql`` (tenant_id + FK join-path indexes).

The transition between configs is *always* explicit:

* Before ``indexed`` run: ``indexes.sql`` is applied via psycopg.
* Before ``default`` run:  every ``ix_bench_*`` index is **dropped** explicitly
  (``DROP INDEX IF EXISTS …``).  This guarantees that a prior ``indexed`` run
  does not leak indexes into a subsequent ``default`` run — even if the script
  is restarted mid-sweep.  The fresh ``TRUNCATE + COPY`` from ``seed.py`` does
  not drop indexes, so the explicit drop is load-bearing here.

**ANALYZE**

``ANALYZE`` is run after index creation / drop and after seeding so the query
planner has fresh statistics.  Without this the planner may retain stale
row-count estimates from the previous scale and pick a suboptimal plan.

Usage::

    python -m benchmarks.run                          # full sweep
    python -m benchmarks.run --scales 1000            # smoke test
    python -m benchmarks.run --scales 1000,10000      # two scales
    python -m benchmarks.run --db postgresql://localhost/mydb --scales 1000

Results land in ``benchmarks/results/results.json`` and
``benchmarks/results/results.md``.
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import time
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_DB_URL = "postgresql://localhost/dazzle_invoice_ops_bench"

# Fixed at 3 — see module docstring for the rationale.
_TENANTS: int = 3

# Default scale ladder (invoices per tenant).
_DEFAULT_SCALES: list[int] = [1_000, 10_000, 100_000]

# Index names defined in benchmarks/indexes.sql — must stay in sync.
_BENCH_INDEX_NAMES: list[str] = [
    "ix_bench_user_tenant_id",
    "ix_bench_supplier_tenant_id",
    "ix_bench_supplierbankaccount_tenant_id",
    "ix_bench_invoice_tenant_id",
    "ix_bench_lineitem_tenant_id",
    "ix_bench_paymentattempt_tenant_id",
    "ix_bench_invoice_supplier",
    "ix_bench_lineitem_invoice",
    "ix_bench_paymentattempt_invoice",
    "ix_bench_supplierbankaccount_supplier",
]

_INDEXES_SQL = Path(__file__).parent / "indexes.sql"
_RESULTS_DIR = Path(__file__).parent / "results"

# Probe ordering for display.
_PROBES: list[str] = ["list", "read", "search", "aggregate"]

# ---------------------------------------------------------------------------
# Index management helpers
# ---------------------------------------------------------------------------


def _pg_url(db_url: str) -> str:
    """Return a bare ``postgresql://`` URL usable by psycopg.connect()."""
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://"):
        if db_url.startswith(prefix):
            return "postgresql://" + db_url[len(prefix) :]
    return db_url


def _apply_indexes(db_url: str) -> None:
    """Execute ``benchmarks/indexes.sql`` against *db_url*."""
    import psycopg

    sql = _INDEXES_SQL.read_text()
    with psycopg.connect(_pg_url(db_url), autocommit=True) as conn:
        conn.execute(sql)
    logger.info("Applied indexes from %s", _INDEXES_SQL)


def _drop_indexes(db_url: str) -> None:
    """Drop every ``ix_bench_*`` index so no index state leaks between runs."""
    import psycopg

    drop_stmts = "\n".join(f"DROP INDEX IF EXISTS {name};" for name in _BENCH_INDEX_NAMES)
    with psycopg.connect(_pg_url(db_url), autocommit=True) as conn:
        conn.execute(drop_stmts)
    logger.info("Dropped %d ix_bench_* indexes (if present)", len(_BENCH_INDEX_NAMES))


def _run_analyze(db_url: str) -> None:
    """Run ``ANALYZE`` on the bench DB so the planner has fresh statistics."""
    import psycopg

    with psycopg.connect(_pg_url(db_url), autocommit=True) as conn:
        conn.execute("ANALYZE")
    logger.info("ANALYZE complete")


def _terminate_stale_connections(db_url: str) -> None:
    """Terminate any lingering backends on the bench DB before re-seeding.

    The previous cell's ``measure()`` boots invoice_ops in-process; its
    connection-pool teardown can leave a connection ``idle in transaction``
    holding relation-level locks.  The next cell's ``seed()`` issues a
    ``TRUNCATE``, which would then block indefinitely on those locks.

    The sweep runner owns the bench DB exclusively for the duration of a run,
    so terminating every *other* backend on it is both safe and required for
    the sweep to make progress.  Without this the second config of every scale
    deadlocks against the first config's leaked connection.
    """
    import psycopg

    with psycopg.connect(_pg_url(db_url), autocommit=True) as conn:
        row = conn.execute(
            """
            SELECT count(*)
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND pid <> pg_backend_pid()
            """
        ).fetchone()
        stale = row[0] if row else 0
        if stale:
            conn.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND pid <> pg_backend_pid()
                """
            )
            logger.info("Terminated %d lingering bench-DB connection(s)", stale)


def _query_pg_version(db_url: str) -> str:
    """Return the PostgreSQL ``server_version`` string."""
    import psycopg

    with psycopg.connect(_pg_url(db_url), autocommit=True) as conn:
        row = conn.execute("SHOW server_version").fetchone()
    return row[0] if row else "unknown"


# ---------------------------------------------------------------------------
# Result serialisation
# ---------------------------------------------------------------------------


def _write_json(
    results_dir: Path,
    timestamp: str,
    host: str,
    pg_version: str,
    tenants: int,
    iterations: int,
    all_results: dict,
) -> Path:
    """Write ``results.json``."""
    out = {
        "header": {
            "timestamp": timestamp,
            "host": host,
            "postgresql_version": pg_version,
            "tenants": tenants,
            "iterations": iterations,
        },
        "results": all_results,
    }
    path = results_dir / "results.json"
    path.write_text(json.dumps(out, indent=2))
    logger.info("Wrote %s", path)
    return path


def _write_markdown(
    results_dir: Path,
    timestamp: str,
    host: str,
    pg_version: str,
    tenants: int,
    iterations: int,
    all_results: dict,
    scales: list[int],
) -> Path:
    """Write ``results.md`` — one section per probe, columns = scale × config."""
    lines: list[str] = []
    lines.append("# invoice_ops Benchmark Results")
    lines.append("")
    lines.append(f"**Generated:** {timestamp}  ")
    lines.append(f"**Host:** {host}  ")
    lines.append(f"**PostgreSQL:** {pg_version}  ")
    lines.append(f"**Tenants:** {tenants}  ")
    lines.append(f"**Iterations per probe:** {iterations}  ")
    lines.append("")
    lines.append(
        "Schema configs: `default` = framework-generated schema (no FK/scope indexes); "
        "`indexed` = + `benchmarks/indexes.sql`."
    )
    lines.append("")

    configs = ["default", "indexed"]

    for probe in _PROBES:
        lines.append(f"## {probe.capitalize()}")
        lines.append("")
        # Header row
        header_cells = ["Scale (invoices/tenant)"]
        for cfg in configs:
            header_cells += [f"{cfg} p50 (ms)", f"{cfg} p95 (ms)", f"{cfg} p99 (ms)"]
        lines.append("| " + " | ".join(header_cells) + " |")
        lines.append("| " + " | ".join(["---"] * len(header_cells)) + " |")

        for scale in scales:
            scale_key = str(scale)
            row_cells = [f"{scale:,}"]
            for cfg in configs:
                try:
                    probe_data = all_results[scale_key][cfg][probe]
                    row_cells += [
                        f"{probe_data['p50_ms']:.1f}",
                        f"{probe_data['p95_ms']:.1f}",
                        f"{probe_data['p99_ms']:.1f}",
                    ]
                except KeyError:
                    row_cells += ["—", "—", "—"]
            lines.append("| " + " | ".join(row_cells) + " |")

        lines.append("")

    path = results_dir / "results.md"
    path.write_text("\n".join(lines))
    logger.info("Wrote %s", path)
    return path


# ---------------------------------------------------------------------------
# Sweep runner
# ---------------------------------------------------------------------------


def run(
    db_url: str = _DEFAULT_DB_URL,
    scales: list[int] | None = None,
    iterations: int = 200,
) -> dict:
    """Run the full scale × config benchmark sweep.

    Args:
        db_url: PostgreSQL connection URL for the bench DB.
        scales: List of invoices-per-tenant values to test.
            Defaults to ``[1_000, 10_000, 100_000]``.
        iterations: Timed calls per probe after warm-up, passed to
            ``benchmarks.measure.measure()``.

    Returns:
        The ``all_results`` dict (scale_str → config → probe → percentiles).
        Also written to ``benchmarks/results/``.
    """
    from benchmarks.measure import measure
    from benchmarks.seed import seed

    if scales is None:
        scales = _DEFAULT_SCALES

    _RESULTS_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now(UTC).isoformat()
    host = platform.node()
    pg_version = _query_pg_version(db_url)

    print("\ninvoice_ops benchmark sweep")
    print(f"  Host:       {host}")
    print(f"  PostgreSQL: {pg_version}")
    print(f"  Tenants:    {_TENANTS}")
    print(f"  Scales:     {scales}")
    print(f"  Iterations: {iterations} per probe")
    print(f"  DB:         {db_url}")
    print()

    all_results: dict = {}

    for scale in scales:
        scale_key = str(scale)
        all_results[scale_key] = {}

        for config in ("default", "indexed"):
            # The prior cell's in-process measure() can leave an
            # `idle in transaction` connection holding locks; clear it before
            # seeding so the TRUNCATE inside seed() does not deadlock.
            _terminate_stale_connections(db_url)

            print(
                f"[scale={scale:,}  config={config}]  "
                f"seeding {_TENANTS} tenants × {scale:,} invoices …"
            )
            t_seed = time.perf_counter()
            counts = seed(db_url=db_url, tenants=_TENANTS, invoices_per_tenant=scale)
            seed_elapsed = time.perf_counter() - t_seed
            total_rows = sum(counts.values())
            print(
                f"[scale={scale:,}  config={config}]  "
                f"seeded {total_rows:,} rows in {seed_elapsed:.1f}s"
            )

            if config == "default":
                print(
                    f"[scale={scale:,}  config={config}]  "
                    f"dropping ix_bench_* indexes (ensures no leakage from prior indexed run) …"
                )
                _drop_indexes(db_url)
            else:
                print(f"[scale={scale:,}  config={config}]  applying indexes.sql …")
                _apply_indexes(db_url)

            print(f"[scale={scale:,}  config={config}]  running ANALYZE …")
            _run_analyze(db_url)

            print(
                f"[scale={scale:,}  config={config}]  "
                f"measuring ({iterations} iterations per probe) …"
            )
            t_measure = time.perf_counter()
            probe_results = measure(db_url=db_url, iterations=iterations)
            measure_elapsed = time.perf_counter() - t_measure

            all_results[scale_key][config] = probe_results

            # Print a quick summary line for this cell.
            summary_parts = []
            for probe in _PROBES:
                p = probe_results.get(probe, {})
                summary_parts.append(f"{probe}: p95={p.get('p95_ms', 0):.1f}ms")
            print(
                f"[scale={scale:,}  config={config}]  "
                f"done in {measure_elapsed:.1f}s — " + "  ".join(summary_parts)
            )
            print()

    # ------------------------------------------------------------------
    # Write results
    # ------------------------------------------------------------------
    # Determine the iterations value actually used (from first cell).
    first_scale = str(scales[0])
    first_config = "default"
    actual_iterations = iterations
    try:
        actual_iterations = all_results[first_scale][first_config][_PROBES[0]]["iterations"]
    except KeyError:
        pass

    json_path = _write_json(
        _RESULTS_DIR,
        timestamp=timestamp,
        host=host,
        pg_version=pg_version,
        tenants=_TENANTS,
        iterations=actual_iterations,
        all_results=all_results,
    )
    md_path = _write_markdown(
        _RESULTS_DIR,
        timestamp=timestamp,
        host=host,
        pg_version=pg_version,
        tenants=_TENANTS,
        iterations=actual_iterations,
        all_results=all_results,
        scales=scales,
    )

    print("Results written:")
    print(f"  {json_path}")
    print(f"  {md_path}")

    return all_results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "invoice_ops benchmark sweep runner — scale × schema-config matrix.\n\n"
            "Runs seed → (drop|apply indexes) → ANALYZE → measure for each combination "
            "and writes results to benchmarks/results/.\n\n"
            "Default scales: 1,000 / 10,000 / 100,000 invoices per tenant.  "
            "1,000,000 is best-effort (seeding alone takes several minutes and "
            "requires ~16 GB free RAM) — specify via --scales 1000000."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db",
        default=_DEFAULT_DB_URL,
        metavar="URL",
        help=(
            "PostgreSQL connection URL (default: %(default)s).  "
            "The database must exist; run `createdb dazzle_invoice_ops_bench` first."
        ),
    )
    parser.add_argument(
        "--scales",
        default=None,
        metavar="N[,N…]",
        help=(
            "Comma-separated list of invoices-per-tenant scales to test "
            "(default: 1000,10000,100000).  "
            "Example: --scales 1000,10000"
        ),
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=200,
        metavar="N",
        help="Timed calls per probe after warm-up (default: 200)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    scales: list[int]
    if args.scales:
        try:
            scales = [int(s.strip()) for s in args.scales.split(",")]
        except ValueError:
            raise SystemExit(f"--scales must be comma-separated integers, got: {args.scales!r}")
    else:
        scales = _DEFAULT_SCALES

    run(db_url=args.db, scales=scales, iterations=args.iterations)


if __name__ == "__main__":
    main()
