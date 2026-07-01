"""Framework schema orchestrator — single advisory-locked boot-time DDL entry point.

``ensure_framework_schema(conn)`` creates ALL in-scope app-DB framework tables
unconditionally, under ONE ``pg_advisory_xact_lock``, idempotent on every call
(``CREATE TABLE/INDEX IF NOT EXISTS``, ``ADD COLUMN IF NOT EXISTS``).

**In-scope tables:** declared once in the DB-artifact registry
(``dazzle.db.artifact_registry.in_baseline_tables``, ADR-0047); this orchestrator
creates exactly that set. Do not re-list tables here — the registry is the single
source (it also carries each table's class / owner / RLS posture / boot-DDL gating).

**Excluded classes (registry rows too, ``in_baseline=False``):** ops_database
tables (separate DB); event-bus ``{prefix}events/offsets/dlq`` (dynamic prefix,
created by PostgresBus); tenant registry ``public.tenants`` + per-tenant schemas.

**Advisory lock strategy:**
  A single ``pg_advisory_xact_lock(0x667A646C)`` ("fzdl" = framework-schema
  DDL) serialises concurrent boot workers for the full DDL block.  Released on
  commit.  Does not overlap with the per-subsystem locks:
    AUTH_DDL_LOCK_KEY    = 0x647A646C  (auth store)
    _PROCESS_DDL_LOCK_KEY = 0x70726F63 (process schema)
    _AUDIT_LOG_LOCK_KEY  = 0x61756474 (audit log)

**Behavior change (accepted, documented in CHANGELOG + ADR-0044):**
  Previously these tables were created lazily/conditionally on first use.
  Now they are created eagerly for every app at boot time.  Each table has
  live consumers (usage-audited 2026-06-23); none is dead code.

**Dual-write rule (widened by ADR-0044):**
  A new framework table goes in the orchestrator here; the squashed alembic
  baseline (0019_process_runtime_tables, down_revision=None) is then
  regenerated.  Per-subsystem DDL methods delegate here — no divergent creator.
"""

from __future__ import annotations

import logging
from typing import Any

# DDL constants re-used from their canonical home modules (no duplication).
# All imports are at module top — none of these create circular imports.
from dazzle.core.coordination.claim import queue_columns_ddl
from dazzle.http.channels.outbox import ensure_outbox_table
from dazzle.http.events.inbox import CREATE_INBOX_INDEXES, CREATE_INBOX_TABLE
from dazzle.http.events.outbox import CREATE_OUTBOX_INDEXES, CREATE_OUTBOX_TABLE
from dazzle.http.runtime.audit_log import ensure_audit_log_table
from dazzle.http.runtime.auth.store import ensure_auth_core_tables
from dazzle.http.runtime.device_registry import ensure_device_tables
from dazzle.http.runtime.file_storage import ensure_file_storage_tables
from dazzle.http.runtime.grant_store import ensure_grant_tables
from dazzle.http.runtime.otp_store import ensure_otp_tables
from dazzle.http.runtime.recovery_codes import ensure_recovery_code_tables
from dazzle.http.runtime.token_store import ensure_refresh_token_tables
from dazzle.http.runtime.triggers import build_assert_subtype_kind_function
from dazzle.http.runtime.usage_signal import ensure_usage_events_table

logger = logging.getLogger(__name__)

# Single advisory lock for the full framework-schema DDL block.
# "fzdl" = 0x667A646C = 1722374252 (decimal).  Does not collide with the
# per-subsystem locks documented in the module docstring.
_FRAMEWORK_DDL_LOCK_KEY = 0x667A646C


