"""Transport-agnostic data-access core (#1422 option b).

The enforcement+data logic relocated out of the REST route-handler closures so
both the REST API and the HTML page layer call ONE core, in-process, instead of
the page layer self-fetching its own REST endpoint over loopback HTTP.

Scope (tenant isolation) is already compiled into Repository SQL via the
``__scope_predicate`` filter key; permit (Cedar) is relocated here from the route
closures. See docs/superpowers/specs/2026-06-20-page-rest-inprocess-core-design.md.
"""

from dataclasses import dataclass
from typing import Any


class AccessForbidden(Exception):
    """Permit (Cedar) denied the operation."""


class RecordNotFound(Exception):
    """Row is missing or hidden by a scope predicate."""


@dataclass(frozen=True)
class AccessContext:
    """Everything enforcement needs, bundled once per request."""

    auth_context: Any
    entity_name: str
    cedar_access_spec: Any | None
    fk_graph: Any | None
    admin_personas: list[str] | None


def access_context_from(
    *,
    auth_context: Any,
    entity_name: str,
    cedar_access_spec: Any | None,
    fk_graph: Any | None,
    admin_personas: list[str] | None,
) -> AccessContext:
    """Bundle the per-request enforcement inputs into an AccessContext."""
    return AccessContext(
        auth_context=auth_context,
        entity_name=entity_name,
        cedar_access_spec=cedar_access_spec,
        fk_graph=fk_graph,
        admin_personas=admin_personas,
    )


async def gated_read(
    service: Any,
    access: AccessContext,
    entity_id: Any,
    *,
    include: list[str] | None = None,
    audit_logger: Any = None,
    request: Any = None,
) -> Any:
    """Read a record by id with scope + permit applied, or raise.

    Relocated verbatim from ``read_handlers.py::_read_cedar`` (the enforcement+data
    half; the HTTP-shaping ``_render_detail_html`` stays in the REST adapter). Scope
    is enforced by ``_scoped_pre_read`` (a scoped ``list`` by id — NOT a bare
    ``Repository.read``, which has no scope); permit by ``evaluate_permission``.

    Raises ``RecordNotFound`` when the row is missing, scope-denied, OR permit-denied
    (READ keeps row-existence opaque — a 404, matching ``read_handlers.py:194``).
    Audits only when ``audit_logger`` and ``request`` are supplied (REST passes them;
    the page adapter passes neither, preserving today's no-audit-on-page-read behavior).
    """
    from dazzle.core.access import AccessDecision, AccessOperationKind
    from dazzle.http.runtime.audit_log import measure_evaluation_time
    from dazzle.http.runtime.audit_wrap import (
        _SCOPE_DENY_EFFECT,
        _build_access_context,
        _log_audit_decision,
        _record_to_dict,
    )
    from dazzle.http.runtime.scope_filters import _scoped_pre_read
    from dazzle.render.access_evaluator import evaluate_permission

    assert access.cedar_access_spec is not None
    result = await _scoped_pre_read(
        service=service,
        operation="read",
        id=entity_id,
        cedar_access_spec=access.cedar_access_spec,
        auth_context=access.auth_context,
        entity_name=access.entity_name,
        fk_graph=access.fk_graph,
        admin_personas=access.admin_personas,
    )
    if result is None:
        if audit_logger and request is not None:
            _u, _ = _build_access_context(access.auth_context)
            await _log_audit_decision(
                audit_logger,
                request,
                operation="read",
                entity_name=access.entity_name,
                entity_id=str(entity_id),
                decision="deny",
                matched_policy=_SCOPE_DENY_EFFECT,
                policy_effect=_SCOPE_DENY_EFFECT,
                user=_u,
            )
        raise RecordNotFound(access.entity_name)

    # `_scoped_pre_read` may return a list-path row lacking `include` relations;
    # re-fetch through the read path to restore the response shape (scope already
    # passed for this id above, so this re-fetch is intentionally unscoped).
    if include:
        hydrated = await service.execute(operation="read", id=entity_id, include=include)
        if hydrated is not None:
            result = hydrated

    user, ctx = _build_access_context(access.auth_context)
    decision: AccessDecision
    decision, eval_us = measure_evaluation_time(
        lambda: evaluate_permission(
            access.cedar_access_spec,
            AccessOperationKind.READ,
            _record_to_dict(result),
            ctx,
            entity_name=access.entity_name,
        )
    )
    if audit_logger and request is not None:
        await _log_audit_decision(
            audit_logger,
            request,
            operation="read",
            entity_name=access.entity_name,
            entity_id=str(entity_id),
            decision="allow" if decision.allowed else "deny",
            matched_policy=decision.matched_policy,
            policy_effect=decision.effect,
            user=user,
            evaluation_time_us=eval_us,
        )
    if not decision.allowed:
        # Permit-denied READ is opaque to the caller (404, not 403) — matches
        # read_handlers.py:194 exactly.
        raise RecordNotFound(access.entity_name)
    return result
