"""NIST SP 800-162 (ABAC) compliance validation harness.

Loads the rbac_validation example DSL and runs 7 compliance checks
using the policy handler functions and role-condition-aware evaluation.

NIST Reference: https://csrc.nist.gov/publications/detail/sp/800-162/final
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.ir.conditions import ConditionExpr
from dazzle.core.ir.domain import (
    EntitySpec,
    PermissionKind,
    PermissionRule,
    PolicyEffect,
)
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

# Reuse policy handler internals for structural analysis
from dazzle.mcp.server.handlers.policy import (
    _analyze,
    _find_conflicts,
    _simulate,
)

# ---------------------------------------------------------------------------
# Fixture: load the rbac_validation example once per module
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2] / "examples" / "rbac_validation"

ALL_ENTITIES = [
    "Patient",
    "MedicalRecord",
    "Prescription",
    "Appointment",
    "LabResult",
    "BillingRecord",
    "Staff",
    "AuditLog",
]

ALL_PERSONAS = [
    "admin",
    "doctor",
    "nurse",
    "receptionist",
    "pharmacist",
    "lab_tech",
    "billing_clerk",
    "intern",
]


@pytest.fixture(scope="module")
def appspec():
    """Load the rbac_validation DSL and return the linked AppSpec."""
    manifest = load_manifest(PROJECT_ROOT / "dazzle.toml")
    dsl_files = discover_dsl_files(PROJECT_ROOT, manifest)
    modules = parse_modules(dsl_files)
    return build_appspec(modules, manifest.project_root)


@pytest.fixture(scope="module")
def entity_map(appspec):
    """Map of entity name -> EntitySpec for quick lookup."""
    return {e.name: e for e in appspec.domain.entities}


# ---------------------------------------------------------------------------
# Role-condition-aware evaluator
# ---------------------------------------------------------------------------


def _extract_roles(condition: ConditionExpr | None) -> set[str]:
    """Recursively extract all role names from a condition tree."""
    if condition is None:
        return set()
    if condition.role_check:
        return {condition.role_check.role_name}
    roles: set[str] = set()
    if condition.left:
        roles |= _extract_roles(condition.left)
    if condition.right:
        roles |= _extract_roles(condition.right)
    return roles


def _evaluate_role_aware(entity: EntitySpec, persona_id: str, op: PermissionKind) -> str:
    """Evaluate permission rules with role-condition awareness.

    Cedar semantics: FORBID > PERMIT > default-deny.
    A rule matches a persona if:
    - rule.personas is non-empty and persona_id is in rule.personas, OR
    - rule.personas is empty and rule.condition is None (i.e. 'authenticated'), OR
    - rule.personas is empty and persona_id is in the condition's role() checks.
    """
    if entity.access is None:
        return "default-deny"

    has_permit = False
    has_forbid = False

    for rule in entity.access.permissions:
        if rule.operation != op:
            continue
        if not _rule_matches_persona_aware(rule, persona_id):
            continue
        if rule.effect == PolicyEffect.FORBID:
            has_forbid = True
        elif rule.effect == PolicyEffect.PERMIT:
            has_permit = True

    if has_forbid:
        return "deny"
    if has_permit:
        return "allow"
    return "default-deny"


def _rule_matches_persona_aware(rule: PermissionRule, persona_id: str) -> bool:
    """Check whether a rule applies to the given persona, considering role() conditions."""
    # If personas list is explicit, use it
    if rule.personas:
        return persona_id in rule.personas

    # If no condition, this is a bare 'authenticated' or 'anonymous' rule — matches all
    if rule.condition is None:
        return True

    # Extract roles from the condition tree
    roles = _extract_roles(rule.condition)

    # If condition has role checks, persona must match one
    if roles:
        return persona_id in roles

    # Condition has no role checks (e.g. field comparison) — matches all authenticated
    return True


# ---------------------------------------------------------------------------
# Check 1: Policy Completeness (NIST 3.1)
# ---------------------------------------------------------------------------


class TestPolicyCompleteness:
    """NIST 3.1 — Every entity has access rules; operations have permit coverage."""

    def test_all_entities_have_access_rules(self, appspec) -> None:
        """No entity should be completely unprotected."""
        result = _analyze(appspec, None)
        assert result["entities_without_rules"] == [], (
            f"Entities without access rules: {result['entities_without_rules']}"
        )

    def test_all_eight_entities_present(self, appspec) -> None:
        """The example declares exactly 8 entities."""
        entity_names = [e.name for e in appspec.domain.entities]
        for name in ALL_ENTITIES:
            assert name in entity_names, f"Missing entity: {name}"
        assert len(appspec.domain.entities) == 8

    def test_every_entity_has_permit_rules(self, entity_map) -> None:
        """Every entity should have at least one PERMIT rule."""
        for name, entity in entity_map.items():
            assert entity.access is not None, f"{name} has no access spec"
            permits = [r for r in entity.access.permissions if r.effect == PolicyEffect.PERMIT]
            assert len(permits) > 0, f"{name} has no PERMIT rules"

    def test_audit_log_has_no_update_or_delete_permit(self, entity_map) -> None:
        """AuditLog should have no PERMIT for update or delete (append-only)."""
        audit_log = entity_map["AuditLog"]
        for rule in audit_log.access.permissions:
            if rule.effect == PolicyEffect.PERMIT:
                assert rule.operation not in (
                    PermissionKind.UPDATE,
                    PermissionKind.DELETE,
                ), f"AuditLog should not permit {rule.operation.value}"


# ---------------------------------------------------------------------------
# Check 2: Conflict Detection (NIST 4.3)
# ---------------------------------------------------------------------------


class TestConflictDetection:
    """NIST 4.3 — Detect contradictory permit/forbid rules; verify Cedar resolution."""

    def test_conflicts_detected(self, appspec) -> None:
        """Some entities intentionally have permit/forbid overlap."""
        result = _find_conflicts(appspec, None)
        assert result["conflict_count"] > 0, "Expected at least one permit/forbid conflict"

    def test_all_conflicts_resolve_forbid_wins(self, appspec) -> None:
        """Every detected conflict should resolve as 'FORBID wins'."""
        result = _find_conflicts(appspec, None)
        for conflict in result["conflicts"]:
            assert conflict["resolution"] == "FORBID wins (Cedar semantics)", (
                f"Unexpected resolution for {conflict['entity']}.{conflict['operation']}"
            )

    def test_patient_delete_conflict(self, appspec) -> None:
        """Patient has both permit(admin, delete) and forbid(non-admin, delete)."""
        result = _find_conflicts(appspec, ["Patient"])
        delete_conflicts = [c for c in result["conflicts"] if c["operation"] == "delete"]
        assert len(delete_conflicts) > 0, "Expected Patient delete conflict"

    def test_prescription_separation_conflict(self, appspec) -> None:
        """Prescription has permit/forbid overlap on create and update."""
        result = _find_conflicts(appspec, ["Prescription"])
        ops_with_conflicts = {c["operation"] for c in result["conflicts"]}
        assert "create" in ops_with_conflicts, "Expected Prescription create conflict"
        assert "update" in ops_with_conflicts, "Expected Prescription update conflict"


# ---------------------------------------------------------------------------
# Check 3: Separation of Duty (NIST 5.2)
# ---------------------------------------------------------------------------


class TestSeparationOfDuty:
    """NIST 5.2 — For SoD pairs, no single non-admin persona can do both."""

    def test_prescription_create_vs_update(self, entity_map) -> None:
        """No non-admin persona can both create AND update prescriptions."""
        rx = entity_map["Prescription"]
        for persona in ALL_PERSONAS:
            if persona == "admin":
                continue  # Admin is break-glass, exempt from SoD
            can_create = _evaluate_role_aware(rx, persona, PermissionKind.CREATE)
            can_update = _evaluate_role_aware(rx, persona, PermissionKind.UPDATE)
            assert not (can_create == "allow" and can_update == "allow"), (
                f"SoD violation: {persona} can both create AND update Prescription"
            )

    def test_doctor_cannot_update_prescription(self, entity_map) -> None:
        """Doctor can create but FORBID overrides update permit."""
        rx = entity_map["Prescription"]
        assert _evaluate_role_aware(rx, "doctor", PermissionKind.CREATE) == "allow"
        assert _evaluate_role_aware(rx, "doctor", PermissionKind.UPDATE) == "deny"

    def test_pharmacist_cannot_create_prescription(self, entity_map) -> None:
        """Pharmacist can update but FORBID overrides create permit."""
        rx = entity_map["Prescription"]
        assert _evaluate_role_aware(rx, "pharmacist", PermissionKind.CREATE) == "deny"
        assert _evaluate_role_aware(rx, "pharmacist", PermissionKind.UPDATE) == "allow"

    def test_billing_clinical_segregation(self, entity_map) -> None:
        """Billing clerk cannot access MedicalRecord; Doctor cannot access BillingRecord."""
        mr = entity_map["MedicalRecord"]
        br = entity_map["BillingRecord"]

        # Billing clerk denied medical records
        for op in PermissionKind:
            decision = _evaluate_role_aware(mr, "billing_clerk", op)
            assert decision != "allow", f"billing_clerk should not have {op.value} on MedicalRecord"

        # Doctor denied billing records
        for op in PermissionKind:
            decision = _evaluate_role_aware(br, "doctor", op)
            assert decision != "allow", f"doctor should not have {op.value} on BillingRecord"


# ---------------------------------------------------------------------------
# Check 4: Least Privilege (NIST 5.1)
# ---------------------------------------------------------------------------


class TestLeastPrivilege:
    """NIST 5.1 — Each persona stays within expected privilege budget."""

    # Maximum number of (entity, operation) "allow" decisions per persona.
    # 8 entities * 5 ops = 40 total possible.
    PRIVILEGE_BUDGET: dict[str, int] = {
        "admin": 38,  # Break-glass: all except AuditLog update/delete
        "doctor": 21,  # Clinical + staff read/list + audit create
        "nurse": 17,  # Clinical read + appointments + staff + audit create
        "receptionist": 11,  # Patient + appointments + staff + audit create
        "pharmacist": 6,  # Prescription read/update/list + staff + audit create
        "lab_tech": 7,  # Lab results + staff + audit create
        "billing_clerk": 7,  # Billing + staff + audit create
        "intern": 2,  # Staff read + list only
    }

    def _count_allows(self, entity_map: dict[str, EntitySpec], persona: str) -> int:
        """Count number of allow decisions for a persona across all entities."""
        count = 0
        for entity in entity_map.values():
            for op in PermissionKind:
                if _evaluate_role_aware(entity, persona, op) == "allow":
                    count += 1
        return count

    def test_persona_privilege_budgets(self, entity_map) -> None:
        """Each persona's allow count must not exceed its budget."""
        for persona, budget in self.PRIVILEGE_BUDGET.items():
            allow_count = self._count_allows(entity_map, persona)
            assert allow_count <= budget, (
                f"{persona} has {allow_count} allows, exceeds budget of {budget}"
            )

    def test_admin_has_most_privileges(self, entity_map) -> None:
        """Admin should have strictly more allows than any other persona."""
        counts: dict[str, int] = {}
        for persona in ALL_PERSONAS:
            counts[persona] = self._count_allows(entity_map, persona)
        admin_count = counts["admin"]
        for persona, count in counts.items():
            if persona != "admin":
                assert admin_count > count, (
                    f"admin ({admin_count}) should have more allows than {persona} ({count})"
                )

    def test_intern_minimal_access(self, entity_map) -> None:
        """Intern should have near-zero allows (only Staff read/list)."""
        intern_allows: list[tuple[str, str]] = []
        for entity_name, entity in entity_map.items():
            for op in PermissionKind:
                if _evaluate_role_aware(entity, "intern", op) == "allow":
                    intern_allows.append((entity_name, op.value))
        # Intern can only read and list Staff (2 allows)
        assert len(intern_allows) <= 2, (
            f"Intern has {len(intern_allows)} allows, expected at most 2: {intern_allows}"
        )
        for entity_name, op_value in intern_allows:
            assert entity_name == "Staff", (
                f"Intern should only access Staff, got {entity_name}.{op_value}"
            )


