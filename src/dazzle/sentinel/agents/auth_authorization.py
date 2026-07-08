"""Auth & Authorization detection agent (AA-01 through AA-08)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.core.ir.domain import PermissionKind, PolicyEffect
from dazzle.core.ir.security import SecurityProfile
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
    from dazzle.core.ir.conditions import ConditionExpr


def _condition_contains_principal_check(condition: ConditionExpr | None) -> bool:
    """True if any node of the condition tree checks WHO the caller is.

    A ``role(x)`` / grant check anywhere in the tree means the rule gates on
    the principal — the `permit: read: role(a) or role(b)` grammar stores its
    role gate here with ``personas == []`` (#1354). Field comparisons gate
    rows, not principals, and don't count.
    """
    if condition is None:
        return False
    if condition.role_check is not None or condition.grant_check is not None:
        return True
    return _condition_contains_principal_check(
        condition.left
    ) or _condition_contains_principal_check(condition.right)


# Sensitive classification levels that warrant stronger security.
_SENSITIVE_CLASSIFICATIONS = frozenset(
    {
        "pii_direct",
        "pii_indirect",
        "pii_sensitive",
        "financial_txn",
        "financial_account",
    }
)


class AuthAuthorizationAgent(DetectionAgent):
    """Detect auth and authorization gaps in the application spec."""

    @property
    def agent_id(self) -> AgentId:
        return AgentId.AA

    # ------------------------------------------------------------------
    # AA-01: Surface without access control
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="AA-01",
        category="auth",
        subcategory="access_control",
        title="Surface without access control",
    )
    def surface_without_access_control(self, appspec: AppSpec) -> list[Finding]:
        """Flag surfaces bound to an entity where neither surface nor entity defines access control."""
        findings: list[Finding] = []
        for surface in appspec.surfaces:
            if surface.entity_ref is None:
                continue
            entity = appspec.get_entity(surface.entity_ref)
            if surface.access is not None:
                continue
            if entity is not None and entity.access is not None:
                continue
            findings.append(
                Finding(
                    agent=AgentId.AA,
                    heuristic_id="AA-01",
                    category="auth",
                    subcategory="access_control",
                    severity=Severity.HIGH,
                    confidence=Confidence.CONFIRMED,
                    title=f"Surface '{surface.name}' has no access control",
                    description=(
                        f"Surface '{surface.name}' references entity "
                        f"'{surface.entity_ref}' but neither the surface nor "
                        f"the entity defines an access control specification. "
                        f"Any user — including unauthenticated visitors — can "
                        f"interact with this data."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="ir_pattern",
                            location=f"surface:{surface.name}",
                            context=(
                                f"surface.access is None, entity "
                                f"'{surface.entity_ref}' access is "
                                f"{'None' if entity is None else 'None'}"
                            ),
                        ),
                    ],
                    remediation=Remediation(
                        summary=(
                            f"Add an access block to surface '{surface.name}' "
                            f"or entity '{surface.entity_ref}'."
                        ),
                        effort=RemediationEffort.SMALL,
                        guidance=(
                            "Define 'access:' on the surface with "
                            "require_auth and allow_personas, or add an "
                            "access spec on the entity with permissions."
                        ),
                        dsl_example=(
                            f'surface {surface.name} "{surface.title or surface.name}":\n'
                            f"  uses entity {surface.entity_ref}\n"
                            f"  access:\n"
                            f"    require_auth: true\n"
                            f"    allow_personas: [admin]"
                        ),
                    ),
                    surface_name=surface.name,
                    entity_name=surface.entity_ref,
                    construct_type="surface",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # AA-02: Entity with no access spec
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="AA-02",
        category="auth",
        subcategory="access_control",
        title="Entity with no access spec",
    )
    def entity_no_access_spec(self, appspec: AppSpec) -> list[Finding]:
        """Flag entities that have no access specification at all."""
        findings: list[Finding] = []
        for entity in appspec.domain.entities:
            if entity.access is not None:
                continue
            findings.append(
                Finding(
                    agent=AgentId.AA,
                    heuristic_id="AA-02",
                    category="auth",
                    subcategory="access_control",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.LIKELY,
                    title=f"Entity '{entity.name}' has no access spec",
                    description=(
                        f"Entity '{entity.name}' does not define an access "
                        f"control specification. Without explicit permissions "
                        f"the runtime may default to open access. Some "
                        f"entities are intentionally internal-only, but this "
                        f"should be verified."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="missing_construct",
                            location=f"entity:{entity.name}",
                            context="entity.access is None",
                        ),
                    ],
                    remediation=Remediation(
                        summary=f"Add an access block to entity '{entity.name}'.",
                        effort=RemediationEffort.SMALL,
                        guidance=(
                            "Define visibility rules and CRUD permissions "
                            "using the access block on the entity."
                        ),
                        dsl_example=(
                            f'entity {entity.name} "{entity.title or entity.name}":\n'
                            f"  ...\n"
                            f"  access:\n"
                            f"    permissions:\n"
                            f"      create: authenticated\n"
                            f"      read: authenticated\n"
                            f"      update: created_by = current_user\n"
                            f"      delete: created_by = current_user"
                        ),
                    ),
                    entity_name=entity.name,
                    construct_type="entity",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # AA-03: Unused persona
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="AA-03",
        category="auth",
        subcategory="personas",
        title="Unused persona",
    )
    def unused_persona(self, appspec: AppSpec) -> list[Finding]:
        """Flag personas that are defined but never referenced as a story persona."""
        findings: list[Finding] = []
        if not appspec.personas:
            return findings
        story_personas = {s.persona for s in appspec.stories}
        for persona in appspec.personas:
            if persona.id not in story_personas:
                findings.append(
                    Finding(
                        agent=AgentId.AA,
                        heuristic_id="AA-03",
                        category="auth",
                        subcategory="personas",
                        severity=Severity.LOW,
                        confidence=Confidence.CONFIRMED,
                        title=f"Persona '{persona.id}' is never used as a story actor",
                        description=(
                            f"Persona '{persona.id}' ({persona.label}) is "
                            f"defined but no story references it as its actor. "
                            f"This may indicate a dead definition or missing "
                            f"story coverage for that role."
                        ),
                        evidence=[
                            Evidence(
                                evidence_type="ir_pattern",
                                location=f"persona:{persona.id}",
                                context=(
                                    f"Persona id '{persona.id}' not found in "
                                    f"story personas: {sorted(story_personas) or '(none)'}"
                                ),
                            ),
                        ],
                        remediation=Remediation(
                            summary=(
                                f"Write at least one story with "
                                f"actor: {persona.id}, or remove the persona."
                            ),
                            effort=RemediationEffort.SMALL,
                            guidance=(
                                "Every persona should be referenced by at "
                                "least one story to ensure its permissions "
                                "and workflows are exercised."
                            ),
                        ),
                        construct_type="persona",
                    ),
                )
        return findings

    # ------------------------------------------------------------------
    # AA-04: Empty personas on classified data
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="AA-04",
        category="auth",
        subcategory="data_governance",
        title="Empty personas on classified data",
    )
    def empty_personas_classified_data(self, appspec: AppSpec) -> list[Finding]:
        """Flag permission rules that don't restrict WHO on classified entities.

        #1354: ``permit: read: role(clinician) or role(admin)`` parses with
        ``personas == []`` — the role gate lives in ``rule.condition`` as an
        OR-tree of role_check nodes, and ``deny_all`` rules (#1281) are
        explicit denials. Both were previously reported as wide-open with
        CONFIRMED confidence (165 false positives on a fully role-scoped
        project). Mirrors the role-gate semantics the runtime and
        ``rbac/matrix.py`` have always applied.
        """
        findings: list[Finding] = []
        policies = appspec.policies
        if policies is None:
            return findings

        # Build a set of entity names that have at least one classification.
        classified_entities: set[str] = {c.entity for c in policies.classifications}

        for entity in appspec.domain.entities:
            if entity.name not in classified_entities:
                continue
            if entity.access is None:
                continue
            for rule in entity.access.permissions:
                if rule.personas != []:
                    continue
                if rule.deny_all:
                    continue  # explicit denial — nothing is open
                if _condition_contains_principal_check(rule.condition):
                    continue  # role()/grant() condition IS the persona restriction

                if rule.condition is not None:
                    # Row-condition only (e.g. `status = draft`): rows are
                    # filtered but WHO is unrestricted. Real signal, weaker
                    # claim than "any authenticated user sees everything".
                    confidence = Confidence.LIKELY
                    description = (
                        f"Entity '{entity.name}' contains classified data but "
                        f"its {rule.effect.value} {rule.operation.value} "
                        f"permission rule restricts only WHICH ROWS (a field "
                        f"condition), not WHO — any authenticated user "
                        f"satisfying the row condition can perform the "
                        f"operation on sensitive data."
                    )
                    snippet = (
                        f"rule: {rule.effect.value} {rule.operation.value}, "
                        f"personas=[], condition=<row filter, no role check>"
                    )
                else:
                    confidence = Confidence.CONFIRMED
                    description = (
                        f"Entity '{entity.name}' contains classified "
                        f"data but its {rule.effect.value} "
                        f"{rule.operation.value} permission rule does "
                        f"not restrict access to specific personas. "
                        f"This means any authenticated user can "
                        f"perform the operation on sensitive data."
                    )
                    snippet = f"rule: {rule.effect.value} {rule.operation.value}, personas=[]"

                findings.append(
                    Finding(
                        agent=AgentId.AA,
                        heuristic_id="AA-04",
                        category="auth",
                        subcategory="data_governance",
                        severity=Severity.MEDIUM,
                        confidence=confidence,
                        title=(
                            f"Entity '{entity.name}' has a "
                            f"{rule.effect.value} {rule.operation.value} "
                            f"rule with empty personas"
                        ),
                        description=description,
                        evidence=[
                            Evidence(
                                evidence_type="ir_pattern",
                                location=f"entity:{entity.name}",
                                snippet=snippet,
                                context=(
                                    f"Entity has classifications: "
                                    f"{[c.classification.value for c in policies.classifications if c.entity == entity.name]}"
                                ),
                            ),
                        ],
                        remediation=Remediation(
                            summary=(
                                f"Restrict the {rule.operation.value} "
                                f"permission on '{entity.name}' to "
                                f"specific personas."
                            ),
                            effort=RemediationEffort.SMALL,
                            guidance=(
                                "Classified data should have explicit "
                                "persona restrictions on every permission "
                                "rule to enforce least-privilege access."
                            ),
                            dsl_example=(
                                f"permit:\n"
                                f"  {rule.operation.value}: "
                                f"role(admin) or role(data_steward)"
                            ),
                        ),
                        entity_name=entity.name,
                        construct_type="entity",
                    ),
                )
        return findings

    # ------------------------------------------------------------------
    # AA-05: Non-admin DELETE without FORBID
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="AA-05",
        category="auth",
        subcategory="permissions",
        title="Non-admin DELETE without FORBID",
    )
    def non_admin_delete_without_forbid(self, appspec: AppSpec) -> list[Finding]:
        """Flag entities where non-admin personas have DELETE PERMIT but no FORBID guard."""
        findings: list[Finding] = []
        for entity in appspec.domain.entities:
            if entity.access is None:
                continue
            delete_permits: list[tuple[list[str], int]] = []
            has_delete_forbid = False
            for idx, rule in enumerate(entity.access.permissions):
                if rule.operation != PermissionKind.DELETE:
                    continue
                if rule.effect == PolicyEffect.FORBID:
                    has_delete_forbid = True
                    break
                if rule.effect == PolicyEffect.PERMIT:
                    delete_permits.append((rule.personas, idx))

            if has_delete_forbid:
                continue

            for personas, _idx in delete_permits:
                non_admin = [p for p in personas if p.lower() != "admin"]
                if not non_admin:
                    continue
                findings.append(
                    Finding(
                        agent=AgentId.AA,
                        heuristic_id="AA-05",
                        category="auth",
                        subcategory="permissions",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.LIKELY,
                        title=(
                            f"Entity '{entity.name}' permits DELETE for "
                            f"non-admin personas without a FORBID guard"
                        ),
                        description=(
                            f"Entity '{entity.name}' grants DELETE to "
                            f"non-admin personas {non_admin} but defines no "
                            f"FORBID rule for DELETE. Without a FORBID guard, "
                            f"accidental or malicious deletion is harder to "
                            f"prevent — consider adding a FORBID rule for "
                            f"specific conditions."
                        ),
                        evidence=[
                            Evidence(
                                evidence_type="ir_pattern",
                                location=f"entity:{entity.name}",
                                snippet=(f"permit delete personas={personas}"),
                                context="No forbid delete rule found",
                            ),
                        ],
                        remediation=Remediation(
                            summary=(
                                f"Add a FORBID DELETE rule on "
                                f"'{entity.name}' to guard against "
                                f"unintended deletion."
                            ),
                            effort=RemediationEffort.SMALL,
                            guidance=(
                                "Cedar-style FORBID rules override PERMIT "
                                "rules. Add a condition-based FORBID to "
                                "protect critical records from deletion."
                            ),
                            dsl_example=(
                                "access:\n  permissions:\n    forbid delete: status = 'archived'"
                            ),
                        ),
                        entity_name=entity.name,
                        construct_type="entity",
                    ),
                )
        return findings

    # ------------------------------------------------------------------
    # AA-06: Weak security with sensitive data
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="AA-06",
        category="auth",
        subcategory="security_profile",
        title="Weak security with sensitive data",
    )
    def weak_security_sensitive_data(self, appspec: AppSpec) -> list[Finding]:
        """Flag BASIC security profile when entities have PII or financial classifications."""
        findings: list[Finding] = []
        if appspec.security is None:
            return findings
        if appspec.security.profile != SecurityProfile.BASIC:
            return findings
        if appspec.policies is None:
            return findings

        sensitive = [
            c
            for c in appspec.policies.classifications
            if c.classification.value in _SENSITIVE_CLASSIFICATIONS
        ]
        if not sensitive:
            return findings

        classification_labels = sorted({c.classification.value for c in sensitive})
        affected_entities = sorted({c.entity for c in sensitive})

        findings.append(
            Finding(
                agent=AgentId.AA,
                heuristic_id="AA-06",
                category="auth",
                subcategory="security_profile",
                severity=Severity.HIGH,
                confidence=Confidence.CONFIRMED,
                title="BASIC security profile with sensitive data classifications",
                description=(
                    f"The application uses security profile 'basic' but "
                    f"entities {affected_entities} have sensitive "
                    f"classifications: {classification_labels}. A basic "
                    f"profile disables HSTS, CSP, and default auth — this "
                    f"is insufficient for data that includes PII or "
                    f"financial information."
                ),
                evidence=[
                    Evidence(
                        evidence_type="config_value",
                        location="security",
                        snippet=f"profile: {appspec.security.profile.value}",
                        context=(f"Sensitive classifications present: {classification_labels}"),
                    ),
                ],
                remediation=Remediation(
                    summary="Upgrade the security profile to 'standard' or 'strict'.",
                    effort=RemediationEffort.MEDIUM,
                    guidance=(
                        "Applications handling PII or financial data should "
                        "use at least 'standard' (session auth, HSTS) or "
                        "'strict' (CSP, tenant isolation) security profiles."
                    ),
                    dsl_example=('app my_app "My App":\n  security_profile: strict'),
                ),
                construct_type="security",
            ),
        )
        return findings

    # ------------------------------------------------------------------
    # AA-07: Surface/entity persona mismatch
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="AA-07",
        category="auth",
        subcategory="personas",
        title="Surface/entity persona mismatch",
    )
    def surface_entity_persona_mismatch(self, appspec: AppSpec) -> list[Finding]:
        """Flag surfaces whose allow_personas set doesn't match entity permission personas."""
        findings: list[Finding] = []
        for surface in appspec.surfaces:
            if surface.access is None:
                continue
            if not surface.access.allow_personas:
                continue
            if surface.entity_ref is None:
                continue
            entity = appspec.get_entity(surface.entity_ref)
            if entity is None or entity.access is None:
                continue

            surface_personas = set(surface.access.allow_personas)
            entity_personas: set[str] = set()
            for rule in entity.access.permissions:
                entity_personas.update(rule.personas)

            # If the entity has no persona restrictions at all, skip — the
            # entity is open to any authenticated user so no conflict.
            if not entity_personas:
                continue

            # Personas allowed on the surface but absent from every entity
            # permission rule.
            surface_only = surface_personas - entity_personas
            if not surface_only:
                continue

            findings.append(
                Finding(
                    agent=AgentId.AA,
                    heuristic_id="AA-07",
                    category="auth",
                    subcategory="personas",
                    severity=Severity.LOW,
                    confidence=Confidence.LIKELY,
                    title=(
                        f"Surface '{surface.name}' allows personas not "
                        f"present in entity '{surface.entity_ref}' permissions"
                    ),
                    description=(
                        f"Surface '{surface.name}' grants access to personas "
                        f"{sorted(surface_only)} but entity "
                        f"'{surface.entity_ref}' does not include those "
                        f"personas in any permission rule. These personas "
                        f"may reach the surface but be denied at the data "
                        f"layer, leading to confusing errors."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="ir_pattern",
                            location=f"surface:{surface.name}",
                            snippet=(f"surface allow_personas={sorted(surface_personas)}"),
                            context=(f"entity permission personas={sorted(entity_personas)}"),
                        ),
                    ],
                    remediation=Remediation(
                        summary=(
                            f"Align surface and entity persona lists for "
                            f"'{surface.name}' / '{surface.entity_ref}'."
                        ),
                        effort=RemediationEffort.SMALL,
                        guidance=(
                            "Ensure every persona allowed on a surface also "
                            "has at least one permission rule on the backing "
                            "entity, or remove the persona from the surface "
                            "allow list."
                        ),
                    ),
                    surface_name=surface.name,
                    entity_name=surface.entity_ref,
                    construct_type="surface",
                ),
            )
        return findings

    # ------------------------------------------------------------------
    # AA-08: Webhook without auth
    # ------------------------------------------------------------------
    @heuristic(
        heuristic_id="AA-08",
        category="auth",
        subcategory="webhooks",
        title="Webhook without auth",
    )
    def webhook_without_auth(self, appspec: AppSpec) -> list[Finding]:
        """Flag webhooks that have no authentication configured."""
        findings: list[Finding] = []
        for webhook in appspec.webhooks:
            if webhook.auth is not None:
                continue
            findings.append(
                Finding(
                    agent=AgentId.AA,
                    heuristic_id="AA-08",
                    category="auth",
                    subcategory="webhooks",
                    severity=Severity.HIGH,
                    confidence=Confidence.CONFIRMED,
                    title=f"Webhook '{webhook.name}' has no authentication",
                    description=(
                        f"Webhook '{webhook.name}' does not define an auth "
                        f"block. Without authentication (e.g. HMAC signing) "
                        f"the receiving endpoint cannot verify that payloads "
                        f"originate from this application, exposing it to "
                        f"spoofed requests."
                    ),
                    evidence=[
                        Evidence(
                            evidence_type="missing_construct",
                            location=f"webhook:{webhook.name}",
                            context="webhook.auth is None",
                        ),
                    ],
                    remediation=Remediation(
                        summary=(f"Add an auth block to webhook '{webhook.name}'."),
                        effort=RemediationEffort.SMALL,
                        guidance=(
                            "Configure HMAC-SHA256 signing or bearer token "
                            "authentication so the receiver can verify "
                            "payload authenticity."
                        ),
                        dsl_example=(
                            f"webhook {webhook.name} "
                            f'"{webhook.title or webhook.name}":\n'
                            f"  entity: {webhook.entity}\n"
                            f'  url: config("WEBHOOK_URL")\n'
                            f"  auth:\n"
                            f"    method: hmac_sha256\n"
                            f'    secret: config("WEBHOOK_SECRET")'
                        ),
                    ),
                    construct_type="webhook",
                ),
            )
        return findings
