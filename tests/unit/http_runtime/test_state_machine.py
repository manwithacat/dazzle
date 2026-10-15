"""Tests for state machine runtime validation."""

import pytest

from dazzle.http.runtime.state_machine import (
    GuardNotSatisfiedError,
    InvalidTransitionError,
    TransitionValidator,
    evaluate_guard_expr,
    validate_status_update,
)
from dazzle.http.specs.entity import (
    AutoTransitionSpec,
    StateMachineSpec,
    StateTransitionSpec,
    TimeUnit,
    TransitionGuardSpec,
)


def _sm(
    states: list[str], *edges: tuple[str, str], guards: list[TransitionGuardSpec] | None = None
) -> StateMachineSpec:
    """A status state machine; ``guards`` attach to every edge."""
    return StateMachineSpec(
        status_field="status",
        states=states,
        transitions=[
            StateTransitionSpec(from_state=a, to_state=b, guards=list(guards or []))
            for a, b in edges
        ],
    )


_REQUIRES_ASSIGNEE = [TransitionGuardSpec(requires_field="assignee")]
_REQUIRES_EDITOR = [TransitionGuardSpec(requires_role="editor")]
_FOUR_EYE = TransitionGuardSpec(
    guard_expr={"op": "!=", "left": {"path": ["reviewer"]}, "right": {"path": ["preparer"]}},
    guard_message="Reviewer must differ from the preparer (four-eye rule)",
)

# =============================================================================
# TransitionValidator
# =============================================================================


@pytest.mark.parametrize(
    ("sm", "from_state", "to_state", "data", "roles"),
    [
        pytest.param(
            _sm(["open", "assigned"], ("open", "assigned")),
            "open",
            "assigned",
            {},
            None,
            id="declared-edge",
        ),
        pytest.param(
            _sm(["draft", "published", "archived"], ("draft", "published"), ("*", "draft")),
            "published",
            "draft",
            {},
            None,
            id="wildcard-from-published",
        ),
        pytest.param(
            _sm(["draft", "published", "archived"], ("draft", "published"), ("*", "draft")),
            "archived",
            "draft",
            {},
            None,
            id="wildcard-from-archived",
        ),
        pytest.param(
            _sm(["open", "assigned"], ("open", "assigned"), guards=_REQUIRES_ASSIGNEE),
            "open",
            "assigned",
            {"assignee": "john@example.com"},
            None,
            id="requires-field-present",
        ),
        pytest.param(
            _sm(["draft", "published"], ("draft", "published"), guards=_REQUIRES_EDITOR),
            "draft",
            "published",
            {},
            ["editor"],
            id="requires-role-held",
        ),
        pytest.param(
            _sm(["open", "closed"], ("open", "closed")),
            "open",
            "open",
            {},
            None,
            id="unchanged-state-is-a-no-op",
        ),
    ],
)
def test_transition_accepted(sm, from_state, to_state, data, roles) -> None:
    result = TransitionValidator(sm).validate_transition(
        from_state, to_state, data, user_roles=roles
    )
    assert result.is_valid
    assert result.error is None


def test_declared_edge_returns_its_transition() -> None:
    sm = _sm(["open", "assigned"], ("open", "assigned"), ("assigned", "open"))
    result = TransitionValidator(sm).validate_transition("open", "assigned", {})
    assert result.transition is not None
    assert (result.transition.from_state, result.transition.to_state) == ("open", "assigned")


def test_undeclared_edge_is_invalid_transition() -> None:
    sm = _sm(["open", "assigned", "resolved"], ("open", "assigned"), ("assigned", "resolved"))
    result = TransitionValidator(sm).validate_transition("open", "resolved", {})
    assert not result.is_valid
    assert isinstance(result.error, InvalidTransitionError)
    assert (result.error.from_state, result.error.to_state) == ("open", "resolved")
    assert "assigned" in result.error.allowed_states


