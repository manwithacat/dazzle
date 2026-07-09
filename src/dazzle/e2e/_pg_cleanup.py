"""Postgres-session cleanup for managed-mode subprocess lifecycle.

#1072 Bug A: when a previous `dazzle serve` subprocess is killed
(SIGTERM from CI timeout, Ctrl+C from operator, OOM kill, etc.), its
SQLAlchemy session pool can leak `idle in transaction` sessions that
hold table locks on the project's database. The next managed-mode
subprocess boots a fresh server, but its migrations / `CREATE INDEX`
queries block waiting on the leaked locks — from httpx's view the
request is accepted but never receives headers, so the contract runner
times out.

The fix here is defensive: before launching a fresh subprocess, scan
`pg_stat_activity` for `idle in transaction` sessions on the project's
database and terminate them. Only targets the same database the
subprocess is about to use; never touches other databases on the
cluster.

Best-effort: any psycopg / network / DSN error is swallowed and the
caller continues. The downstream subprocess boot will surface the
real problem (lock timeout) if cleanup somehow misses.
"""

from __future__ import annotations

import logging
from typing import Final

logger = logging.getLogger(__name__)

# Only target sessions left in the "idle in transaction" state by a
# previous run of dazzle. Other PG states ('active', 'idle', etc.) are
# legitimate concurrent users we don't want to disturb.
_IDLE_IN_TXN_STATES: Final[tuple[str, ...]] = (
    "idle in transaction",
    "idle in transaction (aborted)",
)


def terminate_stale_sessions(database_url: str) -> int:
    """Terminate `idle in transaction` sessions on the database in *database_url*.

    Args:
        database_url: Standard postgres DSN. Both libpq URI form
            (postgresql://user:pass@host:port/dbname) and key-value
            form are accepted by psycopg.

    Returns:
        Number of sessions terminated. Zero on any error (best-effort).
    """
    if not database_url:
        return 0

    try:
        import psycopg
    except ImportError:
        # psycopg is a core dependency, but tolerate its absence so the
        # e2e harness can be imported in environments where it isn't
        # installed (e.g. docs builds, parsing-only tooling).
        return 0

    try:
        # autocommit=True so we don't hold a transaction ourselves while
        # terminating the others.
        with psycopg.connect(database_url, autocommit=True) as conn:
            cur = conn.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND state = ANY(%s)
                  AND pid <> pg_backend_pid()
                """,
                (list(_IDLE_IN_TXN_STATES),),
            )
            rows = cur.fetchall()
    except Exception as exc:
        # Any error here is best-effort — log at debug, return 0,
        # and let the subprocess boot try its luck.
        logger.debug("PG cleanup skipped: %s", exc, exc_info=False)
        return 0

    terminated = sum(1 for (ok,) in rows if ok)
    if terminated:
        logger.info(
            "Terminated %d stale `idle in transaction` PG session(s) before launch",
            terminated,
        )
    return terminated
