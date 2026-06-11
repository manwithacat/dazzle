"""Audit context + access logging + auth wrapping for generated routes.

Extracted verbatim from ``route_generator.py`` (#1361 slice 3). This is the
audit/access cluster: AccessRuntimeContext construction from an AuthContext
(``_build_access_context``, including the audit-context ContextVar
population), audit field-change diffs (``_compute_field_changes``), the
access-decision audit emitter (``_log_audit_decision``), and the
auth-dependency wrapping family (``_wrap_with_auth`` ->
``_build_cedar_handler`` / ``_build_auth_handler`` /
``_build_noauth_handler``) that eliminates the cedar / auth / noauth
handler triplication.

A leaf module by design: it must not import ``route_generator`` at module
level (``route_generator`` imports these names back at module level so the
``route_generator.X`` patch points and re-exports keep working). The shared
helpers that stay in ``route_generator`` (``_normalize_role``,
``_set_handler_annotations``, ``_extract_result_id`` — each also used by
the handler factories / list path remaining there) are imported lazily
inside function bodies, enumerated per function.

``_scoped_pre_read`` is imported at module level from its real home,
``scope_filters`` — the cedar handler resolves it through *this* module's
namespace, so tests that stub the pre-read patch ``audit_wrap``, not
``route_generator`` (see tests/unit/test_audit_log.py).

Deliberately NOT named ``*_routes.py`` — the runtime-urls api-surface walker
globs that pattern and this module defines no routes.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from dazzle.back.runtime.auth import AuthContext, effective_roles_of
from dazzle.back.runtime.scope_filters import _scoped_pre_read
from dazzle.render.access_messages import _forbidden_detail

if TYPE_CHECKING:
    from dazzle.back.runtime.audit_log import AuditLogger
    from dazzle.back.runtime.service_generator import BaseService
    from dazzle.back.specs.auth import EntityAccessSpec
    from dazzle.core.ir.fk_graph import FKGraph

# Audit `policy_effect` sentinel for a read denied by a `scope:` row filter
# rather than a Cedar permit/forbid policy — distinct from the standard
# `permit`/`forbid` effects so audit consumers can grep scope denials (#1174).
_SCOPE_DENY_EFFECT = "scope"


# =============================================================================
# Access Control Helpers
# =============================================================================


def _build_access_context(
    auth_context: "AuthContext",
    admin_personas: list[str] | None = None,
) -> tuple[Any, Any]:
    """Build (user, AccessRuntimeContext) from an AuthContext.

    Returns (user_or_none, runtime_context) for Cedar policy evaluation.

    `admin_personas` (#957 cycle 4) is the list declared in
    `tenancy: admin_personas:` on the active AppSpec. Cycle 5 will
    thread it from each call site's enclosing scope; for now callers
    that haven't been updated pass None and the bypass simply doesn't
    apply (identical to pre-cycle-4 behaviour).
    """
    # Lazy: _normalize_role stays in route_generator (shared with its list
    # path and the scope_filters / workspace lazy importers); a module-level
    # import here would be circular.
    from dazzle.back.runtime.route_generator import _normalize_role
    from dazzle.core.access import AccessRuntimeContext

    user = auth_context.user if auth_context.is_authenticated else None
    # auth Plan 1b: source roles from the active membership (effective_roles),
    # not the global user.roles. effective_roles returns [] when unauthenticated.
    raw_roles = list(effective_roles_of(auth_context))
    ctx = AccessRuntimeContext(
        user_id=str(user.id) if user else None,
        roles=[_normalize_role(r) for r in raw_roles],
        is_superuser=getattr(user, "is_superuser", False) if user else False,
        tenant_admin_personas=admin_personas,
    )

    # #956 cycle 5 — populate the audit-context ContextVar so the
    # audit emitter (cycle 4) can fill `AuditEntry.by_user_id` for
    # every mutation in this request. asyncio gives each request task
    # its own copy of the contextvar, so no explicit reset is needed
    # — the value is gone when the task ends. Unauthenticated requests
    # leave the contextvar at its default (None), preserving the
    # "system write" semantic.
    if user is not None:
        from dazzle.back.runtime.audit_context import set_current_user_id

        set_current_user_id(str(user.id))

    return user, ctx


def _record_to_dict(result: Any) -> dict[str, Any]:
    """Convert a Pydantic model or dict to a plain dict for Cedar evaluation."""
    if hasattr(result, "model_dump"):
        d: dict[str, Any] = result.model_dump()
        return d
    if isinstance(result, dict):
        return result
    return {}


def _compute_field_changes(before: Any, after: Any) -> str | None:
    """Compute a JSON diff of changed fields between two records.

    Returns a JSON string mapping field names to {"old": ..., "new": ...},
    or None if no fields changed.
    """
    import json

    before_dict = _record_to_dict(before)
    after_dict = _record_to_dict(after)

    changes: dict[str, dict[str, Any]] = {}
    all_keys = set(before_dict.keys()) | set(after_dict.keys())
    for key in sorted(all_keys):
        old_val = before_dict.get(key)
        new_val = after_dict.get(key)
        if old_val != new_val:
            changes[key] = {"old": _json_safe(old_val), "new": _json_safe(new_val)}

    if not changes:
        return None
    return json.dumps(changes)


def _json_safe(val: Any) -> Any:
    """Convert a value to a JSON-serializable form."""
    if val is None or isinstance(val, (str, int, float, bool)):
        return val
    return str(val)


async def _log_audit_decision(
    audit_logger: "AuditLogger",
    request: Any,
    *,
    operation: str,
    entity_name: str,
    entity_id: str | None,
    decision: str,
    matched_policy: str | None,
    policy_effect: str | None,
    user: Any | None,
    evaluation_time_us: int | None = None,
    field_changes: str | None = None,
) -> None:
    """Log an access-control decision to the audit logger."""
    from dazzle.back.runtime.audit_log import create_audit_context_from_request

    audit_ctx = create_audit_context_from_request(request)
    await audit_logger.log_decision(
        operation=operation,
        entity_name=entity_name,
        entity_id=entity_id,
        decision=decision,
        matched_policy=matched_policy or "",
        policy_effect=policy_effect or "",
        user_id=str(user.id) if user else None,
        user_email=getattr(user, "email", None) if user else None,
        # Plan 1b: audit attribution stays user-sourced (the actor's global
        # roles); per-membership audit attribution is Plan 2 (compliance
        # evidence). Authorization decisions above use effective_roles.
        user_roles=list(getattr(user, "roles", [])) if user else None,
        evaluation_time_us=evaluation_time_us,
        field_changes=field_changes,
        **audit_ctx,
    )


# =============================================================================
# Auth wrapper — eliminates cedar / auth / noauth triplication
# =============================================================================


def _wrap_with_auth(
    core_fn: Callable[..., Any],
    *,
    service: "BaseService[Any]",
    cedar_access_spec: "EntityAccessSpec | None",
    auth_dep: Callable[..., Any] | None,
    optional_auth_dep: Callable[..., Any] | None,
    require_auth_by_default: bool,
    operation: str,
    entity_name: str,
    audit_logger: "AuditLogger | None",
    include_field_changes: bool = False,
    needs_pre_read: bool = False,
    # v0.71.19 (#1123): write-op scope enforcement plumbing — see
    # `_build_cedar_handler` for the per-op enforcement logic.
    fk_graph: "FKGraph | None" = None,
    admin_personas: list[str] | None = None,
) -> Callable[..., Any]:
    """Wrap a core handler with cedar / auth / noauth variant selection.

    ``core_fn`` signature must be::

        async def core(id_or_none, request, *, current_user=None, existing=None) -> Any

    For create the first positional arg is *None*; for read/update/delete it
    is the resource UUID.

    ``needs_pre_read`` — if True the wrapper fetches the existing record
    *before* calling ``core_fn`` (required by Cedar update/delete for policy
    evaluation and by auth-mode update/delete for field-change diffs).
    """
    _is_create = operation == "create"

    _use_cedar = cedar_access_spec is not None and optional_auth_dep is not None

    if _use_cedar:
        assert optional_auth_dep is not None  # narrowing for mypy
        assert cedar_access_spec is not None  # narrowing for mypy
        return _build_cedar_handler(
            core_fn,
            service=service,
            cedar_access_spec=cedar_access_spec,
            optional_auth_dep=optional_auth_dep,
            operation=operation,
            entity_name=entity_name,
            audit_logger=audit_logger,
            include_field_changes=include_field_changes,
            needs_pre_read=needs_pre_read,
            is_create=_is_create,
            fk_graph=fk_graph,
            admin_personas=admin_personas,
        )

    if require_auth_by_default and auth_dep:
        return _build_auth_handler(
            core_fn,
            service=service,
            auth_dep=auth_dep,
            operation=operation,
            entity_name=entity_name,
            audit_logger=audit_logger,
            include_field_changes=include_field_changes,
            needs_pre_read=needs_pre_read,
            is_create=_is_create,
        )

    return _build_noauth_handler(core_fn, is_create=_is_create)


def _build_cedar_handler(
    core_fn: Callable[..., Any],
    *,
    service: "BaseService[Any]",
    cedar_access_spec: "EntityAccessSpec",
    optional_auth_dep: Callable[..., Any],
    operation: str,
    entity_name: str,
    audit_logger: "AuditLogger | None",
    include_field_changes: bool,
    needs_pre_read: bool,
    is_create: bool,
    # v0.71.19 (#1123): inputs the scope-filter resolver needs for the
    # UPDATE/DELETE enforcement path. None on legacy/test paths that
    # don't pass them — falls through to the pre-#1123 behaviour.
    fk_graph: "FKGraph | None" = None,
    admin_personas: list[str] | None = None,
) -> Callable[..., Any]:
    """Build a Cedar-policy-checked handler (with or without id param)."""
    # Lazy: these stay in route_generator (shared with its read/custom
    # handler factories and create core); a module-level import here would
    # be circular. Build-time import — the inner closures capture them.
    from dazzle.back.runtime.route_generator import (
        _extract_result_id,
        _set_handler_annotations,
    )
    from dazzle.core.access import AccessOperationKind

    _op_kind = getattr(AccessOperationKind, operation.upper())

    async def _cedar_impl(
        id: UUID | None,
        request: Request,
        auth_context: AuthContext,
    ) -> Any:
        from dazzle.back.runtime.audit_log import measure_evaluation_time
        from dazzle.core.access import AccessDecision
        from dazzle.render.access_evaluator import evaluate_permission

        # Pre-read for operations that need existing record for policy eval.
        # v0.71.19 (#1123): for UPDATE/DELETE, the pre-read now applies the
        # scope predicate via list(filters={"id": id, **scope_result}) when
        # `scope: <op>:` rules exist for the operation. Default-deny
        # (no matching scope rule) returns 404 — same shape as LIST default-
        # deny, prevents row-existence leaks. The unscoped read path is
        # preserved when no scope rules apply to this op (back-compat) or
        # when fk_graph is missing (legacy callers / tests).
        existing = None
        if needs_pre_read and id is not None:
            existing = await _scoped_pre_read(
                service=service,
                operation=operation,
                id=id,
                cedar_access_spec=cedar_access_spec,
                auth_context=auth_context,
                entity_name=entity_name,
                fk_graph=fk_graph,
                admin_personas=admin_personas,
            )
            if existing is None:
                # Scope filter hid the row (or it does not exist). Record the
                # deny in the audit trail — a scope-denied UPDATE/DELETE is an
                # access-control decision and `audit: all` entities must
                # capture it, same as the scope-denied READ path — then 404
                # (row-existence opaque to the caller).
                if audit_logger:
                    _u, _ = _build_access_context(auth_context)
                    await _log_audit_decision(
                        audit_logger,
                        request,
                        operation=operation,
                        entity_name=entity_name,
                        entity_id=str(id),
                        decision="deny",
                        matched_policy=_SCOPE_DENY_EFFECT,
                        policy_effect=_SCOPE_DENY_EFFECT,
                        user=_u,
                    )
                raise HTTPException(status_code=404, detail="Not found")

        user, ctx = _build_access_context(auth_context)
        record_dict = _record_to_dict(existing) if existing is not None else None
        decision: AccessDecision
        decision, eval_us = measure_evaluation_time(
            lambda: evaluate_permission(
                cedar_access_spec, _op_kind, record_dict, ctx, entity_name=entity_name
            )
        )

        # Create logs both allow+deny before checking; update/delete only log deny on denial
        if is_create and audit_logger:
            await _log_audit_decision(
                audit_logger,
                request,
                operation=operation,
                entity_name=entity_name,
                entity_id=None,
                decision="allow" if decision.allowed else "deny",
                matched_policy=decision.matched_policy,
                policy_effect=decision.effect,
                user=user,
                evaluation_time_us=eval_us,
            )

        if not decision.allowed:
            if not is_create and audit_logger:
                await _log_audit_decision(
                    audit_logger,
                    request,
                    operation=operation,
                    entity_name=entity_name,
                    entity_id=str(id) if id is not None else None,
                    decision="deny",
                    matched_policy=decision.matched_policy,
                    policy_effect=decision.effect,
                    user=user,
                    evaluation_time_us=eval_us,
                )
            raise HTTPException(
                status_code=403,
                detail=_forbidden_detail(
                    entity_name=entity_name,
                    operation=operation,
                    cedar_access_spec=cedar_access_spec,
                    current_roles=list(effective_roles_of(auth_context)),  # Plan 1b
                ),
            )

        current_user = str(user.id) if user else None
        _user_email = getattr(user, "email", None) if user else None
        raw_roles = list(effective_roles_of(auth_context))  # auth Plan 1b: membership-first
        _is_su = ctx.is_superuser
        result = await core_fn(
            id,
            request,
            current_user=current_user,
            user_email=_user_email,
            existing=existing,
            user_roles=raw_roles,
            is_superuser=_is_su,
            # The CREATE core handler needs the full auth context to resolve
            # `current_user.<attr>` in `scope: create:` predicates (#1174):
            # the attributes (`org`, `school`, ...) live in
            # `auth_context.preferences`, not on the bare `user` record.
            auth_context=auth_context,
        )

        # Post-operation audit (create already logged above)
        if not is_create:
            _fc = None
            if include_field_changes and existing is not None:
                after = {} if operation == "delete" else result
                _fc = _compute_field_changes(existing, after)
            if audit_logger:
                await _log_audit_decision(
                    audit_logger,
                    request,
                    operation=operation,
                    entity_name=entity_name,
                    entity_id=str(id) if id is not None else _extract_result_id(result),
                    decision="allow",
                    matched_policy=decision.matched_policy,
                    policy_effect=decision.effect,
                    user=user,
                    evaluation_time_us=eval_us,
                    field_changes=_fc,
                )

        return result

    # Build properly-typed FastAPI handlers with correct signatures
    if is_create:

        async def _cedar_create(
            request: Request, auth_context: AuthContext = Depends(optional_auth_dep)
        ) -> Any:
            return await _cedar_impl(None, request, auth_context)

        _set_handler_annotations(_cedar_create, with_auth=True)
        return _cedar_create

    async def _cedar_with_id(
        id: UUID, request: Request, auth_context: AuthContext = Depends(optional_auth_dep)
    ) -> Any:
        return await _cedar_impl(id, request, auth_context)

    _set_handler_annotations(_cedar_with_id, with_id=True, with_auth=True)
    return _cedar_with_id


def _build_auth_handler(
    core_fn: Callable[..., Any],
    *,
    service: "BaseService[Any]",
    auth_dep: Callable[..., Any],
    operation: str,
    entity_name: str,
    audit_logger: "AuditLogger | None",
    include_field_changes: bool,
    needs_pre_read: bool,
    is_create: bool,
) -> Callable[..., Any]:
    """Build an authenticated handler (with or without id param)."""
    # Lazy: shared helpers staying in route_generator — see the matching
    # note in _build_cedar_handler.
    from dazzle.back.runtime.route_generator import (
        _extract_result_id,
        _set_handler_annotations,
    )

    async def _auth_impl(
        id: UUID | None,
        request: Request,
        auth_context: AuthContext,
    ) -> Any:
        user = auth_context.user
        current_user = str(user.id) if user else None

        # Pre-read for field-change diffs
        existing = None
        if needs_pre_read and include_field_changes and audit_logger and id is not None:
            existing = await service.execute(operation="read", id=id)

        raw_roles = list(effective_roles_of(auth_context))  # auth Plan 1b: membership-first
        _is_su = getattr(user, "is_superuser", False) if user else False
        _user_email = getattr(user, "email", None) if user else None
        result = await core_fn(
            id,
            request,
            current_user=current_user,
            user_email=_user_email,
            existing=existing,
            user_roles=raw_roles,
            is_superuser=_is_su,
            # See the CREATE-scope note in the cedar-path call site above —
            # `auth_context` carries the preferences `scope: create:`
            # predicates resolve `current_user.<attr>` against (#1174).
            auth_context=auth_context,
        )

        _fc = None
        if existing is not None:
            after = {} if operation == "delete" else result
            _fc = _compute_field_changes(existing, after)
        if audit_logger:
            await _log_audit_decision(
                audit_logger,
                request,
                operation=operation,
                entity_name=entity_name,
                entity_id=str(id) if id is not None else _extract_result_id(result),
                decision="allow",
                matched_policy="authenticated",
                policy_effect="permit",
                user=user,
                field_changes=_fc,
            )
        return result

    if is_create:

        async def _auth_create(
            request: Request, auth_context: AuthContext = Depends(auth_dep)
        ) -> Any:
            return await _auth_impl(None, request, auth_context)

        _set_handler_annotations(_auth_create, with_auth=True)
        return _auth_create

    async def _auth_with_id(
        id: UUID, request: Request, auth_context: AuthContext = Depends(auth_dep)
    ) -> Any:
        return await _auth_impl(id, request, auth_context)

    _set_handler_annotations(_auth_with_id, with_id=True, with_auth=True)
    return _auth_with_id


def _build_noauth_handler(
    core_fn: Callable[..., Any],
    *,
    is_create: bool,
) -> Callable[..., Any]:
    """Build an unauthenticated handler (with or without id param)."""
    # Lazy: _set_handler_annotations stays in route_generator (shared with
    # its read/custom handler factories); module-level would be circular.
    from dazzle.back.runtime.route_generator import _set_handler_annotations

    if is_create:

        async def _noauth_create(request: Request) -> Any:
            return await core_fn(None, request, current_user=None, existing=None)

        _set_handler_annotations(_noauth_create)
        return _noauth_create

    async def _noauth_with_id(id: UUID, request: Request) -> Any:
        return await core_fn(id, request, current_user=None, existing=None)

    _set_handler_annotations(_noauth_with_id, with_id=True)
    return _noauth_with_id
