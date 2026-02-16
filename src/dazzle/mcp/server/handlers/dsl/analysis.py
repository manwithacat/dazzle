"""DSL pattern analysis and frontend spec export handlers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.core.patterns import detect_crud_patterns, detect_integration_patterns

from ..common import extract_progress, load_project_appspec, wrap_handler_errors

logger = logging.getLogger(__name__)


@wrap_handler_errors
def analyze_patterns(project_root: Path, args: dict[str, Any] | None = None) -> str:
    """Analyze the project for patterns."""
    progress = extract_progress(args)
    progress.log_sync("Loading project DSL...")
    app_spec = load_project_appspec(project_root)

    progress.log_sync("Detecting CRUD patterns...")
    crud_patterns = detect_crud_patterns(app_spec)
    progress.log_sync("Detecting integration patterns...")
    integration_patterns = detect_integration_patterns(app_spec)

    crud_list = [
        {
            "entity": p.entity_name,
            "has_create": p.has_create,
            "has_list": p.has_list,
            "has_detail": p.has_detail,
            "has_edit": p.has_edit,
            "is_complete": p.is_complete,
            "missing_operations": p.missing_operations,
            "is_system_managed": p.is_system_managed,
        }
        for p in crud_patterns
    ]
    result: dict[str, Any] = {
        "crud_patterns": crud_list,
        "integration_patterns": [
            {
                "name": p.integration_name,
                "service": p.service_name,
                "has_actions": p.has_actions,
                "has_syncs": p.has_syncs,
                "action_count": p.action_count,
                "sync_count": p.sync_count,
                "connected_entities": list(p.connected_entities or []),
                "connected_surfaces": list(p.connected_surfaces or []),
            }
            for p in integration_patterns
        ],
    }

    has_incomplete = any(not c["is_complete"] for c in crud_list)
    if has_incomplete:
        result["discovery_hint"] = (
            "Some entities have incomplete CRUD coverage. "
            "Use discovery(operation='run', mode='entity_completeness') "
            "for detailed gap analysis with targeted verification."
        )

    return json.dumps(result, indent=2)


@wrap_handler_errors
def export_frontend_spec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Export a framework-agnostic frontend specification from DSL."""
    progress = extract_progress(args)
    progress.log_sync("Loading project DSL...")
    app_spec = load_project_appspec(project_root)

    # Load sitespec (optional)
    progress.log_sync("Loading sitespec...")
    sitespec = None
    try:
        from dazzle.core.sitespec_loader import load_sitespec

        sitespec = load_sitespec(project_root, use_defaults=True)
    except Exception:
        logger.debug("Optional sitespec not available", exc_info=True)

    # Load stories (optional)
    progress.log_sync("Loading stories...")
    stories = []
    try:
        from dazzle.core.stories_persistence import load_stories

        stories = load_stories(project_root)
    except Exception:
        logger.debug("Optional stories not available", exc_info=True)

    # Load test designs (optional)
    progress.log_sync("Loading test designs...")
    test_designs = []
    try:
        from dazzle.testing.test_design_persistence import load_test_designs

        test_designs = load_test_designs(project_root)
    except Exception:
        logger.debug("Optional test designs not available", exc_info=True)

    from dazzle.core.frontend_spec_export import export_frontend_spec

    fmt = args.get("format", "markdown")
    sections = args.get("sections")
    entities = args.get("entities")

    progress.log_sync("Exporting frontend spec...")
    return export_frontend_spec(app_spec, sitespec, stories, test_designs, fmt, sections, entities)
