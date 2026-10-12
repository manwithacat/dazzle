"""Deployment & State detection agent (DS-05 and DS-08)."""

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
_SENSITIVE_CLASSIFICATIONS = _PII_CLASSIFICATIONS | frozenset(
    {"financial_txn", "financial_account"}
)


class DeploymentStateAgent(DetectionAgent):
    """Detect deployment and state management risks in the application spec."""

    @property
    def agent_id(self) -> AgentId:
        return AgentId.DS

    # ------------------------------------------------------------------
    # DS-05: PII data without erasure policy
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="DS-05",
        category="deployment",
        subcategory="governance",
        title="PII data without erasure policy",
    )
    def pii_without_erasure(self, appspec: AppSpec) -> list[Finding]:
        """Flag entities with PII classifications but no erasure policy."""
        findings: list[Finding] = []
        if appspec.policies is None:
            return findings

        pii_entities: dict[str, list[str]] = {}
        for cls in appspec.policies.classifications:
            if cls.classification.value in _PII_CLASSIFICATIONS:
                pii_entities.setdefault(cls.entity, []).append(cls.field)

        if not pii_entities:
            return findings

        erasure_entities = {e.entity for e in appspec.policies.erasures}

        for entity_name, fields in sorted(pii_entities.items()):
            if entity_name in erasure_entities:
                continue
            findings.append(
                Finding(
                    agent=AgentId.DS,
                    heuristic_id="DS-05",
                    category="deployment",
                    subcategory="governance",
                    severity=Severity.HIGH,
                    confidence=Confidence.CONFIRMED,
                    title=(f"Entity '{entity_name}' has PII but no erasure policy"),
                    description=(
                        f"Entity '{entity_name}' has PII-classified fields "
                        f"({', '.join(fields)}) but no erasure policy is "
                        f"defined. GDPR and similar regulations require a "
                        f"right-to-erasure mechanism for personal data."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="ir_pattern",
                            location=f"entity:{entity_name}",
                            context=f"PII fields: {fields}, no erasure spec",
                        ),
                    ],
                    remediation=Remediation(
                        summary=f"Add an erasure policy for entity '{entity_name}'.",
                        effort=RemediationEffort.MEDIUM,
                        dsl_example=(f"policies:\n  erasure {entity_name}: anonymize"),
                    ),
                    entity_name=entity_name,
                    construct_type="entity",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # DS-08: Audit access disabled with sensitive data
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="DS-08",
        category="deployment",
        subcategory="governance",
        title="Audit access disabled with sensitive data",
    )
    def audit_access_disabled_sensitive(self, appspec: AppSpec) -> list[Finding]:
        """Flag policies with audit_access disabled while sensitive classifications exist."""
        findings: list[Finding] = []
        if appspec.policies is None:
            return findings
        if appspec.policies.audit_access:
            return findings

        sensitive = [
            c
            for c in appspec.policies.classifications
            if c.classification.value in _SENSITIVE_CLASSIFICATIONS
        ]
        if not sensitive:
            return findings

        affected_entities = sorted({c.entity for c in sensitive})
        findings.append(
            Finding(
                agent=AgentId.DS,
                heuristic_id="DS-08",
                category="deployment",
                subcategory="governance",
                severity=Severity.HIGH,
                confidence=Confidence.CONFIRMED,
                title="Audit access disabled with sensitive data present",
                description=(
                    f"Policies set audit_access=false but sensitive data "
                    f"classifications exist on entities: {affected_entities}. "
                    f"Access to PII/financial data should be audited for "
                    f"compliance and breach investigation."
                ),
                evidence=[
                    Evidence(
                        evidence_type="config_value",
                        location="policies",
                        snippet="audit_access: false",
                        context=f"Sensitive entities: {affected_entities}",
                    ),
                ],
                remediation=Remediation(
                    summary="Enable audit_access in policies.",
                    effort=RemediationEffort.SMALL,
                    dsl_example="policies:\n  audit_access: true",
                ),
                construct_type="policies",
            ),
        )
        return findings
