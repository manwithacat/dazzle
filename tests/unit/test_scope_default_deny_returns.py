"""Scope resolution must fail closed: `{}` means "all rows", never "unknown".

Why this exists
---------------
``_resolve_scope_filters`` returns either a filter dict, ``{}`` (no restriction)
or ``None`` (deny). Callers branch on it like this::

    if scope_result is None:  return None          # default-deny
    if not scope_result:      unscoped_read(...)    # EVERY row

So ``{}`` is not a neutral value — it is the *most permissive* outcome. The
function's final fall-through used to return ``{}`` for "a rule matched but
produced no resolvable filter" (e.g. a predicate with no ``fk_graph``, so
neither the predicate-compiler path nor the legacy condition-tree path can
run). That silently escalated an unresolvable scope into unrestricted row
access, while every adjacent failure path in the same function denied (#617).

What this catches
-----------------
A return-value that is more permissive than the reason for reaching it. Each row
of the matrix below is a distinct request shape with a single defensible
expected value; the two ``{}`` rows are the only legitimate permissive exits and
both are reached *before* the fall-through.

How to satisfy it
-----------------
When a matched rule cannot be resolved to a filter, ``return None``. Reserve
``{}`` for `scope: all` and for entities that declare no scopes at all.

What this does NOT catch
------------------------
Whether the *content* of a resolved filter is correct (wrong column, wrong
operator) — that is behavioural and belongs with the fk_graph-backed
resolution tests. This gate is about the return contract only.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.http.runtime.scope_filters import _resolve_scope_filters

pytestmark = pytest.mark.gate


def _rule(
    *,
    operation: str = "list",
    personas: tuple[str, ...] = ("student",),
    condition: Any = None,
    predicate: Any = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        operation=SimpleNamespace(value=operation),
        personas=list(personas),
        condition=condition,
        predicate=predicate,
    )


def _spec(*rules: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(scopes=list(rules))


def _resolve(spec: Any, **kwargs: Any) -> dict[str, Any] | None:
    params: dict[str, Any] = {
        "operation": "list",
        "user_roles": {"student"},
        "user_id": "u1",
        "entity_name": "Enrollment",
    }
    params.update(kwargs)
    return _resolve_scope_filters(spec, **params)


def test_entity_with_no_scopes_is_unscoped() -> None:
    """No `scope:` blocks at all — the permit gate owns access, so no row
    filter. Documented at the top of the resolver."""
    assert _resolve(_spec()) == {}


def test_scope_all_returns_unscoped() -> None:
    """`scope: all` (no condition, no predicate) is the one legitimate
    permissive exit, handled before the fall-through."""
    assert _resolve(_spec(_rule())) == {}


def test_tautology_predicate_is_scope_all() -> None:
    """A Tautology predicate is `scope: all` expressed the other way."""
    assert _resolve(_spec(_rule(predicate=SimpleNamespace(kind="tautology")))) == {}


def test_no_matching_rule_denies() -> None:
    """A different operation means no rule matched — deny."""
    assert _resolve(_spec(_rule(operation="read")), operation="list") is None


def test_role_mismatch_denies() -> None:
    """The user holds none of the rule's personas — deny, do not fall through
    to a permissive default."""
    assert _resolve(_spec(_rule(personas=("teacher",)))) is None


def test_predicate_without_fk_graph_denies() -> None:
    """The regression: a matched predicate with no fk_graph cannot be compiled,
    and there is no condition to fall back on. That is a resolution failure and
    must deny — returning {} here means an unscoped read of every row."""
    result = _resolve(
        _spec(_rule(predicate=SimpleNamespace(kind="compare"))),
        fk_graph=None,
    )
    assert result is None, (
        f"unresolvable scope rule returned {result!r}; {{}} is read by callers as "
        "'no row restriction', so this silently escalates to unrestricted access"
    )


def test_resolvable_condition_still_filters() -> None:
    """Guard the fix: a rule that CAN resolve must keep returning a real filter,
    not start denying. Uses a well-formed `AccessConditionSpec` comparison
    (`kind="comparison"`), which is the shape `_extract_condition_filters`
    recognises — a `field`/`op` SimpleNamespace would match no branch and would
    not exercise the path at all."""
    spec = _spec(
        _rule(
            condition=SimpleNamespace(
                kind="comparison",
                field="owner_id",
                value="current_user",
                comparison_op=None,
            )
        )
    )
    result = _resolve(spec)
    assert result is not None, "a resolvable condition must not be denied"
    assert result != {}, (
        "a resolvable condition must not degrade to an unscoped read; {} means "
        "'no row restriction' to every caller"
    )
