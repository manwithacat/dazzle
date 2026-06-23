"""
Alembic environment configuration for Dazzle.

Reads DATABASE_URL from the environment and uses the EntitySpec → SQLAlchemy
MetaData bridge as ``target_metadata`` so that ``--autogenerate`` can diff
the DSL schema against the live database.
"""

import logging
import os
import sys
from logging.config import fileConfig
from pathlib import Path
from typing import Any

import sqlalchemy
from alembic import context

from dazzle.core.db_url import add_psycopg_driver, normalise_postgres_scheme

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Alembic Config object (provides access to alembic.ini values)
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging (if present).
# disable_existing_loggers=False is load-bearing: fileConfig defaults to True, which
# would silence every already-configured app logger (e.g. dazzle.http.runtime.auth.store)
# whenever a migration runs in-process — running `dazzle db upgrade` must not nuke the
# host app's logging, and it broke caplog-based tests downstream of a migration.
if config.config_file_name and os.path.exists(config.config_file_name):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# ---------------------------------------------------------------------------
# Target metadata — built from DSL EntitySpecs
# ---------------------------------------------------------------------------

# Ensure the project src/ is on sys.path so imports work.
_src = str(Path(__file__).resolve().parents[2])  # src/
if _src not in sys.path:
    sys.path.insert(0, _src)


def _load_target_metadata() -> sqlalchemy.MetaData:
    """Lazily load target metadata from the active Dazzle project.

    Delegates to the side-effect-free :func:`load_target_metadata` and falls
    back to empty MetaData on failure (e.g. when running ``alembic current``
    without a project context). The actual DSL→metadata logic lives in
    ``dazzle.http.alembic.metadata_loader`` so callers outside an Alembic run
    can reuse it without importing this module (which executes
    ``config = context.config`` at import time).
    """
    from dazzle.http.alembic.metadata_loader import load_target_metadata

    try:
        return load_target_metadata()
    except Exception:
        logger.warning("Failed to load target metadata from DSL", exc_info=True)
        return sqlalchemy.MetaData()


target_metadata = _load_target_metadata()

# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------


def _get_url() -> str:
    """Get database URL from alembic config or env.

    Prefers ``sqlalchemy.url`` (already normalised by ``db.py``) over the raw
    ``DATABASE_URL`` env var.  Handles Heroku's ``postgres://`` scheme and
    ensures the psycopg v3 driver is used.
    """
    url = config.get_main_option("sqlalchemy.url", "") or os.environ.get("DATABASE_URL", "")
    # Heroku uses the deprecated postgres:// scheme — normalise it, then
    # ensure SQLAlchemy uses psycopg v3, not psycopg2.
    return add_psycopg_driver(normalise_postgres_scheme(url))


# ---------------------------------------------------------------------------
# Revision directive hook
# ---------------------------------------------------------------------------


def _alembic_config(context: Any) -> Any:
    """Return the Alembic ``Config`` for this run, or ``None`` if unavailable.

    The hook receives a :class:`MigrationContext`; its ``environment_context``
    holds the live ``Config``. ``cfg.attributes`` is the documented Alembic
    side-channel between ``dazzle db`` (the command) and this hook — already used
    for ``tenant_schema`` — and is how Task 3.3 passes the engine flag *in* and
    the rendered ``SCHEMA_SNAPSHOT`` literal back *out* to ``revision_command``.
    """
    env_ctx = getattr(context, "environment_context", None)
    return getattr(env_ctx, "config", None) if env_ctx is not None else None


def _framework_table_filter(name: str) -> bool:
    """Table-name predicate for the engine baseline: ``True`` to keep a table.

    Adapts ``framework_tables.include_object`` (Alembic's autogenerate exclusion
    hook) to a bare name check so the engine baseline creates exactly the set of
    tables the legacy baseline did — project tables only, framework-owned tables
    excluded (they are created by the framework baseline migration).
    """
    return _include_object(None, name, "table", False, None)


