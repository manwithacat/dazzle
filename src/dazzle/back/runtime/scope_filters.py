"""Scope / row-RBAC filter resolution for generated routes.

Extracted verbatim from ``route_generator.py`` (#1361 slice 1). This is the
Cedar row-RBAC / scope-filter resolution family: condition-tree extraction,
``current_user.<attr>`` resolution, scope-rule -> SQL filter resolution
(legacy condition trees + the predicate-compiler pipeline), the scoped
pre-read used by UPDATE/DELETE/READ handlers, and the ``scope: create:`` /
``scope: update:`` payload-time enforcers (#1124, #1311, #1312, ADR-0028).

A leaf module by design: it must not import ``route_generator`` at module
level (``route_generator`` imports these names back at module level so the
``route_generator.X`` patch points and re-exports keep working). The one
shared helper that stays in ``route_generator`` (``_normalize_role``, also
used by the audit/list paths there) is imported lazily inside function
bodies.

Deliberately NOT named ``*_routes.py`` — the runtime-urls api-surface walker
globs that pattern and this module defines no routes.
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from dazzle.back.runtime.auth import AuthContext, effective_roles_of

if TYPE_CHECKING:
    from dazzle.back.runtime.service_generator import BaseService
    from dazzle.back.specs.auth import EntityAccessSpec
    from dazzle.core.ir.fk_graph import FKGraph

logger = logging.getLogger(__name__)


# =============================================================================
# Row-level RBAC helpers
# =============================================================================


def _extract_cedar_row_filters(
    cedar_access_spec: "EntityAccessSpec",
    user_id: str,
    auth_context: "AuthContext | None" = None,
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

    # Lazy: _normalize_role stays in route_generator (also used by its
    # audit/list paths); a module-level import here would be circular.
    from dazzle.back.runtime.route_generator import _normalize_role

    _logger = logging.getLogger(__name__)

    permissions = getattr(cedar_access_spec, "permissions", None)
    if not permissions:
        return {}

    # Collect roles from auth_context, normalizing role_ prefix.
    # auth Plan 1b: source from the active membership (effective_roles), not
    # the global user.roles.
    user_roles: set[str] = set()
    if auth_context is not None:
        for r in effective_roles_of(auth_context):
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
    all_ref_targets: dict[str, dict[str, str]] | None = None,
) -> tuple[str, str, list[Any]] | None:
    """Build a subquery for a left-side dotted path like ``manuscript.student``.

    Given field="manuscript.student", resolves:
    - ``manuscript`` → FK field on the current entity (``manuscript`` or
      ``manuscript_id``, whichever ``ref_targets`` carries)
    - target entity ``Manuscript`` (from ``ref_targets``)
    - ``student`` → the column to match on the target entity

    The target column (#1304) is resolved against the *target* entity's own
    FK map in ``all_ref_targets`` (entity → {fk_field: target}): if
    ``<target_field>_id`` is an FK on the target entity, the dotted segment
    names an FK *relation* and the column is ``<target_field>_id``; otherwise
    the segment is taken literally (a scalar column, e.g. ``user``). This is
    model-dependent — some projects name FK fields ``teacher`` (bare), others
    ``teaching_group_id`` — so a blanket ``_id`` suffix is wrong (it broke the
    bare-named ``teacher.user = current_user`` case). When ``all_ref_targets``
    is absent (scope-rule callers that don't thread it), the segment is taken
    literally, preserving the pre-#1304 behaviour.

    Returns (fk_field, subquery_sql, params) or None if the path can't be resolved.
    """
    from dazzle.back.runtime.query_builder import quote_identifier

    parts = field.split(".", 1)
    if len(parts) != 2:
        return None

    relation_name, target_field = parts

    # Resolve relation name to FK field on current entity.
    # Convention: relation "manuscript" → FK field "manuscript_id" (or bare).
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
    # Resolve target_field → actual column via the target entity's FK map.
    target_fks = (all_ref_targets or {}).get(target_entity, {})
    if target_field in target_fks:
        target_col_name = target_field  # FK relation, bare-named on target
    elif f"{target_field}_id" in target_fks:
        target_col_name = f"{target_field}_id"  # FK relation → `_id` column
    else:
        target_col_name = target_field  # literal/scalar column (e.g. `user`)
    target_col = quote_identifier(target_col_name)

    subquery_sql = f'SELECT "id" FROM {target_table} WHERE {target_col} = %s'  # nosemgrep
    return fk_field, subquery_sql, [resolved_value]


def _build_via_subquery(
    *,
    junction_entity: str,
    bindings: list[dict[str, str]],
    user_id: str,
    auth_context: "AuthContext | None" = None,
) -> tuple[str, str, list[Any]]:
    """Build a SQL subquery for a via-check scope condition.

    Returns (entity_field, subquery_sql, params).
    """
    from dazzle.back.runtime.query_builder import quote_identifier

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


def _resolve_user_attribute(attr_name: str, auth_context: "AuthContext | None") -> Any:
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

    # auth Plan 1d: tenant_id is sourced ONLY from the active membership (the
    # hard FK source the RLS fence reads). A membership-less session resolves to
    # the deny sentinel → the scope predicate / fence denies (fail-closed). The
    # legacy preferences/domain-user fallback for tenant_id was removed (clean
    # break) — only the active membership is authoritative now. Other
    # current_user.<attr> scope refs (school, department, …) still resolve via
    # the user/preferences path below.
    if attr_name == "tenant_id":
        membership = getattr(auth_context, "active_membership", None)
        if membership is not None and getattr(membership, "tenant_id", None):
            return str(membership.tenant_id)
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
    auth_context: "AuthContext | None" = None,
    ref_targets: dict[str, str] | None = None,
    context_id: str | None = None,
    all_ref_targets: dict[str, dict[str, str]] | None = None,
    context_only: bool = False,
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

    The ``current_context`` sentinel resolves to the workspace selector's
    selected entity id when provided (#857).  If ``context_id`` is ``None``
    (no selection), the condition is skipped so the existing persona scope
    applies unfiltered.

    ``context_only`` (#1305): when True, emit *only* the ``current_context``
    predicate(s) and skip every ``current_user`` / literal / via-check branch.
    The aggregate / GROUP BY region paths use this to isolate the
    context-selector slice of a compound region ``filter:`` (e.g.
    ``assessment_event.teaching_group = current_context and status = "marked"``)
    so the chart re-scopes by ``context_id`` the same way the list path does —
    *without* re-mixing the row-level ``status`` predicate into the aggregate
    query (the #887 tenant-bounding contract). AND trees are still walked so a
    nested ``current_context`` comparison is found.
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
            result = _build_fk_path_subquery(fld, val, ref_targets, all_ref_targets)
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

        if (
            field
            and value == "current_user"
            and op_val in ("=", "eq", "equals")
            and not context_only
        ):
            # Prefer DSL User entity ID over auth user ID so comparisons
            # against ref User fields work correctly (#546).
            resolved = _resolve_user_attribute("entity_id", auth_context)
            _set_filter(field, user_id if resolved == "__RBAC_DENY__" else resolved)
        elif (
            field
            and isinstance(value, str)
            and value.startswith("current_user.")
            and op_val in ("=", "eq", "equals")
            and not context_only
        ):
            attr_name = value[len("current_user.") :]
            _set_filter(field, _resolve_user_attribute(attr_name, auth_context))
        elif field and value == "current_context" and op_val in ("=", "eq", "equals"):
            # Context selector (#857): resolve to the selected entity id if
            # a selection is active; skip the filter entirely when cleared
            # so the existing persona scope applies unfiltered.
            if context_id:
                _set_filter(field, context_id)
        elif (
            field
            and isinstance(value, str | int | float | bool)
            and value != "current_user"
            and value != "current_context"
            and not context_only  # #1305: aggregate path wants only the context slice
        ):
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
                    left,
                    user_id,
                    filters,
                    _logger,
                    auth_context,
                    ref_targets,
                    context_id,
                    all_ref_targets,
                    context_only,
                )
            if right:
                _extract_condition_filters(
                    right,
                    user_id,
                    filters,
                    _logger,
                    auth_context,
                    ref_targets,
                    context_id,
                    all_ref_targets,
                    context_only,
                )
        return

    if kind == "via_check":
        # #1305: a junction (via) check is a scope/relationship predicate, not
        # the context-selector slice — skip it when isolating context filters.
        if context_only:
            return
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

        if (
            field
            and raw_value == "current_user"
            and op_val in ("=", "eq", "equals")
            and not context_only
        ):
            # Prefer DSL User entity ID over auth user ID so comparisons
            # against ref User fields work correctly (#546).
            resolved = _resolve_user_attribute("entity_id", auth_context)
            _set_filter(field, user_id if resolved == "__RBAC_DENY__" else resolved)
        elif (
            field
            and isinstance(raw_value, str)
            and raw_value.startswith("current_user.")
            and op_val in ("=", "eq", "equals")
            and not context_only
        ):
            attr_name = raw_value[len("current_user.") :]
            _set_filter(field, _resolve_user_attribute(attr_name, auth_context))
        elif field and raw_value == "current_context" and op_val in ("=", "eq", "equals"):
            # Context selector (#857): resolve to the selected entity id if
            # a selection is active; skip the filter entirely when cleared
            # so the existing persona scope applies unfiltered.
            if context_id:
                _set_filter(field, context_id)
        elif (
            field
            and isinstance(raw_value, str | int | float | bool)
            and raw_value != "current_user"
            and raw_value != "current_context"
            and not context_only  # #1305: aggregate path wants only the context slice
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
                    left,
                    user_id,
                    filters,
                    _logger,
                    auth_context,
                    ref_targets,
                    context_id,
                    all_ref_targets,
                    context_only,
                )
            if right:
                _extract_condition_filters(
                    right,
                    user_id,
                    filters,
                    _logger,
                    auth_context,
                    ref_targets,
                    context_id,
                    all_ref_targets,
                    context_only,
                )
        # OR and other logical operators require post-fetch filtering
        # which is handled by the visibility system already
        return

    # Via-check condition (IR path)
    # #1305: a junction (via) check is a scope/relationship predicate, not the
    # context-selector slice — skip it when isolating context filters.
    via_cond = getattr(condition, "via_condition", None)
    if via_cond is not None and not context_only:
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


def _resolve_scope_filters(
    cedar_access_spec: "EntityAccessSpec",
    operation: str,
    user_roles: set[str],
    user_id: str,
    auth_context: "AuthContext | None" = None,
    ref_targets: dict[str, str] | None = None,
    *,
    entity_name: str = "",
    fk_graph: "FKGraph | None" = None,
    admin_personas: list[str] | None = None,
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
                    predicate,
                    entity_name,
                    fk_graph,
                    user_id,
                    auth_context,
                    admin_personas=admin_personas,
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


async def _scoped_pre_read(
    *,
    service: "BaseService[Any]",
    operation: str,
    id: Any,
    cedar_access_spec: "EntityAccessSpec",
    auth_context: "AuthContext",
    entity_name: str,
    fk_graph: "FKGraph | None",
    admin_personas: list[str] | None,
) -> Any:
    """Pre-read with `scope: <operation>:` enforcement applied (#1123).

    For UPDATE/DELETE, this replaces the bare ``service.execute(operation=
    "read", id=id)`` with a scope-validated lookup. Three outcomes match
    the LIST handler's default-deny shape:

    - **No `scope:` rules for this operation** → unscoped read (back-
      compat with pre-#1123 behaviour and tests that don't construct
      scope rules).
    - **`scope:` matched with `all`** → unscoped read (no filter).
    - **`scope:` matched with field condition / predicate** → scoped
      read via ``service.list(filters={"id": id, **scope_result})``;
      if no row comes back, returns ``None`` (handler raises 404).
    - **`scope:` exists but no rule matches this role/op** → returns
      ``None`` (handler raises 404 — same default-deny shape as LIST).

    The 404 shape is deliberate: it makes scope-denied rows
    indistinguishable from non-existent rows, preventing row-existence
    leaks via IDOR-style probing.

    `fk_graph` may be None on legacy/test paths — in that case we
    fall through to the unscoped read (the predicate compiler path
    requires fk_graph; without it we cannot compile a scope predicate
    so we treat it as "no enforcement available here").
    """
    # Lazy: _normalize_role stays in route_generator (circular otherwise).
    from dazzle.back.runtime.route_generator import _normalize_role

    if not getattr(cedar_access_spec, "scopes", None):
        return await service.execute(operation="read", id=id)

    if fk_graph is None:
        # Predicate compiler needs fk_graph; without it we can't compile
        # the scope predicate. Fall back to unscoped pre-read so we don't
        # silently default-deny on test fixtures lacking the FK graph.
        return await service.execute(operation="read", id=id)

    user_roles: set[str] = set()
    user_id: str | None = None
    if auth_context is not None and getattr(auth_context, "is_authenticated", False):
        user = getattr(auth_context, "user", None)
        if user is not None:
            user_id = str(user.id) if getattr(user, "id", None) is not None else None
        # auth Plan 1b: roles from the active membership (effective_roles), not
        # the global user.roles. user_id still comes from the user.
        for r in effective_roles_of(auth_context):
            r_name = r if isinstance(r, str) else getattr(r, "name", str(r))
            user_roles.add(_normalize_role(r_name))

    if user_id is None:
        # Unauthenticated path — fall back to unscoped (the permit gate
        # has already rejected unauth users with cedar_access_spec set;
        # this branch is defensive).
        return await service.execute(operation="read", id=id)

    scope_result = _resolve_scope_filters(
        cedar_access_spec,
        operation,
        user_roles,
        user_id,
        auth_context,
        entity_name=entity_name,
        fk_graph=fk_graph,
        admin_personas=admin_personas,
    )

    if scope_result is None:
        # No matching scope rule for this role/op — default-deny.
        return None

    if not scope_result:
        # `scope: all` for this op — no filter, unscoped read.
        return await service.execute(operation="read", id=id)

    # Scope predicate compiled to a filter dict. Fold {"id": id} on top
    # and use the list path's existing filter handling (which already
    # understands the `__scope_predicate` special key emitted by the
    # predicate compiler). page_size=1 short-circuits at the DB.
    list_result = await service.execute(
        operation="list",
        page=1,
        page_size=1,
        filters={"id": id, **scope_result},
    )
    items = list_result.get("items") if isinstance(list_result, dict) else []
    return items[0] if items else None


class _LazyUserAttrs(dict):  # type: ignore[type-arg]
    """`current_user.<attr>` resolver for `scope: create:` enforcement.

    A `dict` subclass so it satisfies the `user_attrs: dict[str, Any]`
    contract of `check_create_predicate`, but resolves any requested
    attribute name on demand via `_resolve_user_attribute` (built-in
    UserRecord fields + `auth_context.preferences`). This is what makes
    `current_user.org` — and any other DSL-chosen attribute — resolvable
    in create-scope predicates without a hardcoded allowlist (#1174).

    `__missing__` caches each resolved value so a repeated lookup of the
    same attribute (e.g. in an AND/OR predicate) hits the cache. An
    unresolvable attribute resolves to `None` (the `__RBAC_DENY__`
    sentinel is translated away) so the walker's `_compare` rejects it
    — fail-closed, matching the previous "missing key → None" semantics.
    """

    def __init__(self, auth_context: "AuthContext | None") -> None:
        super().__init__()
        self._auth_context = auth_context

    def __missing__(self, key: str) -> Any:
        resolved = _resolve_user_attribute(key, self._auth_context)
        value = None if resolved == "__RBAC_DENY__" else resolved
        self[key] = value  # cache for repeated lookups within one predicate
        return value

    def get(self, key: str, default: Any = None) -> Any:
        # `dict.get` does NOT trigger `__missing__` — only subscripting does.
        # The create-scope walker (`scope_create_eval._walk`) resolves
        # attributes via `user_attrs.get(...)`, so `get` must route through
        # `__getitem__` for lazy resolution to fire. A resolved-but-None
        # attribute is returned as-is (not replaced by `default`) so a
        # genuinely-missing attr still fails the predicate closed.
        return self[key]

    def __bool__(self) -> bool:
        # A lazy resolver is NEVER "empty" — it can resolve any attribute on
        # demand. It must report truthy even before the first lookup caches
        # an entry: `check_create_predicate` does `user_attrs = user_attrs
        # or {}`, and a still-empty `_LazyUserAttrs` (the common case — the
        # cache is only populated lazily) would be falsy and silently
        # replaced by a plain empty dict, dropping the resolver entirely.
        return True


def build_create_scope_probe(
    service: Any,
    entity_name: str,
) -> Callable[[str, list[Any]], bool] | None:
    """Build a sync ``scope: create:`` payload-time probe (#1311, ADR-0028).

    The probe runs a parameterised ``SELECT 1 WHERE <expr> LIMIT 1`` on the
    service's repository connection — which already applies the active tenant
    schema to ``search_path`` — and returns whether it yielded a row. It lets
    the create-scope walker evaluate FK-path (depth > 1) and EXISTS predicates
    against the live DB at payload time, BEFORE the insert, fail-closed.

    Returns None when the service exposes no repository/DB (custom services,
    test doubles); the walker treats a None probe as "cannot evaluate" and
    raises :class:`ScopeCreateUnsupportedError`, which the enforcer maps to a
    default-deny 403.

    Shared by the framework CREATE route (:func:`_enforce_create_scope`) and
    the override path (``policy._check_scope_create``) so both evaluate the
    same boundary.
    """
    repo = getattr(service, "_repository", None) if service is not None else None
    db = getattr(repo, "db", None) if repo is not None else None
    if db is None:
        return None

    def _probe(sql: str, params: list[Any]) -> bool:
        full_sql = f"SELECT 1 WHERE {sql} LIMIT 1"
        try:
            with db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(full_sql, params)  # nosemgrep
                return cursor.fetchone() is not None
        except Exception:
            # ADR-0028 rule 4: fail closed, never leak internal detail. A
            # malformed probe (or a transient DB error) denies the create
            # rather than 500-ing or silently allowing it; the warning log
            # carries the detail for operators.
            logger.warning(
                "scope: create: probe query failed — denying (fail-closed). entity=%s",
                entity_name,
                exc_info=True,
            )
            return False

    return _probe


def _enforce_create_scope(
    *,
    cedar_access_spec: "EntityAccessSpec | None",
    payload: dict[str, Any],
    user_id: str | None,
    user_roles: list[str],
    entity_name: str,
    auth_context: "AuthContext | None",
    service: Any = None,
    fk_graph: "FKGraph | None" = None,
    probe: "Callable[[str, list[Any]], bool] | None" = None,
) -> None:
    """`scope: create:` enforcement (#1124, v0.71.22).

    ``probe`` (optional, #1313): inject a create-scope probe instead of building
    one from ``service``. The atomic-flow executor passes an *in-transaction*
    probe (bound to the flow's connection) so FK-path / EXISTS scope is resolved
    inside the flow's transaction; CRUD callers omit it and the default
    separate-connection probe (:func:`build_create_scope_probe`) is built.

    Walks any matching ``scope: create:`` rules against the post-default
    payload and raises HTTPException(403) if any matching rule rejects
    it. Three outcomes:

    - **No `scope:` rules** → no check (back-compat with apps that
      don't declare scope).
    - **No matching scope-create rule for the user's role** → if other
      `scope:` rules exist for this entity, default-deny (403); this
      matches the LIST handler's default-deny semantic. If the
      `scope:` block has no `create` rules at all, fall through (the
      RBAC lint surfaces this as a `no_scope_rule` warning).
    - **Matching rule with predicate** → walk the predicate; 403 if
      it rejects.

    The 403 carries a ``detail`` body naming the entity + operation so
    debug surfaces can grep on it. We don't leak the exact field that
    failed (avoids handing attackers a payload-tuning oracle).
    """
    # Lazy: _normalize_role stays in route_generator (circular otherwise).
    from dazzle.back.runtime.route_generator import _normalize_role

    if cedar_access_spec is None:
        return
    scopes = getattr(cedar_access_spec, "scopes", None)
    if not scopes:
        return

    # Look for any `scope: create:` rules; bail out if none declared
    # for this entity at all (RBAC lint warns about this separately;
    # default-deny only applies when create rules exist but none match
    # the user's role).
    create_rules: list[Any] = []
    for r in scopes:
        rule_op = getattr(r, "operation", None)
        if rule_op is None:
            continue
        rule_op_val = rule_op.value if hasattr(rule_op, "value") else str(rule_op)
        if rule_op_val == "create":
            create_rules.append(r)
    if not create_rules:
        return

    normalised_roles = {_normalize_role(r) for r in (user_roles or [])}
    matched: list[Any] = []
    for r in create_rules:
        rule_personas = list(getattr(r, "personas", []) or [])
        if "*" in rule_personas or (normalised_roles & set(rule_personas)):
            matched.append(r)

    if not matched:
        # Create rules exist but none matches this role — default-deny.
        # Same shape as `_resolve_scope_filters` returning None on
        # list/read/update/delete.
        raise HTTPException(
            status_code=403,
            detail={
                "error": "scope_create_denied",
                "entity": entity_name,
                "reason": (
                    "No matching scope: create: rule for this role. "
                    "See docs/reference/rbac-scope.md."
                ),
            },
        )

    # Any matched rule with `all` (no predicate) → unrestricted.
    for r in matched:
        if getattr(r, "predicate", None) is None and getattr(r, "condition", None) is None:
            return

    # Build the user-attr resolver from the auth context. A `scope: create:`
    # predicate may reference `current_user.<attr>` for ANY attribute the DSL
    # author chose (`org`, `school`, `team`, ...) — there is no fixed set. So
    # rather than copy a hardcoded allowlist of attribute names (which silently
    # over-denies for any attr not on the list — e.g. acme_billing's
    # `current_user.org`, #1174), resolve every requested attribute lazily
    # through `_resolve_user_attribute` — the same canonical resolver the
    # read/list scope path uses. It reads built-in UserRecord fields *and*
    # `auth_context.preferences` (where domain attributes like `org` are
    # merged from the DSL User entity by `_load_domain_user_attributes`).
    # `_resolve_user_attribute` returns the `__RBAC_DENY__` sentinel for an
    # unresolvable attribute; we translate that to None so the create-scope
    # walker's `_compare` rejects it (fail-closed), identical to the previous
    # "missing key → None" behaviour. `auth_context` is threaded in from the
    # CREATE handler — `request.state.auth_context` was never set, so the old
    # code's resolver was always empty regardless of the attribute name.
    user_attrs = _LazyUserAttrs(auth_context)

    # Run the walker against the predicate. Any matched rule passing the
    # walker is enough to allow the insert (OR of matched rules). If none
    # pass → 403. FK-path (depth > 1) and EXISTS predicates resolve via a
    # payload-time SQL probe on the entity's repository (#1311, ADR-0028);
    # simple leaves stay pure-Python against the payload.
    from dazzle.back.runtime.scope_create_eval import (
        ScopeCreateUnsupportedError,
        check_create_predicate,
    )
    from dazzle.back.runtime.tenant_isolation import get_current_tenant_schema

    if probe is None:
        probe = build_create_scope_probe(service, entity_name)
    schema = get_current_tenant_schema()

    for r in matched:
        predicate = getattr(r, "predicate", None)
        if predicate is None:
            # Condition-tree fallback (legacy path). Not supported on
            # create — the linker rejects this case too. Defensive:
            # default-deny if we hit it at runtime.
            continue
        try:
            if check_create_predicate(
                predicate,
                payload,
                user_id=str(user_id) if user_id else "",
                user_attrs=user_attrs,
                probe=probe,
                fk_graph=fk_graph,
                entity_name=entity_name,
                schema=schema,
            ):
                return  # at least one matched rule passes — allow
        except ScopeCreateUnsupportedError:
            # A probe-requiring shape with no probe available (no DB on the
            # service). Fail closed — default-deny rather than allow an
            # un-enforced FK-path / EXISTS create-scope predicate.
            logger.warning(
                "scope: create: predicate needs a payload-time probe but "
                "none was available (no repository/DB on the service). "
                "Denying. entity=%s",
                entity_name,
            )
            continue

    raise HTTPException(
        status_code=403,
        detail={
            "error": "scope_create_denied",
            "entity": entity_name,
            "reason": (
                "The inserted row does not satisfy the scope: create: "
                "predicate for this role. See docs/reference/rbac-scope.md."
            ),
        },
    )


def _row_to_payload_dict(row: Any) -> dict[str, Any]:
    """Normalise a pre-read row (Pydantic model or dict) to a JSON-shaped dict.

    Mirrors the create path's ``data.model_dump(mode="json")`` so UUID /
    datetime values compare as strings against ``current_user.<attr>`` (always
    str). An unrecognised shape yields an empty dict (the merge then falls back
    to the new values alone).
    """
    if row is None:
        return {}
    if hasattr(row, "model_dump"):
        dumped = row.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    if isinstance(row, dict):
        return dict(row)
    return {}


def _enforce_update_scope(
    *,
    cedar_access_spec: "EntityAccessSpec | None",
    existing: Any,
    new_values: dict[str, Any],
    user_id: str | None,
    user_roles: list[str],
    entity_name: str,
    auth_context: "AuthContext | None",
    service: Any = None,
    fk_graph: "FKGraph | None" = None,
    probe: "Callable[[str, list[Any]], bool] | None" = None,
    also_check_source: bool = False,
) -> None:
    """`scope: update:` DESTINATION enforcement (#1312, ADR-0028).

    ``probe`` (#1313): inject an in-transaction probe (atomic-flow executor)
    instead of building a separate-connection one.

    ``also_check_source`` (#1313): also validate the *source* (``existing``)
    row against ``scope: update:``. The framework UPDATE route validates the
    source via ``_scoped_pre_read`` before calling this, so it passes False;
    the atomic executor has no such pre-read, so it passes True — otherwise a
    flow could mutate a row the principal can't see (claiming a foreign row by
    moving it into scope).

    The pre-read (`_scoped_pre_read`) already validated the *source* row
    against ``scope: update:`` — but it never checked the *new* values the
    payload moves the row to. So an update that repoints an FK / scope-key
    column could move an in-scope row INTO a foreign scope. This re-validates
    the row's **would-be-final state** (the scope-validated ``existing`` row
    with the changed fields overlaid) against the same ``scope: update:``
    rule(s).

    Outcomes mirror `_enforce_create_scope`, with two deliberate differences:

    - **Denial → 404, not 403.** Per ADR-0028 rule 4 / the IDOR-avoidance
      contract, a destination denial is indistinguishable from a missing row
      (and the source pre-read already 404s the same way). The structured
      reason goes to the server log, not the client.
    - The payload checked is ``{**existing, **new_values}`` — so a scope-key
      column the partial update doesn't touch keeps its already-validated
      value, and only a column the payload actually changes can flip the
      verdict.

    FK-path (depth > 1) and EXISTS destination guards resolve via the same
    payload-time SQL probe as create-scope (#1311); simple leaves stay
    pure-Python. No ``scope: update:`` rules, or a matched ``all`` rule → no-op.
    """
    # Lazy: _normalize_role stays in route_generator (circular otherwise).
    from dazzle.back.runtime.route_generator import _normalize_role

    if cedar_access_spec is None:
        return
    scopes = getattr(cedar_access_spec, "scopes", None)
    if not scopes:
        return

    update_rules: list[Any] = []
    for r in scopes:
        rule_op = getattr(r, "operation", None)
        if rule_op is None:
            continue
        rule_op_val = rule_op.value if hasattr(rule_op, "value") else str(rule_op)
        if rule_op_val == "update":
            update_rules.append(r)
    if not update_rules:
        return

    normalised_roles = {_normalize_role(r) for r in (user_roles or [])}
    matched: list[Any] = [
        r
        for r in update_rules
        if "*" in (list(getattr(r, "personas", []) or []))
        or (normalised_roles & set(getattr(r, "personas", []) or []))
    ]
    if not matched:
        # Update rules exist but none matches this role. The source pre-read
        # under the same rules should already have 404'd, but default-deny
        # here too for safety (IDOR-shaped 404).
        _deny_update_destination(entity_name, user_id, "no matching scope: update: rule")

    # Any matched rule with `all` (no predicate) → unrestricted destination.
    for r in matched:
        if getattr(r, "predicate", None) is None and getattr(r, "condition", None) is None:
            return

    user_attrs = _LazyUserAttrs(auth_context)

    from dazzle.back.runtime.scope_create_eval import (
        ScopeCreateUnsupportedError,
        check_create_predicate,
    )
    from dazzle.back.runtime.tenant_isolation import get_current_tenant_schema

    if probe is None:
        probe = build_create_scope_probe(service, entity_name)
    schema = get_current_tenant_schema()

    def _passes(payload: dict[str, Any]) -> bool:
        """True if ``payload`` satisfies any matched scope: update: rule."""
        for r in matched:
            predicate = getattr(r, "predicate", None)
            if predicate is None:
                continue
            try:
                if check_create_predicate(
                    predicate,
                    payload,
                    user_id=str(user_id) if user_id else "",
                    user_attrs=user_attrs,
                    probe=probe,
                    fk_graph=fk_graph,
                    entity_name=entity_name,
                    schema=schema,
                ):
                    return True
            except ScopeCreateUnsupportedError:
                logger.warning(
                    "scope: update: predicate needs a payload-time probe but "
                    "none was available. Denying. entity=%s",
                    entity_name,
                )
                continue
        return False

    # Source check (atomic path only): the principal must already be able to
    # touch the existing row — otherwise a flow could claim a foreign row by
    # moving it into scope. The framework route validates this via the pre-read.
    if also_check_source and not _passes(_row_to_payload_dict(existing)):
        _deny_update_destination(
            entity_name, user_id, "source row does not satisfy the scope: update: predicate"
        )

    # Destination check: the would-be-final row (existing ⊕ changed fields). A
    # scope-key column the partial update doesn't set keeps its existing value.
    merged = {**_row_to_payload_dict(existing), **new_values}
    if not _passes(merged):
        _deny_update_destination(
            entity_name, user_id, "new values do not satisfy the scope: update: predicate"
        )


def _deny_update_destination(entity_name: str, user_id: str | None, reason: str) -> None:
    """Raise the IDOR-shaped 404 for an update-destination denial (#1312).

    The client sees a plain 404 (indistinguishable from a missing row, matching
    the source pre-read); operators get the reason in the server log.
    """
    logger.info(
        "scope: update: destination denied entity=%s user=%s reason=%s",
        entity_name,
        user_id,
        reason,
    )
    raise HTTPException(status_code=404, detail="Not found")


def _should_bypass_tenant_filter(
    auth_context: "AuthContext | None",
    admin_personas: list[str] | None,
) -> bool:
    """#957 cycle 5 — does this user's persona bypass the scope filter?

    Returns True when the active `tenancy: admin_personas:` list
    intersects the authenticated user's roles, OR when the user is a
    superuser. Otherwise returns False and the scope predicate compiles
    normally.

    Empty/None ``admin_personas`` (the cycle-5 default for unmigrated
    call sites) means the bypass never applies — identical to the
    pre-cycle-5 behaviour.
    """
    # Lazy: _normalize_role stays in route_generator (circular otherwise).
    from dazzle.back.runtime.route_generator import _normalize_role

    if auth_context is None or not getattr(auth_context, "is_authenticated", False):
        return False
    user = getattr(auth_context, "user", None)
    if user is None:
        return False
    if getattr(user, "is_superuser", False):
        return True
    if not admin_personas:
        return False
    # auth Plan 1b: admin bypass keyed on the active membership's roles.
    user_roles = set(effective_roles_of(auth_context))
    # AuthContext roles may carry the `role_` prefix from the auth
    # backend; predicate compilation works against the bare DSL names.
    normalised = {_normalize_role(r) for r in user_roles}
    return not normalised.isdisjoint(admin_personas)


def _resolve_predicate_filters(
    predicate: Any,
    entity_name: str,
    fk_graph: "FKGraph",
    user_id: str,
    auth_context: "AuthContext | None",
    admin_personas: list[str] | None = None,
) -> dict[str, Any]:
    """Compile a ScopePredicate to SQL and resolve runtime markers.

    Returns a filters dict with the special ``__scope_predicate`` key
    containing a ``(sql, params)`` tuple ready for the QueryBuilder.

    `admin_personas` (#957 cycle 5) — when the active user matches one
    of these tenant-admin personas, the scope filter is skipped and an
    empty dict is returned. Cycle 6 will thread this list from each
    list/read call site's enclosing AppSpec.
    """
    if _should_bypass_tenant_filter(auth_context, admin_personas):
        return {}

    from dazzle.back.runtime.predicate_compiler import (
        CurrentUserRef,
        UserAttrRef,
        compile_predicate,
    )
    from dazzle.back.runtime.tenant_isolation import get_current_tenant_schema

    schema = get_current_tenant_schema()
    sql, raw_params = compile_predicate(predicate, entity_name, fk_graph, schema=schema)

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
