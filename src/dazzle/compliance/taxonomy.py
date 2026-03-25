"""Compliance framework taxonomy loader.

Loads and validates YAML taxonomy files (e.g. ISO 27001).
Types are defined in models.py.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from dazzle.compliance.models import Control, DslEvidence, Taxonomy, Theme


class TaxonomyError(Exception):
    """Error loading or validating a compliance taxonomy."""


def load_taxonomy(path: Path) -> Taxonomy:
    """Load a compliance framework taxonomy from a YAML file.

    Args:
        path: Path to the framework YAML file.

    Returns:
        Parsed and validated Taxonomy.

    Raises:
        TaxonomyError: If the file is missing, malformed, or invalid.
    """
    if not path.exists():
        raise TaxonomyError(f"Taxonomy file not found: {path}")

    try:
        with path.open() as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise TaxonomyError(f"Invalid YAML in {path}: {e}") from e

    if not isinstance(raw, dict) or "framework" not in raw:
        raise TaxonomyError(f"Missing 'framework' key in {path}")

    fw = raw["framework"]

    try:
        themes = []
        for theme_data in fw.get("themes", []):
            controls = []
            for ctrl_data in theme_data.get("controls", []):
                evidence = [DslEvidence(**e) for e in ctrl_data.get("dsl_evidence", [])]
                controls.append(
                    Control(
                        id=ctrl_data["id"],
                        name=ctrl_data["name"],
                        objective=ctrl_data.get("objective", ""),
                        dsl_evidence=evidence,
                        attributes=ctrl_data.get("attributes", {}),
                        cross_references=ctrl_data.get("cross_references", []),
                    )
                )
            themes.append(
                Theme(
                    id=theme_data["id"],
                    name=theme_data["name"],
                    controls=controls,
                    mandatory=theme_data.get("mandatory", True),
                    applicability=theme_data.get("applicability", ""),
                )
            )

        return Taxonomy(
            id=fw["id"],
            name=fw["name"],
            version=fw.get("version", ""),
            jurisdiction=fw.get("jurisdiction", ""),
            body=fw.get("body", ""),
            related_frameworks=fw.get("related_frameworks", []),
            themes=themes,
        )
    except KeyError as e:
        raise TaxonomyError(f"Missing required field {e} in {path}") from e
