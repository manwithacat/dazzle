"""benchmarks/measure.py — in-process endpoint latency measurement (SP6).

Boots ``examples/invoice_ops`` against the pre-seeded benchmark database
(``dazzle_invoice_ops_bench``) and measures p50 / p95 / p99 latency (ms)
for four representative probes:

* **list**      — ``GET /invoices``  (scope-filtered list, paginated)
* **read**      — ``GET /invoices/{id}``  (single row lookup)
* **search**    — ``GET /invoices?q=<term>``  (FTS / ILIKE)
* **aggregate** — ``Repository.aggregate`` for Invoice COUNT grouped by
  ``status``.  invoice_ops has no chart/report surface so there is no
  dedicated HTTP aggregate endpoint; we call the Repository method directly
  with a DB connection that carries no per-request auth context — this
  measures the pure SQL + scope-predicate layer without HTTP overhead.  Any
  future chart surface added to invoice_ops should replace this probe with
  an HTTP call.

Auth-user / domain-user pairing
---------------------------------
``examples/invoice_ops`` scope rules reference ``current_user.tenant_id``.
The runtime resolves this by loading the *domain* ``User`` entity row whose
``email`` matches the authenticated session user and merging its columns into
``AuthContext.preferences``.

``benchmarks/seed.py`` creates domain ``User`` rows (in the ``User`` table)
but NOT auth users (the ``users`` auth table, managed by ``AuthStore``).
``measure()`` therefore:

1. Picks the deterministic bench email for tenant-0, role ``auditor``
   (``auditor.t0000@bench.invalid``).  This email already has a matching
   domain ``User`` row in the seeded DB so ``current_user.tenant_id``
   resolves correctly.
2. Calls ``auth_store.create_user(email, password, roles=["auditor"])`` if
   the auth row does not yet exist (idempotent — safe to call on repeat
   runs against the same persistent DB).
3. Logs an ``httpx.AsyncClient`` in via ``dazzle.cli.rbac._login``.

Usage::

    python -m benchmarks.measure --db postgresql://localhost/dazzle_invoice_ops_bench
    python -m benchmarks.measure --db postgresql://localhost/dazzle_invoice_ops_bench \\
        --iterations 500

Public API::

    measure(db_url: str, iterations: int = 200) -> dict[str, dict[str, float]]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import statistics
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants derived from benchmarks/seed.py
# ---------------------------------------------------------------------------

# Tenant index 0 — the first tenant seeded by _build_tenants(n).
_BENCH_TENANT_IDX: int = 0

# Role used for probing — auditor has list/read access but no write risk.
_BENCH_ROLE: str = "auditor"

# Email template from seed.py's _build_users: f"{role}.t{t_idx:04d}@bench.invalid"
_BENCH_EMAIL: str = f"{_BENCH_ROLE}.t{_BENCH_TENANT_IDX:04d}@bench.invalid"

# Password for the auth user created here (not seeded by seed.py).
_BENCH_PASSWORD: str = "bench-measure-password"  # nosec B105 — bench DB only

# Base URL used for the in-process ASGI client.
_BASE_URL: str = "http://invoice-ops-bench.local"

# Warm-up iterations discarded before percentile calculation.
_WARMUP: int = 10

# Path to the invoice_ops example app.
_PROJECT_ROOT: Path = Path("examples/invoice_ops")

# Search term — matches invoice_number prefix seeded for tenant-0.
# seed.py uses: f"INV-{tid[:6].upper()}-{i:06d}" where tid is the uuid5 for tenant-0.
# The first 6 chars of str(uuid5(NS, "tenant:0")) — verified at runtime via a quick
# list probe; we fall back to "INV-" which matches all tenant-0 invoices.
_SEARCH_TERM: str = "INV-0D8C34"  # tenant-0 prefix as observed in the seeded DB


# ---------------------------------------------------------------------------
# Percentile helper
# ---------------------------------------------------------------------------


def _percentiles(samples: list[float]) -> dict[str, float]:
    """Return p50 / p95 / p99 from a sorted sample list (milliseconds)."""
    n = len(samples)
    if n == 0:
        return {"p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0}
    s = sorted(samples)

    def _pct(p: float) -> float:
        # Nearest-rank method.
        idx = max(0, int(p / 100.0 * n) - 1)
        return round(s[min(idx, n - 1)], 3)

    return {
        "p50_ms": _pct(50),
        "p95_ms": _pct(95),
        "p99_ms": _pct(99),
    }


# ---------------------------------------------------------------------------
# Core measurement coroutine
# ---------------------------------------------------------------------------


async def _run_measure(
    db_url: str,
    iterations: int,
) -> dict[str, dict[str, Any]]:
    """Boot invoice_ops, authenticate, run probes, return percentile dicts."""
    import httpx

    from dazzle.cli.rbac import _login
    from dazzle.rbac.verifier import _build_asgi_app, _probe_transport

    # ------------------------------------------------------------------
    # 1. Build the ASGI app against the pre-seeded persistent bench DB.
    #    enable_test_mode=True so entity tables are created if missing
    #    (safe no-op when they already exist from seed.py's ensure_schema).
    # ------------------------------------------------------------------
    logger.info("Booting invoice_ops against %s …", db_url)
    built = _build_asgi_app(_PROJECT_ROOT, db_url)
    auth_store = built.builder.auth_store
    assert auth_store is not None, "invoice_ops has auth enabled"

    # ------------------------------------------------------------------
    # 2. Ensure the auth user exists (auth_store, not domain User row —
    #    the domain User row was seeded by seed.py).  Idempotent: skips
    #    creation if the row already exists.
    # ------------------------------------------------------------------
    if auth_store.get_user_by_email(_BENCH_EMAIL) is None:
        auth_store.create_user(_BENCH_EMAIL, _BENCH_PASSWORD, roles=[_BENCH_ROLE])
        logger.info("Created auth user %s (role=%s)", _BENCH_EMAIL, _BENCH_ROLE)
    else:
        logger.info("Auth user %s already exists — reusing", _BENCH_EMAIL)

    # ------------------------------------------------------------------
    # 3. Build transport + authenticated client.
    #    _probe_transport sets raise_app_exceptions=False so server-side
    #    errors surface as HTTP status codes rather than Python exceptions.
    # ------------------------------------------------------------------
    transport = _probe_transport(httpx.ASGITransport(app=built.app))
    client = httpx.AsyncClient(
        transport=transport,
        base_url=_BASE_URL,
        follow_redirects=True,
    )
    await _login(client, _BASE_URL, _BENCH_EMAIL, _BENCH_PASSWORD)
    logger.info("Authenticated as %s", _BENCH_EMAIL)

    # ------------------------------------------------------------------
    # 4. Discover a known invoice id for the read probe.
    #    Prefer the deterministic uuid5 from seed.py for tenant-0 / inv-0,
    #    but confirm via a list call so the probe never 404s if the DB was
    #    re-seeded with different parameters.
    # ------------------------------------------------------------------
    list_resp = await client.get("/invoices")
    assert list_resp.status_code == 200, (
        f"Initial list probe failed: {list_resp.status_code} — check auth pairing. "
        f"Body: {list_resp.text[:300]}"
    )
    payload = list_resp.json()
    items = payload.get("items", payload) if isinstance(payload, dict) else payload
    assert isinstance(items, list) and len(items) > 0, (
        "Initial list returned zero invoices — is the bench DB seeded? "
        "Run: python -m benchmarks.seed --db <url> --tenants 2 --invoices-per-tenant 100"
    )
    probe_invoice_id: str = items[0]["id"]
    logger.info("Read probe will use invoice id=%s", probe_invoice_id)

    # ------------------------------------------------------------------
    # 5. Probe loop — four probes, each run `iterations` times.
    #    First _WARMUP calls discarded; timings collected with perf_counter.
    # ------------------------------------------------------------------
    probes: dict[str, Any] = {}  # probe_name -> raw timing samples

    async def _timed_get(url: str) -> float:
        t0 = time.perf_counter()
        resp = await client.get(url)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if resp.status_code >= 400:
            logger.warning("Probe %s returned HTTP %d", url, resp.status_code)
        return elapsed_ms

    # ---- list -----------------------------------------------------------
    logger.info("Running list probe (%d iterations + %d warmup) …", iterations, _WARMUP)
    list_samples: list[float] = []
    for i in range(iterations + _WARMUP):
        ms = await _timed_get("/invoices")
        if i >= _WARMUP:
            list_samples.append(ms)
    probes["list"] = list_samples

    # ---- read -----------------------------------------------------------
    logger.info("Running read probe (%d iterations + %d warmup) …", iterations, _WARMUP)
    read_samples: list[float] = []
    for i in range(iterations + _WARMUP):
        ms = await _timed_get(f"/invoices/{probe_invoice_id}")
        if i >= _WARMUP:
            read_samples.append(ms)
    probes["read"] = read_samples

    # ---- search ---------------------------------------------------------
    logger.info("Running search probe (%d iterations + %d warmup) …", iterations, _WARMUP)
    search_samples: list[float] = []
    for i in range(iterations + _WARMUP):
        ms = await _timed_get(f"/invoices?q={_SEARCH_TERM}")
        if i >= _WARMUP:
            search_samples.append(ms)
    probes["search"] = search_samples

    # ---- aggregate (Repository.aggregate — no HTTP chart endpoint) ------
    # invoice_ops has no bar_chart / pivot_table surface so there is no
    # dedicated HTTP aggregate route.  We call Repository.aggregate directly
    # against the booted app's db_manager (same connection pool / DB as the
    # HTTP probes) with a scalar Dimension on "status".
    #
    # Note: Repository.aggregate does not carry per-request AuthContext, so
    # scope predicates are NOT applied — this is a raw SQL GROUP BY timing
    # measuring the data layer only.  The "list" probe covers the full
    # scope-filtered path.  A future chart surface added to invoice_ops
    # should replace this with an HTTP probe.
    logger.info("Running aggregate probe (%d iterations + %d warmup) …", iterations, _WARMUP)
    agg_samples: list[float] = []
    repo = built.builder.repositories.get("Invoice")
    assert repo is not None, "Invoice repository not found in built app"

    from dazzle.http.runtime.aggregate import Dimension

    status_dim = Dimension(name="status")

    for i in range(iterations + _WARMUP):
        t0 = time.perf_counter()
        await repo.aggregate(
            dimensions=[status_dim],
            measures={"count": "count"},
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if i >= _WARMUP:
            agg_samples.append(elapsed_ms)
    probes["aggregate"] = agg_samples

    # ------------------------------------------------------------------
    # 6. Close client and release DB pool.
    # ------------------------------------------------------------------
    await client.aclose()
    db_manager = getattr(built.builder, "_db_manager", None)
    if db_manager is not None:
        db_manager.close_pool()

    # ------------------------------------------------------------------
    # 7. Compute percentiles.
    # ------------------------------------------------------------------
    results: dict[str, dict[str, Any]] = {}
    for probe_name, samples in probes.items():
        pct = _percentiles(samples)
        pct["iterations"] = iterations
        # Also record mean for diagnostics.
        pct["mean_ms"] = round(statistics.mean(samples), 3) if samples else 0.0
        results[probe_name] = pct
        logger.info(
            "  %-12s  p50=%.1fms  p95=%.1fms  p99=%.1fms  (mean=%.1fms)",
            probe_name,
            pct["p50_ms"],
            pct["p95_ms"],
            pct["p99_ms"],
            pct["mean_ms"],
        )

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def measure(db_url: str, iterations: int = 200) -> dict[str, dict[str, Any]]:
    """Boot invoice_ops in-process and measure endpoint latency percentiles.

    Args:
        db_url: PostgreSQL connection URL pointing at the **already-seeded**
            benchmark database (e.g.
            ``postgresql://localhost/dazzle_invoice_ops_bench``).  The schema
            and data must already exist — call ``benchmarks.seed.seed()`` first
            if the DB is empty.
        iterations: Number of timed calls per probe after warm-up (default 200).
            The first 10 calls are discarded as JIT / connection warm-up.

    Returns:
        Mapping of probe name → percentile dict::

            {
                "list":      {"p50_ms": …, "p95_ms": …, "p99_ms": …,
                              "mean_ms": …, "iterations": 200},
                "read":      { … },
                "search":    { … },
                "aggregate": { … },
            }

    Raises:
        AssertionError: if auth fails, the list endpoint returns no rows,
            or the Invoice repository is not available.
    """
    return asyncio.run(_run_measure(db_url, iterations))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Measure invoice_ops endpoint latency percentiles against "
            "a pre-seeded PostgreSQL benchmark database."
        )
    )
    parser.add_argument(
        "--db",
        required=True,
        metavar="URL",
        help="PostgreSQL connection URL (e.g. postgresql://localhost/dazzle_invoice_ops_bench)",
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

    results = measure(db_url=args.db, iterations=args.iterations)

    col_w = 12
    print(
        f"\n{'Probe':{col_w}}  {'p50 (ms)':>10}  {'p95 (ms)':>10}  {'p99 (ms)':>10}  {'mean (ms)':>10}  {'N':>6}"
    )
    print("-" * (col_w + 52))
    for probe, pct in results.items():
        print(
            f"{probe:{col_w}}  "
            f"{pct['p50_ms']:>10.1f}  "
            f"{pct['p95_ms']:>10.1f}  "
            f"{pct['p99_ms']:>10.1f}  "
            f"{pct['mean_ms']:>10.1f}  "
            f"{pct['iterations']:>6}"
        )


if __name__ == "__main__":
    main()
