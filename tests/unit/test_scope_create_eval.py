"""Unit tests for `dazzle.http.runtime.scope_create_eval` (#1124, #1311).

The simple-predicate subset (ColumnCheck, UserAttrCheck, PathCheck
depth 1, Tautology / Contradiction, BoolComposite over those) is
evaluated in pure Python against the payload — covered here.

FK-path (depth > 1) and ExistsCheck predicates resolve via a
payload-time SQL probe (#1311); the probe machinery is covered in
`test_scope_create_probe.py`. When NO probe is supplied (as in the
backstop tests below), those shapes raise ScopeCreateUnsupportedError
rather than silently passing un-enforced.
"""

from __future__ import annotations

import pytest

from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    Contradiction,
    ExistsBinding,
    ExistsCheck,
    PathCheck,
    Tautology,
    UserAttrCheck,
    ValueRef,
)
from dazzle.http.runtime.scope_create_eval import (
    ScopeCreateUnsupportedError,
    check_create_predicate,
)

# ---------------------------------------------------------------------------
# UserAttrCheck — the most common shape (`created_by = current_user`)
# ---------------------------------------------------------------------------


def test_user_attr_check_passes_when_field_equals_user_id() -> None:
    p = UserAttrCheck(field="created_by", op=CompOp.EQ, user_attr="id")
    assert check_create_predicate(p, {"created_by": "u-1"}, user_id="u-1") is True


def test_user_attr_check_rejects_when_field_does_not_equal_user_id() -> None:
    p = UserAttrCheck(field="created_by", op=CompOp.EQ, user_attr="id")
    assert check_create_predicate(p, {"created_by": "u-2"}, user_id="u-1") is False


def test_user_attr_check_resolves_named_user_attribute() -> None:
    """`school_id = current_user.school as: teacher` — payload's
    `school_id` must equal `auth_user.school`."""
    p = UserAttrCheck(field="school_id", op=CompOp.EQ, user_attr="school")
    assert (
        check_create_predicate(
            p,
            {"school_id": "school-42"},
            user_id="u-1",
            user_attrs={"school": "school-42"},
        )
        is True
    )
    assert (
        check_create_predicate(
            p,
            {"school_id": "school-99"},
            user_id="u-1",
            user_attrs={"school": "school-42"},
        )
        is False
    )


def test_user_attr_check_missing_attr_rejects() -> None:
    """If the auth context doesn't carry the named attribute, the
    predicate evaluates against None — never matches a non-None
    payload field, so it rejects."""
    p = UserAttrCheck(field="school_id", op=CompOp.EQ, user_attr="school")
    assert (
        check_create_predicate(p, {"school_id": "school-42"}, user_id="u-1", user_attrs={}) is False
    )


# ---------------------------------------------------------------------------
# ColumnCheck — `status = "draft" as: member`
# ---------------------------------------------------------------------------


def test_column_check_literal_eq() -> None:
    p = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="draft"))
    assert check_create_predicate(p, {"status": "draft"}, user_id="u-1") is True
    assert check_create_predicate(p, {"status": "published"}, user_id="u-1") is False


def test_column_check_with_current_user_value_ref() -> None:
    """`owner = current_user` expressed as a ColumnCheck with a
    current_user ValueRef — same shape as UserAttrCheck, validate
    both code paths."""
    p = ColumnCheck(field="owner", op=CompOp.EQ, value=ValueRef(current_user=True))
    assert check_create_predicate(p, {"owner": "u-1"}, user_id="u-1") is True
    assert check_create_predicate(p, {"owner": "u-2"}, user_id="u-1") is False


def test_column_check_neq() -> None:
    p = ColumnCheck(field="status", op=CompOp.NEQ, value=ValueRef(literal="archived"))
    assert check_create_predicate(p, {"status": "draft"}, user_id="u-1") is True
    assert check_create_predicate(p, {"status": "archived"}, user_id="u-1") is False


def test_column_check_missing_field_rejects_on_eq() -> None:
    """Payload doesn't have the field at all → predicate sees None →
    None == literal is False."""
    p = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="draft"))
    assert check_create_predicate(p, {}, user_id="u-1") is False


