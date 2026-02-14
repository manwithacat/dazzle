"""Deployment & State detection agent (DS-01 through DS-08)."""

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
    # DS-01: Interface API without authentication
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="DS-01",
        category="deployment",
        subcategory="auth",
        title="Interface API without authentication",
    )
    def interface_without_auth(self, appspec: AppSpec) -> list[Finding]:
        """Flag interface APIs that use auth method 'none'."""
        from dazzle.core.ir.governance import InterfaceAuthMethod

        findings: list[Finding] = []
        if appspec.interfaces is None:
            return findings
        for api in appspec.interfaces.apis:
            if api.auth != InterfaceAuthMethod.NONE:
                continue
            findings.append(
                Finding(
                    agent=AgentId.DS,
                    heuristic_id="DS-01",
                    category="deployment",
                    subcategory="auth",
                    severity=Severity.HIGH,
                    confidence=Confidence.CONFIRMED,
                    title=f"Interface '{api.name}' has no authentication",
                    description=(
                        f"Interface API '{api.name}' uses auth method 'none'. "
                        f"Any caller can access this API without credentials, "
                        f"including bots and malicious actors."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="config_value",
                            location=f"interface:{api.name}",
                            snippet=f"auth: {api.auth.value}",
                        ),
                    ],
                    remediation=Remediation(
                        summary=f"Add authentication to interface '{api.name}'.",
                        effort=RemediationEffort.MEDIUM,
                        dsl_example=(f"interfaces:\n  api {api.name}:\n    auth: oauth2"),
                    ),
                    construct_type="interface",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # DS-02: Interface API without rate limiting
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="DS-02",
        category="deployment",
        subcategory="resilience",
        title="Interface API without rate limiting",
    )
    def interface_without_rate_limit(self, appspec: AppSpec) -> list[Finding]:
        """Flag interface APIs that have no rate limit configured."""
        findings: list[Finding] = []
        if appspec.interfaces is None:
            return findings
        for api in appspec.interfaces.apis:
            if api.rate_limit is not None:
                continue
            findings.append(
                Finding(
                    agent=AgentId.DS,
                    heuristic_id="DS-02",
                    category="deployment",
                    subcategory="resilience",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.LIKELY,
                    title=f"Interface '{api.name}' has no rate limit",
                    description=(
                        f"Interface API '{api.name}' does not define a "
                        f"rate_limit. Without rate limiting the API is "
                        f"vulnerable to abuse and denial-of-service."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="missing_construct",
                            location=f"interface:{api.name}",
                            context="rate_limit is None",
                        ),
                    ],
                    remediation=Remediation(
                        summary=f"Add rate limiting to interface '{api.name}'.",
                        effort=RemediationEffort.SMALL,
                        dsl_example=(f"interfaces:\n  api {api.name}:\n    rate_limit: 1000/hour"),
                    ),
                    construct_type="interface",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # DS-03: Transaction without idempotency key
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="DS-03",
        category="deployment",
        subcategory="state",
        title="Transaction without idempotency key",
    )
    def transaction_without_idempotency(self, appspec: AppSpec) -> list[Finding]:
        """Flag transactions that have no idempotency key."""
        findings: list[Finding] = []
        for txn in appspec.transactions:
            if txn.idempotency_key:
                continue
            findings.append(
                Finding(
                    agent=AgentId.DS,
                    heuristic_id="DS-03",
                    category="deployment",
                    subcategory="state",
                    severity=Severity.HIGH,
                    confidence=Confidence.CONFIRMED,
                    title=f"Transaction '{txn.name}' has no idempotency key",
                    description=(
                        f"Transaction '{txn.name}' does not define an "
                        f"idempotency_key. Retries or duplicate submissions "
                        f"may produce duplicate financial entries."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="missing_construct",
                            location=f"transaction:{txn.name}",
                            context="idempotency_key is empty",
                        ),
                    ],
                    remediation=Remediation(
                        summary=f"Add an idempotency key to transaction '{txn.name}'.",
                        effort=RemediationEffort.SMALL,
                        dsl_example=(f"transaction {txn.name}:\n  idempotency_key: payment.id"),
                    ),
                    construct_type="transaction",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # DS-04: Queue channel with direct delivery
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="DS-04",
        category="deployment",
        subcategory="messaging",
        title="Queue channel with direct delivery",
    )
    def queue_direct_delivery(self, appspec: AppSpec) -> list[Finding]:
        """Flag queue channels with send operations using direct delivery."""
        from dazzle.core.ir.messaging import ChannelKind, DeliveryMode

        findings: list[Finding] = []
        for channel in appspec.channels:
            if channel.kind != ChannelKind.QUEUE:
                continue
            for op in channel.send_operations:
                if op.delivery_mode != DeliveryMode.DIRECT:
                    continue
                findings.append(
                    Finding(
                        agent=AgentId.DS,
                        heuristic_id="DS-04",
                        category="deployment",
                        subcategory="messaging",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.LIKELY,
                        title=(
                            f"Queue channel '{channel.name}' send '{op.name}' uses direct delivery"
                        ),
                        description=(
                            f"Send operation '{op.name}' on queue channel "
                            f"'{channel.name}' uses delivery_mode 'direct' "
                            f"(fire-and-forget) instead of 'outbox'. "
                            f"Messages may be lost if the application crashes "
                            f"between committing the business transaction and "
                            f"publishing the message."
                        ),
                        evidence=[
                            Evidence(
                                evidence_type="config_value",
                                location=f"channel:{channel.name}/send:{op.name}",
                                snippet=f"delivery_mode: {op.delivery_mode.value}",
                            ),
                        ],
                        remediation=Remediation(
                            summary=(
                                f"Use outbox delivery for send '{op.name}' "
                                f"on channel '{channel.name}'."
                            ),
                            effort=RemediationEffort.MEDIUM,
                            dsl_example=(
                                f"channel {channel.name}:\n"
                                f"  kind: queue\n"
                                f"  send {op.name}:\n"
                                f"    delivery: outbox"
                            ),
                        ),
                        construct_type="channel",
                    ),
                )
        return findings

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
    # DS-06: Transaction without validation rules
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="DS-06",
        category="deployment",
        subcategory="state",
        title="Transaction without validation rules",
    )
    def transaction_without_validations(self, appspec: AppSpec) -> list[Finding]:
        """Flag transactions that define no validation rules (preconditions)."""
        findings: list[Finding] = []
        for txn in appspec.transactions:
            if txn.validation:
                continue
            findings.append(
                Finding(
                    agent=AgentId.DS,
                    heuristic_id="DS-06",
                    category="deployment",
                    subcategory="state",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.LIKELY,
                    title=f"Transaction '{txn.name}' has no validation rules",
                    description=(
                        f"Transaction '{txn.name}' does not define any "
                        f"validation rules. Preconditions guard against "
                        f"invalid transfers (e.g. negative amounts, "
                        f"insufficient balance)."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="missing_construct",
                            location=f"transaction:{txn.name}",
                            context="validations is empty",
                        ),
                    ],
                    remediation=Remediation(
                        summary=f"Add validation rules to transaction '{txn.name}'.",
                        effort=RemediationEffort.SMALL,
                    ),
                    construct_type="transaction",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # DS-07: Channel without throttle configuration
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="DS-07",
        category="deployment",
        subcategory="messaging",
        title="Channel without throttle configuration",
    )
    def channel_without_throttle(self, appspec: AppSpec) -> list[Finding]:
        """Flag channels without provider rate-limit configuration."""
        findings: list[Finding] = []
        for channel in appspec.channels:
            if channel.provider_config is not None:
                continue
            findings.append(
                Finding(
                    agent=AgentId.DS,
                    heuristic_id="DS-07",
                    category="deployment",
                    subcategory="messaging",
                    severity=Severity.LOW,
                    confidence=Confidence.POSSIBLE,
                    title=f"Channel '{channel.name}' has no provider rate config",
                    description=(
                        f"Channel '{channel.name}' does not configure a "
                        f"provider_config. Without rate controls, burst traffic "
                        f"may overwhelm downstream consumers or exceed "
                        f"provider rate limits."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="missing_construct",
                            location=f"channel:{channel.name}",
                            context="provider_config is None",
                        ),
                    ],
                    remediation=Remediation(
                        summary=f"Add provider_config to channel '{channel.name}'.",
                        effort=RemediationEffort.SMALL,
                        dsl_example=(
                            f"channel {channel.name}:\n"
                            f"  provider_config:\n"
                            f"    max_per_minute: 200\n"
                            f"    max_concurrent: 10"
                        ),
                    ),
                    construct_type="channel",
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
