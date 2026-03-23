"""Load and validate compliance framework taxonomy YAML files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class TaxonomyError(Exception):
    """Raised when a taxonomy file is missing, malformed, or invalid."""


@dataclass
class DslEvidence:
    construct: str
    description: str


@dataclass
class Control:
    id: str
    name: str
    objective: str
    attributes: dict = field(default_factory=dict)
    dsl_evidence: list[DslEvidence] = field(default_factory=list)


@dataclass
class Theme:
    id: str
    name: str
    controls: list[Control] = field(default_factory=list)


@dataclass
class Taxonomy:
    id: str
    name: str
    jurisdiction: str
    body: str
    version: str
    themes: list[Theme] = field(default_factory=list)

    def all_controls(self) -> list[Control]:
        """Return flat list of all controls across all themes."""
        return [c for t in self.themes for c in t.controls]

    def controls_by_id(self) -> dict[str, Control]:
        """Return dict mapping control ID to Control."""
        return {c.id: c for c in self.all_controls()}


def load_taxonomy(path: Path) -> Taxonomy:
    """Load a framework taxonomy from a YAML file."""
    if not path.exists():
        raise TaxonomyError(f"Taxonomy file not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise TaxonomyError(f"Invalid YAML in {path}: {e}") from e

    if not isinstance(raw, dict) or "framework" not in raw:
        raise TaxonomyError(f"Missing 'framework' key in {path}")

    fw = raw["framework"]
    themes = []
    for t in fw.get("themes", []):
        controls = []
        for c in t.get("controls", []):
            evidence = [
                DslEvidence(construct=e["construct"], description=e["description"])
                for e in c.get("dsl_evidence", [])
            ]
            controls.append(
                Control(
                    id=c["id"],
                    name=c["name"],
                    objective=c.get("objective", ""),
                    attributes=c.get("attributes", {}),
                    dsl_evidence=evidence,
                )
            )
        themes.append(Theme(id=t["id"], name=t["name"], controls=controls))

    return Taxonomy(
        id=fw["id"],
        name=fw["name"],
        jurisdiction=fw.get("jurisdiction", ""),
        body=fw.get("body", ""),
        version=fw.get("version", ""),
        themes=themes,
    )
