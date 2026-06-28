"""Shared PostgreSQL helpers for the auth e2e tests (`@pytest.mark.e2e`).

The auth stores are PostgreSQL-only (ADR-0008: no SQLite in the runtime), so these
tests need a live test database. They skip when none is configured and reset their
own tables per test for isolation — mirroring tests/unit/test_grant_store.py.

URL resolution matches the project's PG-test convention: `TEST_DATABASE_URL` (local
dev) or `DATABASE_URL` (the CI postgres-service jobs).
"""

from __future__ import annotations

import os

import psycopg
import pytest

# Tables each store's _init_db() creates — dropped per test for a clean slate.
AUTH_TABLES = (
    "users",
    "sessions",
    "memberships",
    "organizations",
    "scim_groups",
    "scim_group_members",
    "saml_consumed_assertions",
    "password_reset_tokens",
    "user_preferences",
    "join_requests",
)
TOKEN_TABLES = ("refresh_tokens",)
DEVICE_TABLES = ("devices",)


def has_pg() -> bool:
    """True when a test database URL is configured (for class-level skipif)."""
    return bool(os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL"))


def pg_url_or_skip() -> str:
    """The test Postgres URL, or skip the test if none is configured."""
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL / DATABASE_URL not set — PostgreSQL auth tests skipped")
    return url


def reset_tables(url: str, *tables: str) -> None:
    """Drop the given tables (CASCADE) so the store's _init_db recreates them clean."""
    conn = psycopg.connect(url)
    try:
        conn.execute("DROP TABLE IF EXISTS " + ", ".join(tables) + " CASCADE")
        conn.commit()
    finally:
        conn.close()


def fresh_url(*tables: str) -> str:
    """Skip-or-resolve the URL and reset the given tables for a clean slate."""
    url = pg_url_or_skip()
    reset_tables(url, *tables)
    return url
