"""Render-time affordance gating against declared predicates (#1787).

Two gates, one rule — a control the runtime would refuse is never offered:

- **Surface-action ``visible:``** (option B). A ``ConditionExpr`` on a surface
  ``action`` is evaluated against the record and the principal. A false
  predicate means the action is not rendered. For ``integration X action Y``
  outcomes the predicate is also the permission: the manual-trigger route
  re-evaluates it and refuses with 403 naming the predicate
  (:func:`integration_action_refusal`). External / surface / experience
  outcomes land on host routes, which remain the authz boundary (#1310).
- **State-machine guards** (option C). ``requires_role`` and expression guards
  on a transition are evaluated at render time through the same
  ``TransitionValidator`` the PUT uses (:func:`transition_offered`), so a
  transition the PUT would refuse is not offered on the detail page or a list
  row. The PUT-side check is unchanged and remains the permission.

Functions over IR + dicts — callers resolve the principal and the record;
:func:`enforce_integration_action` is the one that reads (the User row) and raises.
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import HTTPException

from dazzle.core import ir
from dazzle.core.condition_eval import condition_to_dsl, evaluate_condition
from dazzle.core.strings import normalize_role
from dazzle.http.runtime.auth.models import effective_roles_of
from dazzle.http.runtime.state_machine import TransitionValidator
from dazzle.http.runtime.tenant_render_context import inject_current_tenant
from dazzle.render.fragment.state_affordance import gated_row_transitions

logger = logging.getLogger(__name__)


def condition_context(
    *,
    user_roles: list[str] | None,
    current_user_id: str | None = None,
    current_user_entity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The evaluation context ``evaluate_condition`` reads (roles normalised)."""
    ctx: dict[str, Any] = {"user_roles": [normalize_role(r) for r in user_roles or []]}
    if current_user_id:
        ctx["current_user_id"] = current_user_id
    if current_user_entity:
        ctx["current_user_entity"] = current_user_entity
    return ctx


