"""
Tenant isolation for DNR-Back applications.

Provides per-tenant SQLite databases for development environments.
In production, this would typically be tenant-per-schema in PostgreSQL.

Usage:
    manager = TenantDatabaseManager(base_dir=".dazzle/tenants")

    # Get database manager for a specific tenant
    tenant_db = manager.get_tenant_manager("tenant-123")

    # Provision a new tenant (creates database with schema)
    manager.provision_tenant("tenant-456", entities)
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from dazzle_dnr_back.runtime.migrations import auto_migrate
from dazzle_dnr_back.runtime.repository import DatabaseManager


class TenantDatabaseManager:
    """
    Manages per-tenant SQLite databases.

    For development environments, provides separate SQLite files per tenant,
    simulating the tenant-per-schema model used in production PostgreSQL.

    Directory structure:
        .dazzle/tenants/
            {tenant_id}/
                data.db
    """

    def __init__(
        self,
        base_dir: str | Path = ".dazzle/tenants",
        entities: list[Any] | None = None,
    ):
        """
        Initialize the tenant database manager.

        Args:
            base_dir: Base directory for tenant databases
            entities: Entity specs for schema creation (optional, can be set later)
        """
        self.base_dir = Path(base_dir)
        self.entities = entities or []
        self._managers: dict[str, DatabaseManager] = {}

        # Ensure base directory exists
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_tenant_path(self, tenant_id: str) -> Path:
        """Get the database path for a tenant."""
        # Sanitize tenant ID to prevent path traversal
        safe_id = "".join(c for c in tenant_id if c.isalnum() or c in "-_")
        if not safe_id:
            raise ValueError(f"Invalid tenant ID: {tenant_id}")
        return self.base_dir / safe_id / "data.db"

    def get_tenant_manager(self, tenant_id: str) -> DatabaseManager:
        """
        Get or create a DatabaseManager for a tenant.

        Args:
            tenant_id: The tenant's unique identifier

        Returns:
            DatabaseManager for the tenant's database
        """
        if tenant_id in self._managers:
            return self._managers[tenant_id]

        db_path = self._get_tenant_path(tenant_id)
        manager = DatabaseManager(db_path)
        self._managers[tenant_id] = manager
        return manager

    def provision_tenant(
        self,
        tenant_id: str,
        entities: list[Any] | None = None,
    ) -> DatabaseManager:
        """
        Provision a new tenant database.

        Creates the database directory and applies schema migrations.

        Args:
            tenant_id: The tenant's unique identifier
            entities: Entity specs for schema creation (uses default if not provided)

        Returns:
            DatabaseManager for the new tenant's database
        """
        entities = entities or self.entities
        if not entities:
            raise ValueError("No entities provided for schema creation")

        # Create tenant directory
        db_path = self._get_tenant_path(tenant_id)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Get database manager
        manager = self.get_tenant_manager(tenant_id)

        # Apply migrations
        auto_migrate(manager, entities, record_history=True)

        return manager

    def delete_tenant(self, tenant_id: str) -> bool:
        """
        Delete a tenant's database.

        Args:
            tenant_id: The tenant's unique identifier

        Returns:
            True if deleted, False if tenant didn't exist
        """
        # Remove from cache
        if tenant_id in self._managers:
            del self._managers[tenant_id]

        # Delete directory
        db_path = self._get_tenant_path(tenant_id)
        tenant_dir = db_path.parent

        if tenant_dir.exists():
            shutil.rmtree(tenant_dir)
            return True

        return False

    def list_tenants(self) -> list[str]:
        """
        List all provisioned tenants.

        Returns:
            List of tenant IDs
        """
        tenants = []
        if self.base_dir.exists():
            for path in self.base_dir.iterdir():
                if path.is_dir() and (path / "data.db").exists():
                    tenants.append(path.name)
        return tenants

    def tenant_exists(self, tenant_id: str) -> bool:
        """
        Check if a tenant database exists.

        Args:
            tenant_id: The tenant's unique identifier

        Returns:
            True if tenant database exists
        """
        db_path = self._get_tenant_path(tenant_id)
        return db_path.exists()


# =============================================================================
# Context Variables for Request-scoped Tenant
# =============================================================================


try:
    from contextvars import ContextVar

    # Current tenant ID (set by middleware)
    _current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)

    def get_current_tenant_id() -> str | None:
        """Get the current tenant ID from request context."""
        return _current_tenant_id.get()

    def set_current_tenant_id(tenant_id: str | None) -> None:
        """Set the current tenant ID in request context."""
        _current_tenant_id.set(tenant_id)

except ImportError:
    # Fallback for older Python
    _current_tenant_id_value: str | None = None

    def get_current_tenant_id() -> str | None:
        """Get the current tenant ID."""
        global _current_tenant_id_value
        return _current_tenant_id_value

    def set_current_tenant_id(tenant_id: str | None) -> None:
        """Set the current tenant ID."""
        global _current_tenant_id_value
        _current_tenant_id_value = tenant_id