def _ensure_framework_schema_ddl(cur: Any) -> None:  # cur: psycopg.Cursor
    """Execute all framework-schema DDL statements on an open cursor.

    This is the no-commit, no-lock DDL core.  It is called by:
    - ``ensure_framework_schema`` (which wraps it with advisory-lock + commit)
    - The squashed Alembic baseline ``0019_process_runtime_tables`` (which
      runs inside Alembic's migration transaction — no separate commit or lock)

    Every statement uses ``IF NOT EXISTS`` / ``CREATE OR REPLACE`` so the
    function is idempotent.

    Args:
        cur: An open psycopg cursor in an active transaction.  The caller
             is responsible for committing (or rolling back) afterwards.
    """
    # ── assert_subtype_kind plpgsql function ──────────────────────────────
    # Created unconditionally (CREATE OR REPLACE).  Required by the
    # per-child-table triggers that enforce subtype kind consistency
    # (#1217 Phase 3e.iii).  Previously created lazily by pg_backend.py
    # only when child entities were present; now ensured for every app.
    cur.execute(build_assert_subtype_kind_function())

    # ── _dazzle_params (#572) ─────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS _dazzle_params (
            key TEXT NOT NULL,
            scope TEXT NOT NULL,
            scope_id TEXT NOT NULL DEFAULT '',
            value_json JSONB NOT NULL,
            updated_by TEXT,
            updated_at TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (key, scope, scope_id)
        )
    """)

    # ── AUTH TABLES ───────────────────────────────────────────────────────
    # Delegated to ensure_auth_core_tables (auth/store.py) — single
    # definition, two callers (store._init_db + this orchestrator).
    ensure_auth_core_tables(cur)
    # Case-insensitive email uniqueness (#1342, M2) is part of the
    # migration-managed schema so a NON-OWNER production runtime (which skips
    # AuthStore._init_db, #1462) still gets the structural backstop. Safe here
    # unconditionally: the baseline only runs against a fresh DB (no rows → no
    # LOWER(email) collisions), and an upgrade-path DB already carries this index
    # from a prior _init_db, so IF NOT EXISTS is a no-op. The loud collision
    # *pre-check* stays in AuthStore._ensure_email_ci_uniqueness for the dev path.
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_key ON users (LOWER(email))")

    # ── PROCESS TABLES (process_runs, process_tasks) ──────────────────────
    # Reuse queue_columns_ddl (single source of truth for queue columns).
    runs_queue_cols = queue_columns_ddl("process_runs")
    tasks_queue_cols = queue_columns_ddl("process_tasks")

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS process_runs (
            run_id              text        NOT NULL PRIMARY KEY,
            process_name        text        NOT NULL,
            process_version     text        NOT NULL DEFAULT 'v1',
            dsl_version         text        NOT NULL DEFAULT '0.1',
            current_step        text,
            inputs              jsonb       NOT NULL DEFAULT '{{}}'::jsonb,
            context             jsonb       NOT NULL DEFAULT '{{}}'::jsonb,
            outputs             jsonb,
            error               text,
            idempotency_key     text,
            started_at          timestamptz NOT NULL DEFAULT now(),
            updated_at          timestamptz NOT NULL DEFAULT now(),
            completed_at        timestamptz,
            {runs_queue_cols}
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS ix_process_runs_due
        ON process_runs (deliver_at)
        WHERE status IN ('pending', 'claimed')
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS ix_process_runs_idempotency_key
        ON process_runs (idempotency_key)
        WHERE idempotency_key IS NOT NULL
    """)

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS process_tasks (
            task_id             text        NOT NULL PRIMARY KEY,
            run_id              text        NOT NULL
                REFERENCES process_runs (run_id) ON DELETE CASCADE,
            step_name           text        NOT NULL,
            surface_name        text        NOT NULL,
            entity_name         text        NOT NULL,
            entity_id           text        NOT NULL,
            assignee_id         text,
            assignee_role       text,
            outcome             text,
            outcome_data        jsonb,
            due_at              timestamptz NOT NULL,
            escalated_at        timestamptz,
            completed_at        timestamptz,
            created_at          timestamptz NOT NULL DEFAULT now(),
            {tasks_queue_cols}
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS ix_process_tasks_due
        ON process_tasks (deliver_at)
        WHERE status IN ('pending', 'claimed')
    """)

    # ── AUDIT TABLES ──────────────────────────────────────────────────────
    # Delegated to ensure_audit_log_table (audit_log.py) — single
    # definition, two callers.  The orchestrator unconditionally adds the
    # row_hash column (ADD COLUMN IF NOT EXISTS is a no-op when absent) so
    # hash-chain upgrades work without a separate migration step.
    ensure_audit_log_table(cur, hash_chain=True)

    # _dazzle_atomic_audit (#1317, ADR-0029).
    cur.execute("""
        CREATE TABLE IF NOT EXISTS _dazzle_atomic_audit (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            flow_name TEXT NOT NULL,
            user_id TEXT,
            user_email TEXT,
            user_roles TEXT,
            operation TEXT NOT NULL,
            entity_name TEXT NOT NULL,
            entity_id TEXT,
            decision TEXT NOT NULL,
            matched_policy TEXT
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_atomic_audit_flow "
        "ON _dazzle_atomic_audit(flow_name, timestamp)"
    )

    # ── FILE STORAGE (dazzle_files) ───────────────────────────────────────
    # Delegated to ensure_file_storage_tables (file_storage.py).
    ensure_file_storage_tables(cur)

    # ── REFRESH TOKENS ────────────────────────────────────────────────────
    # Delegated to ensure_refresh_token_tables (token_store.py).
    ensure_refresh_token_tables(cur)

    # ── DEVICES ───────────────────────────────────────────────────────────
    # Delegated to ensure_device_tables (device_registry.py).
    ensure_device_tables(cur)

    # ── GRANTS (_grants, _grant_events) ──────────────────────────────────
    # Delegated to ensure_grant_tables (grant_store.py).
    ensure_grant_tables(cur)

    # ── OTP CODES (_dazzle_otp_codes) ────────────────────────────────────
    # Delegated to ensure_otp_tables (otp_store.py).
    ensure_otp_tables(cur)

    # ── RECOVERY CODES (_dazzle_recovery_codes) ──────────────────────────
    # Delegated to ensure_recovery_code_tables (recovery_codes.py).
    ensure_recovery_code_tables(cur)

    # ── EVENT INBOX / OUTBOX (fixed names) ───────────────────────────────
    # The FIXED framework tables _dazzle_event_inbox and _dazzle_event_outbox
    # are in-scope.  The PREFIXED {prefix}events/offsets/dlq tables (created
    # by PostgresBus._create_tables) are EXCLUDED (dynamic prefix).
    # DDL constants from inbox.py / outbox.py.
    cur.execute(CREATE_INBOX_TABLE)
    for _ix in CREATE_INBOX_INDEXES:
        cur.execute(_ix)

    cur.execute(CREATE_OUTBOX_TABLE)
    for _ix_name, _ix_sql in CREATE_OUTBOX_INDEXES:
        cur.execute(_ix_sql)

    # ── CHANNEL DELIVERY OUTBOX (_dazzle_outbox) ─────────────────────────
    # #1499: a fixed-name framework table that was previously created ungated at
    # boot by ChannelManager (and missing from this baseline). Now delegated to the
    # single ensure_outbox_table DDL (channels/outbox.py), like the other tables.
    ensure_outbox_table(cur)

    # ── USAGE SIGNAL (_dazzle_usage_events) ──────────────────────────────
    # ADR-0050 Option A: first-party usage-frequency capture feeding UX inference.
    # Orchestrator-only (no request-path boot entry) — single DDL source in
    # usage_signal.py.
    ensure_usage_events_table(cur)


def ensure_framework_schema(conn: Any) -> None:  # conn: psycopg.Connection
    """Create ALL in-scope app-DB framework tables if they don't exist.

    Idempotent — safe to call on every boot worker simultaneously.  The
    ``pg_advisory_xact_lock`` serialises concurrent callers at the Postgres
    level; ``IF NOT EXISTS`` / ``ADD COLUMN IF NOT EXISTS`` make every
    statement a no-op when the object is already present.

    The connection is committed inside this function (same pattern as
    ``AuthStore._init_db`` and ``ensure_process_tables``).

    Args:
        conn: A psycopg synchronous connection (autocommit=False).  The caller
              must NOT already be inside a transaction; the lock is transaction-
              scoped and released on commit.
    """
    with conn.cursor() as cur:
        # ── single lock for the whole block ──────────────────────────────────
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (_FRAMEWORK_DDL_LOCK_KEY,))
        _ensure_framework_schema_ddl(cur)

    conn.commit()
    logger.debug("ensure_framework_schema: all framework tables ensured")
