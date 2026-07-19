"""Domain gaps — what blocks safe promote to DSL."""

from __future__ import annotations

from dataclasses import dataclass, field

from dazzle.domain_brief.models import AgentDomain, DomainDesk, DomainPersona


@dataclass
class DomainGap:
    code: str
    severity: str  # error | warn
    message: str


@dataclass
class GapsReport:
    ready_to_promote: bool
    gaps: list[DomainGap] = field(default_factory=list)
    grounded_nouns: int = 0
    personas: int = 0
    desks: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "ready_to_promote": self.ready_to_promote,
            "grounded_nouns": self.grounded_nouns,
            "personas": self.personas,
            "desks": self.desks,
            "gaps": [
                {"code": g.code, "severity": g.severity, "message": g.message} for g in self.gaps
            ],
        }


def _persona_gaps(personas: list[DomainPersona], desks: list[DomainDesk]) -> list[DomainGap]:
    gaps: list[DomainGap] = []
    if not personas:
        gaps.append(
            DomainGap("no_personas", "error", "Need ≥1 persona with a job desk before DSL.")
        )
    if not desks and personas:
        gaps.append(
            DomainGap(
                "no_desks",
                "error",
                "Personas lack desks — declare a job desk per persona.",
            )
        )
    for p in personas:
        if not p.desk:
            gaps.append(DomainGap("persona_no_desk", "error", f"Persona {p.label} has no desk."))
    for d in desks:
        if not d.owner_field_hint:
            gaps.append(
                DomainGap(
                    "desk_no_owner",
                    "warn",
                    f"Desk {d.name} missing owner_field_hint (current_user bind).",
                )
            )
    return gaps


def score_gaps(domain: AgentDomain) -> GapsReport:
    gaps: list[DomainGap] = []
    grounded = [n for n in domain.nouns if n.status == "grounded"]
    gaps.extend(_persona_gaps(domain.personas, domain.desks))
    if not grounded:
        gaps.append(
            DomainGap(
                "no_grounded_nouns",
                "error",
                "Need ≥1 domain noun grounded in founder brief.",
            )
        )
    if domain.personas and not domain.demo_spine:
        gaps.append(
            DomainGap(
                "no_demo_spine",
                "warn",
                "No demo spine — seed stories prevent empty-desk theater.",
            )
        )
    for q in domain.open_questions:
        if q.blocks_promote:
            gaps.append(
                DomainGap(
                    "open_question",
                    "error",
                    f"Open question blocks promote ({q.id}): {q.text[:120]}",
                )
            )
    if domain.rejected_chrome:
        gaps.append(
            DomainGap(
                "chrome_rejected",
                "warn",
                f"Rejected chrome: {', '.join(domain.rejected_chrome[:12])}",
            )
        )

    errors = [g for g in gaps if g.severity == "error"]
    return GapsReport(
        ready_to_promote=len(errors) == 0 and bool(domain.personas) and bool(grounded),
        gaps=gaps,
        grounded_nouns=len(grounded),
        personas=len(domain.personas),
        desks=len(domain.desks),
    )
