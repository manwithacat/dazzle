"""
Mailpit MCP tool handlers.

Provides MCP tools for querying Mailpit to monitor feedback and bug reports
submitted via the Dazzle Bar during human-led UX testing.

Operations:
- list_messages: List recent messages with metadata
- get_message: Get full message content
- search: Search by sender/subject/content
- delete: Remove a processed message
- stats: Get message counts and health status
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger("dazzle.mcp.mailpit")


def _get_mailpit_url() -> str:
    """Get Mailpit HTTP API URL from environment or default."""
    return os.getenv("MAILPIT_URL", "http://localhost:8025").rstrip("/")


async def _mailpit_request(
    method: str,
    endpoint: str,
    params: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any] | bytes | None:
    """Make HTTP request to Mailpit API.

    Returns:
        JSON response as dict, raw bytes, or None on error
    """
    try:
        import httpx
    except ImportError:
        return {"error": "httpx not installed - run: pip install httpx"}

    url = f"{_get_mailpit_url()}{endpoint}"

    try:
        async with httpx.AsyncClient() as client:
            if method == "GET":
                response = await client.get(url, params=params, timeout=timeout)
            elif method == "DELETE":
                response = await client.delete(url, params=params, timeout=timeout)
            else:
                return {"error": f"Unsupported method: {method}"}

            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    result: dict[str, Any] = response.json()
                    return result
                return response.content
            elif response.status_code == 404:
                return {"error": "Message not found"}
            else:
                return {"error": f"Mailpit API error: {response.status_code}"}

    except httpx.ConnectError:
        return {"error": f"Cannot connect to Mailpit at {_get_mailpit_url()}"}
    except httpx.TimeoutException:
        return {"error": "Mailpit request timed out"}
    except Exception as e:
        return {"error": f"Mailpit request failed: {str(e)}"}


def _format_message_summary(msg: dict[str, Any]) -> dict[str, Any]:
    """Format a message summary for LLM consumption."""
    # Parse Mailpit message format
    from_data = msg.get("From", {})
    to_data = msg.get("To", [])

    return {
        "id": msg.get("ID"),
        "subject": msg.get("Subject", "(no subject)"),
        "from": from_data.get("Address", "") if isinstance(from_data, dict) else str(from_data),
        "to": [t.get("Address", "") if isinstance(t, dict) else str(t) for t in to_data],
        "date": msg.get("Date"),
        "read": msg.get("Read", False),
        "snippet": msg.get("Snippet", "")[:200],
        "attachments": msg.get("Attachments", 0),
        "size": msg.get("Size", 0),
    }


async def list_messages(arguments: dict[str, Any]) -> str:
    """List recent messages from Mailpit.

    Args:
        arguments: May contain 'limit' (default 20), 'category' filter

    Returns:
        JSON with message summaries
    """
    limit = arguments.get("limit", 20)
    category = arguments.get("category")

    result = await _mailpit_request(
        "GET",
        "/api/v1/messages",
        params={"limit": min(limit, 100)},
    )

    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)

    if not isinstance(result, dict):
        return json.dumps({"error": "Unexpected response from Mailpit"})

    messages = result.get("messages", [])
    formatted = []

    for msg in messages:
        summary = _format_message_summary(msg)

        # Filter by category if specified (check subject for [BUG], [FEATURE], etc.)
        if category:
            subject = summary.get("subject", "").upper()
            category_upper = category.upper()
            if f"[{category_upper}]" not in subject and f"({category_upper})" not in subject:
                continue

        formatted.append(summary)

    return json.dumps(
        {
            "total": result.get("total", len(formatted)),
            "count": len(formatted),
            "messages": formatted,
            "mailpit_url": _get_mailpit_url(),
        },
        indent=2,
    )


async def get_message(arguments: dict[str, Any]) -> str:
    """Get full message content from Mailpit.

    Args:
        arguments: Must contain 'message_id'

    Returns:
        JSON with full message content
    """
    message_id = arguments.get("message_id")
    if not message_id:
        return json.dumps({"error": "message_id is required"})

    # Get message metadata
    result = await _mailpit_request("GET", f"/api/v1/message/{message_id}")

    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)

    if not isinstance(result, dict):
        return json.dumps({"error": "Unexpected response from Mailpit"})

    # Format full message
    from_data = result.get("From", {})
    to_data = result.get("To", [])

    formatted = {
        "id": result.get("ID"),
        "subject": result.get("Subject", "(no subject)"),
        "from": {
            "name": from_data.get("Name", ""),
            "address": from_data.get("Address", ""),
        }
        if isinstance(from_data, dict)
        else {"address": str(from_data)},
        "to": [
            {"name": t.get("Name", ""), "address": t.get("Address", "")}
            if isinstance(t, dict)
            else {"address": str(t)}
            for t in to_data
        ],
        "date": result.get("Date"),
        "text": result.get("Text", ""),
        "html": result.get("HTML", "")[:5000] if result.get("HTML") else None,
        "headers": result.get("Headers", {}),
        "attachments": [
            {
                "filename": att.get("FileName"),
                "content_type": att.get("ContentType"),
                "size": att.get("Size"),
            }
            for att in result.get("Attachments", [])
        ],
    }

    return json.dumps(formatted, indent=2)


async def search_messages(arguments: dict[str, Any]) -> str:
    """Search messages in Mailpit.

    Args:
        arguments: Must contain 'query', may contain 'limit'

    Returns:
        JSON with matching messages
    """
    query = arguments.get("query")
    if not query:
        return json.dumps({"error": "query is required"})

    limit = arguments.get("limit", 20)

    result = await _mailpit_request(
        "GET",
        "/api/v1/search",
        params={"query": query, "limit": min(limit, 100)},
    )

    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)

    if not isinstance(result, dict):
        return json.dumps({"error": "Unexpected response from Mailpit"})

    messages = result.get("messages", [])
    formatted = [_format_message_summary(msg) for msg in messages]

    return json.dumps(
        {
            "query": query,
            "total": result.get("total", len(formatted)),
            "count": len(formatted),
            "messages": formatted,
        },
        indent=2,
    )


async def delete_message(arguments: dict[str, Any]) -> str:
    """Delete a message from Mailpit.

    Args:
        arguments: Must contain 'message_id'

    Returns:
        JSON with success/error status
    """
    message_id = arguments.get("message_id")
    if not message_id:
        return json.dumps({"error": "message_id is required"})

    result = await _mailpit_request("DELETE", f"/api/v1/messages/{message_id}")

    if isinstance(result, dict) and "error" in result:
        return json.dumps(result)

    return json.dumps({"success": True, "deleted_id": message_id})


async def get_stats(arguments: dict[str, Any]) -> str:
    """Get Mailpit statistics and health status.

    Returns:
        JSON with message counts, storage info, health status
    """
    # Get info endpoint
    info_result = await _mailpit_request("GET", "/api/v1/info")

    if isinstance(info_result, dict) and "error" in info_result:
        return json.dumps(
            {
                "healthy": False,
                "error": info_result.get("error"),
                "mailpit_url": _get_mailpit_url(),
            }
        )

    # Get message count
    messages_result = await _mailpit_request("GET", "/api/v1/messages", params={"limit": 1})

    total_messages = 0
    if isinstance(messages_result, dict) and "total" in messages_result:
        total_messages = messages_result.get("total", 0)

    return json.dumps(
        {
            "healthy": True,
            "mailpit_url": _get_mailpit_url(),
            "version": info_result.get("Version") if isinstance(info_result, dict) else None,
            "database_size": info_result.get("DatabaseSize")
            if isinstance(info_result, dict)
            else None,
            "total_messages": total_messages,
            "messages_info": info_result.get("Messages") if isinstance(info_result, dict) else None,
            "checked_at": datetime.now().isoformat(),
        },
        indent=2,
    )


# =============================================================================
# Main Handler
# =============================================================================


async def handle_mailpit(arguments: dict[str, Any]) -> str:
    """Handle consolidated Mailpit operations.

    This is an async handler since Mailpit operations require HTTP requests.
    """
    operation = arguments.get("operation")

    if operation == "list_messages":
        return await list_messages(arguments)
    elif operation == "get_message":
        return await get_message(arguments)
    elif operation == "search":
        return await search_messages(arguments)
    elif operation == "delete":
        return await delete_message(arguments)
    elif operation == "stats":
        return await get_stats(arguments)
    else:
        return json.dumps({"error": f"Unknown mailpit operation: {operation}"})
