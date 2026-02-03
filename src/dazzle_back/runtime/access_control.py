"""
Access control and row-level security for DNR Backend.

Provides owner-based and tenant-based access control for entities.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# =============================================================================
# Access Context
# =============================================================================


class AccessContext(BaseModel):
    """
    Context for access control decisions.

    Contains the current user, tenant, and roles for making access decisions.
    """

    user_id: UUID | None = None
    tenant_id: UUID | None = None
    roles: list[str] = Field(default_factory=list)
    is_superuser: bool = False

    @property
    def is_authenticated(self) -> bool:
        """Check if user is authenticated."""
        return self.user_id is not None

    @property
    def is_tenant_scoped(self) -> bool:
        """Check if context has tenant scope."""
        return self.tenant_id is not None

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return role in self.roles or self.is_superuser


# =============================================================================
# Access Operations
# =============================================================================


class AccessOperation(StrEnum):
    """CRUD operations for access control."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"


# =============================================================================
# Access Rules
# =============================================================================


class AccessRule(BaseModel):
    """
    A single access rule for an entity operation.

    Rules can be:
    - "public": Anyone can access
    - "authenticated": Any logged-in user
    - "owner": Only the record owner
    - "role:admin": Users with specific role
    - "tenant": Same tenant only
    """

    operation: AccessOperation
    rule: str  # "public", "authenticated", "owner", "role:X", "tenant"
    owner_field: str | None = None  # Field that stores owner ID
    tenant_field: str | None = None  # Field that stores tenant ID

    def evaluate(
        self,
        context: AccessContext,
        record: dict[str, Any] | None = None,
    ) -> bool:
        """
        Evaluate if access is allowed.

        Args:
            context: Access context with user/tenant info
            record: Record being accessed (for owner/tenant checks)

        Returns:
            True if access is allowed
        """
        # Superusers bypass all checks
        if context.is_superuser:
            return True

        # Parse rule
        if self.rule == "public":
            return True

        if self.rule == "authenticated":
            return context.is_authenticated

        if self.rule == "owner":
            if not context.is_authenticated:
                return False
            if record is None:
                # For create operations, allow if authenticated
                return self.operation == AccessOperation.CREATE
            if self.owner_field is None:
                return False
            owner_id = record.get(self.owner_field)
            if owner_id is None:
                return False
            # Handle both UUID and string comparison
            return str(owner_id) == str(context.user_id)

        if self.rule == "tenant":
            if not context.is_tenant_scoped:
                return False
            if record is None:
                return True  # For create, will set tenant_id
            if self.tenant_field is None:
                return False
            tenant_id = record.get(self.tenant_field)
            if tenant_id is None:
                return False
            return str(tenant_id) == str(context.tenant_id)

        if self.rule.startswith("role:"):
            role = self.rule[5:]  # Remove "role:" prefix
            return context.has_role(role)

        # Unknown rule, deny by default
        return False


# =============================================================================
# Access Policy
# =============================================================================


