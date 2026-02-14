"""Tests for the Operational Hygiene detection agent (OP-01 through OP-08)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dazzle.core.ir.governance import DataClassification
from dazzle.core.ir.process import StepKind
from dazzle.sentinel.agents.operational_hygiene import OperationalHygieneAgent
from dazzle.sentinel.models import AgentId, Severity

from .conftest import make_appspec, mock_entity


@pytest.fixture
def agent() -> OperationalHygieneAgent:
    return OperationalHygieneAgent()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _policies_with_classification(
    entity: str,
    field: str,
    classification: DataClassification = DataClassification.PII_DIRECT,
) -> MagicMock:
    cls_spec = MagicMock()
    cls_spec.entity = entity
    cls_spec.field = field
    cls_spec.classification = classification
    policies = MagicMock()
    policies.classifications = [cls_spec]
    return policies


def _llm_intent(name: str, *, pii: object | None = None) -> MagicMock:
    intent = MagicMock()
    intent.name = name
    intent.pii = pii
    return intent


def _llm_config(
    *,
    redact_pii: bool = False,
    log_prompts: bool = True,
    log_completions: bool = True,
) -> MagicMock:
    logging_cfg = MagicMock()
    logging_cfg.redact_pii = redact_pii
    logging_cfg.log_prompts = log_prompts
    logging_cfg.log_completions = log_completions
    cfg = MagicMock()
    cfg.logging = logging_cfg
    return cfg


def _sla(
    name: str,
    *,
    on_breach: object | None = None,
    tiers: list | None = None,
) -> MagicMock:
    sla = MagicMock()
    sla.name = name
    sla.on_breach = on_breach
    sla.tiers = tiers if tiers is not None else []
    return sla


def _approval(name: str, *, escalation: object | None = None) -> MagicMock:
    approval = MagicMock()
    approval.name = name
    approval.escalation = escalation
    return approval


def _service_step(name: str, *, retry: object | None = None) -> MagicMock:
    step = MagicMock()
    step.kind = StepKind.SERVICE
    step.name = name
    step.retry = retry
    return step


def _non_service_step(name: str, kind: StepKind = StepKind.SEND) -> MagicMock:
    step = MagicMock()
    step.kind = kind
    step.name = name
    step.retry = None
    return step


def _process(
    name: str,
    steps: list | None = None,
    *,
    compensations: list | None = None,
) -> MagicMock:
    proc = MagicMock()
    proc.name = name
    proc.steps = steps or []
    proc.compensations = compensations if compensations is not None else []
    return proc


# =============================================================================
# OP-01  Entity audit without field-level tracking
# =============================================================================


class TestOP01AuditWithoutFieldTracking:
    def test_flags_entity_with_audit_but_no_field_changes(
        self, agent: OperationalHygieneAgent
    ) -> None:
        audit = MagicMock()
        audit.enabled = True
        audit.log_field_changes = False
        entity = mock_entity("Customer", audit=audit)
        policies = _policies_with_classification("Customer", "email")
        appspec = make_appspec([entity], policies=policies)

        findings = agent.audit_without_field_tracking(appspec)

        assert len(findings) == 1
        assert findings[0].heuristic_id == "OP-01"
        assert findings[0].severity == Severity.MEDIUM
        assert "Customer" in findings[0].title

    def test_passes_when_log_field_changes_enabled(self, agent: OperationalHygieneAgent) -> None:
        audit = MagicMock()
        audit.enabled = True
        audit.log_field_changes = True
        entity = mock_entity("Customer", audit=audit)
        policies = _policies_with_classification("Customer", "email")
        appspec = make_appspec([entity], policies=policies)

        assert agent.audit_without_field_tracking(appspec) == []

    def test_passes_when_audit_disabled(self, agent: OperationalHygieneAgent) -> None:
        audit = MagicMock()
        audit.enabled = False
        audit.log_field_changes = False
        entity = mock_entity("Customer", audit=audit)
        policies = _policies_with_classification("Customer", "email")
        appspec = make_appspec([entity], policies=policies)

        assert agent.audit_without_field_tracking(appspec) == []

    def test_passes_when_entity_not_classified(self, agent: OperationalHygieneAgent) -> None:
        audit = MagicMock()
        audit.enabled = True
        audit.log_field_changes = False
        entity = mock_entity("Task", audit=audit)
        # Classification is for a different entity
        policies = _policies_with_classification("Customer", "email")
        appspec = make_appspec([entity], policies=policies)

        assert agent.audit_without_field_tracking(appspec) == []

    def test_passes_when_no_policies(self, agent: OperationalHygieneAgent) -> None:
        audit = MagicMock()
        audit.enabled = True
        audit.log_field_changes = False
        entity = mock_entity("Customer", audit=audit)
        appspec = make_appspec([entity], policies=None)

        assert agent.audit_without_field_tracking(appspec) == []

    def test_passes_when_no_audit_config(self, agent: OperationalHygieneAgent) -> None:
        entity = mock_entity("Customer", audit=None)
        policies = _policies_with_classification("Customer", "email")
        appspec = make_appspec([entity], policies=policies)

        assert agent.audit_without_field_tracking(appspec) == []

    def test_flags_multiple_entities(self, agent: OperationalHygieneAgent) -> None:
        audit1 = MagicMock()
        audit1.enabled = True
        audit1.log_field_changes = False
        audit2 = MagicMock()
        audit2.enabled = True
        audit2.log_field_changes = False
        e1 = mock_entity("Customer", audit=audit1)
        e2 = mock_entity("Employee", audit=audit2)

        cls1 = MagicMock()
        cls1.entity = "Customer"
        cls1.field = "email"
        cls1.classification = DataClassification.PII_DIRECT
        cls2 = MagicMock()
        cls2.entity = "Employee"
        cls2.field = "ssn"
        cls2.classification = DataClassification.PII_SENSITIVE
        policies = MagicMock()
        policies.classifications = [cls1, cls2]

        appspec = make_appspec([e1, e2], policies=policies)
        findings = agent.audit_without_field_tracking(appspec)
        assert len(findings) == 2


# =============================================================================
# OP-02  LLM intent without PII policy
# =============================================================================


class TestOP02LlmIntentNoPiiPolicy:
    def test_flags_intent_with_no_pii(self, agent: OperationalHygieneAgent) -> None:
        intent = _llm_intent("classify_ticket", pii=None)
        appspec = make_appspec(llm_intents=[intent])

        findings = agent.llm_intent_no_pii_policy(appspec)

        assert len(findings) == 1
        assert findings[0].heuristic_id == "OP-02"
        assert findings[0].severity == Severity.HIGH
        assert "classify_ticket" in findings[0].title

    def test_passes_when_pii_set(self, agent: OperationalHygieneAgent) -> None:
        pii_cfg = MagicMock()
        intent = _llm_intent("classify_ticket", pii=pii_cfg)
        appspec = make_appspec(llm_intents=[intent])

        assert agent.llm_intent_no_pii_policy(appspec) == []

    def test_passes_when_no_intents(self, agent: OperationalHygieneAgent) -> None:
        appspec = make_appspec(llm_intents=[])
        assert agent.llm_intent_no_pii_policy(appspec) == []

    def test_flags_multiple_intents(self, agent: OperationalHygieneAgent) -> None:
        i1 = _llm_intent("classify_ticket", pii=None)
        i2 = _llm_intent("summarize", pii=None)
        i3 = _llm_intent("translate", pii=MagicMock())
        appspec = make_appspec(llm_intents=[i1, i2, i3])

        findings = agent.llm_intent_no_pii_policy(appspec)
        assert len(findings) == 2
        names = {f.title for f in findings}
        assert "LLM intent 'classify_ticket' has no PII policy" in names
        assert "LLM intent 'summarize' has no PII policy" in names


# =============================================================================
# OP-03  LLM logging without PII redaction
# =============================================================================


class TestOP03LlmLoggingNoRedaction:
    def test_flags_logging_without_redaction(self, agent: OperationalHygieneAgent) -> None:
        cfg = _llm_config(redact_pii=False, log_prompts=True, log_completions=True)
        appspec = make_appspec(llm_config=cfg)

        findings = agent.llm_logging_no_redaction(appspec)

        assert len(findings) == 1
        assert findings[0].heuristic_id == "OP-03"
        assert findings[0].severity == Severity.MEDIUM

    def test_flags_when_only_prompts_logged(self, agent: OperationalHygieneAgent) -> None:
        cfg = _llm_config(redact_pii=False, log_prompts=True, log_completions=False)
        appspec = make_appspec(llm_config=cfg)

        findings = agent.llm_logging_no_redaction(appspec)
        assert len(findings) == 1

    def test_flags_when_only_completions_logged(self, agent: OperationalHygieneAgent) -> None:
        cfg = _llm_config(redact_pii=False, log_prompts=False, log_completions=True)
        appspec = make_appspec(llm_config=cfg)

        findings = agent.llm_logging_no_redaction(appspec)
        assert len(findings) == 1

    def test_passes_when_redact_pii_enabled(self, agent: OperationalHygieneAgent) -> None:
        cfg = _llm_config(redact_pii=True, log_prompts=True, log_completions=True)
        appspec = make_appspec(llm_config=cfg)

        assert agent.llm_logging_no_redaction(appspec) == []

    def test_passes_when_no_logging(self, agent: OperationalHygieneAgent) -> None:
        cfg = _llm_config(redact_pii=False, log_prompts=False, log_completions=False)
        appspec = make_appspec(llm_config=cfg)

        assert agent.llm_logging_no_redaction(appspec) == []

    def test_passes_when_no_llm_config(self, agent: OperationalHygieneAgent) -> None:
        appspec = make_appspec(llm_config=None)
        assert agent.llm_logging_no_redaction(appspec) == []


# =============================================================================
# OP-04  SLA without breach action
# =============================================================================


class TestOP04SlaWithoutBreachAction:
    def test_flags_sla_with_no_breach_action(self, agent: OperationalHygieneAgent) -> None:
        sla = _sla("response_sla", on_breach=None)
        appspec = make_appspec(slas=[sla])

        findings = agent.sla_without_breach_action(appspec)

        assert len(findings) == 1
        assert findings[0].heuristic_id == "OP-04"
        assert findings[0].severity == Severity.HIGH
        assert "response_sla" in findings[0].title

    def test_passes_when_breach_action_set(self, agent: OperationalHygieneAgent) -> None:
        breach = MagicMock()
        sla = _sla("response_sla", on_breach=breach)
        appspec = make_appspec(slas=[sla])

        assert agent.sla_without_breach_action(appspec) == []

    def test_passes_when_no_slas(self, agent: OperationalHygieneAgent) -> None:
        appspec = make_appspec(slas=[])
        assert agent.sla_without_breach_action(appspec) == []

    def test_flags_multiple_slas(self, agent: OperationalHygieneAgent) -> None:
        sla1 = _sla("response_sla", on_breach=None)
        sla2 = _sla("resolution_sla", on_breach=None)
        sla3 = _sla("ok_sla", on_breach=MagicMock())
        appspec = make_appspec(slas=[sla1, sla2, sla3])

        findings = agent.sla_without_breach_action(appspec)
        assert len(findings) == 2


# =============================================================================
# OP-05  Approval without escalation
# =============================================================================


class TestOP05ApprovalWithoutEscalation:
    def test_flags_approval_with_no_escalation(self, agent: OperationalHygieneAgent) -> None:
        approval = _approval("purchase_approval", escalation=None)
        appspec = make_appspec(approvals=[approval])

        findings = agent.approval_without_escalation(appspec)

        assert len(findings) == 1
        assert findings[0].heuristic_id == "OP-05"
        assert findings[0].severity == Severity.MEDIUM
        assert "purchase_approval" in findings[0].title

    def test_passes_when_escalation_set(self, agent: OperationalHygieneAgent) -> None:
        esc = MagicMock()
        approval = _approval("purchase_approval", escalation=esc)
        appspec = make_appspec(approvals=[approval])

        assert agent.approval_without_escalation(appspec) == []

    def test_passes_when_no_approvals(self, agent: OperationalHygieneAgent) -> None:
        appspec = make_appspec(approvals=[])
        assert agent.approval_without_escalation(appspec) == []

    def test_flags_multiple_approvals(self, agent: OperationalHygieneAgent) -> None:
        a1 = _approval("purchase_approval", escalation=None)
        a2 = _approval("expense_approval", escalation=None)
        a3 = _approval("leave_approval", escalation=MagicMock())
        appspec = make_appspec(approvals=[a1, a2, a3])

        findings = agent.approval_without_escalation(appspec)
        assert len(findings) == 2


# =============================================================================
# OP-06  Process without compensation
# =============================================================================


class TestOP06ProcessWithoutCompensation:
    def test_flags_process_with_service_steps_no_compensation(
        self, agent: OperationalHygieneAgent
    ) -> None:
        step1 = _service_step("validate")
        step2 = _service_step("execute")
        proc = _process("approve_order", [step1, step2], compensations=[])
        appspec = make_appspec(processes=[proc])

        findings = agent.process_without_compensation(appspec)

        assert len(findings) == 1
        assert findings[0].heuristic_id == "OP-06"
        assert findings[0].severity == Severity.MEDIUM
        assert "approve_order" in findings[0].title

    def test_passes_when_compensations_exist(self, agent: OperationalHygieneAgent) -> None:
        step1 = _service_step("validate")
        step2 = _service_step("execute")
        comp = MagicMock()
        proc = _process("approve_order", [step1, step2], compensations=[comp])
        appspec = make_appspec(processes=[proc])

        assert agent.process_without_compensation(appspec) == []

    def test_passes_when_fewer_than_two_service_steps(self, agent: OperationalHygieneAgent) -> None:
        step1 = _service_step("validate")
        proc = _process("simple_process", [step1], compensations=[])
        appspec = make_appspec(processes=[proc])

        assert agent.process_without_compensation(appspec) == []

    def test_passes_when_non_service_steps_only(self, agent: OperationalHygieneAgent) -> None:
        step1 = _non_service_step("notify", StepKind.SEND)
        step2 = _non_service_step("pause", StepKind.WAIT)
        proc = _process("notification_flow", [step1, step2], compensations=[])
        appspec = make_appspec(processes=[proc])

        assert agent.process_without_compensation(appspec) == []

    def test_passes_when_no_processes(self, agent: OperationalHygieneAgent) -> None:
        appspec = make_appspec(processes=[])
        assert agent.process_without_compensation(appspec) == []

    def test_counts_only_service_steps(self, agent: OperationalHygieneAgent) -> None:
        """Mixed steps: only 1 service step + 1 send step should NOT flag."""
        step1 = _service_step("validate")
        step2 = _non_service_step("notify", StepKind.SEND)
        proc = _process("mixed_process", [step1, step2], compensations=[])
        appspec = make_appspec(processes=[proc])

        assert agent.process_without_compensation(appspec) == []


# =============================================================================
# OP-07  Process service step without retry
# =============================================================================


class TestOP07ServiceStepWithoutRetry:
    def test_flags_service_step_without_retry(self, agent: OperationalHygieneAgent) -> None:
        step = _service_step("validate", retry=None)
        proc = _process("approve_order", [step])
        appspec = make_appspec(processes=[proc])

        findings = agent.service_step_without_retry(appspec)

        assert len(findings) == 1
        assert findings[0].heuristic_id == "OP-07"
        assert findings[0].severity == Severity.MEDIUM
        assert "validate" in findings[0].title
        assert "approve_order" in findings[0].title

    def test_passes_when_retry_configured(self, agent: OperationalHygieneAgent) -> None:
        retry_cfg = MagicMock()
        step = _service_step("validate", retry=retry_cfg)
        proc = _process("approve_order", [step])
        appspec = make_appspec(processes=[proc])

        assert agent.service_step_without_retry(appspec) == []

    def test_skips_non_service_steps(self, agent: OperationalHygieneAgent) -> None:
        step = _non_service_step("notify", StepKind.SEND)
        proc = _process("notification_flow", [step])
        appspec = make_appspec(processes=[proc])

        assert agent.service_step_without_retry(appspec) == []

    def test_passes_when_no_processes(self, agent: OperationalHygieneAgent) -> None:
        appspec = make_appspec(processes=[])
        assert agent.service_step_without_retry(appspec) == []

    def test_flags_multiple_steps_across_processes(self, agent: OperationalHygieneAgent) -> None:
        s1 = _service_step("validate", retry=None)
        s2 = _service_step("execute", retry=None)
        s3 = _service_step("charge", retry=MagicMock())
        proc1 = _process("order_flow", [s1, s2])
        proc2 = _process("payment_flow", [s3])
        appspec = make_appspec(processes=[proc1, proc2])

        findings = agent.service_step_without_retry(appspec)
        assert len(findings) == 2


# =============================================================================
# OP-08  SLA without tiers
# =============================================================================


class TestOP08SlaWithoutTiers:
    def test_flags_sla_with_empty_tiers(self, agent: OperationalHygieneAgent) -> None:
        sla = _sla("response_sla", tiers=[])
        appspec = make_appspec(slas=[sla])

        findings = agent.sla_without_tiers(appspec)

        assert len(findings) == 1
        assert findings[0].heuristic_id == "OP-08"
        assert findings[0].severity == Severity.MEDIUM
        assert "response_sla" in findings[0].title

    def test_passes_when_tiers_defined(self, agent: OperationalHygieneAgent) -> None:
        tier = MagicMock()
        sla = _sla("response_sla", tiers=[tier])
        appspec = make_appspec(slas=[sla])

        assert agent.sla_without_tiers(appspec) == []

    def test_passes_when_no_slas(self, agent: OperationalHygieneAgent) -> None:
        appspec = make_appspec(slas=[])
        assert agent.sla_without_tiers(appspec) == []

    def test_flags_multiple_slas_without_tiers(self, agent: OperationalHygieneAgent) -> None:
        sla1 = _sla("response_sla", tiers=[])
        sla2 = _sla("resolution_sla", tiers=[])
        sla3 = _sla("ok_sla", tiers=[MagicMock()])
        appspec = make_appspec(slas=[sla1, sla2, sla3])

        findings = agent.sla_without_tiers(appspec)
        assert len(findings) == 2


# =============================================================================
# Full agent run
# =============================================================================


class TestOperationalHygieneAgentRun:
    def test_agent_id(self, agent: OperationalHygieneAgent) -> None:
        assert agent.agent_id == AgentId.OP

    def test_has_8_heuristics(self, agent: OperationalHygieneAgent) -> None:
        assert len(agent.get_heuristics()) == 8

    def test_heuristic_ids(self, agent: OperationalHygieneAgent) -> None:
        ids = [meta.heuristic_id for meta, _ in agent.get_heuristics()]
        assert ids == [f"OP-0{i}" for i in range(1, 9)]
