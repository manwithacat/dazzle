"""
MCP handler for user profile operations.

Operations:
  observe         — Analyze recent tool invocations from KG telemetry
  observe_message — Analyze a user message for vocabulary signals
  get             — Return the current profile context for LLM consumption
  reset           — Delete profile and return fresh default
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from .common import extract_progress

logger = logging.getLogger("dazzle.mcp.handlers.user_profile")


def handle_user_profile(arguments: dict[str, Any]) -> str:
    """Dispatch user_profile operations."""
    progress = extract_progress(arguments)
    progress.log_sync("Processing user profile...")
    from dazzle.mcp.user_profile import (
        analyze_message,
        analyze_tool_invocations,
        load_profile,
        profile_to_context,
        reset_profile,
        save_profile,
    )

    operation = arguments.get("operation")

    if operation == "observe":
        return _observe(arguments, load_profile, analyze_tool_invocations, save_profile)
    elif operation == "observe_message":
        return _observe_message(arguments, load_profile, analyze_message, save_profile)
    elif operation == "get":
        profile = load_profile()
        return json.dumps(profile_to_context(profile), indent=2)
    elif operation == "reset":
        profile = reset_profile()
        return json.dumps(
            {"status": "reset", "profile": profile_to_context(profile)},
            indent=2,
        )
    else:
        return json.dumps({"error": f"Unknown user_profile operation: {operation}"})


def _observe(
    arguments: dict[str, Any],
    load_profile: Any,
    analyze_tool_invocations: Any,
    save_profile: Any,
) -> str:
    """Read recent invocations from KG telemetry and update the profile."""
    limit = arguments.get("limit", 50)
    since_minutes = arguments.get("since_minutes", 30)

    # Try to get invocations from KG telemetry
    invocations: list[dict[str, Any]] = []
    try:
        from dazzle.mcp.server.state import get_knowledge_graph

        graph = get_knowledge_graph()
        if graph is not None:
            since: float | None = None
            if since_minutes is not None:
                since = time.time() - (since_minutes * 60)
            invocations = graph.get_tool_invocations(limit=limit, since=since)
    except Exception as e:
        logger.debug("KG telemetry unavailable: %s", e)

    if not invocations:
        return json.dumps({"status": "no_data", "message": "No recent tool invocations found"})

    profile = load_profile()
    analyze_tool_invocations(invocations, profile)
    save_profile(profile)

    from dazzle.mcp.user_profile import profile_to_context

    return json.dumps(
        {
            "status": "updated",
            "invocations_processed": len(invocations),
            "profile": profile_to_context(profile),
        },
        indent=2,
    )


def _observe_message(
    arguments: dict[str, Any],
    load_profile: Any,
    analyze_message: Any,
    save_profile: Any,
) -> str:
    """Analyze a user message for vocabulary signals."""
    message_text = arguments.get("message_text", "")
    if not message_text:
        return json.dumps({"error": "message_text is required for observe_message"})

    profile = load_profile()
    analyze_message(message_text, profile)
    save_profile(profile)

    from dazzle.mcp.user_profile import profile_to_context

    return json.dumps(
        {
            "status": "updated",
            "profile": profile_to_context(profile),
        },
        indent=2,
    )
