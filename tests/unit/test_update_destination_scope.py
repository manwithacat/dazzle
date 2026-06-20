"""Tests for `scope: update:` DESTINATION re-validation (#1312, ADR-0028).

The pre-read validates the *source* row; `_enforce_update_scope` re-validates
the row's would-be-final state (existing ⊕ changed fields) so an update can't
repoint an FK to move the row INTO a foreign scope. Denial is an IDOR-shaped
404 (indistinguishable from a missing row), not a 403.

These exercise the route-level enforcer directly with lightweight stubs (it
reads the access spec / rules via ``getattr``). The shared predicate evaluator
— including the FK-path / EXISTS payload-time probe — is covered in
`test_scope_create_probe.py`; here we focus on the update-specific logic:
operation filtering, the existing⊕new merge, and 404-on-denial.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException

from dazzle.core.ir.predicates import CompOp, UserAttrCheck
from dazzle.http.runtime.route_generator import _enforce_update_scope


def _spec(rules: list) -> SimpleNamespace:
    return SimpleNamespace(scopes=rules)


def _update_rule(predicate=None, personas=("member",), condition=None) -> SimpleNamespace:
    return SimpleNamespace(
        operation="update",
        personas=list(personas),
        predicate=predicate,
        condition=condition,
    )


# `created_by = current_user` — resolves to user_id (no auth_context needed).
def _owner_rule() -> SimpleNamespace:
    return _update_rule(UserAttrCheck(field="created_by", op=CompOp.EQ, user_attr="id"))


def _enforce(spec, existing, new_values, *, user_id="u-1", roles=("member",)) -> None:
    _enforce_update_scope(
        cedar_access_spec=spec,
        existing=existing,
        new_values=new_values,
        user_id=user_id,
        user_roles=list(roles),
        entity_name="Task",
        auth_context=None,
    )


# ---------------------------------------------------------------------------
# No-op cases
# ---------------------------------------------------------------------------


def test_no_access_spec_is_noop() -> None:
    _enforce(None, {"created_by": "u-9"}, {"created_by": "u-9"})  # no raise


def test_no_update_rules_is_noop() -> None:
    # A create rule exists but no update rule — update destination unguarded.
    create_rule = SimpleNamespace(
        operation="create", personas=["member"], predicate=None, condition=None
    )
    _enforce(_spec([create_rule]), {"created_by": "u-9"}, {"title": "x"})  # no raise


def test_matched_all_rule_is_noop() -> None:
    # `scope: update: all as: member` → predicate None → unrestricted.
    _enforce(_spec([_update_rule(predicate=None)]), {"created_by": "u-9"}, {"created_by": "u-9"})


# ---------------------------------------------------------------------------
# Destination enforcement
# ---------------------------------------------------------------------------


def test_untouched_scope_key_keeps_existing_value_and_allows() -> None:
    """A partial update that doesn't touch the scope key uses the existing
    (already-validated) value — the row stays in scope, allow."""
    _enforce(
        _spec([_owner_rule()]),
        existing={"created_by": "u-1", "title": "old"},
        new_values={"title": "new"},  # created_by untouched
    )  # no raise — merged created_by stays "u-1" == user_id


def test_repoint_fk_into_foreign_scope_is_denied_404() -> None:
    """Repointing the scope key to a foreign value → 404 (the #1312 hole)."""
    with pytest.raises(HTTPException) as exc:
        _enforce(
            _spec([_owner_rule()]),
            existing={"created_by": "u-1", "title": "old"},
            new_values={"created_by": "u-2"},  # move to another owner
        )
    assert exc.value.status_code == 404


def test_repoint_fk_to_own_scope_is_allowed() -> None:
    """Setting the scope key back to the caller's own value → allow."""
    _enforce(
        _spec([_owner_rule()]),
        existing={"created_by": "u-1"},
        new_values={"created_by": "u-1"},
    )  # no raise


def test_no_matching_rule_for_role_denies_404() -> None:
    """Update rules exist but none matches the caller's role → 404."""
    with pytest.raises(HTTPException) as exc:
        _enforce(
            _spec([_owner_rule()]),
            existing={"created_by": "u-1"},
            new_values={"created_by": "u-1"},
            roles=("viewer",),  # not 'member'
        )
    assert exc.value.status_code == 404


def test_existing_pydantic_model_is_normalised() -> None:
    """`existing` may be a Pydantic-style model — _row_to_payload_dict handles
    it via model_dump so the merge sees the existing scope-key value."""
    model_like = SimpleNamespace(model_dump=lambda mode=None: {"created_by": "u-1"})
    _enforce(
        _spec([_owner_rule()]),
        existing=model_like,
        new_values={"title": "new"},
    )  # no raise — model's created_by="u-1" survives the merge


def test_fk_path_destination_without_probe_fails_closed_404() -> None:
    """An FK-path update rule with no service/DB to probe → fail-closed 404
    (rather than allowing an un-enforced destination)."""
    from dazzle.core.ir.predicates import PathCheck, ValueRef

    fk_rule = _update_rule(
        PathCheck(
            path=["team", "department"],
            op=CompOp.EQ,
            value=ValueRef(user_attr="department"),
        )
    )
    with pytest.raises(HTTPException) as exc:
        # service defaults to None → build_create_scope_probe returns None →
        # the walker raises ScopeCreateUnsupportedError → caught → 404.
        _enforce(_spec([fk_rule]), existing={"team": "t-1"}, new_values={"team": "t-2"})
    assert exc.value.status_code == 404
