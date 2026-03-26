"""Orchestrate the full compliance compilation pipeline.

Coordinates: taxonomy loading → evidence extraction → AuditSpec compilation.
File output is handled by the CLI, not this module.
"""

from pathlib import Path
from typing import Any

from dazzle.compliance.compiler import compile_auditspec
from dazzle.compliance.evidence import extract_evidence_from_project
from dazzle.compliance.models import AuditSpec
from dazzle.compliance.taxonomy import load_taxonomy

# Default framework taxonomy bundled with Dazzle
_BUNDLED_FRAMEWORKS = Path(__file__).parent / "frameworks"


def compile_full_pipeline(
    project_root: Path,
    framework: str = "iso27001",
    taxonomy_path: Path | None = None,
) -> AuditSpec:
    """Run the full compliance pipeline: taxonomy + evidence → AuditSpec.

    Args:
        project_root: Path to the Dazzle project root.
        framework: Framework ID (used to find bundled taxonomy YAML).
        taxonomy_path: Override path to taxonomy YAML file.

    Returns:
        Compiled AuditSpec with per-control assessments.
    """
    # Load taxonomy
    if taxonomy_path is None:
        taxonomy_path = _BUNDLED_FRAMEWORKS / f"{framework}.yaml"
    taxonomy = load_taxonomy(taxonomy_path)

    # Extract evidence from AppSpec
    evidence = extract_evidence_from_project(project_root)

    # Compile
    auditspec = compile_auditspec(taxonomy, evidence)
    auditspec.dsl_source = str(project_root)

    return auditspec


def topological_sort_documents(
    doc_specs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort document specs by dependency order with cycle detection.

    Args:
        doc_specs: List of document spec dicts with 'id' and 'depends_on' keys.

    Returns:
        Sorted list of document spec dicts.

    Raises:
        ValueError: If a circular dependency is detected.
    """
    specs_by_id: dict[str, dict[str, Any]] = {s["id"]: s for s in doc_specs}
    deps: dict[str, list[str]] = {s["id"]: s.get("depends_on", []) for s in doc_specs}

    visited: set[str] = set()
    in_progress: set[str] = set()
    order: list[dict[str, Any]] = []

    def visit(doc_id: str) -> None:
        if doc_id in in_progress:
            raise ValueError(f"Circular dependency detected: {doc_id}")
        if doc_id in visited:
            return
        in_progress.add(doc_id)
        for dep in deps.get(doc_id, []):
            visit(dep)
        in_progress.discard(doc_id)
        visited.add(doc_id)
        if doc_id in specs_by_id:
            order.append(specs_by_id[doc_id])

    for doc_id in specs_by_id:
        visit(doc_id)

    return order


def build_agent_context(
    auditspec: AuditSpec,
    doc_specs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build per-document agent context from an AuditSpec.

    Args:
        auditspec: Compiled AuditSpec.
        doc_specs: Sorted document specifications.

    Returns:
        List of context dicts, one per document, for AI agent dispatch.
    """
    use_all_controls = False
    control_ids: set[str] = set()

    for doc in doc_specs:
        controls = doc.get("controls", [])
        if controls == "all":
            use_all_controls = True
        elif isinstance(controls, list):
            control_ids.update(controls)

    # Filter controls for each document
    contexts: list[dict[str, Any]] = []
    for doc in doc_specs:
        doc_controls = doc.get("controls", [])
        if doc_controls == "all" or use_all_controls:
            relevant = auditspec.controls
        elif isinstance(doc_controls, list):
            relevant = [c for c in auditspec.controls if c.control_id in set(doc_controls)]
        else:
            relevant = []

        contexts.append(
            {
                "document_id": doc["id"],
                "document_title": doc.get("title", doc["id"]),
                "controls": [c.model_dump() for c in relevant],
                "summary": auditspec.summary.model_dump(),
            }
        )

    return contexts
