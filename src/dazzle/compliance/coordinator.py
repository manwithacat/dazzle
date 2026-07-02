"""Orchestrate the full compliance compilation pipeline.

Coordinates: taxonomy loading → evidence extraction → AuditSpec compilation.
File output is handled by the CLI, not this module.
"""

from pathlib import Path

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
