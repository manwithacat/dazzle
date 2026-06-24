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

from dazzle.core.access import AccessDecision, AccessOperationKind


class AccessForbidden(Exception):
    """Permit (Cedar) denied the operation."""


class RecordNotFound(Exception):
    """Row is missing or hidden by a scope predicate."""


class InvalidTemporalParam(Exception):
    """A temporal query param (``?as_of=``) was malformed. The message is the
    client-facing 400 detail. Raised AFTER the permit gate so a denied caller is
    rejected (403) before any input is validated (the principled order, #1406)."""


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


# Sentinel: the scope layer matched no rule for this role → default-deny. The
# caller turns this into an EMPTY page (the list's documented shape), NOT an error.
_SCOPE_DEFAULT_DENY = object()


def _apply_list_permit_gate(
    cedar: Any, auth_context: Any, is_authenticated: bool, entity_name: str
) -> None:
    """Cedar LIST permit gate. Raises ``AccessForbidden`` only when ALL list rules
    are pure role checks and the caller's role is denied. Rules carrying field
    conditions are row-level filters (enforced by scope below), so a field-conditioned
    ruleset deliberately skips this gate."""
    if not (cedar and is_authenticated and auth_context):
        return
    from dazzle.http.runtime.audit_wrap import _build_access_context
    from dazzle.http.runtime.condition_evaluator import _is_field_condition

    list_rules = [r for r in cedar.permissions if r.operation == AccessOperationKind.LIST]
    has_field_conditions = any(_is_field_condition(r.condition) for r in list_rules)
    if list_rules and not has_field_conditions:
        from dazzle.render.access_evaluator import evaluate_permission

        _user, _ctx = _build_access_context(auth_context)
        decision = evaluate_permission(
            cedar, AccessOperationKind.LIST, None, _ctx, entity_name=entity_name
        )
        if not decision.allowed:
            raise AccessForbidden(entity_name)


def _resolve_list_scope(
    access: AccessContext,
    *,
    is_authenticated: bool,
    user_id: str | None,
    ref_targets: dict[str, str] | None,
    sql_filters: dict[str, Any] | None,
) -> Any:
    """Merge the Cedar list-scope predicates into ``sql_filters``. Returns the merged
    filters, or ``_SCOPE_DEFAULT_DENY`` when no scope rule matched the role (the caller
    returns an empty page). An empty scope result (``{}``) leaves filters unchanged."""
    cedar = access.cedar_access_spec
    if not (cedar and is_authenticated and user_id):
        return sql_filters
    from dazzle.http.runtime.auth.models import effective_roles_of
    from dazzle.http.runtime.policy import _normalize_role
    from dazzle.http.runtime.scope_filters import _resolve_scope_filters

    if not getattr(cedar, "scopes", None):
        return sql_filters
    _scope_user_roles = {_normalize_role(_r) for _r in effective_roles_of(access.auth_context)}
    scope_result = _resolve_scope_filters(
        cedar,
        "list",
        _scope_user_roles,
        user_id,
        access.auth_context,
        ref_targets,
        entity_name=access.entity_name,
        fk_graph=access.fk_graph,
        admin_personas=access.admin_personas,
    )
    if scope_result is None:
        return _SCOPE_DEFAULT_DENY
    if scope_result:
        return {**(sql_filters or {}), **scope_result}
    return sql_filters


def _parse_temporal_filters(
    service: Any, *, temporal_as_of_raw: str | None, temporal_include_closed: bool
) -> dict[str, Any]:
    """Parse the temporal query params (``?as_of=`` / ``?include_closed=``) into the
    repository's special filter keys (``__as_of`` / ``<end>__isnull``). Parsed AFTER
    the permit gate + scope so a denied caller is rejected (403) before any input is
    validated (#1406 order). Raises ``InvalidTemporalParam`` on a malformed ``as_of``.
    Returns ``{}`` for non-temporal entities."""
    _temporal: dict[str, Any] = {}
    _entity_spec = getattr(service, "entity_spec", None)
    _entity_temporal = _entity_spec.temporal if _entity_spec is not None else None
    if _entity_temporal is None:
        return _temporal
    if temporal_as_of_raw:
        from datetime import date as _date

        try:
            _temporal["__as_of"] = _date.fromisoformat(temporal_as_of_raw)
        except (ValueError, TypeError):
            raise InvalidTemporalParam(
                f"Invalid {_entity_temporal.as_of_param}={temporal_as_of_raw!r}: "
                f"expected YYYY-MM-DD"
            )
    if temporal_include_closed:
        _temporal[f"{_entity_temporal.end_field}__isnull"] = False
    return _temporal


