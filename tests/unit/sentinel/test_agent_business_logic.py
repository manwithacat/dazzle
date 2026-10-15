"""Tests for the Business Logic detection agent (BL-01, BL-02, BL-05 to BL-07).

One table: each case builds an AppSpec, runs one heuristic and pins the exact
findings (see ``assert_findings``). Agent identity, heuristic order and the
clean-spec run live in ``test_registry.py``.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from dazzle.core.ir.process import ProcessTriggerKind
from dazzle.core.ir.stories import StoryTrigger
from dazzle.sentinel.agents.business_logic import BusinessLogicAgent
from dazzle.sentinel.models import Confidence, Severity

from .conftest import assert_findings, make_appspec, make_entity, mock_entity

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _process(
    name: str,
    *,
    implements: list[str] | None = None,
    trigger_kind: ProcessTriggerKind | None = None,
    trigger_entity: str | None = None,
) -> MagicMock:
    p = MagicMock()
    p.name = name
    p.title = name
    p.implements = implements or []
    if trigger_kind:
        p.trigger = MagicMock()
        p.trigger.kind = trigger_kind
        p.trigger.entity_name = trigger_entity
    else:
        p.trigger = None
    return p


def _story(
    trigger: StoryTrigger = StoryTrigger.FORM_SUBMITTED, scope: list[str] | None = None
) -> MagicMock:
    s = MagicMock()
    s.story_id = "ST-001"
    s.persona = "admin"
    s.trigger = trigger
    s.title = "ST-001"
    if scope is not None:
        s.entities = scope
    return s


def _sla(name: str, entity: str) -> MagicMock:
    s = MagicMock()
    s.name = name
    s.entity = entity
    return s


def _experience(start_step: str, steps: list[tuple[str, list[str]]]) -> MagicMock:
    """Build an experience mock. steps is [(name, [next_step_names])]."""
    exp = MagicMock()
    exp.name = "onboarding"
    exp.start_step = start_step
    step_mocks = []
    step_dict: dict[str, MagicMock] = {}
    for step_name, nexts in steps:
        step = MagicMock()
        step.name = step_name
        step.transitions = []
        for ns in nexts:
            t = MagicMock()
            t.next_step = ns
            step.transitions.append(t)
        step_mocks.append(step)
        step_dict[step_name] = step
    exp.steps = step_mocks
    exp.get_step = lambda name, d=step_dict: d.get(name)
    return exp


def _schedule(name: str) -> MagicMock:
    s = MagicMock()
    s.name = name
    s.title = name
    return s


def _surface(name: str, entity_ref: str | None = None) -> MagicMock:
    s = MagicMock()
    s.name = name
    s.entity_ref = entity_ref
    return s


def _sm_entity(name: str, *, role_guarded: bool) -> MagicMock:
    """Entity mock with a one-transition state machine, optionally role-guarded."""
    guard = MagicMock()
    guard.is_role_guard = role_guarded
    transition = MagicMock()
    transition.guards = [guard]
    sm = MagicMock()
    sm.transitions = [transition]
    return mock_entity(name, state_machine=sm)


def _status_story_on(*entities: Any) -> Any:
    """A status_changed story scoped to Order, over the given entities."""
    story = _story(StoryTrigger.STATUS_CHANGED, scope=["Order"])
    return make_appspec(list(entities), stories=[story])


def _managed_by_route() -> Any:
    entity = mock_entity("OnboardingProgress")
    entity.managed_by = "route"
    return make_appspec([entity])


# ---------------------------------------------------------------------------
# Heuristic table
# ---------------------------------------------------------------------------

CASES = [
    # BL-01  process not linked to any story
    pytest.param(
        "check_process_empty_implements",
        lambda: make_appspec(processes=[_process("approve_order")]),
        [{"heuristic_id": "BL-01", "severity": Severity.LOW}],
        id="BL-01-flags-unlinked-process",
    ),
    pytest.param(
        "check_process_empty_implements",
        lambda: make_appspec(processes=[_process("approve_order", implements=["ST-001"])]),
        [],
        id="BL-01-linked-process",
    ),
    # BL-02  status_changed story with nothing implementing it
    pytest.param(
        "check_story_trigger_mismatch",
        lambda: make_appspec(stories=[_story(StoryTrigger.STATUS_CHANGED)]),
        [{"heuristic_id": "BL-02"}],
        id="BL-02-flags-status-story-without-process",
    ),
    pytest.param(
        "check_story_trigger_mismatch",
        lambda: make_appspec(
            stories=[_story(StoryTrigger.STATUS_CHANGED)],
            processes=[_process("h", trigger_kind=ProcessTriggerKind.ENTITY_STATUS_TRANSITION)],
        ),
        [],
        id="BL-02-status-transition-process-satisfies",
    ),
    pytest.param(
        "check_story_trigger_mismatch",
        lambda: make_appspec(stories=[_story(StoryTrigger.FORM_SUBMITTED)]),
        [],
        id="BL-02-ignores-non-status-trigger",
    ),
    # #1356: a role-guarded state machine on an in-scope entity implements the story.
    pytest.param(
        "check_story_trigger_mismatch",
        lambda: _status_story_on(_sm_entity("Order", role_guarded=True)),
        [],
        id="BL-02-role-guarded-machine-suppresses-1356",
    ),
    pytest.param(
        "check_story_trigger_mismatch",
        lambda: _status_story_on(_sm_entity("Order", role_guarded=False)),
        [{"heuristic_id": "BL-02", "confidence": Confidence.POSSIBLE}],
        id="BL-02-unguarded-machine-downgrades-1356",
    ),
    pytest.param(
        "check_story_trigger_mismatch",
        lambda: _status_story_on(make_entity("Order")),
        [{"heuristic_id": "BL-02", "confidence": Confidence.LIKELY}],
        id="BL-02-no-machine-stays-likely-1356",
    ),
    pytest.param(
        "check_story_trigger_mismatch",
        lambda: _status_story_on(_sm_entity("Invoice", role_guarded=True), make_entity("Order")),
        [{"heuristic_id": "BL-02"}],
        id="BL-02-out-of-scope-machine-does-not-suppress-1356",
    ),
    # BL-05  SLA nothing monitors
    pytest.param(
        "check_sla_without_monitoring",
        lambda: make_appspec(slas=[_sla("response_sla", "Ticket")]),
        [{"heuristic_id": "BL-05", "severity": Severity.MEDIUM}],
        id="BL-05-flags-unmonitored-sla",
    ),
    pytest.param(
        "check_sla_without_monitoring",
        lambda: make_appspec(
            slas=[_sla("response_sla", "Ticket")], schedules=[_schedule("check_sla_breaches")]
        ),
        [],
        id="BL-05-sla-schedule-satisfies",
    ),
    pytest.param(
        "check_sla_without_monitoring",
        lambda: make_appspec(
            slas=[_sla("response_sla", "Ticket")],
            processes=[_process("monitor_ticket", trigger_entity="Ticket")],
        ),
        [],
        id="BL-05-entity-process-satisfies",
    ),
    # BL-06  experience step unreachable from the start step
    pytest.param(
        "check_experience_unreachable_steps",
        lambda: make_appspec(
            experiences=[
                _experience("step1", [("step1", ["step2"]), ("step2", []), ("orphan", [])])
            ]
        ),
        [{"heuristic_id": "BL-06", "description_has": "orphan"}],
        id="BL-06-flags-orphan-step",
    ),
    pytest.param(
        "check_experience_unreachable_steps",
        lambda: make_appspec(
            experiences=[
                _experience("step1", [("step1", ["step2"]), ("step2", ["step3"]), ("step3", [])])
            ]
        ),
        [],
        id="BL-06-all-steps-reachable",
    ),
    # BL-07  entity no surface references
    pytest.param(
        "check_entity_without_surface",
        lambda: make_appspec([make_entity("AuditLog")]),
        [{"heuristic_id": "BL-07", "severity": Severity.LOW}],
        id="BL-07-flags-entity-without-surface",
    ),
    pytest.param(
        "check_entity_without_surface",
        lambda: make_appspec([make_entity("Task")], surfaces=[_surface("task_list", "Task")]),
        [],
        id="BL-07-surface-satisfies",
    ),
    # #1333 marker: lifecycle owned outside the surface graph (fixed under #1356).
    pytest.param(
        "check_entity_without_surface",
        _managed_by_route,
        [],
        id="BL-07-managed-by-entity-not-flagged-1333",
    ),
]


@pytest.mark.parametrize(("heuristic", "build", "expected"), CASES)
def test_heuristic(
    heuristic: str, build: Callable[[], Any], expected: list[dict[str, Any]]
) -> None:
    assert_findings(getattr(BusinessLogicAgent(), heuristic)(build()), expected)
