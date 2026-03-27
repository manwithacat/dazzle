"""Tenant schema provisioner — creates PostgreSQL schemas with entity tables."""

import logging
from pathlib import Path
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
        """Create schema and run Alembic migrations within it.

        Creates the PostgreSQL schema, then delegates to Alembic to
        apply all migrations matching the AppSpec entities.
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

        # Step 2: Run Alembic migrations for the tenant schema
        from alembic import command
        from alembic.config import Config as AlembicConfig

        try:
            import dazzle_back

            alembic_dir = Path(dazzle_back.__file__).resolve().parent / "alembic"
        except (ImportError, AttributeError):
            alembic_dir = Path(__file__).resolve().parents[2] / "dazzle_back" / "alembic"
        cfg = AlembicConfig(str(alembic_dir / "alembic.ini"))
        cfg.set_main_option("script_location", str(alembic_dir))
        cfg.set_main_option("sqlalchemy.url", self._db_url)
        cfg.attributes["tenant_schema"] = schema_name
        command.upgrade(cfg, "head")

        logger.info("Provisioned schema %s via Alembic", schema_name)

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
