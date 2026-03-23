"""Compliance pipeline coordinator — orchestrates compilation, agent dispatch, and rendering."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from dazzle.compliance.compiler import compile_auditspec
from dazzle.compliance.evidence import _find_dsl_files, extract_all_evidence
from dazzle.compliance.review import generate_review_yaml
from dazzle.compliance.slicer import slice_auditspec
from dazzle.compliance.taxonomy import load_taxonomy


def topological_sort_documents(documents: list[dict]) -> list[dict]:
    """Sort documents by depends_on for correct generation order."""
    by_id = {d["id"]: d for d in documents}
    visited = set()
    order = []

    def visit(doc_id):
        if doc_id in visited:
            return
        visited.add(doc_id)
        doc = by_id.get(doc_id, {})
        for dep in doc.get("depends_on", []):
            if dep in by_id:
                visit(dep)
        order.append(by_id[doc_id])

    for doc in documents:
        visit(doc["id"])

    return order


def build_agent_context(
    document: dict,
    auditspec: dict,
    formality: str = "formal",
) -> dict:
    """Build the context dict that gets passed to a per-document AI agent."""
    all_control_ids = set()
    section_instructions = []

    for section in document.get("sections", []):
        controls = section.get("controls", [])
        if controls == "all":
            all_control_ids = "all"
        elif isinstance(all_control_ids, set) and isinstance(controls, list):
            all_control_ids.update(controls)

        section_instructions.append(
            {
                "title": section["title"],
                "source": section.get("source", "auditspec"),
                "extract": section.get("extract"),
                "ai_instruction": section.get("ai_instruction", ""),
                "tone": section.get("tone", ""),
                "layout": section.get("layout"),
                "columns": section.get("columns"),
                "filter": section.get("filter"),
            }
        )

    if all_control_ids == "all":
        sliced = auditspec
    else:
        sliced = slice_auditspec(auditspec, controls=list(all_control_ids))

    return {
        "document_id": document["id"],
        "document_title": document["name"],
        "formality": formality,
        "target_pages": document.get("target_pages"),
        "sliced_auditspec": sliced,
        "section_instructions": section_instructions,
    }


def compile_full_pipeline(
    project_path: Path,
    framework: str = "iso27001",
) -> dict:
    """Run the full deterministic pipeline: taxonomy + evidence -> AuditSpec."""
    taxonomy_path = project_path / ".dazzle" / "compliance" / "frameworks" / f"{framework}.yaml"
    taxonomy = load_taxonomy(taxonomy_path)
    evidence = extract_all_evidence(project_path)

    # Discover DSL source path for the hash
    dsl_files = _find_dsl_files(project_path)
    dsl_source = str(dsl_files[0]) if dsl_files else str(project_path / "dsl" / "app.dsl")

    return compile_auditspec(taxonomy, evidence, dsl_source)


def write_outputs(
    project_path: Path,
    auditspec: dict,
    framework: str = "iso27001",
) -> Path:
    """Write AuditSpec and review.yaml to output directory."""
    output_dir = project_path / ".dazzle" / "compliance" / "output" / framework
    output_dir.mkdir(parents=True, exist_ok=True)

    auditspec_path = output_dir / "auditspec.json"
    auditspec_path.write_text(json.dumps(auditspec, indent=2))

    review = generate_review_yaml(auditspec)
    review_path = output_dir / "review.yaml"
    review_path.write_text(yaml.dump(review, default_flow_style=False))

    (output_dir / "markdown").mkdir(exist_ok=True)

    return output_dir
