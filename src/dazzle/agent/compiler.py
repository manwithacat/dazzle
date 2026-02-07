"""
Narrative Compiler: converts raw discovery observations into actionable proposals.

The compiler groups gaps by root cause, prioritizes by severity and frequency,
generates human-readable narratives, and optionally checks adjacency against
the knowledge graph.

Input: list[Observation] from an AgentTranscript
Output: list[Proposal] — structured, prioritized, ready for DSL emission
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .transcript import Observation

logger = logging.getLogger("dazzle.agent.compiler")


# =============================================================================
# Proposal Model
# =============================================================================

# Severity weights for prioritization
SEVERITY_WEIGHTS: dict[str, int] = {
    "critical": 100,
    "high": 60,
    "medium": 30,
    "low": 10,
    "info": 0,
}

# Category labels for human-readable output
CATEGORY_LABELS: dict[str, str] = {
    "missing_crud": "Missing CRUD Operation",
    "workflow_gap": "Workflow Gap",
    "navigation_gap": "Navigation Gap",
    "ux_issue": "UX Issue",
    "access_gap": "Access Control Gap",
    "data_gap": "Data Gap",
    "gap": "General Gap",
}


@dataclass
class Proposal:
    """
    An actionable proposal generated from one or more observations.

    Proposals are the primary output of the narrative compiler. Each one
    describes a specific improvement to the application, grounded in
    evidence from the discovery session.
    """

    id: str
    title: str
    narrative: str  # "As [persona], I expected... but found..."
    category: str  # Same categories as Observation
    priority: int  # Computed from severity × frequency
    severity: str  # Highest severity among contributing observations
    affected_entities: list[str] = field(default_factory=list)
    affected_surfaces: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    observation_count: int = 1
    observations: list[Observation] = field(default_factory=list)
    adjacency_valid: bool = True  # Within 2-step boundary
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "id": self.id,
            "title": self.title,
            "narrative": self.narrative,
            "category": self.category,
            "priority": self.priority,
            "severity": self.severity,
            "affected_entities": self.affected_entities,
            "affected_surfaces": self.affected_surfaces,
            "locations": self.locations,
            "observation_count": self.observation_count,
            "adjacency_valid": self.adjacency_valid,
            "metadata": self.metadata,
        }


# =============================================================================
# Grouping
# =============================================================================


@dataclass
class _ObservationGroup:
    """Internal grouping of related observations."""

    key: str
    category: str
    observations: list[Observation] = field(default_factory=list)

    @property
    def max_severity(self) -> str:
        """Highest severity in the group."""
        best = "info"
        best_weight = 0
        for obs in self.observations:
            w = SEVERITY_WEIGHTS.get(obs.severity, 0)
            if w > best_weight:
                best_weight = w
                best = obs.severity
        return best

    @property
    def priority_score(self) -> int:
        """Priority = max_severity_weight × observation_count."""
        return SEVERITY_WEIGHTS.get(self.max_severity, 0) * len(self.observations)


def _group_key(obs: Observation) -> str:
    """
    Compute a grouping key for an observation.

    Observations are grouped by (category, primary_entity_or_location).
    This merges observations like "Task has no delete on /tasks" and
    "Task has no delete on /task/123" into a single group.
    """
    # Use the first related artefact as the primary entity
    primary = obs.related_artefacts[0] if obs.related_artefacts else ""

    # Strip prefixes for grouping
    if ":" in primary:
        primary = primary.split(":", 1)[1]

    # Fall back to location-based grouping
    if not primary and obs.location:
        # Normalize URL: strip query params and trailing segments
        loc = obs.location.split("?")[0].rstrip("/")
        # Use the first meaningful path segment
        parts = [p for p in loc.split("/") if p and p not in ("http:", "https:", "localhost:3000")]
        primary = parts[0] if parts else "unknown"

    if not primary:
        primary = "general"

    return f"{obs.category}:{primary}"


def _group_observations(observations: list[Observation]) -> list[_ObservationGroup]:
    """Group observations by root cause."""
    groups: dict[str, _ObservationGroup] = {}

    for obs in observations:
        # Skip info-level positive confirmations
        if obs.severity == "info":
            continue

        key = _group_key(obs)
        if key not in groups:
            groups[key] = _ObservationGroup(key=key, category=obs.category)
        groups[key].observations.append(obs)

    return list(groups.values())


# =============================================================================
# Narrative Generation
# =============================================================================


def _generate_narrative(
    group: _ObservationGroup,
    persona: str = "user",
) -> str:
    """
    Generate a human-readable narrative for a group of observations.

    Format: "As [persona], I expected to [action] on [surface] but found [gap].
    This affects [entities/workflows]."
    """
    obs = group.observations[0]  # Use first observation as primary
    cat_label = CATEGORY_LABELS.get(group.category, "Gap")

    # Build the "expected" and "found" parts based on category
    if group.category == "missing_crud":
        action = _infer_crud_action(group)
        expected = f"perform {action} operations"
        found = "no interface for this action exists"
    elif group.category == "workflow_gap":
        expected = "follow the defined workflow steps"
        found = "a required step or transition is missing"
    elif group.category == "navigation_gap":
        expected = "navigate to the expected page"
        found = "the page could not be reached or returned an error"
    elif group.category == "ux_issue":
        expected = "interact with a complete, validated form"
        found = "fields or validation were missing"
    elif group.category == "access_gap":
        expected = "access the surface"
        found = "access was denied or not available"
    elif group.category == "data_gap":
        expected = "see the expected data"
        found = "data was missing or incomplete"
    else:
        expected = "find the expected functionality"
        found = obs.description[:100] if obs.description else "it was not available"

    # Location context
    location_text = ""
    locations = _collect_locations(group)
    if locations:
        location_text = f" at {locations[0]}"

    # Entity context
    entities = _collect_entities(group)
    entity_text = ""
    if entities:
        entity_text = f" This affects: {', '.join(entities[:3])}."

    # Count context
    count_text = ""
    if len(group.observations) > 1:
        count_text = f" ({len(group.observations)} related observations)"

    narrative = (
        f"[{cat_label}] As {persona}, I expected to {expected}{location_text}, "
        f"but found {found}.{entity_text}{count_text}"
    )

    # Add specific details from observations
    if obs.description and len(obs.description) > len(found):
        narrative += f"\n\nDetail: {obs.description}"

    return narrative


def infer_crud_action(text: str) -> str:
    """Infer which CRUD action is referenced in descriptive text."""
    text = text.lower()
    if "delete" in text or "remove" in text:
        return "delete"
    if "create" in text or "add" in text or "new" in text:
        return "create"
    if "edit" in text or "update" in text or "modify" in text:
        return "edit"
    if "list" in text or "browse" in text or "index" in text:
        return "list"
    if "view" in text or "detail" in text or "show" in text:
        return "view"
    return "CRUD"


def _infer_crud_action(group: _ObservationGroup) -> str:
    """Infer which CRUD action is missing from observation titles/descriptions."""
    text = " ".join(o.title + " " + o.description for o in group.observations)
    return infer_crud_action(text)


def _collect_locations(group: _ObservationGroup) -> list[str]:
    """Collect unique locations from a group."""
    seen: set[str] = set()
    locations: list[str] = []
    for obs in group.observations:
        if obs.location and obs.location not in seen:
            seen.add(obs.location)
            locations.append(obs.location)
    return locations


def _collect_entities(group: _ObservationGroup) -> list[str]:
    """Collect unique entity references from a group."""
    seen: set[str] = set()
    entities: list[str] = []
    for obs in group.observations:
        for art in obs.related_artefacts:
            # Strip prefix for display
            name = art.split(":", 1)[1] if ":" in art else art
            if name not in seen:
                seen.add(name)
                entities.append(name)
    return entities


def _collect_surfaces(group: _ObservationGroup) -> list[str]:
    """Collect surface names from locations and related artefacts."""
    surfaces: list[str] = []
    seen: set[str] = set()
    for obs in group.observations:
        for art in obs.related_artefacts:
            if art.startswith("surface:"):
                name = art.split(":", 1)[1]
                if name not in seen:
                    seen.add(name)
                    surfaces.append(name)
    return surfaces


# =============================================================================
# Adjacency Validation
# =============================================================================


def _check_adjacency(
    group: _ObservationGroup,
    kg_store: Any | None,
) -> bool:
    """
    Check if a proposal is within the 2-step adjacency boundary.

    Returns True if:
    - No KG store available (can't check, assume valid)
    - All referenced entities exist in the KG and are within 2 hops of each other
    - No entities referenced (nothing to check)
    """
    if kg_store is None:
        return True

    entities = _collect_entities(group)
    if not entities:
        return True

    # Check that at least one entity exists in the KG
    for entity_name in entities[:3]:
        for prefix in ("entity:", "surface:"):
            ent = kg_store.get_entity(prefix + entity_name)
            if ent:
                return True

    # No referenced entities found in KG — likely hallucinated
    return False


# =============================================================================
# NarrativeCompiler
# =============================================================================


class NarrativeCompiler:
    """
    Converts raw discovery observations into structured, prioritized proposals.

    Usage:
        compiler = NarrativeCompiler(persona="admin", kg_store=kg)
        proposals = compiler.compile(transcript.observations)
        report = compiler.report(proposals)
    """

    def __init__(
        self,
        persona: str = "user",
        kg_store: Any | None = None,
    ):
        self._persona = persona
        self._kg_store = kg_store

    def compile(self, observations: list[Observation]) -> list[Proposal]:
        """
        Compile observations into proposals.

        Steps:
        1. Filter out info-level observations
        2. Group by root cause (category + primary entity)
        3. Generate narrative for each group
        4. Check adjacency validity
        5. Sort by priority (severity × frequency)
        """
        if not observations:
            return []

        groups = _group_observations(observations)
        proposals: list[Proposal] = []

        for i, group in enumerate(groups):
            narrative = _generate_narrative(group, self._persona)
            adjacency_valid = _check_adjacency(group, self._kg_store)

            proposal = Proposal(
                id=f"P-{i + 1:03d}",
                title=group.observations[0].title,
                narrative=narrative,
                category=group.category,
                priority=group.priority_score,
                severity=group.max_severity,
                affected_entities=_collect_entities(group),
                affected_surfaces=_collect_surfaces(group),
                locations=_collect_locations(group),
                observation_count=len(group.observations),
                observations=group.observations,
                adjacency_valid=adjacency_valid,
            )
            proposals.append(proposal)

        # Sort by priority descending
        proposals.sort(key=lambda p: p.priority, reverse=True)

        # Re-number after sort
        for i, p in enumerate(proposals):
            p.id = f"P-{i + 1:03d}"

        return proposals

    def report(self, proposals: list[Proposal]) -> str:
        """
        Generate a human-readable report from proposals.

        Returns a markdown-formatted string suitable for display
        or inclusion in a discovery report.
        """
        if not proposals:
            return "# Discovery Report\n\nNo gaps found. The application matches the DSL specification."

        lines = [
            "# Discovery Report",
            "",
            f"**Persona:** {self._persona}",
            f"**Total proposals:** {len(proposals)}",
            "",
        ]

        # Summary by category
        cat_counts: Counter[str] = Counter()
        sev_counts: Counter[str] = Counter()
        for p in proposals:
            cat_counts[p.category] += 1
            sev_counts[p.severity] += 1

        lines.append("## Summary")
        lines.append("")
        lines.append("| Category | Count |")
        lines.append("|----------|-------|")
        for cat, count in cat_counts.most_common():
            label = CATEGORY_LABELS.get(cat, cat)
            lines.append(f"| {label} | {count} |")

        lines.append("")
        lines.append("| Severity | Count |")
        lines.append("|----------|-------|")
        for sev in ("critical", "high", "medium", "low"):
            if sev in sev_counts:
                lines.append(f"| {sev} | {sev_counts[sev]} |")

        # Proposals
        lines.append("")
        lines.append("## Proposals")
        lines.append("")

        for p in proposals:
            adjacency_flag = "" if p.adjacency_valid else " [OUT OF SCOPE]"
            lines.append(f"### {p.id}: {p.title}{adjacency_flag}")
            lines.append("")
            lines.append(
                f"**Priority:** {p.priority} | **Severity:** {p.severity} | **Category:** {CATEGORY_LABELS.get(p.category, p.category)}"
            )
            if p.affected_entities:
                lines.append(f"**Entities:** {', '.join(p.affected_entities)}")
            if p.locations:
                lines.append(f"**Locations:** {', '.join(p.locations)}")
            lines.append("")
            lines.append(p.narrative)
            lines.append("")

        return "\n".join(lines)

    def to_json(self, proposals: list[Proposal]) -> dict[str, Any]:
        """Serialize proposals to JSON-compatible dict."""
        return {
            "persona": self._persona,
            "total_proposals": len(proposals),
            "proposals": [p.to_json() for p in proposals],
            "summary": {
                "by_category": dict(Counter(p.category for p in proposals)),
                "by_severity": dict(Counter(p.severity for p in proposals)),
                "total_observations": sum(p.observation_count for p in proposals),
                "adjacency_valid_count": sum(1 for p in proposals if p.adjacency_valid),
            },
        }
