"""MCP handler for felt product / demo quality (#1626).

Read-only (ADR-0002). Aggregates structural maturity probes, persona-home
seed residual, and empty-hero still floors into one OBSERVE payload.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dazzle.mcp.server.handlers.common import wrap_handler_errors
from dazzle.product_quality import score_project, score_status_lines


@wrap_handler_errors
def product_quality_score_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Score product/demo quality for a project or examples fleet.

    Args:
        project_path: resolved MCP project (cwd / active / project_path).
        args: {
            "app": optional showcase app name when scoring examples/,
            "project_root": optional override path (app or examples/),
            "min_home_hits": min seed hits per current_user region (default 1),
        }
    """
    explicit = args.get("project_root")
    root = Path(explicit) if explicit else project_path
    app = args.get("app")
    min_hits = int(args.get("min_home_hits") or 1)

    report = score_project(root, app=app, min_home_hits=min_hits)
    payload = report.to_dict()
    payload["status_lines"] = score_status_lines(report)
    return json.dumps(payload, indent=2)
