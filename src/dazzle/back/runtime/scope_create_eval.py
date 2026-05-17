"""Python-side evaluator for ``scope: create:`` predicates (#1124).

Unlike list/read/update/delete enforcement (which compiles the
predicate to SQL and folds it into a WHERE clause), `create` has no
existing row to filter against — there's a payload waiting to become
a row. The natural semantic is "the inserted row must satisfy the
predicate", evaluated against the payload AFTER framework defaulting
runs (e.g. after `inject_current_user_refs` injects ``current_user``
into a missing ``created_by`` field).

v1 (this module) supports the simple-predicate subset:

- ``ColumnCheck`` — ``field op literal``
- ``UserAttrCheck`` — ``field op current_user.attr`` (or bare
  ``current_user`` == auth user id)
- ``PathCheck`` depth 1 — equivalent to ColumnCheck (single column,
  no FK traversal)
- ``Tautology`` / ``Contradiction`` — constants (``scope: all`` /
  guard rejects)
- ``BoolComposite`` (``and`` / ``or`` / ``not``) — recurses

PathCheck with depth > 1 (FK-path predicates) and ExistsCheck /
NotExistsCheck (junction-table predicates) are NOT supported in v1
and the linker rejects them at link time with a clear message. Those
cases need a payload-time SQL probe; deferred until adoption signal
indicates the additional roundtrip-per-create is worth the
implementation work.

The walker is intentionally narrow — it only traverses the predicate
algebra, no SQL, no DB roundtrip. Raising on encountering an
unsupported predicate shape is a defensive backstop (the linker
should already have caught it).
"""

from __future__ import annotations

from typing import Any

from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    Contradiction,
    ExistsCheck,
    PathCheck,
    ScopePredicate,
    Tautology,
    UserAttrCheck,
    ValueRef,
)


class ScopeCreateUnsupportedError(Exception):
    """Raised when the predicate contains a shape that v1 can't process.

    Should NOT happen in practice — the linker (`linker._validate_scope_create_rules`)
    rejects unsupported shapes at link time with a clear message
    pointing to docs. This exception is a defensive backstop for the
    case where IR construction bypasses the linker (tests, fixtures,
    programmatic predicate construction).
    """


def check_create_predicate(
    predicate: ScopePredicate,
    payload: dict[str, Any],
    *,
    user_id: str,
    user_attrs: dict[str, Any] | None = None,
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

    Raises:
        ScopeCreateUnsupportedError: if the predicate contains a shape
        v1 doesn't support (FK-path depth > 1, ExistsCheck, etc.).
        These should be caught at link time; this exception is a
        defensive backstop.
    """
    user_attrs = user_attrs or {}
    return _walk(predicate, payload, user_id, user_attrs)


def _walk(
    p: ScopePredicate,
    payload: dict[str, Any],
    user_id: str,
    user_attrs: dict[str, Any],
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
            # FK-path predicates — v1 rejects at link time. Defensive.
            raise ScopeCreateUnsupportedError(
                "PathCheck with depth > 1 is not supported on scope: create: "
                f"in v1 (path={p.path!r}). The linker should have rejected "
                "this at link time. See #1124 and docs/reference/rbac-scope.md."
            )
        # Depth 1 = single column, equivalent to ColumnCheck.
        return _compare(payload.get(p.path[0]), p.op, _resolve_value(p.value, user_id, user_attrs))
    if isinstance(p, BoolComposite):
        if p.op == BoolOp.AND:
            return all(_walk(c, payload, user_id, user_attrs) for c in p.children)
        if p.op == BoolOp.OR:
            return any(_walk(c, payload, user_id, user_attrs) for c in p.children)
        if p.op == BoolOp.NOT:
            # Single-child NOT — invariant from BoolComposite.make().
            return not _walk(p.children[0], payload, user_id, user_attrs)
        raise ScopeCreateUnsupportedError(f"Unknown BoolOp: {p.op!r}")
    if isinstance(p, ExistsCheck):
        # Junction-table predicates — v1 rejects at link time. Defensive.
        raise ScopeCreateUnsupportedError(
            "ExistsCheck / NotExistsCheck (junction-table predicates) "
            "are not supported on scope: create: in v1. The linker "
            "should have rejected this at link time. See #1124 and "
            "docs/reference/rbac-scope.md."
        )
    raise ScopeCreateUnsupportedError(f"Unknown predicate kind: {type(p).__name__}")


def _resolve_value(value: ValueRef, user_id: str, user_attrs: dict[str, Any]) -> Any:
    """Resolve a ValueRef to a concrete Python value for comparison.

    Per the IR, exactly one of ``literal`` / ``current_user`` /
    ``user_attr`` / ``literal_null`` is set:

    - ``current_user=True`` → the authenticated user's PK
    - ``user_attr="X"``     → ``user_attrs[X]`` (None when missing)
    - ``literal_null=True`` → Python None (SQL NULL literal)
    - ``literal=<scalar>``  → pass through
    """
    if value.current_user:
        return user_id
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
    "ScopeCreateUnsupportedError",
    "check_create_predicate",
]