def predicate_holds(
    predicate: ir.ConditionExpr | None,
    record: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    """True when ``predicate`` is absent or evaluates true. Fails closed on error."""
    if predicate is None:
        return True
    try:
        return bool(evaluate_condition(predicate.model_dump(), record, context))
    except Exception:
        logger.warning(
            "visible: predicate `%s` failed to evaluate; treating as false",
            condition_to_dsl(predicate),
            exc_info=True,
        )
        return False


def _value_mentions_current_user_path(condition: ir.ConditionExpr | None) -> bool:
    if condition is None:
        return False
    comparison = condition.comparison
    if comparison is not None:
        literal = comparison.value.literal if comparison.value is not None else None
        if isinstance(literal, str) and literal.startswith("current_user."):
            return True
        if comparison.field and comparison.field.startswith("current_user."):
            return True
    return _value_mentions_current_user_path(condition.left) or _value_mentions_current_user_path(
        condition.right
    )


def needs_user_entity(predicates: list[ir.ConditionExpr | None]) -> bool:
    """True when any predicate reads ``current_user.<path>`` (needs the User row)."""
    return any(_value_mentions_current_user_path(p) for p in predicates)


def surface_visible_predicates(surface: ir.SurfaceSpec | None) -> list[ir.ConditionExpr | None]:
    """Every ``visible:`` declared on a surface (actions, sections, fields)."""
    if surface is None:
        return []
    out: list[ir.ConditionExpr | None] = [a.visible for a in surface.actions]
    for section in surface.sections:
        out.append(section.visible)
        out.extend(el.visible for el in section.elements)
    return out


def hidden_action_names(
    surface: ir.SurfaceSpec | None,
    record: dict[str, Any],
    context: dict[str, Any],
) -> set[str]:
    """Names of the surface's actions whose ``visible:`` is false for this record."""
    if surface is None:
        return set()
    return {
        action.name
        for action in surface.actions
        if not predicate_holds(action.visible, record, context)
    }


def integration_action_bindings(
    appspec: ir.AppSpec,
    entity_name: str,
    integration_name: str,
    mapping_name: str,
) -> list[tuple[ir.SurfaceSpec, ir.SurfaceAction]]:
    """Surface actions on ``entity_name`` whose outcome is
    ``integration <integration_name> action <mapping_name>``."""
    out: list[tuple[ir.SurfaceSpec, ir.SurfaceAction]] = []
    for surface in appspec.surfaces:
        if surface.entity_ref != entity_name:
            continue
        for action in surface.actions:
            outcome = action.outcome
            if (
                outcome.kind == ir.OutcomeKind.INTEGRATION
                and outcome.target == integration_name
                and outcome.action == mapping_name
            ):
                out.append((surface, action))
    return out


def integration_action_refusal(
    appspec: ir.AppSpec,
    entity_name: str,
    integration_name: str,
    mapping_name: str,
    record: dict[str, Any],
    context: dict[str, Any],
) -> str | None:
    """Why the manual trigger is refused for this record and principal, or None.

    Unbound triggers (no surface action names them) are not gated here. A
    trigger bound by several surface actions is permitted when any binding is
    unconditional or its predicate holds — the union of what the surfaces
    offer, so render and POST agree whichever surface the user came from.
    """
    bindings = integration_action_bindings(appspec, entity_name, integration_name, mapping_name)
    if not bindings:
        return None
    failed: list[str] = []
    for surface, action in bindings:
        if predicate_holds(action.visible, record, context):
            return None
        failed.append(
            f"surface '{surface.name}' action '{action.name}' "
            f"visible: {condition_to_dsl(action.visible)}"
        )
    return "Action not available for this record: " + "; ".join(failed)


def transition_offered(
    state_machine: Any,
    record: dict[str, Any],
    from_state: str,
    to_state: str,
    *,
    user_roles: list[str] | None,
    current_user: str | None = None,
    is_superuser: bool = False,
) -> bool:
    """Would the PUT accept ``from_state -> to_state`` for this principal?

    Runs ``TransitionValidator.validate_transition`` with ``for_render=True``:
    ``requires_role`` and expression guards are evaluated exactly as the PUT
    evaluates them; ``requires <field>`` guards and ``has_grant()`` guards are
    left to the PUT (the former is a fill-this-in prompt the 422 explains, the
    latter needs a grant-store connection render does not hold).
    """
    if state_machine is None or not from_state:
        return True
    # The PUT validates against the stored row, whose refs are bare ids; a
    # rendered record carries expanded ``{"id": ...}`` FK dicts. Flatten so a
    # guard like ``reviewer != current_user`` reads the same value on both sides.
    stored_shape = {
        k: (v["id"] if isinstance(v, dict) and "id" in v else v) for k, v in record.items()
    }
    result = TransitionValidator(state_machine).validate_transition(
        from_state,
        to_state,
        stored_shape,
        user_roles,
        current_user,
        is_superuser=is_superuser,
        for_render=True,
    )
    return result.is_valid


def principal_facts(auth_context: Any) -> tuple[list[str], str | None, bool]:
    """``(roles, current_user, is_superuser)`` exactly as the PUT derives them."""
    roles = list(effective_roles_of(auth_context))
    authenticated = bool(
        auth_context is not None and getattr(auth_context, "is_authenticated", False)
    )
    user = getattr(auth_context, "user", None) if authenticated else None
    current_user = str(user.id) if user is not None and getattr(user, "id", None) else None
    is_superuser = bool(getattr(user, "is_superuser", False)) if user is not None else False
    return roles, current_user, is_superuser


def _has_principal_guards(state_machine: Any) -> bool:
    for t in getattr(state_machine, "transitions", None) or ():
        for g in getattr(t, "guards", None) or ():
            if getattr(g, "requires_role", None) or getattr(g, "guard_expr", None):
                return True
    return False


def refused_row_transitions(
    state_machine: Any,
    items: list[dict[str, Any]],
    transitions: tuple[Any, ...],
    status_field: str,
    auth_context: Any,
) -> dict[str, frozenset[str]]:
    """Per list row, the target states whose guards refuse this principal (#1787 C).

    Keyed by ``str(row["id"])``. Rows absent from the map refuse nothing. Only
    transitions already valid from the row's state are checked — the state gate
    (:func:`gated_row_transitions`) still runs in the renderer.
    """
    if not state_machine or not transitions or not status_field:
        return {}
    if not _has_principal_guards(state_machine):
        return {}
    roles, current_user, is_superuser = principal_facts(auth_context)
    out: dict[str, frozenset[str]] = {}
    for item in items:
        current = str(item.get(status_field, "") or "")
        refused = frozenset(
            t.to_state
            for t in gated_row_transitions(list(transitions), current)
            if not transition_offered(
                state_machine,
                item,
                current,
                t.to_state,
                user_roles=roles,
                current_user=current_user,
                is_superuser=is_superuser,
            )
        )
        if refused:
            out[str(item.get("id"))] = refused
    return out


async def enforce_integration_action(
    appspec: ir.AppSpec,
    entity_name: str,
    integration_name: str,
    mapping_name: str,
    record: dict[str, Any],
    auth_context: Any,
    *,
    user_repository: Any = None,
    request: Any = None,
) -> None:
    """Refuse a manual integration trigger whose surface-action ``visible:`` is
    false for this record and principal (#1787) — 403 naming the predicate.

    The same :func:`integration_action_refusal` gates the detail-page button,
    so a button that renders is a POST that is accepted. Triggers no surface
    action binds are not gated here.
    """
    bindings = integration_action_bindings(appspec, entity_name, integration_name, mapping_name)
    if not bindings:
        return
    roles, current_user, _ = principal_facts(auth_context)
    user_entity: dict[str, Any] | None = None
    if (
        current_user
        and user_repository is not None
        and needs_user_entity([action.visible for _, action in bindings])
    ):
        try:
            row = await user_repository.read(UUID(current_user))
            if row is not None:
                user_entity = row if isinstance(row, dict) else row.model_dump()
        except Exception:
            logger.debug("current_user entity unresolved for visible:", exc_info=True)
    ctx = condition_context(
        user_roles=roles, current_user_id=current_user, current_user_entity=user_entity
    )
    if request is not None:
        inject_current_tenant(ctx, request)
    refusal = integration_action_refusal(
        appspec, entity_name, integration_name, mapping_name, record, ctx
    )
    if refusal is not None:
        raise HTTPException(status_code=403, detail=refusal)
