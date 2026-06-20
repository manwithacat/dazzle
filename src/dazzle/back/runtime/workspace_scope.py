"""Workspace region scope filter — RBAC row-level enforcement.

Extracted from workspace_rendering.py in #1057 cut 5 (v0.67.104).
Mirrors `route_generator._make_list_handler`'s scope enforcement so
workspace regions cannot bypass row-level scope rules (#574).
"""

from typing import Any

from dazzle.back.runtime.workspace_context import WorkspaceRegionContext


def _apply_workspace_scope_filters(
    ctx: WorkspaceRegionContext,
    auth_context: Any,
    user_id: str | None,
    filters: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, bool]:
    """Apply entity-level scope predicates to workspace region filters.

    Mirrors the scope enforcement in ``route_generator._make_list_handler``
    so that workspace regions cannot bypass row-level scope rules (#574).

    Returns:
        (merged_filters, denied) — *denied* is True when no scope rule
        matched the user's roles (default-deny: caller should return empty).
    """
    cedar_access_spec = ctx.cedar_access_spec
    if not cedar_access_spec or not user_id or not auth_context:
        return filters, False

    scopes = getattr(cedar_access_spec, "scopes", None)
    if not scopes:
        # No scope rules — pass through without row filtering (#607).
        # The permit gate already controls entity-level access.
        return filters, False

    from dazzle.back.runtime.auth.models import effective_roles_of
    from dazzle.back.runtime.route_support import _normalize_role
    from dazzle.back.runtime.scope_filters import _resolve_scope_filters

    # Collect normalized user roles. auth Plan 1b: source from effective_roles
    # (the active membership's roles when present, else legacy user.roles) so
    # membership-scoped sessions match scope rules — the global user.roles is
    # empty under the per-org membership model.
    scope_user_roles: set[str] = {_normalize_role(r) for r in effective_roles_of(auth_context)}

    scope_result = _resolve_scope_filters(
        cedar_access_spec,
        "list",
        scope_user_roles,
        user_id,
        auth_context,
        entity_name=ctx.source,
        fk_graph=ctx.fk_graph,
    )

    if scope_result is None:
        # No scope rule matched — default-deny
        return filters, True

    if scope_result:
        filters = {**(filters or {}), **scope_result}

    return filters, False
