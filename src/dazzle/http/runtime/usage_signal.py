"""First-party usage-signal capture table (ADR-0050, Option A — Phase 1).

A lean, append-only framework table recording *end-user usage frequency* —
which surface field/action gets engaged — so the DSL→render inference layer can
refine data-driven UI choices (#1517 `1a` region-form inference, `3a` action
prominence) from real usage instead of only the static AppSpec.

**Scope (deliberately narrow).** This is NOT product analytics (no consent / GA4 /
PII vocabulary — those live in ``compliance/analytics/``) and NOT the orphaned ops
platform (health / API tracking / SSE). It captures exactly two event kinds —
``field`` engagement and ``action`` invocation — keyed by ``(tenant_id, surface,
target)``.

**Storage.** PostgreSQL only (ADR-0008). Append-only with a ``ts`` column so the
aggregate can apply a **time window** later (a usage signal must be able to
*decay* — a field popular a year ago should not dominate forever). ``tenant_id``
is ``''`` for single-tenant apps and the tenant slug/id otherwise; every read is
tenant-fenced (ADR-0050). The table is **orchestrator-only** — created by
``ensure_framework_schema`` at boot, never by a request-path ``_init_db`` — so it
needs no ``skip_boot_schema_ddl`` gating (there is no independent boot path).

Registered in the ADR-0047 db-artifact registry and built by the ADR-0044
framework-schema orchestrator; the squashed alembic baseline is regenerated from
that orchestrator (``dazzle db reframework-baseline``).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Kinds of usage event we record. ``field`` = a form field was engaged; ``action``
# = a surface action was invoked. Kept as a closed set so the aggregate + inferers
# can reason about exactly these two.
USAGE_KIND_FIELD = "field"
USAGE_KIND_ACTION = "action"

# One queued usage event: (tenant_id, surface, kind, target).
_UsageRow = tuple[str, str, str, str]


def ensure_usage_events_table(cur: Any) -> None:
    """Create ``_dazzle_usage_events`` and its indexes (idempotent).

    Single source of DDL for the usage-events table. Called only by the framework
    schema orchestrator (``_ensure_framework_schema_ddl``); no per-subsystem boot
    path, so no ``skip_boot_schema_ddl`` guard is needed. ``cur`` is an open
    psycopg cursor — the caller owns the commit.
    """
    cur.execute("""
        CREATE TABLE IF NOT EXISTS _dazzle_usage_events (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tenant_id TEXT NOT NULL DEFAULT '',
            surface TEXT NOT NULL,
            kind TEXT NOT NULL,
            target TEXT NOT NULL,
            ts TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    # The inference aggregate groups by (tenant_id, surface, kind, target); the
    # ts index serves time-windowed reads + any future retention prune.
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_events_agg "
        "ON _dazzle_usage_events (tenant_id, surface, kind, target)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_events_ts ON _dazzle_usage_events (tenant_id, ts)"
    )


def read_usage_counts(
    cur: Any,
    *,
    tenant_id: str | None,
    surface: str,
    window_days: int | None = None,
) -> dict[tuple[str, str], int]:
    """Tenant-fenced usage-frequency counts for one surface (ADR-0050 Phase 2).

    Returns ``{(kind, target): count}`` — e.g. ``{('action', 'approve'): 12,
    ('field', 'title'): 4}`` — for the given ``tenant_id`` (``''`` for single-tenant,
    matching the collector's coercion). This is the single read the render-time
    inferers (Phase 4) consume for `1a`/`3a`.

    **Tenant fence is the scope contract:** usage rows are framework-owned and
    tenant-keyed, so a plain ``WHERE tenant_id = %s`` is the isolation boundary —
    a second tenant's rows can never appear (no domain scope-predicate needed).

    **Recency:** ``window_days`` restricts to the trailing N days so a signal can
    *decay* (a field popular a year ago should not dominate forever). ``None`` =
    all-time. ``cur`` is an open psycopg cursor; the caller owns the connection.
    """
    sql = (
        "SELECT kind, target, count(*) AS n FROM _dazzle_usage_events "
        "WHERE tenant_id = %s AND surface = %s"
    )
    params: list[Any] = [tenant_id or "", surface]
    if window_days is not None:
        sql += " AND ts > now() - make_interval(days => %s)"
        params.append(window_days)
    sql += " GROUP BY kind, target"
    cur.execute(sql, params)
    # Factory-agnostic: the framework's pooled connection uses a dict_row factory
    # (rows are mappings), while a plain psycopg cursor yields tuples. Handle both.
    result: dict[tuple[str, str], int] = {}
    for row in cur.fetchall():
        if isinstance(row, dict):
            result[(row["kind"], row["target"])] = int(row["n"])
        else:
            result[(row[0], row[1])] = int(row[2])
    return result


