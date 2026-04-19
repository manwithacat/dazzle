"""Set of entity names backed by non-PostgreSQL stores.

``SystemHealth``, ``SystemMetric``, ``ProcessRun``, ``LogEntry``,
``EventTrace`` are synthetic platform entities whose data lives in
Redis or in-memory buffers, not in Postgres. They appear in the
AppSpec (so the admin workspace can render them) but they have no
SQL table — :func:`dazzle_back.runtime.sa_schema.build_metadata`
filters them out, and :func:`dazzle.db.reset.db_reset_impl` must do
the same (#814).

Kept at the ``dazzle.db`` layer so both the server-side schema
builder and the client-side reset helper import the same source of
truth.
"""

from __future__ import annotations

VIRTUAL_ENTITY_NAMES: frozenset[str] = frozenset(
    {
        "SystemHealth",
        "SystemMetric",
        "ProcessRun",
        "LogEntry",
        "EventTrace",
    }
)
