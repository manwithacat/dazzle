"""Access control value types — shared between dazzle_back and dazzle_ui.

These types have NO backend dependencies. They exist in dazzle.core so both
dazzle_back (which implements access evaluation) and dazzle_ui (which consumes
access decisions for UI filtering) can import them without circular deps.
"""

from enum import StrEnum
from typing import Any
from uuid import UUID


class AccessOperationKind(StrEnum):
    """Access operation types."""

    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"


class AccessDecision:
    """
    Result of an access evaluation.

    Couples the allow/deny decision with the reason, enabling audit logging.
    """

    __slots__ = ("allowed", "matched_policy", "effect")

    def __init__(
        self,
        allowed: bool,
        matched_policy: str = "",
        effect: str = "",
    ):
        self.allowed = allowed
        self.matched_policy = matched_policy
        self.effect = effect

    def __bool__(self) -> bool:
        return self.allowed

    def __repr__(self) -> str:
        return f"AccessDecision(allowed={self.allowed}, policy={self.matched_policy!r})"


class AccessRuntimeContext:
    """
    Runtime context for access rule evaluation.

    Provides user identity, roles, and entity resolution for relationship traversal.
    """

    def __init__(
        self,
        user_id: str | UUID | None = None,
        roles: list[str] | None = None,
        is_superuser: bool = False,
        entity_resolver: Any = None,
        tenant_admin_personas: list[str] | None = None,
    ):
        """
        Initialize access context.

        Args:
            user_id: Current user's ID
            roles: List of user's roles
            is_superuser: Whether user is a superuser (bypasses all checks)
            entity_resolver: Callable to resolve related entities by (entity_name, id)
            tenant_admin_personas: Personas declared in `tenancy: admin_personas:`
                that bypass the tenant-scope filter when matched against the
                user's roles (#957 cycle 4). Empty default → identical to
                pre-cycle-4 behaviour.
        """
        self.user_id = str(user_id) if user_id else None
        self.roles = set(roles or [])
        self.is_superuser = is_superuser
        self.entity_resolver = entity_resolver
        # Stored as a frozenset for fast intersection with `roles`.
        self.tenant_admin_personas: frozenset[str] = frozenset(tenant_admin_personas or [])

    @property
    def is_authenticated(self) -> bool:
        """Check if user is authenticated."""
        return self.user_id is not None

    @property
    def bypasses_tenant_filter(self) -> bool:
        """True if this context should skip the tenant_id row filter.

        #957 cycle 4 — admin personas declared via `tenancy:
        admin_personas:` short-circuit cross-tenant scope predicates so
        support / super_admin users can read any tenant's records.
        Superusers also bypass for parity with `has_role`. Cycle 5 will
        use this in scope-predicate evaluation.
        """
        if self.is_superuser:
            return True
        return not self.tenant_admin_personas.isdisjoint(self.roles)

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return role in self.roles or self.is_superuser
