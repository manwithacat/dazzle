"""Public policy-gate API for route overrides + arbitrary project code (#1126).

Closes the remaining write-op authorisation gap: the framework's
generated CRUD routes evaluate ``permit:`` + ``scope:`` rules since
v0.71.19/v0.71.22, but ``# dazzle:route-override`` handlers and any
other arbitrary project code had no public path back into the same
machinery. Projects re-encoded the policy by hand, drifting from the
DSL's declaration. ISO 27001 A.9.4.1 / SOC 2 CC6.1 audits prefer
"policy declared, framework enforced" over "policy declared, project
hand-checked" — this module is the bridge.

Two surfaces:

- :class:`PolicyRegistry` — attached to ``app.state.policy_registry``
  at app boot. Maps DSL entity name → :class:`EntityPolicyInfo` which
  bundles the access spec, FK graph, admin-personas list, and service
  for that entity. Built once; same data the framework's own CRUD
  routes consume.

- :func:`check_entity_op` — public callable. Project code does::

      from dazzle.http.runtime.policy import check_entity_op

      async def handler(request, pupil_user_id):
          row = await check_entity_op(
              request, "StudentProfile", "update", row_id=pupil_user_id,
          )
          # Authorised by construction. Get on with the side-effects.
          ...

  Same primitive that the declarative ``# dazzle:implements`` annotation
  uses to wrap override handlers — the imperative form sees through the
  same lens.

Behaviour for each op:

- ``list`` / ``read`` / ``update`` / ``delete``: fetch the row at
  ``row_id``. If absent OR the user's ``scope: <op>:`` rule rejects it,
  raises ``HTTPException(404)`` — matches the LIST handler's default-
  deny shape and prevents row-existence leaks via IDOR. If permit
  rejects, raises ``HTTPException(403)``.
- ``create``: evaluates the permit gate against the role, then walks
  the ``scope: create:`` predicate against the post-default payload
  via the v1 walker from ``scope_create_eval``. ``HTTPException(403)``
  with ``error: scope_create_denied`` detail on rejection. Returns
  ``None`` (no row to return).

When the DSL declares no ``scope:`` rule for the entity-op pair: the
permit gate runs as normal; the scope gate is a no-op. Apps with
intentionally-unscoped entities continue to work; the framework
doesn't synthesise a deny.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, Request

if TYPE_CHECKING:
    from dazzle.core.ir.fk_graph import FKGraph
    from dazzle.http.runtime.service_generator import BaseService
    from dazzle.http.specs.auth import EntityAccessSpec

logger = logging.getLogger(__name__)


# =============================================================================
# Registry — built at app boot in `server.py`
# =============================================================================


@dataclass
class EntityPolicyInfo:
    """The data the framework's own CRUD handlers consume, exposed as
    a public bundle so override handlers can reach the same primitives."""

    entity_name: str
    cedar_access_spec: EntityAccessSpec | None
    fk_graph: FKGraph | None
    admin_personas: list[str] = field(default_factory=list)
    service: BaseService[Any] | None = None


@dataclass
class PolicyRegistry:
    """Per-app registry of entity policy bundles.

    Built once at app boot from the same inputs `RouteGenerator`
    consumes. Attached to ``app.state.policy_registry`` so any code
    path (route overrides, custom routers, MCP handlers) can reach
    the framework's permit + scope machinery without re-wiring it.
    """

    entities: dict[str, EntityPolicyInfo] = field(default_factory=dict)

    def get(self, entity_name: str) -> EntityPolicyInfo | None:
        return self.entities.get(entity_name)


# =============================================================================
# Public `check_entity_op` — the imperative API surfaced to overrides
# =============================================================================


async def check_entity_op(
    request: Request,
    entity_name: str,
    op: str,
    *,
    row_id: Any | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    """Run permit + scope evaluation as the framework would for a CRUD route.

    Args:
        request: the incoming FastAPI Request. The registry +
            authenticated user are read off ``request.app.state`` /
            ``request.state.auth_context`` (set by the auth middleware
            upstream).
        entity_name: DSL entity name (e.g. ``"StudentProfile"``).
        op: one of ``"list"``, ``"read"``, ``"create"``, ``"update"``,
            ``"delete"``.
        row_id: target row's primary key for read/update/delete. Required
            for those ops; ignored for ``create`` and ``list``.
        payload: for ``create``, the insert payload (required) — the row as
            it will land in DB (post-defaulting, post-``current_user``
            injection). For ``update``, the changed-fields payload (optional);
            when provided it triggers the same ``scope: update:`` DESTINATION
            re-validation the framework route runs (#1312) — the row's
            would-be-final state must satisfy the update scope rule, so an
            update can't move a row INTO a foreign scope. Ignored for
            list/read/delete.

    Returns:
        The fetched row dict (for read/update/delete), or ``None``
        (for create/list). The fetched row lets the caller skip an
        extra round-trip when they were going to read it anyway.

    Raises:
        HTTPException(403): permit rule denies the (role, op) pair.
            For create, also raised when the scope predicate fails.
        HTTPException(404): row at ``row_id`` doesn't exist, OR exists
            but the user's scope rule rejects it. Default-deny shape;
            mirrors LIST handler semantics.
    """
    op = op.lower()
    if op not in {"list", "read", "create", "update", "delete"}:
        raise ValueError(f"check_entity_op: unknown op {op!r}")

    registry = getattr(getattr(request, "app", None), "state", None)
    registry = getattr(registry, "policy_registry", None) if registry is not None else None
    if registry is None:
        # Defensive: if the app didn't wire a policy registry, fail
        # closed rather than silently bypassing the check. Most likely
        # cause is a test fixture that constructed a bare FastAPI app
        # without going through `app_factory.create_app`.
        raise RuntimeError(
            "check_entity_op called but no policy_registry on app.state — "
            "this is a framework wiring bug; apps built via "
            "`dazzle.http.runtime.app_factory.create_app` have one "
            "automatically. See #1126."
        )

    # Auth check first — override use case assumes auth has run upstream.
    # Even unprotected entities require an authenticated caller; we don't
    # want to silently let anonymous traffic through just because the
    # entity has no permit/scope rules.
    auth_ctx = getattr(getattr(request, "state", None), "auth_context", None)
    user = getattr(auth_ctx, "user", None) if auth_ctx is not None else None
    if user is None or not getattr(auth_ctx, "is_authenticated", False):
        raise HTTPException(status_code=401, detail="authentication required")

    user_id = str(user.id) if getattr(user, "id", None) is not None else None
    if user_id is None:
        raise HTTPException(status_code=401, detail="authentication required")
    # auth Plan 1b: the permit/scope gates read the active membership's roles
    # (effective_roles), falling back to global user roles only when no
    # membership is active (1a transition).
    from dazzle.http.runtime.auth.models import effective_roles_of

    user_roles_raw = effective_roles_of(auth_ctx)

    info = registry.get(entity_name)
    if info is None or info.cedar_access_spec is None:
        # No access spec for this entity — treat as unprotected (matches
        # the framework's behaviour when an entity has no `permit:` rules
        # at all). Log at INFO so adopters can grep for unexpected
        # permissive paths.
        logger.info(
            "policy.check_entity_op:unprotected entity=%s op=%s user=%s (no access spec)",
            entity_name,
            op,
            user_id,
        )
        return None

    # ── PERMIT GATE ─────────────────────────────────────────────────
    if not _permit_passes(info.cedar_access_spec, op, user_roles_raw, user_id):
        logger.info(
            "policy.check_entity_op:permit-denied entity=%s op=%s user=%s",
            entity_name,
            op,
            user_id,
        )
        raise HTTPException(status_code=403, detail="permit denied")

    # ── SCOPE GATE ──────────────────────────────────────────────────
    if op == "create":
        if payload is None:
            raise ValueError("check_entity_op: payload required for op=create")
        _check_scope_create(
            access_spec=info.cedar_access_spec,
            payload=payload,
            entity_name=entity_name,
            user_id=user_id,
            user_roles=user_roles_raw,
            request=request,
            service=getattr(info, "service", None),
            fk_graph=getattr(info, "fk_graph", None),
        )
        return None

    if op == "list":
        # The LIST handler folds scope into the SQL filter at query
        # time. There's no single row to check here; if the override
        # is rolling its own list query, it's responsible for applying
        # the filter — `dazzle.http.runtime.route_generator._resolve_scope_filters`
        # is the public-ish hook for that. Permit-only gate suffices.
        return None

    if row_id is None:
        raise ValueError(f"check_entity_op: row_id required for op={op!r}")
    if info.service is None:
        raise RuntimeError(
            f"check_entity_op: no service registered for entity {entity_name!r} — "
            "framework wiring bug"
        )

    # For read/update/delete: scoped pre-read. Same shape as the
    # cedar handler in route_generator. `auth_ctx` is narrowed to
    # non-None by the early-return on `user is None` above; cast for
    # the type-checker.
    from typing import cast

    from dazzle.http.runtime.auth.models import AuthContext
    from dazzle.http.runtime.scope_filters import _scoped_pre_read

    existing = await _scoped_pre_read(
        service=info.service,
        operation=op,
        id=row_id,
        cedar_access_spec=info.cedar_access_spec,
        auth_context=cast(AuthContext, auth_ctx),
        entity_name=entity_name,
        fk_graph=info.fk_graph,
        admin_personas=info.admin_personas,
    )
    if existing is None:
        # Row doesn't exist OR user's scope rule rejects it. 404 either
        # way — IDOR-protection.
        logger.info(
            "policy.check_entity_op:scope-denied entity=%s op=%s row_id=%s user=%s",
            entity_name,
            op,
            row_id,
            user_id,
        )
        # Detail string MUST match the destination-guard 404 below
        # (`_enforce_update_scope` → `_deny_update_destination` → "Not found")
        # so a scope denial is byte-indistinguishable from a missing row in
        # this path too (IDOR-avoidance, #1312).
        raise HTTPException(status_code=404, detail="Not found")

    # #1312 (ADR-0028): for an update with a payload, re-validate the
    # DESTINATION — the source pre-read above only checked the existing row.
    # Same enforcement the framework UPDATE route runs; 404 on denial.
    if op == "update" and payload is not None:
        from dazzle.http.runtime.scope_filters import _enforce_update_scope

        _enforce_update_scope(
            cedar_access_spec=info.cedar_access_spec,
            existing=existing,
            new_values=payload,
            user_id=user_id,
            user_roles=user_roles_raw,
            entity_name=entity_name,
            auth_context=auth_ctx,
            service=info.service,
            fk_graph=info.fk_graph,
        )
    return existing


# =============================================================================
# Internal helpers
# =============================================================================


def _permit_passes(
    access_spec: EntityAccessSpec,
    op: str,
    user_roles_raw: list[str],
    user_id: str,
) -> bool:
    """Evaluate the permit gate for (role, op) — no record dict needed
    because v0.71.19+ permit rules are role-only (ADR-0010).

    `user_id` threads through so AccessRuntimeContext.is_authenticated
    reports True. `PermissionRule.require_auth` defaults to True and
    `evaluate_permission` short-circuits to DENY on unauth — passing
    an empty user_id would silently fail every check."""
    from dazzle.core.access import AccessOperationKind, AccessRuntimeContext
    from dazzle.render.access_evaluator import evaluate_permission

    op_kind = getattr(AccessOperationKind, op.upper(), None)
    if op_kind is None:
        return False

    normalised_roles = [_normalize_role(r) for r in user_roles_raw]
    ctx = AccessRuntimeContext(
        roles=normalised_roles,
        user_id=user_id,
        is_superuser=False,
    )
    decision = evaluate_permission(access_spec, op_kind, None, ctx, entity_name="")
    return bool(getattr(decision, "allowed", False))


def _normalize_role(role: str) -> str:
    """Strip the auth-layer `role_` prefix — DSL personas are bare names."""
    return role.removeprefix("role_") if isinstance(role, str) else str(role)


def _check_scope_create(
    *,
    access_spec: EntityAccessSpec,
    payload: dict[str, Any],
    entity_name: str,
    user_id: str,
    user_roles: list[str],
    request: Request,
    service: Any = None,
    fk_graph: Any = None,
) -> None:
    """Walk `scope: create:` rules; raise HTTPException(403) on reject.

    Mirrors the logic in `route_generator._enforce_create_scope` so
    overrides see the same enforcement as framework-generated CREATE
    routes. Simple leaves (ColumnCheck, UserAttrCheck, PathCheck depth 1,
    BoolComposite) evaluate in-Python; FK-path (depth > 1) and EXISTS
    leaves resolve via a payload-time SQL probe built from the entity's
    ``service`` repository (#1311, ADR-0028). When no service/DB is
    available the probe-requiring shapes fail closed (default-deny 403).
    """
    scopes = getattr(access_spec, "scopes", None) or []
    create_rules = [
        r
        for r in scopes
        if getattr(getattr(r, "operation", None), "value", str(getattr(r, "operation", None)))
        == "create"
    ]
    if not create_rules:
        return

    normalised = {_normalize_role(r) for r in user_roles}
    matched: list[Any] = []
    for r in create_rules:
        personas = list(getattr(r, "personas", []) or [])
        if "*" in personas or (normalised & set(personas)):
            matched.append(r)

    if not matched:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "scope_create_denied",
                "entity": entity_name,
                "reason": "No matching scope: create: rule for this role.",
            },
        )

    # If any matched rule is `all` (no predicate), the user gets through.
    for r in matched:
        if getattr(r, "predicate", None) is None and getattr(r, "condition", None) is None:
            return

    # Build the user-attr resolver from the auth context — same lazy
    # resolver `route_generator._enforce_create_scope` uses (#1174). A
    # `scope: create:` predicate may reference `current_user.<attr>` for
    # ANY DSL-chosen attribute (`org`, `school`, ...); resolving lazily
    # through `_resolve_user_attribute` (built-in UserRecord fields +
    # `auth_context.preferences`) avoids the hardcoded-allowlist bug that
    # silently over-denied any attribute not on a fixed list.
    from dazzle.http.runtime.scope_filters import _LazyUserAttrs

    auth_ctx = getattr(request.state, "auth_context", None) if hasattr(request, "state") else None
    user_attrs = _LazyUserAttrs(auth_ctx)

    from dazzle.http.runtime.scope_create_eval import (
        ScopeCreateUnsupportedError,
        check_create_predicate,
    )
    from dazzle.http.runtime.scope_filters import build_create_scope_probe
    from dazzle.http.runtime.tenant_isolation import get_current_tenant_schema

    probe = build_create_scope_probe(service, entity_name)
    schema = get_current_tenant_schema()

    for r in matched:
        predicate = getattr(r, "predicate", None)
        if predicate is None:
            continue
        try:
            if check_create_predicate(
                predicate,
                payload,
                user_id=user_id,
                user_attrs=user_attrs,
                probe=probe,
                fk_graph=fk_graph,
                entity_name=entity_name,
                schema=schema,
            ):
                return
        except ScopeCreateUnsupportedError:
            logger.warning(
                "policy.check_entity_op:create-predicate-no-probe entity=%s — "
                "FK-path / EXISTS create-scope needs a repository-backed probe "
                "but none was available; denying.",
                entity_name,
            )
            continue

    raise HTTPException(
        status_code=403,
        detail={
            "error": "scope_create_denied",
            "entity": entity_name,
            "reason": "The inserted row does not satisfy the scope: create: predicate.",
        },
    )


__all__ = [
    "EntityPolicyInfo",
    "PolicyRegistry",
    "check_entity_op",
]
