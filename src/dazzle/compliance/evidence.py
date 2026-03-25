"""Extract compliance evidence from AppSpec IR.

Walks the typed AppSpec to find DSL constructs that evidence compliance
controls. Each construct type has a dedicated extractor function (~10 lines).

Usage:
    evidence = extract_evidence(appspec)          # from parsed IR
    evidence = extract_evidence_from_project(path) # convenience wrapper
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from dazzle.compliance.models import EvidenceItem, EvidenceMap

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec


def extract_evidence(appspec: AppSpec) -> EvidenceMap:
    """Walk AppSpec IR and extract compliance evidence.

    Returns an EvidenceMap with items keyed by raw construct name.
    """
    items: dict[str, list[EvidenceItem]] = {
        "classify": _extract_classify(appspec),
        "permit": _extract_permit(appspec),
        "scope": _extract_scope(appspec),
        "visible": _extract_visible(appspec),
        "transitions": _extract_transitions(appspec),
        "process": _extract_processes(appspec),
        "persona": _extract_personas(appspec),
        "story": _extract_stories(appspec),
        "grant_schema": _extract_grant_schemas(appspec),
        "llm_intent": _extract_llm_intents(appspec),
        "sla": _extract_slas(appspec),
        "schedule": _extract_schedules(appspec),
        "archetype": _extract_archetypes(appspec),
    }
    return EvidenceMap(items=items)


def extract_evidence_from_project(project_root: Path) -> EvidenceMap:
    """Convenience wrapper: parse DSL -> AppSpec -> extract evidence."""
    from dazzle.cli.utils import load_project_appspec

    appspec = load_project_appspec(project_root)
    evidence = extract_evidence(appspec)

    # Compute DSL hash over all files
    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.manifest import load_manifest

    manifest_path = project_root / "dazzle.toml"
    if manifest_path.exists():
        manifest = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(project_root, manifest)
        content = "".join(f.read_text() for f in sorted(dsl_files))
        evidence.dsl_hash = f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"

    return evidence


# ---------------------------------------------------------------------------
# Per-construct extractors
# ---------------------------------------------------------------------------


def _extract_classify(appspec: AppSpec) -> list[EvidenceItem]:
    if not appspec.policies:
        return []
    classifications = appspec.policies.classifications
    if not classifications:
        return []
    return [
        EvidenceItem(
            entity=c.entity,
            construct="classify",
            detail=f"{c.classification} on {c.entity}.{c.field}",
            dsl_ref=f"{c.entity}.classify",
        )
        for c in classifications
    ]


def _extract_permit(appspec: AppSpec) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for entity in appspec.domain.entities:
        if not entity.access:
            continue
        for perm in entity.access.permissions:
            items.append(
                EvidenceItem(
                    entity=entity.name,
                    construct="permit",
                    detail=f"{perm.operation}: {perm.condition}",
                    dsl_ref=f"{entity.name}.permit",
                )
            )
    return items


def _extract_scope(appspec: AppSpec) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for entity in appspec.domain.entities:
        if not entity.access:
            continue
        for scope in entity.access.scopes:
            items.append(
                EvidenceItem(
                    entity=entity.name,
                    construct="scope",
                    detail=f"{scope.operation}: {scope.condition}",
                    dsl_ref=f"{entity.name}.scope",
                )
            )
    return items


def _extract_visible(appspec: AppSpec) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for entity in appspec.domain.entities:
        if not entity.access:
            continue
        for vis in entity.access.visibility:
            items.append(
                EvidenceItem(
                    entity=entity.name,
                    construct="visible",
                    detail=f"{vis.context}: {vis.condition}",
                    dsl_ref=f"{entity.name}.visible",
                )
            )
    return items


def _extract_transitions(appspec: AppSpec) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for entity in appspec.domain.entities:
        if not entity.state_machine:
            continue
        for t in entity.state_machine.transitions:
            items.append(
                EvidenceItem(
                    entity=entity.name,
                    construct="transitions",
                    detail=f"{t.from_state} -> {t.to_state}",
                    dsl_ref=f"{entity.name}.transitions",
                )
            )
    return items


def _extract_processes(appspec: AppSpec) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            entity=p.name,
            construct="process",
            detail=f"{p.title or p.name} ({len(p.steps)} steps)",
            dsl_ref=f"{p.name}.process",
        )
        for p in appspec.processes
    ]


def _extract_personas(appspec: AppSpec) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            entity=p.id,
            construct="persona",
            detail=getattr(p, "name", None) or p.id,
            dsl_ref=f"{p.id}.persona",
        )
        for p in appspec.personas
    ]


def _extract_stories(appspec: AppSpec) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            entity=s.story_id,
            construct="story",
            detail=f"{s.title or s.story_id} (actor: {s.actor})",
            dsl_ref=f"{s.story_id}.story",
        )
        for s in appspec.stories
    ]


def _extract_grant_schemas(appspec: AppSpec) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            entity=g.scope if hasattr(g, "scope") else g.name,
            construct="grant_schema",
            detail=f"grant_schema on {g.scope if hasattr(g, 'scope') else g.name}",
            dsl_ref=f"{g.scope if hasattr(g, 'scope') else g.name}.grant_schema",
        )
        for g in appspec.grant_schemas
    ]


def _extract_llm_intents(appspec: AppSpec) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            entity=intent.name,
            construct="llm_intent",
            detail=f"{intent.title or intent.name}",
            dsl_ref=f"{intent.name}.llm_intent",
        )
        for intent in appspec.llm_intents
    ]


def _extract_slas(appspec: AppSpec) -> list[EvidenceItem]:
    """Extract evidence from SLA definitions."""
    return [
        EvidenceItem(
            entity=sla.entity or sla.name,
            construct="sla",
            detail=f"SLA '{sla.name}' with {len(sla.tiers)} tier(s)"
            + (f" on entity {sla.entity}" if sla.entity else ""),
            dsl_ref=f"{sla.name}.sla",
        )
        for sla in (appspec.slas or [])
    ]


def _extract_schedules(appspec: AppSpec) -> list[EvidenceItem]:
    """Extract evidence from schedule definitions."""
    return [
        EvidenceItem(
            entity=s.name,
            construct="schedule",
            detail=f"Schedule '{s.name}'"
            + (f" (cron: {s.cron})" if s.cron else "")
            + (f" implements {', '.join(s.implements)}" if s.implements else ""),
            dsl_ref=f"{s.name}.schedule",
        )
        for s in (appspec.schedules or [])
    ]


def _extract_archetypes(appspec: AppSpec) -> list[EvidenceItem]:
    """Extract evidence from archetype definitions."""
    return [
        EvidenceItem(
            entity=a.name,
            construct="archetype",
            detail=f"Archetype '{a.name}' with {len(a.fields)} field(s)"
            + (f", {len(a.invariants)} invariant(s)" if a.invariants else ""),
            dsl_ref=f"{a.name}.archetype",
        )
        for a in (appspec.archetypes or [])
    ]
