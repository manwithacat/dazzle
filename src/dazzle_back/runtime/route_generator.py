"""
Route generator - generates FastAPI routes from EndpointSpec.

This module creates FastAPI routers and routes from backend specifications.
"""

from collections.abc import Callable
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from dazzle.core.strings import to_api_plural
from dazzle_back.runtime._fastapi_compat import (
    FASTAPI_AVAILABLE,
    Depends,
    HTMLResponse,
    HTTPException,
    Query,
    Request,
)
from dazzle_back.runtime._fastapi_compat import APIRouter as _APIRouter
from dazzle_back.specs.endpoint import EndpointSpec, HttpMethod
from dazzle_back.specs.service import OperationKind, ServiceSpec

if FASTAPI_AVAILABLE:
    from dazzle_back.runtime.auth import AuthContext
    from dazzle_back.runtime.htmx_response import htmx_trigger_headers
else:
    AuthContext = None  # type: ignore[assignment,misc]

# Expose APIRouter name for return-type annotations (the real class is
# imported as _APIRouter to allow a None fallback when FastAPI is absent).
APIRouter = _APIRouter


def _set_handler_annotations(fn: Any, *, with_id: bool = False, with_auth: bool = False) -> None:
    """Set FastAPI-compatible type annotations on a dynamic handler function."""
    ann: dict[str, Any] = {"request": Request, "return": Any}
    if with_id:
        ann["id"] = UUID
    if with_auth:
        ann["auth_context"] = AuthContext
    fn.__annotations__ = ann


def _is_htmx_request(request: Any) -> bool:
    """Check if this is a genuine HTMX request (HX-Request header present)."""
    from dazzle_back.runtime.htmx_response import HtmxDetails

    return HtmxDetails.from_request(request).is_htmx


def _wants_html(request: Any) -> bool:
    """Check if the client wants an HTML response (HTMX or browser navigation)."""
    if _is_htmx_request(request):
        return True
    if hasattr(request, "headers"):
        accept = request.headers.get("Accept", "")
        return "text/html" in accept
    return False


def _htmx_current_url(request: Any) -> str | None:
    """Return the HX-Current-URL header if this is an HTMX request, else None."""
    return request.headers.get("hx-current-url") if _is_htmx_request(request) else None


def _htmx_parent_url(request: Any) -> str | None:
    """Return the parent of HX-Current-URL (e.g. /tasks/abc → /tasks) for post-delete redirect."""
    url = _htmx_current_url(request)
    if not url:
        return None
    # Strip trailing ID segment to get list page URL
    from urllib.parse import urlparse

    parsed = urlparse(url)
    parent = parsed.path.rsplit("/", 1)[0] or "/"
    return parent


def _with_htmx_triggers(
    request: Any, result: Any, entity_name: str, action: str, redirect_url: str | None = None
) -> Any:
    """Wrap a mutation result with HX-Trigger headers for HTMX requests.

    For non-HTMX requests, returns the result unchanged (JSON serialized by FastAPI).
    For HTMX requests, returns a JSONResponse with HX-Trigger headers so the client
    can react to entity mutations (show toasts, refresh lists, etc.).

    Args:
        request: The incoming request.
        result: The mutation result.
        entity_name: Name of the entity (e.g. "Task").
        action: Mutation action ("created", "updated", "deleted").
        redirect_url: Optional URL for HX-Redirect header (post-create navigation).
    """
    if not _is_htmx_request(request):
        return result

    from fastapi.responses import JSONResponse as _JSONResponse

    # Serialize Pydantic models
    if hasattr(result, "model_dump"):
        body = result.model_dump(mode="json")
    elif isinstance(result, dict):
        # Plain dicts may contain UUID or other non-JSON-serializable values
        # from the CRUD service layer.  Pre-convert via jsonable_encoder so
        # Starlette's JSONResponse (which uses stdlib json.dumps) doesn't crash.
        from fastapi.encoders import jsonable_encoder

        body = jsonable_encoder(result)
    else:
        body = result

    headers = htmx_trigger_headers(entity_name, action)
    if redirect_url:
        headers["HX-Redirect"] = redirect_url
    return _JSONResponse(content=body, headers=headers)


async def _parse_request_body(request: Any) -> dict[str, Any]:
    """Parse request body as JSON or form data.

    HTMX forms send JSON when the json-enc extension is loaded, but
    fall back to form-urlencoded otherwise.  Accept both so the API
    works regardless of client encoding.

    Empty string values are converted to None so that optional fields
    (e.g. ref/UUID fields) pass Pydantic validation.
    """
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        body = dict(form)
    else:
        # Default: JSON (covers application/json and missing header)
        body = await request.json()
    # Convert empty strings to None for optional field validation
    return {k: (None if v == "" else v) for k, v in body.items()}


# =============================================================================
# Row-level RBAC helpers
# =============================================================================


def _extract_cedar_row_filters(
    cedar_access_spec: Any,
    user_id: str,
    auth_context: Any | None = None,
) -> dict[str, Any]:
    """Extract SQL-compatible row filters from Cedar permission rules.

    .. deprecated::
        Superseded by the predicate compiler pipeline in v0.44+.  Scope rules
        now carry compiled :class:`ScopePredicate` trees which are compiled to
        SQL by :func:`compile_predicate`.  This function is retained only for
        backward compatibility with callers that have not yet migrated to the
        scope: block syntax.

    Scans LIST and READ permission rules for field-level conditions that
    reference ``current_user`` and converts them to repository filter syntax.
    Role-only rules (no field condition) are skipped since they grant
    unrestricted access to the operation.

    Returns a dict suitable for merging into the repository's filter kwargs.
    """
    import logging

    _logger = logging.getLogger(__name__)

    permissions = getattr(cedar_access_spec, "permissions", None)
    if not permissions:
        return {}

    # Collect roles from auth_context, normalizing role_ prefix
    user_roles: set[str] = set()
    if auth_context is not None:
        _user_obj = getattr(auth_context, "user", None)
        if _user_obj:
            for r in getattr(_user_obj, "roles", []):
                name = r if isinstance(r, str) else getattr(r, "name", str(r))
                user_roles.add(_normalize_role(name))

    filters: dict[str, Any] = {}
    has_unrestricted_permit = False

    for rule in permissions:
        op = getattr(rule, "operation", None)
        if op is None:
            continue
        op_val = op.value if hasattr(op, "value") else str(op)

        # Only process LIST and READ rules
        if op_val not in ("list", "read"):
            continue

        effect = getattr(rule, "effect", None)
        if effect is None:
            continue
        effect_val = effect.value if hasattr(effect, "value") else str(effect)
        if effect_val != "permit":
            continue

        condition = getattr(rule, "condition", None)
        if condition is None:
            # Unconditional permit — user has full access, no row filter needed.
            # But only if they pass the role check (if personas specified).
            rule_personas = getattr(rule, "personas", [])
            if rule_personas:
                if user_roles & set(rule_personas):
                    has_unrestricted_permit = True
            else:
                has_unrestricted_permit = True
            continue

        # Check if this rule applies to the user's roles
        rule_personas = getattr(rule, "personas", [])
        if rule_personas and not (user_roles & set(rule_personas)):
            continue

        # Extract field comparison conditions
        _extract_condition_filters(condition, user_id, filters, _logger, auth_context)

    # If user has any unrestricted permit, don't apply row filters
    if has_unrestricted_permit:
        return {}

    return filters


def _build_fk_path_subquery(
    field: str,
    resolved_value: Any,
    ref_targets: dict[str, str],
) -> tuple[str, str, list[Any]] | None:
    """Build a subquery for a left-side dotted path like ``manuscript.student``.

    Given field="manuscript.student", resolves:
    - ``manuscript`` → FK field ``manuscript_id`` on current entity
    - target entity ``Manuscript`` (from ref_targets["manuscript_id"])
    - ``student`` → column ``student_id`` on target entity (with _id suffix inferred)

    Returns (fk_field, subquery_sql, params) or None if the path can't be resolved.
    """
    from dazzle_back.runtime.query_builder import quote_identifier

    parts = field.split(".", 1)
    if len(parts) != 2:
        return None

    relation_name, target_field = parts

    # Resolve relation name to FK field on current entity.
    # Convention: relation "manuscript" → FK field "manuscript_id"
    fk_candidates = [f"{relation_name}_id", relation_name]
    target_entity = None
    fk_field = None
    for candidate in fk_candidates:
        if candidate in ref_targets:
            fk_field = candidate
            target_entity = ref_targets[candidate]
            break

    if not target_entity or not fk_field:
        return None

    target_table = quote_identifier(target_entity)
    # The target field may or may not have _id suffix — try both
    target_col = quote_identifier(target_field)

    subquery_sql = f'SELECT "id" FROM {target_table} WHERE {target_col} = %s'  # nosemgrep
    return fk_field, subquery_sql, [resolved_value]


def _build_via_subquery(
    *,
    junction_entity: str,
    bindings: list[dict[str, str]],
    user_id: str,
    auth_context: Any = None,
) -> tuple[str, str, list[Any]]:
    """Build a SQL subquery for a via-check scope condition.

    Returns (entity_field, subquery_sql, params).
    """
    from dazzle_back.runtime.query_builder import quote_identifier

    junction_table = quote_identifier(junction_entity)
    select_field = None
    entity_field = None
    where_clauses: list[str] = []
    params: list[Any] = []

    for binding in bindings:
        jf = quote_identifier(binding["junction_field"])
        target = binding["target"]
        op = binding.get("operator", "=")

        if target == "null":
            if op == "=":
                where_clauses.append(f"{jf} IS NULL")  # nosemgrep
            else:
                where_clauses.append(f"{jf} IS NOT NULL")  # nosemgrep
        elif target.startswith("current_user"):
            if target == "current_user":
                # Prefer DSL User entity ID over auth user ID so via
                # clauses matching ref User fields work correctly (#534).
                resolved = _resolve_user_attribute("entity_id", auth_context)
                if resolved == "__RBAC_DENY__":
                    resolved = user_id  # fallback to auth ID
            else:
                attr_name = target[len("current_user.") :]
                resolved = _resolve_user_attribute(attr_name, auth_context)
                if resolved == "__RBAC_DENY__":
                    # Null FK on the user — no possible junction match.
                    # Return an impossible subquery so the caller gets zero
                    # rows instead of a 500 from a type-mismatch (#580).
                    # Find entity_field from remaining bindings if not yet set.
                    ef = entity_field
                    if ef is None:
                        for b in bindings:
                            if not b["target"].startswith("current_user") and b["target"] != "null":
                                ef = b["target"]
                                break
                    return ef or "id", "SELECT NULL WHERE FALSE", []
            where_clauses.append(f"{jf} = %s")  # nosemgrep
            params.append(resolved)
        else:
            # Entity binding: target is a field name on the scoped entity
            select_field = jf
            entity_field = target

    if select_field is None or entity_field is None:
        raise ValueError("via condition must have at least one entity binding")

    where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
    subquery_sql = f"SELECT {select_field} FROM {junction_table} WHERE {where_sql}"  # nosemgrep

    return entity_field, subquery_sql, params


