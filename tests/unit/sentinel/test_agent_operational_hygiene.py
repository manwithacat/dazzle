"""Tests for the Operational Hygiene detection agent (OP-01 to OP-04, OP-06 to OP-08).

One table: each case builds an AppSpec, runs one heuristic and pins the exact
findings (see ``assert_findings``). Agent identity, heuristic order and the
clean-spec run live in ``test_registry.py``.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from dazzle.core.ir.governance import DataClassification
from dazzle.core.ir.process import StepKind
from dazzle.sentinel.agents.operational_hygiene import OperationalHygieneAgent
from dazzle.sentinel.models import Severity

from .conftest import assert_findings, make_appspec, mock_entity

# ---------------------------------------------------------------------------
# Builders
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


def _audited(
    entity: str = "Customer",
    audit: object | None = None,
    classified: bool = True,
) -> Any:
    policies = _policies_with_classification("Customer", "email") if classified else None
    return make_appspec([mock_entity(entity, audit=audit)], policies=policies)


def _op(n: int, severity: Severity, title_has: str | tuple[str, ...] | None = None) -> Any:
    want: dict[str, Any] = {"heuristic_id": f"OP-0{n}", "severity": severity}
    if title_has is not None:
        want["title_has"] = title_has
    return [want]


def _procs(*steps: Any, name: str = "approve_order", compensations: list | None = None) -> Any:
    return make_appspec(processes=[_process(name, list(steps), compensations=compensations)])


# ---------------------------------------------------------------------------
# Heuristic table
# ---------------------------------------------------------------------------

CASES = [
    # OP-01  audited, classified entity without field-level change tracking
    pytest.param(
        "audit_without_field_tracking",
        lambda: _audited(audit=_audit(enabled=True, log_field_changes=False)),
        _op(1, Severity.MEDIUM, "Customer"),
        id="OP-01-flags-audit-without-field-changes",
    ),
    pytest.param(
        "audit_without_field_tracking",
        lambda: _audited(audit=_audit(enabled=True, log_field_changes=True)),
        [],
        id="OP-01-log-field-changes-enabled",
    ),
    pytest.param(
        "audit_without_field_tracking",
        lambda: _audited(audit=_audit(enabled=False)),
        [],
        id="OP-01-audit-disabled",
    ),
    pytest.param(
        "audit_without_field_tracking",
        lambda: _audited("Task", audit=_audit(enabled=True)),
        [],
        id="OP-01-entity-not-classified",
    ),
    pytest.param(
        "audit_without_field_tracking",
        lambda: _audited(audit=_audit(enabled=True), classified=False),
        [],
        id="OP-01-no-policies",
    ),
    pytest.param(
        "audit_without_field_tracking",
        lambda: _audited(audit=None),
        [],
        id="OP-01-no-audit-config",
    ),
    # OP-02  LLM intent without a PII policy
    pytest.param(
        "llm_intent_no_pii_policy",
        lambda: make_appspec(llm_intents=[_llm_intent("classify_ticket")]),
        _op(2, Severity.HIGH, "classify_ticket"),
        id="OP-02-flags-intent-without-pii",
    ),
    pytest.param(
        "llm_intent_no_pii_policy",
        lambda: make_appspec(llm_intents=[_llm_intent("classify_ticket", pii=MagicMock())]),
        [],
        id="OP-02-pii-set",
    ),
    pytest.param("llm_intent_no_pii_policy", make_appspec, [], id="OP-02-no-intents"),
    # OP-03  LLM prompt/completion logging without PII redaction
    *[
        pytest.param(
            "llm_logging_no_redaction",
            lambda p=prompts, c=completions: make_appspec(
                llm_config=_llm_config(log_prompts=p, log_completions=c)
            ),
            _op(3, Severity.MEDIUM),
            id=f"OP-03-flags-logging-{label}-without-redaction",
        )
        for prompts, completions, label in (
            (True, True, "both"),
            (True, False, "prompts-only"),
            (False, True, "completions-only"),
        )
    ],
    pytest.param(
        "llm_logging_no_redaction",
        lambda: make_appspec(llm_config=_llm_config(redact_pii=True)),
        [],
        id="OP-03-redaction-enabled",
    ),
    pytest.param(
        "llm_logging_no_redaction",
        lambda: make_appspec(llm_config=_llm_config(log_prompts=False, log_completions=False)),
        [],
        id="OP-03-no-logging",
    ),
    pytest.param("llm_logging_no_redaction", make_appspec, [], id="OP-03-no-llm-config"),
    # OP-04  SLA without a breach action
    pytest.param(
        "sla_without_breach_action",
        lambda: make_appspec(slas=[_sla("response_sla")]),
        _op(4, Severity.HIGH, "response_sla"),
        id="OP-04-flags-sla-without-breach-action",
    ),
    pytest.param(
        "sla_without_breach_action",
        lambda: make_appspec(slas=[_sla("response_sla", on_breach=MagicMock())]),
        [],
        id="OP-04-breach-action-set",
    ),
    pytest.param("sla_without_breach_action", make_appspec, [], id="OP-04-no-slas"),
    # OP-06  process with >=2 service steps and no compensation
    pytest.param(
        "process_without_compensation",
        lambda: _procs(_service_step("validate"), _service_step("execute")),
        _op(6, Severity.MEDIUM, "approve_order"),
        id="OP-06-flags-two-service-steps-without-compensation",
    ),
    pytest.param(
        "process_without_compensation",
        lambda: _procs(
            _service_step("validate"), _service_step("execute"), compensations=[MagicMock()]
        ),
        [],
        id="OP-06-compensations-exist",
    ),
    pytest.param("process_without_compensation", make_appspec, [], id="OP-06-no-processes"),
    pytest.param(
        "process_without_compensation",
        lambda: _procs(_service_step("validate")),
        [],
        id="OP-06-fewer-than-two-service-steps",
    ),
    pytest.param(
        "process_without_compensation",
        lambda: _procs(
            _non_service_step("notify", StepKind.SEND), _non_service_step("pause", StepKind.WAIT)
        ),
        [],
        id="OP-06-non-service-steps-only",
    ),
    pytest.param(
        "process_without_compensation",
        lambda: _procs(_service_step("validate"), _non_service_step("notify", StepKind.SEND)),
        [],
        id="OP-06-counts-service-steps-only",
    ),
    # OP-07  service step without retry (title names step and process)
    pytest.param(
        "service_step_without_retry",
        lambda: _procs(_service_step("validate")),
        _op(7, Severity.MEDIUM, ("validate", "approve_order")),
        id="OP-07-flags-service-step-without-retry",
    ),
    pytest.param(
        "service_step_without_retry",
        lambda: _procs(_service_step("validate", retry=MagicMock())),
        [],
        id="OP-07-retry-configured",
    ),
    pytest.param(
        "service_step_without_retry",
        lambda: _procs(_non_service_step("notify", StepKind.SEND)),
        [],
        id="OP-07-skips-non-service-step",
    ),
    pytest.param("service_step_without_retry", make_appspec, [], id="OP-07-no-processes"),
    # OP-08  SLA without tiers
    pytest.param(
        "sla_without_tiers",
        lambda: make_appspec(slas=[_sla("response_sla")]),
        _op(8, Severity.MEDIUM, "response_sla"),
        id="OP-08-flags-sla-without-tiers",
    ),
    pytest.param(
        "sla_without_tiers",
        lambda: make_appspec(slas=[_sla("response_sla", tiers=[MagicMock()])]),
        [],
        id="OP-08-tiers-defined",
    ),
    pytest.param("sla_without_tiers", make_appspec, [], id="OP-08-no-slas"),
]


@pytest.mark.parametrize(("heuristic", "build", "expected"), CASES)
def test_heuristic(
    heuristic: str, build: Callable[[], Any], expected: list[dict[str, Any]]
) -> None:
    assert_findings(getattr(OperationalHygieneAgent(), heuristic)(build()), expected)


def test_run_iterates_across_collections() -> None:
    # Multiple offenders in multiple collections — exercises the iteration
    # path that was previously tested in per-heuristic 'multiple_X' tests.
    slas = [
        _sla("response_sla", on_breach=None, tiers=[]),
        _sla("resolution_sla", on_breach=None, tiers=[]),
    ]
    intents = [
        _llm_intent("classify_a", pii=None),
        _llm_intent("classify_b", pii=None),
    ]
    result = OperationalHygieneAgent().run(make_appspec(slas=slas, llm_intents=intents))
    ids = [f.heuristic_id for f in result.findings]
    assert ids.count("OP-04") == 2  # 2 SLAs without breach
    assert ids.count("OP-02") == 2  # 2 intents without PII
    assert ids.count("OP-08") == 2  # 2 SLAs without tiers
