"""MCP handler for feedback widget operations.

Provides list/get/triage/resolve operations for the human->agent feedback loop.
Calls the running server's CRUD endpoints via the shared feedback_impl module.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from .common import extract_progress


def list_handler(project_root: Path, args: dict[str, Any]) -> str:
    """List feedback reports with optional filters."""
    from dazzle.cli.feedback_impl import feedback_list

    progress = extract_progress(args)
    progress.log_sync("Listing feedback reports...")

    result = asyncio.run(
        feedback_list(
            project_root,
            status=args.get("status"),
            category=args.get("category"),
            severity=args.get("severity"),
            limit=int(args.get("limit", 20)),
        )
    )
    return json.dumps(result, indent=2)


def get_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get a single feedback report by ID."""
    from dazzle.cli.feedback_impl import feedback_get

    progress = extract_progress(args)
    report_id = args.get("id", "")
    if not report_id:
        return json.dumps({"error": "id is required"})

    progress.log_sync(f"Fetching feedback report {report_id[:8]}...")
    result = asyncio.run(feedback_get(report_id, project_root))
    return json.dumps(result, indent=2)


def triage_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Triage a feedback report (new -> triaged)."""
    from dazzle.cli.feedback_impl import feedback_triage

    progress = extract_progress(args)
    report_id = args.get("id", "")
    if not report_id:
        return json.dumps({"error": "id is required"})

    progress.log_sync(f"Triaging feedback report {report_id[:8]}...")
    result = asyncio.run(
        feedback_triage(
            report_id,
            project_root,
            agent_notes=args.get("agent_notes"),
            agent_classification=args.get("agent_classification"),
            assigned_to=args.get("assigned_to"),
        )
    )
    return json.dumps(result, indent=2)


def resolve_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Resolve a feedback report (triaged/in_progress -> resolved)."""
    from dazzle.cli.feedback_impl import feedback_resolve

    progress = extract_progress(args)
    report_id = args.get("id", "")
    if not report_id:
        return json.dumps({"error": "id is required"})

    progress.log_sync(f"Resolving feedback report {report_id[:8]}...")
    result = asyncio.run(
        feedback_resolve(
            report_id,
            project_root,
            agent_notes=args.get("agent_notes"),
            resolved_by=args.get("resolved_by"),
        )
    )
    return json.dumps(result, indent=2)
