"""
Tenant isolation for DNR-Back applications.

Provides per-tenant PostgreSQL schemas for multi-tenant deployments.
Each tenant gets an isolated schema within the same database.

Usage:
    manager = TenantDatabaseManager(database_url="postgresql://...")

    # Get database backend for a specific tenant
    tenant_db = manager.get_tenant_manager("tenant-123")

    # Provision a new tenant (creates schema with tables)
    manager.provision_tenant("tenant-456", entities)
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from dazzle_back.runtime.migrations import auto_migrate
from dazzle_back.runtime.pg_backend import PostgresBackend


class TenantDatabaseManager:
    """
    Manages per-tenant PostgreSQL schemas.

    Each tenant gets an isolated schema within the same database.
    Schema naming: tenant_{tenant_id}
    """

    def __init__(
        self,
        database_url: str,
        base_dir: str | None = None,  # Deprecated, ignored
        entities: list[Any] | None = None,
    ):
        """
        Initialize the tenant database manager.

        Args:
            database_url: PostgreSQL connection URL
            base_dir: Deprecated, ignored
            entities: Entity specs for schema creation (optional, can be set later)
        """
        self.database_url = database_url
        self.entities = entities or []
        self._managers: dict[str, PostgresBackend] = {}

    def _get_tenant_schema(self, tenant_id: str) -> str:
        """Get the schema name for a tenant."""
        safe_id = "".join(c for c in tenant_id if c.isalnum() or c in "-_")
        if not safe_id:
            raise ValueError(f"Invalid tenant ID: {tenant_id}")
        return f"tenant_{safe_id}"

    def get_tenant_manager(self, tenant_id: str) -> PostgresBackend:
        """
        Get or create a PostgresBackend for a tenant.

        Args:
            tenant_id: The tenant's unique identifier

        Returns:
            PostgresBackend configured for the tenant's schema
        """
        if tenant_id in self._managers:
            return self._managers[tenant_id]

        schema = self._get_tenant_schema(tenant_id)

        # Create a backend that sets search_path to the tenant schema
        manager = PostgresBackend(self.database_url, search_path=schema)
        self._managers[tenant_id] = manager
        return manager

    def provision_tenant(
        self,
        tenant_id: str,
        entities: list[Any] | None = None,
    ) -> PostgresBackend:
        """
        Provision a new tenant schema.

        Creates the schema and applies schema migrations.

        Args:
            tenant_id: The tenant's unique identifier
            entities: Entity specs for schema creation (uses default if not provided)

        Returns:
            PostgresBackend for the new tenant's schema
        """
        entities = entities or self.entities
        if not entities:
            raise ValueError("No entities provided for schema creation")

        schema = self._get_tenant_schema(tenant_id)

        # Create schema if it doesn't exist
        import psycopg

        with psycopg.connect(self.database_url) as conn:
            conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            conn.commit()

        # Get database manager
        manager = self.get_tenant_manager(tenant_id)

        # Apply migrations
        auto_migrate(manager, entities, record_history=True)

        return manager

    def delete_tenant(self, tenant_id: str) -> bool:
        """
        Delete a tenant's schema and all data.

        Args:
            tenant_id: The tenant's unique identifier

        Returns:
            True if deleted, False if tenant didn't exist
        """
        # Remove from cache
        if tenant_id in self._managers:
            self._managers[tenant_id].close()
            del self._managers[tenant_id]

        schema = self._get_tenant_schema(tenant_id)

        import psycopg

        with psycopg.connect(self.database_url) as conn:
            # Check if schema exists
            row = conn.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                (schema,),
            ).fetchone()

            if row:
                conn.execute(f"DROP SCHEMA {schema} CASCADE")
                conn.commit()
                return True

        return False

    def list_tenants(self) -> list[str]:
        """
        List all provisioned tenants.

        Returns:
            List of tenant IDs
        """
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            rows = conn.execute(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name LIKE 'tenant_%'"
            ).fetchall()

        return [row["schema_name"].removeprefix("tenant_") for row in rows]

    def tenant_exists(self, tenant_id: str) -> bool:
        """
        Check if a tenant schema exists.

        Args:
            tenant_id: The tenant's unique identifier

        Returns:
            True if tenant schema exists
        """
        schema = self._get_tenant_schema(tenant_id)

        import psycopg

        with psycopg.connect(self.database_url) as conn:
            row = conn.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                (schema,),
            ).fetchone()
            return row is not None


# =============================================================================
# Context Variables for Request-scoped Tenant
# =============================================================================


# Current tenant ID (set by middleware)
_current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)


def get_current_tenant_id() -> str | None:
    """Get the current tenant ID from request context."""
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: str | None) -> None:
    """Set the current tenant ID in request context."""
    _current_tenant_id.set(tenant_id)
