"""Tenant-bound DML inside an Alembic revision + the upgrade RLS tripwire (#1778).

Under ``shared_schema`` tenancy every fenced table has ``FORCE ROW LEVEL
SECURITY`` and a restrictive ``tenant_fence`` keyed on the ``dazzle.tenant_id``
GUC. A migration session binds no tenant, so for any non-superuser,
non-``BYPASSRLS`` role an unbound ``SELECT`` / ``UPDATE`` / ``INSERT … SELECT``
on a fenced table matches **zero rows without an error** — a hand-authored
backfill at the ``# === DATA MIGRATION ===`` seam silently does nothing once
RLS has been applied (it works on a fresh replay, where RLS is applied after
the upgrade). DDL is not fenced.

Two pieces close that:

* :func:`arm_rls_tripwire` — ``env.py`` calls it at the start of the upgrade
  transaction when ``dazzle db upgrade`` sets :data:`RLS_TRIPWIRE_ATTR`. It
  issues ``SET LOCAL row_security = off``: not a bypass (any role may set it),
  but a tripwire — a statement RLS would filter now raises
  ``query would be affected by row-level security policy`` instead of matching
  nothing. Superuser / ``BYPASSRLS`` roles are never filtered, so they are
  unaffected either way.
* :func:`for_each_tenant` — the supported way to run seam DML on fenced tables:
  binds each tenant in turn (ids from the unfenced ``organizations`` table via
  :func:`dazzle.db.tenant_ids.iter_tenant_ids`), runs the statement, and
  returns per-tenant row counts. It switches ``row_security`` back on locally
  for its own duration, because the tripwire also errors on a *bound* statement
  that RLS filters.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from alembic import op

from dazzle.db.tenant_ids import iter_tenant_ids
from dazzle.http.runtime.rls_schema import TENANT_GUC

logger = logging.getLogger(__name__)

#: ``Config.attributes`` key ``dazzle db upgrade`` sets to arm the tripwire.
RLS_TRIPWIRE_ATTR = "dazzle_rls_tripwire"

# set_config takes bind parameters (SET / SET LOCAL cannot — #1201), so the GUC
# name and value are both parameters here; nothing is interpolated.
_SET_CONFIG_LOCAL = "SELECT set_config(%s, %s, true)"  # nosemgrep
_READ_ROW_SECURITY = "SELECT current_setting('row_security')"


def arm_rls_tripwire(dbapi_conn: Any) -> None:
    """Issue ``SET LOCAL row_security = off`` on *dbapi_conn* (raw psycopg).

    Transaction-scoped: discarded on the upgrade transaction's commit or
    rollback. No parameter is involved, so the parameterised-``SET`` gate does
    not apply.
    """
    cur = dbapi_conn.cursor()
    try:
        cur.execute("SET LOCAL row_security = off")
    finally:
        cur.close()


def _set_local(bind: Any, name: str, value: str) -> None:
    bind.exec_driver_sql(_SET_CONFIG_LOCAL, (name, value))


def for_each_tenant(sql: str, *, params: Mapping[str, Any] | None = None) -> dict[str, int]:
    """Run *sql* once per tenant with ``dazzle.tenant_id`` bound; return row counts.

    Call from inside a revision's ``upgrade()``::

        from dazzle.http.alembic.tenant_dml import for_each_tenant

        for_each_tenant(
            'INSERT INTO "Taxpayer" (tenant_id, id, contact) '
            'SELECT c.tenant_id, gen_random_uuid(), c.id FROM "Contact" c '
            'WHERE NOT EXISTS (SELECT 1 FROM "Taxpayer" t WHERE t.contact = c.id)'
        )

    *sql* is executed through SQLAlchemy ``text()`` (``:name`` placeholders, the
    same as ``op.execute``); *params* binds them. Tenant ids come from the
    unfenced ``organizations`` table — never from a fenced one. ``row_security``
    is switched on for the loop (so it works under the upgrade tripwire) and
    restored afterwards; the tenant GUC is reset to ``''`` (fail-closed). A run
    where every tenant reports 0 rows is logged as a warning — on a populated
    database that usually means the statement's predicate is wrong.

    Returns ``{tenant_id: rowcount}``.
    """
    bind = op.get_bind()
    prior_row_security = str(bind.exec_driver_sql(_READ_ROW_SECURITY).scalar())
    _set_local(bind, "row_security", "on")
    stmt = sa.text(sql)
    bound = dict(params or {})
    counts: dict[str, int] = {}
    try:
        tenant_ids = iter_tenant_ids(bind.connection.dbapi_connection)
        for tenant_id in tenant_ids:
            _set_local(bind, TENANT_GUC, tenant_id)
            counts[tenant_id] = int(bind.execute(stmt, bound).rowcount or 0)
    except BaseException:
        # The transaction is usually aborted here, so restoring may itself fail;
        # the rollback discards these LOCAL settings anyway. Never mask the cause.
        try:
            _restore(bind, prior_row_security)
        except Exception:
            logger.debug("for_each_tenant: restore after failure skipped", exc_info=True)
        raise
    _restore(bind, prior_row_security)

    if not any(counts.values()):
        logger.warning(
            "for_each_tenant affected 0 rows across %d tenant(s)%s — check the "
            "statement's predicate if this database holds data (#1778).",
            len(counts),
            "" if counts else " (organizations is empty)",
        )
    else:
        logger.info("for_each_tenant row counts: %s", counts)
    return counts


def _restore(bind: Any, prior_row_security: str) -> None:
    _set_local(bind, TENANT_GUC, "")
    _set_local(bind, "row_security", prior_row_security)
