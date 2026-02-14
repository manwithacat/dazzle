"""Business Logic detection agent (BL-01 through BL-08)."""

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
from dazzle.core.ir.process import ProcessTriggerKind
from dazzle.core.ir.stories import StoryTrigger


class BusinessLogicAgent(DetectionAgent):
    """Detects business-logic risks and gaps in the application specification."""

    @property
    def agent_id(self) -> AgentId:
        return AgentId.BL

    # ------------------------------------------------------------------
    # BL-01  Process with empty implements
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="BL-01",
        category="business_logic",
        subcategory="process_traceability",
        title="Process not linked to any story",
    )
    def check_process_empty_implements(self, appspec: AppSpec) -> list[Finding]:
        """Flag processes whose implements list is empty (not linked to any story)."""
        findings: list[Finding] = []

        for process in appspec.processes:
            if not process.implements:
                findings.append(
                    Finding(
                        agent=AgentId.BL,
                        heuristic_id="BL-01",
                        category="business_logic",
                        subcategory="process_traceability",
                        severity=Severity.LOW,
                        confidence=Confidence.CONFIRMED,
                        title=f"Process '{process.name}' is not linked to any story",
                        description=(
                            f"Process '{process.name}' has an empty 'implements' "
                            f"list, meaning it is not traceable to any user story. "
                            f"Unlinked processes risk delivering functionality "
                            f"that was never requested or validated against "
                            f"acceptance criteria."
                        ),
                        construct_type="process",
                        evidence=[
                            Evidence(
                                evidence_type="ir_pattern",
                                location=f"process.{process.name}",
                                context="implements=[]",
                            )
                        ],
                        remediation=Remediation(
                            summary=(
                                "Link this process to one or more stories via "
                                "the 'implements' field."
                            ),
                            effort=RemediationEffort.TRIVIAL,
                            dsl_example=(f"process {process.name}:\n  implements: [ST-001]"),
                        ),
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # BL-02  Story trigger mismatch
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="BL-02",
        category="business_logic",
        subcategory="trigger_mismatch",
        title="Story with status_changed trigger but no matching process",
    )
    def check_story_trigger_mismatch(self, appspec: AppSpec) -> list[Finding]:
        """Flag stories with a status_changed trigger that have no corresponding
        process with an entity_status_transition trigger."""
        findings: list[Finding] = []

        has_status_transition_process = any(
            p.trigger is not None and p.trigger.kind == ProcessTriggerKind.ENTITY_STATUS_TRANSITION
            for p in appspec.processes
        )

        for story in appspec.stories:
            if story.trigger == StoryTrigger.STATUS_CHANGED and not has_status_transition_process:
                findings.append(
                    Finding(
                        agent=AgentId.BL,
                        heuristic_id="BL-02",
                        category="business_logic",
                        subcategory="trigger_mismatch",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.LIKELY,
                        title=(
                            f"Story '{story.story_id}' uses status_changed but "
                            f"no process handles status transitions"
                        ),
                        description=(
                            f"Story '{story.story_id}' ('{story.title}') declares "
                            f"a 'status_changed' trigger, but no process in the "
                            f"specification has an 'entity_status_transition' "
                            f"trigger. The behaviour described by this story "
                            f"will not be executed automatically."
                        ),
                        construct_type="story",
                        evidence=[
                            Evidence(
                                evidence_type="ir_pattern",
                                location=f"story.{story.story_id}",
                                context=(
                                    f"trigger={story.trigger.value}, "
                                    f"process_status_transition_triggers=0"
                                ),
                            )
                        ],
                        remediation=Remediation(
                            summary=(
                                "Create a process with an "
                                "'entity_status_transition' trigger that "
                                "implements this story."
                            ),
                            effort=RemediationEffort.MEDIUM,
                            dsl_example=(
                                f"process handle_{story.story_id.lower().replace('-', '_')}:\n"
                                f"  implements: [{story.story_id}]\n"
                                f"  trigger:\n"
                                f"    kind: entity_status_transition\n"
                                f"    entity: <EntityName>\n"
                                f"    to_status: <target_status>"
                            ),
                        ),
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # BL-03  Entity with invariants but no test designs
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="BL-03",
        category="business_logic",
        subcategory="untested_invariant",
        title="Entity invariants without test coverage",
    )
    def check_invariants_without_tests(self, appspec: AppSpec) -> list[Finding]:
        """Flag entities that have invariants but no test designs covering them."""
        findings: list[Finding] = []
        test_names_lower = [t.name.lower() for t in appspec.tests]

        for entity in appspec.domain.entities:
            if not entity.invariants:
                continue

            entity_name_lower = entity.name.lower()
            has_covering_test = any(entity_name_lower in tn for tn in test_names_lower)

            if not has_covering_test:
                invariant_strs = [str(inv.expression) for inv in entity.invariants]
                findings.append(
                    Finding(
                        agent=AgentId.BL,
                        heuristic_id="BL-03",
                        category="business_logic",
                        subcategory="untested_invariant",
                        severity=Severity.LOW,
                        confidence=Confidence.POSSIBLE,
                        title=(
                            f"Entity '{entity.name}' has {len(entity.invariants)} "
                            f"invariant(s) but no test designs"
                        ),
                        description=(
                            f"Entity '{entity.name}' declares invariants "
                            f"({', '.join(invariant_strs)}) but no test in the "
                            f"specification references this entity. Invariants "
                            f"that are never tested may silently fail in "
                            f"production."
                        ),
                        entity_name=entity.name,
                        evidence=[
                            Evidence(
                                evidence_type="missing_construct",
                                location=f"entity.{entity.name}.invariants",
                                context=(
                                    f"invariant_count={len(entity.invariants)}, matching_tests=0"
                                ),
                            )
                        ],
                        remediation=Remediation(
                            summary=(
                                f"Add test designs that exercise the invariants on '{entity.name}'."
                            ),
                            effort=RemediationEffort.SMALL,
                            dsl_example=(
                                f"test {entity.name}_invariant_test:\n"
                                f"  action: create {entity.name}\n"
                                f"  expect: error"
                            ),
                        ),
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # BL-04  Approval entity transitions lack role guards
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="BL-04",
        category="business_logic",
        subcategory="approval_role_guard",
        title="Approval workflow transitions lack role guards",
    )
    def check_approval_transitions_without_role_guards(self, appspec: AppSpec) -> list[Finding]:
        """Flag approval workflows whose backing entity state transitions
        do not have role-based guards."""
        findings: list[Finding] = []

        for approval in appspec.approvals:
            if not approval.entity:
                continue

            entity = appspec.get_entity(approval.entity)
            if entity is None or entity.state_machine is None:
                continue

            unguarded: list[str] = []
            for transition in entity.state_machine.transitions:
                has_role_guard = any(g.requires_role for g in transition.guards)
                if not has_role_guard:
                    unguarded.append(f"{transition.from_state} -> {transition.to_state}")

            if unguarded:
                findings.append(
                    Finding(
                        agent=AgentId.BL,
                        heuristic_id="BL-04",
                        category="business_logic",
                        subcategory="approval_role_guard",
                        severity=Severity.HIGH,
                        confidence=Confidence.CONFIRMED,
                        title=(
                            f"Approval '{approval.name}' has transitions "
                            f"without role guards on entity '{approval.entity}'"
                        ),
                        description=(
                            f"Approval '{approval.name}' targets entity "
                            f"'{approval.entity}', but the following state "
                            f"transitions lack a 'requires_role' guard: "
                            f"{', '.join(unguarded)}. Without role guards, "
                            f"any authenticated user could advance the "
                            f"approval workflow."
                        ),
                        entity_name=approval.entity,
                        construct_type="approval",
                        evidence=[
                            Evidence(
                                evidence_type="ir_pattern",
                                location=(f"entity.{approval.entity}.state_machine"),
                                context=(
                                    f"approval={approval.name}, unguarded_transitions={unguarded}"
                                ),
                            )
                        ],
                        remediation=Remediation(
                            summary=(
                                "Add 'requires_role' guards to the state "
                                "transitions that control the approval flow."
                            ),
                            effort=RemediationEffort.SMALL,
                            dsl_example=(
                                f"  pending_approval -> approved: "
                                f"role({approval.approver_role or 'approver'})"
                            ),
                        ),
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # BL-05  SLA without monitoring process/schedule
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="BL-05",
        category="business_logic",
        subcategory="sla_monitoring",
        title="SLA without monitoring process or schedule",
    )
    def check_sla_without_monitoring(self, appspec: AppSpec) -> list[Finding]:
        """Flag SLAs that have no schedule or process to monitor them."""
        findings: list[Finding] = []

        # Build a set of entity names and name fragments referenced by
        # processes and schedules (lowercased for fuzzy matching).
        monitored_refs: set[str] = set()
        for process in appspec.processes:
            name_lower = process.name.lower()
            monitored_refs.add(name_lower)
            if process.title:
                monitored_refs.add(process.title.lower())
            if process.trigger and process.trigger.entity_name:
                monitored_refs.add(process.trigger.entity_name.lower())
        for schedule in appspec.schedules:
            name_lower = schedule.name.lower()
            monitored_refs.add(name_lower)
            if schedule.title:
                monitored_refs.add(schedule.title.lower())

        for sla in appspec.slas:
            sla_entity_lower = sla.entity.lower() if sla.entity else ""
            sla_name_lower = sla.name.lower()

            has_monitor = (
                any(
                    sla_entity_lower in ref or sla_name_lower in ref or "sla" in ref
                    for ref in monitored_refs
                )
                if sla_entity_lower or sla_name_lower
                else False
            )

            if not has_monitor:
                findings.append(
                    Finding(
                        agent=AgentId.BL,
                        heuristic_id="BL-05",
                        category="business_logic",
                        subcategory="sla_monitoring",
                        severity=Severity.MEDIUM,
                        confidence=Confidence.LIKELY,
                        title=(f"SLA '{sla.name}' has no monitoring process or schedule"),
                        description=(
                            f"SLA '{sla.name}' tracks entity "
                            f"'{sla.entity}' but no process or schedule "
                            f"in the specification appears to monitor it. "
                            f"Without active monitoring, SLA breaches will "
                            f"go undetected and escalation actions will "
                            f"not fire."
                        ),
                        construct_type="sla",
                        evidence=[
                            Evidence(
                                evidence_type="missing_construct",
                                location=f"sla.{sla.name}",
                                context=(
                                    f"entity={sla.entity}, "
                                    f"matching_processes=0, "
                                    f"matching_schedules=0"
                                ),
                            )
                        ],
                        remediation=Remediation(
                            summary=(
                                "Create a schedule or process that periodically "
                                "checks SLA deadlines and triggers breach "
                                "actions."
                            ),
                            effort=RemediationEffort.MEDIUM,
                            dsl_example=(
                                f"schedule check_{sla.name.lower()}_sla:\n"
                                f'  cron: "*/15 * * * *"\n'
                                f"  steps:\n"
                                f"    - name: check_breaches\n"
                                f"      service: SLAMonitor"
                            ),
                        ),
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # BL-06  Experience with unreachable steps
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="BL-06",
        category="business_logic",
        subcategory="unreachable_step",
        title="Experience with unreachable steps",
    )
    def check_experience_unreachable_steps(self, appspec: AppSpec) -> list[Finding]:
        """Flag experience steps that are not reachable from the start_step."""
        findings: list[Finding] = []

        for experience in appspec.experiences:
            if not experience.steps:
                continue

            all_step_names = {step.name for step in experience.steps}

            # BFS from start_step.
            reachable: set[str] = set()
            queue = [experience.start_step]
            while queue:
                current = queue.pop(0)
                if current in reachable or current not in all_step_names:
                    continue
                reachable.add(current)
                step = experience.get_step(current)
                if step is None:
                    continue
                for transition in step.transitions:
                    if transition.next_step not in reachable:
                        queue.append(transition.next_step)

            unreachable = all_step_names - reachable
            if unreachable:
                findings.append(
                    Finding(
                        agent=AgentId.BL,
                        heuristic_id="BL-06",
                        category="business_logic",
                        subcategory="unreachable_step",
                        severity=Severity.HIGH,
                        confidence=Confidence.CONFIRMED,
                        title=(
                            f"Experience '{experience.name}' has "
                            f"{len(unreachable)} unreachable step(s)"
                        ),
                        description=(
                            f"Experience '{experience.name}' starts at "
                            f"'{experience.start_step}' but the following "
                            f"steps are not reachable via any transition "
                            f"chain: {sorted(unreachable)}. Users will "
                            f"never encounter these steps, and the logic "
                            f"they contain is dead code."
                        ),
                        construct_type="experience",
                        evidence=[
                            Evidence(
                                evidence_type="ir_pattern",
                                location=f"experience.{experience.name}",
                                context=(
                                    f"start_step={experience.start_step}, "
                                    f"total_steps={len(experience.steps)}, "
                                    f"unreachable={sorted(unreachable)}"
                                ),
                            )
                        ],
                        remediation=Remediation(
                            summary=(
                                "Add transitions leading to the unreachable "
                                "steps, or remove them if they are no longer "
                                "needed."
                            ),
                            effort=RemediationEffort.SMALL,
                            dsl_example=(
                                f"  step existing_step:\n"
                                f"    transitions:\n"
                                f"      - event: continue\n"
                                f"        next_step: {sorted(unreachable)[0]}"
                            ),
                        ),
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # BL-07  Entity not referenced by any surface
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="BL-07",
        category="business_logic",
        subcategory="entity_no_surface",
        title="Entity not referenced by any surface",
    )
    def check_entity_without_surface(self, appspec: AppSpec) -> list[Finding]:
        """Flag entities that are not referenced by any surface's entity_ref."""
        findings: list[Finding] = []

        surface_entities = {s.entity_ref for s in appspec.surfaces if s.entity_ref}

        for entity in appspec.domain.entities:
            if entity.name not in surface_entities:
                findings.append(
                    Finding(
                        agent=AgentId.BL,
                        heuristic_id="BL-07",
                        category="business_logic",
                        subcategory="entity_no_surface",
                        severity=Severity.LOW,
                        confidence=Confidence.POSSIBLE,
                        title=(f"Entity '{entity.name}' is not used by any surface"),
                        description=(
                            f"Entity '{entity.name}' is defined in the domain "
                            f"model but no surface references it via "
                            f"'entity_ref'. This may indicate the entity is "
                            f"an internal/backend-only model, or it may be "
                            f"missing a UI surface."
                        ),
                        entity_name=entity.name,
                        evidence=[
                            Evidence(
                                evidence_type="missing_construct",
                                location=f"entity.{entity.name}",
                                context=(f"surface_entity_refs={sorted(surface_entities)}"),
                            )
                        ],
                        remediation=Remediation(
                            summary=(
                                f"Create a surface for '{entity.name}' or "
                                f"confirm it is intentionally backend-only."
                            ),
                            effort=RemediationEffort.SMALL,
                            dsl_example=(
                                f"surface {entity.name.lower()}_list "
                                f'"{entity.name} List":\n'
                                f"  uses entity {entity.name}\n"
                                f"  mode: list"
                            ),
                        ),
                    )
                )

        return findings

    # ------------------------------------------------------------------
    # BL-08  Shared enum not referenced
    # ------------------------------------------------------------------

    @heuristic(
        heuristic_id="BL-08",
        category="business_logic",
        subcategory="unreferenced_enum",
        title="Shared enum not referenced by any entity field",
    )
    def check_unreferenced_enum(self, appspec: AppSpec) -> list[Finding]:
        """Flag shared enums that are not referenced by any entity field."""
        findings: list[Finding] = []

        # Collect all enum names referenced by entity fields.
        referenced_enums: set[str] = set()
        for entity in appspec.domain.entities:
            for field in entity.fields:
                if field.type.kind == FieldTypeKind.ENUM and field.type.ref_entity:
                    referenced_enums.add(field.type.ref_entity)

        for enum_spec in appspec.enums:
            if enum_spec.name not in referenced_enums:
                findings.append(
                    Finding(
                        agent=AgentId.BL,
                        heuristic_id="BL-08",
                        category="business_logic",
                        subcategory="unreferenced_enum",
                        severity=Severity.LOW,
                        confidence=Confidence.POSSIBLE,
                        title=(
                            f"Shared enum '{enum_spec.name}' is not referenced by any entity field"
                        ),
                        description=(
                            f"Shared enum '{enum_spec.name}' is defined but "
                            f"no entity field references it. This enum may "
                            f"be unused dead code or it may be intended for "
                            f"a field that has not been connected yet."
                        ),
                        construct_type="enum",
                        evidence=[
                            Evidence(
                                evidence_type="ir_pattern",
                                location=f"enum.{enum_spec.name}",
                                context=(
                                    f"values={[v.name for v in enum_spec.values]}, "
                                    f"referenced_by_fields=0"
                                ),
                            )
                        ],
                        remediation=Remediation(
                            summary=(
                                f"Reference enum '{enum_spec.name}' from an "
                                f"entity field or remove it if no longer needed."
                            ),
                            effort=RemediationEffort.TRIVIAL,
                            dsl_example=(
                                f"entity Example:\n"
                                f"  status: {enum_spec.name} = "
                                f"{enum_spec.values[0].name if enum_spec.values else 'value'}"
                            ),
                        ),
                    )
                )

        return findings
