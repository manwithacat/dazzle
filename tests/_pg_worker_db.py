"""Per-xdist-worker PostgreSQL database provisioning.

Gives every xdist worker its own database (``<base>_gw0``, ``<base>_gw1``, …)
so postgres-backed tests parallelise without cross-worker state contention:
the worker's ``pytest_configure`` (see tests/conftest.py) rewrites
TEST_DATABASE_URL / DATABASE_URL before any test module is imported, which
matters because most postgres test files read the URL at module import time
(``_PG_URL = os.environ.get(...)`` at module top).

Falls back gracefully: when the role can't CREATE DATABASE (or psycopg /
the server is unavailable), tests/conftest.py pins all postgres-marked tests
to a single worker via ``xdist_group`` instead — serial semantics, as before
the v0.92.80 parallelisation.

Provisioned databases are created empty. That is sufficient by construction:
the postgres suite either creates per-test scratch databases itself or lazily
creates its tables with idempotent ``CREATE TABLE IF NOT EXISTS`` DDL (the
2026-07-02 sweep of all 63 postgres-marked files found no test that assumes
externally pre-created schema — see
dev_docs/2026-07-02-ci-runtime-and-suite-size-analysis.md).
"""

import functools
import os
import time
from urllib.parse import urlsplit, urlunsplit

PG_ENV_VARS = ("TEST_DATABASE_URL", "DATABASE_URL")


def base_pg_url() -> str | None:
    """The configured Postgres URL, with TEST_DATABASE_URL taking precedence."""
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _split_dbname(url: str) -> tuple:
    """Return (urlsplit parts, database name) for a postgres URL."""
    parts = urlsplit(url)
    dbname = parts.path.lstrip("/") or "postgres"
    return parts, dbname


def worker_db_url(url: str, worker_id: str) -> tuple[str, str]:
    """Return (rewritten url, worker database name) for this worker."""
    parts, dbname = _split_dbname(url)
    worker_db = f"{dbname}_{worker_id}"
    rewritten = urlunsplit(parts._replace(path=f"/{worker_db}"))
    return rewritten, worker_db


@functools.lru_cache(maxsize=1)
def can_create_databases(url: str) -> bool:
    """True when the URL's role may CREATE DATABASE (superuser or CREATEDB).

    Any failure (driver missing, server down, auth error) returns False —
    the caller falls back to single-worker pinning, and whatever is actually
    wrong surfaces through the tests' own skip/fail behaviour.
    """
    try:
        import psycopg

        with psycopg.connect(url, connect_timeout=5) as conn:
            row = conn.execute(
                "SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname = current_user"
            ).fetchone()
            return bool(row and row[0])
    except Exception:
        return False


def provision_worker_database(url: str, worker_id: str) -> str:
    """Create (drop-if-exists first) this worker's database; return its URL.

    DROP … WITH (FORCE) clears leftovers from interrupted earlier runs even
    if stale connections linger (PostgreSQL 13+). The short retry loop covers
    transient contention when several workers CREATE DATABASE from template1
    at the same moment. Raises on definitive failure — the caller turns that
    into a loud usage error rather than silently sharing the base database.
    """
    import psycopg

    new_url, worker_db = worker_db_url(url, worker_id)
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            with psycopg.connect(url, autocommit=True, connect_timeout=10) as conn:
                conn.execute(f'DROP DATABASE IF EXISTS "{worker_db}" WITH (FORCE)')
                conn.execute(f'CREATE DATABASE "{worker_db}"')
            return new_url
        except Exception as exc:  # noqa: BLE001 — retried, then re-raised below
            last_exc = exc
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"could not provision per-worker database {worker_db!r}: {last_exc}")
