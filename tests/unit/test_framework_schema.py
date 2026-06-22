"""Real-PG tests for ensure_framework_schema.

Skipped unless DATABASE_URL is set.  The test creates a scratch schema,
calls ensure_framework_schema, asserts every in-scope table and the
assert_subtype_kind function exist, calls again (idempotency), then drops
the scratch schema.
"""

from __future__ import annotations

import os
import uuid

import pytest

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping real-PG framework-schema tests",
)

# Every in-scope table (spec §2 / plan global-constraints).
IN_SCOPE_TABLES: list[str] = [
    # params
    "_dazzle_params",
    # auth
    "users",
    "sessions",
    "memberships",
    "organizations",
    "membership_events",
    "invitations",
    "connections",
    "connection_secret_events",
    "scim_groups",
    "scim_group_members",
    "saml_consumed_assertions",
    "password_reset_tokens",
    "magic_links",
    "email_verification_tokens",
    "user_preferences",
    "join_requests",
    # process
    "process_runs",
    "process_tasks",
    # audit/misc
    "_dazzle_audit_log",
    "_dazzle_atomic_audit",
    "dazzle_files",
    "refresh_tokens",
    "devices",
    "_grants",
    "_grant_events",
    "_dazzle_otp_codes",
    "_dazzle_recovery_codes",
    "_dazzle_event_inbox",
    "_dazzle_event_outbox",
]


def _scratch_schema() -> str:
    """A unique scratch schema name for this test run."""
    return f"_dz_test_{uuid.uuid4().hex[:12]}"


@pytest.fixture()
def pg_conn():
    """A psycopg connection and a scratch schema, cleaned up after the test."""
    import psycopg
    from psycopg.rows import dict_row

    schema = _scratch_schema()
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    conn.autocommit = False

    cur = conn.cursor()
    cur.execute(f"CREATE SCHEMA {schema}")
    cur.execute(f"SET search_path TO {schema}, public")
    conn.commit()

    yield conn, schema

    # Cleanup — drop the scratch schema and close.
    try:
        conn.rollback()
        conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        conn.commit()
    finally:
        conn.close()


def _tables_in_schema(conn: object, schema: str) -> set[str]:
    """Return the set of table names in *schema*."""
    cur = conn.cursor()  # type: ignore[union-attr]
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = %s AND table_type = 'BASE TABLE'",
        (schema,),
    )
    return {row["table_name"] for row in cur.fetchall()}


def _function_exists(conn: object, schema: str, fn_name: str) -> bool:
    """Return True iff a function with *fn_name* exists in *schema*."""
    cur = conn.cursor()  # type: ignore[union-attr]
    cur.execute(
        "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = %s AND p.proname = %s LIMIT 1",
        (schema, fn_name),
    )
    return cur.fetchone() is not None


class TestEnsureFrameworkSchema:
    def test_all_in_scope_tables_exist_after_call(self, pg_conn: tuple) -> None:
        """After one call, every in-scope table must be present."""
        conn, schema = pg_conn

        from dazzle.http.runtime.framework_schema import ensure_framework_schema

        ensure_framework_schema(conn)

        present = _tables_in_schema(conn, schema)
        missing = sorted(set(IN_SCOPE_TABLES) - present)
        assert not missing, f"Missing tables after ensure_framework_schema: {missing}"

    def test_assert_subtype_kind_function_exists(self, pg_conn: tuple) -> None:
        """The assert_subtype_kind plpgsql function must be created."""
        conn, schema = pg_conn

        from dazzle.http.runtime.framework_schema import ensure_framework_schema

        ensure_framework_schema(conn)

        assert _function_exists(conn, schema, "assert_subtype_kind"), (
            "assert_subtype_kind function not found in schema"
        )

    def test_idempotent_second_call_is_no_error(self, pg_conn: tuple) -> None:
        """Calling twice must not raise (IF NOT EXISTS semantics)."""
        conn, schema = pg_conn

        from dazzle.http.runtime.framework_schema import ensure_framework_schema

        ensure_framework_schema(conn)
        # Second call: must be a no-op
        ensure_framework_schema(conn)

        present = _tables_in_schema(conn, schema)
        missing = sorted(set(IN_SCOPE_TABLES) - present)
        assert not missing, f"Missing tables after second call: {missing}"

    def test_excluded_tables_not_created(self, pg_conn: tuple) -> None:
        """Ops-DB, prefixed event-bus, and tenant-registry tables must NOT appear."""
        conn, schema = pg_conn

        from dazzle.http.runtime.framework_schema import ensure_framework_schema

        ensure_framework_schema(conn)

        present = _tables_in_schema(conn, schema)
        # These are the canonical exclusions from spec §2 / plan global constraints.
        excluded = {
            "tenants",  # tenant registry (public.tenants, separate)
            # ops-DB tables — not exhaustive, just a representative sample
            "api_requests",
            "health_checks",
        }
        leaked = present & excluded
        assert not leaked, f"Excluded tables leaked into framework schema: {leaked}"
