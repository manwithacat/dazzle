"""Static drift gate (#1342): every table AuthStore._init_db creates must be mirrored by an
alembic migration's ``op.create_table`` OR by the squashed baseline (0019_process_runtime_tables,
ADR-0044) — EXCEPT a known allowlist of tables that are now eagerly created by the orchestrator
and therefore appear in the baseline's DDL core rather than as op.create_table() calls.

The squashed baseline (Task 2, framework-migration-baseline plan) calls
``_ensure_framework_schema_ddl(cur)`` which executes raw SQL — those tables don't appear as
``op.create_table(...)`` in source.  The allowlist documents which tables are covered by the
baseline's DDL core vs. the old per-migration op.create_table pattern.

Pure source parsing — no DB — so it runs in the fast lane and the anti-drift teeth always
bite. The companion PG test (test_authstore_alembic_parity_pg) proves the chain coexists with
_init_db at runtime (the real prod order: _init_db creates base tables, then alembic alters)."""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_STORE = _REPO / "src/dazzle/http/runtime/auth/store.py"
_ALEMBIC = _REPO / "src/dazzle/http/alembic/versions"

# Tables _init_db creates INLINE (`CREATE TABLE IF NOT EXISTS`) that are mirrored by the
# squashed baseline (0019_process_runtime_tables) via its DDL core, NOT via op.create_table.
# ADR-0044: the baseline calls _ensure_framework_schema_ddl(cur) which executes raw SQL,
# so op.create_table() source-scanning never sees these tables.
# Any new _init_db table not in this set AND not in op.create_table() fails this gate.
_BASELINE_DDL_CORE_TABLES = {
    # Auth tables in _init_db inline DDL, now covered by ensure_auth_core_tables() via baseline:
    "memberships",
    "organizations",
    "saml_consumed_assertions",
    "scim_group_members",
    "scim_groups",
    "join_requests",
    # Tables always in _INIT_DB_PRIMARY_ONLY (not in _init_db inline DDL at all):
    "users",
    "sessions",
    "password_reset_tokens",
    "user_preferences",
}

# Kept for backward-compat reference — tables _init_db creates that alembic has never
# mirrored via op.create_table.  Now subsumed into _BASELINE_DDL_CORE_TABLES above.
_INIT_DB_PRIMARY_ONLY = _BASELINE_DDL_CORE_TABLES


def _init_db_tables() -> set[str]:
    src = _STORE.read_text(encoding="utf-8")
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", src))


def _alembic_created_tables() -> set[str]:
    tables: set[str] = set()
    for f in _ALEMBIC.glob("*.py"):
        src = f.read_text(encoding="utf-8")
        tables |= set(re.findall(r"""op\.create_table\(\s*["'](\w+)""", src))
    return tables


def test_init_db_tables_are_mirrored_in_alembic() -> None:
    init = _init_db_tables()
    alembic = _alembic_created_tables()
    assert init, "parser found no CREATE TABLE in _init_db — regex drift?"
    unmirrored = (init - alembic) - _INIT_DB_PRIMARY_ONLY
    assert not unmirrored, (
        f"tables in _init_db but NOT mirrored by an alembic op.create_table: "
        f"{sorted(unmirrored)}. Add an alembic migration mirroring them, or add to "
        "_INIT_DB_PRIMARY_ONLY (here AND in the PG gate) with a justifying note."
    )


def test_allowlist_has_no_stale_entries() -> None:
    # An allowlisted table that's since been mirrored should be removed from the allowlist —
    # keep it honest so the allowlist only ever names genuinely-unmirrored tables.
    init = _init_db_tables()
    alembic = _alembic_created_tables()
    stale = {t for t in _INIT_DB_PRIMARY_ONLY if t in alembic} | {
        t for t in _INIT_DB_PRIMARY_ONLY if t not in init
    }
    assert not stale, (
        f"allowlist entries that are mirrored or no longer in _init_db: {sorted(stale)}"
    )
