"""Access control value types — shared between dazzle.back and dazzle.ui.

These types have NO backend dependencies. They exist in dazzle.core so both
dazzle.back (which implements access evaluation) and dazzle.ui (which consumes
access decisions for UI filtering) can import them without circular deps.

#1096 (parent #1086): the access-rule spec types (AccessConditionSpec,
VisibilityRuleSpec, PermissionRuleSpec, ScopeRuleSpec, EntityAccessSpec,
and the four supporting StrEnums) moved here from back.specs.auth so the
access evaluator can eventually live in a neutral location too (#1094).
"""

from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dazzle.core import ir


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


# =============================================================================
# Access rule spec types (moved from back.specs.auth in #1096)
# =============================================================================


class AccessComparisonKind(StrEnum):
    """Comparison operators for access rule conditions."""

    EQUALS = "="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="
    IN = "in"
    NOT_IN = "not in"
    IS = "is"
    IS_NOT = "is not"


class AccessLogicalKind(StrEnum):
    """Logical operators for combining access conditions."""

    AND = "and"
    OR = "or"


class AccessAuthContext(StrEnum):
    """Authentication context for access rules."""

    ANONYMOUS = "anonymous"
    AUTHENTICATED = "authenticated"


class AccessPolicyEffect(StrEnum):
    """Policy effect for Cedar-style access rules."""

    PERMIT = "permit"
    FORBID = "forbid"


class AccessConditionSpec(BaseModel):
    """Access condition specification.

    Represents a node in the expression tree for access conditions.
    Can be:
    - comparison: field op value (e.g., owner_id = current_user)
    - role_check: role(role_name) (e.g., role(admin))
    - logical: left op right (combining conditions with AND/OR)

    Examples:
        - owner_id = current_user
        - role(admin)
        - owner_id = current_user or role(admin)
        - owner.team_id = current_team and status = active
    """

    kind: Literal["comparison", "role_check", "logical", "grant_check", "via_check"] = Field(
        description="Condition type"
    )
    # For comparison: field, operator, value
    field: str | None = Field(
        default=None,
        description="Field path for comparison (supports dotted paths like owner.team_id)",
    )
    comparison_op: AccessComparisonKind | None = Field(
        default=None, description="Comparison operator"
    )
    value: str | int | float | bool | None = Field(
        default=None, description="Comparison value (literal or special like 'current_user')"
    )
    value_list: list[str | int | float | bool] | None = Field(
        default=None, description="List of values for IN/NOT IN operators"
    )
    # For role_check: role name
    role_name: str | None = Field(default=None, description="Role name for role() check")
    # For grant_check: has_grant(relation, scope_field)
    grant_relation: str | None = Field(
        default=None, description="Grant relation name for has_grant() check"
    )
    grant_scope_field: str | None = Field(
        default=None, description="Scope field for has_grant() check"
    )
    # For via_check: subquery through junction table (#530)
    via_junction_entity: str | None = Field(
        default=None, description="Junction entity name (e.g., 'AgentAssignment')"
    )
    via_bindings: list[dict[str, str]] | None = Field(
        default=None, description="List of binding dicts with junction_field, target, operator"
    )
    # For logical: left, operator, right
    logical_op: AccessLogicalKind | None = Field(
        default=None, description="Logical operator (AND/OR)"
    )
    logical_left: "AccessConditionSpec | None" = Field(
        default=None, description="Left operand for logical"
    )
    logical_right: "AccessConditionSpec | None" = Field(
        default=None, description="Right operand for logical"
    )

    model_config = ConfigDict(frozen=True)


class VisibilityRuleSpec(BaseModel):
    """Visibility rule for entity read access.

    Defines when users can see/read entities.

    Examples:
        - Anonymous users can see if is_public = true
        - Authenticated users can see if owner_id = current_user
    """

    context: AccessAuthContext = Field(description="Auth context (anonymous/authenticated)")
    condition: AccessConditionSpec = Field(description="Condition for visibility")

    model_config = ConfigDict(frozen=True)


class PermissionRuleSpec(BaseModel):
    """Permission rule for entity access control (Cedar-style).

    Defines when users can perform operations on entities.
    Supports permit/forbid semantics for Cedar-style policy evaluation.

    Examples:
        - Only owner can update: owner_id = current_user
        - Only admin can delete: role(admin)
        - Interns cannot delete: effect=FORBID, role(intern)
    """

    operation: AccessOperationKind = Field(description="Operation type")
    require_auth: bool = Field(default=True, description="Require authentication")
    condition: AccessConditionSpec | None = Field(
        default=None,
        description="Condition for permission (None = always allowed if authenticated)",
    )
    effect: AccessPolicyEffect = Field(
        default=AccessPolicyEffect.PERMIT,
        description="Cedar-style effect (permit/forbid)",
    )
    personas: list[str] = Field(
        default_factory=list,
        description="Persona scope (empty = any authenticated user)",
    )

    model_config = ConfigDict(frozen=True)