def _apply_list_post_filter(result: dict[str, Any], post_filter: Any, user_id: str | None) -> None:
    """Apply the OR-condition visibility post-filter to the result page in place
    (re-counting ``total``). No-op when there's no post-filter or no items."""
    if not (post_filter and result and "items" in result):
        return
    from dazzle.http.runtime.condition_evaluator import filter_records_by_condition

    context = {"current_user_id": user_id}
    items = result["items"]
    if items and hasattr(items[0], "model_dump"):
        items = [item.model_dump() for item in items]
    filtered_items = filter_records_by_condition(items, post_filter, context)
    result["items"] = filtered_items
    result["total"] = len(filtered_items)


async def gated_list(
    service: Any,
    access: AccessContext,
    *,
    page: int,
    page_size: int,
    sort_list: list[str] | None = None,
    search: str | None = None,
    user_filters: dict[str, Any] | None = None,
    select_fields: list[str] | None = None,
    auto_include: list[str] | None = None,
    search_fields: list[str] | None = None,
    access_spec: dict[str, Any] | None = None,
    ref_targets: dict[str, str] | None = None,
    temporal_as_of_raw: str | None = None,
    temporal_include_closed: bool = False,
) -> dict[str, Any]:
    """List rows with scope + permit applied, or raise. Returns the
    ``{items,total,page,page_size}`` page dict (pre-shaping).

    Relocated verbatim from ``list_handlers.py::_list_handler_body`` — the
    enforcement+data half: the Cedar LIST permit gate (→ ``AccessForbidden``
    instead of the route's ``HTTPException(403)``), the legacy visibility filter,
    the Cedar scope merge (scope-default-deny → an EMPTY page, NOT an error — the
    list's documented shape), the ``service.execute("list", …)`` call, and the
    OR-condition ``post_filter`` that runs on the result. HTTP concerns stay in
    the adapter: request-param parsing (the caller passes already-parsed
    ``user_filters``, incl. any temporal ``__as_of``/``__isnull`` keys, plus
    ``sort_list``), the success audit, and all output shaping.

    ``is_authenticated``/``user_id`` derive from ``access.auth_context`` exactly
    as the route handler computes them.
    """
    from dazzle.http.runtime.condition_evaluator import build_visibility_filter

    auth_context = access.auth_context
    is_authenticated = bool(auth_context and auth_context.is_authenticated)
    user_id = (
        str(auth_context.user.id) if auth_context and getattr(auth_context, "user", None) else None
    )

    # 1. Cedar LIST permit gate (pure-role rules → 403; field-conditioned → scope below).
    _apply_list_permit_gate(
        access.cedar_access_spec, auth_context, is_authenticated, access.entity_name
    )

    # 2. Legacy visibility filter + 3. Cedar scope merge (default-deny → empty page).
    sql_filters, post_filter = build_visibility_filter(access_spec, is_authenticated, user_id)
    sql_filters = _resolve_list_scope(
        access,
        is_authenticated=is_authenticated,
        user_id=user_id,
        ref_targets=ref_targets,
        sql_filters=sql_filters,
    )
    if sql_filters is _SCOPE_DEFAULT_DENY:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    # 4. Temporal params — parsed post-gate so a denied caller is rejected before
    #    any input validation runs (#1406 order).
    _temporal = _parse_temporal_filters(
        service,
        temporal_as_of_raw=temporal_as_of_raw,
        temporal_include_closed=temporal_include_closed,
    )

    merged_filters: dict[str, Any] | None = None
    if sql_filters or user_filters or _temporal:
        merged_filters = {**(sql_filters or {}), **(user_filters or {}), **_temporal}

    result: dict[str, Any] = await service.execute(
        operation="list",
        page=page,
        page_size=page_size,
        filters=merged_filters,
        sort=sort_list,
        search=search,
        select_fields=select_fields,
        include=auto_include,
        search_fields=search_fields,
    )

    # 5. OR-condition visibility post-filter (runs on the result page).
    _apply_list_post_filter(result, post_filter, user_id)
    return result