# ---------------------------------------------------------------------------
# PathCheck depth 1 — equivalent to ColumnCheck
# ---------------------------------------------------------------------------


def test_path_check_depth_one_passes() -> None:
    p = PathCheck(path=["status"], op=CompOp.EQ, value=ValueRef(literal="draft"))
    assert check_create_predicate(p, {"status": "draft"}, user_id="u-1") is True


def test_path_check_depth_two_without_probe_raises() -> None:
    """A depth>1 FK-path predicate needs a payload-time probe (#1311).
    With no probe supplied, the walker raises rather than passing an
    un-enforced predicate — a defensive backstop. (With a probe it is
    supported; see test_scope_create_probe.py.)"""
    p = PathCheck(
        path=["manuscript", "school_id"], op=CompOp.EQ, value=ValueRef(literal="school-42")
    )
    with pytest.raises(ScopeCreateUnsupportedError, match="depth > 1"):
        check_create_predicate(p, {"manuscript": "m-1"}, user_id="u-1")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_tautology_always_passes() -> None:
    """`scope: all` compiles to a Tautology — always allows."""
    assert check_create_predicate(Tautology(), {}, user_id="u-1") is True


def test_contradiction_always_rejects() -> None:
    """Contradiction is the algebraic constant FALSE — always rejects."""
    assert check_create_predicate(Contradiction(), {"status": "draft"}, user_id="u-1") is False


# ---------------------------------------------------------------------------
# BoolComposite (and / or / not)
# ---------------------------------------------------------------------------


def _user_eq() -> UserAttrCheck:
    return UserAttrCheck(field="owner", op=CompOp.EQ, user_attr="id")


def _status_draft() -> ColumnCheck:
    return ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="draft"))


def test_bool_composite_and_passes_when_both_pass() -> None:
    p = BoolComposite.make(BoolOp.AND, [_user_eq(), _status_draft()])
    assert check_create_predicate(p, {"owner": "u-1", "status": "draft"}, user_id="u-1") is True


def test_bool_composite_and_rejects_when_either_fails() -> None:
    p = BoolComposite.make(BoolOp.AND, [_user_eq(), _status_draft()])
    # owner mismatches
    assert check_create_predicate(p, {"owner": "u-2", "status": "draft"}, user_id="u-1") is False
    # status mismatches
    assert (
        check_create_predicate(p, {"owner": "u-1", "status": "published"}, user_id="u-1") is False
    )


def test_bool_composite_or_passes_when_either_passes() -> None:
    p = BoolComposite.make(BoolOp.OR, [_user_eq(), _status_draft()])
    # only owner matches
    assert check_create_predicate(p, {"owner": "u-1", "status": "published"}, user_id="u-1") is True
    # only status matches
    assert check_create_predicate(p, {"owner": "u-2", "status": "draft"}, user_id="u-1") is True


def test_bool_composite_or_rejects_when_both_fail() -> None:
    p = BoolComposite.make(BoolOp.OR, [_user_eq(), _status_draft()])
    assert (
        check_create_predicate(p, {"owner": "u-2", "status": "published"}, user_id="u-1") is False
    )


def test_bool_composite_not_inverts() -> None:
    p = BoolComposite.make(BoolOp.NOT, [_status_draft()])
    assert check_create_predicate(p, {"status": "published"}, user_id="u-1") is True
    assert check_create_predicate(p, {"status": "draft"}, user_id="u-1") is False


# ---------------------------------------------------------------------------
# Defensive backstops — unsupported shapes raise at runtime if IR
# bypassed the linker (programmatic predicate construction, fixtures).
# ---------------------------------------------------------------------------


def test_exists_check_without_probe_raises() -> None:
    """An ExistsCheck needs a payload-time probe (#1311). With no probe
    supplied, the walker raises rather than passing un-enforced. (With a
    probe it is supported; see test_scope_create_probe.py.)"""
    p = ExistsCheck(
        target_entity="TeamMembership",
        bindings=[
            ExistsBinding(junction_field="user_id", target="current_user"),
            ExistsBinding(junction_field="team_id", target="id"),
        ],
    )
    with pytest.raises(ScopeCreateUnsupportedError, match="ExistsCheck"):
        check_create_predicate(p, {"team_id": "t-1"}, user_id="u-1")
