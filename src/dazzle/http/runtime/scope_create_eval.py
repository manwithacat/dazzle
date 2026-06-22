"""Python-side evaluator for ``scope: create:`` predicates (#1124, #1311).

Unlike list/read/update/delete enforcement (which compiles the
predicate to SQL and folds it into a WHERE clause), `create` has no
existing row to filter against — there's a payload waiting to become
a row. The natural semantic is "the inserted row must satisfy the
predicate", evaluated against the payload AFTER framework defaulting
runs (e.g. after `inject_current_user_refs` injects ``current_user``
into a missing ``created_by`` field).

The walker is a **hybrid**:

- The simple-predicate subset is evaluated in pure Python against the
  payload, with no DB roundtrip:

  - ``ColumnCheck`` — ``field op literal``
  - ``UserAttrCheck`` — ``field op current_user.attr`` (or bare
    ``current_user`` == auth user id)
  - ``PathCheck`` depth 1 — equivalent to ColumnCheck (single column)
  - ``Tautology`` / ``Contradiction`` — constants
  - ``BoolComposite`` (``and`` / ``or`` / ``not``) — recurses

- The two shapes whose authorization boundary is a multi-hop FK path
  or a junction table are evaluated with a **payload-time SQL probe**
  (#1311, ADR-0028):

  - ``PathCheck`` depth > 1 — resolve the FK path against the DB using
    the payload's FK value (``teaching_group.department =
    current_user.department``).
  - ``ExistsCheck`` / ``NotExistsCheck`` — junction-table membership
    (``via TeamMembership(user = current_user, team = team)``).

  The probe SQL is built by ``predicate_compiler`` (root-entity refs
  bound to payload values via ``PayloadFieldRef`` markers) and executed
  by an injected ``probe`` callable so this module stays DB-agnostic
  and unit-testable. ``BoolComposite`` naturally combines
  payload-evaluated and probe-evaluated leaves.

Every leaf fails **closed**: a missing payload FK value, an
unresolvable ``current_user.<attr>``, or a probe that returns no row
all evaluate to False (deny).

When no ``probe`` callable is supplied (e.g. a programmatically
constructed predicate, or a call site without DB access), the two
probe-requiring shapes raise :class:`ScopeCreateUnsupportedError` — a
defensive backstop so they cannot silently pass un-enforced.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    Contradiction,
    ExistsCheck,
    PathCheck,
    PolyPathCheck,
    ScopePredicate,
    Tautology,
    UserAttrCheck,
    ValueRef,
)
from dazzle.http.runtime.predicate_compiler import (
    CurrentTenantRef,
    CurrentUserRef,
    PayloadFieldRef,
    UserAttrRef,
    compile_exists_check_probe,
    compile_path_check_probe,
    compile_poly_path_check_probe,
)

if TYPE_CHECKING:
    from dazzle.core.ir.fk_graph import FKGraph

# A create-scope probe runs a parameterised ``SELECT 1 WHERE <expr>`` and
# returns True iff it yields a row. The walker resolves all markers to
# concrete values before calling it, so the callable only sees plain SQL +
# scalar params. Supplied by the route layer (it owns the DB connection).
ProbeFn = Callable[[str, list[Any]], bool]


class ScopeCreateUnsupportedError(Exception):
    """Raised when a predicate needs a DB probe but none was supplied.

    The framework CREATE path (`route_generator._enforce_create_scope`)
    and the override path (`policy._check_scope_create`) both build a
    probe from the entity's service/repository, so this should not fire
    in production. It is a defensive backstop for call sites that
    evaluate a predicate without DB access (programmatic construction,
    fixtures) — surfacing the gap rather than silently passing an
    un-enforced FK-path / EXISTS create-scope predicate.
    """


def check_create_predicate(
    predicate: ScopePredicate,
    payload: dict[str, Any],
    *,
    user_id: str,
    user_attrs: dict[str, Any] | None = None,
    probe: ProbeFn | None = None,
    fk_graph: FKGraph | None = None,
    entity_name: str = "",
    schema: str | None = None,
) -> bool:
    """Walk a `scope: create:` predicate against a post-default payload.

    Returns True if the predicate matches (insert proceeds), False if
    it rejects (handler should 403).

    Args:
        predicate: the parsed ScopePredicate from the IR.
        payload: the row-shaped dict the framework is about to insert.
            Typically ``data.model_dump()`` after current_user refs
            and persona-backed refs have been injected.
        user_id: the authenticated user's ID (resolves bare
            ``current_user`` markers).
        user_attrs: extra attributes on the auth user
            (resolves ``current_user.<attr>`` markers). Common keys:
            ``school``, ``org_id``, ``tenant_id``, etc.
        probe: runs a payload-time ``SELECT 1 WHERE <expr>`` for FK-path
            (depth > 1) / EXISTS predicates and returns whether it
            matched. None on call sites without DB access — those raise
            :class:`ScopeCreateUnsupportedError` on a probe-requiring
            shape (defensive backstop).
        fk_graph: FK graph for compiling probe SQL (required when the
            predicate contains FK-path / EXISTS leaves).
        entity_name: the root entity being created (for probe SQL).
        schema: optional tenant schema for probe table qualification.

    Raises:
        ScopeCreateUnsupportedError: a probe-requiring shape was reached
            but no ``probe`` callable was supplied.
    """
    user_attrs = user_attrs or {}
    return _walk(
        predicate,
        payload,
        user_id,
        user_attrs,
        probe=probe,
        fk_graph=fk_graph,
        entity_name=entity_name,
        schema=schema,
    )


def _walk(
    p: ScopePredicate,
    payload: dict[str, Any],
    user_id: str,
    user_attrs: dict[str, Any],
    *,
    probe: ProbeFn | None,
    fk_graph: FKGraph | None,
    entity_name: str,
    schema: str | None,
) -> bool:
    if isinstance(p, Tautology):
        return True
    if isinstance(p, Contradiction):
        return False
    if isinstance(p, ColumnCheck):
        return _compare(payload.get(p.field), p.op, _resolve_value(p.value, user_id, user_attrs))
    if isinstance(p, UserAttrCheck):
        right = user_id if p.user_attr in ("id", "") else user_attrs.get(p.user_attr)
        return _compare(payload.get(p.field), p.op, right)
    if isinstance(p, PathCheck):
        if len(p.path) > 1:
            # FK-path predicate — resolve the chain against the DB using the
            # payload's root FK value (#1311).
            if probe is None or fk_graph is None:
                raise ScopeCreateUnsupportedError(
                    "PathCheck with depth > 1 needs a payload-time SQL probe "
                    f"(path={p.path!r}) but none was supplied. See #1311 and "
                    "docs/reference/rbac-scope.md."
                )
            sql, raw_params = compile_path_check_probe(p, entity_name, fk_graph, schema=schema)
            return _run_probe(sql, raw_params, payload, user_id, user_attrs, probe)
        # Depth 1 = single column, equivalent to ColumnCheck.
        return _compare(payload.get(p.path[0]), p.op, _resolve_value(p.value, user_id, user_attrs))
    if isinstance(p, BoolComposite):
        if p.op == BoolOp.AND:
            return all(
                _walk(
                    c,
                    payload,
                    user_id,
                    user_attrs,
                    probe=probe,
                    fk_graph=fk_graph,
                    entity_name=entity_name,
                    schema=schema,
                )
                for c in p.children
            )
        if p.op == BoolOp.OR:
            return any(
                _walk(
                    c,
                    payload,
                    user_id,
                    user_attrs,
                    probe=probe,
                    fk_graph=fk_graph,
                    entity_name=entity_name,
                    schema=schema,
                )
                for c in p.children
            )
        if p.op == BoolOp.NOT:
            # Single-child NOT — invariant from BoolComposite.make().
            return not _walk(
                p.children[0],
                payload,
                user_id,
                user_attrs,
                probe=probe,
                fk_graph=fk_graph,
                entity_name=entity_name,
                schema=schema,
            )
        raise ScopeCreateUnsupportedError(f"Unknown BoolOp: {p.op!r}")
    if isinstance(p, ExistsCheck):
        # Junction-table predicate — resolve membership against the DB,
        # entity-side bindings sourced from the payload (#1311).
        if probe is None or fk_graph is None:
            raise ScopeCreateUnsupportedError(
                "ExistsCheck / NotExistsCheck (junction-table predicates) "
                "need a payload-time SQL probe but none was supplied. See "
                "#1311 and docs/reference/rbac-scope.md."
            )
        sql, raw_params = compile_exists_check_probe(p, entity_name, fk_graph, schema=schema)
        return _run_probe(sql, raw_params, payload, user_id, user_attrs, probe)
    if isinstance(p, PolyPathCheck):
        # #1455: poly_ref create/update scope. The discriminator is a pure-payload
        # check (the row's {field}_type must match the selected branch); the sub is
        # a payload-time probe against the target row the payload's {field}_id names.
        if payload.get(p.type_field) != p.type_value:
            return False
        if probe is None or fk_graph is None:
            raise ScopeCreateUnsupportedError(
                "PolyPathCheck needs a payload-time SQL probe but none was supplied. "
                "See #1455 and docs/reference/rbac-scope.md."
            )
        sql, raw_params = compile_poly_path_check_probe(p, entity_name, fk_graph, schema=schema)
        return _run_probe(sql, raw_params, payload, user_id, user_attrs, probe)
    raise ScopeCreateUnsupportedError(f"Unknown predicate kind: {type(p).__name__}")


def _run_probe(
    sql: str,
    raw_params: list[Any],
    payload: dict[str, Any],
    user_id: str,
    user_attrs: dict[str, Any],
    probe: ProbeFn,
) -> bool:
    """Resolve compiler markers to concrete values and run the probe.

    The compiler emits ``PayloadFieldRef`` / ``CurrentUserRef`` /
    ``UserAttrRef`` markers in place of literal params. We resolve them
    here (the walker already has the payload + user context) so the
    ``probe`` callable only ever sees plain SQL + scalar params.
    """
    resolved = [_resolve_marker(param, payload, user_id, user_attrs) for param in raw_params]
    return bool(probe(sql, resolved))


def _resolve_marker(
    param: Any,
    payload: dict[str, Any],
    user_id: str,
    user_attrs: dict[str, Any],
) -> Any:
    if isinstance(param, PayloadFieldRef):
        return _payload_value(payload, param.field_name)
    if isinstance(param, CurrentUserRef):
        # Resolve to the DSL User-entity id (`entity_id`), consistent with the
        # read/list/update/delete scope path (`_resolve_predicate_filters`) and
        # the simple-leaf `current_user` → UserAttrCheck(entity_id) mapping —
        # so the same DSL token binds the same principal everywhere. A junction
        # FK (`via M(user = current_user, ...)`) holds the domain User-entity
        # id, not the auth UserRecord id, and those differ when auth ≠ entity.
        # Fall back to the auth user id when entity_id is unresolvable (tests,
        # or apps where the two coincide by convention). `_LazyUserAttrs.get`
        # routes through lazy `_resolve_user_attribute`; a plain dict returns
        # None and falls back.
        entity_id = user_attrs.get("entity_id")
        return entity_id if entity_id is not None else user_id
    if isinstance(param, CurrentTenantRef):
        # #1394: host-resolved tenant id, bound as a probe SQL parameter. None
        # (no host tenant) → the probe's `= %s` / `IN (%s)` sees SQL NULL → no
        # match → the create is refused rather than left unfenced (fail-closed).
        from dazzle.http.runtime.tenant_isolation import get_current_host_tenant_id

        return get_current_host_tenant_id()
    if isinstance(param, UserAttrRef):
        # `entity_id` is the `current_user` self-id sentinel (predicate_builder maps
        # `= current_user` → UserAttrCheck(user_attr="entity_id")). Resolve it like
        # CurrentUserRef — entity_id attr, falling back to the auth user id — so a
        # bare `current_user` inside a probe (e.g. a poly_ref sub, #1455) binds the
        # principal even when entity_id isn't in user_attrs.
        if param.attr_name == "entity_id":
            entity_id = user_attrs.get("entity_id")
            return entity_id if entity_id is not None else user_id
        # `dict.get` on `_LazyUserAttrs` routes through lazy resolution.
        return user_attrs.get(param.attr_name)
    return param


def _payload_value(payload: dict[str, Any], field: str) -> Any:
    """Read ``field`` from the create payload, tolerating ref-name variants.

    The compiler resolves an FK to the column name in the FK graph
    (``teaching_group_id``), but a payload built from a Pydantic input
    schema may key it under the relation name (``teaching_group``) — or
    vice-versa. Mirror the ``_resolve_segment`` / ``_resolve_field_on_entity``
    heuristics: try the exact name, then the ``_id`` add/strip variant.
    A genuinely-absent value returns None → the probe's ``%s IN (…)`` /
    ``= %s`` sees NULL → no match → fail-closed.
    """
    if field in payload:
        return payload.get(field)
    if field.endswith("_id"):
        bare = field[: -len("_id")]
        if bare in payload:
            return payload.get(bare)
    elif f"{field}_id" in payload:
        return payload.get(f"{field}_id")
    return None


# A right-hand sentinel that no payload value can ever equal, so a comparison
# against it fails closed (#1394). Used when `current_tenant` is referenced but
# no host tenant is bound: returning Python None would let `None == None` MATCH
# when the payload field is also absent (fail-OPEN). The sentinel makes the
# create-scope EQ comparison always False → deny.
_CT_DENY = object()


def _resolve_value(value: ValueRef, user_id: str, user_attrs: dict[str, Any]) -> Any:
    """Resolve a ValueRef to a concrete Python value for comparison.

    Per the IR, exactly one of ``literal`` / ``current_user`` / ``current_tenant``
    / ``user_attr`` / ``literal_null`` is set:

    - ``current_user=True``   → the authenticated user's PK
    - ``current_tenant=True`` → the host-resolved tenant id (#1394), or the
      deny-sentinel ``_CT_DENY`` when no host tenant is bound so the comparison
      fails closed even if the payload field is also absent
    - ``user_attr="X"``       → ``user_attrs[X]`` (None when missing)
    - ``literal_null=True``   → Python None (SQL NULL literal)
    - ``literal=<scalar>``    → pass through
    """
    if value.current_user:
        return user_id
    if value.current_tenant:
        from dazzle.http.runtime.tenant_isolation import get_current_host_tenant_id

        host_tid = get_current_host_tenant_id()
        return host_tid if host_tid else _CT_DENY
    if value.user_attr:
        return user_attrs.get(value.user_attr)
    if value.literal_null:
        return None
    return value.literal


def _compare(left: Any, op: CompOp, right: Any) -> bool:
    """Apply a comparison operator. None values short-circuit to
    False for equality (mirrors SQL's `NULL = X` → NULL → false in
    a WHERE clause) and to False for ordering comparisons (we don't
    want a missing payload field to silently match an ordering
    predicate)."""
    # #1394: the unresolvable-`current_tenant` deny sentinel fails closed for
    # EVERY operator, not just EQ. Without this, `field != current_tenant` with
    # no host tenant would be `left != _CT_DENY` → always True → fail OPEN.
    if left is _CT_DENY or right is _CT_DENY:
        return False
    if op == CompOp.EQ:
        return bool(left == right)
    if op == CompOp.NEQ:
        return bool(left != right)
    if op == CompOp.IS:
        return left is right
    if op == CompOp.IS_NOT:
        return left is not right
    if op == CompOp.IN:
        try:
            return left in (right or ())
        except TypeError:
            return False
    if op == CompOp.NOT_IN:
        try:
            return left not in (right or ())
        except TypeError:
            return False
    if left is None or right is None:
        # Ordering comparisons against None: deny.
        return False
    try:
        if op == CompOp.LT:
            return bool(left < right)
        if op == CompOp.LTE:
            return bool(left <= right)
        if op == CompOp.GT:
            return bool(left > right)
        if op == CompOp.GTE:
            return bool(left >= right)
    except TypeError:
        # Incomparable types (e.g. str vs int) — deny.
        return False
    raise ScopeCreateUnsupportedError(f"Unknown CompOp: {op!r}")


__all__ = [
    "ProbeFn",
    "ScopeCreateUnsupportedError",
    "check_create_predicate",
]