def _resolve_user_attribute(attr_name: str, auth_context: Any) -> Any:
    """Resolve a ``current_user.<attr_name>`` dotted reference to a concrete value.

    Resolution order:
    1. Built-in ``UserRecord`` fields (``id``, ``email``, ``username``, etc.)
    2. ``auth_context.preferences`` dict (domain-specific attributes like
       ``school``, ``school_id``, etc.)

    If the attribute is not found, returns ``"__RBAC_DENY__"`` so the caller
    can inject an impossible filter — enforcing deny-by-default security.
    """
    _RBAC_DENY = "__RBAC_DENY__"

    if auth_context is None:
        return _RBAC_DENY

    user = getattr(auth_context, "user", None)

    # 1. Built-in UserRecord fields (id, email, username, ...).
    # Only accept scalar primitives — avoids MagicMock/object auto-attribute
    # hits in tests and rejects non-serialisable field values in production.
    _SCALAR = str | int | float | bool
    if user is not None:
        # Try exact attribute name first
        user_val = getattr(user, attr_name, None)
        if isinstance(user_val, _SCALAR):
            return str(user_val)
        # Also try <attr>_id variant (e.g. "school" → try "school_id")
        user_val_id = getattr(user, f"{attr_name}_id", None)
        if isinstance(user_val_id, _SCALAR):
            return str(user_val_id)

    # 2. Preferences dict (stores domain-level attributes as strings).
    # Treat None values as missing — they must not bypass the deny sentinel (#591).
    prefs: dict[str, str] = getattr(auth_context, "preferences", {}) or {}
    if attr_name in prefs and prefs[attr_name] is not None:
        return prefs[attr_name]
    # Also try <attr>_id variant in preferences
    attr_id_key = f"{attr_name}_id"
    if attr_id_key in prefs and prefs[attr_id_key] is not None:
        return prefs[attr_id_key]

    return _RBAC_DENY


def _extract_condition_filters(
    condition: Any,
    user_id: str,
    filters: dict[str, Any],
    _logger: Any,
    auth_context: Any = None,
    ref_targets: dict[str, str] | None = None,
) -> None:
    """Recursively extract SQL filters from a condition tree.

    Handles two condition formats:
    - **IR ConditionExpr**: ``.comparison`` (Comparison), ``.operator``, ``.left``/``.right``
    - **AccessConditionSpec**: ``.kind``, ``.field``, ``.value``, ``.comparison_op``,
      ``.logical_op``, ``.logical_left``/``.logical_right``

    Only simple equality conditions with ``current_user`` are pushed to SQL.
    OR trees require post-fetch filtering (handled by the visibility system).

    Dotted ``current_user.<attr>`` values are resolved from the authenticated
    user's built-in fields and preferences.  If the attribute cannot be
    resolved the filter is set to ``__RBAC_DENY__`` to ensure no rows are
    returned — secure by default (#526).

    Left-side dotted paths (e.g. ``manuscript.student``) are resolved via
    subquery JOINs when ``ref_targets`` provides FK→entity mapping (#556).
    """
    kind = getattr(condition, "kind", "")

    # Helper: assign a filter, using subquery if field is a dotted FK path (#556)
    def _set_filter(fld: str, val: Any) -> None:
        if val == "__RBAC_DENY__":
            # Null FK / missing attribute — use impossible subquery so the
            # query returns zero rows instead of crashing with a type error (#580).
            filters[f"{fld}__in_subquery"] = ("SELECT NULL WHERE FALSE", [])
            return
        if "." in fld and ref_targets:
            result = _build_fk_path_subquery(fld, val, ref_targets)
            if result:
                fk_field, sql, params = result
                filters[f"{fk_field}__in_subquery"] = (sql, params)
                return
        filters[fld] = val

    # ---- AccessConditionSpec path (has explicit .kind) --------------------
    if kind == "comparison":
        field = getattr(condition, "field", None)
        value = getattr(condition, "value", None)
        op = getattr(condition, "comparison_op", None)
        if op is None:
            op_val = "="
        else:
            op_val = op.value if hasattr(op, "value") else str(op)

        if field and value == "current_user" and op_val in ("=", "eq", "equals"):
            # Prefer DSL User entity ID over auth user ID so comparisons
            # against ref User fields work correctly (#546).
            resolved = _resolve_user_attribute("entity_id", auth_context)
            _set_filter(field, user_id if resolved == "__RBAC_DENY__" else resolved)
        elif (
            field
            and isinstance(value, str)
            and value.startswith("current_user.")
            and op_val in ("=", "eq", "equals")
        ):
            attr_name = value[len("current_user.") :]
            _set_filter(field, _resolve_user_attribute(attr_name, auth_context))
        elif field and isinstance(value, str | int | float | bool) and value != "current_user":
            if op_val in ("=", "eq", "equals"):
                _set_filter(field, value)
            elif op_val in ("!=", "ne", "not_equals"):
                filters[f"{field}__ne"] = value
            elif op_val in (">", "gt"):
                filters[f"{field}__gt"] = value
            elif op_val in (">=", "ge"):
                filters[f"{field}__gte"] = value
            elif op_val in ("<", "lt"):
                filters[f"{field}__lt"] = value
            elif op_val in ("<=", "le"):
                filters[f"{field}__lte"] = value
            elif op_val == "in":
                filters[f"{field}__in"] = value
        return

    if kind == "logical":
        logical_op = getattr(condition, "logical_op", None)
        if logical_op is None:
            return
        logical_op_val = logical_op.value if hasattr(logical_op, "value") else str(logical_op)
        if logical_op_val == "and":
            left = getattr(condition, "logical_left", None)
            right = getattr(condition, "logical_right", None)
            if left:
                _extract_condition_filters(
                    left, user_id, filters, _logger, auth_context, ref_targets
                )
            if right:
                _extract_condition_filters(
                    right, user_id, filters, _logger, auth_context, ref_targets
                )
        return

    if kind == "via_check":
        junction_entity = getattr(condition, "via_junction_entity", None)
        bindings = getattr(condition, "via_bindings", None)
        if junction_entity and bindings:
            entity_field, subquery_sql, subquery_params = _build_via_subquery(
                junction_entity=junction_entity,
                bindings=bindings,
                user_id=user_id,
                auth_context=auth_context,
            )
            filters[f"{entity_field}__in_subquery"] = (subquery_sql, subquery_params)
        return

    # ---- IR ConditionExpr path (no .kind, uses .comparison/.operator) -----
    comp = getattr(condition, "comparison", None)
    if comp is not None:
        field = getattr(comp, "field", None)
        cond_value = getattr(comp, "value", None)
        op = getattr(comp, "operator", None)
        op_val = getattr(op, "value", None) or (str(op) if op else "=")

        # Resolve the raw value from ConditionValue or plain string
        raw_value: Any = None
        if cond_value is not None and hasattr(cond_value, "literal"):
            raw_value = getattr(cond_value, "literal", cond_value)
        elif isinstance(cond_value, str):
            raw_value = cond_value
        else:
            raw_value = cond_value

        if field and raw_value == "current_user" and op_val in ("=", "eq", "equals"):
            # Prefer DSL User entity ID over auth user ID so comparisons
            # against ref User fields work correctly (#546).
            resolved = _resolve_user_attribute("entity_id", auth_context)
            _set_filter(field, user_id if resolved == "__RBAC_DENY__" else resolved)
        elif (
            field
            and isinstance(raw_value, str)
            and raw_value.startswith("current_user.")
            and op_val in ("=", "eq", "equals")
        ):
            attr_name = raw_value[len("current_user.") :]
            _set_filter(field, _resolve_user_attribute(attr_name, auth_context))
        elif (
            field
            and isinstance(raw_value, str | int | float | bool)
            and raw_value != "current_user"
        ):
            if op_val in ("=", "eq", "equals"):
                _set_filter(field, raw_value)
            elif op_val in ("!=", "ne", "not_equals"):
                filters[f"{field}__ne"] = raw_value
            elif op_val in (">", "gt"):
                filters[f"{field}__gt"] = raw_value
            elif op_val in (">=", "ge"):
                filters[f"{field}__gte"] = raw_value
            elif op_val in ("<", "lt"):
                filters[f"{field}__lt"] = raw_value
            elif op_val in ("<=", "le"):
                filters[f"{field}__lte"] = raw_value
            elif op_val == "in":
                filters[f"{field}__in"] = raw_value
        return

    # Compound ConditionExpr: .operator (AND/OR) with .left / .right
    logical_op = getattr(condition, "operator", None)
    if logical_op is not None:
        logical_op_val = logical_op.value if hasattr(logical_op, "value") else str(logical_op)

        # Only push AND conditions to SQL; OR needs post-fetch filtering
        if logical_op_val == "and":
            left = getattr(condition, "left", None)
            right = getattr(condition, "right", None)
            if left:
                _extract_condition_filters(
                    left, user_id, filters, _logger, auth_context, ref_targets
                )
            if right:
                _extract_condition_filters(
                    right, user_id, filters, _logger, auth_context, ref_targets
                )
        # OR and other logical operators require post-fetch filtering
        # which is handled by the visibility system already
        return

    # Via-check condition (IR path)
    via_cond = getattr(condition, "via_condition", None)
    if via_cond is not None:
        bindings_dicts = [
            {"junction_field": b.junction_field, "target": b.target, "operator": b.operator}
            for b in via_cond.bindings
        ]
        entity_field, subquery_sql, subquery_params = _build_via_subquery(
            junction_entity=via_cond.junction_entity,
            bindings=bindings_dicts,
            user_id=user_id,
            auth_context=auth_context,
        )
        filters[f"{entity_field}__in_subquery"] = (subquery_sql, subquery_params)
        return


# =============================================================================
# Access Control Helpers
# =============================================================================


def _normalize_role(role: str) -> str:
    """Normalize a database role name to match DSL role references.

    Database roles may have a ``role_`` prefix (e.g. ``role_school_admin``)
    while DSL access rules use bare names (e.g. ``role(school_admin)``).
    """
    return role.removeprefix("role_")


def _build_access_context(auth_context: Any) -> tuple[Any, Any]:
    """Build (user, AccessRuntimeContext) from an AuthContext.

    Returns (user_or_none, runtime_context) for Cedar policy evaluation.
    """
    from dazzle_back.runtime.access_evaluator import AccessRuntimeContext

    user = auth_context.user if auth_context.is_authenticated else None
    raw_roles = list(getattr(user, "roles", [])) if user else []
    ctx = AccessRuntimeContext(
        user_id=str(user.id) if user else None,
        roles=[_normalize_role(r) for r in raw_roles],
        is_superuser=getattr(user, "is_superuser", False) if user else False,
    )
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
    audit_logger: Any,
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
    from dazzle_back.runtime.audit_log import create_audit_context_from_request

    audit_ctx = create_audit_context_from_request(request)
    await audit_logger.log_decision(
        operation=operation,
        entity_name=entity_name,
        entity_id=entity_id,
        decision=decision,
        matched_policy=matched_policy,
        policy_effect=policy_effect,
        user_id=str(user.id) if user else None,
        user_email=getattr(user, "email", None) if user else None,
        user_roles=list(getattr(user, "roles", [])) if user else None,
        evaluation_time_us=evaluation_time_us,
        field_changes=field_changes,
        **audit_ctx,
    )