class ScopeRuleSpec(BaseModel):
    """Row-filtering scope rule — converted from IR ScopeRule.

    Defines which records a role can see after passing the permit gate.
    condition=None means 'all' (no filter). personas=["*"] means all
    authorized roles.

    The ``predicate`` field carries the compiled :class:`ScopePredicate` tree
    from the linker (typed as ``Any`` to avoid circular imports).  When present,
    the runtime uses :func:`compile_predicate` to produce SQL directly, bypassing
    the legacy condition-tree-to-filter-dict pipeline.
    """

    operation: AccessOperationKind = Field(description="Operation type")
    condition: AccessConditionSpec | None = Field(
        default=None,
        description="Row-filter condition (None means 'all records')",
    )
    personas: list[str] = Field(
        default_factory=list,
        description="Persona scope (['*'] means all authorized roles)",
    )
    predicate: Any = Field(
        default=None,
        description="Compiled ScopePredicate tree (set by linker, used at runtime for SQL generation)",
    )

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


class EntityAccessSpec(BaseModel):
    """Entity-level access control specification.

    Combines visibility rules (read access), permission rules (write access),
    and scope rules (row-level filtering after permit gate).
    """

    visibility: list[VisibilityRuleSpec] = Field(
        default_factory=list, description="Visibility rules (read access)"
    )
    permissions: list[PermissionRuleSpec] = Field(
        default_factory=list, description="Permission rules (create/update/delete access)"
    )
    scopes: list[ScopeRuleSpec] = Field(
        default_factory=list, description="Row-filtering scope rules (post-permit gate)"
    )

    model_config = ConfigDict(frozen=True)


# Rebuild model for recursive AccessConditionSpec self-reference
AccessConditionSpec.model_rebuild()


# =============================================================================
# Workspace persona resolution (single source of truth)
# =============================================================================


def workspace_allowed_personas(
    workspace: ir.WorkspaceSpec,
    personas: list[ir.PersonaSpec],
) -> list[str] | None:
    """Return the set of persona IDs allowed to access a workspace.

    This is the **single source of truth** for "who can see this workspace".
    Both the server-side access enforcement (``_workspace_handler``) and the
    sidebar nav generator (``template_compiler``) must call this function so
    they agree on what each persona sees. Before this helper existed
    (manwithacat/dazzle#775), the two paths had diverging rules and the sidebar would
    show workspace links for personas that the enforcement path would 403 on
    — a pattern observed in 4 example apps across cycles 199, 201, 216, 217
    of the autonomous ``/ux-cycle`` loop.

    It lives in :mod:`dazzle.core.access` (relocated from
    ``dazzle.ui.converters.workspace_converter`` in #1324 FR-6 follow-up) so
    that core consumers — notably :func:`dazzle.core.validator.validate_nav_curation`
    — can call it without core depending on the ui layer. The
    ``workspace_converter`` module re-exports it for existing ui/testing callers.

    Resolution order:

    1. **Explicit `access.allow_personas`** — if the DSL declares
       ``access: persona(admin, agent)`` with a non-empty ``allow_personas``
       list, exactly those personas are allowed. Returns the list verbatim.
    2. **Explicit `access.deny_personas`** — if the DSL declares a non-empty
       deny list (and no allow list), all personas except the denied ones
       are allowed. Returns the inverted set.
    3. **Implicit `persona.default_workspace`** — if no explicit access
       declaration exists on the workspace, personas are filtered by their
       ``default_workspace`` attribute: only personas whose
       ``default_workspace`` equals this workspace's name are allowed.
    4. **Fallback: all personas** — if the workspace has no explicit access
       AND no persona claims it as their default, return ``None`` meaning
       "visible to every authenticated user". This preserves backward
       compatibility with workspaces that predate ``default_workspace``.

    A return value of ``None`` means **no filter** (visible to everyone
    authenticated). A return value of an empty list means **no one** — which
    is a legitimate configuration but almost always a DSL bug; callers
    should probably log a warning. A non-empty list means **only these
    personas**.

    Args:
        workspace: The workspace IR node.
        personas: The list of all persona specs from the AppSpec. Used only
            for resolution steps 2 and 3 (deny-list inversion and
            default_workspace inference).

    Returns:
        A list of persona IDs, or ``None`` for the "no filter" case.
    """
    ws_access = getattr(workspace, "access", None)
    if ws_access is not None:
        allow = list(getattr(ws_access, "allow_personas", None) or [])
        deny = list(getattr(ws_access, "deny_personas", None) or [])
        if allow:
            return allow
        if deny:
            return [p.id for p in personas if p.id not in deny]
    # No explicit access declaration — infer from persona default_workspace
    claimants = [p.id for p in personas if p.default_workspace == workspace.name]
    if claimants:
        return claimants
    # Truly open workspace (backward compat for pre-default_workspace apps)
    return None