@pytest.mark.parametrize(
    ("guards", "data", "roles", "guard_type", "guard_value"),
    [
        pytest.param(
            _REQUIRES_ASSIGNEE, {"assignee": None}, None, "requires", "assignee", id="field-none"
        ),
        pytest.param(
            _REQUIRES_ASSIGNEE,
            {"assignee": ""},
            None,
            "requires",
            "assignee",
            id="field-empty-string",
        ),
        pytest.param(_REQUIRES_EDITOR, {}, ["viewer"], "role", "editor", id="role-missing"),
    ],
)
def test_guard_rejects(guards, data, roles, guard_type, guard_value) -> None:
    sm = _sm(["a", "b"], ("a", "b"), guards=guards)
    result = TransitionValidator(sm).validate_transition("a", "b", data, user_roles=roles)
    assert not result.is_valid
    assert isinstance(result.error, GuardNotSatisfiedError)
    assert (result.error.guard_type, result.error.guard_value) == (guard_type, guard_value)


# =============================================================================
# validate_status_update
# =============================================================================


@pytest.mark.parametrize(
    ("sm", "current", "update"),
    [
        pytest.param(None, {"status": "open"}, {"status": "closed"}, id="no-state-machine"),
        pytest.param(
            _sm(["open", "closed"], ("open", "closed")),
            {"status": "open", "title": "Test"},
            {"title": "Updated Test"},
            id="status-not-in-update",
        ),
    ],
)
def test_status_update_not_checked(sm, current, update) -> None:
    assert (
        validate_status_update(state_machine=sm, current_data=current, update_data=update) is None
    )


@pytest.mark.parametrize(
    ("sm", "current", "update", "error_type"),
    [
        pytest.param(
            _sm(["open", "closed"], ("open", "closed")),
            {"status": "open"},
            {"status": "closed"},
            None,
            id="declared-edge",
        ),
        pytest.param(
            _sm(["open", "assigned", "closed"], ("open", "assigned"), ("assigned", "closed")),
            {"status": "open"},
            {"status": "closed"},
            InvalidTransitionError,
            id="skipping-a-state-is-invalid",
        ),
        pytest.param(
            _sm(["draft", "published"], ("draft", "published")),
            {"status": None},
            {"status": "draft"},
            None,
            id="initial-status-declared",
        ),
        pytest.param(
            _sm(["draft", "published"], ("draft", "published")),
            {"status": None},
            {"status": "invalid_state"},
            InvalidTransitionError,
            id="initial-status-undeclared",
        ),
        pytest.param(
            _sm(["open", "assigned"], ("open", "assigned"), guards=_REQUIRES_ASSIGNEE),
            {"status": "open"},
            {"status": "assigned", "assignee": "john@example.com"},
            None,
            id="guard-sees-update-merged-over-current",
        ),
        pytest.param(
            _sm(["review", "closed"], ("review", "closed"), guards=[_FOUR_EYE]),
            {"status": "review", "reviewer": "alice", "preparer": "bob"},
            {"status": "closed"},
            None,
            id="expr-guard-passes",
        ),
        pytest.param(
            _sm(["review", "closed"], ("review", "closed"), guards=[_FOUR_EYE]),
            {"status": "review", "reviewer": "alice", "preparer": "alice"},
            {"status": "closed"},
            GuardNotSatisfiedError,
            id="expr-guard-fails",
        ),
    ],
)
def test_status_update(sm, current, update, error_type) -> None:
    result = validate_status_update(state_machine=sm, current_data=current, update_data=update)
    assert result is not None
    assert result.is_valid is (error_type is None)
    if error_type is not None:
        assert isinstance(result.error, error_type)


# =============================================================================
# StateMachineSpec helpers
# =============================================================================


