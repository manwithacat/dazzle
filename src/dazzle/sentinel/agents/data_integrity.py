"""Data Integrity detection agent (DI-01 through DI-08)."""

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

from dazzle.core.ir.fields import FieldTypeKind
from dazzle.core.ir.governance import DataClassification

# Field names that conventionally warrant a UNIQUE constraint.
_UNIQUE_WORTHY_NAMES: frozenset[str] = frozenset(
    {"email", "code", "slug", "username", "phone", "ssn", "tax_id"}
)

# DataClassification values considered PII or financial.
_SENSITIVE_CLASSIFICATIONS: frozenset[DataClassification] = frozenset(
    {
        DataClassification.PII_DIRECT,
        DataClassification.PII_INDIRECT,
        DataClassification.PII_SENSITIVE,
        DataClassification.FINANCIAL_TXN,
        DataClassification.FINANCIAL_ACCOUNT,
    }
)

# FieldTypeKind values that are numeric (for ledger sync target checks).
_NUMERIC_KINDS: frozenset[FieldTypeKind] = frozenset(
    {FieldTypeKind.INT, FieldTypeKind.DECIMAL, FieldTypeKind.MONEY}
)


class DataIntegrityAgent(DetectionAgent):
    """Detects data-integrity risks in the domain model."""

    @property
    def agent_id(self) -> AgentId:
        return AgentId.DI

    # ------------------------------------------------------------------
    # DI-01  Cascade delete missing
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="DI-01",
        category="data_integrity",
        subcategory="cascade_delete",
        title="Cascade delete missing on relationship",
    )
    def check_cascade_delete_missing(self, appspec: AppSpec) -> list[Finding]:
        """Flag has_many / has_one fields without explicit relationship_behavior."""
        findings: list[Finding] = []
        relationship_kinds = {FieldTypeKind.HAS_MANY, FieldTypeKind.HAS_ONE}

        for entity in appspec.domain.entities:
            for field in entity.fields:
                if (
                    field.type.kind in relationship_kinds
                    and field.type.relationship_behavior is None
                ):
                    findings.append(
                        Finding(
                            agent=AgentId.DI,
                            heuristic_id="DI-01",
                            category="data_integrity",
                            subcategory="cascade_delete",
                            severity=Severity.HIGH,
                            confidence=Confidence.CONFIRMED,
                            title=f"No cascade behavior on {entity.name}.{field.name}",
                            description=(
                                f"Relationship field '{field.name}' on entity "
                                f"'{entity.name}' ({field.type.kind.value} "
                                f"{field.type.ref_entity}) does not specify a "
                                f"relationship_behavior (cascade, restrict, or nullify). "
                                f"Deleting a parent record may leave orphaned children."
                            ),
                            entity_name=entity.name,
                            evidence=[
                                Evidence(
                                    evidence_type="ir_pattern",
                                    location=f"entity.{entity.name}.{field.name}",
                                    context=(
                                        f"kind={field.type.kind.value}, "
                                        f"ref_entity={field.type.ref_entity}, "
                                        f"relationship_behavior=None"
                                    ),
                                )
                            ],
                            remediation=Remediation(
                                summary=(
                                    "Add an explicit delete behavior to the relationship "
                                    "field: cascade, restrict, or nullify."
                                ),
                                effort=RemediationEffort.SMALL,
                                dsl_example=(
                                    f"  {field.name}: {field.type.kind.value} "
                                    f"{field.type.ref_entity} cascade"
                                ),
                            ),
                        )
                    )

        return findings

    # ------------------------------------------------------------------
    # DI-02  Orphaned ref (target entity not found)
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="DI-02",
        category="data_integrity",
        subcategory="orphaned_ref",
        title="Ref field references unknown entity",
    )
    def check_orphaned_ref(self, appspec: AppSpec) -> list[Finding]:
        """Flag ref fields whose target entity cannot be resolved in the AppSpec."""
        findings: list[Finding] = []
        known_entities = {e.name for e in appspec.domain.entities}

        for entity in appspec.domain.entities:
            for field in entity.fields:
                if (
                    field.type.kind == FieldTypeKind.REF
                    and field.type.ref_entity
                    and field.type.ref_entity not in known_entities
                ):
                    findings.append(
                        Finding(
                            agent=AgentId.DI,
                            heuristic_id="DI-02",
                            category="data_integrity",
                            subcategory="orphaned_ref",
                            severity=Severity.MEDIUM,
                            confidence=Confidence.CONFIRMED,
                            title=(
                                f"Orphaned ref: {entity.name}.{field.name} -> "
                                f"{field.type.ref_entity}"
                            ),
                            description=(
                                f"Field '{field.name}' on entity '{entity.name}' "
                                f"references entity '{field.type.ref_entity}' which "
                                f"does not exist in the domain model. This will cause "
                                f"foreign-key failures at runtime."
                            ),
                            entity_name=entity.name,
                            evidence=[
                                Evidence(
                                    evidence_type="ir_pattern",
                                    location=f"entity.{entity.name}.{field.name}",
                                    context=(
                                        f"ref_entity={field.type.ref_entity}, "
                                        f"known_entities={sorted(known_entities)}"
                                    ),
                                )
                            ],
                            remediation=Remediation(
                                summary=(
                                    f"Define the missing entity '{field.type.ref_entity}' "
                                    f"or correct the ref target name."
                                ),
                                effort=RemediationEffort.MEDIUM,
                                dsl_example=(
                                    f"entity {field.type.ref_entity} "
                                    f'"{field.type.ref_entity}":\n'
                                    f"  id: uuid pk\n"
                                    f"  name: str(200) required"
                                ),
                            ),
                        )
                    )

        return findings

    # ------------------------------------------------------------------
    # DI-03  Entity without primary key
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="DI-03",
        category="data_integrity",
        subcategory="missing_pk",
        title="Entity without primary key",
    )
    def check_missing_primary_key(self, appspec: AppSpec) -> list[Finding]:
        """Flag entities that have no field marked with the PK modifier."""
        findings: list[Finding] = []

        for entity in appspec.domain.entities:
            if entity.primary_key is None:
                findings.append(
                    Finding(
                        agent=AgentId.DI,
                        heuristic_id="DI-03",
                        category="data_integrity",
                        subcategory="missing_pk",
                        severity=Severity.CRITICAL,
                        confidence=Confidence.CONFIRMED,
                        title=f"Entity '{entity.name}' has no primary key",
                        description=(
                            f"Entity '{entity.name}' does not declare any field "
                            f"with the 'pk' modifier. Without a primary key the "
                            f"entity cannot be uniquely identified, which breaks "
                            f"lookups, relationships, and data integrity."
                        ),
                        entity_name=entity.name,
                        evidence=[
                            Evidence(
                                evidence_type="missing_construct",
                                location=f"entity.{entity.name}",
                                context=(
                                    f"fields={[f.name for f in entity.fields]}, "
                                    f"none have FieldModifier.PK"
                                ),
                            )
                        ],
                        remediation=Remediation(
                            summary="Add a primary key field to the entity.",
                            effort=RemediationEffort.SMALL,
                            dsl_example="  id: uuid pk",
                        ),
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # DI-04  Unique-worthy field without UNIQUE
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="DI-04",
        category="data_integrity",
        subcategory="missing_unique",
        title="Unique-worthy field without UNIQUE constraint",
    )
    def check_missing_unique_constraint(self, appspec: AppSpec) -> list[Finding]:
        """Flag fields whose name suggests uniqueness but lack a UNIQUE modifier."""
        findings: list[Finding] = []

        for entity in appspec.domain.entities:
            for field in entity.fields:
                if (
                    field.name in _UNIQUE_WORTHY_NAMES
                    and not field.is_unique
                    and not field.is_primary_key
                ):
                    findings.append(
                        Finding(
                            agent=AgentId.DI,
                            heuristic_id="DI-04",
                            category="data_integrity",
                            subcategory="missing_unique",
                            severity=Severity.MEDIUM,
                            confidence=Confidence.LIKELY,
                            title=(
                                f"Field '{entity.name}.{field.name}' likely needs "
                                f"a UNIQUE constraint"
                            ),
                            description=(
                                f"Field '{field.name}' on entity '{entity.name}' "
                                f"is conventionally unique (e.g. email, slug, "
                                f"username) but does not carry a 'unique' or "
                                f"'unique?' modifier. Duplicate values may slip "
                                f"in and cause business-logic errors."
                            ),
                            entity_name=entity.name,
                            evidence=[
                                Evidence(
                                    evidence_type="ir_pattern",
                                    location=f"entity.{entity.name}.{field.name}",
                                    context=(f"modifiers={[m.value for m in field.modifiers]}"),
                                )
                            ],
                            remediation=Remediation(
                                summary=(
                                    f"Add 'unique' (or 'unique?' if nullable) to "
                                    f"the '{field.name}' field."
                                ),
                                effort=RemediationEffort.TRIVIAL,
                                dsl_example=(f"  {field.name}: {field.type.kind.value} unique"),
                            ),
                        )
                    )

        return findings

    # ------------------------------------------------------------------
    # DI-05  Dead-end state-machine states
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="DI-05",
        category="data_integrity",
        subcategory="dead_end_state",
        title="Dead-end state in state machine",
    )
    def check_dead_end_states(self, appspec: AppSpec) -> list[Finding]:
        """Flag states that are transition targets but have no outbound transitions.

        A state that is reachable (appears as ``to_state``) but has no outbound
        transition and is not the final state in the declared list is likely a
        dead-end.  Terminal states (the last declared state, or states that are
        never a ``to_state``) are excluded because they are intentionally final.
        """
        findings: list[Finding] = []

        for entity in appspec.domain.entities:
            sm = entity.state_machine
            if sm is None or not sm.states or not sm.transitions:
                continue

            # States used as a from_state (excluding wildcard "*").
            from_states: set[str] = set()
            # States used as a to_state.
            to_states: set[str] = set()

            for t in sm.transitions:
                if t.from_state != "*":
                    from_states.add(t.from_state)
                to_states.add(t.to_state)

            # The last declared state is typically the terminal state.
            terminal_state = sm.states[-1] if sm.states else None

            for state in sm.states:
                # Dead-end: reachable (is a to_state) but no outgoing
                # transitions, and not the conventional terminal state.
                if state in to_states and state not in from_states and state != terminal_state:
                    findings.append(
                        Finding(
                            agent=AgentId.DI,
                            heuristic_id="DI-05",
                            category="data_integrity",
                            subcategory="dead_end_state",
                            severity=Severity.LOW,
                            confidence=Confidence.POSSIBLE,
                            title=(f"Potential dead-end state '{state}' in {entity.name}"),
                            description=(
                                f"State '{state}' in entity '{entity.name}' is "
                                f"the target of a transition but has no outbound "
                                f"transitions defined. If this is not intentionally "
                                f"terminal, records may become stuck."
                            ),
                            entity_name=entity.name,
                            evidence=[
                                Evidence(
                                    evidence_type="ir_pattern",
                                    location=(f"entity.{entity.name}.state_machine"),
                                    context=(
                                        f"state={state}, states={sm.states}, outbound_transitions=0"
                                    ),
                                )
                            ],
                            remediation=Remediation(
                                summary=(
                                    f"Either add an outbound transition from "
                                    f"'{state}' or confirm it is a valid terminal "
                                    f"state."
                                ),
                                effort=RemediationEffort.SMALL,
                                dsl_example=(f"  {state} -> next_state: requires some_field"),
                            ),
                        )
                    )

        return findings

    # ------------------------------------------------------------------
    # DI-06  Cross-entity computed field dependency
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="DI-06",
        category="data_integrity",
        subcategory="cross_entity_computed",
        title="Computed field with cross-entity dependency",
    )
    def check_cross_entity_computed(self, appspec: AppSpec) -> list[Finding]:
        """Flag computed fields that depend on paths crossing entity boundaries."""
        findings: list[Finding] = []

        for entity in appspec.domain.entities:
            for cf in entity.computed_fields:
                cross_deps = [d for d in cf.dependencies if "." in d]
                if cross_deps:
                    findings.append(
                        Finding(
                            agent=AgentId.DI,
                            heuristic_id="DI-06",
                            category="data_integrity",
                            subcategory="cross_entity_computed",
                            severity=Severity.INFO,
                            confidence=Confidence.CONFIRMED,
                            title=(f"Cross-entity dependency in {entity.name}.{cf.name}"),
                            description=(
                                f"Computed field '{cf.name}' on entity "
                                f"'{entity.name}' references cross-entity paths: "
                                f"{cross_deps}. This creates a runtime dependency "
                                f"on related records and may impact query "
                                f"performance or cache-invalidation strategies."
                            ),
                            entity_name=entity.name,
                            evidence=[
                                Evidence(
                                    evidence_type="ir_pattern",
                                    location=(f"entity.{entity.name}.computed.{cf.name}"),
                                    context=(
                                        f"expression={cf.expression}, "
                                        f"cross_entity_deps={cross_deps}"
                                    ),
                                )
                            ],
                            remediation=Remediation(
                                summary=(
                                    "Ensure the cross-entity relationship is "
                                    "indexed and consider caching the computed "
                                    "value if it is queried frequently."
                                ),
                                effort=RemediationEffort.MEDIUM,
                            ),
                        )
                    )

        return findings

    # ------------------------------------------------------------------
    # DI-07  PII / financial fields without audit
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="DI-07",
        category="data_integrity",
        subcategory="sensitive_no_audit",
        title="PII/financial fields without audit logging",
    )
    def check_sensitive_fields_without_audit(self, appspec: AppSpec) -> list[Finding]:
        """Flag entities that have classified PII/financial fields but no audit."""
        findings: list[Finding] = []

        if appspec.policies is None:
            return findings

        # Group classifications by entity.
        entity_classifications: dict[str, list[str]] = {}
        for cls_spec in appspec.policies.classifications:
            if cls_spec.classification in _SENSITIVE_CLASSIFICATIONS:
                entity_classifications.setdefault(cls_spec.entity, []).append(
                    f"{cls_spec.field} ({cls_spec.classification.value})"
                )

        for entity_name, classified_fields in entity_classifications.items():
            entity = appspec.get_entity(entity_name)
            if entity is None:
                continue

            audit_enabled = entity.audit is not None and entity.audit.enabled
            if not audit_enabled:
                findings.append(
                    Finding(
                        agent=AgentId.DI,
                        heuristic_id="DI-07",
                        category="data_integrity",
                        subcategory="sensitive_no_audit",
                        severity=Severity.HIGH,
                        confidence=Confidence.CONFIRMED,
                        title=(f"Entity '{entity_name}' has sensitive data but no audit logging"),
                        description=(
                            f"Entity '{entity_name}' contains fields classified "
                            f"as PII or financial ({', '.join(classified_fields)}) "
                            f"but audit logging is not enabled. Regulatory "
                            f"frameworks (GDPR, PCI-DSS) typically require an "
                            f"audit trail for access to sensitive data."
                        ),
                        entity_name=entity_name,
                        evidence=[
                            Evidence(
                                evidence_type="config_value",
                                location=f"entity.{entity_name}.audit",
                                context=(
                                    f"audit={'disabled' if entity.audit is None else 'enabled=' + str(entity.audit.enabled)}, "
                                    f"classified_fields={classified_fields}"
                                ),
                            )
                        ],
                        remediation=Remediation(
                            summary=(
                                "Enable audit logging on the entity to track "
                                "access to sensitive fields."
                            ),
                            effort=RemediationEffort.SMALL,
                            dsl_example=(f"entity {entity_name}:\n  audit:\n    enabled: true"),
                        ),
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # DI-08  Ledger sync_to target field type mismatch
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="DI-08",
        category="data_integrity",
        subcategory="ledger_sync_type",
        title="Ledger sync_to target field type mismatch",
    )
    def check_ledger_sync_target(self, appspec: AppSpec) -> list[Finding]:
        """Flag ledgers whose sync_to target field is missing or non-numeric."""
        findings: list[Finding] = []

        for ledger in appspec.ledgers:
            if ledger.sync is None:
                continue

            target_entity_name = ledger.sync.target_entity
            target_field_name = ledger.sync.target_field
            entity = appspec.get_entity(target_entity_name)

            if entity is None:
                findings.append(
                    Finding(
                        agent=AgentId.DI,
                        heuristic_id="DI-08",
                        category="data_integrity",
                        subcategory="ledger_sync_type",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.CONFIRMED,
                        title=(
                            f"Ledger '{ledger.name}' sync target entity "
                            f"'{target_entity_name}' not found"
                        ),
                        description=(
                            f"Ledger '{ledger.name}' is configured to sync to "
                            f"'{target_entity_name}.{target_field_name}' but "
                            f"entity '{target_entity_name}' does not exist in "
                            f"the domain model."
                        ),
                        construct_type="ledger",
                        evidence=[
                            Evidence(
                                evidence_type="ir_pattern",
                                location=f"ledger.{ledger.name}.sync",
                                context=(
                                    f"target_entity={target_entity_name}, entity_not_found=True"
                                ),
                            )
                        ],
                        remediation=Remediation(
                            summary=(
                                f"Define entity '{target_entity_name}' or "
                                f"correct the sync_to target."
                            ),
                            effort=RemediationEffort.MEDIUM,
                        ),
                    )
                )
                continue

            field = entity.get_field(target_field_name)

            if field is None:
                findings.append(
                    Finding(
                        agent=AgentId.DI,
                        heuristic_id="DI-08",
                        category="data_integrity",
                        subcategory="ledger_sync_type",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.CONFIRMED,
                        title=(
                            f"Ledger '{ledger.name}' sync target field "
                            f"'{target_entity_name}.{target_field_name}' not found"
                        ),
                        description=(
                            f"Ledger '{ledger.name}' syncs to "
                            f"'{target_entity_name}.{target_field_name}' but "
                            f"field '{target_field_name}' does not exist on "
                            f"entity '{target_entity_name}'."
                        ),
                        entity_name=target_entity_name,
                        construct_type="ledger",
                        evidence=[
                            Evidence(
                                evidence_type="ir_pattern",
                                location=(
                                    f"ledger.{ledger.name}.sync -> entity.{target_entity_name}"
                                ),
                                context=(
                                    f"target_field={target_field_name}, "
                                    f"available_fields="
                                    f"{[f.name for f in entity.fields]}"
                                ),
                            )
                        ],
                        remediation=Remediation(
                            summary=(
                                f"Add a numeric field '{target_field_name}' to "
                                f"entity '{target_entity_name}' or correct the "
                                f"sync_to target."
                            ),
                            effort=RemediationEffort.SMALL,
                            dsl_example=(f"  {target_field_name}: decimal(18,2)"),
                        ),
                    )
                )
                continue

            if field.type.kind not in _NUMERIC_KINDS:
                findings.append(
                    Finding(
                        agent=AgentId.DI,
                        heuristic_id="DI-08",
                        category="data_integrity",
                        subcategory="ledger_sync_type",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.CONFIRMED,
                        title=(
                            f"Ledger '{ledger.name}' sync target "
                            f"'{target_entity_name}.{target_field_name}' is not "
                            f"numeric"
                        ),
                        description=(
                            f"Ledger '{ledger.name}' syncs its balance to "
                            f"'{target_entity_name}.{target_field_name}' but the "
                            f"field type is '{field.type.kind.value}' instead of "
                            f"a numeric type (int, decimal, money). Balance "
                            f"values written to this field may be truncated or "
                            f"rejected."
                        ),
                        entity_name=target_entity_name,
                        construct_type="ledger",
                        evidence=[
                            Evidence(
                                evidence_type="ir_pattern",
                                location=(f"entity.{target_entity_name}.{target_field_name}"),
                                context=(
                                    f"field_type={field.type.kind.value}, "
                                    f"expected_types="
                                    f"{sorted(k.value for k in _NUMERIC_KINDS)}"
                                ),
                            )
                        ],
                        remediation=Remediation(
                            summary=(
                                f"Change the type of "
                                f"'{target_entity_name}.{target_field_name}' "
                                f"to a numeric type (decimal, int, or money)."
                            ),
                            effort=RemediationEffort.SMALL,
                            dsl_example=(f"  {target_field_name}: decimal(18,2)"),
                        ),
                    )
                )

        return findings
