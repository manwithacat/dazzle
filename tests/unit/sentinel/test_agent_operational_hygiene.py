"""Tests for the Operational Hygiene detection agent (OP-01 through OP-08)."""

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


def _audit(*, enabled: bool = True, log_field_changes: bool = False) -> MagicMock:
    audit = MagicMock()
    audit.enabled = enabled
    audit.log_field_changes = log_field_changes
    return audit


# =============================================================================
# OP-01  Entity audit without field-level tracking
# =============================================================================


class TestOP01AuditWithoutFieldTracking:
    def test_flags_entity_with_audit_but_no_field_changes(
        self, agent: OperationalHygieneAgent
    ) -> None:
        entity = mock_entity("Customer", audit=_audit(enabled=True, log_field_changes=False))
        policies = _policies_with_classification("Customer", "email")
        findings = agent.audit_without_field_tracking(make_appspec([entity], policies=policies))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "OP-01"
        assert findings[0].severity == Severity.MEDIUM
        assert "Customer" in findings[0].title

    @pytest.mark.parametrize(
        "scenario",
        [
            "log_field_changes_enabled",
            "audit_disabled",
            "entity_not_classified",
            "no_policies",
            "no_audit_config",
        ],
    )
    def test_op01_passes(self, agent: OperationalHygieneAgent, scenario: str) -> None:
        if scenario == "log_field_changes_enabled":
            entity = mock_entity("Customer", audit=_audit(enabled=True, log_field_changes=True))
            policies = _policies_with_classification("Customer", "email")
        elif scenario == "audit_disabled":
            entity = mock_entity("Customer", audit=_audit(enabled=False, log_field_changes=False))
            policies = _policies_with_classification("Customer", "email")
        elif scenario == "entity_not_classified":
            entity = mock_entity("Task", audit=_audit(enabled=True, log_field_changes=False))
            policies = _policies_with_classification("Customer", "email")
        elif scenario == "no_policies":
            entity = mock_entity("Customer", audit=_audit(enabled=True, log_field_changes=False))
            policies = None
        else:  # no_audit_config
            entity = mock_entity("Customer", audit=None)
            policies = _policies_with_classification("Customer", "email")
        appspec = make_appspec([entity], policies=policies)
        assert agent.audit_without_field_tracking(appspec) == []


# =============================================================================
# OP-02  LLM intent without PII policy
# =============================================================================