def _drive_snapshot_engine(cfg: Any, script: Any, *, baseline: bool = False) -> bool:
    """Replace the autogenerate ops with the #1431 snapshot-diff engine's ops.

    Returns ``True`` when the engine suppressed an empty directive (caller clears
    it); ``False`` when it replaced the op-trees in place. ``cfg`` is the live
    Alembic ``Config`` (the caller guarantees it is non-None). The engine computes
    the delta from the head migration's embedded ``SCHEMA_SNAPSHOT`` vs the live DSL
    — NOT from a metadata-vs-DB diff — so it emits intentful, additive create/alter
    ops. The current snapshot literal is stashed on
    ``cfg.attributes['dazzle_schema_snapshot']`` so the command can post-write the
    ``SCHEMA_SNAPSHOT = <literal>`` module constant into the generated file.
    """
    from alembic.script import ScriptDirectory

    from dazzle.db.migration_engine import generate_baseline_plan, generate_revision

    if baseline:
        # Fresh-database baseline: diff against an empty prev and exclude
        # framework-owned tables (the framework baseline migration creates those).
        plan = generate_baseline_plan(table_filter=_framework_table_filter)
    else:
        script_dir = ScriptDirectory.from_config(cfg)
        plan = generate_revision(script_dir)

    if plan.is_empty:
        return True  # signal: suppress (caller clears directives)

    # Replace the autogenerate-derived op-trees with the engine's rendered ops.
    script.upgrade_ops = plan.upgrade_ops
    script.downgrade_ops = plan.downgrade_ops

    # Hand the snapshot literal back to the command for post-write injection.
    cfg.attributes["dazzle_schema_snapshot"] = plan.snapshot_literal
    return False


def _process_revision_directives(context: Any, revision: Any, directives: list[Any]) -> None:
    """Post-process autogenerated migration directives.

    The #1431 snapshot-diff engine is the **sole** generator (ADR-0045): it replaces
    the autogenerate op-trees with its own diff-derived ops (DSL-snapshot vs the head
    migration's embedded ``SCHEMA_SNAPSHOT``) and stashes the current snapshot literal
    on ``cfg.attributes`` for the command to post-write. Empty diffs are suppressed.
    ``dazzle db baseline`` sets ``dazzle_baseline=True`` for the fresh-DB case
    (empty prev + framework-table exclusion). The legacy metadata-vs-live-DB
    autogenerate path was removed — for schema the engine can't express, hand-author
    a revision with ``--no-autogenerate``.

    A bare ``alembic`` invocation without the dazzle command wiring has no live
    ``Config`` (``cfg is None``), so the engine can't stash the snapshot literal it
    needs — that case is unsupported and the revision is suppressed with a warning
    directing the operator to ``dazzle db revision``.
    """
    if not directives:
        return

    script = directives[0]
    if script.upgrade_ops is None:
        return

    cfg = _alembic_config(context)
    if cfg is None:
        logger.warning(
            "alembic autogenerate ran without a dazzle Config (bare `alembic` "
            "invocation): the #1431 engine is unavailable here. Use `dazzle db "
            "revision` / `dazzle db migrate` instead — suppressing this revision."
        )
        directives[:] = []
        return

    baseline = bool(cfg.attributes.get("dazzle_baseline", False))
    if _drive_snapshot_engine(cfg, script, baseline=baseline):
        directives[:] = []


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------

# #1188/#1357: exclusion rules live in the importable registry module —
# env.py executes only under the alembic context and cannot be imported by
# tests. See framework_tables.include_object for the full rationale.
from dazzle.http.alembic.framework_tables import include_object as _include_object  # noqa: E402


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without connecting)."""
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=_include_object,
        process_revision_directives=_process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    from sqlalchemy import create_engine

    url = _get_url()
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is required for online migrations.")

    connectable = create_engine(url)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=_include_object,
            process_revision_directives=_process_revision_directives,
        )

        with context.begin_transaction():
            tenant_schema = config.attributes.get("tenant_schema")
            if tenant_schema:
                import re

                # Validate: slug_to_schema_name() guarantees alphanumeric +
                # underscore only, but we enforce it here too so this file is
                # safe regardless of call-site discipline.
                if not re.fullmatch(r"[a-zA-Z0-9_]+", tenant_schema):
                    raise ValueError(
                        f"Invalid tenant_schema {tenant_schema!r}: "
                        "must be alphanumeric and underscores only"
                    )
                # Use the raw DBAPI cursor to SET search_path so that SQLAlchemy's
                # text() pathway is not involved (avoids taint-analysis false positives).
                # The schema name is validated as a safe identifier above.
                dbapi_conn: Any = connection.connection
                cur = dbapi_conn.cursor()
                try:
                    from psycopg import sql as pgsql

                    # SET cannot take a bound parameter; compose the
                    # already-validated identifier safely instead (#1201).
                    stmt = pgsql.SQL("SET search_path TO {}, public").format(
                        pgsql.Identifier(tenant_schema)
                    )
                    cur.execute(stmt)  # nosemgrep
                finally:
                    cur.close()
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
