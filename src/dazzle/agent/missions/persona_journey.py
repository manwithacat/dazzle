"""
Headless persona journey analysis: static DSL/KG analysis of persona journey completeness.

Answers "can each persona accomplish their stories through the surfaces and workspaces
defined in the DSL?" using deterministic static analysis — no running app needed.

Output feeds the existing compile→emit pipeline via Observation conversion, so findings
can become DSL proposals automatically.

Analysis passes (per persona):
1. Workspace reachability — persona has a valid, accessible workspace with regions
2. Surface access — surfaces accessible per access control rules
3. Story surface coverage — story-implied CRUD has matching accessible surfaces
4. Process surface wiring — human_task steps reference existing, accessible surfaces
5. Experience completeness — experience steps/transitions are valid and accessible
6. Dead-end detection — surfaces with no outgoing navigation edges
7. Cross-entity gaps — multi-entity stories have connected navigation paths
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..compiler import infer_crud_action
from ..transcript import Observation
from ._shared import get_surface_entity, is_step_kind

logger = logging.getLogger("dazzle.agent.missions.persona_journey")


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class PersonaJourneyGap:
    """A gap in a persona's journey through the application."""

    persona_id: str
    gap_type: str
    severity: str
    description: str
    entity_name: str | None = None
    surface_name: str | None = None
    story_id: str | None = None
    process_name: str | None = None
    experience_name: str | None = None
    related_artefacts: list[str] = field(default_factory=list)


