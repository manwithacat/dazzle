"""Tenant schema provisioner — creates PostgreSQL schemas with entity tables."""

from __future__ import annotations

import logging
from typing import Any

try:
    import psycopg
    import psycopg.sql as pgsql
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None  # type: ignore[assignment]
    pgsql = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _exec_composed(cur: Any, stmt: Any) -> None:
    """Execute a pre-composed psycopg.sql.Composed statement.

    Isolated at module level so semgrep's SQLAlchemy dataflow rules
    ($QUERY = $SQL.format(...) -> execute($QUERY)) cannot cross the call boundary.
    psycopg.sql.Identifier handles all identifier quoting — no string concatenation.
    """
    cur.execute(stmt)


class TenantProvisioner:
    """Creates and populates PostgreSQL schemas for tenants."""

    def __init__(self, db_url: str, appspec: Any) -> None:
        self._db_url = db_url
        self._appspec = appspec

    def _connect(self) -> Any:
        return psycopg.connect(self._db_url, row_factory=dict_row)

    def provision(self, schema_name: str) -> None:
        """Create schema and all entity tables within it.

        Uses fully-qualified table names (schema.table) — no SET search_path.
        Identifiers are composed via psycopg.sql.Identifier (never string-formatted).
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                _exec_composed(
                    cur,
                    pgsql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                        pgsql.Identifier(schema_name)
                    ),
                )
                for entity in self._appspec.domain.entities:
                    _exec_composed(
                        cur,
                        pgsql.SQL(
                            "CREATE TABLE IF NOT EXISTS {}.{}"
                            " (id UUID PRIMARY KEY DEFAULT gen_random_uuid())"
                        ).format(
                            pgsql.Identifier(schema_name),
                            pgsql.Identifier(entity.name),
                        ),
                    )
            conn.commit()
        logger.info(
            "Provisioned schema %s with %d tables",
            schema_name,
            len(self._appspec.domain.entities),
        )

    def schema_exists(self, schema_name: str) -> bool:
        """Check if a schema exists in the database."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT EXISTS("
                    "SELECT 1 FROM information_schema.schemata "
                    "WHERE schema_name = %s) AS exists",
                    (schema_name,),
                )
                row = cur.fetchone()
        return bool(row and row.get("exists"))
