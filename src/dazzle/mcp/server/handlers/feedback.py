"""
MCP handlers for feedback management.

Provides tools for LLM agents to ingest, review, and manage user feedback
submitted via the Dazzle Bar feedback button.

Feedback is stored in:
- .dazzle/feedback/feedback.jsonl (structured, for LLM ingestion)
- .dazzle/feedback/feedback.md (human-readable)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..state import get_project_path


def _get_feedback_logger() -> Any:
    """Get a FeedbackLogger instance for the active project."""
    from dazzle_dnr_back.runtime.control_plane import FeedbackLogger

    project_path = get_project_path()
    if not project_path:
        raise ValueError("No active project. Select a project first.")

    feedback_dir = project_path / ".dazzle" / "feedback"
    return FeedbackLogger(feedback_dir=feedback_dir)


async def list_feedback_handler(
    status: str | None = None,
    category: str | None = None,
    limit: int = 20,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    List feedback entries from the Dazzle Bar.

    Use this tool to see what feedback users have submitted. Feedback is
    captured when users click the Feedback button in the Dazzle Bar.

    Args:
        status: Filter by status - "new", "acknowledged", "addressed", "wont_fix"
        category: Filter by category (e.g., "Bug Report", "Feature Request")
        limit: Maximum entries to return (default: 20)
        project_path: Optional project path override

    Returns:
        List of feedback entries with id, timestamp, message, category, route, status
    """
    if project_path:
        from dazzle_dnr_back.runtime.control_plane import FeedbackLogger

        feedback_dir = Path(project_path) / ".dazzle" / "feedback"
        logger = FeedbackLogger(feedback_dir=feedback_dir)
    else:
        logger = _get_feedback_logger()

    entries = logger.list_feedback(status=status, category=category, limit=limit)

    return {
        "count": len(entries),
        "entries": [entry.model_dump() for entry in entries],
        "filters": {
            "status": status,
            "category": category,
            "limit": limit,
        },
    }


async def get_feedback_handler(
    feedback_id: str,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Get a specific feedback entry by ID.

    Use this to get full details of a feedback item including extra context
    like viewport size, user agent, and any additional metadata.

    Args:
        feedback_id: The 8-character feedback ID (e.g., "a1b2c3d4")
        project_path: Optional project path override

    Returns:
        Full feedback entry with all fields
    """
    if project_path:
        from dazzle_dnr_back.runtime.control_plane import FeedbackLogger

        feedback_dir = Path(project_path) / ".dazzle" / "feedback"
        logger = FeedbackLogger(feedback_dir=feedback_dir)
    else:
        logger = _get_feedback_logger()

    entry = logger.get_feedback(feedback_id)

    if not entry:
        return {"error": f"Feedback '{feedback_id}' not found"}

    return {"feedback": entry.model_dump()}


async def update_feedback_handler(
    feedback_id: str,
    status: str,
    notes: str | None = None,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Update the status of a feedback entry.

    Use this to track feedback as it's being addressed. Status flow:
    - "new" -> "acknowledged" (you've seen it)
    - "acknowledged" -> "addressed" (you've fixed/implemented it)
    - OR -> "wont_fix" (decided not to address)

    Args:
        feedback_id: The 8-character feedback ID
        status: New status - "acknowledged", "addressed", or "wont_fix"
        notes: Optional notes about the resolution
        project_path: Optional project path override

    Returns:
        Success/failure status
    """
    valid_statuses = {"new", "acknowledged", "addressed", "wont_fix"}
    if status not in valid_statuses:
        return {"error": f"Invalid status. Must be one of: {valid_statuses}"}

    if project_path:
        from dazzle_dnr_back.runtime.control_plane import FeedbackLogger

        feedback_dir = Path(project_path) / ".dazzle" / "feedback"
        logger = FeedbackLogger(feedback_dir=feedback_dir)
    else:
        logger = _get_feedback_logger()

    success = logger.update_feedback_status(feedback_id, status, notes)

    if not success:
        return {"error": f"Feedback '{feedback_id}' not found"}

    return {
        "status": "updated",
        "feedback_id": feedback_id,
        "new_status": status,
        "notes": notes,
    }


async def get_feedback_summary_handler(
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Get a summary of all feedback for quick context.

    Use this at the start of a session to understand the current feedback
    state - how many items are new, acknowledged, or addressed.

    Args:
        project_path: Optional project path override

    Returns:
        Summary with total count, counts by status and category
    """
    if project_path:
        from dazzle_dnr_back.runtime.control_plane import FeedbackLogger

        feedback_dir = Path(project_path) / ".dazzle" / "feedback"
        logger = FeedbackLogger(feedback_dir=feedback_dir)
    else:
        logger = _get_feedback_logger()

    summary = logger.get_summary()

    # Add guidance for LLM
    guidance = []
    if summary.get("unaddressed", 0) > 0:
        guidance.append(
            f"There are {summary['unaddressed']} unaddressed feedback items "
            "that may need attention."
        )
    if summary.get("by_category", {}).get("Bug Report", 0) > 0:
        guidance.append(
            f"There are {summary['by_category']['Bug Report']} bug reports "
            "that should be prioritized."
        )

    return {
        **summary,
        "guidance": guidance,
        "file_location": ".dazzle/feedback/feedback.jsonl",
    }
