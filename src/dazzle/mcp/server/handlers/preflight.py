"""Pre-flight server reachability check for MCP handlers.

Fast HTTP probe before expensive server-dependent operations.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def check_server_reachable(base_url: str, timeout: float = 5.0) -> str | None:
    """Probe base_url for reachability. Returns None if OK, error JSON string if not."""
    try:
        import httpx
    except ImportError:
        return None  # graceful fallback — skip check if httpx unavailable

    try:
        with httpx.Client(timeout=timeout) as client:
            client.get(base_url)
        return None
    except httpx.ConnectError:
        return json.dumps(
            {
                "error": f"Server not reachable at {base_url}. Is it running?",
                "hint": "Start the app with: dazzle serve",
            }
        )
    except httpx.TimeoutException:
        return json.dumps(
            {
                "error": f"Server at {base_url} timed out after {timeout}s",
                "hint": "The server may be starting up. Try again shortly.",
            }
        )
    except Exception as e:
        logger.debug("Preflight check failed: %s", e)
        return None  # Don't block on unexpected errors
