"""Tenant excision — delete one tenant's entire footprint (RLS Phase E.1, #1338).

Deletes, in ONE transaction on a single (BYPASSRLS) connection: every
tenant-scoped domain row ``WHERE tenant_id = X`` (children-first), the
tenant-root row ``WHERE id = X`` (last), the auth-store ``memberships WHERE
tenant_id = X``, the ``organizations`` row ``WHERE id = X``, and the identities
orphaned by this removal. Atomic: any failure rolls the whole thing back — there
is no half-excised tenant. Run as ``dazzle_bypass`` so the deletes are not
themselves fenced by RLS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from psycopg import sql

from dazzle.core.ir.fk_graph import FKGraph
from dazzle.http.runtime.sa_schema import scoped_entity_names


class ExcisionError(RuntimeError):
    """Excision cannot proceed safely (e.g. an FK cycle in the tenant graph)."""


@dataclass
class ExcisionResult:
    tenant_id: str
    dry_run: bool
    deleted: dict[str, int] = field(default_factory=dict)
    root: str | None = None  # the domain tenant-root entity (None if app has none)


def _tenant_root_name(appspec: Any) -> str | None:
    for e in appspec.domain.entities:
        if getattr(e, "is_tenant_root", False):
            return str(e.name)
        if getattr(getattr(e, "archetype_kind", None), "name", "") == "TENANT":
            return str(e.name)
    return None


def _scalar(row: Any) -> Any:
    """First column of a psycopg row (tuple or dict_row)."""
    if row is None:
        return None
    return next(iter(row.values())) if isinstance(row, dict) else row[0]


def _count(conn: Any, query: Any, params: tuple[Any, ...]) -> int:
    """Run a count query (a str or a psycopg ``Composed``) and return the int."""
    return int(_scalar(conn.execute(query, params).fetchone()) or 0)


def excise_tenant(
    appspec: Any,
    tenant_id: str,
    *,
    conn: Any,
    dry_run: bool = False,
    allow_missing: bool = False,
) -> ExcisionResult:
    """Excise ``tenant_id`` on ``conn`` (must be a BYPASSRLS role for real RLS).

    ``conn`` is a sync psycopg connection that **must not be autocommit** — this
    function owns one explicit transaction and commits on success (or rolls back
    when ``dry_run`` / on error). An autocommit connection would defeat
    all-or-nothing excision and silently turn ``dry_run`` into a destructive run,
    so it is rejected. Returns counts per table (would-delete counts under
    ``dry_run``).

    Unless ``allow_missing`` is set, the ``organizations`` row for ``tenant_id``
    must exist — otherwise the excision is a no-op that would falsely report
    success (a typo'd / already-excised id). ``allow_missing`` is the cleanup
    escape hatch (e.g. finishing a partially-excised tenant).
    """
    if getattr(conn, "autocommit", False):
        raise ExcisionError(
            "excise_tenant requires a non-autocommit connection — it owns one "
            "explicit transaction so a mid-excision failure rolls back atomically"
        )

    if not allow_missing:
        org_exists = _count(conn, "SELECT count(*) FROM organizations WHERE id = %s", (tenant_id,))
        if org_exists == 0:
            raise ExcisionError(
                f"no organization with id {tenant_id!r} — refusing a no-op excision "
                "that would falsely report success (pass allow_missing to override "
                "for partial-cleanup)"
            )

    partition_key = "tenant_id"
    tenancy = getattr(appspec, "tenancy", None)
    isolation = getattr(tenancy, "isolation", None) if tenancy is not None else None
    if isolation is not None:
        partition_key = getattr(isolation, "partition_key", "tenant_id")

    entities = list(appspec.domain.entities)
    scoped = scoped_entity_names(entities, partition_key)
    root = _tenant_root_name(appspec)

    # Topo set = scoped entities + the root (if any, and not itself scoped).
    topo_set = sorted(scoped) + ([root] if root and root not in scoped else [])
    graph = FKGraph.from_entities(entities)
    order: list[str] = []
    if topo_set:
        computed = graph.deletion_order(topo_set)
        if computed is None:
            raise ExcisionError(
                f"cannot excise tenant {tenant_id!r}: the tenant entity graph has a "
                "cycle (self-referential or circular FK) — no safe deletion order"
            )
        order = computed

    result = ExcisionResult(tenant_id=tenant_id, dry_run=dry_run, root=root)
    try:
        # Capture identities in this tenant BEFORE deleting its memberships, so we
        # can reap exactly those orphaned by this excision (not a still-membered
        # identity that also belongs to another tenant).
        rows = conn.execute(
            "SELECT identity_id FROM memberships WHERE tenant_id = %s", (tenant_id,)
        ).fetchall()
        identity_ids = [_scalar_of(r, "identity_id") for r in rows]

        for name in order:
            # Composable SQL: the table + key column are psycopg Identifiers
            # (auto-quoted, injection-safe); tenant_id is always a bound param.
            tbl = sql.Identifier(name)
            col = sql.Identifier("id") if name == root else sql.Identifier("tenant_id")
            if dry_run:
                count_q = sql.SQL("SELECT count(*) FROM {tbl} WHERE {col} = %s").format(
                    tbl=tbl, col=col
                )
                result.deleted[name] = _count(conn, count_q, (tenant_id,))
            else:
                delete_q = sql.SQL("DELETE FROM {tbl} WHERE {col} = %s").format(tbl=tbl, col=col)
                result.deleted[name] = conn.execute(delete_q, (tenant_id,)).rowcount

        # Auth-store cascade: memberships, then orphaned identities, then org.
        if dry_run:
            result.deleted["memberships"] = _count(
                conn, "SELECT count(*) FROM memberships WHERE tenant_id = %s", (tenant_id,)
            )
        else:
            result.deleted["memberships"] = conn.execute(
                "DELETE FROM memberships WHERE tenant_id = %s", (tenant_id,)
            ).rowcount

        reaped = 0
        if identity_ids:
            orphan_rows = conn.execute(
                "SELECT u.id FROM users u WHERE u.id = ANY(%s) "
                "AND NOT EXISTS (SELECT 1 FROM memberships m WHERE m.identity_id = u.id)",
                (identity_ids,),
            ).fetchall()
            orphans = [_scalar_of(r, "id") for r in orphan_rows]
            if orphans and not dry_run:
                # Clear the reaped identities' rows in every auth table that FKs
                # users(id) (sessions/password_reset_tokens/user_preferences have
                # NO ON DELETE CASCADE), or the users delete FK-violates and rolls
                # back the WHOLE excision. These tables are always present
                # (AuthStore._init_db); user_id is keyed by the orphan id set.
                for child in ("sessions", "password_reset_tokens", "user_preferences"):
                    del_child = sql.SQL("DELETE FROM {} WHERE user_id = ANY(%s)").format(
                        sql.Identifier(child)
                    )
                    conn.execute(del_child, (orphans,))
                conn.execute("DELETE FROM users WHERE id = ANY(%s)", (orphans,))
            reaped = len(orphans)
        result.deleted["users"] = reaped

        if dry_run:
            result.deleted["organizations"] = _count(
                conn, "SELECT count(*) FROM organizations WHERE id = %s", (tenant_id,)
            )
        else:
            result.deleted["organizations"] = conn.execute(
                "DELETE FROM organizations WHERE id = %s", (tenant_id,)
            ).rowcount

        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    return result


def _scalar_of(row: Any, key: str) -> Any:
    """Value of *key* from a psycopg row that may be a dict_row or a tuple."""
    return row[key] if isinstance(row, dict) else row[0]