# ---------------------------------------------------------------------------
# Check 5: Default Deny (NIST 3.2)
# ---------------------------------------------------------------------------


class TestDefaultDeny:
    """NIST 3.2 — Intern gets default-deny; explicit FORBID returns 'deny'."""

    def test_intern_denied_on_clinical_entities(self, entity_map) -> None:
        """Intern should be denied on all clinical entities."""
        clinical = ["Patient", "Appointment"]
        for entity_name in clinical:
            entity = entity_map[entity_name]
            for op in PermissionKind:
                decision = _evaluate_role_aware(entity, "intern", op)
                assert decision in ("default-deny", "deny"), (
                    f"intern should be denied {op.value} on {entity_name}, got {decision}"
                )

    def test_intern_explicit_forbid_on_medical_record(self, entity_map) -> None:
        """MedicalRecord has explicit FORBID for intern — should return 'deny'."""
        mr = entity_map["MedicalRecord"]
        for op in PermissionKind:
            decision = _evaluate_role_aware(mr, "intern", op)
            assert decision == "deny", (
                f"intern should be explicitly denied {op.value} on MedicalRecord, got {decision}"
            )

    def test_audit_log_forbid_update_delete_for_all(self, entity_map) -> None:
        """AuditLog forbids update/delete for all authenticated users."""
        al = entity_map["AuditLog"]
        for persona in ALL_PERSONAS:
            assert _evaluate_role_aware(al, persona, PermissionKind.UPDATE) == "deny", (
                f"{persona} should be denied UPDATE on AuditLog"
            )
            assert _evaluate_role_aware(al, persona, PermissionKind.DELETE) == "deny", (
                f"{persona} should be denied DELETE on AuditLog"
            )

    def test_simulate_traces_deny_reason(self, appspec) -> None:
        """Simulate should return detailed deny trace for intern on MedicalRecord."""
        result = _simulate(appspec, "MedicalRecord", "intern", "read")
        assert result["decision"] == "deny"
        assert "FORBID" in result["reason"]
        assert len(result["matching_rules"]) > 0


