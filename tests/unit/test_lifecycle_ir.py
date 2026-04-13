"""Unit tests for LifecycleSpec, LifecycleStateSpec, LifecycleTransitionSpec."""

import pytest
from pydantic import ValidationError

from dazzle.core.ir.lifecycle import (
    LifecycleSpec,
    LifecycleStateSpec,
    LifecycleTransitionSpec,
)


def test_state_spec_requires_name_and_order() -> None:
    state = LifecycleStateSpec(name="new", order=0)
    assert state.name == "new"
    assert state.order == 0


def test_state_spec_order_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        LifecycleStateSpec(name="new", order=-1)


def test_transition_spec_basic() -> None:
    t = LifecycleTransitionSpec(
        from_state="new",
        to_state="assigned",
        evidence=None,
        roles=["support_agent"],
    )
    assert t.from_state == "new"
    assert t.to_state == "assigned"
    assert t.evidence is None


def test_transition_spec_with_evidence() -> None:
    t = LifecycleTransitionSpec(
        from_state="in_progress",
        to_state="resolved",
        evidence="resolution_notes != null",
        roles=["support_agent"],
    )
    assert t.evidence == "resolution_notes != null"


def test_lifecycle_spec_basic() -> None:
    lc = LifecycleSpec(
        status_field="status",
        states=[
            LifecycleStateSpec(name="new", order=0),
            LifecycleStateSpec(name="resolved", order=1),
        ],
        transitions=[
            LifecycleTransitionSpec(
                from_state="new",
                to_state="resolved",
                evidence=None,
                roles=["any"],
            ),
        ],
    )
    assert lc.status_field == "status"
    assert len(lc.states) == 2


def test_lifecycle_states_are_frozen() -> None:
    lc = LifecycleSpec(
        status_field="status",
        states=[LifecycleStateSpec(name="new", order=0)],
        transitions=[],
    )
    with pytest.raises(ValidationError):
        lc.status_field = "other"  # type: ignore[misc]
