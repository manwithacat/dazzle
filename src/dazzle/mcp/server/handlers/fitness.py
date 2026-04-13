"""MCP handler for the fitness triage queue.

Read-only per ADR-0002. Regeneration happens via CLI
(`dazzle fitness triage`); this handler only parses the existing
fitness-queue.md and returns its contents as JSON.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from dazzle.fitness.triage import read_queue_file
from dazzle.mcp.server.handlers.common import wrap_handler_errors

_HEADER_RAW_RE = re.compile(r"^\*\*Raw findings:\*\*\s*(\d+)", re.MULTILINE)


def _parse_raw_findings(queue_file: Path) -> int:
    """Extract the 'Raw findings' count from the queue file header."""
    try:
        text = queue_file.read_text()
    except OSError:
        return 0
    m = _HEADER_RAW_RE.search(text)
    return int(m.group(1)) if m else 0


@wrap_handler_errors
def fitness_queue_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Return the ranked fitness queue for a project as JSON.

    Args:
        project_path: unused in this handler (MCP passes cwd)
        args: {
            "project_root": path to the example app,
            "top": max clusters to return (default 10),
        }
    """
    explicit = args.get("project_root")
    if not explicit:
        return json.dumps(
            {
                "error": "project_root is required",
                "project_root": None,
            },
            indent=2,
        )
    project_root = Path(explicit)
    queue_file = project_root / "dev_docs" / "fitness-queue.md"

    if not queue_file.exists():
        return json.dumps(
            {
                "error": "no fitness queue — run 'dazzle fitness triage' first",
                "project_root": str(project_root),
            },
            indent=2,
        )

    clusters = read_queue_file(queue_file)
    top = int(args.get("top", 10))
    shown = clusters[:top]
    raw_findings = _parse_raw_findings(queue_file)

    payload = {
        "project": project_root.name,
        "queue_file": str(queue_file),
        "raw_findings": raw_findings,
        "clusters_total": len(clusters),
        "clusters": [
            {
                "rank": i + 1,
                "cluster_id": c.cluster_id,
                "severity": c.severity,
                "locus": c.locus,
                "axis": c.axis,
                "persona": c.persona,
                "cluster_size": c.cluster_size,
                "summary": c.canonical_summary,
                "first_seen": c.first_seen.isoformat(),
                "last_seen": c.last_seen.isoformat(),
                "sample_id": c.sample_id,
            }
            for i, c in enumerate(shown)
        ],
    }
    return json.dumps(payload, indent=2)