class TestOP02LlmIntentNoPiiPolicy:
    def test_flags_intent_with_no_pii(self, agent: OperationalHygieneAgent) -> None:
        intent = _llm_intent("classify_ticket", pii=None)
        findings = agent.llm_intent_no_pii_policy(make_appspec(llm_intents=[intent]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "OP-02"
        assert findings[0].severity == Severity.HIGH
        assert "classify_ticket" in findings[0].title

    def test_passes_when_pii_set(self, agent: OperationalHygieneAgent) -> None:
        intent = _llm_intent("classify_ticket", pii=MagicMock())
        assert agent.llm_intent_no_pii_policy(make_appspec(llm_intents=[intent])) == []

    def test_passes_when_no_intents(self, agent: OperationalHygieneAgent) -> None:
        assert agent.llm_intent_no_pii_policy(make_appspec(llm_intents=[])) == []


# =============================================================================
# OP-03  LLM logging without PII redaction
# =============================================================================


class TestOP03LlmLoggingNoRedaction:
    @pytest.mark.parametrize(
        ("log_prompts", "log_completions"),
        [(True, True), (True, False), (False, True)],
        ids=["both", "prompts_only", "completions_only"],
    )
    def test_flags_logging_without_redaction(
        self,
        agent: OperationalHygieneAgent,
        log_prompts: bool,
        log_completions: bool,
    ) -> None:
        cfg = _llm_config(
            redact_pii=False, log_prompts=log_prompts, log_completions=log_completions
        )
        findings = agent.llm_logging_no_redaction(make_appspec(llm_config=cfg))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "OP-03"
        assert findings[0].severity == Severity.MEDIUM

    @pytest.mark.parametrize(
        ("redact_pii", "log_prompts", "log_completions", "config"),
        [
            (True, True, True, "cfg"),
            (False, False, False, "cfg"),
            (False, False, False, "none"),
        ],
        ids=["redact_enabled", "no_logging", "no_llm_config"],
    )
    def test_no_finding(
        self,
        agent: OperationalHygieneAgent,
        redact_pii: bool,
        log_prompts: bool,
        log_completions: bool,
        config: str,
    ) -> None:
        if config == "none":
            appspec = make_appspec(llm_config=None)
        else:
            cfg = _llm_config(
                redact_pii=redact_pii, log_prompts=log_prompts, log_completions=log_completions
            )
            appspec = make_appspec(llm_config=cfg)
        assert agent.llm_logging_no_redaction(appspec) == []


# =============================================================================
# OP-04  SLA without breach action
# =============================================================================


class TestOP04SlaWithoutBreachAction:
    def test_flags_sla_with_no_breach_action(self, agent: OperationalHygieneAgent) -> None:
        sla = _sla("response_sla", on_breach=None)
        findings = agent.sla_without_breach_action(make_appspec(slas=[sla]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "OP-04"
        assert findings[0].severity == Severity.HIGH
        assert "response_sla" in findings[0].title

    def test_passes_when_breach_action_set(self, agent: OperationalHygieneAgent) -> None:
        sla = _sla("response_sla", on_breach=MagicMock())
        assert agent.sla_without_breach_action(make_appspec(slas=[sla])) == []

    def test_passes_when_no_slas(self, agent: OperationalHygieneAgent) -> None:
        assert agent.sla_without_breach_action(make_appspec(slas=[])) == []


# =============================================================================
# OP-05  Approval without escalation
# =============================================================================


class TestOP05ApprovalWithoutEscalation:
    def test_flags_approval_with_no_escalation(self, agent: OperationalHygieneAgent) -> None:
        approval = _approval("purchase_approval", escalation=None)
        findings = agent.approval_without_escalation(make_appspec(approvals=[approval]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "OP-05"
        assert findings[0].severity == Severity.MEDIUM
        assert "purchase_approval" in findings[0].title

    def test_passes_when_escalation_set(self, agent: OperationalHygieneAgent) -> None:
        approval = _approval("purchase_approval", escalation=MagicMock())
        assert agent.approval_without_escalation(make_appspec(approvals=[approval])) == []

    def test_passes_when_no_approvals(self, agent: OperationalHygieneAgent) -> None:
        assert agent.approval_without_escalation(make_appspec(approvals=[])) == []


# =============================================================================
# OP-06  Process without compensation
# =============================================================================


class TestOP06ProcessWithoutCompensation:
    def test_flags_process_with_service_steps_no_compensation(
        self, agent: OperationalHygieneAgent
    ) -> None:
        proc = _process(
            "approve_order",
            [_service_step("validate"), _service_step("execute")],
            compensations=[],
        )
        findings = agent.process_without_compensation(make_appspec(processes=[proc]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "OP-06"
        assert findings[0].severity == Severity.MEDIUM
        assert "approve_order" in findings[0].title

    def test_passes_when_compensations_exist(self, agent: OperationalHygieneAgent) -> None:
        proc = _process(
            "approve_order",
            [_service_step("validate"), _service_step("execute")],
            compensations=[MagicMock()],
        )
        assert agent.process_without_compensation(make_appspec(processes=[proc])) == []

    def test_passes_when_no_processes(self, agent: OperationalHygieneAgent) -> None:
        assert agent.process_without_compensation(make_appspec(processes=[])) == []

    @pytest.mark.parametrize(
        ("steps", "proc_name"),
        [
            ([_service_step("validate")], "simple_process"),
            (
                [
                    _non_service_step("notify", StepKind.SEND),
                    _non_service_step("pause", StepKind.WAIT),
                ],
                "notification_flow",
            ),
            (
                [_service_step("validate"), _non_service_step("notify", StepKind.SEND)],
                "mixed_process",
            ),
        ],
        ids=["fewer_than_two_service_steps", "non_service_only", "mixed_counts_service_only"],
    )
    def test_no_finding_insufficient_service_steps(
        self,
        agent: OperationalHygieneAgent,
        steps: list,
        proc_name: str,
    ) -> None:
        proc = _process(proc_name, steps, compensations=[])
        assert agent.process_without_compensation(make_appspec(processes=[proc])) == []


# =============================================================================
# OP-07  Process service step without retry
# =============================================================================


class TestOP07ServiceStepWithoutRetry:
    def test_flags_service_step_without_retry(self, agent: OperationalHygieneAgent) -> None:
        proc = _process("approve_order", [_service_step("validate", retry=None)])
        findings = agent.service_step_without_retry(make_appspec(processes=[proc]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "OP-07"
        assert findings[0].severity == Severity.MEDIUM
        assert "validate" in findings[0].title
        assert "approve_order" in findings[0].title

    def test_passes_when_retry_configured(self, agent: OperationalHygieneAgent) -> None:
        proc = _process("approve_order", [_service_step("validate", retry=MagicMock())])
        assert agent.service_step_without_retry(make_appspec(processes=[proc])) == []

    def test_skips_non_service_steps(self, agent: OperationalHygieneAgent) -> None:
        proc = _process("notification_flow", [_non_service_step("notify", StepKind.SEND)])
        assert agent.service_step_without_retry(make_appspec(processes=[proc])) == []

    def test_passes_when_no_processes(self, agent: OperationalHygieneAgent) -> None:
        assert agent.service_step_without_retry(make_appspec(processes=[])) == []


# =============================================================================
# OP-08  SLA without tiers
# =============================================================================


class TestOP08SlaWithoutTiers:
    def test_flags_sla_with_empty_tiers(self, agent: OperationalHygieneAgent) -> None:
        sla = _sla("response_sla", tiers=[])
        findings = agent.sla_without_tiers(make_appspec(slas=[sla]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "OP-08"
        assert findings[0].severity == Severity.MEDIUM
        assert "response_sla" in findings[0].title

    def test_passes_when_tiers_defined(self, agent: OperationalHygieneAgent) -> None:
        sla = _sla("response_sla", tiers=[MagicMock()])
        assert agent.sla_without_tiers(make_appspec(slas=[sla])) == []

    def test_passes_when_no_slas(self, agent: OperationalHygieneAgent) -> None:
        assert agent.sla_without_tiers(make_appspec(slas=[])) == []


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

    def test_run_iterates_across_collections(self, agent: OperationalHygieneAgent) -> None:
        # Multiple offenders in multiple collections — exercises the iteration
        # path that was previously tested in per-heuristic 'multiple_X' tests.
        slas = [
            _sla("response_sla", on_breach=None, tiers=[]),
            _sla("resolution_sla", on_breach=None, tiers=[]),
        ]
        approvals = [
            _approval("a", escalation=None),
            _approval("b", escalation=None),
        ]
        intents = [
            _llm_intent("classify_a", pii=None),
            _llm_intent("classify_b", pii=None),
        ]
        result = agent.run(make_appspec(slas=slas, approvals=approvals, llm_intents=intents))
        ids = [f.heuristic_id for f in result.findings]
        assert ids.count("OP-04") == 2  # 2 SLAs without breach
        assert ids.count("OP-05") == 2  # 2 approvals without escalation
        assert ids.count("OP-02") == 2  # 2 intents without PII
        assert ids.count("OP-08") == 2  # 2 SLAs without tiers