# =============================================================================
# Route Handler Factory
# =============================================================================


# =============================================================================
# Auth wrapper — eliminates cedar / auth / noauth triplication
# =============================================================================


def _wrap_with_auth(
    core_fn: Callable[..., Any],
    *,
    service: Any,
    cedar_access_spec: Any | None,
    auth_dep: Callable[..., Any] | None,
    optional_auth_dep: Callable[..., Any] | None,
    require_auth_by_default: bool,
    operation: str,
    entity_name: str,
    audit_logger: Any | None,
    include_field_changes: bool = False,
    needs_pre_read: bool = False,
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
    service: Any,
    cedar_access_spec: Any,
    optional_auth_dep: Callable[..., Any],
    operation: str,
    entity_name: str,
    audit_logger: Any | None,
    include_field_changes: bool,
    needs_pre_read: bool,
    is_create: bool,
) -> Callable[..., Any]:
    """Build a Cedar-policy-checked handler (with or without id param)."""
    from dazzle_back.specs.auth import AccessOperationKind

    _op_kind = getattr(AccessOperationKind, operation.upper())

    async def _cedar_impl(
        id: UUID | None,
        request: Request,
        auth_context: Any,
    ) -> Any:
        from dazzle_back.runtime.access_evaluator import AccessDecision, evaluate_permission
        from dazzle_back.runtime.audit_log import measure_evaluation_time

        # Pre-read for operations that need existing record for policy eval
        existing = None
        if needs_pre_read and id is not None:
            existing = await service.execute(operation="read", id=id)
            if existing is None:
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
            raise HTTPException(status_code=403, detail="Forbidden")

        current_user = str(user.id) if user else None
        raw_roles = list(getattr(user, "roles", [])) if user else []
        _is_su = ctx.is_superuser
        result = await core_fn(
            id,
            request,
            current_user=current_user,
            existing=existing,
            user_roles=raw_roles,
            is_superuser=_is_su,
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
    service: Any,
    auth_dep: Callable[..., Any],
    operation: str,
    entity_name: str,
    audit_logger: Any | None,
    include_field_changes: bool,
    needs_pre_read: bool,
    is_create: bool,
) -> Callable[..., Any]:
    """Build an authenticated handler (with or without id param)."""

    async def _auth_impl(
        id: UUID | None,
        request: Request,
        auth_context: Any,
    ) -> Any:
        user = auth_context.user
        current_user = str(user.id) if user else None

        # Pre-read for field-change diffs
        existing = None
        if needs_pre_read and include_field_changes and audit_logger and id is not None:
            existing = await service.execute(operation="read", id=id)

        raw_roles = list(getattr(user, "roles", [])) if user else []
        _is_su = getattr(user, "is_superuser", False) if user else False
        result = await core_fn(
            id,
            request,
            current_user=current_user,
            existing=existing,
            user_roles=raw_roles,
            is_superuser=_is_su,
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
    if is_create:

        async def _noauth_create(request: Request) -> Any:
            return await core_fn(None, request, current_user=None, existing=None)

        _set_handler_annotations(_noauth_create)
        return _noauth_create

    async def _noauth_with_id(id: UUID, request: Request) -> Any:
        return await core_fn(id, request, current_user=None, existing=None)

    _set_handler_annotations(_noauth_with_id, with_id=True)
    return _noauth_with_id


def create_list_handler(
    service: Any,
    _response_schema: type[BaseModel] | None = None,
    access_spec: dict[str, Any] | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
    require_auth_by_default: bool = False,
    select_fields: list[str] | None = None,
    json_projection: list[str] | None = None,
    auto_include: list[str] | None = None,
    htmx_columns: list[dict[str, Any]] | None = None,
    htmx_detail_url: str | None = None,
    htmx_entity_name: str = "Item",
    htmx_empty_message: str = "No items found.",
    cedar_access_spec: Any | None = None,
    audit_logger: Any | None = None,
    entity_name: str = "Item",
    search_fields: list[str] | None = None,
    filter_fields: list[str] | None = None,
    ref_targets: dict[str, str] | None = None,
    fk_graph: Any | None = None,
    graph_spec: tuple[Any, Any | None] | None = None,
    all_services: dict[str, Any] | None = None,
) -> Callable[..., Any]:
    """Create a handler for list operations with optional access control.

    Args:
        service: Service instance for data operations
        _response_schema: Response schema (unused, kept for compatibility)
        access_spec: Access control specification for this entity
        optional_auth_dep: FastAPI dependency for optional auth (returns AuthContext)
        require_auth_by_default: If True, require authentication when no access_spec is defined
        select_fields: Optional field projection for SQL queries
        json_projection: Optional field names to include in JSON API responses (#360)
        auto_include: Optional relation names to auto-eager-load (prevents N+1)
        htmx_columns: Column definitions for HTMX table row rendering
        htmx_detail_url: Detail URL template for row click navigation
        htmx_entity_name: Entity name for HTMX rendering context
        htmx_empty_message: Message when no items found
        audit_logger: Optional AuditLogger for recording list access decisions
        entity_name: Entity name for audit logging
        search_fields: Optional field names for LIKE-based search (#361)
        filter_fields: Allowed field names for bare query param filtering (#596)
    """

    def _inject_htmx_meta(request: Request) -> None:
        """Set HTMX rendering metadata on request.state for table row fragments."""
        if htmx_columns is not None:
            request.state.htmx_columns = htmx_columns
        if htmx_detail_url is not None:
            request.state.htmx_detail_url = htmx_detail_url
        request.state.htmx_entity_name = htmx_entity_name
        request.state.htmx_empty_message = htmx_empty_message

    if optional_auth_dep is not None:

        async def _auth_handler(
            request: Request,
            auth_context: AuthContext = Depends(optional_auth_dep),
            page: int = Query(1, ge=1, description="Page number"),
            page_size: int = Query(20, ge=1, le=100, description="Items per page"),
            sort: str | None = Query(None, description="Sort field"),
            dir: str = Query("asc", description="Sort direction (asc/desc)"),
            search: str | None = Query(None, description="Search query"),
            q: str | None = Query(None, description="Search query (alias for search)"),
        ) -> Any:
            is_authenticated = auth_context.is_authenticated
            user_id = str(auth_context.user.id) if auth_context.user else None

            # Deny-default: require authentication when enabled and no explicit access rules
            if require_auth_by_default and not access_spec and not is_authenticated:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required",
                )

            # Support ?q= as alias for ?search= (#596)
            effective_search = search or q

            _inject_htmx_meta(request)
            return await _list_handler_body(
                service,
                access_spec,
                is_authenticated,
                user_id,
                request,
                page,
                page_size,
                sort,
                dir,
                effective_search,
                select_fields=select_fields,
                json_projection=json_projection,
                auto_include=auto_include,
                cedar_access_spec=cedar_access_spec,
                auth_context=auth_context,
                audit_logger=audit_logger,
                entity_name=entity_name,
                user=auth_context.user if auth_context and auth_context.is_authenticated else None,
                search_fields=search_fields,
                filter_fields=filter_fields,
                ref_targets=ref_targets,
                fk_graph=fk_graph,
                graph_spec=graph_spec,
                all_services=all_services,
            )

        _auth_handler.__annotations__ = {
            "request": Request,
            "auth_context": AuthContext,
            "page": int,
            "page_size": int,
            "sort": str | None,
            "dir": str,
            "search": str | None,
            "q": str | None,
            "return": Any,
        }
        return _auth_handler

    async def _noauth_handler(
        request: Request,
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(20, ge=1, le=100, description="Items per page"),
        sort: str | None = Query(None, description="Sort field"),
        dir: str = Query("asc", description="Sort direction (asc/desc)"),
        search: str | None = Query(None, description="Search query"),
        q: str | None = Query(None, description="Search query (alias for search)"),
    ) -> Any:
        # Support ?q= as alias for ?search= (#596)
        effective_search = search or q

        _inject_htmx_meta(request)
        return await _list_handler_body(
            service,
            access_spec,
            False,
            None,
            request,
            page,
            page_size,
            sort,
            dir,
            effective_search,
            select_fields=select_fields,
            json_projection=json_projection,
            auto_include=auto_include,
            cedar_access_spec=cedar_access_spec,
            audit_logger=audit_logger,
            entity_name=entity_name,
            search_fields=search_fields,
            filter_fields=filter_fields,
            ref_targets=ref_targets,
            fk_graph=fk_graph,
            graph_spec=graph_spec,
            all_services=all_services,
        )

    _noauth_handler.__annotations__ = {
        "request": Request,
        "page": int,
        "page_size": int,
        "sort": str | None,
        "dir": str,
        "search": str | None,
        "q": str | None,
        "return": Any,
    }
    return _noauth_handler


def _resolve_scope_filters(
    cedar_access_spec: Any,
    operation: str,
    user_roles: set[str],
    user_id: str,
    auth_context: Any | None = None,
    ref_targets: dict[str, str] | None = None,
    *,
    entity_name: str = "",
    fk_graph: Any | None = None,
) -> dict[str, Any] | None:
    """Resolve scope rules to SQL filters for the user's matched role.

    When the matched scope rule carries a compiled ``predicate``
    (:class:`ScopePredicate`), the predicate compiler is used to produce a
    single ``(sql, params)`` tuple.  Marker objects in *params* are resolved
    to concrete values using the current user context.

    Returns:
        dict of SQL filters — if a scope rule matches with a field condition.
            May contain the special key ``__scope_predicate`` with a
            ``(sql, params)`` tuple when the predicate pipeline is active.
        {} (empty dict) — if scope is 'all' (no filter needed)
        None — if no scope rule matches (default-deny: empty result set)
    """
    import logging

    scopes = getattr(cedar_access_spec, "scopes", None)
    if not scopes:
        # No scope rules defined — pass through without row filtering (#607).
        # The permit gate already controls entity-level access. Entities that
        # need row-level isolation must add explicit scope: blocks.
        return {}

    op_val = operation if isinstance(operation, str) else operation.value

    # Collect ALL matching scope rules for the user's roles, not just the
    # first one (#604).  If any matching rule is unconditional (scope: all),
    # the user gets unrestricted access.  This handles dual-role users where
    # one role has a restrictive scope and another has scope: all.
    matched_rules: list[Any] = []
    for scope_rule in scopes:
        rule_op = getattr(scope_rule, "operation", None)
        if rule_op is None:
            continue
        rule_op_val = rule_op.value if hasattr(rule_op, "value") else str(rule_op)
        if rule_op_val != op_val:
            continue

        rule_personas = getattr(scope_rule, "personas", [])
        if "*" in rule_personas or (user_roles & set(rule_personas)):
            matched_rules.append(scope_rule)

    if not matched_rules:
        return None  # No scope rule matched — default-deny

    # If ANY matched rule is unconditional (scope: all), return no filter.
    # This is the most permissive outcome — a user with ANY role granting
    # scope: all sees everything, regardless of other roles' restrictions.
    for rule in matched_rules:
        condition = getattr(rule, "condition", None)
        predicate = getattr(rule, "predicate", None)
        # scope: all produces either predicate=None or predicate=Tautology()
        is_tautology = getattr(predicate, "kind", None) == "tautology"
        if (condition is None and predicate is None) or is_tautology:
            return {}  # scope: all — no filter

    # All matched rules have conditions — apply the first one that resolves.
    # TODO(#604): When multiple restrictive rules match, OR-combine them
    # so the user sees the union of rows visible under each role.
    for rule in matched_rules:
        condition = getattr(rule, "condition", None)
        predicate = getattr(rule, "predicate", None)

        # ---- Predicate-compiler path ----------------------------------------
        if predicate is not None and fk_graph is not None:
            try:
                return _resolve_predicate_filters(
                    predicate, entity_name, fk_graph, user_id, auth_context
                )
            except Exception:
                # Predicate compilation/resolution failed (e.g. null FK in
                # EXISTS binding) — deny cleanly rather than 500 (#617)
                logging.getLogger(__name__).warning(
                    "Scope predicate resolution failed for %s — denying",
                    entity_name,
                    exc_info=True,
                )
                return None

        # ---- Legacy condition-tree path (fallback) --------------------------
        if condition is not None:
            try:
                filters: dict[str, Any] = {}
                _extract_condition_filters(
                    condition,
                    user_id,
                    filters,
                    logging.getLogger(__name__),
                    auth_context,
                    ref_targets,
                )
                return filters
            except Exception:
                logging.getLogger(__name__).warning(
                    "Legacy scope condition resolution failed for %s — denying",
                    entity_name,
                    exc_info=True,
                )
                return None

    return {}  # Matched but no resolvable condition — treat as no filter


