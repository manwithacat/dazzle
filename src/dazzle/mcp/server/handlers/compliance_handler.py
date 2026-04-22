"""Compliance MCP handler — read-only compliance pipeline operations."""

import json
from pathlib import Path
from typing import Any


def compile_compliance(project_path: Path, args: dict[str, Any]) -> str:
    """Compile taxonomy + evidence → AuditSpec JSON."""
    from dazzle.compliance.coordinator import compile_full_pipeline

    framework = args.get("framework", "iso27001")
    auditspec = compile_full_pipeline(project_path, framework=framework)
    return json.dumps(auditspec.model_dump(), indent=2)


def extract_evidence_op(project_path: Path, args: dict[str, Any]) -> str:
    """Extract evidence only → EvidenceMap JSON."""
    from dazzle.compliance.evidence import extract_evidence_from_project

    evidence = extract_evidence_from_project(project_path)
    return json.dumps(evidence.model_dump(), indent=2)


def compliance_gaps(project_path: Path, args: dict[str, Any]) -> str:
    """Compile + filter to gaps/partial → ControlResult list JSON.

    Uses ``dazzle.compliance.slicer.slice_auditspec`` so the filter logic
    stays in one place (shared with the ``dazzle compliance gaps`` CLI).
    """
    from dazzle.compliance.coordinator import compile_full_pipeline
    from dazzle.compliance.slicer import slice_auditspec

    framework = args.get("framework", "iso27001")
    auditspec = compile_full_pipeline(project_path, framework=framework)

    status_filter = args.get("status_filter") or ["gap", "partial"]
    tier_filter_arg = args.get("tier_filter")
    tier_filter = [int(t) for t in tier_filter_arg] if tier_filter_arg else None

    sliced = slice_auditspec(
        auditspec.model_dump(),
        status_filter=status_filter,
        tier_filter=tier_filter,
    )
    controls = sliced["controls"]
    return json.dumps({"gaps": controls, "count": len(controls)}, indent=2)


def compliance_summary(project_path: Path, args: dict[str, Any]) -> str:
    """Compile → AuditSummary JSON."""
    from dazzle.compliance.coordinator import compile_full_pipeline

    framework = args.get("framework", "iso27001")
    auditspec = compile_full_pipeline(project_path, framework=framework)
    return json.dumps(auditspec.summary.model_dump(), indent=2)


def compliance_review(project_path: Path, args: dict[str, Any]) -> str:
    """Compile + generate review data → review items JSON."""
    from dazzle.compliance.coordinator import compile_full_pipeline
    from dazzle.compliance.review import generate_review_data

    framework = args.get("framework", "iso27001")
    auditspec = compile_full_pipeline(project_path, framework=framework)
    review = generate_review_data(auditspec.model_dump())
    return json.dumps(review, indent=2)