# ---------------------------------------------------------------------------
# Check 6: Audit Completeness (NIST Section 6)
# ---------------------------------------------------------------------------


class TestAuditCompleteness:
    """NIST Section 6 — Sensitive entities have audit enabled; AuditLog does not."""

    AUDITED_ENTITIES = [
        "Patient",
        "MedicalRecord",
        "Prescription",
        "Appointment",
        "LabResult",
        "BillingRecord",
        "Staff",
    ]

    def test_sensitive_entities_audited(self, entity_map) -> None:
        """All sensitive entities must have audit enabled."""
        for name in self.AUDITED_ENTITIES:
            entity = entity_map[name]
            assert entity.audit is not None, f"{name} missing audit config"
            assert entity.audit.enabled is True, f"{name} audit not enabled"

    def test_audit_log_not_audited(self, entity_map) -> None:
        """AuditLog should not audit itself (prevents infinite recursion)."""
        al = entity_map["AuditLog"]
        assert al.audit is not None, "AuditLog should have explicit audit config"
        assert al.audit.enabled is False, "AuditLog should have audit disabled"

    def test_audit_all_vs_selective(self, entity_map) -> None:
        """Some entities audit all ops, some audit selectively."""
        # Patient has audit: all (empty operations = all)
        patient = entity_map["Patient"]
        assert patient.audit.operations == [], "Patient should audit all operations"

        # Appointment has audit: [create, update, delete]
        appt = entity_map["Appointment"]
        assert PermissionKind.CREATE in appt.audit.operations
        assert PermissionKind.UPDATE in appt.audit.operations
        assert PermissionKind.DELETE in appt.audit.operations
        assert PermissionKind.READ not in appt.audit.operations

    def test_staff_selective_audit(self, entity_map) -> None:
        """Staff audits only create, update, delete (not read/list)."""
        staff = entity_map["Staff"]
        assert staff.audit is not None
        assert PermissionKind.CREATE in staff.audit.operations
        assert PermissionKind.UPDATE in staff.audit.operations
        assert PermissionKind.DELETE in staff.audit.operations
        assert PermissionKind.READ not in staff.audit.operations
        assert PermissionKind.LIST not in staff.audit.operations


