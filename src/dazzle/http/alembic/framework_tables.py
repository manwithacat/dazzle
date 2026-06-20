"""Canonical registry of framework-owned tables in the project app database.

#1357: ``dazzle db revision --autogenerate`` compares the DSL-derived
SQLAlchemy metadata against the live database. Every table the framework
creates at runtime (auth store ``_init_db``, audit/event/grant/file DDL) is
absent from that metadata, so without an exclusion list autogenerate proposes
dropping all of them — a destructive migration against a healthy database.

This module is the single source of truth for "framework-owned". The drift
gate ``tests/unit/test_framework_tables_registry_1357.py`` scrapes every
``CREATE TABLE IF NOT EXISTS`` in ``src/dazzle/http/`` and fails if a new
runtime table is not registered here.
"""

from __future__ import annotations

# Tables created by framework runtime DDL (auth store, token/otp stores,
# grants, files, analytics, audit, events, deploy history, spec versioning,
# device registry, ops schema…). Names scraped from src/dazzle/http/ and
# pinned by the drift gate.
FRAMEWORK_TABLES: frozenset[str] = frozenset(
    {
        "alembic_version",  # alembic's own bookkeeping
        "analytics_events",
        "api_calls",
        "connection_secret_events",
        "connections",
        "dazzle_files",
        "deployment_history",
        "devices",
        "email_verification_tokens",
        "event_log",
        "health_checks",
        "invitations",
        "join_requests",
        "magic_links",
        "membership_events",
        "memberships",
        "ops_credentials",
        "organizations",
        "password_reset_tokens",
        "refresh_tokens",
        "retention_config",
        "saml_consumed_assertions",
        "scim_group_members",
        "scim_groups",
        "sessions",
        "spec_versions",
        "user_preferences",
        "users",
    }
)

# Any table starting with one of these prefixes is framework-owned by
# convention (audit log, event outbox/inbox, params, atomic audit, grants,
# ops schema) — prefix rules survive new members without registry edits.
FRAMEWORK_TABLE_PREFIXES: tuple[str, ...] = ("_dazzle_", "_grant", "_ops_")


def is_framework_table(name: str) -> bool:
    """True if *name* is a table the framework owns in the project app DB."""
    return name in FRAMEWORK_TABLES or name.startswith(FRAMEWORK_TABLE_PREFIXES)


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """Alembic ``include_object`` hook for autogenerate (#1188, #1357).

    Lives here (not env.py) because env.py executes only under the alembic
    context and cannot be imported by tests.

    - Framework-owned tables are not in the DSL metadata; without exclusion
      autogenerate proposes dropping all of them against a live DB.
    - Runtime-managed indexes (``idx_`` prefix: FTS GIN indexes,
      framework-table indexes) are created by DDL at boot, not by the
      metadata — reflected-only ``idx_*`` entries are skipped
      (metadata-emitted indexes use the ``ix_`` prefix).
    - Unnamed unique constraints cannot be reconciled by name, so Alembic
      re-emits them every run.
    """
    if type_ == "table" and name is not None and is_framework_table(name):
        return False
    if type_ == "index" and reflected and name is not None and name.startswith("idx_"):
        return False
    if type_ == "unique_constraint" and name is None:
        return False
    return True
