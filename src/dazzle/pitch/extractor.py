"""
PitchSpec extractor - merges DSL-extracted data with PitchSpec.

Reads AppSpec from DSL files and populates PitchContext with
both user-specified PitchSpec content and auto-extracted DSL data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ir import PitchSpec

logger = logging.getLogger(__name__)


@dataclass
class PitchContext:
    """Merged view of PitchSpec + DSL-extracted data for generators."""

    spec: PitchSpec
    # Project root for plugin discovery:
    project_root: Path | None = None
    # Chart image paths (populated by generators):
    chart_paths: dict[str, Path] = field(default_factory=dict)
    # DSL-extracted (auto-populated):
    app_name: str | None = None
    entities: list[str] = field(default_factory=list)
    surfaces: list[str] = field(default_factory=list)
    personas: list[dict[str, str]] = field(default_factory=list)
    workspaces: list[dict[str, str]] = field(default_factory=list)
    state_machines: list[dict[str, str]] = field(default_factory=list)
    story_count: int = 0
    integrations: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    ledger_count: int = 0
    process_count: int = 0
    e2e_flow_count: int = 0
    infra_summary: dict[str, Any] = field(default_factory=dict)


def extract_pitch_context(project_root: Path, spec: PitchSpec) -> PitchContext:
    """Extract DSL data and merge with PitchSpec into a PitchContext.

    Loads the DSL manifest, parses files, builds AppSpec, and extracts
    entity names, surface names, persona info, workspace info, and story count.

    DSL extraction is additive: it populates fields the user didn't set
    in PitchSpec, but never overwrites explicit values.

    Args:
        project_root: Root directory of the DAZZLE project.
        spec: User-provided PitchSpec.

    Returns:
        PitchContext with both PitchSpec and DSL data.
    """
    ctx = PitchContext(spec=spec)

    try:
        from dazzle.core.fileset import discover_dsl_files
        from dazzle.core.linker import build_appspec
        from dazzle.core.manifest import load_manifest
        from dazzle.core.parser import parse_modules

        manifest_path = project_root / "dazzle.toml"
        if not manifest_path.exists():
            logger.debug("No dazzle.toml found, skipping DSL extraction")
            return ctx

        manifest = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, manifest.project_root)

        # Extract app name
        ctx.app_name = appspec.title or appspec.name

        # Extract entities
        ctx.entities = [e.name for e in appspec.domain.entities]

        # Extract surfaces
        ctx.surfaces = [s.name for s in appspec.surfaces]

        # Extract personas
        ctx.personas = [
            {
                "id": p.id,
                "label": p.label or p.id,
                "description": p.description or "",
            }
            for p in appspec.personas
        ]

        # Extract workspaces
        ctx.workspaces = [
            {
                "name": w.name,
                "title": w.title or w.name,
                "purpose": w.purpose or "",
            }
            for w in appspec.workspaces
        ]

        # Extract state machines
        for entity in appspec.domain.entities:
            if entity.state_machine:
                ctx.state_machines.append(
                    {
                        "entity": entity.name,
                        "field": entity.state_machine.status_field,
                        "states": str(len(entity.state_machine.states)),
                        "transitions": str(len(entity.state_machine.transitions)),
                    }
                )

        # Count stories
        try:
            from dazzle.core.stories_persistence import load_stories

            stories = load_stories(project_root)
            ctx.story_count = len(stories)
        except Exception:
            pass

        # Extract integrations
        try:
            ctx.integrations = [i.name for i in appspec.domain.integrations]
        except Exception:
            pass

        # Extract services
        try:
            ctx.services = [s.name for s in appspec.domain_services]
        except Exception:
            pass

        # Count ledgers (TigerBeetle)
        try:
            ctx.ledger_count = len(appspec.domain.ledgers)
        except Exception:
            pass

        # Count processes
        try:
            ctx.process_count = len(appspec.processes)
        except Exception:
            pass

        # Count E2E test flows
        try:
            from dazzle.testing.e2e_flow_persistence import load_e2e_flows

            flows = load_e2e_flows(project_root)
            ctx.e2e_flow_count = len(flows)
        except Exception:
            pass

        # Infrastructure summary
        try:
            from dazzle.core.infra import analyze_infra_requirements

            ctx.infra_summary = analyze_infra_requirements(appspec)
        except Exception:
            pass

        logger.info(
            f"Extracted DSL context: {len(ctx.entities)} entities, "
            f"{len(ctx.surfaces)} surfaces, {len(ctx.personas)} personas"
        )

    except Exception as e:
        logger.warning(f"Could not extract DSL data: {e}")

    return ctx
