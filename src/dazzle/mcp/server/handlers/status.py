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
    from pathlib import Path

    from dazzle.core.manifest import load_manifest

    reload_requested = args.get("reload", False)
    result: dict[str, Any] = {
        "mode": "dev" if is_dev_mode() else "normal",
        "project_root": str(get_project_root()),
    }

    # Determine the effective active project — roots wins over internal state
    resolved = args.get("_resolved_project_path")
    if isinstance(resolved, Path) and (resolved / "dazzle.toml").exists():
        active: dict[str, Any] = {"path": str(resolved)}
        try:
            manifest = load_manifest(resolved / "dazzle.toml")
            active["manifest_name"] = manifest.name
            active["version"] = manifest.version
        except Exception:
            pass
        result["active_project"] = active
    elif is_dev_mode():
        project_name = get_active_project()
        if project_name:
            active = {"name": project_name}
            project_path = get_available_projects().get(project_name)
            if project_path:
                active["path"] = str(project_path)
            result["active_project"] = active
        else:
            result["active_project"] = None

    # Project version from package metadata
    try:
        from importlib.metadata import version as pkg_version

        result["version"] = pkg_version("dazzle")
    except Exception:
        result["version"] = "unknown"

    # Internal KB version info
    version_info = get_mcp_version()
    result["semantics_version"] = version_info

    if reload_requested:
        if not is_dev_mode():
            result["reload"] = "skipped - only available in dev mode"
        else:
            # Re-seed the Knowledge Graph from TOML (single operation replaces
            # the old reload_cache + reload_inference_kb pair).
            try:
                from dazzle.mcp.knowledge_graph.seed import seed_framework_knowledge

                from ..state import get_knowledge_graph

                graph = get_knowledge_graph()
                if graph is not None:
                    seed_framework_knowledge(graph)

                # Reload modules that cache data from TOML/config files
                import importlib
                import sys as _sys

                for mod_name in [
                    "dazzle.core.ir.fidelity",
                    "dazzle.core.fidelity_scorer",
                    "dazzle.mcp.server.handlers.fidelity",
                    "dazzle.agent.missions.persona_journey",
                    "dazzle.mcp.server.handlers.discovery",
                ]:
                    if mod_name in _sys.modules:
                        importlib.reload(_sys.modules[mod_name])

                # Get the new version after reload
                from dazzle.mcp.semantics import get_mcp_version as new_get_version

                new_version_info = new_get_version()
                result["reload"] = "success"
                result["new_semantics_version"] = new_version_info

            except Exception as e:
                result["reload"] = f"failed: {e}"

    # Browser resource status
    try:
        from dazzle.testing.browser_gate import get_browser_gate

        gate = get_browser_gate()
        result["browser_gate"] = {
            "max_concurrent": gate.max_concurrent,
            "active": gate.active_count,
        }
    except Exception:
        pass

    # Activity log path — useful for workshop / tail -f
    try:
        from ..state import get_activity_log

        alog = get_activity_log()
        if alog is not None:
            result["activity_log_path"] = str(alog.path)
    except Exception:
        pass

    if is_dev_mode():
        result["available_projects"] = list(get_available_projects().keys())

    return json.dumps(result, indent=2)


def get_telemetry_handler(args: dict[str, Any]) -> str:
    """Get MCP tool call telemetry data."""
    from ..state import get_knowledge_graph

    graph = get_knowledge_graph()
    if graph is None:
        return json.dumps({"error": "Knowledge graph not initialized"})

    stats_only = args.get("stats_only", False)
    tool_name = args.get("tool_name")
    since_minutes = args.get("since_minutes")

    result: dict[str, Any] = {"stats": graph.get_tool_stats()}

    if not stats_only:
        since: float | None = None
        if since_minutes is not None:
            import time

            since = time.time() - (since_minutes * 60)

        result["recent"] = graph.get_tool_invocations(
            limit=args.get("count", 50),
            tool_name_filter=tool_name,
            since=since,
        )

    return json.dumps(result, indent=2)


def get_activity_handler(args: dict[str, Any]) -> str:
    """Read recent MCP activity log entries.

    Returns a structured response with entries, cursor for polling,
    and a human-readable formatted summary.

    Parameters:
        cursor_seq: int — sequence number to read after (0 = from start)
        cursor_epoch: int — epoch counter for staleness detection
        count: int — max entries to return (default 20)
        format: str — "structured" (default) or "formatted" (markdown)
    """
    from ..state import get_activity_log

    activity_log = get_activity_log()
    if activity_log is None:
        return json.dumps({"error": "Activity log not initialized"})

    cursor_seq = args.get("cursor_seq", 0)
    cursor_epoch = args.get("cursor_epoch", 0)
    count = args.get("count", 20)
    fmt = args.get("format", "structured")

    data = activity_log.read_since(
        cursor_seq=cursor_seq,
        cursor_epoch=cursor_epoch,
        count=count,
    )

    if fmt == "formatted":
        # Return rich markdown summary for display
        from ..activity_log import ActivityLog as _AL

        formatted = _AL.format_summary(data, color=False)
        result: dict[str, Any] = {
            "formatted": formatted,
            "cursor": data["cursor"],
            "has_more": data["has_more"],
        }
        if data.get("active_tool"):
            result["active_tool"] = data["active_tool"]
        return json.dumps(result, indent=2)

    # Structured mode — full data
    return json.dumps(data, indent=2)


def get_dnr_logs_handler(args: dict[str, Any]) -> str:
    """Get DNR runtime logs for debugging."""
    from pathlib import Path

    count = args.get("count", 50)
    level = args.get("level")
    errors_only = args.get("errors_only", False)

    # Prefer roots-resolved path, then active project, then project root
    resolved = args.get("_resolved_project_path")
    if isinstance(resolved, Path):
        project_path = resolved
    else:
        project_path = get_active_project_path() or get_project_root()
    log_dir = project_path / ".dazzle" / "logs"
    log_file = log_dir / "dazzle.log"

    result: dict[str, Any] = {
        "log_file": str(log_file),
        "project": str(project_path),
    }

    if not log_file.exists():
        result["status"] = "no_logs"
        result["message"] = (
            "No log file found. Start the DNR server with `dazzle serve` to generate logs."
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
