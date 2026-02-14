"""Integration & Dependency detection agent (ID-01 through ID-08)."""

from __future__ import annotations

import re
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

_CONFIG_RE = re.compile(r"config\s*\(")


class IntegrationDependencyAgent(DetectionAgent):
    """Detect integration and dependency risks in the application spec."""

    @property
    def agent_id(self) -> AgentId:
        return AgentId.ID

    # ------------------------------------------------------------------
    # ID-01: External API without authentication
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="ID-01",
        category="integration",
        subcategory="auth",
        title="External API without authentication",
    )
    def api_without_auth(self, appspec: AppSpec) -> list[Finding]:
        """Flag external APIs that use auth kind 'none'."""
        from dazzle.core.ir.services import AuthKind

        findings: list[Finding] = []
        for api in appspec.apis:
            if api.auth_profile.kind == AuthKind.NONE:
                findings.append(
                    Finding(
                        agent=AgentId.ID,
                        heuristic_id="ID-01",
                        category="integration",
                        subcategory="auth",
                        severity=Severity.HIGH,
                        confidence=Confidence.CONFIRMED,
                        title=f"API '{api.name}' has no authentication",
                        description=(
                            f"External API '{api.name}' is configured with "
                            f"auth kind 'none'. Calls to this API will be "
                            f"unauthenticated, risking unauthorized access "
                            f"and data exposure."
                        ),
                        evidence=[
                            Evidence(
                                evidence_type="config_value",
                                location=f"api:{api.name}",
                                snippet="auth_profile.kind: none",
                            ),
                        ],
                        remediation=Remediation(
                            summary=f"Add authentication to API '{api.name}'.",
                            effort=RemediationEffort.SMALL,
                            guidance=(
                                "Configure an auth profile with oauth2, "
                                "api_key, or jwt authentication."
                            ),
                            dsl_example=(
                                f'api {api.name} "{api.title or api.name}":\n'
                                f"  auth:\n"
                                f"    kind: api_key_header"
                            ),
                        ),
                        construct_type="api",
                    ),
                )
        return findings

    # ------------------------------------------------------------------
    # ID-02: Integration referencing unknown API
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="ID-02",
        category="integration",
        subcategory="references",
        title="Integration referencing unknown API",
    )
    def integration_unknown_api(self, appspec: AppSpec) -> list[Finding]:
        """Flag integrations that reference APIs not defined in the spec."""
        findings: list[Finding] = []
        known_apis = {api.name for api in appspec.apis}
        for integration in appspec.integrations:
            for ref in integration.api_refs:
                if ref not in known_apis:
                    findings.append(
                        Finding(
                            agent=AgentId.ID,
                            heuristic_id="ID-02",
                            category="integration",
                            subcategory="references",
                            severity=Severity.HIGH,
                            confidence=Confidence.CONFIRMED,
                            title=(
                                f"Integration '{integration.name}' references unknown API '{ref}'"
                            ),
                            description=(
                                f"Integration '{integration.name}' lists API "
                                f"'{ref}' in api_refs but no APISpec with that "
                                f"name exists. The integration will fail at "
                                f"runtime."
                            ),
                            evidence=[
                                Evidence(
                                    evidence_type="ir_pattern",
                                    location=f"integration:{integration.name}",
                                    snippet=f"api_refs: {integration.api_refs}",
                                    context=f"Known APIs: {sorted(known_apis) or '(none)'}",
                                ),
                            ],
                            remediation=Remediation(
                                summary=f"Define API '{ref}' or fix the reference.",
                                effort=RemediationEffort.SMALL,
                            ),
                            construct_type="integration",
                        ),
                    )
        return findings

    # ------------------------------------------------------------------
    # ID-03: Integration referencing unknown foreign model
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="ID-03",
        category="integration",
        subcategory="references",
        title="Integration referencing unknown foreign model",
    )
    def integration_unknown_foreign_model(self, appspec: AppSpec) -> list[Finding]:
        """Flag integrations that reference foreign models not in the spec."""
        findings: list[Finding] = []
        known_fms = {fm.name for fm in appspec.foreign_models}
        for integration in appspec.integrations:
            for ref in integration.foreign_model_refs:
                if ref not in known_fms:
                    findings.append(
                        Finding(
                            agent=AgentId.ID,
                            heuristic_id="ID-03",
                            category="integration",
                            subcategory="references",
                            severity=Severity.HIGH,
                            confidence=Confidence.CONFIRMED,
                            title=(
                                f"Integration '{integration.name}' references "
                                f"unknown foreign model '{ref}'"
                            ),
                            description=(
                                f"Integration '{integration.name}' lists "
                                f"foreign model '{ref}' in foreign_model_refs "
                                f"but no ForeignModelSpec with that name "
                                f"exists."
                            ),
                            evidence=[
                                Evidence(
                                    evidence_type="ir_pattern",
                                    location=f"integration:{integration.name}",
                                    snippet=f"foreign_model_refs: {integration.foreign_model_refs}",
                                    context=f"Known FMs: {sorted(known_fms) or '(none)'}",
                                ),
                            ],
                            remediation=Remediation(
                                summary=f"Define foreign model '{ref}' or fix the reference.",
                                effort=RemediationEffort.SMALL,
                            ),
                            construct_type="integration",
                        ),
                    )
        return findings

    # ------------------------------------------------------------------
    # ID-04: Webhook without retry configuration
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="ID-04",
        category="integration",
        subcategory="resilience",
        title="Webhook without retry configuration",
    )
    def webhook_without_retry(self, appspec: AppSpec) -> list[Finding]:
        """Flag webhooks that have no retry policy configured."""
        findings: list[Finding] = []
        for webhook in appspec.webhooks:
            if webhook.retry is not None:
                continue
            findings.append(
                Finding(
                    agent=AgentId.ID,
                    heuristic_id="ID-04",
                    category="integration",
                    subcategory="resilience",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.CONFIRMED,
                    title=f"Webhook '{webhook.name}' has no retry configuration",
                    description=(
                        f"Webhook '{webhook.name}' does not define a retry "
                        f"policy. Transient failures will cause permanent "
                        f"missed notifications."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="missing_construct",
                            location=f"webhook:{webhook.name}",
                            context="webhook.retry is None",
                        ),
                    ],
                    remediation=Remediation(
                        summary=f"Add retry configuration to webhook '{webhook.name}'.",
                        effort=RemediationEffort.SMALL,
                        dsl_example=(
                            f"webhook {webhook.name}:\n"
                            f"  retry:\n"
                            f"    max_attempts: 3\n"
                            f"    backoff: exponential"
                        ),
                    ),
                    construct_type="webhook",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # ID-05: Hard-coded webhook URL
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="ID-05",
        category="integration",
        subcategory="configuration",
        title="Hard-coded webhook URL",
    )
    def hardcoded_webhook_url(self, appspec: AppSpec) -> list[Finding]:
        """Flag webhooks with literal URLs instead of config() references."""
        findings: list[Finding] = []
        for webhook in appspec.webhooks:
            if not webhook.url:
                continue
            if _CONFIG_RE.search(webhook.url):
                continue
            findings.append(
                Finding(
                    agent=AgentId.ID,
                    heuristic_id="ID-05",
                    category="integration",
                    subcategory="configuration",
                    severity=Severity.LOW,
                    confidence=Confidence.LIKELY,
                    title=f"Webhook '{webhook.name}' has a hard-coded URL",
                    description=(
                        f"Webhook '{webhook.name}' uses a literal URL "
                        f"instead of a config() reference. Hard-coded URLs "
                        f"cannot vary across environments."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="config_value",
                            location=f"webhook:{webhook.name}",
                            snippet=f"url: {webhook.url}",
                        ),
                    ],
                    remediation=Remediation(
                        summary="Use config() to externalise the webhook URL.",
                        effort=RemediationEffort.TRIVIAL,
                        dsl_example=(f'  url: config("WEBHOOK_{webhook.name.upper()}_URL")'),
                    ),
                    construct_type="webhook",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # ID-06: Foreign model without key fields
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="ID-06",
        category="integration",
        subcategory="data_model",
        title="Foreign model without key fields",
    )
    def foreign_model_no_keys(self, appspec: AppSpec) -> list[Finding]:
        """Flag foreign models with no key fields defined."""
        findings: list[Finding] = []
        for fm in appspec.foreign_models:
            if fm.key_fields:
                continue
            findings.append(
                Finding(
                    agent=AgentId.ID,
                    heuristic_id="ID-06",
                    category="integration",
                    subcategory="data_model",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.CONFIRMED,
                    title=f"Foreign model '{fm.name}' has no key fields",
                    description=(
                        f"Foreign model '{fm.name}' does not define key_fields. "
                        f"Without a key, sync operations cannot match foreign "
                        f"records to local entities, risking duplicate data."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="missing_construct",
                            location=f"foreign_model:{fm.name}",
                            context="key_fields is empty",
                        ),
                    ],
                    remediation=Remediation(
                        summary=f"Define key_fields on foreign model '{fm.name}'.",
                        effort=RemediationEffort.SMALL,
                    ),
                    construct_type="foreign_model",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # ID-07: Integration sync without match rules
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="ID-07",
        category="integration",
        subcategory="sync",
        title="Integration sync without match rules",
    )
    def sync_without_match_rules(self, appspec: AppSpec) -> list[Finding]:
        """Flag integration syncs that have no match rules."""
        findings: list[Finding] = []
        for integration in appspec.integrations:
            for sync in integration.syncs:
                if sync.match_rules:
                    continue
                findings.append(
                    Finding(
                        agent=AgentId.ID,
                        heuristic_id="ID-07",
                        category="integration",
                        subcategory="sync",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.CONFIRMED,
                        title=(
                            f"Sync '{sync.name}' in integration "
                            f"'{integration.name}' has no match rules"
                        ),
                        description=(
                            f"Sync '{sync.name}' does not define match_rules "
                            f"to map foreign records to local entities. "
                            f"Without match rules the sync cannot perform "
                            f"upserts and may create duplicates."
                        ),
                        evidence=[
                            Evidence(
                                evidence_type="missing_construct",
                                location=f"integration:{integration.name}/sync:{sync.name}",
                                context="match_rules is empty",
                            ),
                        ],
                        remediation=Remediation(
                            summary=f"Add match_rules to sync '{sync.name}'.",
                            effort=RemediationEffort.SMALL,
                        ),
                        construct_type="integration",
                    ),
                )
        return findings

    # ------------------------------------------------------------------
    # ID-08: Integration-kind service without guarantees
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="ID-08",
        category="integration",
        subcategory="contracts",
        title="Integration service without guarantees",
    )
    def integration_service_no_guarantees(self, appspec: AppSpec) -> list[Finding]:
        """Flag domain services of kind 'integration' that define no guarantees."""
        from dazzle.core.ir.services import DomainServiceKind

        findings: list[Finding] = []
        for svc in appspec.domain_services:
            if svc.kind != DomainServiceKind.INTEGRATION:
                continue
            if svc.guarantees:
                continue
            findings.append(
                Finding(
                    agent=AgentId.ID,
                    heuristic_id="ID-08",
                    category="integration",
                    subcategory="contracts",
                    severity=Severity.LOW,
                    confidence=Confidence.LIKELY,
                    title=f"Integration service '{svc.name}' has no guarantees",
                    description=(
                        f"Domain service '{svc.name}' is of kind 'integration' "
                        f"but defines no behavioural guarantees. Guarantees "
                        f"document idempotency, timeout, and error contracts "
                        f"for consumers."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="missing_construct",
                            location=f"service:{svc.name}",
                            context="guarantees is empty",
                        ),
                    ],
                    remediation=Remediation(
                        summary=f"Add guarantees to service '{svc.name}'.",
                        effort=RemediationEffort.SMALL,
                        dsl_example=(
                            f'service {svc.name} "{svc.title or svc.name}":\n'
                            f"  kind: integration\n"
                            f"  guarantees:\n"
                            f'    - "Idempotent: safe to retry on failure."\n'
                            f'    - "Timeout: 30 seconds."'
                        ),
                    ),
                    construct_type="service",
                ),
            )
        return findings
