"""Apply and verify the DSL's ``search:`` columns on a live database (#1850).

A ``search:`` block becomes a generated ``search_vector`` tsvector column plus a GIN
index (:mod:`dazzle.http.runtime.search_schema`). The expression comes from the DSL,
so it is not in the framework Alembic chain; a development boot applies it after
``create_all`` and production — which runs no boot-time DDL — gets it from
``dazzle db upgrade`` (a post-migration step, like RLS) or ``dazzle db apply-search``.

One planner (:func:`~dazzle.http.runtime.search_schema.plan_search_ddl`) serves the
apply, the development boot and ``dazzle db verify``'s drift report: a missing column
is added, a column whose expression no longer matches the ``search:`` field list is
dropped and re-added with its index, a missing index is created, and a generated
column on an entity whose ``search:`` block was removed is dropped. A database that
already matches gets no DDL.

Run as a role that owns the entity tables (the role that runs the migrations).
"""

from __future__ import annotations

from typing import Any

from dazzle.http.runtime.search_schema import (
    LIVE_INDEXES_SQL,
    LIVE_SEARCH_COLUMNS_SQL,
    LIVE_TABLES_SQL,
    build_search_columns,
    live_search_state,
    plan_search_ddl,
)

from .connection import fetchall


async def plan_search_columns(conn: Any, appspec: Any, entities: list[Any]) -> list[Any]:
    """Return the :class:`SearchAction` list that reconciles *conn* with the appspec."""
    desired = build_search_columns(entities, list(getattr(appspec, "searches", []) or []))
    columns, indexes, tables = live_search_state(
        await fetchall(conn, LIVE_SEARCH_COLUMNS_SQL),
        await fetchall(conn, LIVE_INDEXES_SQL),
        await fetchall(conn, LIVE_TABLES_SQL),
    )
    return plan_search_ddl(
        desired,
        live_columns=columns,
        live_indexes=indexes,
        live_tables=tables,
        entity_tables=[e.name for e in entities],
    )


async def apply_search_columns(conn: Any, appspec: Any, entities: list[Any]) -> list[Any]:
    """Reconcile the search columns in one transaction; return the actions applied.

    ``table_missing`` actions carry no DDL and are returned for reporting only.
    """
    actions = await plan_search_columns(conn, appspec, entities)
    statements = [stmt for action in actions for stmt in action.statements]
    if statements:
        async with conn.transaction():
            for stmt in statements:
                await conn.execute(stmt)
    return actions


async def detect_search_drift(conn: Any, appspec: Any, entities: list[Any]) -> list[dict[str, Any]]:
    """``dazzle db verify``: every table whose search column differs from the DSL."""
    return [
        {"entity": a.table, "action": a.action, "detail": a.detail}
        for a in await plan_search_columns(conn, appspec, entities)
    ]
