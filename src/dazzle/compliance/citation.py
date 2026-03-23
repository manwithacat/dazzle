"""Deterministic citation validation for generated compliance documents."""

from __future__ import annotations

import re
from typing import Any

CITATION_PATTERN = re.compile(r"DSL ref:\s*(\w+)\.(\w+)")


def validate_citations(text: str, auditspec: dict[str, Any]) -> list[str]:
    """Validate all DSL ref: citations in text against the AuditSpec.

    Citation format: ``DSL ref: EntityName.construct``

    Where ``EntityName`` is the DSL entity name and ``construct`` is the
    evidence construct type (e.g. permit, classify, scope).

    Returns list of issue descriptions for invalid citations. Empty if all valid.
    """
    valid_refs: set[tuple[str, str]] = set()
    for control in auditspec.get("controls", []):
        for ev in control.get("evidence", []):
            construct = ev.get("construct", "")
            for ref in ev.get("refs", []):
                entity = ref.get("entity", "")
                if entity:
                    valid_refs.add((entity, construct))

    issues: list[str] = []
    for match in CITATION_PATTERN.finditer(text):
        entity = match.group(1)
        construct = match.group(2)
        if (entity, construct) not in valid_refs:
            issues.append(
                f"Invalid citation: DSL ref: {entity}.{construct} — not found in AuditSpec evidence"
            )

    return issues