def test_spec_transition_queries() -> None:
    sm = _sm(["a", "b", "c"], ("a", "b"), ("a", "c"), ("b", "c"))
    assert {t.to_state for t in sm.get_transitions_from("a")} == {"b", "c"}
    assert len(sm.get_transitions_from("a")) == 2
    assert sm.get_allowed_targets("a") == {"b", "c"}
    assert sm.is_transition_allowed("a", "b") is True
    assert sm.is_transition_allowed("c", "a") is False
    t = sm.get_transition("a", "b")
    assert t is not None and (t.from_state, t.to_state) == ("a", "b")
    assert sm.get_transition("b", "a") is None


@pytest.mark.parametrize(
    ("value", "unit", "seconds"),
    [
        pytest.param(5, TimeUnit.MINUTES, 300, id="minutes"),
        pytest.param(2, TimeUnit.HOURS, 7200, id="hours"),
        pytest.param(7, TimeUnit.DAYS, 604800, id="days"),
    ],
)
def test_auto_transition_delay_seconds(value, unit, seconds) -> None:
    assert AutoTransitionSpec(delay_value=value, delay_unit=unit).delay_seconds == seconds


# =============================================================================
# evaluate_guard_expr
# =============================================================================


def _path(*p: str) -> dict:
    return {"path": list(p)}


def _lit(v: object) -> dict:
    return {"value": v}


def _bin(op: str, left: dict, right: dict) -> dict:
    return {"op": op, "left": left, "right": right}


_REVIEWER_NE_PREPARER = _bin("!=", _path("reviewer"), _path("preparer"))
_STATUS_IS_COMPLETED = _bin("==", _path("status"), _lit("completed"))
_AML_COMPLETED = _bin("==", _path("self", "contact", "aml_status"), _lit("completed"))
_FOUR_EYE_AND_REVIEW = _bin(
    "and", _REVIEWER_NE_PREPARER, _bin("==", _path("status"), _lit("review"))
)
_ADMIN_OR_MANAGER = _bin(
    "or", _bin("==", _path("role"), _lit("admin")), _bin("==", _path("role"), _lit("manager"))
)
_NOT_LOCKED = {"op": "not", "operand": _path("is_locked")}
_AMOUNT_POSITIVE = _bin(">", _path("amount"), _lit(0))
_REVIEWER_SET = _bin("!=", _path("reviewer"), _lit(None))
_STATUS_IN = {
    "value": _path("status"),
    "items": [_lit("approved"), _lit("verified")],
    "negated": False,
}
_STATUS_NOT_IN = {
    "value": _path("status"),
    "items": [_lit("draft"), _lit("cancelled")],
    "negated": True,
}