def _resolve_predicate_filters(
    predicate: Any,
    entity_name: str,
    fk_graph: Any,
    user_id: str,
    auth_context: Any | None,
) -> dict[str, Any]:
    """Compile a ScopePredicate to SQL and resolve runtime markers.

    Returns a filters dict with the special ``__scope_predicate`` key
    containing a ``(sql, params)`` tuple ready for the QueryBuilder.
    """
    from dazzle_back.runtime.predicate_compiler import (
        CurrentUserRef,
        UserAttrRef,
        compile_predicate,
    )

    sql, raw_params = compile_predicate(predicate, entity_name, fk_graph)

    if not sql:
        return {}  # Tautology — no filter needed

    # Resolve marker objects in params to concrete runtime values
    resolved_params: list[Any] = []
    for p in raw_params:
        if isinstance(p, CurrentUserRef):
            # Prefer DSL User entity ID over auth user ID (#546)
            resolved = _resolve_user_attribute("entity_id", auth_context)
            resolved_params.append(user_id if resolved == "__RBAC_DENY__" else resolved)
        elif isinstance(p, UserAttrRef):
            resolved = _resolve_user_attribute(p.attr_name, auth_context)
            if resolved == "__RBAC_DENY__":
                # Null FK — deny cleanly instead of passing sentinel to SQL (#580)
                return None  # type: ignore[return-value]
            resolved_params.append(resolved)
        else:
            resolved_params.append(p)

    return {"__scope_predicate": (sql, resolved_params)}


def _is_field_condition(condition: Any) -> bool:
    """Return True if condition requires record data to evaluate.

    Role checks need only the user's roles — evaluable at the gate without a record.
    Comparisons and grant checks reference entity fields — need record data.
    Logical nodes recurse: if either branch needs record data, the whole
    condition is a field condition.
    """
    if condition is None:
        return False
    kind = getattr(condition, "kind", None)
    if kind == "role_check":
        return False
    if kind in ("comparison", "grant_check", "via_check"):
        return True
    if kind == "logical":
        return _is_field_condition(getattr(condition, "logical_left", None)) or _is_field_condition(
            getattr(condition, "logical_right", None)
        )
    return False


