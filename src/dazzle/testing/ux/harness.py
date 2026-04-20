"""Postgres test harness for UX verification.

Manages the lifecycle of a test database: create, schema baseline,
fixture seeding, and teardown. Assumes Postgres is already running.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DB_URL = "postgresql://localhost:5432/postgres"


def check_postgres_available(db_url: str = _DEFAULT_DB_URL) -> bool:
    """Check if Postgres is reachable."""
    # Try pg_isready first (fast, no auth needed)
    pg_isready = shutil.which("pg_isready")
    if pg_isready:
        try:
            result = subprocess.run(
                [pg_isready, "-q"],
                timeout=5,
                capture_output=True,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Fallback: try to connect via psycopg
    try:
        import psycopg

        with psycopg.connect(db_url, autocommit=True, connect_timeout=5) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


@dataclass
class PostgresHarness:
    """Manages a test database for UX verification.

    Usage:
        with PostgresHarness(project_name="simple_task") as harness:
            # harness.test_db_url is ready
            # schema applied, fixtures can be seeded
            pass
        # test DB dropped on exit
    """

    project_name: str
    db_url: str = _DEFAULT_DB_URL
    keep_db: bool = False
    test_db_url: str = ""

    def _admin_connection(self) -> Any:
        """Connect to the admin database (usually 'postgres')."""
        import psycopg

        return psycopg.connect(self.db_url, autocommit=True)

    def _test_db_name(self) -> str:
        # Sanitize project name for SQL identifier
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in self.project_name)
        return f"dazzle_ux_test_{safe}"

    def _ddl_drop(self, db_name: str) -> object:
        """Return a safely-composed DROP DATABASE statement."""
        from psycopg import sql as pgsql

        ident = pgsql.Identifier(db_name)
        return pgsql.SQL("DROP DATABASE IF EXISTS {0}").format(ident)

    def _ddl_create(self, db_name: str) -> object:
        """Return a safely-composed CREATE DATABASE statement."""
        from psycopg import sql as pgsql

        ident = pgsql.Identifier(db_name)
        return pgsql.SQL("CREATE DATABASE {0}").format(ident)

    def create_test_db(self) -> str:
        """Create the test database, dropping it first if it exists."""
        db_name = self._test_db_name()
        drop_stmt = self._ddl_drop(db_name)
        create_stmt = self._ddl_create(db_name)
        conn = self._admin_connection()
        try:
            # Terminate existing connections
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (db_name,),
            )
            conn.execute(drop_stmt)
            conn.execute(create_stmt)
        finally:
            conn.close()

        # Build test DB URL by replacing the database name in the admin URL
        # Parse the admin URL and swap the database
        if "/" in self.db_url:
            base = self.db_url.rsplit("/", 1)[0]
            self.test_db_url = f"{base}/{db_name}"
        else:
            self.test_db_url = f"{self.db_url}/{db_name}"

        logger.info("Created test database: %s", db_name)
        return self.test_db_url

    def drop_test_db(self) -> None:
        """Drop the test database."""
        db_name = self._test_db_name()
        drop_stmt = self._ddl_drop(db_name)
        conn = self._admin_connection()
        try:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (db_name,),
            )
            conn.execute(drop_stmt)
        finally:
            conn.close()
        logger.info("Dropped test database: %s", db_name)

    def __enter__(self) -> PostgresHarness:
        self.create_test_db()
        return self

    def __exit__(self, *args: object) -> None:
        if not self.keep_db:
            self.drop_test_db()