class AccessPolicy(BaseModel):
    """
    Access policy for an entity.

    Defines rules for each CRUD operation.
    """

    entity_name: str
    owner_field: str | None = None
    tenant_field: str | None = None
    rules: dict[AccessOperation, AccessRule] = Field(default_factory=dict)

    @classmethod
    def create_public(cls, entity_name: str) -> AccessPolicy:
        """Create a policy that allows public access to all operations."""
        policy = cls(entity_name=entity_name)
        for op in AccessOperation:
            policy.rules[op] = AccessRule(operation=op, rule="public")
        return policy

    @classmethod
    def create_authenticated(cls, entity_name: str) -> AccessPolicy:
        """Create a policy that requires authentication for all operations."""
        policy = cls(entity_name=entity_name)
        for op in AccessOperation:
            policy.rules[op] = AccessRule(operation=op, rule="authenticated")
        return policy

    @classmethod
    def create_owner_based(
        cls,
        entity_name: str,
        owner_field: str = "owner_id",
    ) -> AccessPolicy:
        """
        Create a policy where users can only access their own records.

        - create: authenticated (owner set automatically)
        - read: owner only
        - update: owner only
        - delete: owner only
        - list: owner only (filtered)
        """
        policy = cls(entity_name=entity_name, owner_field=owner_field)

        # Create: any authenticated user
        policy.rules[AccessOperation.CREATE] = AccessRule(
            operation=AccessOperation.CREATE,
            rule="authenticated",
        )

        # Read/Update/Delete: owner only
        for op in [AccessOperation.READ, AccessOperation.UPDATE, AccessOperation.DELETE]:
            policy.rules[op] = AccessRule(
                operation=op,
                rule="owner",
                owner_field=owner_field,
            )

        # List: owner filter applied
        policy.rules[AccessOperation.LIST] = AccessRule(
            operation=AccessOperation.LIST,
            rule="owner",
            owner_field=owner_field,
        )

        return policy

    @classmethod
    def create_tenant_based(
        cls,
        entity_name: str,
        tenant_field: str = "tenant_id",
    ) -> AccessPolicy:
        """
        Create a policy where all operations are scoped to tenant.

        - All operations require tenant context
        - Records filtered by tenant_id
        """
        policy = cls(entity_name=entity_name, tenant_field=tenant_field)

        for op in AccessOperation:
            policy.rules[op] = AccessRule(
                operation=op,
                rule="tenant",
                tenant_field=tenant_field,
            )

        return policy

    def can_access(
        self,
        operation: AccessOperation,
        context: AccessContext,
        record: dict[str, Any] | None = None,
    ) -> bool:
        """
        Check if access is allowed for an operation.

        Args:
            operation: The operation being performed
            context: Access context with user/tenant info
            record: Record being accessed (optional)

        Returns:
            True if access is allowed
        """
        rule = self.rules.get(operation)

        if rule is None:
            # No rule defined, deny by default
            return False

        return rule.evaluate(context, record)

    def get_list_filters(self, context: AccessContext) -> dict[str, Any]:
        """
        Get filters to apply when listing records.

        Returns filters based on the LIST rule (owner/tenant).

        Args:
            context: Access context

        Returns:
            Dictionary of filters to apply
        """
        filters: dict[str, Any] = {}
        rule = self.rules.get(AccessOperation.LIST)

        if rule is None:
            return filters

        if rule.rule == "owner" and self.owner_field and context.user_id:
            filters[self.owner_field] = context.user_id

        if rule.rule == "tenant" and self.tenant_field and context.tenant_id:
            filters[self.tenant_field] = context.tenant_id

        return filters


# =============================================================================
# Policy Registry
# =============================================================================


class PolicyRegistry:
    """
    Registry of access policies for entities.

    Stores and retrieves policies by entity name.
    """

    def __init__(self):
        self._policies: dict[str, AccessPolicy] = {}
        self._default_policy: AccessPolicy | None = None

    def register(self, policy: AccessPolicy) -> None:
        """Register a policy for an entity."""
        self._policies[policy.entity_name] = policy

    def get(self, entity_name: str) -> AccessPolicy | None:
        """Get policy for an entity."""
        return self._policies.get(entity_name, self._default_policy)

    def set_default(self, policy: AccessPolicy) -> None:
        """Set the default policy for entities without explicit policy."""
        self._default_policy = policy

    def has_policy(self, entity_name: str) -> bool:
        """Check if entity has a registered policy."""
        return entity_name in self._policies


# =============================================================================
# Access Enforcement
# =============================================================================


class AccessDenied(Exception):
    """Raised when access is denied."""

    def __init__(
        self,
        operation: AccessOperation,
        entity: str,
        reason: str = "Access denied",
    ):
        self.operation = operation
        self.entity = entity
        self.reason = reason
        super().__init__(f"{operation.value} on {entity}: {reason}")


