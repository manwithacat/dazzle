"""
GraphQL Context for multi-tenant support.

The context is attached to every GraphQL request and provides:
- Tenant isolation
- User identity
- Role-based access control
- Request metadata
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from starlette.requests import Request


@dataclass(frozen=True)
class GraphQLContext:
    """
    GraphQL request context for multi-tenant applications.

    Every resolver receives this context and should use it for:
    - Tenant scoping (all queries filtered by tenant_id)
    - User authorization (check roles before actions)
    - Audit logging (request_id for tracing)

    Attributes:
        tenant_id: Current tenant identifier (from auth token)
        user_id: Current user identifier (from auth token)
        roles: List of user roles for authorization
        request_id: Unique request identifier for tracing
        ip_address: Client IP address (optional)
        session: Additional session data (optional)
        is_authenticated: Whether the user is authenticated
        is_anonymous: Whether this is an anonymous request

    Example:
        async def resolve_tasks(self, info: Info) -> list[Task]:
            ctx = info.context
            # Always scope by tenant
            return await task_service.list_tasks(
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
            )
    """

    tenant_id: str | None = None
    user_id: str | None = None
    roles: tuple[str, ...] = field(default_factory=tuple)
    request_id: str | None = None
    ip_address: str | None = None
    session: dict[str, Any] = field(default_factory=dict)

    @property
    def is_authenticated(self) -> bool:
        """Check if the user is authenticated."""
        return self.user_id is not None

    @property
    def is_anonymous(self) -> bool:
        """Check if this is an anonymous request."""
        return self.user_id is None

    def has_role(self, role: str) -> bool:
        """Check if the user has a specific role."""
        return role in self.roles

    def has_any_role(self, *roles: str) -> bool:
        """Check if the user has any of the specified roles."""
        return any(role in self.roles for role in roles)

    def has_all_roles(self, *roles: str) -> bool:
        """Check if the user has all of the specified roles."""
        return all(role in self.roles for role in roles)

    def require_authenticated(self) -> None:
        """Raise if user is not authenticated."""
        if not self.is_authenticated:
            raise PermissionError("Authentication required")

    def require_role(self, role: str) -> None:
        """Raise if user doesn't have the specified role."""
        self.require_authenticated()
        if not self.has_role(role):
            raise PermissionError(f"Role '{role}' required")

    def require_tenant(self) -> str:
        """Get tenant_id or raise if not set."""
        if not self.tenant_id:
            raise PermissionError("Tenant context required")
        return self.tenant_id


def create_context_from_request(request: Request) -> GraphQLContext:
    """
    Create GraphQL context from an HTTP request.

    Extracts tenant, user, and role information from:
    1. Request state (set by auth middleware)
    2. Headers (X-Tenant-ID, X-Request-ID)
    3. Client information

    Args:
        request: Starlette/FastAPI request object

    Returns:
        GraphQLContext populated from request
    """
    import uuid

    # Try to get auth context from request state (set by AuthMiddleware)
    auth_context = getattr(request.state, "auth_context", None)

    tenant_id = None
    user_id = None
    roles: tuple[str, ...] = ()
    session: dict[str, Any] = {}

    if auth_context:
        # AuthContext from DNR auth middleware
        tenant_id = getattr(auth_context, "tenant_id", None)
        user_id = getattr(auth_context, "user_id", None)
        roles_list = getattr(auth_context, "roles", [])
        roles = tuple(roles_list) if roles_list else ()
        session = getattr(auth_context, "session", {}) or {}

    # Allow tenant override from header (for testing/admin)
    header_tenant = request.headers.get("X-Tenant-ID")
    if header_tenant and not tenant_id:
        tenant_id = header_tenant

    # Get or generate request ID
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    # Get client IP
    ip_address = request.client.host if request.client else None

    return GraphQLContext(
        tenant_id=tenant_id,
        user_id=user_id,
        roles=roles,
        request_id=request_id,
        ip_address=ip_address,
        session=session,
    )


def create_anonymous_context(
    request_id: str | None = None,
    tenant_id: str | None = None,
) -> GraphQLContext:
    """
    Create an anonymous context for unauthenticated requests.

    Useful for:
    - Public queries
    - Health checks
    - Schema introspection

    Args:
        request_id: Optional request ID for tracing
        tenant_id: Optional tenant ID for multi-tenant public data

    Returns:
        Anonymous GraphQLContext
    """
    import uuid

    return GraphQLContext(
        tenant_id=tenant_id,
        user_id=None,
        roles=(),
        request_id=request_id or str(uuid.uuid4()),
        ip_address=None,
        session={},
    )


def create_system_context(
    tenant_id: str | None = None,
    request_id: str | None = None,
) -> GraphQLContext:
    """
    Create a system context for internal operations.

    System context has elevated privileges for:
    - Background jobs
    - Migrations
    - Admin operations

    Args:
        tenant_id: Optional tenant scope
        request_id: Optional request ID for tracing

    Returns:
        System GraphQLContext with admin role
    """
    import uuid

    return GraphQLContext(
        tenant_id=tenant_id,
        user_id="system",
        roles=("system", "admin"),
        request_id=request_id or str(uuid.uuid4()),
        ip_address=None,
        session={"is_system": True},
    )