async def _list_handler_body(
    service: Any,
    access_spec: dict[str, Any] | None,
    is_authenticated: bool,
    user_id: str | None,
    request: Any,
    page: int,
    page_size: int,
    sort: str | None,
    dir: str,
    search: str | None,
    select_fields: list[str] | None = None,
    json_projection: list[str] | None = None,
    auto_include: list[str] | None = None,
    cedar_access_spec: Any | None = None,
    auth_context: Any | None = None,
    audit_logger: Any | None = None,
    entity_name: str = "Item",
    user: Any | None = None,
    search_fields: list[str] | None = None,
    filter_fields: list[str] | None = None,
    ref_targets: dict[str, str] | None = None,
    fk_graph: Any | None = None,
    graph_spec: tuple[Any, Any | None] | None = None,
    all_services: dict[str, Any] | None = None,
) -> Any:
    """Shared list handler logic for both auth and no-auth paths."""
    from dazzle_back.runtime.condition_evaluator import (
        build_visibility_filter,
        filter_records_by_condition,
    )

    # Gate: Cedar LIST permission check (entity-level, before row filters).
    # Only enforced when ALL list rules are pure role checks. Rules with
    # field conditions (e.g. school = current_user.school) are row-level
    # filters that can't be evaluated without a record — those pass the gate
    # and are enforced at query time by scope predicates. (#502, #503)
    if cedar_access_spec and is_authenticated and auth_context:
        from dazzle_back.specs.auth import AccessOperationKind

        list_rules = [
            r for r in cedar_access_spec.permissions if r.operation == AccessOperationKind.LIST
        ]
        # Only gate when all list rules are pure role checks (no field conditions)
        has_field_conditions = any(_is_field_condition(r.condition) for r in list_rules)
        if list_rules and not has_field_conditions:
            from dazzle_back.runtime.access_evaluator import evaluate_permission

            _user, _ctx = _build_access_context(auth_context)
            decision = evaluate_permission(
                cedar_access_spec, AccessOperationKind.LIST, None, _ctx, entity_name=entity_name
            )
            if not decision.allowed:
                raise HTTPException(status_code=403, detail="Forbidden")

    # Build visibility filters
    sql_filters, post_filter = build_visibility_filter(access_spec, is_authenticated, user_id)

    # Apply scope filters (v0.44 — scope: blocks with predicate-compiled SQL).
    # When scopes list is non-empty, use _resolve_scope_filters which delegates
    # to the predicate compiler when predicates are available.
    if cedar_access_spec and is_authenticated and user_id:
        # Collect normalized user roles for scope matching
        _scope_user_roles: set[str] = set()
        if auth_context is not None:
            _scope_user_obj = getattr(auth_context, "user", None)
            if _scope_user_obj:
                for _r in getattr(_scope_user_obj, "roles", []):
                    _rname = _r if isinstance(_r, str) else getattr(_r, "name", str(_r))
                    _scope_user_roles.add(_normalize_role(_rname))

        _has_scopes = bool(getattr(cedar_access_spec, "scopes", None))
        if _has_scopes:
            scope_result = _resolve_scope_filters(
                cedar_access_spec,
                "list",
                _scope_user_roles,
                user_id,
                auth_context,
                ref_targets,
                entity_name=entity_name,
                fk_graph=fk_graph,
            )
            if scope_result is None:
                # No scope rule matched this role — default-deny at scope layer
                return {
                    "items": [],
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                }
            if scope_result:
                sql_filters = {**(sql_filters or {}), **scope_result}

    # Extract filter[field] params from query string
    filters: dict[str, Any] = {}
    # Reserved query param names that should never be treated as field filters
    _reserved_params = {"page", "page_size", "sort", "dir", "search", "q", "format"}
    for key, value in request.query_params.items():
        if key.startswith("filter[") and key.endswith("]") and value:
            filters[key[7:-1]] = value
        elif filter_fields and key in filter_fields and key not in _reserved_params and value:
            # Accept bare ?field=value when field is in the DSL-declared filter list (#596)
            filters[key] = value

    # Merge visibility filters with user filters
    merged_filters: dict[str, Any] | None = None
    if sql_filters or filters:
        merged_filters = {**(sql_filters or {}), **filters}

    # Build sort list for repository
    sort_list = [f"-{sort}" if dir == "desc" else sort] if sort else None

    # Execute list with filters, sort, and search
    result = await service.execute(
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

    # Audit log the list access
    if audit_logger:
        await _log_audit_decision(
            audit_logger,
            request,
            operation="list",
            entity_name=entity_name,
            entity_id=None,
            decision="allow",
            matched_policy="authenticated" if is_authenticated else "public",
            policy_effect="permit",
            user=user,
        )

    # Apply post-filtering if needed (for OR conditions)
    if post_filter and result and "items" in result:
        context = {"current_user_id": user_id}
        # Convert Pydantic models to dicts for filtering
        items = result["items"]
        if items and hasattr(items[0], "model_dump"):
            items = [item.model_dump() for item in items]
        filtered_items = filter_records_by_condition(items, post_filter, context)
        result["items"] = filtered_items
        result["total"] = len(filtered_items)

    # Graph format serialization (#619 Phase 2)
    format_param = request.query_params.get("format")
    if format_param and format_param != "raw":
        from starlette.responses import JSONResponse

        if format_param not in ("cytoscape", "d3"):
            return JSONResponse(
                {"detail": "Invalid format. Supported: cytoscape, d3, raw"},
                status_code=400,
            )
        if graph_spec is None:
            return JSONResponse(
                {"detail": f"Entity '{entity_name}' does not declare graph_edge:"},
                status_code=400,
            )

        from dazzle_back.runtime.graph_serializer import GraphSerializer

        graph_edge_spec, node_specs = graph_spec

        # Extract items as dicts
        items = result.get("items", []) if isinstance(result, dict) else []
        edge_dicts = []
        for item in items:
            if hasattr(item, "model_dump"):
                edge_dicts.append(item.model_dump(mode="json"))
            elif isinstance(item, dict):
                edge_dicts.append(item)

        # Collect node IDs grouped by target entity type
        node_ids_by_entity: dict[str, set[str]] = {}
        for edge in edge_dicts:
            for field_name in (graph_edge_spec.source, graph_edge_spec.target):
                ref_id = edge.get(field_name)
                if ref_id is None:
                    continue
                ref_entity = (ref_targets or {}).get(field_name, "")
                if ref_entity:
                    node_ids_by_entity.setdefault(ref_entity, set()).add(str(ref_id))

        # Batch-fetch nodes per entity type
        all_nodes: list[dict] = []
        for ref_entity_name, ids in node_ids_by_entity.items():
            node_service = (all_services or {}).get(ref_entity_name)
            if node_service is None:
                continue
            try:
                node_result = await node_service.execute(
                    operation="list",
                    page=1,
                    page_size=len(ids),
                    filters={"id__in": list(ids)},
                )
                node_items = node_result.get("items", []) if isinstance(node_result, dict) else []
                for ni in node_items:
                    if hasattr(ni, "model_dump"):
                        all_nodes.append(ni.model_dump(mode="json"))
                    elif isinstance(ni, dict):
                        all_nodes.append(ni)
            except Exception:
                pass  # Node fetch failure — edges returned, nodes omitted

        # Pick graph_node spec (first available for the serializer)
        gn_spec = next(iter(node_specs.values()), None) if node_specs else None
        serializer = GraphSerializer(graph_edge=graph_edge_spec, graph_node=gn_spec)

        if format_param == "cytoscape":
            return serializer.to_cytoscape(edge_dicts, all_nodes)
        else:
            return serializer.to_d3(edge_dicts, all_nodes)

    # Browser navigation: redirect to UI list page (#356)
    if _wants_html(request) and not _is_htmx_request(request):
        from starlette.responses import RedirectResponse

        _slug = entity_name.lower().replace("_", "-")
        redirect_url = f"/app/{_slug}"
        if request.query_params:
            redirect_url += f"?{request.url.query}"
        return RedirectResponse(url=redirect_url, status_code=302)

    # HTMX content negotiation: return HTML fragment for HX-Request
    if _is_htmx_request(request):
        try:
            from dazzle_back.runtime.htmx_response import HtmxDetails
            from dazzle_ui.runtime.template_renderer import render_fragment

            htmx = HtmxDetails.from_request(request)

            # Derive table_id from HX-Target (e.g. "dt-tasks-body" → "dt-tasks")
            table_id = "dt-table"
            if htmx.target and htmx.target.endswith("-body"):
                table_id = htmx.target.removesuffix("-body")

            items = result.get("items", []) if isinstance(result, dict) else []
            # Convert Pydantic models to dicts
            if items and hasattr(items[0], "model_dump"):
                items = [item.model_dump() for item in items]

            total = result.get("total", 0) if isinstance(result, dict) else 0
            table_dict = {
                "rows": items,
                "columns": request.state.htmx_columns
                if hasattr(request.state, "htmx_columns")
                else [],
                "detail_url_template": getattr(request.state, "htmx_detail_url", None),
                "entity_name": getattr(request.state, "htmx_entity_name", "Item"),
                "api_endpoint": str(request.url.path),
                "table_id": table_id,
                "sort_field": sort or "",
                "sort_dir": dir,
                "filter_values": filters,
                "page": page,
                "page_size": page_size,
                "total": total,
                "empty_message": getattr(request.state, "htmx_empty_message", "No items found."),
            }

            # Render table rows
            html = render_fragment("fragments/table_rows.html", table=table_dict)

            # Check if table uses infinite scroll mode
            pagination_mode = getattr(request.state, "htmx_pagination_mode", "pages")

            if pagination_mode == "infinite":
                # Append sentinel row for infinite scroll (triggers on revealed)
                sentinel_html = render_fragment("fragments/table_sentinel.html", table=table_dict)
                html += sentinel_html
            else:
                # Append OOB pagination so buttons stay in sync after
                # sort/filter/search/page changes
                pagination_html = render_fragment(
                    "fragments/table_pagination.html", table=table_dict
                )
                html += (
                    f'<div id="{table_id}-pagination" hx-swap-oob="true">{pagination_html}</div>'
                )

            return HTMLResponse(content=html)
        except ImportError:
            pass  # Template renderer not available, fall through to JSON
        except Exception:
            import logging as _logging

            _logging.getLogger("dazzle.runtime").exception(
                "HTMX fragment render failed for %s", entity_name
            )
            # Return an error row so the skeleton resolves with a visible message
            # instead of hanging indefinitely (#496).
            return HTMLResponse(
                content=(
                    '<tr><td colspan="99" class="text-center py-8 text-error">'
                    "Something went wrong loading this list.</td></tr>"
                ),
                status_code=200,
            )

    # Apply field projection to JSON responses (#360)
    if json_projection and result and isinstance(result, dict) and "items" in result:
        allowed = set(json_projection)
        projected_items = []
        for item in result["items"]:
            if hasattr(item, "model_dump"):
                d = item.model_dump(mode="json")
            elif isinstance(item, dict):
                d = item
            else:
                projected_items.append(item)
                continue
            projected_items.append({k: v for k, v in d.items() if k in allowed})
        result = {**result, "items": projected_items}

    return result


def _render_detail_html(request: Any, result: Any, entity_name: str) -> Any:
    """Render a detail view for HTMX or browser requests.

    - HTMX request → bare HTML fragment (for partial swap)
    - Direct browser navigation → full page with app shell (#349)
    - API client (JSON) → None (let FastAPI serialize)
    """
    if not _wants_html(request):
        return None
    try:
        from dazzle_ui.runtime.template_renderer import render_fragment

        # Convert Pydantic model to dict
        if hasattr(result, "model_dump"):
            item = result.model_dump(mode="json")
        elif isinstance(result, dict):
            from fastapi.encoders import jsonable_encoder

            item = jsonable_encoder(result)
        else:
            return None

        fragment_html = render_fragment(
            "fragments/detail_fields.html",
            item=item,
            entity_name=entity_name,
        )

        if _is_htmx_request(request):
            # HTMX partial swap: return bare fragment
            return HTMLResponse(content=fragment_html)

        # Direct browser navigation: wrap fragment in a full page (#349)
        from dazzle_ui.runtime.template_renderer import get_jinja_env

        env = get_jinja_env()
        wrapper_source = (  # noqa: UP031
            "{%% extends 'layouts/single_column.html' %%}{%% block content %%}%s{%% endblock %%}"
        ) % fragment_html
        full_html = env.from_string(wrapper_source).render(
            page_title=f"{entity_name} Detail",
        )
        return HTMLResponse(content=full_html)
    except ImportError:
        return None  # Template renderer not available
    except Exception:
        return None  # Fragment not found or render error


def create_read_handler(
    service: Any,
    _response_schema: type[BaseModel] | None = None,
    auth_dep: Callable[..., Any] | None = None,
    require_auth_by_default: bool = False,
    entity_name: str = "Item",
    audit_logger: Any | None = None,
    cedar_access_spec: Any | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
    auto_include: list[str] | None = None,
) -> Callable[..., Any]:
    """Create a handler for read operations with optional Cedar-style access control."""

    async def _core(
        id: UUID,
        request: Request,
        *,
        current_user: str | None = None,
        existing: Any = None,
        **_extra: Any,
    ) -> Any:
        result = await service.execute(operation="read", id=id, include=auto_include)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        html = _render_detail_html(request, result, entity_name)
        return html if html is not None else result

    # READ is special: Cedar needs the *fetched* record for policy eval, but
    # the core already does the fetch.  The generic wrapper's pre-read would
    # double-fetch.  So for Cedar-READ we inline a lightweight wrapper that
    # fetches once, evaluates, then returns.
    _use_cedar = cedar_access_spec is not None and optional_auth_dep is not None
    if _use_cedar:

        async def _read_cedar(
            id: UUID, request: Request, auth_context: AuthContext = Depends(optional_auth_dep)
        ) -> Any:
            from dazzle_back.runtime.access_evaluator import AccessDecision, evaluate_permission
            from dazzle_back.runtime.audit_log import measure_evaluation_time
            from dazzle_back.specs.auth import AccessOperationKind

            result = await service.execute(operation="read", id=id, include=auto_include)
            if result is None:
                raise HTTPException(status_code=404, detail="Not found")

            user, ctx = _build_access_context(auth_context)
            assert cedar_access_spec is not None
            decision: AccessDecision
            decision, eval_us = measure_evaluation_time(
                lambda: evaluate_permission(
                    cedar_access_spec,
                    AccessOperationKind.READ,
                    _record_to_dict(result),
                    ctx,
                    entity_name=entity_name,
                )
            )

            if audit_logger:
                await _log_audit_decision(
                    audit_logger,
                    request,
                    operation="read",
                    entity_name=entity_name,
                    entity_id=str(id),
                    decision="allow" if decision.allowed else "deny",
                    matched_policy=decision.matched_policy,
                    policy_effect=decision.effect,
                    user=user,
                    evaluation_time_us=eval_us,
                )

            if not decision.allowed:
                raise HTTPException(status_code=404, detail="Not found")
            html = _render_detail_html(request, result, entity_name)
            return html if html is not None else result

        _set_handler_annotations(_read_cedar, with_id=True, with_auth=True)
        return _read_cedar

    # Non-cedar: use the generic wrapper (no pre-read needed)
    return _wrap_with_auth(
        _core,
        service=service,
        cedar_access_spec=None,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        require_auth_by_default=require_auth_by_default,
        operation="read",
        entity_name=entity_name,
        audit_logger=audit_logger,
    )


def _extract_result_id(result: Any) -> str | None:
    """Extract the id from a create result (Pydantic model or dict)."""
    if hasattr(result, "id"):
        return str(result.id)
    if isinstance(result, dict) and "id" in result:
        return str(result["id"])
    return None


def create_create_handler(
    service: Any,
    input_schema: type[BaseModel],
    _response_schema: type[BaseModel] | None = None,
    auth_dep: Callable[..., Any] | None = None,
    require_auth_by_default: bool = False,
    entity_name: str = "Item",
    entity_slug: str = "",
    audit_logger: Any | None = None,
    cedar_access_spec: Any | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Create a handler for create operations with optional Cedar-style access control."""

    def _build_redirect_url(result: Any) -> str | None:
        if not entity_slug:
            return None
        result_id = _extract_result_id(result)
        if result_id:
            return f"/app/{entity_slug}/{result_id}"
        return None

    async def _core(
        _id: Any,
        request: Request,
        *,
        current_user: str | None = None,
        existing: Any = None,
        **_extra: Any,
    ) -> Any:
        body = await _parse_request_body(request)
        data = input_schema.model_validate(body)
        result = await service.execute(operation="create", data=data)
        return _with_htmx_triggers(
            request, result, entity_name, "created", redirect_url=_build_redirect_url(result)
        )

    return _wrap_with_auth(
        _core,
        service=service,
        cedar_access_spec=cedar_access_spec,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        require_auth_by_default=require_auth_by_default,
        operation="create",
        entity_name=entity_name,
        audit_logger=audit_logger,
    )


def create_update_handler(
    service: Any,
    input_schema: type[BaseModel],
    _response_schema: type[BaseModel] | None = None,
    auth_dep: Callable[..., Any] | None = None,
    require_auth_by_default: bool = False,
    entity_name: str = "Item",
    audit_logger: Any | None = None,
    cedar_access_spec: Any | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
    include_field_changes: bool = False,
) -> Callable[..., Any]:
    """Create a handler for update operations with optional Cedar-style access control."""

    async def _core(
        id: UUID,
        request: Request,
        *,
        current_user: str | None = None,
        existing: Any = None,
        user_roles: list[str] | None = None,
        is_superuser: bool = False,
    ) -> Any:
        body = await _parse_request_body(request)
        data = input_schema.model_validate(body)
        kwargs: dict[str, Any] = {"operation": "update", "id": id, "data": data}
        if current_user is not None:
            kwargs["current_user"] = current_user
        if user_roles is not None:
            kwargs["user_roles"] = user_roles
        kwargs["is_superuser"] = is_superuser
        result = await service.execute(**kwargs)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return _with_htmx_triggers(
            request, result, entity_name, "updated", redirect_url=_htmx_current_url(request)
        )

    return _wrap_with_auth(
        _core,
        service=service,
        cedar_access_spec=cedar_access_spec,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        require_auth_by_default=require_auth_by_default,
        operation="update",
        entity_name=entity_name,
        audit_logger=audit_logger,
        include_field_changes=include_field_changes,
        needs_pre_read=True,
    )


def create_delete_handler(
    service: Any,
    auth_dep: Callable[..., Any] | None = None,
    require_auth_by_default: bool = False,
    entity_name: str = "Item",
    audit_logger: Any | None = None,
    cedar_access_spec: Any | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
    include_field_changes: bool = False,
) -> Callable[..., Any]:
    """Create a handler for delete operations with optional Cedar-style access control."""

    async def _core(
        id: UUID,
        request: Request,
        *,
        current_user: str | None = None,
        existing: Any = None,
        **_extra: Any,
    ) -> Any:
        result = await service.execute(operation="delete", id=id)
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        return _with_htmx_triggers(
            request,
            {"deleted": True},
            entity_name,
            "deleted",
            redirect_url=_htmx_parent_url(request),
        )

    return _wrap_with_auth(
        _core,
        service=service,
        cedar_access_spec=cedar_access_spec,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        require_auth_by_default=require_auth_by_default,
        operation="delete",
        entity_name=entity_name,
        audit_logger=audit_logger,
        include_field_changes=include_field_changes,
        needs_pre_read=True,
    )


def create_custom_handler(
    service: Any,
    input_schema: type[BaseModel] | None = None,
) -> Callable[..., Any]:
    """Create a handler for custom operations."""
    if input_schema:

        async def handler_with_input(request: Request) -> Any:
            body = await request.json()
            data = input_schema.model_validate(body)
            result = await service.execute(**data.model_dump())
            return result

        # Override annotations with the proper type so FastAPI recognizes it
        _set_handler_annotations(handler_with_input)

        return handler_with_input
    else:

        async def handler_no_input() -> Any:
            result = await service.execute()
            return result

        return handler_no_input


# =============================================================================
# Graph helpers (#619 Phase 3–4)
# =============================================================================


def _check_networkx() -> bool:
    """Return True if NetworkX is available."""
    try:
        import networkx  # noqa: F401

        return True
    except ImportError:
        return False


def _extract_domain_filters(request: Any, filter_fields: list[str] | None) -> dict[str, Any]:
    """Extract domain-scope filters from query params for graph algorithms."""
    filters: dict[str, Any] = {}
    if not filter_fields:
        return filters
    reserved = {
        "format",
        "to",
        "weighted",
        "depth",
        "page",
        "page_size",
        "sort",
        "dir",
        "search",
        "q",
    }
    for key, value in request.query_params.items():
        if key in filter_fields and key not in reserved and value:
            filters[key] = value
        elif key.startswith("filter[") and key.endswith("]"):
            field = key[7:-1]
            if field in filter_fields and value:
                filters[field] = value
    return filters


async def _materialize_graph(
    db_manager: Any,
    node_table: str,
    edge_table: str,
    graph_edge_spec: Any,
    filters: dict[str, Any] | None = None,
) -> tuple[Any, list[dict], list[dict]]:
    """Load nodes + edges from DB and build a NetworkX graph.

    Returns (nx_graph, node_dicts, edge_dicts).
    """
    from dazzle_back.runtime.graph_materializer import GraphMaterializer
    from dazzle_back.runtime.query_builder import quote_identifier

    filter_sql = ""
    filter_params: dict[str, Any] = {}
    if filters:
        clauses = []
        for i, (key, value) in enumerate(filters.items()):
            param_name = f"filter_{i}"
            clauses.append(f"{quote_identifier(key)} = %({param_name})s")
            filter_params[param_name] = value
        filter_sql = " WHERE " + " AND ".join(clauses)

    src = graph_edge_spec.source
    tgt = graph_edge_spec.target

    # Table names are DSL-derived identifiers (not user input), but we
    # quote them properly via quote_identifier for defense-in-depth.
    edge_tbl = quote_identifier(edge_table)
    node_tbl = quote_identifier(node_table)

    with db_manager.connection() as conn:
        cursor = conn.cursor()

        edge_sql = f"SELECT * FROM {edge_tbl}{filter_sql}"  # nosemgrep
        cursor.execute(edge_sql, filter_params)
        edges = cursor.fetchall()

        node_ids: set[str] = set()
        for edge in edges:
            if edge.get(src):
                node_ids.add(str(edge[src]))
            if edge.get(tgt):
                node_ids.add(str(edge[tgt]))

        nodes: list[dict[str, Any]] = []
        if node_ids:
            node_sql = f'SELECT * FROM {node_tbl} WHERE "id" IN %(node_ids)s'  # nosemgrep
            cursor.execute(node_sql, {"node_ids": tuple(node_ids)})
            nodes = cursor.fetchall()

    def _stringify(rows: list) -> list[dict]:  # type: ignore[type-arg]
        result = []
        for row in rows:
            out = {}
            for k, v in row.items():
                out[k] = str(v) if hasattr(v, "hex") else v
            result.append(out)
        return result

    str_nodes = _stringify(nodes)
    str_edges = _stringify(edges)
    materializer = GraphMaterializer(graph_edge=graph_edge_spec)
    return materializer.build(str_nodes, str_edges), str_nodes, str_edges


_VALID_GRAPH_FORMATS = {"cytoscape", "d3", "raw"}


async def _neighborhood_handler_body(
    seed_id: UUID,
    depth: int,
    format: str,
    entity_name: str,
    graph_edge_spec: Any,
    graph_node_spec: Any | None,
    node_table: str,
    edge_table: str,
    db_manager: Any,
    node_service: Any,
) -> Any:
    """Core logic for the neighborhood graph endpoint."""
    from starlette.responses import JSONResponse

    from dazzle_back.runtime.graph_serializer import GraphSerializer
    from dazzle_back.runtime.neighborhood import NeighborhoodQueryBuilder

    # 1. Validate format
    if format not in _VALID_GRAPH_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid format '{format}'. Must be one of: {', '.join(sorted(_VALID_GRAPH_FORMATS))}",
        )

    # 2. Check seed node exists
    seed_record = await node_service.execute(operation="read", id=seed_id)
    if seed_record is None:
        raise HTTPException(status_code=404, detail=f"{entity_name} not found")

    # 3. Build CTE
    builder = NeighborhoodQueryBuilder(
        node_table=node_table,
        edge_table=edge_table,
        graph_edge=graph_edge_spec,
    )
    cte_sql, cte_params = builder.cte_query(str(seed_id), depth)

    # 4. Execute: CTE → node fetch → edge fetch
    with db_manager.connection() as conn:
        cursor = conn.cursor()

        # Discover reachable node IDs
        cursor.execute(cte_sql, cte_params)
        cte_rows = cursor.fetchall()
        node_ids = [str(row["node_id"]) for row in cte_rows]

        if not node_ids:
            # Seed exists but has no connections — return it alone
            node_ids = [str(seed_id)]

        # Fetch full node records
        node_sql, node_params = builder.node_fetch_query(node_ids)
        cursor.execute(node_sql, node_params)
        nodes = cursor.fetchall()

        # Fetch edges between discovered nodes
        edge_sql, edge_params = builder.edge_fetch_query(node_ids)
        cursor.execute(edge_sql, edge_params)
        edges = cursor.fetchall()

    # 5. Serialize UUIDs to strings
    def _stringify_uuids(rows: list[dict]) -> list[dict]:
        result = []
        for row in rows:
            out = {}
            for k, v in row.items():
                out[k] = str(v) if isinstance(v, UUID) else v
            result.append(out)
        return result

    nodes = _stringify_uuids(nodes)
    edges = _stringify_uuids(edges)

    # 6. Return via GraphSerializer or raw
    if format == "raw":
        return JSONResponse(content={"nodes": nodes, "edges": edges})

    serializer = GraphSerializer(
        graph_edge=graph_edge_spec,
        graph_node=graph_node_spec,
    )
    if format == "cytoscape":
        return JSONResponse(content=serializer.to_cytoscape(edges, nodes))
    else:
        return JSONResponse(content=serializer.to_d3(edges, nodes))


def create_neighborhood_handler(
    entity_name: str,
    graph_edge_spec: Any,
    graph_node_spec: Any | None,
    node_table: str,
    edge_table: str,
    db_manager: Any,
    node_service: Any,
    optional_auth_dep: Callable[..., Any] | None = None,
    cedar_access_spec: Any | None = None,
    fk_graph: Any | None = None,
    ref_targets: dict[str, str] | None = None,
) -> Callable[..., Any]:
    """Create a handler for graph neighborhood traversal (#619 Phase 3).

    Returns reachable nodes and edges from a seed node up to a given depth.
    """
    if optional_auth_dep is not None:

        async def _auth_handler(
            id: UUID,
            auth_context: AuthContext = Depends(optional_auth_dep),
            depth: int = Query(1, ge=1, le=3, description="Traversal depth"),
            format: str = Query("cytoscape", description="Response format: cytoscape, d3, or raw"),
        ) -> Any:
            return await _neighborhood_handler_body(
                seed_id=id,
                depth=depth,
                format=format,
                entity_name=entity_name,
                graph_edge_spec=graph_edge_spec,
                graph_node_spec=graph_node_spec,
                node_table=node_table,
                edge_table=edge_table,
                db_manager=db_manager,
                node_service=node_service,
            )

        _auth_handler.__annotations__ = {
            "id": UUID,
            "auth_context": AuthContext,
            "depth": int,
            "format": str,
            "return": Any,
        }
        return _auth_handler

    async def _noauth_handler(
        id: UUID,
        depth: int = Query(1, ge=1, le=3, description="Traversal depth"),
        format: str = Query("cytoscape", description="Response format: cytoscape, d3, or raw"),
    ) -> Any:
        return await _neighborhood_handler_body(
            seed_id=id,
            depth=depth,
            format=format,
            entity_name=entity_name,
            graph_edge_spec=graph_edge_spec,
            graph_node_spec=graph_node_spec,
            node_table=node_table,
            edge_table=edge_table,
            db_manager=db_manager,
            node_service=node_service,
        )

    _noauth_handler.__annotations__ = {
        "id": UUID,
        "depth": int,
        "format": str,
        "return": Any,
    }
    return _noauth_handler


# =============================================================================
# Algorithm endpoint handlers (#619 Phase 4)
# =============================================================================


def create_shortest_path_handler(
    entity_name: str,
    graph_edge_spec: Any,
    graph_node_spec: Any | None,
    node_table: str,
    edge_table: str,
    db_manager: Any,
    filter_fields: list[str] | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Create handler for GET /{entity}/{id}/graph/shortest-path?to={target_id}."""

    async def _handler(
        request: Request,
        id: UUID,
        to: UUID = Query(..., description="Target node ID"),
        format: str = Query("cytoscape", description="Response format"),
        weighted: bool = Query(False, description="Use edge weights"),
    ) -> Any:
        from starlette.responses import JSONResponse

        from dazzle_back.runtime.graph_algorithms import shortest_path
        from dazzle_back.runtime.graph_serializer import GraphSerializer

        if format not in _VALID_GRAPH_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid format. Supported: {', '.join(sorted(_VALID_GRAPH_FORMATS))}",
            )

        filters = _extract_domain_filters(request, filter_fields)
        g, all_nodes, all_edges = await _materialize_graph(
            db_manager,
            node_table,
            edge_table,
            graph_edge_spec,
            filters,
        )

        result = shortest_path(g, source=str(id), target=str(to), weighted=weighted)

        if format == "raw":
            return JSONResponse(content=result)

        path_ids = set(result.get("path", []))
        serializer = GraphSerializer(graph_edge=graph_edge_spec, graph_node=graph_node_spec)

        if not path_ids:
            empty = (
                serializer.to_cytoscape([], [])
                if format == "cytoscape"
                else serializer.to_d3([], [])
            )
            empty["shortest_path"] = result
            return JSONResponse(content=empty)

        path_nodes = [n for n in all_nodes if str(n.get("id")) in path_ids]
        path_edges = [
            e
            for e in all_edges
            if str(e.get(graph_edge_spec.source)) in path_ids
            and str(e.get(graph_edge_spec.target)) in path_ids
        ]

        if format == "cytoscape":
            out = serializer.to_cytoscape(path_edges, path_nodes)
        else:
            out = serializer.to_d3(path_edges, path_nodes)
        out["shortest_path"] = result
        return JSONResponse(content=out)

    _handler.__name__ = f"shortest_path_{entity_name.lower()}"
    return _handler


def create_components_handler(
    entity_name: str,
    graph_edge_spec: Any,
    graph_node_spec: Any | None,
    node_table: str,
    edge_table: str,
    db_manager: Any,
    filter_fields: list[str] | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Create handler for GET /{entity}/graph/components."""

    async def _handler(
        request: Request,
        format: str = Query("raw", description="Response format"),
    ) -> Any:
        from starlette.responses import JSONResponse

        from dazzle_back.runtime.graph_algorithms import connected_components
        from dazzle_back.runtime.graph_serializer import GraphSerializer

        if format not in _VALID_GRAPH_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid format. Supported: {', '.join(sorted(_VALID_GRAPH_FORMATS))}",
            )

        filters = _extract_domain_filters(request, filter_fields)
        g, all_nodes, all_edges = await _materialize_graph(
            db_manager,
            node_table,
            edge_table,
            graph_edge_spec,
            filters,
        )

        result = connected_components(g)

        if format == "raw":
            return JSONResponse(content=result)

        serializer = GraphSerializer(graph_edge=graph_edge_spec, graph_node=graph_node_spec)
        if format == "cytoscape":
            out = serializer.to_cytoscape(all_edges, all_nodes)
        else:
            out = serializer.to_d3(all_edges, all_nodes)
        out["components"] = result
        return JSONResponse(content=out)

    _handler.__name__ = f"components_{entity_name.lower()}"
    return _handler


# =============================================================================
# Route Generator
# =============================================================================


class RouteGenerator:
    """
    Generates FastAPI routes from endpoint specifications.

    Creates routes with appropriate HTTP methods, paths, and handlers.
    """

    def __init__(
        self,
        services: dict[str, Any],
        models: dict[str, type[BaseModel]],
        schemas: dict[str, dict[str, type[BaseModel]]] | None = None,
        entity_access_specs: dict[str, dict[str, Any]] | None = None,
        auth_dep: Callable[..., Any] | None = None,
        optional_auth_dep: Callable[..., Any] | None = None,
        require_auth_by_default: bool = False,
        auth_store: Any | None = None,
        audit_logger: Any | None = None,
        cedar_access_specs: dict[str, Any] | None = None,
        entity_list_projections: dict[str, list[str]] | None = None,
        entity_search_fields: dict[str, list[str]] | None = None,
        entity_filter_fields: dict[str, list[str]] | None = None,
        entity_auto_includes: dict[str, list[str]] | None = None,
        entity_htmx_meta: dict[str, dict[str, Any]] | None = None,
        entity_audit_configs: dict[str, Any] | None = None,
        entity_ref_targets: dict[str, dict[str, str]] | None = None,
        fk_graph: Any | None = None,
        entity_graph_specs: dict[str, tuple[Any, Any | None]] | None = None,
        node_graph_specs: dict[str, dict] | None = None,
        db_manager: Any | None = None,
    ):
        """
        Initialize the route generator.

        Args:
            services: Dictionary mapping service names to service instances
            models: Dictionary mapping entity names to Pydantic models
            schemas: Optional dictionary with create/update schemas per entity
            entity_access_specs: Optional dictionary mapping entity names to access specs
            auth_dep: FastAPI dependency that requires authentication (raises 401)
            optional_auth_dep: FastAPI dependency for optional auth (returns empty AuthContext)
            require_auth_by_default: If True, require auth for all routes when no access spec
            auth_store: AuthStore instance for creating per-route role-based dependencies
            audit_logger: Optional AuditLogger for recording access decisions
            cedar_access_specs: Optional dict of entity_name -> EntityAccessSpec for Cedar evaluation
            entity_list_projections: Optional dict mapping entity names to projected field lists
            entity_auto_includes: Optional dict mapping entity names to auto-eager-loaded relations
            entity_htmx_meta: Optional dict mapping entity names to HTMX rendering metadata
            entity_audit_configs: Optional dict of entity_name -> AuditConfig for per-entity filtering
            entity_ref_targets: Optional dict mapping entity_name -> {fk_field: target_entity} for
                dotted-path scope resolution (#556)
            fk_graph: Optional FKGraph from the linked AppSpec for predicate compilation
            node_graph_specs: Optional dict mapping node entity names to graph metadata (#619)
            db_manager: Optional database manager for neighborhood queries (#619)
        """
        if not FASTAPI_AVAILABLE:
            raise RuntimeError("FastAPI is not installed. Install with: pip install fastapi")

        self.services = services
        self.models = models
        self.schemas = schemas or {}
        self.entity_access_specs = entity_access_specs or {}
        self.auth_dep = auth_dep
        self.optional_auth_dep = optional_auth_dep
        self.require_auth_by_default = require_auth_by_default
        self.auth_store = auth_store
        self.audit_logger = audit_logger
        self.cedar_access_specs = cedar_access_specs or {}
        self.entity_list_projections = entity_list_projections or {}
        self.entity_search_fields = entity_search_fields or {}
        self.entity_filter_fields = entity_filter_fields or {}
        self.entity_auto_includes = entity_auto_includes or {}
        self.entity_htmx_meta = entity_htmx_meta or {}
        self.entity_audit_configs = entity_audit_configs or {}
        self.entity_ref_targets = entity_ref_targets or {}
        self.fk_graph = fk_graph
        self.entity_graph_specs = entity_graph_specs or {}
        self.node_graph_specs = node_graph_specs or {}
        self.db_manager = db_manager
        self._router = _APIRouter()

    def generate_route(
        self,
        endpoint: EndpointSpec,
        service_spec: ServiceSpec | None = None,
    ) -> None:
        """
        Generate a single route from an endpoint specification.

        Args:
            endpoint: Endpoint specification
            service_spec: Optional service specification for type hints
        """
        service = self.services.get(endpoint.service)
        if not service:
            raise ValueError(f"Service not found: {endpoint.service}")

        # Determine entity name for schemas
        entity_name = None
        is_crud_service = False

        if service_spec:
            entity_name = service_spec.domain_operation.entity
            is_crud_service = service_spec.is_crud

        # Get schemas for the entity
        entity_schemas = self.schemas.get(entity_name or "", {})
        model = self.models.get(entity_name or "")

        # For CRUD services, determine operation from HTTP method
        # For non-CRUD services, use the service's domain_operation.kind
        operation_kind = None
        if service_spec and not is_crud_service:
            operation_kind = service_spec.domain_operation.kind

        # Create appropriate handler based on HTTP method (primary) or operation kind (secondary)
        handler: Callable[..., Any]

        # Derive entity slug for post-create redirect
        _entity_slug = (entity_name or "").lower().replace("_", "-")

        # Resolve audit logger and Cedar access spec for this entity
        _cedar_spec = self.cedar_access_specs.get(entity_name or "")
        _audit_config = self.entity_audit_configs.get(entity_name or "")
        # Per-entity audit gate: if entity has an AuditConfig, respect its
        # `enabled` flag. Entities with Cedar access specs always get audit
        # logging (access-decision logging). Entities with no audit config
        # and no Cedar spec get no logging.
        _audit_enabled = False
        if _audit_config and getattr(_audit_config, "enabled", False):
            _audit_enabled = True
        elif _cedar_spec is not None:
            # Cedar entities always log access decisions
            _audit_enabled = True
        _audit = self.audit_logger if _audit_enabled else None
        # Pre-compute which operations this entity wants audited (empty = all)
        _audit_ops: set[str] = set()
        if _audit_config and getattr(_audit_config, "operations", None):
            _audit_ops = {str(op) for op in _audit_config.operations}
        # Check whether to capture field-level diffs for update/delete
        _include_fc = bool(_audit_config and getattr(_audit_config, "include_field_changes", False))

        def _audit_for(op: str) -> Any:
            """Return the audit logger if this operation should be audited."""
            if _audit is None:
                return None
            if _audit_ops and op not in _audit_ops:
                return None
            return _audit

        # POST -> CREATE
        if endpoint.method == HttpMethod.POST or operation_kind == OperationKind.CREATE:
            create_schema = entity_schemas.get("create", model)
            if create_schema:
                handler = create_create_handler(
                    service,
                    create_schema,
                    model,
                    auth_dep=self.auth_dep,
                    require_auth_by_default=self.require_auth_by_default,
                    entity_name=entity_name or "Item",
                    entity_slug=_entity_slug,
                    audit_logger=_audit_for("create"),
                    cedar_access_spec=_cedar_spec,
                    optional_auth_dep=self.optional_auth_dep,
                )
                self._add_route(endpoint, handler, response_model=model)
            else:
                raise ValueError(f"No create schema for endpoint: {endpoint.name}")

        # GET with {id} -> READ
        elif (
            endpoint.method == HttpMethod.GET and "{id}" in endpoint.path
        ) or operation_kind == OperationKind.READ:
            includes = self.entity_auto_includes.get(entity_name or "")
            handler = create_read_handler(
                service,
                model,
                auth_dep=self.auth_dep,
                require_auth_by_default=self.require_auth_by_default,
                entity_name=entity_name or "Item",
                audit_logger=_audit_for("read"),
                cedar_access_spec=_cedar_spec,
                optional_auth_dep=self.optional_auth_dep,
                auto_include=includes,
            )
            self._add_route(endpoint, handler, response_model=None)

        # GET without {id} -> LIST
        elif (
            endpoint.method == HttpMethod.GET and "{id}" not in endpoint.path
        ) or operation_kind == OperationKind.LIST:
            # Get access spec for this entity
            access_spec = self.entity_access_specs.get(entity_name or "")
            # Get field projection for this entity (from view-backed list surfaces)
            projection = self.entity_list_projections.get(entity_name or "")
            # Get search fields for this entity (from surface config)
            _search_fields = self.entity_search_fields.get(entity_name or "")
            # Get filter fields for this entity (from surface UX config)
            _filter_fields = self.entity_filter_fields.get(entity_name or "")
            # Get auto-include refs for this entity (prevents N+1 queries)
            includes = self.entity_auto_includes.get(entity_name or "")
            # Get HTMX rendering metadata (columns, detail URL, etc.)
            _htmx = self.entity_htmx_meta.get(entity_name or "", {})
            # Get graph metadata for edge entities (#619 Phase 2)
            _graph_spec = self.entity_graph_specs.get(entity_name or "")
            handler = create_list_handler(
                service,
                model,
                access_spec=access_spec,
                optional_auth_dep=self.optional_auth_dep,
                require_auth_by_default=self.require_auth_by_default,
                select_fields=projection,
                json_projection=projection,
                auto_include=includes,
                htmx_columns=_htmx.get("columns"),
                htmx_detail_url=_htmx.get("detail_url"),
                htmx_entity_name=_htmx.get("entity_name", entity_name or "Item"),
                htmx_empty_message=_htmx.get("empty_message", "No items found."),
                cedar_access_spec=_cedar_spec,
                audit_logger=_audit_for("list"),
                entity_name=entity_name or "Item",
                search_fields=_search_fields,
                filter_fields=_filter_fields,
                ref_targets=self.entity_ref_targets.get(entity_name or ""),
                fk_graph=self.fk_graph,
                graph_spec=_graph_spec,
                all_services=self.services,
            )
            self._add_route(endpoint, handler, response_model=None)

            # Register /graph neighborhood endpoint for graph_node entities (#619)
            _node_graph = self.node_graph_specs.get(entity_name or "")
            if _node_graph:
                _graph_path = endpoint.path.rstrip("/") + "/{id}/graph"
                _graph_handler = create_neighborhood_handler(
                    entity_name=entity_name or "Item",
                    graph_edge_spec=_node_graph["graph_edge"],
                    graph_node_spec=_node_graph.get("graph_node"),
                    node_table=_node_graph["node_table"],
                    edge_table=_node_graph["edge_table"],
                    db_manager=self.db_manager,
                    node_service=service,
                    optional_auth_dep=self.optional_auth_dep,
                    cedar_access_spec=_cedar_spec,
                    fk_graph=self.fk_graph,
                    ref_targets=self.entity_ref_targets.get(entity_name or ""),
                )
                self._router.add_api_route(
                    _graph_path,
                    _graph_handler,
                    methods=["GET"],
                    tags=[entity_name or "Item"],
                    summary=f"Neighborhood graph for {entity_name}",
                )

            # Register algorithm endpoints for graph_node entities (#619 Phase 4)
            if _node_graph and _check_networkx():
                _alg_filter_fields = self.entity_filter_fields.get(entity_name or "")

                # Shortest path: /{entity}/{id}/graph/shortest-path
                _sp_path = endpoint.path.rstrip("/") + "/{id}/graph/shortest-path"
                _sp_handler = create_shortest_path_handler(
                    entity_name=entity_name or "Item",
                    graph_edge_spec=_node_graph["graph_edge"],
                    graph_node_spec=_node_graph.get("graph_node"),
                    node_table=_node_graph["node_table"],
                    edge_table=_node_graph["edge_table"],
                    db_manager=self.db_manager,
                    filter_fields=_alg_filter_fields,
                    optional_auth_dep=self.optional_auth_dep,
                )
                self._router.add_api_route(
                    _sp_path,
                    _sp_handler,
                    methods=["GET"],
                    tags=[entity_name or "Item"],
                    summary=f"Shortest path for {entity_name}",
                )

                # Connected components: /{entity}/graph/components
                _cc_path = endpoint.path.rstrip("/") + "/graph/components"
                _cc_handler = create_components_handler(
                    entity_name=entity_name or "Item",
                    graph_edge_spec=_node_graph["graph_edge"],
                    graph_node_spec=_node_graph.get("graph_node"),
                    node_table=_node_graph["node_table"],
                    edge_table=_node_graph["edge_table"],
                    db_manager=self.db_manager,
                    filter_fields=_alg_filter_fields,
                    optional_auth_dep=self.optional_auth_dep,
                )
                self._router.add_api_route(
                    _cc_path,
                    _cc_handler,
                    methods=["GET"],
                    tags=[entity_name or "Item"],
                    summary=f"Connected components for {entity_name}",
                )

        # PUT/PATCH -> UPDATE
        elif (
            endpoint.method in (HttpMethod.PUT, HttpMethod.PATCH)
            or operation_kind == OperationKind.UPDATE
        ):
            update_schema = entity_schemas.get("update", model)
            if update_schema:
                handler = create_update_handler(
                    service,
                    update_schema,
                    model,
                    auth_dep=self.auth_dep,
                    require_auth_by_default=self.require_auth_by_default,
                    entity_name=entity_name or "Item",
                    audit_logger=_audit_for("update"),
                    cedar_access_spec=_cedar_spec,
                    optional_auth_dep=self.optional_auth_dep,
                    include_field_changes=_include_fc,
                )
                self._add_route(endpoint, handler, response_model=model)
            else:
                raise ValueError(f"No update schema for endpoint: {endpoint.name}")

        # DELETE -> DELETE
        elif endpoint.method == HttpMethod.DELETE or operation_kind == OperationKind.DELETE:
            handler = create_delete_handler(
                service,
                auth_dep=self.auth_dep,
                require_auth_by_default=self.require_auth_by_default,
                entity_name=entity_name or "Item",
                audit_logger=_audit_for("delete"),
                cedar_access_spec=_cedar_spec,
                optional_auth_dep=self.optional_auth_dep,
                include_field_changes=_include_fc,
            )
            self._add_route(endpoint, handler, response_model=None)

        else:
            # Custom operation
            handler = create_custom_handler(service)
            self._add_route(endpoint, handler, response_model=None)

    def _add_route(
        self,
        endpoint: EndpointSpec,
        handler: Callable[..., Any],
        response_model: type[BaseModel] | None = None,
    ) -> None:
        """Add a route to the router."""
        # Map HTTP methods to router methods
        method_map = {
            HttpMethod.GET: self._router.get,
            HttpMethod.POST: self._router.post,
            HttpMethod.PUT: self._router.put,
            HttpMethod.PATCH: self._router.patch,
            HttpMethod.DELETE: self._router.delete,
        }

        router_method = method_map.get(endpoint.method)
        if not router_method:
            raise ValueError(f"Unsupported HTTP method: {endpoint.method}")

        # Convert path parameters from {id} to FastAPI format
        path = endpoint.path

        # Build route decorator kwargs
        route_kwargs: dict[str, Any] = {
            "summary": endpoint.description or endpoint.name,
            "tags": endpoint.tags or [],
        }

        if response_model:
            route_kwargs["response_model"] = response_model

        # Add role-based dependencies (RBAC)
        dependencies: list[Any] = []
        if endpoint.require_roles and self.auth_store:
            from dazzle_back.runtime.auth import create_auth_dependency

            role_dep = create_auth_dependency(self.auth_store, require_roles=endpoint.require_roles)
            dependencies.append(Depends(role_dep))

        if endpoint.deny_roles and self.auth_store:
            from dazzle_back.runtime.auth import create_deny_dependency

            deny_dep = create_deny_dependency(self.auth_store, deny_roles=endpoint.deny_roles)
            dependencies.append(Depends(deny_dep))

        if dependencies:
            route_kwargs["dependencies"] = dependencies

        # Add the route
        router_method(path, **route_kwargs)(handler)

    def generate_all_routes(
        self,
        endpoints: list[EndpointSpec],
        service_specs: dict[str, ServiceSpec] | None = None,
    ) -> APIRouter:
        """
        Generate routes for all endpoints.

        Endpoints are sorted so that static paths are registered before
        parameterized paths at the same depth.  This prevents FastAPI from
        matching a path parameter (e.g. ``{id}``) against a literal segment
        like ``create`` — the same strategy used by the UI page router.

        Args:
            endpoints: List of endpoint specifications
            service_specs: Optional dictionary mapping service names to specs

        Returns:
            FastAPI router with all routes
        """
        service_specs = service_specs or {}

        # Register /{plural}/create guard routes BEFORE main routes so
        # FastAPI doesn't match "create" as a UUID {id} parameter (#598).
        # FastAPI uses first-match-wins, so /tasks/create must be
        # registered before /tasks/{id}.
        _guarded: set[str] = set()
        for ep in endpoints:
            if ep.method == HttpMethod.GET and ep.path.endswith("/{id}"):
                prefix = ep.path[: -len("/{id}")]
                if prefix and prefix not in _guarded:
                    _guarded.add(prefix)
                    create_path = f"{prefix}/create"

                    async def _create_guard(request: Request) -> Any:
                        raise HTTPException(
                            status_code=404,
                            detail="Use the UI create form or POST to the collection endpoint",
                        )

                    self._router.get(
                        create_path,
                        tags=["Guard"],
                        include_in_schema=False,
                    )(_create_guard)

        def _route_sort_key(ep: EndpointSpec) -> tuple[int, int]:
            # More segments first, then static before dynamic at same depth.
            return (-ep.path.count("/"), 0 if "{" not in ep.path else 1)

        for endpoint in sorted(endpoints, key=_route_sort_key):
            service_spec = service_specs.get(endpoint.service)
            self.generate_route(endpoint, service_spec)

        return self._router

    @property
    def router(self) -> APIRouter:
        """Get the generated router."""
        return self._router


# =============================================================================
# Convenience Functions
# =============================================================================


def generate_crud_routes(
    entity_name: str,
    service: Any,
    model: type[BaseModel],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    prefix: str | None = None,
    tags: list[str | Enum] | None = None,
) -> APIRouter:
    """
    Generate standard CRUD routes for an entity.

    This is a convenience function for quickly creating RESTful routes.

    Args:
        entity_name: Name of the entity
        service: CRUD service instance
        model: Pydantic model for the entity
        create_schema: Schema for create operations
        update_schema: Schema for update operations
        prefix: Optional URL prefix (defaults to /entity_name)
        tags: Optional tags for grouping in OpenAPI docs

    Returns:
        FastAPI router with CRUD routes
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is not installed. Install with: pip install fastapi")

    router = _APIRouter()
    prefix = prefix or f"/{to_api_plural(entity_name)}"
    tags = tags or [entity_name]

    # List
    @router.get(prefix, tags=tags, summary=f"List {entity_name}s")
    async def list_items(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ) -> Any:
        return await service.execute(operation="list", page=page, page_size=page_size)

    # Read
    @router.get(f"{prefix}/{{id}}", tags=tags, summary=f"Get {entity_name}", response_model=model)
    async def get_item(id: UUID) -> Any:
        result = await service.execute(operation="read", id=id)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return result

    # Create
    @router.post(prefix, tags=tags, summary=f"Create {entity_name}", response_model=model)
    async def create_item(request: Request, data: create_schema) -> Any:
        result = await service.execute(operation="create", data=data)
        return _with_htmx_triggers(request, result, entity_name, "created")

    # Update
    @router.put(
        f"{prefix}/{{id}}", tags=tags, summary=f"Update {entity_name}", response_model=model
    )
    async def update_item(id: UUID, request: Request, data: update_schema) -> Any:
        result = await service.execute(operation="update", id=id, data=data)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return _with_htmx_triggers(
            request, result, entity_name, "updated", redirect_url=_htmx_current_url(request)
        )

    # Delete
    @router.delete(f"{prefix}/{{id}}", tags=tags, summary=f"Delete {entity_name}")
    async def delete_item(id: UUID, request: Request) -> Any:
        result = await service.execute(operation="delete", id=id)
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        return _with_htmx_triggers(
            request,
            {"deleted": True},
            entity_name,
            "deleted",
            redirect_url=_htmx_parent_url(request),
        )

    return router
