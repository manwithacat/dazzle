"""Composition analysis MCP handler.

Provides deterministic visual hierarchy auditing via the ``composition``
MCP tool.  Phase 1 implements the ``audit`` operation which evaluates
sitespec structure against composition rules (attention weights, ratio,
ordering, balance, minimum thresholds).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def audit_composition_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Run deterministic composition audit from sitespec structure.

    Derives section elements from SiteSpec, computes attention weights,
    and evaluates composition rules.  Returns scored JSON report.
    """
    from dazzle.core.composition import run_composition_audit
    from dazzle.core.sitespec_loader import load_sitespec_with_copy

    routes_filter: list[str] | None = args.get("pages")

    try:
        sitespec = load_sitespec_with_copy(project_path, use_defaults=True)

        if not sitespec.pages:
            return json.dumps(
                {
                    "pages": [],
                    "overall_score": 100,
                    "summary": "No pages defined in sitespec",
                    "markdown": "# Composition Audit\n\nNo pages to audit.",
                }
            )

        result = run_composition_audit(sitespec, routes_filter=routes_filter)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.exception("Composition audit failed")
        return json.dumps({"error": str(e)})
