"""Static drift gate (#1342): every table AuthStore._init_db creates must be mirrored by an
alembic migration's ``op.create_table`` — EXCEPT a known allowlist of tables alembic
deliberately doesn't create yet (the deferred full-consolidation set). A new ``_init_db``-only
table that isn't mirrored fails this gate, forcing the author to add the alembic mirror (or
consciously extend the allowlist with a note).

Pure source parsing — no DB — so it runs in the fast lane and the anti-drift teeth always
bite. The companion PG test (test_authstore_alembic_parity_pg) proves the chain coexists with
_init_db at runtime (the real prod order: _init_db creates base tables, then alembic alters)."""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_STORE = _REPO / "src/dazzle/back/runtime/auth/store.py"
_ALEMBIC = _REPO / "src/dazzle/back/alembic/versions"

# Tables _init_db creates INLINE (`CREATE TABLE IF NOT EXISTS`) that alembic deliberately does
# NOT mirror yet — the deferred full-consolidation set. (magic_links / email_verification_tokens
# are created via imported DDL constants, not inline, so the regex below never sees them and
# they don't belong here.) See docs/superpowers/specs/2026-06-08-authstore-alembic-parity-
# foundation-design.md.
_INIT_DB_PRIMARY_ONLY = {
    "users",
    "sessions",
    "password_reset_tokens",
    "user_preferences",
}


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