def read_usage_counts_for_request(
    request: Any, *, surface: str, kind: str, window_days: int | None = 90
) -> dict[str, int]:
    """Best-effort per-render read of ``{target: count}`` for one ``(surface, kind)``.

    The single request-time read the render inferers share (3a action prominence,
    2d column economy). Leases a pooled connection from ``app.state.db_manager``,
    tenant-fenced to the resolved request tenant (``''`` for single-tenant). Returns
    ``{}`` on any failure / no DB — so the inferers fall back byte-identically to
    their declared default. The ``_dazzle_usage_events`` table is NON_FENCED, so
    tenant scoping is the explicit ``WHERE tenant_id`` filter, not RLS.
    """
    app = getattr(request, "app", None)
    state = getattr(app, "state", None) if app is not None else None
    db_mgr = getattr(state, "db_manager", None) if state is not None else None
    if db_mgr is None:
        return {}
    resolved = getattr(getattr(request, "state", None), "tenant", None)
    resolved_id = getattr(resolved, "id", None) if resolved is not None else None
    tenant_id = str(resolved_id) if resolved_id is not None else ""
    try:
        with db_mgr.connection() as conn, conn.cursor() as cur:
            raw = read_usage_counts(
                cur, tenant_id=tenant_id, surface=surface, window_days=window_days
            )
    except Exception:
        # Best-effort: a usage read must never break a render — fall back to the
        # declared default. WARNING (not debug) so a persistent failure is visible.
        logger.warning(
            "usage-signal read failed for %s/%s; using declared default",
            surface,
            kind,
            exc_info=True,
        )
        return {}
    return {target: cnt for (k, target), cnt in raw.items() if k == kind}


def record_usage_from_request(request: Any) -> None:
    """Record a heading-action click from the ``X-Dz-Usage-Action`` request header
    (ADR-0050 Phase 3, 3a). Internally safe — never raises, so a middleware can
    call it unguarded without risking the request path.

    The header (``"<surface>|<target>"``) is set by the hx-boosted heading-action
    anchors (`_render_shell`); it is present only on a heading-action click, so this
    is a no-op on every other request. The tenant key is the resolved request tenant
    id (``''`` for single-tenant), matching what ``read_usage_counts`` reads back.
    """
    header = request.headers.get("X-Dz-Usage-Action") if hasattr(request, "headers") else None
    if not header:
        return
    collector = getattr(getattr(request.app, "state", None), "usage_collector", None)
    if collector is None:
        return
    surface, sep, target = header.partition("|")
    if not sep or not surface or not target:
        return
    resolved = getattr(getattr(request, "state", None), "tenant", None)
    resolved_id = getattr(resolved, "id", None) if resolved is not None else None
    tenant_id = str(resolved_id) if resolved_id is not None else ""
    collector.record(tenant_id=tenant_id, surface=surface, kind=USAGE_KIND_ACTION, target=target)


