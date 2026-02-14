"""Operational Hygiene detection agent (OP-01 through OP-08)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.sentinel.agents.base import DetectionAgent, heuristic
from dazzle.sentinel.models import (
    AgentId,
    Confidence,
    Evidence,
    Finding,
    Remediation,
    RemediationEffort,
    Severity,
)

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec

_PII_CLASSIFICATIONS = frozenset({"pii_direct", "pii_indirect", "pii_sensitive"})


class OperationalHygieneAgent(DetectionAgent):
    """Detect operational hygiene gaps in the application spec."""

    @property
    def agent_id(self) -> AgentId:
        return AgentId.OP

    # ------------------------------------------------------------------
    # OP-01: Entity audit without field-level tracking
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="OP-01",
        category="operations",
        subcategory="audit",
        title="Entity audit without field-level tracking",
    )
    def audit_without_field_tracking(self, appspec: AppSpec) -> list[Finding]:
        """Flag entities with audit enabled but log_field_changes disabled,
        where the entity holds classified data."""
        findings: list[Finding] = []
        if appspec.policies is None:
            return findings

        classified_entities = {c.entity for c in appspec.policies.classifications}

        for entity in appspec.domain.entities:
            if entity.name not in classified_entities:
                continue
            audit = getattr(entity, "audit", None)
            if audit is None:
                continue
            if not getattr(audit, "enabled", False):
                continue
            if getattr(audit, "log_field_changes", True):
                continue
            findings.append(
                Finding(
                    agent=AgentId.OP,
                    heuristic_id="OP-01",
                    category="operations",
                    subcategory="audit",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.LIKELY,
                    title=(f"Entity '{entity.name}' audit does not track field-level changes"),
                    description=(
                        f"Entity '{entity.name}' has audit enabled but "
                        f"log_field_changes is disabled. Since this entity "
                        f"holds classified data, field-level tracking is "
                        f"important for compliance investigations."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="config_value",
                            location=f"entity:{entity.name}",
                            snippet="audit.log_field_changes: false",
                        ),
                    ],
                    remediation=Remediation(
                        summary=(f"Enable log_field_changes on entity '{entity.name}'."),
                        effort=RemediationEffort.TRIVIAL,
                    ),
                    entity_name=entity.name,
                    construct_type="entity",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # OP-02: LLM intent without PII policy
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="OP-02",
        category="operations",
        subcategory="llm",
        title="LLM intent without PII policy",
    )
    def llm_intent_no_pii_policy(self, appspec: AppSpec) -> list[Finding]:
        """Flag LLM intents that have no PII handling policy."""
        findings: list[Finding] = []
        for intent in appspec.llm_intents:
            if intent.pii is not None:
                continue
            findings.append(
                Finding(
                    agent=AgentId.OP,
                    heuristic_id="OP-02",
                    category="operations",
                    subcategory="llm",
                    severity=Severity.HIGH,
                    confidence=Confidence.LIKELY,
                    title=f"LLM intent '{intent.name}' has no PII policy",
                    description=(
                        f"LLM intent '{intent.name}' does not configure a "
                        f"PII handling policy. Prompts containing personal "
                        f"data may be sent to external LLM providers without "
                        f"scanning or redaction."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="missing_construct",
                            location=f"llm_intent:{intent.name}",
                            context="pii is None",
                        ),
                    ],
                    remediation=Remediation(
                        summary=f"Add a PII policy to intent '{intent.name}'.",
                        effort=RemediationEffort.SMALL,
                        dsl_example=(
                            f"llm_intent {intent.name}:\n  pii:\n    scan: true\n    action: redact"
                        ),
                    ),
                    construct_type="llm_intent",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # OP-03: LLM logging without PII redaction
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="OP-03",
        category="operations",
        subcategory="llm",
        title="LLM logging without PII redaction",
    )
    def llm_logging_no_redaction(self, appspec: AppSpec) -> list[Finding]:
        """Flag LLM config where logging is enabled but PII redaction is off."""
        findings: list[Finding] = []
        if appspec.llm_config is None:
            return findings
        logging_cfg = appspec.llm_config.logging
        if logging_cfg.redact_pii:
            return findings
        # Only flag if at least something is being logged.
        if not logging_cfg.log_prompts and not logging_cfg.log_completions:
            return findings
        findings.append(
            Finding(
                agent=AgentId.OP,
                heuristic_id="OP-03",
                category="operations",
                subcategory="llm",
                severity=Severity.MEDIUM,
                confidence=Confidence.CONFIRMED,
                title="LLM logging enabled without PII redaction",
                description=(
                    "LLM config logs prompts and/or completions but "
                    "redact_pii is disabled. Personal data may be "
                    "persisted in log artifacts, violating data "
                    "protection policies."
                ),
                evidence=[
                    Evidence(
                        evidence_type="config_value",
                        location="llm_config",
                        snippet=(
                            f"log_prompts: {logging_cfg.log_prompts}, "
                            f"log_completions: {logging_cfg.log_completions}, "
                            f"redact_pii: false"
                        ),
                    ),
                ],
                remediation=Remediation(
                    summary="Enable redact_pii in LLM logging config.",
                    effort=RemediationEffort.TRIVIAL,
                    dsl_example=("llm_config:\n  logging:\n    redact_pii: true"),
                ),
                construct_type="llm_config",
            ),
        )
        return findings

    # ------------------------------------------------------------------
    # OP-04: SLA without breach action
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="OP-04",
        category="operations",
        subcategory="sla",
        title="SLA without breach action",
    )
    def sla_without_breach_action(self, appspec: AppSpec) -> list[Finding]:
        """Flag SLAs that have no on_breach action configured."""
        findings: list[Finding] = []
        for sla in appspec.slas:
            if sla.on_breach is not None:
                continue
            findings.append(
                Finding(
                    agent=AgentId.OP,
                    heuristic_id="OP-04",
                    category="operations",
                    subcategory="sla",
                    severity=Severity.HIGH,
                    confidence=Confidence.CONFIRMED,
                    title=f"SLA '{sla.name}' has no breach action",
                    description=(
                        f"SLA '{sla.name}' does not define an on_breach "
                        f"action. When the SLA is breached no one is "
                        f"notified and no automated remediation occurs."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="missing_construct",
                            location=f"sla:{sla.name}",
                            context="on_breach is None",
                        ),
                    ],
                    remediation=Remediation(
                        summary=f"Add on_breach action to SLA '{sla.name}'.",
                        effort=RemediationEffort.SMALL,
                        dsl_example=(f"sla {sla.name}:\n  on_breach:\n    notify: support_lead"),
                    ),
                    construct_type="sla",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # OP-05: Approval without escalation
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="OP-05",
        category="operations",
        subcategory="approvals",
        title="Approval without escalation",
    )
    def approval_without_escalation(self, appspec: AppSpec) -> list[Finding]:
        """Flag approvals that have no escalation configured."""
        findings: list[Finding] = []
        for approval in appspec.approvals:
            if approval.escalation is not None:
                continue
            findings.append(
                Finding(
                    agent=AgentId.OP,
                    heuristic_id="OP-05",
                    category="operations",
                    subcategory="approvals",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.LIKELY,
                    title=(f"Approval '{approval.name}' has no escalation"),
                    description=(
                        f"Approval '{approval.name}' does not define an "
                        f"escalation path. If the assigned approver is "
                        f"unavailable, requests will stall indefinitely."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="missing_construct",
                            location=f"approval:{approval.name}",
                            context="escalation is None",
                        ),
                    ],
                    remediation=Remediation(
                        summary=(f"Add escalation config to approval '{approval.name}'."),
                        effort=RemediationEffort.SMALL,
                        dsl_example=(
                            f"approval {approval.name}:\n"
                            f"  escalation:\n"
                            f"    after: 48 hours\n"
                            f"    to: senior_manager"
                        ),
                    ),
                    construct_type="approval",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # OP-06: Process without compensation (saga)
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="OP-06",
        category="operations",
        subcategory="resilience",
        title="Process without compensation",
    )
    def process_without_compensation(self, appspec: AppSpec) -> list[Finding]:
        """Flag processes with service steps but no compensations."""
        from dazzle.core.ir.process import StepKind

        findings: list[Finding] = []
        for process in appspec.processes:
            service_steps = [s for s in process.steps if s.kind == StepKind.SERVICE]
            if len(service_steps) < 2:
                continue
            if process.compensations:
                continue
            findings.append(
                Finding(
                    agent=AgentId.OP,
                    heuristic_id="OP-06",
                    category="operations",
                    subcategory="resilience",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.LIKELY,
                    title=(
                        f"Process '{process.name}' has "
                        f"{len(service_steps)} service steps but no "
                        f"compensations"
                    ),
                    description=(
                        f"Process '{process.name}' orchestrates "
                        f"{len(service_steps)} service calls but defines "
                        f"no compensation handlers. If a step fails "
                        f"mid-process, earlier steps cannot be rolled back "
                        f"(saga pattern)."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="ir_pattern",
                            location=f"process:{process.name}",
                            snippet=(f"service steps: {[s.name for s in service_steps]}"),
                            context="compensations: []",
                        ),
                    ],
                    remediation=Remediation(
                        summary=(f"Add compensation handlers to process '{process.name}'."),
                        effort=RemediationEffort.MEDIUM,
                    ),
                    construct_type="process",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # OP-07: Process service step without retry
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="OP-07",
        category="operations",
        subcategory="resilience",
        title="Process service step without retry",
    )
    def service_step_without_retry(self, appspec: AppSpec) -> list[Finding]:
        """Flag process service steps that have no retry configuration."""
        from dazzle.core.ir.process import StepKind

        findings: list[Finding] = []
        for process in appspec.processes:
            for step in process.steps:
                if step.kind != StepKind.SERVICE:
                    continue
                if step.retry is not None:
                    continue
                findings.append(
                    Finding(
                        agent=AgentId.OP,
                        heuristic_id="OP-07",
                        category="operations",
                        subcategory="resilience",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.LIKELY,
                        title=(
                            f"Step '{step.name}' in process '{process.name}' has no retry config"
                        ),
                        description=(
                            f"Service step '{step.name}' in process "
                            f"'{process.name}' does not configure retry "
                            f"behaviour. Transient failures will cause the "
                            f"entire process to fail immediately."
                        ),
                        evidence=[
                            Evidence(
                                evidence_type="missing_construct",
                                location=(f"process:{process.name}/step:{step.name}"),
                                context="retry is None",
                            ),
                        ],
                        remediation=Remediation(
                            summary=(f"Add retry config to step '{step.name}'."),
                            effort=RemediationEffort.SMALL,
                        ),
                        construct_type="process",
                    ),
                )
        return findings

    # ------------------------------------------------------------------
    # OP-08: SLA without tiers
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="OP-08",
        category="operations",
        subcategory="sla",
        title="SLA without tiers",
    )
    def sla_without_tiers(self, appspec: AppSpec) -> list[Finding]:
        """Flag SLAs that define no escalation tiers."""
        findings: list[Finding] = []
        for sla in appspec.slas:
            if sla.tiers:
                continue
            findings.append(
                Finding(
                    agent=AgentId.OP,
                    heuristic_id="OP-08",
                    category="operations",
                    subcategory="sla",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.CONFIRMED,
                    title=f"SLA '{sla.name}' has no tiers defined",
                    description=(
                        f"SLA '{sla.name}' does not define any tiers "
                        f"(warning, breach, critical). Without tiers "
                        f"there are no measurable deadlines and "
                        f"escalation cannot be triggered."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="missing_construct",
                            location=f"sla:{sla.name}",
                            context="tiers is empty",
                        ),
                    ],
                    remediation=Remediation(
                        summary=f"Add tiers to SLA '{sla.name}'.",
                        effort=RemediationEffort.SMALL,
                        dsl_example=(
                            f"sla {sla.name}:\n"
                            f"  tiers:\n"
                            f"    warning: 4 hours\n"
                            f"    breach: 8 hours\n"
                            f"    critical: 24 hours"
                        ),
                    ),
                    construct_type="sla",
                ),
            )
        return findings
