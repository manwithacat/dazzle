"""
Status and logging tool handlers.

Handles MCP server status and DNR log retrieval.
"""

from __future__ import annotations

import json
from typing import Any

from dazzle.mcp.semantics import get_mcp_version

from ..state import (
    get_active_project,
    get_active_project_path,
    get_available_projects,
    get_project_root,
    is_dev_mode,
)


def get_mcp_status_handler(args: dict[str, Any]) -> str:
    """Get MCP server status and optionally reload modules."""

    reload_requested = args.get("reload", False)
    result: dict[str, Any] = {
        "mode": "dev" if is_dev_mode() else "normal",
        "project_root": str(get_project_root()),
    }

    # Get current version info
    version_info = get_mcp_version()
    result["semantics_version"] = version_info

    if reload_requested:
        if not is_dev_mode():
            result["reload"] = "skipped - only available in dev mode"
        else:
            # Reload the semantics data from TOML files
            try:
                from dazzle.mcp.semantics_kb import reload_cache

                reload_cache()

                # Get the new version after reload
                from dazzle.mcp.semantics import get_mcp_version as new_get_version

                new_version_info = new_get_version()
                result["reload"] = "success"
                result["new_semantics_version"] = new_version_info

            except Exception as e:
                result["reload"] = f"failed: {e}"

    # Add active project info in dev mode
    if is_dev_mode():
        result["active_project"] = get_active_project()
        result["available_projects"] = list(get_available_projects().keys())

    return json.dumps(result, indent=2)


def get_dnr_logs_handler(args: dict[str, Any]) -> str:
    """Get DNR runtime logs for debugging."""
    count = args.get("count", 50)
    level = args.get("level")
    errors_only = args.get("errors_only", False)

    # Get project path
    project_path = get_active_project_path() or get_project_root()
    log_dir = project_path / ".dazzle" / "logs"
    log_file = log_dir / "dnr.log"

    result: dict[str, Any] = {
        "log_file": str(log_file),
        "project": str(project_path),
    }

    if not log_file.exists():
        result["status"] = "no_logs"
        result["message"] = (
            "No log file found. Start the DNR server with `dazzle dnr serve` to generate logs."
        )
        result["hint"] = f"Log file will be created at: {log_file}"
        return json.dumps(result, indent=2)

    try:
        entries: list[dict[str, Any]] = []
        with open(log_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if level and entry.get("level") != level.upper():
                        continue
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue

        if errors_only:
            # Return error summary
            errors = [e for e in entries if e.get("level") == "ERROR"]
            warnings = [e for e in entries if e.get("level") == "WARNING"]

            # Group by component
            by_component: dict[str, list[dict[str, Any]]] = {}
            for error in errors:
                comp = error.get("component", "unknown")
                if comp not in by_component:
                    by_component[comp] = []
                by_component[comp].append(error)

            result["status"] = "error_summary"
            result["total_entries"] = len(entries)
            result["error_count"] = len(errors)
            result["warning_count"] = len(warnings)
            result["errors_by_component"] = {k: len(v) for k, v in by_component.items()}
            result["recent_errors"] = errors[-10:]  # Last 10 errors
        else:
            # Return recent logs
            recent = entries[-count:] if count < len(entries) else entries
            result["status"] = "ok"
            result["total_entries"] = len(entries)
            result["returned"] = len(recent)
            result["entries"] = recent

        return json.dumps(result, indent=2)

    except OSError as e:
        result["status"] = "error"
        result["error"] = str(e)
        return json.dumps(result, indent=2)
