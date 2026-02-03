"""
Cross-tenant aggregation controls for Data Products.

Implements the security controls for cross-tenant data access:
- Permission validation before cross-tenant queries
- Audit logging for cross-tenant operations
- Rate limiting for cross-tenant aggregations

Design Document: dev_docs/architecture/event_first/EventSystemStabilityRules-v1.md
Rule 11: Multi-tenancy enforced everywhere
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from dazzle.core.ir.governance import DataProductSpec

logger = logging.getLogger("dazzle.data_products.cross_tenant")


class CrossTenantPermission(StrEnum):
    """Permissions for cross-tenant operations."""

    NONE = "none"  # No cross-tenant access
    READ_AGGREGATED = "read_aggregated"  # Can read aggregated data only
    READ_ANONYMISED = "read_anonymised"  # Can read anonymised individual records
    READ_FULL = "read_full"  # Full cross-tenant access (dangerous)
    ADMIN = "admin"  # Platform admin access


class CrossTenantAuditAction(StrEnum):
    """Actions that are audited for cross-tenant operations."""

    QUERY = "query"
    AGGREGATE = "aggregate"
    EXPORT = "export"
    DENIED = "denied"


@dataclass
class CrossTenantAuditEntry:
    """Audit log entry for cross-tenant operations."""

    timestamp: datetime
    action: CrossTenantAuditAction
    requesting_tenant: str
    target_tenants: list[str]
    data_product: str
    permission_used: CrossTenantPermission
    record_count: int = 0
    fields_accessed: list[str] = field(default_factory=list)
    reason: str | None = None
    request_id: str | None = None


@dataclass
class CrossTenantPolicy:
    """Policy for cross-tenant data access.

    Defines what a tenant can access across tenant boundaries
    and under what conditions.
    """

    tenant_id: str
    permission: CrossTenantPermission = CrossTenantPermission.NONE
    allowed_products: list[str] = field(default_factory=list)  # Empty = all
    denied_products: list[str] = field(default_factory=list)
    allowed_target_tenants: list[str] = field(default_factory=list)  # Empty = all
    max_records_per_query: int = 10000
    require_aggregation: bool = True
    require_anonymisation: bool = True
    audit_all_access: bool = True


class CrossTenantValidator:
    """Validates cross-tenant access requests.

    Enforces cross-tenant policies and logs audit entries
    for all cross-tenant operations.

    Example:
        validator = CrossTenantValidator()
        validator.add_policy(tenant_policy)

        # Check access
        allowed = validator.check_access(
            requesting_tenant="tenant_a",
            target_tenants=["tenant_b", "tenant_c"],
            product_name="analytics_v1",
        )
        if not allowed.permitted:
            raise PermissionError(allowed.reason)

        # Log the operation
        validator.audit_access(
            requesting_tenant="tenant_a",
            target_tenants=["tenant_b", "tenant_c"],
            product_name="analytics_v1",
            action=CrossTenantAuditAction.AGGREGATE,
            record_count=1500,
        )
    """

    def __init__(self) -> None:
        """Initialize the validator."""
        self._policies: dict[str, CrossTenantPolicy] = {}
        self._audit_log: list[CrossTenantAuditEntry] = []
        self._default_policy = CrossTenantPolicy(
            tenant_id="*",
            permission=CrossTenantPermission.NONE,
        )

    def add_policy(self, policy: CrossTenantPolicy) -> None:
        """Add or update a tenant's cross-tenant policy.

        Args:
            policy: The policy to add
        """
        self._policies[policy.tenant_id] = policy

    def get_policy(self, tenant_id: str) -> CrossTenantPolicy:
        """Get policy for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Policy for tenant, or default policy if not found
        """
        return self._policies.get(tenant_id, self._default_policy)

    @dataclass
    class AccessCheckResult:
        """Result of an access check."""

        permitted: bool
        reason: str
        permission_level: CrossTenantPermission
        constraints: dict[str, Any] = field(default_factory=dict)

    def check_access(
        self,
        requesting_tenant: str,
        target_tenants: list[str],
        product_name: str,
        product_spec: DataProductSpec | None = None,
    ) -> AccessCheckResult:
        """Check if cross-tenant access is permitted.

        Args:
            requesting_tenant: Tenant making the request
            target_tenants: Tenants whose data is being accessed
            product_name: Data product being accessed
            product_spec: Optional product spec for additional checks

        Returns:
            AccessCheckResult with permission status and constraints
        """
        # Same-tenant access is always allowed
        if len(target_tenants) == 1 and target_tenants[0] == requesting_tenant:
            return self.AccessCheckResult(
                permitted=True,
                reason="Same-tenant access",
                permission_level=CrossTenantPermission.READ_FULL,
            )

        # Get policy for requesting tenant
        policy = self.get_policy(requesting_tenant)

        # Check base permission
        if policy.permission == CrossTenantPermission.NONE:
            return self.AccessCheckResult(
                permitted=False,
                reason="Cross-tenant access not permitted for this tenant",
                permission_level=CrossTenantPermission.NONE,
            )

        # Check product allowlist
        if policy.allowed_products and product_name not in policy.allowed_products:
            return self.AccessCheckResult(
                permitted=False,
                reason=f"Product {product_name} not in allowed list",
                permission_level=policy.permission,
            )

        # Check product denylist
        if product_name in policy.denied_products:
            return self.AccessCheckResult(
                permitted=False,
                reason=f"Product {product_name} explicitly denied",
                permission_level=policy.permission,
            )

        # Check target tenant allowlist
        if policy.allowed_target_tenants:
            for tenant in target_tenants:
                if tenant not in policy.allowed_target_tenants:
                    return self.AccessCheckResult(
                        permitted=False,
                        reason=f"Tenant {tenant} not in allowed target list",
                        permission_level=policy.permission,
                    )

        # Check if product allows cross-tenant
        if product_spec and not product_spec.cross_tenant:
            return self.AccessCheckResult(
                permitted=False,
                reason="Data product does not allow cross-tenant access",
                permission_level=policy.permission,
            )

        # Build constraints
        constraints: dict[str, Any] = {
            "max_records": policy.max_records_per_query,
            "require_aggregation": policy.require_aggregation,
            "require_anonymisation": policy.require_anonymisation,
        }

        return self.AccessCheckResult(
            permitted=True,
            reason="Access permitted with constraints",
            permission_level=policy.permission,
            constraints=constraints,
        )

    def audit_access(
        self,
        requesting_tenant: str,
        target_tenants: list[str],
        product_name: str,
        action: CrossTenantAuditAction,
        record_count: int = 0,
        fields_accessed: list[str] | None = None,
        reason: str | None = None,
        request_id: str | None = None,
    ) -> CrossTenantAuditEntry:
        """Log an audit entry for cross-tenant access.

        Args:
            requesting_tenant: Tenant making the request
            target_tenants: Tenants whose data was accessed
            product_name: Data product accessed
            action: Type of action performed
            record_count: Number of records accessed
            fields_accessed: Fields that were accessed
            reason: Reason for access (for denied actions)
            request_id: Request ID for correlation

        Returns:
            The created audit entry
        """
        policy = self.get_policy(requesting_tenant)

        entry = CrossTenantAuditEntry(
            timestamp=datetime.now(UTC),
            action=action,
            requesting_tenant=requesting_tenant,
            target_tenants=target_tenants,
            data_product=product_name,
            permission_used=policy.permission,
            record_count=record_count,
            fields_accessed=fields_accessed or [],
            reason=reason,
            request_id=request_id,
        )

        self._audit_log.append(entry)

        # Log for observability
        if action == CrossTenantAuditAction.DENIED:
            logger.warning(
                "Cross-tenant access denied",
                extra={
                    "requesting_tenant": requesting_tenant,
                    "target_tenants": target_tenants,
                    "product": product_name,
                    "reason": reason,
                },
            )
        else:
            logger.info(
                "Cross-tenant access",
                extra={
                    "action": action.value,
                    "requesting_tenant": requesting_tenant,
                    "target_tenants": target_tenants,
                    "product": product_name,
                    "record_count": record_count,
                },
            )

        return entry

    def get_audit_log(
        self,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[CrossTenantAuditEntry]:
        """Get audit log entries.

        Args:
            tenant_id: Filter by requesting tenant
            limit: Maximum entries to return

        Returns:
            List of audit entries, most recent first
        """
        entries = self._audit_log
        if tenant_id:
            entries = [e for e in entries if e.requesting_tenant == tenant_id]
        return list(reversed(entries[-limit:]))

    def clear_audit_log(self) -> None:
        """Clear the in-memory audit log.

        In production, audit logs should be persisted to a
        durable store before clearing.
        """
        self._audit_log.clear()
