"""Tenant enumeration from an unfenced source (#1778).

Under ``shared_schema`` tenancy every domain table carries the restrictive
``tenant_fence`` with ``FORCE ROW LEVEL SECURITY``, so a session with no
``dazzle.tenant_id`` bound sees *zero* rows of any fenced table — including the
tenant-root entity's table. Enumerating tenants by reading a fenced table
therefore returns an empty list and silently turns a per-tenant loop into a
no-op (the #1778 failure class).

The framework ``organizations`` auth table is the unfenced source: it is
``non_fenced`` in :mod:`dazzle.db.artifact_registry`, and ADR-0037 makes the
root-kind organization's ``id`` equal to the ``dazzle.tenant_id`` the fence
compares against. Every tenant-keyed operation outside a request
(per-tenant data migrations, tenant excision, per-tenant dumps) reads tenant
ids from here and nowhere else.

``conn`` is a sync psycopg connection (tuple or ``dict_row`` rows). Inside an
Alembic revision, pass the raw DBAPI connection of ``op.get_bind()`` — it
shares the migration's transaction.
"""

from __future__ import annotations

from typing import Any

#: The unfenced table tenant ids are read from. Pinned against the artifact
#: registry's RLS posture by ``tests/unit/test_tenant_dml.py``.
TENANT_SOURCE_TABLE = "organizations"

# Literal SQL (no interpolation); the table named must stay TENANT_SOURCE_TABLE.
_TENANT_IDS_SQL = "SELECT id FROM organizations ORDER BY id"
_TENANT_EXISTS_SQL = "SELECT 1 FROM organizations WHERE id = %s"


def first_column(row: Any) -> Any:
    """First column of a psycopg row (tuple or ``dict_row``)."""
    return next(iter(row.values())) if isinstance(row, dict) else row[0]


def iter_tenant_ids(conn: Any) -> list[str]:
    """Every tenant id, in a stable order, read from ``organizations``.

    Never reads a fenced table, so the result does not depend on whether a
    tenant GUC is bound or RLS is enforced for the current role.
    """
    rows = conn.execute(_TENANT_IDS_SQL).fetchall()
    return [str(first_column(r)) for r in rows]


def tenant_exists(conn: Any, tenant_id: str) -> bool:
    """True when ``organizations`` carries a row for ``tenant_id``."""
    return conn.execute(_TENANT_EXISTS_SQL, (tenant_id,)).fetchone() is not None
