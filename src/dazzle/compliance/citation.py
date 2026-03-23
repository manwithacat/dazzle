"""Deterministic citation validation for generated compliance documents."""

from __future__ import annotations

import re

CITATION_PATTERN = re.compile(r"DSL ref:\s*(\w+)\.(\w+)")


def validate_citations(text: str, auditspec: dict) -> list[str]:
    """Validate all DSL ref: citations in text against the AuditSpec.

    Returns list of issue descriptions for invalid citations. Empty if all valid.
    """
    valid_refs = set()
    for control in auditspec.get("controls", []):
        for ev in control.get("evidence", []):
            construct = ev.get("construct", "")
            for ref in ev.get("refs", []):
                entity = ref.get("entity", "")
                if entity:
                    valid_refs.add((entity, construct))

    issues = []
    for match in CITATION_PATTERN.finditer(text):
        entity = match.group(1)
        construct = match.group(2)
        if (entity, construct) not in valid_refs:
            issues.append(
                f"Invalid citation: DSL ref: {entity}.{construct} — not found in AuditSpec evidence"
            )

    return issues
