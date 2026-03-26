"""Deterministic citation validation for generated compliance documents."""

import re
from typing import Any

CITATION_PATTERN = re.compile(r"DSL ref:\s*(\w+)\.(\w+)")


def validate_citations(text: str, auditspec: dict[str, Any]) -> list[str]:
    """Validate all DSL ref: citations in text against the AuditSpec.

    Citation format: ``DSL ref: EntityName.construct``

    Where ``EntityName`` is the DSL entity name and ``construct`` is the
    evidence construct type (e.g. permit, classify, scope).

    Accepts either the new typed AuditSpec schema (evidence items with
    entity/construct/dsl_ref fields) or the legacy dict schema (evidence
    items with construct + refs list).

    Returns list of issue descriptions for invalid citations. Empty if all valid.
    """
    valid_refs: set[tuple[str, str]] = set()
    for control in auditspec.get("controls", []):
        for ev in control.get("evidence", []):
            construct = ev.get("construct", "")
            # New schema: each evidence item has entity and dsl_ref directly
            entity = ev.get("entity", "")
            if entity:
                valid_refs.add((entity, construct))
            # Legacy schema: evidence has refs list
            for ref in ev.get("refs", []):
                ref_entity = ref.get("entity", "")
                if ref_entity:
                    valid_refs.add((ref_entity, construct))

    issues: list[str] = []
    for match in CITATION_PATTERN.finditer(text):
        entity = match.group(1)
        construct = match.group(2)
        if (entity, construct) not in valid_refs:
            issues.append(
                f"Invalid citation: DSL ref: {entity}.{construct} — not found in AuditSpec evidence"
            )

    return issues