@pytest.mark.parametrize(
    ("expr", "data", "expected"),
    [
        pytest.param(
            _REVIEWER_NE_PREPARER,
            {"reviewer": "alice", "preparer": "bob"},
            True,
            id="field-ne-field.differ",
        ),
        pytest.param(
            _REVIEWER_NE_PREPARER,
            {"reviewer": "alice", "preparer": "alice"},
            False,
            id="field-ne-field.same",
        ),
        pytest.param(
            _bin("!=", _path("self", "reviewer"), _path("self", "preparer")),
            {"reviewer": "alice", "preparer": "bob"},
            True,
            id="self-prefix-stripped",
        ),
        pytest.param(
            _STATUS_IS_COMPLETED, {"status": "completed"}, True, id="field-eq-literal.match"
        ),
        pytest.param(
            _STATUS_IS_COMPLETED, {"status": "pending"}, False, id="field-eq-literal.miss"
        ),
        pytest.param(
            _AML_COMPLETED, {"contact": {"aml_status": "completed"}}, True, id="nested-path.match"
        ),
        pytest.param(
            _AML_COMPLETED, {"contact": {"aml_status": "pending"}}, False, id="nested-path.miss"
        ),
        pytest.param(
            _FOUR_EYE_AND_REVIEW,
            {"reviewer": "alice", "preparer": "bob", "status": "review"},
            True,
            id="and.both-true",
        ),
        pytest.param(
            _FOUR_EYE_AND_REVIEW,
            {"reviewer": "alice", "preparer": "alice", "status": "review"},
            False,
            id="and.left-false",
        ),
        pytest.param(_ADMIN_OR_MANAGER, {"role": "admin"}, True, id="or.left-true"),
        pytest.param(_ADMIN_OR_MANAGER, {"role": "manager"}, True, id="or.right-true"),
        pytest.param(_ADMIN_OR_MANAGER, {"role": "viewer"}, False, id="or.neither"),
        pytest.param(_NOT_LOCKED, {"is_locked": False}, True, id="not.false-operand"),
        pytest.param(_NOT_LOCKED, {"is_locked": True}, False, id="not.true-operand"),
        pytest.param(_AMOUNT_POSITIVE, {"amount": 100}, True, id="gt.above"),
        pytest.param(_AMOUNT_POSITIVE, {"amount": 0}, False, id="gt.equal"),
        pytest.param(_AMOUNT_POSITIVE, {"amount": -5}, False, id="gt.below"),
        pytest.param(_REVIEWER_SET, {"reviewer": "alice"}, True, id="ne-null.set"),
        pytest.param(_REVIEWER_SET, {"reviewer": None}, False, id="ne-null.none"),
        pytest.param(_REVIEWER_SET, {}, False, id="ne-null.missing-key"),
        pytest.param(_STATUS_IN, {"status": "approved"}, True, id="in.member"),
        pytest.param(_STATUS_IN, {"status": "pending"}, False, id="in.non-member"),
        pytest.param(_STATUS_NOT_IN, {"status": "active"}, True, id="not-in.non-member"),
        pytest.param(_STATUS_NOT_IN, {"status": "draft"}, False, id="not-in.member"),
        pytest.param(_lit(True), {}, True, id="literal-true"),
        pytest.param(_lit(False), {}, False, id="literal-false"),
    ],
)
def test_evaluate_guard_expr(expr, data, expected) -> None:
    assert evaluate_guard_expr(expr, data) is expected


# =============================================================================
# Expression guards inside TransitionValidator
# =============================================================================


def test_four_eye_expr_guard_rejects_same_person_with_custom_message() -> None:
    validator = TransitionValidator(
        _sm(["review", "closed"], ("review", "closed"), guards=[_FOUR_EYE])
    )
    assert validator.validate_transition(
        "review", "closed", {"reviewer": "alice", "preparer": "bob"}
    ).is_valid
    result = validator.validate_transition(
        "review", "closed", {"reviewer": "alice", "preparer": "alice"}
    )
    assert not result.is_valid
    assert isinstance(result.error, GuardNotSatisfiedError)
    assert result.error.guard_type == "expression"
    assert "Reviewer must differ from the preparer (four-eye rule)" in str(result.error)


def test_expr_guard_combined_with_field_guard() -> None:
    """Guards are checked in order: the field guard first, then the expression."""
    sm = _sm(
        ["review", "closed"],
        ("review", "closed"),
        guards=[TransitionGuardSpec(requires_field="reviewer"), _FOUR_EYE],
    )
    validator = TransitionValidator(sm)

    result = validator.validate_transition("review", "closed", {"preparer": "bob"})
    assert not result.is_valid
    assert result.error.guard_type == "requires"  # type: ignore[union-attr]

    result = validator.validate_transition(
        "review", "closed", {"reviewer": "alice", "preparer": "alice"}
    )
    assert not result.is_valid
    assert result.error.guard_type == "expression"  # type: ignore[union-attr]

    assert validator.validate_transition(
        "review", "closed", {"reviewer": "alice", "preparer": "bob"}
    ).is_valid


def test_expr_guard_default_message() -> None:
    guard = TransitionGuardSpec(guard_expr=_AMOUNT_POSITIVE)
    sm = _sm(["pending", "approved"], ("pending", "approved"), guards=[guard])
    result = TransitionValidator(sm).validate_transition("pending", "approved", {"amount": 0})
    assert not result.is_valid
    assert "Guard condition not met" in str(result.error)
