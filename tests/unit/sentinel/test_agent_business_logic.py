"""Tests for the Business Logic detection agent (BL-01 through BL-08)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dazzle.core.ir import FieldTypeKind
from dazzle.core.ir.process import ProcessTriggerKind
from dazzle.core.ir.stories import StoryTrigger
from dazzle.sentinel.agents.business_logic import BusinessLogicAgent
from dazzle.sentinel.models import AgentId, Severity

from .conftest import make_appspec, make_entity, make_field, mock_entity, pk_field, str_field


@pytest.fixture
def agent() -> BusinessLogicAgent:
    return BusinessLogicAgent()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _process(
    name: str,
    *,
    implements: list[str] | None = None,
    trigger_kind: ProcessTriggerKind | None = None,
    trigger_entity: str | None = None,
    title: str | None = None,
) -> MagicMock:
    p = MagicMock()
    p.name = name
    p.title = title or name
    p.implements = implements or []
    if trigger_kind:
        p.trigger = MagicMock()
        p.trigger.kind = trigger_kind
        p.trigger.entity_name = trigger_entity
    else:
        p.trigger = None
    return p


def _story(
    story_id: str,
    actor: str = "admin",
    trigger: StoryTrigger = StoryTrigger.FORM_SUBMITTED,
    title: str = "",
) -> MagicMock:
    s = MagicMock()
    s.story_id = story_id
    s.actor = actor
    s.trigger = trigger
    s.title = title or story_id
    return s


def _sla(name: str, entity: str) -> MagicMock:
    s = MagicMock()
    s.name = name
    s.entity = entity
    return s


def _approval(
    name: str,
    entity: str,
    approver_role: str = "approver",
) -> MagicMock:
    a = MagicMock()
    a.name = name
    a.entity = entity
    a.approver_role = approver_role
    return a


def _experience(
    name: str,
    start_step: str,
    steps: list[tuple[str, list[str]]],
) -> MagicMock:
    """Build an experience mock. steps is [(name, [next_step_names])]."""
    exp = MagicMock()
    exp.name = name
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


def _enum(name: str, values: list[str]) -> MagicMock:
    e = MagicMock()
    e.name = name
    e.values = []
    for v in values:
        val = MagicMock()
        val.name = v
        e.values.append(val)
    return e


def _test_spec(name: str) -> MagicMock:
    t = MagicMock()
    t.name = name
    return t


def _schedule(name: str, title: str = "") -> MagicMock:
    s = MagicMock()
    s.name = name
    s.title = title or name
    return s


def _surface(name: str, entity_ref: str | None = None) -> MagicMock:
    s = MagicMock()
    s.name = name
    s.entity_ref = entity_ref
    return s


def _invariant(expr: str) -> MagicMock:
    inv = MagicMock()
    inv.expression = expr
    return inv


# =============================================================================
# BL-01  Process not linked to any story
# =============================================================================


class TestBL01ProcessEmptyImplements:
    def test_flags_unlinked_process(self, agent: BusinessLogicAgent) -> None:
        process = _process("approve_order", implements=[])
        findings = agent.check_process_empty_implements(make_appspec(processes=[process]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "BL-01"
        assert findings[0].severity == Severity.LOW

    def test_passes_when_linked(self, agent: BusinessLogicAgent) -> None:
        process = _process("approve_order", implements=["ST-001"])
        assert agent.check_process_empty_implements(make_appspec(processes=[process])) == []


# =============================================================================
# BL-02  Story trigger mismatch
# =============================================================================


class TestBL02StoryTriggerMismatch:
    def test_flags_status_changed_without_process(self, agent: BusinessLogicAgent) -> None:
        story = _story("ST-001", trigger=StoryTrigger.STATUS_CHANGED)
        findings = agent.check_story_trigger_mismatch(make_appspec(stories=[story]))
        assert len(findings) == 1

    def test_passes_with_matching_process(self, agent: BusinessLogicAgent) -> None:
        story = _story("ST-001", trigger=StoryTrigger.STATUS_CHANGED)
        process = _process(
            "handle_status",
            trigger_kind=ProcessTriggerKind.ENTITY_STATUS_TRANSITION,
        )
        assert (
            agent.check_story_trigger_mismatch(make_appspec(stories=[story], processes=[process]))
            == []
        )

    def test_ignores_non_status_triggers(self, agent: BusinessLogicAgent) -> None:
        story = _story("ST-001", trigger=StoryTrigger.FORM_SUBMITTED)
        assert agent.check_story_trigger_mismatch(make_appspec(stories=[story])) == []


# =============================================================================
# BL-03  Entity invariants without test coverage
# =============================================================================


class TestBL03InvariantsWithoutTests:
    def test_flags_invariants_without_tests(self, agent: BusinessLogicAgent) -> None:
        entity = mock_entity(
            "Order",
            invariants=[_invariant("total > 0")],
        )
        findings = agent.check_invariants_without_tests(make_appspec([entity]))
        assert len(findings) == 1

    def test_passes_with_covering_test(self, agent: BusinessLogicAgent) -> None:
        entity = mock_entity(
            "Order",
            invariants=[_invariant("total > 0")],
        )
        test = _test_spec("test_order_invariants")
        assert agent.check_invariants_without_tests(make_appspec([entity], tests=[test])) == []

    def test_no_invariants(self, agent: BusinessLogicAgent) -> None:
        entity = mock_entity("Task", invariants=[])
        assert agent.check_invariants_without_tests(make_appspec([entity])) == []


# =============================================================================
# BL-04  Approval transitions lack role guards
# =============================================================================


class TestBL04ApprovalRoleGuards:
    def _sm_with_guards(self, transitions: list[tuple[str, str, bool]]) -> MagicMock:
        """transitions is [(from, to, has_role_guard)]."""
        sm = MagicMock()
        sm.states = list({t[0] for t in transitions} | {t[1] for t in transitions})
        sm.transitions = []
        for from_s, to_s, has_guard in transitions:
            t = MagicMock()
            t.from_state = from_s
            t.to_state = to_s
            guard = MagicMock()
            guard.requires_role = "approver" if has_guard else None
            t.guards = [guard]
            sm.transitions.append(t)
        return sm

    def test_flags_unguarded_transitions(self, agent: BusinessLogicAgent) -> None:
        sm = self._sm_with_guards(
            [
                ("draft", "pending_approval", False),
                ("pending_approval", "approved", False),
            ]
        )
        entity = mock_entity("Request", state_machine=sm)
        approval = _approval("approve_request", "Request")
        findings = agent.check_approval_transitions_without_role_guards(
            make_appspec([entity], approvals=[approval])
        )
        assert len(findings) == 1

    def test_passes_all_guarded(self, agent: BusinessLogicAgent) -> None:
        sm = self._sm_with_guards(
            [
                ("draft", "pending_approval", True),
                ("pending_approval", "approved", True),
            ]
        )
        entity = mock_entity("Request", state_machine=sm)
        approval = _approval("approve_request", "Request")
        assert (
            agent.check_approval_transitions_without_role_guards(
                make_appspec([entity], approvals=[approval])
            )
            == []
        )


# =============================================================================
# BL-05  SLA without monitoring
# =============================================================================


class TestBL05SLAMonitoring:
    def test_flags_sla_without_monitor(self, agent: BusinessLogicAgent) -> None:
        sla = _sla("response_sla", "Ticket")
        findings = agent.check_sla_without_monitoring(make_appspec(slas=[sla]))
        assert len(findings) == 1
        assert findings[0].severity == Severity.MEDIUM

    def test_passes_with_matching_schedule(self, agent: BusinessLogicAgent) -> None:
        sla = _sla("response_sla", "Ticket")
        schedule = _schedule("check_sla_breaches")
        assert (
            agent.check_sla_without_monitoring(make_appspec(slas=[sla], schedules=[schedule])) == []
        )

    def test_passes_with_matching_process(self, agent: BusinessLogicAgent) -> None:
        sla = _sla("response_sla", "Ticket")
        process = _process("monitor_ticket", trigger_entity="Ticket")
        assert (
            agent.check_sla_without_monitoring(make_appspec(slas=[sla], processes=[process])) == []
        )


# =============================================================================
# BL-06  Experience with unreachable steps
# =============================================================================


class TestBL06UnreachableSteps:
    def test_flags_unreachable_steps(self, agent: BusinessLogicAgent) -> None:
        exp = _experience(
            "onboarding",
            start_step="step1",
            steps=[
                ("step1", ["step2"]),
                ("step2", []),
                ("orphan", []),  # not reachable from step1
            ],
        )
        findings = agent.check_experience_unreachable_steps(make_appspec(experiences=[exp]))
        assert len(findings) == 1
        assert "orphan" in findings[0].description

    def test_passes_all_reachable(self, agent: BusinessLogicAgent) -> None:
        exp = _experience(
            "onboarding",
            start_step="step1",
            steps=[
                ("step1", ["step2"]),
                ("step2", ["step3"]),
                ("step3", []),
            ],
        )
        assert agent.check_experience_unreachable_steps(make_appspec(experiences=[exp])) == []


# =============================================================================
# BL-07  Entity not referenced by any surface
# =============================================================================


class TestBL07EntityWithoutSurface:
    def test_flags_entity_without_surface(self, agent: BusinessLogicAgent) -> None:
        entity = make_entity("AuditLog")
        findings = agent.check_entity_without_surface(make_appspec([entity]))
        assert len(findings) == 1
        assert findings[0].severity == Severity.LOW

    def test_passes_with_surface(self, agent: BusinessLogicAgent) -> None:
        entity = make_entity("Task")
        surface = _surface("task_list", entity_ref="Task")
        assert agent.check_entity_without_surface(make_appspec([entity], surfaces=[surface])) == []


# =============================================================================
# BL-08  Shared enum not referenced
# =============================================================================


class TestBL08UnreferencedEnum:
    def test_flags_unreferenced_enum(self, agent: BusinessLogicAgent) -> None:
        enum = _enum("Priority", ["low", "medium", "high"])
        findings = agent.check_unreferenced_enum(make_appspec(enums=[enum]))
        assert len(findings) == 1

    def test_passes_when_referenced(self, agent: BusinessLogicAgent) -> None:
        enum = _enum("Priority", ["low", "medium", "high"])
        entity = make_entity(
            "Task",
            [pk_field(), make_field("priority", FieldTypeKind.ENUM, ref_entity="Priority")],
        )
        assert agent.check_unreferenced_enum(make_appspec([entity], enums=[enum])) == []


# =============================================================================
# Full agent run
# =============================================================================


class TestBusinessLogicAgentRun:
    def test_agent_id(self, agent: BusinessLogicAgent) -> None:
        assert agent.agent_id == AgentId.BL

    def test_has_8_heuristics(self, agent: BusinessLogicAgent) -> None:
        assert len(agent.get_heuristics()) == 8

    def test_heuristic_ids(self, agent: BusinessLogicAgent) -> None:
        ids = [meta.heuristic_id for meta, _ in agent.get_heuristics()]
        assert ids == [f"BL-0{i}" for i in range(1, 9)]

    def test_clean_appspec_no_errors(self, agent: BusinessLogicAgent) -> None:
        entity = make_entity("Task", [pk_field(), str_field("title")])
        surface = _surface("task_list", entity_ref="Task")
        result = agent.run(make_appspec([entity], surfaces=[surface]))
        assert result.errors == []
