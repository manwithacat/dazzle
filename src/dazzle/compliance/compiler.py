"""AuditSpec compiler — combines taxonomy + DSL evidence into the IR."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from dazzle.compliance.taxonomy import Control, Taxonomy

CONSTRUCT_TO_KEY = {
    "classify": "classify",
    "permit": "permit",
    "scope": "scope",
    "visible": "visible",
    "transitions": "transitions",
    "processes": "processes",
    "stories": "stories",
    "grant_schema": "permit",
    "persona": "personas",
    "workspace": "personas",
    "llm_config": "classify",
    "archetype": "classify",
    "scenarios": "stories",
}


def _build_evidence_for_control(
    control: Control, all_evidence: dict
) -> tuple[list[dict], list[dict]]:
    """Build evidence and gap entries for a single control."""
    evidence = []
    gaps = []

    if not control.dsl_evidence:
        gaps.append(
            {
                "description": f"No DSL construct addresses '{control.name}' — requires organisational policy",
                "tier": 3,
                "action": f"Document policy for: {control.name}",
            }
        )
        return evidence, gaps

    for mapping in control.dsl_evidence:
        key = CONSTRUCT_TO_KEY.get(mapping.construct, mapping.construct)
        data = all_evidence.get(key)

        if data and (
            isinstance(data, list) and len(data) > 0 or isinstance(data, dict) and len(data) > 0
        ):
            entry = {
                "construct": mapping.construct,
                "type": mapping.description,
                "summary": f"DSL {mapping.construct} evidence found",
            }

            if isinstance(data, list):
                entry["count"] = len(data)
                entry["refs"] = data[:5]
            elif isinstance(data, dict):
                entry["count"] = len(data)
                entry["refs"] = [{"entity": k, **v} for k, v in list(data.items())[:5]]

            evidence.append(entry)
        else:
            gaps.append(
                {
                    "description": f"No {mapping.construct} evidence found: {mapping.description}",
                    "tier": 2,
                    "action": f"Add {mapping.construct} constructs or document manually",
                }
            )

    return evidence, gaps


def _compute_status(evidence: list[dict], gaps: list[dict]) -> str:
    """Compute control status from evidence and gaps."""
    if not evidence and gaps:
        return "gap"
    if evidence and not gaps:
        return "evidenced"
    return "partial"


def _find_theme(taxonomy: Taxonomy, control_id: str) -> str:
    """Find which theme a control belongs to."""
    for theme in taxonomy.themes:
        for ctrl in theme.controls:
            if ctrl.id == control_id:
                return theme.id
    return "unknown"


def compile_auditspec(
    taxonomy: Taxonomy,
    evidence: dict,
    dsl_source: str,
    dsl_content: str | None = None,
) -> dict:
    """Compile an AuditSpec from taxonomy and evidence."""
    if dsl_content is None:
        dsl_path = Path(dsl_source)
        dsl_content = dsl_path.read_text() if dsl_path.exists() else ""

    dsl_hash = f"sha256:{hashlib.sha256(dsl_content.encode()).hexdigest()[:16]}"

    controls = []
    counts = {"evidenced": 0, "partial": 0, "gaps": 0}

    for control in taxonomy.all_controls():
        ev, gaps = _build_evidence_for_control(control, evidence)
        status = _compute_status(ev, gaps)
        counts[status if status != "gap" else "gaps"] += 1

        controls.append(
            {
                "id": control.id,
                "name": control.name,
                "theme": _find_theme(taxonomy, control.id),
                "status": status,
                "evidence": ev,
                "gaps": gaps,
                "recommendations": [],
            }
        )

    return {
        "auditspec_version": "1.0",
        "framework": taxonomy.id,
        "framework_version": taxonomy.version,
        "generated_at": datetime.now(UTC).isoformat(),
        "dsl_source": dsl_source,
        "dsl_hash": dsl_hash,
        "summary": {
            "total_controls": len(controls),
            **counts,
        },
        "controls": controls,
    }
