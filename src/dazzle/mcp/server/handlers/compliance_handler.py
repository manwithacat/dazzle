"""MCP handler for compliance operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dazzle.compliance.coordinator import compile_full_pipeline, write_outputs
from dazzle.compliance.evidence import extract_all_evidence
from dazzle.compliance.review import generate_review_yaml


async def handle_compliance(operation: str, project_path: str, **kwargs: Any) -> dict:
    """Handle compliance MCP tool operations.

    Operations:
        compile: Compile AuditSpec from taxonomy + DSL evidence
        evidence: Extract DSL evidence summary
        gaps: List controls with gaps
        review: Generate review.yaml for human-in-the-loop
        summary: Quick compliance posture summary
    """
    pp = Path(project_path)

    if operation == "compile":
        framework = kwargs.get("framework", "iso27001")
        auditspec = compile_full_pipeline(pp, framework=framework)
        output_dir = write_outputs(pp, auditspec, framework=framework)
        return {
            "status": "compiled",
            "output_dir": str(output_dir),
            "summary": auditspec["summary"],
        }

    elif operation == "evidence":
        evidence = extract_all_evidence(pp)
        return {
            "constructs": {
                k: len(v) if isinstance(v, list) else len(v) for k, v in evidence.items()
            }
        }

    elif operation == "gaps":
        framework = kwargs.get("framework", "iso27001")
        auditspec = compile_full_pipeline(pp, framework=framework)
        gaps = [
            {"id": c["id"], "name": c["name"], "gaps": c["gaps"]}
            for c in auditspec["controls"]
            if c["status"] in ("gap", "partial")
        ]
        return {"gap_count": len(gaps), "gaps": gaps}

    elif operation == "review":
        framework = kwargs.get("framework", "iso27001")
        auditspec = compile_full_pipeline(pp, framework=framework)
        return generate_review_yaml(auditspec)

    elif operation == "summary":
        framework = kwargs.get("framework", "iso27001")
        auditspec = compile_full_pipeline(pp, framework=framework)
        s = auditspec["summary"]
        return {
            "framework": framework,
            "total_controls": s["total_controls"],
            "evidenced": s["evidenced"],
            "partial": s["partial"],
            "gaps": s["gaps"],
            "coverage_pct": round((s["evidenced"] + s["partial"]) / s["total_controls"] * 100, 1)
            if s["total_controls"] > 0
            else 0,
        }

    else:
        return {"error": f"Unknown operation: {operation}"}
