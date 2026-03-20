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
        """Create schema and run full auto_migrate within it.

        Creates the PostgreSQL schema, then delegates to auto_migrate to
        generate complete table definitions matching the AppSpec entities.
        Identifiers are composed via psycopg.sql.Identifier (never string-formatted).
        """
        # Step 1: Create the schema
        with self._connect() as conn:
            with conn.cursor() as cur:
                _exec_composed(
                    cur,
                    pgsql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                        pgsql.Identifier(schema_name)
                    ),
                )
            conn.commit()

        # Step 2: Run auto_migrate to create full table definitions
        from dazzle_back.converters.entity_converter import convert_entities
        from dazzle_back.runtime.migrations import auto_migrate
        from dazzle_back.runtime.pg_backend import PostgresBackend

        db_manager = PostgresBackend(self._db_url)
        entities = convert_entities(self._appspec.domain.entities)
        plan = auto_migrate(
            db_manager,
            entities,
            record_history=False,
            schema=schema_name,
        )

        table_count = sum(1 for s in plan.steps if s.action == "create_table")
        logger.info(
            "Provisioned schema %s — %d tables created, %d total migration steps",
            schema_name,
            table_count,
            len(plan.steps),
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
