"""All Pydantic models for the compliance compiler.

Single import point for agents consuming the module. Contains:
- Taxonomy types (framework structure)
- Evidence types (DSL evidence extracted from AppSpec)
- AuditSpec types (compiler output)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# =============================================================================
# Taxonomy Types (loaded from framework YAML files)
# =============================================================================


class DslEvidence(BaseModel):
    """Maps a DSL construct to a compliance control."""

    construct: str  # type: ignore[assignment]  # shadows deprecated BaseModel.construct
    description: str = ""


class Control(BaseModel):
    """A single compliance framework control (e.g. ISO 27001 A.5.1)."""

    id: str
    name: str
    objective: str = ""
    dsl_evidence: list[DslEvidence] = Field(default_factory=list)
    attributes: dict[str, list[str]] = Field(default_factory=dict)
    cross_references: list[str] = Field(default_factory=list)  # e.g. ["iso27001:A.8.3"]


class Theme(BaseModel):
    """A group of related controls (e.g. 'Organisational Controls')."""

    id: str
    name: str
    controls: list[Control]
    mandatory: bool = True  # SOC 2: Security is mandatory, others optional
    applicability: str = ""  # conditions for applicability (e.g. "when processing financial data")


class Taxonomy(BaseModel):
    """A complete compliance framework taxonomy."""

    id: str
    name: str
    version: str = ""
    jurisdiction: str = ""
    body: str = ""  # standards body (e.g. "ISO")
    related_frameworks: list[str] = Field(default_factory=list)  # e.g. ["soc2", "iso27001"]
    themes: list[Theme]

    def all_controls(self) -> list[Control]:
        """Flat list of all controls across all themes."""
        return [c for t in self.themes for c in t.controls]

    def controls_by_id(self) -> dict[str, Control]:
        """Map control ID to Control for O(1) lookup."""
        return {c.id: c for t in self.themes for c in t.controls}


# =============================================================================
# Evidence Types (extracted from AppSpec IR)
# =============================================================================


class EvidenceItem(BaseModel):
    """A single piece of compliance evidence found in the DSL."""

    entity: str  # which entity/persona/process this was found on
    construct: str  # type: ignore[assignment]  # shadows deprecated BaseModel.construct
    detail: str  # human-readable summary
    dsl_ref: str  # "EntityName.construct" for citation validation


class EvidenceMap(BaseModel):
    """All evidence extracted from an AppSpec.

    Keys in ``items`` use raw DSL construct names (classify, permit, scope,
    visible, transitions, process, persona, story, grant_schema, llm_intent).
    The CONSTRUCT_TO_KEY mapping in compiler.py maps these to taxonomy
    categories when matching against control dsl_evidence entries.
    """

    items: dict[str, list[EvidenceItem]] = Field(default_factory=dict)
    dsl_hash: str = ""


# =============================================================================
# AuditSpec Types (compiler output)
# =============================================================================


class AuditSummary(BaseModel):
    """Summary counts for an audit spec."""

    total_controls: int = 0
    evidenced: int = 0
    partial: int = 0
    gaps: int = 0
    excluded: int = 0


class ControlResult(BaseModel):
    """Assessment result for a single compliance control."""

    control_id: str
    control_name: str
    theme_id: str
    status: Literal["evidenced", "partial", "gap", "excluded"]
    tier: int  # evidenced=1, partial=2, gap=3, excluded=0
    evidence: list[EvidenceItem] = Field(default_factory=list)
    gap_description: str = ""
    action: str = ""  # recommended action for gaps


class AuditSpec(BaseModel):
    """Complete audit specification — the central IR of the compliance pipeline."""

    framework_id: str
    framework_name: str
    framework_version: str = ""
    generated_at: str
    dsl_hash: str
    dsl_source: str = ""  # project root path for provenance
    controls: list[ControlResult] = Field(default_factory=list)
    summary: AuditSummary = Field(default_factory=AuditSummary)
