"""Composition analysis MCP handler.

Provides visual hierarchy auditing via the ``composition`` MCP tool.

Operations:
- ``audit`` — deterministic sitespec-based composition analysis
- ``capture`` — Playwright section-level screenshot pipeline
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


def capture_composition_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Capture section-level screenshots from a running Dazzle app.

    Requires a ``base_url`` pointing to the running app.  Uses Playwright
    to navigate pages, locate ``.dz-section-{type}`` elements, and take
    clipped screenshots of each section.
    """
    from dataclasses import asdict

    from dazzle.core.composition_capture import capture_page_sections
    from dazzle.core.sitespec_loader import load_sitespec_with_copy

    base_url: str | None = args.get("base_url")
    if not base_url:
        return json.dumps(
            {"error": "base_url is required for capture (e.g. http://localhost:3000)"}
        )

    routes_filter: list[str] | None = args.get("pages")
    viewports: list[str] | None = args.get("viewports")
    output_dir = project_path / ".dazzle" / "composition" / "captures"

    try:
        sitespec = load_sitespec_with_copy(project_path, use_defaults=True)

        if not sitespec.pages:
            return json.dumps({"captures": [], "summary": "No pages to capture"})

        captures = capture_page_sections(
            base_url,
            sitespec,
            output_dir=output_dir,
            viewports=viewports,
            routes_filter=routes_filter,
        )

        captures_data = [asdict(c) for c in captures]
        total_sections = sum(len(c.sections) for c in captures)
        total_tokens = sum(c.total_tokens_est for c in captures)

        return json.dumps(
            {
                "captures": captures_data,
                "total_sections": total_sections,
                "total_tokens_est": total_tokens,
                "output_dir": str(output_dir),
                "summary": (
                    f"Captured {total_sections} sections across "
                    f"{len(captures)} page/viewport combinations "
                    f"(~{total_tokens:,} tokens)"
                ),
            },
            indent=2,
        )
    except ImportError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.exception("Composition capture failed")
        return json.dumps({"error": str(e)})