class UsageSignalMiddleware:
    """Raw ASGI middleware that records heading-action clicks (ADR-0050 Phase 3, 3a).

    **Raw ASGI, NOT ``BaseHTTPMiddleware``** — the latter has body-consumption
    issues that break streaming/SSE responses (see the same rationale in
    ``csrf.py``/``api_middleware.py``). This passes ``receive``/``send`` through
    **untouched**, so streaming responses are unaffected, and records **after** the
    inner app completes — when ``request.state.tenant`` is resolved. ``record_usage_
    from_request`` is a no-op unless the ``X-Dz-Usage-Action`` header is present, so
    the per-request cost off the heading-action path is one dict lookup.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        await self.app(scope, receive, send)
        # Post-response: tenant state is now set. Reuse the internally-safe recorder
        # via a lightweight Request view over the same scope (no body read).
        from starlette.requests import Request

        record_usage_from_request(Request(scope))


class UsageCollector:
    """Async, non-blocking batched writer for ``_dazzle_usage_events`` (Phase 1b).

    Mirrors ``AuditLogger``'s pattern: callers ``record(...)`` (fire-and-forget,
    dropped under backpressure — a lost usage sample is harmless, the inference
    layer already tolerates sparse data via its cold-start fallback), a background
    ``_flush_loop`` batch-INSERTs on an interval, and ``start()``/``stop()`` are
    driven by the app lifespan (a running event loop is guaranteed at startup).

    PostgreSQL-only (ADR-0008). Does **not** create the table — that is the
    orchestrator's job (``ensure_usage_events_table``); the collector only writes.
    Dormant until Phase 3 wires ``record`` calls into the action/field paths.
    """

    def __init__(
        self,
        database_url: str,
        *,
        max_queue_size: int = 10000,
        flush_interval: float = 2.0,
    ) -> None:
        self._database_url = database_url
        self._flush_interval = flush_interval
        self._queue: asyncio.Queue[_UsageRow] = asyncio.Queue(maxsize=max_queue_size)
        self._dropped_count = 0
        self._task: asyncio.Task[None] | None = None
        self._stopped = False

    def record(self, *, tenant_id: str | None, surface: str, kind: str, target: str) -> None:
        """Enqueue one usage event (non-blocking; dropped when the queue is full).

        ``tenant_id`` is coerced to ``''`` for single-tenant apps so it matches the
        table's ``NOT NULL DEFAULT ''`` and the tenant-fenced read (Phase 2).
        """
        if not surface or not target:
            return
        try:
            self._queue.put_nowait((tenant_id or "", surface, kind, target))
        except asyncio.QueueFull:
            self._dropped_count += 1
            if self._dropped_count % 1000 == 1:
                logger.warning("Usage-signal queue full, dropped %d event(s)", self._dropped_count)

    def start(self) -> None:
        """Start the background flush task (call from within a running loop)."""
        if self._task is None or self._task.done():
            self._stopped = False
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._flush_loop())

    async def stop(self) -> None:
        """Stop the flush task and flush any remaining queued events."""
        self._stopped = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._flush()

    async def _flush_loop(self) -> None:
        while not self._stopped:
            try:
                await asyncio.sleep(self._flush_interval)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.warning("Usage-signal flush error", exc_info=True)

    async def _flush(self) -> None:
        rows = self._drain_queue()
        if rows:
            await asyncio.to_thread(self._write_rows, rows)

    def _drain_queue(self) -> list[_UsageRow]:
        rows: list[_UsageRow] = []
        while not self._queue.empty():
            try:
                rows.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return rows

    def _write_rows(self, rows: list[_UsageRow]) -> None:
        """Synchronously batch-INSERT drained events. Best-effort: a write failure
        is logged, never raised — usage capture must never break a request path."""
        if not rows:
            return
        try:
            import psycopg
        except ImportError:  # pragma: no cover - psycopg is a runtime dependency
            logger.warning("psycopg unavailable; usage-signal events dropped")
            return
        try:
            with psycopg.connect(self._database_url) as conn:
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO _dazzle_usage_events (tenant_id, surface, kind, target) "
                        "VALUES (%s, %s, %s, %s)",
                        rows,
                    )
                conn.commit()
        except Exception:
            logger.warning("Usage-signal batch write failed; %d event(s) lost", len(rows))