@dataclass
class PersonaJourneyReport:
    """Results of persona journey analysis for a single persona."""

    persona_id: str
    gaps: list[PersonaJourneyGap] = field(default_factory=list)
    surface_coverage: dict[str, bool] = field(default_factory=dict)
    story_coverage: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class HeadlessDiscoveryReport:
    """Complete headless discovery report across all personas."""

    persona_reports: list[PersonaJourneyReport] = field(default_factory=list)
    entity_report: Any | None = None  # EntityCompletenessReport
    workflow_report: Any | None = None  # WorkflowCoherenceReport

    def to_observations(self) -> list[Observation]:
        """Convert all gaps to pipeline-compatible Observations."""
        observations: list[Observation] = []
        for pr in self.persona_reports:
            for gap in pr.gaps:
                observations.append(_gap_to_observation(gap))
        return observations

    def to_json(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        result: dict[str, Any] = {
            "persona_reports": [],
        }
        for pr in self.persona_reports:
            pr_dict: dict[str, Any] = {
                "persona_id": pr.persona_id,
                "gaps": [
                    {
                        "persona_id": g.persona_id,
                        "gap_type": g.gap_type,
                        "severity": g.severity,
                        "description": g.description,
                        "entity_name": g.entity_name,
                        "surface_name": g.surface_name,
                        "story_id": g.story_id,
                        "process_name": g.process_name,
                        "experience_name": g.experience_name,
                        "related_artefacts": g.related_artefacts,
                    }
                    for g in pr.gaps
                ],
                "surface_coverage": pr.surface_coverage,
                "story_coverage": pr.story_coverage,
            }
            result["persona_reports"].append(pr_dict)

        if self.entity_report is not None:
            result["entity_summary"] = self.entity_report.to_summary()
        if self.workflow_report is not None:
            result["workflow_summary"] = self.workflow_report.to_summary()

        return result

    def to_summary(self) -> str:
        """Render a markdown summary."""
        lines: list[str] = ["# Headless Discovery Report\n"]

        total_gaps = sum(len(pr.gaps) for pr in self.persona_reports)
        lines.append(
            f"**{len(self.persona_reports)}** persona(s) analyzed, **{total_gaps}** gap(s) found.\n"
        )

        for pr in self.persona_reports:
            lines.append(f"## Persona: {pr.persona_id}\n")
            if not pr.gaps:
                lines.append("No gaps found.\n")
                continue
            for gap in pr.gaps:
                lines.append(f"- [{gap.severity.upper()}] **{gap.gap_type}**: {gap.description}")
            lines.append("")

        if self.entity_report is not None:
            lines.append("## Entity Completeness\n")
            lines.append(self.entity_report.to_summary())
            lines.append("")

        if self.workflow_report is not None:
            lines.append("## Workflow Coherence\n")
            lines.append(self.workflow_report.to_summary())
            lines.append("")

        return "\n".join(lines)


# =============================================================================
# Gap → Observation Mapping
# =============================================================================

_GAP_TYPE_TO_CATEGORY: dict[str, str] = {
    "workspace_unreachable": "navigation_gap",
    "surface_inaccessible": "access_gap",
    "story_no_surface": "missing_crud",
    "process_step_no_surface": "workflow_gap",
    "experience_broken_step": "workflow_gap",
    "experience_dangling_transition": "navigation_gap",
    "dead_end_surface": "navigation_gap",
    "cross_entity_gap": "navigation_gap",
}


def _gap_to_observation(gap: PersonaJourneyGap) -> Observation:
    """Convert a PersonaJourneyGap to a pipeline-compatible Observation."""
    category = _GAP_TYPE_TO_CATEGORY.get(gap.gap_type, "gap")
    return Observation(
        category=category,
        severity=gap.severity,
        title=f"[{gap.persona_id}] {gap.gap_type}: {gap.description[:80]}",
        description=gap.description,
        location=gap.surface_name or gap.experience_name or "",
        related_artefacts=gap.related_artefacts,
        metadata={"headless": True, "gap_type": gap.gap_type, "persona_id": gap.persona_id},
    )


# =============================================================================
# Shared Helpers
# =============================================================================


def _compute_accessible_surfaces(persona_id: str, appspec: Any) -> set[str]:
    """
    Compute the set of surface names accessible to a persona.

    Access rules:
    - No access spec → accessible
    - allow_personas empty and persona not in deny_personas → accessible
    - allow_personas contains persona_id → accessible
    - Otherwise → inaccessible
    """
    surfaces = getattr(appspec, "surfaces", []) or []
    accessible: set[str] = set()

    for surface in surfaces:
        access = getattr(surface, "access", None)
        if access is None:
            accessible.add(surface.name)
            continue

        allow = getattr(access, "allow_personas", None) or []
        deny = getattr(access, "deny_personas", None) or []

        if persona_id in deny:
            continue

        if not allow or persona_id in allow:
            accessible.add(surface.name)

    return accessible


def _get_persona_stories(persona_id: str, appspec: Any) -> list[Any]:
    """Get stories where this persona is the actor."""
    stories = getattr(appspec, "stories", []) or []
    return [s for s in stories if getattr(s, "actor", None) == persona_id]


def _get_story_entities(story: Any) -> list[str]:
    """Extract entity names from a story's scope."""
    scope = getattr(story, "scope", None)
    if not scope:
        return []
    if isinstance(scope, list):
        return [str(s) for s in scope]
    if isinstance(scope, str):
        return [scope]
    return []


def _get_surfaces_for_entity(entity_name: str, appspec: Any) -> list[Any]:
    """Get all surfaces that reference a given entity."""
    surfaces = getattr(appspec, "surfaces", []) or []
    return [s for s in surfaces if get_surface_entity(s) == entity_name]


# =============================================================================
# Analysis Pass 1: Workspace Reachability
# =============================================================================


def _analyze_workspace_reachability(
    persona_id: str,
    persona: Any,
    appspec: Any,
) -> list[PersonaJourneyGap]:
    """Check that persona has a valid, accessible workspace with regions."""
    gaps: list[PersonaJourneyGap] = []
    workspaces = getattr(appspec, "workspaces", []) or []
    workspace_map = {ws.name: ws for ws in workspaces}

    default_ws = getattr(persona, "default_workspace", None)
    if not default_ws:
        gaps.append(
            PersonaJourneyGap(
                persona_id=persona_id,
                gap_type="workspace_unreachable",
                severity="medium",
                description=f"Persona '{persona_id}' has no default_workspace",
            )
        )
        return gaps

    ws = workspace_map.get(default_ws)
    if not ws:
        gaps.append(
            PersonaJourneyGap(
                persona_id=persona_id,
                gap_type="workspace_unreachable",
                severity="critical",
                description=f"Persona '{persona_id}' default_workspace '{default_ws}' does not exist in appspec",
                related_artefacts=[f"workspace:{default_ws}"],
            )
        )
        return gaps

    # Check workspace access control
    ws_access = getattr(ws, "access", None)
    if ws_access:
        allow = getattr(ws_access, "allow_personas", None) or []
        deny = getattr(ws_access, "deny_personas", None) or []
        if persona_id in deny or (allow and persona_id not in allow):
            gaps.append(
                PersonaJourneyGap(
                    persona_id=persona_id,
                    gap_type="workspace_unreachable",
                    severity="high",
                    description=f"Persona '{persona_id}' denied access to workspace '{default_ws}'",
                    related_artefacts=[f"workspace:{default_ws}"],
                )
            )

    # Check workspace has regions
    regions = getattr(ws, "regions", []) or []
    if not regions:
        gaps.append(
            PersonaJourneyGap(
                persona_id=persona_id,
                gap_type="workspace_unreachable",
                severity="medium",
                description=f"Workspace '{default_ws}' has no regions",
                related_artefacts=[f"workspace:{default_ws}"],
            )
        )

    return gaps


# =============================================================================
# Analysis Pass 2: Surface Access
# =============================================================================


def _analyze_surface_access(
    persona_id: str,
    persona: Any,
    appspec: Any,
    accessible_surfaces: set[str],
) -> list[PersonaJourneyGap]:
    """Flag surfaces that reference entities in persona's stories but are inaccessible."""
    gaps: list[PersonaJourneyGap] = []

    # Get entities from persona's stories
    stories = _get_persona_stories(persona_id, appspec)
    story_entity_names: set[str] = set()
    for story in stories:
        story_entity_names.update(_get_story_entities(story))

    # Check surfaces for those entities
    for entity_name in story_entity_names:
        entity_surfaces = _get_surfaces_for_entity(entity_name, appspec)
        for surface in entity_surfaces:
            if surface.name not in accessible_surfaces:
                gaps.append(
                    PersonaJourneyGap(
                        persona_id=persona_id,
                        gap_type="surface_inaccessible",
                        severity="high",
                        description=(
                            f"Surface '{surface.name}' for entity '{entity_name}' "
                            f"is not accessible to persona '{persona_id}'"
                        ),
                        entity_name=entity_name,
                        surface_name=surface.name,
                        related_artefacts=[f"entity:{entity_name}", f"surface:{surface.name}"],
                    )
                )

    return gaps


# =============================================================================
# Analysis Pass 3: Story Surface Coverage
# =============================================================================


def _analyze_story_surface_coverage(
    persona_id: str,
    persona: Any,
    appspec: Any,
    accessible_surfaces: set[str],
) -> list[PersonaJourneyGap]:
    """Check that stories have accessible surfaces for their implied CRUD operations."""
    gaps: list[PersonaJourneyGap] = []
    stories = _get_persona_stories(persona_id, appspec)

    for story in stories:
        story_id = getattr(story, "story_id", None) or getattr(story, "id", "unknown")
        entity_names = _get_story_entities(story)

        # Infer CRUD action from story conditions/title
        story_text = " ".join(
            filter(
                None,
                [
                    getattr(story, "title", ""),
                    getattr(story, "description", ""),
                    " ".join(getattr(story, "conditions", []) or []),
                ],
            )
        )
        implied_action = infer_crud_action(story_text)

        for entity_name in entity_names:
            entity_surfaces = _get_surfaces_for_entity(entity_name, appspec)
            accessible_entity_surfaces = [
                s for s in entity_surfaces if s.name in accessible_surfaces
            ]

            # Check if the implied CRUD action has a matching surface mode
            if implied_action != "CRUD":
                # Map action to expected surface mode
                action_to_mode = {
                    "create": "create",
                    "edit": "edit",
                    "delete": "edit",  # delete typically via edit or list
                    "list": "list",
                    "view": "view",
                }
                expected_mode = action_to_mode.get(implied_action)
                if expected_mode:
                    has_mode = any(
                        str(getattr(s, "mode", "")) == expected_mode
                        for s in accessible_entity_surfaces
                    )
                    if not has_mode:
                        gaps.append(
                            PersonaJourneyGap(
                                persona_id=persona_id,
                                gap_type="story_no_surface",
                                severity="high",
                                description=(
                                    f"Story '{story_id}' implies '{implied_action}' on '{entity_name}' "
                                    f"but no accessible '{expected_mode}' surface exists"
                                ),
                                entity_name=entity_name,
                                story_id=story_id,
                                related_artefacts=[f"entity:{entity_name}", f"story:{story_id}"],
                            )
                        )
            else:
                # Generic CRUD — check entity has at least one accessible surface
                if not accessible_entity_surfaces:
                    gaps.append(
                        PersonaJourneyGap(
                            persona_id=persona_id,
                            gap_type="story_no_surface",
                            severity="high",
                            description=(
                                f"Story '{story_id}' references entity '{entity_name}' "
                                f"but no accessible surfaces exist"
                            ),
                            entity_name=entity_name,
                            story_id=story_id,
                            related_artefacts=[f"entity:{entity_name}", f"story:{story_id}"],
                        )
                    )

    return gaps


# =============================================================================
# Analysis Pass 4: Process Surface Wiring
# =============================================================================


def _analyze_process_surface_wiring(
    persona_id: str,
    persona: Any,
    appspec: Any,
    accessible_surfaces: set[str],
) -> list[PersonaJourneyGap]:
    """Check that process human_task steps reference existing, accessible surfaces."""
    gaps: list[PersonaJourneyGap] = []
    processes = getattr(appspec, "processes", []) or []
    surfaces = getattr(appspec, "surfaces", []) or []
    surface_names = {s.name for s in surfaces}

    # Get persona's story IDs
    persona_story_ids: set[str] = set()
    for story in _get_persona_stories(persona_id, appspec):
        sid = getattr(story, "story_id", None) or getattr(story, "id", None)
        if sid:
            persona_story_ids.add(sid)

    for proc in processes:
        implements = set(getattr(proc, "implements", []) or [])
        if not implements.intersection(persona_story_ids):
            continue

        for step in getattr(proc, "steps", []):
            if not is_step_kind(step, "human_task"):
                continue
            human_task = getattr(step, "human_task", None)
            if not human_task:
                continue
            surface_ref = getattr(human_task, "surface", None)
            if not surface_ref:
                continue

            if surface_ref not in surface_names:
                gaps.append(
                    PersonaJourneyGap(
                        persona_id=persona_id,
                        gap_type="process_step_no_surface",
                        severity="critical",
                        description=(
                            f"Process '{proc.name}' step '{step.name}' references "
                            f"surface '{surface_ref}' which does not exist"
                        ),
                        surface_name=surface_ref,
                        process_name=proc.name,
                        related_artefacts=[f"process:{proc.name}", f"surface:{surface_ref}"],
                    )
                )
            elif surface_ref not in accessible_surfaces:
                gaps.append(
                    PersonaJourneyGap(
                        persona_id=persona_id,
                        gap_type="process_step_no_surface",
                        severity="high",
                        description=(
                            f"Process '{proc.name}' step '{step.name}' references "
                            f"surface '{surface_ref}' which is not accessible to persona '{persona_id}'"
                        ),
                        surface_name=surface_ref,
                        process_name=proc.name,
                        related_artefacts=[f"process:{proc.name}", f"surface:{surface_ref}"],
                    )
                )

    return gaps


# =============================================================================
# Analysis Pass 5: Experience Completeness
# =============================================================================


def _analyze_experience_completeness(
    persona_id: str,
    persona: Any,
    appspec: Any,
    accessible_surfaces: set[str],
) -> list[PersonaJourneyGap]:
    """Check experience steps and transitions for validity and accessibility."""
    gaps: list[PersonaJourneyGap] = []
    experiences = getattr(appspec, "experiences", []) or []
    surfaces = getattr(appspec, "surfaces", []) or []
    surface_names = {s.name for s in surfaces}

    # Get entities from persona's stories
    story_entity_names: set[str] = set()
    for story in _get_persona_stories(persona_id, appspec):
        story_entity_names.update(_get_story_entities(story))

    for exp in experiences:
        # Check if this experience references surfaces for persona's entities
        exp_steps = getattr(exp, "steps", []) or []
        exp_surfaces: set[str] = set()
        for step in exp_steps:
            step_kind = str(getattr(step, "kind", ""))
            if step_kind == "surface" or step_kind == "StepKind.SURFACE":
                surface_ref = getattr(step, "surface", None)
                if surface_ref:
                    exp_surfaces.add(surface_ref)

        # Check if any experience surface is for persona's entities
        relevant = False
        for s_name in exp_surfaces:
            for s in surfaces:
                if s.name == s_name and get_surface_entity(s) in story_entity_names:
                    relevant = True
                    break
            if relevant:
                break

        if not relevant:
            continue

        # Build step name set for transition validation
        step_names = {getattr(s, "name", "") for s in exp_steps}

        # Check start_step
        start_step = getattr(exp, "start_step", None)
        if start_step and start_step not in step_names:
            gaps.append(
                PersonaJourneyGap(
                    persona_id=persona_id,
                    gap_type="experience_broken_step",
                    severity="critical",
                    description=(
                        f"Experience '{exp.name}' start_step '{start_step}' "
                        f"does not reference a valid step"
                    ),
                    experience_name=exp.name,
                    related_artefacts=[f"experience:{exp.name}"],
                )
            )

        # Check each step
        for step in exp_steps:
            step_kind = str(getattr(step, "kind", ""))
            if step_kind == "surface" or step_kind == "StepKind.SURFACE":
                surface_ref = getattr(step, "surface", None)
                step_name = getattr(step, "name", "unknown")
                if surface_ref and surface_ref not in surface_names:
                    gaps.append(
                        PersonaJourneyGap(
                            persona_id=persona_id,
                            gap_type="experience_broken_step",
                            severity="critical",
                            description=(
                                f"Experience '{exp.name}' step '{step_name}' references "
                                f"surface '{surface_ref}' which does not exist"
                            ),
                            surface_name=surface_ref,
                            experience_name=exp.name,
                            related_artefacts=[f"experience:{exp.name}", f"surface:{surface_ref}"],
                        )
                    )
                elif surface_ref and surface_ref not in accessible_surfaces:
                    gaps.append(
                        PersonaJourneyGap(
                            persona_id=persona_id,
                            gap_type="experience_broken_step",
                            severity="high",
                            description=(
                                f"Experience '{exp.name}' step '{step_name}' references "
                                f"surface '{surface_ref}' not accessible to '{persona_id}'"
                            ),
                            surface_name=surface_ref,
                            experience_name=exp.name,
                            related_artefacts=[f"experience:{exp.name}", f"surface:{surface_ref}"],
                        )
                    )

            # Check transitions
            transitions = getattr(step, "transitions", []) or []
            for transition in transitions:
                next_step = getattr(transition, "next_step", None)
                if next_step and next_step not in step_names:
                    gaps.append(
                        PersonaJourneyGap(
                            persona_id=persona_id,
                            gap_type="experience_dangling_transition",
                            severity="medium",
                            description=(
                                f"Experience '{exp.name}' step '{getattr(step, 'name', '?')}' "
                                f"transitions to '{next_step}' which does not exist"
                            ),
                            experience_name=exp.name,
                            related_artefacts=[f"experience:{exp.name}"],
                        )
                    )

        # Check for orphan steps (unreachable from start)
        if start_step and start_step in step_names:
            reachable = _find_reachable_steps(start_step, exp_steps)
            for step in exp_steps:
                sn = getattr(step, "name", "")
                if sn and sn not in reachable:
                    gaps.append(
                        PersonaJourneyGap(
                            persona_id=persona_id,
                            gap_type="experience_dangling_transition",
                            severity="medium",
                            description=(
                                f"Experience '{exp.name}' step '{sn}' is unreachable "
                                f"from start_step '{start_step}'"
                            ),
                            experience_name=exp.name,
                            related_artefacts=[f"experience:{exp.name}"],
                        )
                    )

    return gaps


def _find_reachable_steps(start: str, steps: list[Any]) -> set[str]:
    """BFS from start step, following transitions."""
    step_map: dict[str, Any] = {}
    for s in steps:
        sn = getattr(s, "name", "")
        if sn:
            step_map[sn] = s

    visited: set[str] = set()
    queue = [start]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        step = step_map.get(current)
        if not step:
            continue
        for t in getattr(step, "transitions", []) or []:
            ns = getattr(t, "next_step", None)
            if ns and ns not in visited:
                queue.append(ns)

    return visited


# =============================================================================
# Analysis Pass 6: Dead-End Detection
# =============================================================================


def _analyze_dead_ends(
    persona_id: str,
    persona: Any,
    appspec: Any,
    accessible_surfaces: set[str],
) -> list[PersonaJourneyGap]:
    """Flag accessible surfaces with no outgoing navigation edges."""
    gaps: list[PersonaJourneyGap] = []
    surfaces = getattr(appspec, "surfaces", []) or []
    workspaces = getattr(appspec, "workspaces", []) or []
    experiences = getattr(appspec, "experiences", []) or []

    # Build navigation graph: surface_name → set of reachable surface names
    nav_graph: dict[str, set[str]] = {s.name: set() for s in surfaces}

    # Workspace regions: surfaces in the same workspace region can reach each other
    for ws in workspaces:
        for region in getattr(ws, "regions", []) or []:
            region_surfaces = getattr(region, "surfaces", []) or []
            # Normalize: could be strings or objects
            region_surface_names = []
            for rs in region_surfaces:
                if isinstance(rs, str):
                    region_surface_names.append(rs)
                else:
                    region_surface_names.append(getattr(rs, "name", str(rs)))

            # All surfaces in a region can navigate to each other
            for s1 in region_surface_names:
                for s2 in region_surface_names:
                    if s1 != s2 and s1 in nav_graph:
                        nav_graph[s1].add(s2)

    # Experience transitions add navigation edges
    for exp in experiences:
        for step in getattr(exp, "steps", []) or []:
            step_kind = str(getattr(step, "kind", ""))
            if step_kind in ("surface", "StepKind.SURFACE"):
                source_surface = getattr(step, "surface", None)
                if source_surface and source_surface in nav_graph:
                    for t in getattr(step, "transitions", []) or []:
                        ns = getattr(t, "next_step", None)
                        # Find next step's surface
                        if ns:
                            for other_step in getattr(exp, "steps", []) or []:
                                if getattr(other_step, "name", "") == ns:
                                    target_surface = getattr(other_step, "surface", None)
                                    if target_surface:
                                        nav_graph[source_surface].add(target_surface)

    # Surface actions can also imply navigation
    for surface in surfaces:
        for action in getattr(surface, "actions", []) or []:
            target = getattr(action, "navigate_to", None) or getattr(action, "target", None)
            if target and target in nav_graph and surface.name in nav_graph:
                nav_graph[surface.name].add(target)

    # Flag accessible surfaces with no outgoing edges (except list surfaces)
    for surface in surfaces:
        if surface.name not in accessible_surfaces:
            continue
        mode = str(getattr(surface, "mode", ""))
        # List surfaces are acceptable endpoints
        if mode == "list":
            continue
        if surface.name in nav_graph and not nav_graph[surface.name]:
            gaps.append(
                PersonaJourneyGap(
                    persona_id=persona_id,
                    gap_type="dead_end_surface",
                    severity="low",
                    description=f"Surface '{surface.name}' (mode: {mode}) has no outgoing navigation",
                    surface_name=surface.name,
                    related_artefacts=[f"surface:{surface.name}"],
                )
            )

    return gaps


# =============================================================================
# Analysis Pass 7: Cross-Entity Gaps
# =============================================================================


def _analyze_cross_entity_gaps(
    persona_id: str,
    persona: Any,
    appspec: Any,
    accessible_surfaces: set[str],
    kg_store: Any | None = None,
) -> list[PersonaJourneyGap]:
    """Check that multi-entity stories have connected navigation paths."""
    gaps: list[PersonaJourneyGap] = []
    stories = _get_persona_stories(persona_id, appspec)
    workspaces = getattr(appspec, "workspaces", []) or []
    surfaces = getattr(appspec, "surfaces", []) or []

    # Build entity → workspace map
    entity_workspaces: dict[str, set[str]] = {}
    for ws in workspaces:
        for region in getattr(ws, "regions", []) or []:
            region_surfaces = getattr(region, "surfaces", []) or []
            for rs in region_surfaces:
                rs_name = rs if isinstance(rs, str) else getattr(rs, "name", str(rs))
                # Find entity for this surface
                for s in surfaces:
                    if s.name == rs_name:
                        ent = get_surface_entity(s)
                        if ent:
                            entity_workspaces.setdefault(ent, set()).add(ws.name)

    for story in stories:
        entity_names = _get_story_entities(story)
        if len(entity_names) < 2:
            continue

        story_id = getattr(story, "story_id", None) or getattr(story, "id", "unknown")

        # Check each pair of entities shares a workspace or has KG adjacency
        for i, e1 in enumerate(entity_names):
            for e2 in entity_names[i + 1 :]:
                ws1 = entity_workspaces.get(e1, set())
                ws2 = entity_workspaces.get(e2, set())

                if ws1 & ws2:
                    continue  # Shared workspace — OK

                # Try KG adjacency as fallback
                if kg_store:
                    try:
                        adj = kg_store.compute_adjacency(f"entity:{e1}", f"entity:{e2}")
                        if adj and adj.get("distance", 999) <= 2:
                            continue
                    except Exception:
                        pass

                gaps.append(
                    PersonaJourneyGap(
                        persona_id=persona_id,
                        gap_type="cross_entity_gap",
                        severity="medium",
                        description=(
                            f"Story '{story_id}' spans entities '{e1}' and '{e2}' "
                            f"but they share no workspace or navigation path"
                        ),
                        story_id=story_id,
                        related_artefacts=[f"entity:{e1}", f"entity:{e2}", f"story:{story_id}"],
                    )
                )

    return gaps


# =============================================================================
# Entry Point
# =============================================================================


def run_headless_discovery(
    appspec: Any,
    persona_ids: list[str] | None = None,
    kg_store: Any | None = None,
    include_entity_analysis: bool = True,
    include_workflow_analysis: bool = True,
) -> HeadlessDiscoveryReport:
    """
    Run headless persona journey analysis on a DSL spec.

    Pure static analysis — no running app needed. Checks whether each persona
    can accomplish their stories through the surfaces and workspaces in the DSL.

    Args:
        appspec: Parsed AppSpec from the DSL
        persona_ids: Specific persona IDs to analyze (None = all)
        kg_store: Optional KnowledgeGraphStore for adjacency checks
        include_entity_analysis: Include entity completeness analysis
        include_workflow_analysis: Include workflow coherence analysis

    Returns:
        HeadlessDiscoveryReport with per-persona gaps and optional sub-reports
    """
    report = HeadlessDiscoveryReport()

    personas = getattr(appspec, "personas", []) or []
    if persona_ids:
        id_set = set(persona_ids)
        personas = [p for p in personas if _persona_id(p) in id_set]

    for persona in personas:
        pid = _persona_id(persona)
        accessible = _compute_accessible_surfaces(pid, appspec)

        pr = PersonaJourneyReport(persona_id=pid)

        # Record surface coverage
        for surface in getattr(appspec, "surfaces", []) or []:
            pr.surface_coverage[surface.name] = surface.name in accessible

        # Record story coverage
        for story in _get_persona_stories(pid, appspec):
            sid: str = getattr(story, "story_id", None) or getattr(story, "id", None) or "unknown"
            entities = _get_story_entities(story)
            missing_surfaces: list[str] = []
            for ent in entities:
                ent_surfaces = _get_surfaces_for_entity(ent, appspec)
                accessible_ent = [s for s in ent_surfaces if s.name in accessible]
                if not accessible_ent:
                    missing_surfaces.append(ent)
            pr.story_coverage[sid] = {
                "covered": len(missing_surfaces) == 0,
                "missing_surfaces": missing_surfaces,
            }

        # Run all 7 analysis passes
        pr.gaps.extend(_analyze_workspace_reachability(pid, persona, appspec))
        pr.gaps.extend(_analyze_surface_access(pid, persona, appspec, accessible))
        pr.gaps.extend(_analyze_story_surface_coverage(pid, persona, appspec, accessible))
        pr.gaps.extend(_analyze_process_surface_wiring(pid, persona, appspec, accessible))
        pr.gaps.extend(_analyze_experience_completeness(pid, persona, appspec, accessible))
        pr.gaps.extend(_analyze_dead_ends(pid, persona, appspec, accessible))
        pr.gaps.extend(_analyze_cross_entity_gaps(pid, persona, appspec, accessible, kg_store))

        report.persona_reports.append(pr)

    # Optional sub-analyses
    if include_entity_analysis:
        try:
            from .entity_completeness import _static_entity_analysis

            report.entity_report = _static_entity_analysis(appspec)
        except Exception as e:
            logger.warning(f"Entity analysis failed: {e}")

    if include_workflow_analysis:
        try:
            from .workflow_coherence import _static_workflow_analysis

            report.workflow_report = _static_workflow_analysis(appspec)
        except Exception as e:
            logger.warning(f"Workflow analysis failed: {e}")

    return report


def _persona_id(persona: Any) -> str:
    """Extract persona ID, handling both .id and .name attributes."""
    return str(getattr(persona, "id", None) or getattr(persona, "name", None) or "unknown")
