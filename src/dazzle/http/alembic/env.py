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
from dazzle.http.alembic.directive_scoping import hoist_cyclic_create_fks

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


def _drive_snapshot_engine(context: Any, script: Any) -> bool:
    """Replace the autogenerate ops with the #1431 snapshot-diff engine's ops.

    Returns ``True`` when the engine suppressed an empty directive (caller clears
    it); ``False`` when it replaced the op-trees in place (or when ``cfg is None``
    and the engine could not run — the caller's ``use_engine`` guard makes the
    latter unreachable in practice, since only ``dazzle db revision`` opts in via a
    non-None ``cfg``). The engine (opt-in for ``dazzle db revision``) computes the
    delta from the head migration's embedded ``SCHEMA_SNAPSHOT`` vs the live DSL — NOT
    from the metadata-vs-DB autogenerate diff — so it emits intentful, additive
    create/alter ops and must NOT be additive-scoped (#1427) or re-USING-injected
    (the renderer already injects USING clauses). The current snapshot literal is
    stashed on ``cfg.attributes['dazzle_schema_snapshot']`` so ``revision_command``
    can post-write the ``SCHEMA_SNAPSHOT = <literal>`` module constant into the
    generated file (the chosen embedding seam — see that command's docstring).
    """
    from alembic.script import ScriptDirectory

    from dazzle.db.migration_engine import generate_revision

    cfg = _alembic_config(context)
    if cfg is None:
        # No live Config (e.g. a bare alembic invocation without the
        # environment_context wiring): the engine has nowhere to stash the
        # snapshot literal back to revision_command, so fall through to the
        # legacy autogenerate path rather than crash in ScriptDirectory.from_config.
        return False
    script_dir = ScriptDirectory.from_config(cfg)
    plan = generate_revision(script_dir)

    if plan.is_empty:
        return True  # signal: suppress (caller clears directives)

    # Replace the autogenerate-derived op-trees with the engine's rendered ops.
    script.upgrade_ops = plan.upgrade_ops
    script.downgrade_ops = plan.downgrade_ops

    # Hand the snapshot literal back to revision_command for post-write injection.
    if cfg is not None:
        cfg.attributes["dazzle_schema_snapshot"] = plan.snapshot_literal
    return False


def _process_revision_directives(context: Any, revision: Any, directives: list[Any]) -> None:
    """Post-process autogenerated migration directives.

    Two mutually-exclusive paths, selected by ``cfg.attributes['dazzle_use_engine']``
    (the #1431 snapshot-diff engine is **opt-in**, set explicitly to ``True`` only
    by ``dazzle db revision``; it defaults to the legacy path when the flag is absent):

    * **Engine (opt-in, #1431):** replace the op-trees with the snapshot-diff
      engine's rendered ops and stash the current ``SCHEMA_SNAPSHOT`` literal for
      post-write injection. Suppress when the DSL is unchanged. ONLY ``dazzle db
      revision`` (sans ``--legacy-autogenerate``) sets this — and it is the only
      command that post-writes the ``SCHEMA_SNAPSHOT`` constant the engine needs to
      diff against next time. Routing baseline/migrate/tenant/bare alembic runs
      through the engine would emit ``create_table`` ops with no embedded snapshot,
      breaking the next ``db revision``'s diff (it would re-emit every table).
    * **Legacy autogenerate (default; also ``--legacy-autogenerate``):**
      1. Suppress empty revisions (no-op when DSL hasn't changed).
      2. Scope to additive ops by default (no destructive whole-schema rewrite, #1427).
      (No USING injection — type changes are stripped by step 2; the #1431 engine is
      the canonical path for type-changes-with-USING. See ``_process_legacy_autogenerate``.)
    """
    if not directives:
        return

    script = directives[0]
    if script.upgrade_ops is None:
        return

    cfg = _alembic_config(context)
    # The engine is opt-in: only `dazzle db revision` sets `dazzle_use_engine=True`.
    # A bare alembic run / `db baseline` / `db migrate` / tenant migration leaves
    # the flag absent and gets the legacy autogenerate path (the prior behaviour),
    # because only `db revision` post-writes the SCHEMA_SNAPSHOT the engine needs.
    use_engine = False
    if cfg is not None:
        use_engine = bool(cfg.attributes.get("dazzle_use_engine", False))

    if use_engine:
        if _drive_snapshot_engine(context, script):
            directives[:] = []
        return

    _process_legacy_autogenerate(script, directives)


