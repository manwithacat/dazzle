"""Compile taxonomy + evidence into a typed AuditSpec.

Maps DSL evidence to compliance framework controls and produces
a per-control assessment (evidenced / partial / gap / excluded).
"""

from datetime import UTC, datetime
from typing import Literal

from dazzle.compliance.models import (
    AuditSpec,
    AuditSummary,
    ControlResult,
    EvidenceItem,
    EvidenceMap,
    Taxonomy,
)

# Maps raw DSL construct names to taxonomy evidence categories.
# When a taxonomy control lists dsl_evidence with construct="permit",
# evidence items from both "permit" AND "grant_schema" match.
#
# Why these mappings exist:
# grant_schema → permit: delegation rules evidence access control policies
# workspace → personas: workspace assignments evidence role-based interfaces
# llm_intent → classify: AI intent config evidences data handling governance
# archetype → classify: audit trail fields evidence data lifecycle tracking
# scenarios → stories: test scenarios evidence control validation
CONSTRUCT_TO_KEY: dict[str, str] = {
    "grant_schema": "permit",
    "workspace": "personas",
    "llm_intent": "classify",
    "archetype": "classify",
    "scenarios": "stories",
}


def compile_auditspec(taxonomy: Taxonomy, evidence: EvidenceMap) -> AuditSpec:
    """Compile a taxonomy and evidence map into a typed AuditSpec.

    For each control in the taxonomy, checks whether the DSL evidence
    contains items matching the control's expected constructs. Produces
    a ControlResult with status and tier for each control.
    """
    # Build reverse mapping: taxonomy category → list of evidence items
    evidence_by_category: dict[str, list[EvidenceItem]] = {}
    for construct_name, items in evidence.items.items():
        # Map to taxonomy category (or use raw name if no mapping)
        category = CONSTRUCT_TO_KEY.get(construct_name, construct_name)
        evidence_by_category.setdefault(category, []).extend(items)

    # Pre-compute theme lookup
    control_to_theme: dict[str, str] = {}
    for theme in taxonomy.themes:
        for ctrl in theme.controls:
            control_to_theme[ctrl.id] = theme.id

    # Assess each control
    results: list[ControlResult] = []
    for control in taxonomy.all_controls():
        expected = {e.construct for e in control.dsl_evidence}
        matched: list[EvidenceItem] = []
        for category in expected:
            matched.extend(evidence_by_category.get(category, []))

        status: Literal["evidenced", "partial", "gap", "excluded"]
        if matched:
            status = "evidenced"
            tier = 1
        elif not expected:
            # Control has no DSL evidence mapping — excluded
            status = "excluded"
            tier = 0
        else:
            status = "gap"
            tier = 3

        results.append(
            ControlResult(
                control_id=control.id,
                control_name=control.name,
                theme_id=control_to_theme.get(control.id, ""),
                status=status,
                tier=tier,
                evidence=matched,
            )
        )

    # Summary
    summary = AuditSummary(
        total_controls=len(results),
        evidenced=sum(1 for r in results if r.status == "evidenced"),
        partial=sum(1 for r in results if r.status == "partial"),
        gaps=sum(1 for r in results if r.status == "gap"),
        excluded=sum(1 for r in results if r.status == "excluded"),
    )

    return AuditSpec(
        framework_id=taxonomy.id,
        framework_name=taxonomy.name,
        framework_version=taxonomy.version,
        generated_at=datetime.now(UTC).isoformat(),
        dsl_hash=evidence.dsl_hash,
        controls=results,
        summary=summary,
    )
