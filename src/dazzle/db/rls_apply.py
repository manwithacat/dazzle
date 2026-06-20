"""Apply RLS policy DDL to a live database (RLS tenancy Phase D — production apply).

The single, DB-bound apply path shared by ``dazzle db apply-rls`` and the
``dazzle db upgrade`` hook. It runs the DB-free DDL set from
:func:`dazzle.http.runtime.rls_schema.build_all_rls_ddl` against a connection.

**CRITICAL — owner role.** ``ENABLE``/``FORCE ROW LEVEL SECURITY`` and
``CREATE POLICY`` require table OWNERSHIP. The runtime connects as the non-owner
``dazzle_app`` role (Phase B) and **cannot** run this DDL. So this apply must run
in the deploy/migrate step that connects as the table owner — the ``dazzle db
apply-rls`` command (operator runs it with an owner URL) and the ``dazzle db
upgrade`` flow (the same role that runs the DDL migrations = owner). It must
NEVER run from ``dazzle serve`` boot in production.

The DDL is idempotent (each ``CREATE POLICY`` is preceded by ``DROP POLICY IF
EXISTS``; ``ENABLE``/``FORCE`` are inherently re-run-safe), so re-applying is a
no-op on the policy set. A no-tenancy / non-``shared_schema`` / no-scoped-entity
appspec yields an empty DDL list, so this is a no-op (returns 0) for every such
app — matching the dev ``create_all`` apply gate.
"""

from __future__ import annotations

from typing import Any


async def apply_rls_policies(conn: Any, appspec: Any, entities: list[Any]) -> int:
    """Apply the appspec's RLS policy DDL on ``conn``; return the statement count.

    Builds the DDL via :func:`build_all_rls_ddl` and executes each statement on
    the (psycopg3 async) connection — matching ``dazzle.cli.db._run_with_connection``'s
    async contract, where the callback receives a psycopg3 ``AsyncConnection`` and
    runs ``await conn.execute(<raw SQL string>)``.

    Returns the number of statements executed; ``0`` (no-op) when the DDL list is
    empty (no row-level tenancy, a non-``shared_schema`` isolation mode, or no
    tenant-scoped entity). Idempotent — safe to re-run.

    Args:
        conn: A psycopg3 ``AsyncConnection`` owned/closed by the caller (do NOT
            close it here). Must connect as a role that OWNS the tenant tables.
        appspec: The application IR (``.tenancy``, ``.domain.entities``,
            ``.fk_graph``).
        entities: The converted back-spec entities (``convert_entities(...)``).

    Raises:
        ValueError: A scoped entity carries scope rules but ``appspec.fk_graph``
            is missing (propagated from :func:`build_all_rls_ddl`).
    """
    from dazzle.http.runtime.rls_schema import build_all_rls_ddl

    statements = build_all_rls_ddl(appspec, entities)
    for stmt in statements:
        await conn.execute(stmt)
    return len(statements)