def _legacy_scope_to_additive(script: Any, directives: list[Any]) -> bool:
    """Apply the #1427 additive-only scoping to a legacy autogenerate directive.

    Returns ``True`` when the caller should stop (the revision became empty after
    scoping and was suppressed). Mutates ``script.upgrade_ops`` / ``downgrade_ops``
    in place. ``DAZZLE_ALEMBIC_ALLOW_DESTRUCTIVE=1`` bypasses scoping (audit-logged).
    """
    if os.environ.get("DAZZLE_ALEMBIC_ALLOW_DESTRUCTIVE") == "1":
        # Affirmative audit line: a reader of CI/migration logs can see WHY this
        # revision contains drop/alter ops (the additive-only default was bypassed).
        logger.warning(
            "DAZZLE_ALEMBIC_ALLOW_DESTRUCTIVE=1: additive-only scoping bypassed — "
            "autogenerate may emit destructive ops in this revision (#1427)."
        )
        return False

    from dazzle.http.alembic.directive_scoping import scope_upgrade_to_additive

    dropped = scope_upgrade_to_additive(script.upgrade_ops)
    if dropped:
        logger.warning(
            "Autogenerate scoped to additive ops (#1427): suppressed %d "
            "destructive op(s) — hand-author these (or set "
            "DAZZLE_ALEMBIC_ALLOW_DESTRUCTIVE=1): %s",
            len(dropped),
            "; ".join(dropped),
        )
    # The diff may have been ENTIRELY destructive — re-check before emitting.
    if script.upgrade_ops.is_empty():
        directives[:] = []
        return True
    # Keep the downgrade the exact inverse of the now-additive upgrade, else it
    # would still carry the reversals of the ops we just stripped.
    script.downgrade_ops = script.upgrade_ops.reverse()
    return False


def _process_legacy_autogenerate(script: Any, directives: list[Any]) -> None:
    """The pre-#1431 metadata-vs-DB autogenerate path (``--legacy-autogenerate``).

    1. Suppress empty revisions (no-op when DSL hasn't changed).
    2. Scope to additive ops by default (no destructive whole-schema rewrite, #1427).

    Note: this path does NOT inject ``postgresql_using`` clauses for type changes.
    The #1427 additive scoping (step 2) strips every ``AlterColumnOp`` *before* any
    USING handling could run, so the old ``_legacy_inject_using_clauses`` only ever
    fired under ``DAZZLE_ALEMBIC_ALLOW_DESTRUCTIVE=1`` — and even then it set
    ``kw["postgresql_using"]``, which Alembic's file renderer silently drops (#1433).
    Removed in v0.83.64: the #1431 engine (``dazzle db revision`` sans
    ``--legacy-autogenerate``) is the canonical path for type changes with a USING
    cast; an operator who bypasses both the engine and the destructive guardrail
    owns their own casts (hand-author the ``USING`` in the generated revision).
    """
    # Suppress empty migrations
    if script.upgrade_ops.is_empty():
        directives[:] = []
        return

    if _legacy_scope_to_additive(script, directives):
        return  # revision became empty after additive scoping — suppressed

    # #1460: Alembic renders use_alter (cyclic / self-referential) FKs inline in
    # create_table, where SQLAlchemy's CreateTable compiler silently omits them
    # (use_alter means "emit via a trailing ALTER") while Alembic emits no such
    # ALTER — so those FKs vanish from a `db baseline` / `db migrate` schema. Hoist
    # them into trailing op.create_foreign_key calls, mirroring create_all.
    hoisted = hoist_cyclic_create_fks(script.upgrade_ops)
    if hoisted:
        logger.info(
            "Hoisted %d cyclic/self-referential FK(s) to post-create ALTER (#1460): %s",
            len(hoisted),
            ", ".join(hoisted),
        )
        # Keep the downgrade the exact inverse (drop these FKs before their tables).
        script.downgrade_ops = script.upgrade_ops.reverse()


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