class AccessEnforcer:
    """
    Enforces access policies on repository operations.

    Wraps repository methods to check access before allowing operations.
    """

    def __init__(
        self,
        policy: AccessPolicy,
        get_context: Callable[[], AccessContext],
    ):
        """
        Initialize the enforcer.

        Args:
            policy: Access policy to enforce
            get_context: Callable that returns current access context
        """
        self.policy = policy
        self.get_context = get_context

    def check_create(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Check create access and inject owner/tenant IDs.

        Args:
            data: Record data to create

        Returns:
            Data with owner/tenant IDs injected

        Raises:
            AccessDenied: If access is denied
        """
        context = self.get_context()

        if not self.policy.can_access(AccessOperation.CREATE, context):
            raise AccessDenied(
                AccessOperation.CREATE,
                self.policy.entity_name,
                "Not authorized to create",
            )

        # Inject owner_id if policy uses owner-based access
        if self.policy.owner_field and context.user_id:
            data = {**data, self.policy.owner_field: context.user_id}

        # Inject tenant_id if policy uses tenant-based access
        if self.policy.tenant_field and context.tenant_id:
            data = {**data, self.policy.tenant_field: context.tenant_id}

        return data

    def check_read(self, record: dict[str, Any] | None) -> None:
        """
        Check read access for a record.

        Args:
            record: Record being read

        Raises:
            AccessDenied: If access is denied
        """
        if record is None:
            return  # Not found is handled separately

        context = self.get_context()

        if not self.policy.can_access(AccessOperation.READ, context, record):
            raise AccessDenied(
                AccessOperation.READ,
                self.policy.entity_name,
                "Not authorized to read this record",
            )

    def check_update(self, record: dict[str, Any]) -> None:
        """
        Check update access for a record.

        Args:
            record: Record being updated

        Raises:
            AccessDenied: If access is denied
        """
        context = self.get_context()

        if not self.policy.can_access(AccessOperation.UPDATE, context, record):
            raise AccessDenied(
                AccessOperation.UPDATE,
                self.policy.entity_name,
                "Not authorized to update this record",
            )

    def check_delete(self, record: dict[str, Any]) -> None:
        """
        Check delete access for a record.

        Args:
            record: Record being deleted

        Raises:
            AccessDenied: If access is denied
        """
        context = self.get_context()

        if not self.policy.can_access(AccessOperation.DELETE, context, record):
            raise AccessDenied(
                AccessOperation.DELETE,
                self.policy.entity_name,
                "Not authorized to delete this record",
            )

    def get_list_filters(self) -> dict[str, Any]:
        """
        Get filters to apply when listing records.

        Returns:
            Dictionary of filters based on access policy
        """
        context = self.get_context()
        return self.policy.get_list_filters(context)


# =============================================================================
# Entity Policy Detection
# =============================================================================


def detect_owner_field(fields: list[dict[str, Any]]) -> str | None:
    """
    Detect owner field from entity fields.

    Looks for fields named owner_id, owner, user_id, created_by, etc.

    Args:
        fields: List of field definitions

    Returns:
        Owner field name or None
    """
    owner_field_names = {
        "owner_id",
        "owner",
        "user_id",
        "created_by",
        "author_id",
        "author",
    }

    for field in fields:
        name = field.get("name", "").lower()
        if name in owner_field_names:
            return field.get("name")

        # Check if it's a ref to User entity
        field_type = field.get("type", {})
        if field_type.get("kind") == "ref":
            ref_entity = field_type.get("ref_entity", "").lower()
            if ref_entity in ("user", "users", "account"):
                return field.get("name")

    return None


def detect_tenant_field(fields: list[dict[str, Any]]) -> str | None:
    """
    Detect tenant field from entity fields.

    Looks for fields named tenant_id, tenant, organization_id, etc.

    Args:
        fields: List of field definitions

    Returns:
        Tenant field name or None
    """
    tenant_field_names = {
        "tenant_id",
        "tenant",
        "organization_id",
        "org_id",
        "company_id",
        "workspace_id",
    }

    for field in fields:
        name = field.get("name", "").lower()
        if name in tenant_field_names:
            return field.get("name")

    return None


def create_policy_from_entity(
    entity_name: str,
    fields: list[dict[str, Any]],
    default_mode: str = "public",
) -> AccessPolicy:
    """
    Create an access policy based on entity field analysis.

    Args:
        entity_name: Name of the entity
        fields: List of field definitions
        default_mode: Default access mode ("public", "authenticated", "owner")

    Returns:
        Access policy for the entity
    """
    owner_field = detect_owner_field(fields)
    tenant_field = detect_tenant_field(fields)

    # If entity has owner field, use owner-based policy
    if owner_field:
        return AccessPolicy.create_owner_based(entity_name, owner_field)

    # If entity has tenant field, use tenant-based policy
    if tenant_field:
        return AccessPolicy.create_tenant_based(entity_name, tenant_field)

    # Fall back to default mode
    if default_mode == "authenticated":
        return AccessPolicy.create_authenticated(entity_name)

    return AccessPolicy.create_public(entity_name)
