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

from typing import Any

# Kinds of usage event we record. ``field`` = a form field was engaged; ``action``
# = a surface action was invoked. Kept as a closed set so the aggregate + inferers
# can reason about exactly these two.
USAGE_KIND_FIELD = "field"
USAGE_KIND_ACTION = "action"


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
