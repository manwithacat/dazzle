"""Framework schema orchestrator — single advisory-locked boot-time DDL entry point.

``ensure_framework_schema(conn)`` creates ALL in-scope app-DB framework tables
unconditionally, under ONE ``pg_advisory_xact_lock``, idempotent on every call
(``CREATE TABLE/INDEX IF NOT EXISTS``, ``ADD COLUMN IF NOT EXISTS``).

**In-scope tables (usage-audited, spec §2 / plan global-constraints):**
  _dazzle_params; auth (users, sessions, memberships, organizations,
  membership_events, invitations, connections, connection_secret_events,
  scim_groups, scim_group_members, saml_consumed_assertions,
  password_reset_tokens, magic_links, email_verification_tokens,
  user_preferences, join_requests); process_runs, process_tasks;
  _dazzle_audit_log, _dazzle_atomic_audit, dazzle_files, refresh_tokens,
  devices, _grants, _grant_events, _dazzle_otp_codes, _dazzle_recovery_codes,
  _dazzle_event_inbox, _dazzle_event_outbox.

**Excluded (not in the app-DB baseline):**
  ops_database tables (separate DB); event-bus ``{prefix}events/offsets/dlq``
  (dynamic prefix, created by PostgresBus); tenant registry ``public.tenants``
  and per-tenant schemas.

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
from dazzle.http.events.inbox import CREATE_INBOX_INDEXES, CREATE_INBOX_TABLE
from dazzle.http.events.outbox import CREATE_OUTBOX_INDEXES, CREATE_OUTBOX_TABLE
from dazzle.http.runtime.auth.connections import CONNECTIONS_DDL, CONNECTIONS_INDEXES
from dazzle.http.runtime.auth.email_verification import EMAIL_VERIFICATION_TOKENS_DDL
from dazzle.http.runtime.auth.invitations import INVITATIONS_DDL, INVITATIONS_INDEXES
from dazzle.http.runtime.auth.magic_link import MAGIC_LINKS_DDL
from dazzle.http.runtime.auth.membership_events import (
    MEMBERSHIP_EVENTS_DDL,
    MEMBERSHIP_EVENTS_INDEXES,
)
from dazzle.http.runtime.auth.secret_rotation import (
    CONNECTION_SECRET_EVENTS_DDL,
    CONNECTION_SECRET_EVENTS_INDEXES,
)
from dazzle.http.runtime.triggers import build_assert_subtype_kind_function

logger = logging.getLogger(__name__)

# Single advisory lock for the full framework-schema DDL block.
# "fzdl" = 0x667A646C = 1722374252 (decimal).  Does not collide with the
# per-subsystem locks documented in the module docstring.
_FRAMEWORK_DDL_LOCK_KEY = 0x667A646C


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
        # DDL reused from AuthStore._init_db (auth/store.py) — no divergent
        # copy.  The per-column ADD … IF NOT EXISTS guards handle pre-existing
        # tables that pre-date the 2FA / email-verification columns.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                username TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                is_superuser BOOLEAN DEFAULT FALSE,
                roles TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # Idempotent column additions (mirrors AuthStore._init_db ALTER loop).
        for _col, _col_type, _default in [
            ("totp_secret", "TEXT", None),
            ("totp_enabled", "BOOLEAN", "FALSE"),
            ("email_otp_enabled", "BOOLEAN", "FALSE"),
            ("recovery_codes_generated", "BOOLEAN", "FALSE"),
            ("email_verified", "BOOLEAN", "FALSE"),
        ]:
            _default_clause = f" DEFAULT {_default}" if _default else ""
            cur.execute(
                f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {_col} {_col_type}{_default_clause}"
            )

        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")

        # Case-insensitive email uniqueness (#1342, M2) — functional unique index.
        # NOTE: In the orchestrator path we skip the pre-existing-collision check
        # that AuthStore._ensure_email_ci_uniqueness performs (that check raises
        # loudly for duplicate-email rows and is appropriate only for upgrade
        # paths on pre-existing databases; fresh installs never have the
        # conflict).  The structural index still enforces the invariant.
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_key ON users (LOWER(email))"
        )

        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                csrf_secret TEXT
            )
        """)
        cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS csrf_secret TEXT")
        cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS active_membership_id TEXT")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS memberships (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                identity_id TEXT NOT NULL,
                roles TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'active',
                invited_by TEXT,
                joined_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CONSTRAINT uq_memberships_tenant_identity UNIQUE (tenant_id, identity_id)
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_memberships_identity_id ON memberships(identity_id)"
        )
        cur.execute("CREATE INDEX IF NOT EXISTS ix_memberships_tenant_id ON memberships(tenant_id)")
        # external_id for SCIM dedup (#1342 gap 1)
        cur.execute("ALTER TABLE memberships ADD COLUMN IF NOT EXISTS external_id TEXT")
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_memberships_tenant_external "
            "ON memberships(tenant_id, external_id) WHERE external_id IS NOT NULL"
        )

        cur.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                is_test BOOLEAN NOT NULL DEFAULT false,
                settings TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CONSTRAINT uq_organizations_slug UNIQUE (slug)
            )
        """)

        # membership_events (auth Plan 2a) — reuse the DDL constant.
        cur.execute(MEMBERSHIP_EVENTS_DDL)
        for _ix in MEMBERSHIP_EVENTS_INDEXES:
            cur.execute(_ix)

        # invitations (auth Plan 3a) — reuse the DDL constant.
        cur.execute(INVITATIONS_DDL)
        for _ix in INVITATIONS_INDEXES:
            cur.execute(_ix)

        # connections (auth Plan 4a) — reuse the DDL constant.
        cur.execute(CONNECTIONS_DDL)
        for _ix in CONNECTIONS_INDEXES:
            cur.execute(_ix)

        # Grace-window columns for connections (#1342 alembic 0012).
        cur.execute(
            "ALTER TABLE connections ADD COLUMN IF NOT EXISTS previous_encrypted_secret TEXT"
        )
        cur.execute(
            "ALTER TABLE connections ADD COLUMN IF NOT EXISTS previous_secret_expires_at TEXT"
        )

        # connection_secret_events (#1342 rotation audit) — reuse the DDL constant.
        cur.execute(CONNECTION_SECRET_EVENTS_DDL)
        for _ix in CONNECTION_SECRET_EVENTS_INDEXES:
            cur.execute(_ix)

        # scim_groups + scim_group_members (#1342).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scim_groups (
                id            TEXT PRIMARY KEY,
                connection_id TEXT NOT NULL,
                display_name  TEXT NOT NULL,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL,
                UNIQUE (connection_id, display_name)
            )
        """)
        cur.execute("ALTER TABLE scim_groups ADD COLUMN IF NOT EXISTS external_id TEXT")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_scim_groups_conn ON scim_groups(connection_id)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS scim_group_members (
                group_id      TEXT NOT NULL REFERENCES scim_groups(id) ON DELETE CASCADE,
                membership_id TEXT NOT NULL,
                PRIMARY KEY (group_id, membership_id)
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_scim_group_members_member "
            "ON scim_group_members(membership_id)"
        )

        # saml_consumed_assertions (IdP-initiated replay cache, #1342).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS saml_consumed_assertions (
                assertion_id  TEXT PRIMARY KEY,
                connection_id TEXT NOT NULL,
                tenant_id     TEXT,
                expires_at    TEXT NOT NULL,
                created_at    TEXT NOT NULL
            )
        """)

        # password_reset_tokens.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used BOOLEAN DEFAULT FALSE
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_reset_tokens_user ON password_reset_tokens(user_id)"
        )

        # magic_links (#695) — reuse DDL constant.
        cur.execute(MAGIC_LINKS_DDL)

        # email_verification_tokens (#1109) — reuse DDL constant.
        cur.execute(EMAIL_VERIFICATION_TOKENS_DDL)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_email_verify_user ON email_verification_tokens(user_id)"
        )

        # user_preferences (v0.38.0).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT NOT NULL REFERENCES users(id),
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, key)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_prefs_user ON user_preferences(user_id)")

        # join_requests (#1424) — verified-domain self-service.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS join_requests (
                id          TEXT PRIMARY KEY,
                tenant_id   TEXT NOT NULL,
                identity_id TEXT NOT NULL,
                email       TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                created_at  TEXT NOT NULL,
                decided_at  TEXT,
                decided_by  TEXT
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_join_requests_tenant ON join_requests(tenant_id)"
        )
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_join_requests_pending "
            "ON join_requests(tenant_id, identity_id) WHERE status = 'pending'"
        )

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

        # _dazzle_audit_log (#1172) — DDL inlined (no module-level DDL constant
        # in audit_log.py; the class _init_db owns it).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS _dazzle_audit_log (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                user_id TEXT,
                user_email TEXT,
                user_roles TEXT,
                operation TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                entity_id TEXT,
                decision TEXT NOT NULL,
                matched_policy TEXT,
                policy_effect TEXT,
                ip_address TEXT,
                request_path TEXT,
                request_method TEXT,
                tenant_id TEXT,
                evaluation_time_us INTEGER,
                field_changes TEXT
            )
        """)
        # row_hash column (opt-in hash-chain integrity, #1197) — ADD IF NOT EXISTS
        # so existing tables without it are upgraded silently.
        cur.execute("ALTER TABLE _dazzle_audit_log ADD COLUMN IF NOT EXISTS row_hash TEXT")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_entity "
            "ON _dazzle_audit_log(entity_name, timestamp)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_user ON _dazzle_audit_log(user_id, timestamp)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON _dazzle_audit_log(timestamp)"
        )

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
        # DDL inlined (no module-level constant in file_storage.py).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dazzle_files (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                size BIGINT NOT NULL,
                storage_key TEXT NOT NULL,
                storage_backend TEXT NOT NULL,
                entity_name TEXT,
                entity_id TEXT,
                field_name TEXT,
                thumbnail_key TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_files_entity
            ON dazzle_files(entity_name, entity_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_files_field
            ON dazzle_files(entity_name, field_name)
        """)

        # ── REFRESH TOKENS ────────────────────────────────────────────────────
        # DDL inlined (no module-level constant in token_store.py).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_id TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at TEXT,
                ip_address TEXT,
                user_agent TEXT
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires ON refresh_tokens(expires_at)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_device "
            "ON refresh_tokens(user_id, device_id)"
        )

        # ── DEVICES ───────────────────────────────────────────────────────────
        # DDL inlined (no module-level constant in device_registry.py).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                push_token TEXT NOT NULL,
                device_name TEXT,
                app_version TEXT,
                os_version TEXT,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                UNIQUE(user_id, push_token)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_user_id ON devices(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_platform ON devices(platform)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_active ON devices(user_id, is_active)")

        # ── GRANTS (_grants, _grant_events) ──────────────────────────────────
        # DDL inlined (GrantStore._ensure_tables owns it; no module-level constant).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS _grants (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                schema_name     TEXT NOT NULL,
                relation        TEXT NOT NULL,
                principal_id    UUID NOT NULL,
                scope_entity    TEXT NOT NULL,
                scope_id        UUID NOT NULL,
                status          TEXT NOT NULL CHECK (status IN (
                    'pending_approval', 'active', 'rejected',
                    'cancelled', 'expired', 'revoked'
                )),
                granted_by_id   UUID NOT NULL,
                approved_by_id  UUID,
                granted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                approved_at     TIMESTAMPTZ,
                expires_at      TIMESTAMPTZ,
                revoked_at      TIMESTAMPTZ,
                revoked_by_id   UUID
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_grants_lookup
            ON _grants (principal_id, relation, scope_id, status)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_grants_expiry
            ON _grants (status, expires_at)
            WHERE status = 'active' AND expires_at IS NOT NULL
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS _grant_events (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                grant_id    UUID NOT NULL REFERENCES _grants(id),
                event_type  TEXT NOT NULL CHECK (event_type IN (
                    'created', 'approved', 'rejected',
                    'cancelled', 'revoked', 'expired'
                )),
                actor_id    UUID NOT NULL,
                timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
                metadata    JSONB
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_grant_events_grant_id
            ON _grant_events (grant_id)
        """)

        # ── OTP CODES (_dazzle_otp_codes) ────────────────────────────────────
        # DDL inlined (OTPStore.init_db uses f-string with TABLE constant).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS _dazzle_otp_codes (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                method TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                attempts INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 3,
                used BOOLEAN DEFAULT FALSE
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_otp_user_method ON _dazzle_otp_codes(user_id, method)"
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_otp_expires ON _dazzle_otp_codes(expires_at)")

        # ── RECOVERY CODES (_dazzle_recovery_codes) ──────────────────────────
        # DDL inlined (RecoveryCodeStore.init_db uses f-string with TABLE constant).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS _dazzle_recovery_codes (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                used BOOLEAN DEFAULT FALSE,
                used_at TEXT,
                created_at TEXT NOT NULL
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_recovery_user ON _dazzle_recovery_codes(user_id)"
        )

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

    conn.commit()
    logger.debug("ensure_framework_schema: all framework tables ensured")


# ---------------------------------------------------------------------------
# Per-subsystem helpers — thin wrappers that call ensure_framework_schema so
# the stores' existing call sites still work during the transition period
# (before all call sites are removed in Task 4 cleanup).
# ---------------------------------------------------------------------------


def ensure_params_table_conn(conn: Any) -> None:
    """Conn-taking wrapper used by the orchestrator for _dazzle_params only.

    Provided so the old ``ensure_dazzle_params_table(db_manager)`` call site
    in ``server.py`` can be migrated to pass a raw conn instead of a manager.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (_FRAMEWORK_DDL_LOCK_KEY,))
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
    conn.commit()