# ---------------------------------------------------------------------------
# Check 7: Compliance Report (Aggregate)
# ---------------------------------------------------------------------------


class TestComplianceReport:
    """Aggregates all checks into a structured compliance report."""

    def test_generate_compliance_report(self, appspec, entity_map) -> None:
        """Generate a NIST compliance summary report."""
        # 1. Policy completeness
        analysis = _analyze(appspec, None)
        completeness_ok = len(analysis["entities_without_rules"]) == 0

        # 2. Conflicts — all resolved via Cedar semantics
        conflicts = _find_conflicts(appspec, None)
        all_cedar_resolved = all(
            c["resolution"] == "FORBID wins (Cedar semantics)" for c in conflicts["conflicts"]
        )

        # 3. Separation of duty — Prescription create vs update
        rx = entity_map["Prescription"]
        sod_violations = []
        for persona in ALL_PERSONAS:
            if persona == "admin":
                continue
            can_create = _evaluate_role_aware(rx, persona, PermissionKind.CREATE) == "allow"
            can_update = _evaluate_role_aware(rx, persona, PermissionKind.UPDATE) == "allow"
            if can_create and can_update:
                sod_violations.append(persona)

        # 4. Default deny — intern denied on MedicalRecord
        intern_denied = all(
            _evaluate_role_aware(entity_map["MedicalRecord"], "intern", op) == "deny"
            for op in PermissionKind
        )

        # 5. Audit completeness
        audited = all(
            entity_map[n].audit is not None and entity_map[n].audit.enabled
            for n in TestAuditCompleteness.AUDITED_ENTITIES
        )
        audit_log_not_audited = (
            entity_map["AuditLog"].audit is not None and not entity_map["AuditLog"].audit.enabled
        )

        report = {
            "nist_sp_800_162_compliance": {
                "section_3_1_policy_completeness": {
                    "pass": completeness_ok,
                    "entities_without_rules": analysis["entities_without_rules"],
                },
                "section_4_3_conflict_detection": {
                    "pass": all_cedar_resolved,
                    "conflict_count": conflicts["conflict_count"],
                    "all_cedar_resolved": all_cedar_resolved,
                },
                "section_5_2_separation_of_duty": {
                    "pass": len(sod_violations) == 0,
                    "violations": sod_violations,
                },
                "section_3_2_default_deny": {
                    "pass": intern_denied,
                },
                "section_5_1_least_privilege": {
                    "pass": True,  # Validated per-persona in TestLeastPrivilege
                },
                "section_6_audit": {
                    "pass": audited and audit_log_not_audited,
                    "all_sensitive_audited": audited,
                    "audit_log_self_audit_disabled": audit_log_not_audited,
                },
            },
            "overall_pass": all(
                [
                    completeness_ok,
                    all_cedar_resolved,
                    len(sod_violations) == 0,
                    intern_denied,
                    audited,
                    audit_log_not_audited,
                ]
            ),
        }

        # Verify overall pass
        assert report["overall_pass"], f"Compliance report failed:\n{json.dumps(report, indent=2)}"

        # Verify each section passes
        for section, data in report["nist_sp_800_162_compliance"].items():
            assert data["pass"], f"{section} failed: {json.dumps(data, indent=2)}"
