"""MCP handler for feedback widget operations.

Provides list/get/summarise/triage/resolve operations for the human->agent
feedback loop. Calls the server's CRUD endpoints via the shared
``feedback_impl`` module, which targets the local ``dazzle serve`` or, with
``DAZZLE_FEEDBACK_URL`` / ``DAZZLE_FEEDBACK_COOKIE`` set, a deployed app.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from dazzle.cli import feedback_impl

from .common import extract_progress


def list_handler(project_root: Path, args: dict[str, Any]) -> str:
    """List feedback reports with optional filters (grouped by review_session when present)."""
    progress = extract_progress(args)
    progress.log_sync("Listing feedback reports...")

    result = asyncio.run(
        feedback_impl.feedback_list(
            project_root,
            status=args.get("status"),
            category=args.get("category"),
            severity=args.get("severity"),
            limit=int(args.get("limit", 20)),
            since=args.get("since"),
            surface=args.get("surface"),
            review_session=args.get("review_session"),
            page_url=args.get("page_url"),
        )
    )
    return json.dumps(result, indent=2)


def get_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get a single feedback report by ID."""
    progress = extract_progress(args)
    report_id = args.get("id", "")
    if not report_id:
        return json.dumps({"error": "id is required"})

    progress.log_sync(f"Fetching feedback report {report_id[:8]}...")
    result = asyncio.run(feedback_impl.feedback_get(report_id, project_root))
    return json.dumps(result, indent=2)


def summarise_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Summarise open notes grouped by surface then severity."""
    progress = extract_progress(args)
    progress.log_sync("Summarising feedback reports...")

    result = asyncio.run(
        feedback_impl.feedback_summarise(
            project_root,
            status=args.get("status") or "new,triaged",
            since=args.get("since"),
            limit=int(args.get("limit", 200)),
        )
    )
    return json.dumps(result, indent=2)


def triage_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Triage a feedback report (new -> triaged)."""
    progress = extract_progress(args)
    report_id = args.get("id", "")
    if not report_id:
        return json.dumps({"error": "id is required"})

    progress.log_sync(f"Triaging feedback report {report_id[:8]}...")
    result = asyncio.run(
        feedback_impl.feedback_triage(
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
    progress = extract_progress(args)
    report_id = args.get("id", "")
    if not report_id:
        return json.dumps({"error": "id is required"})

    progress.log_sync(f"Resolving feedback report {report_id[:8]}...")
    result = asyncio.run(
        feedback_impl.feedback_resolve(
            report_id,
            project_root,
            agent_notes=args.get("agent_notes"),
            resolved_by=args.get("resolved_by"),
        )
    )
    return json.dumps(result, indent=2)
