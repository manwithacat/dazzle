"""
Status and logging tool handlers.

Handles MCP server status and the Dazzle runtime log retrieval.
"""

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.core.manifest import load_manifest
from dazzle.core.paths import project_last_seen_version, project_log_dir, project_manifest
from dazzle.db.connection import resolve_db_url
from dazzle.mcp.semantics_kb import get_mcp_version
from dazzle.product_quality.persona_homes import (
    STABLE_PERSONA_USER_IDS,
    score_persona_homes,
)

from ..state import (
    get_active_project,
    get_active_project_path,
    get_available_projects,
    get_project_root,
    is_dev_mode,
)
from .common import error_response, extract_progress, wrap_handler_errors

logger = logging.getLogger(__name__)


def _db_row_to_entry(row: dict[str, Any]) -> dict[str, Any]:
    """Convert an activity_events DB row to the entry shape used by ActivityLog formatting."""
    entry: dict[str, Any] = {
        "type": row["event_type"],
        "tool": row["tool"],
        "ts": row.get("ts", ""),
    }
    for src, dst in (
        ("operation", "operation"),
        ("duration_ms", "duration_ms"),
        ("error", "error"),
        ("warnings", "warnings"),
        ("progress_current", "current"),
        ("progress_total", "total"),
        ("message", "message"),
        ("level", "level"),
        ("source", "source"),
        ("context_json", "context_json"),
    ):
        if row.get(src) is not None and row.get(src) != "":
            entry[dst] = row[src]
    if row.get("success") is not None:
        entry["success"] = bool(row["success"])
    return entry


def _mask_database_url(url: str) -> str:
    """Redact password in a postgres URL for agent-facing payloads."""
    if "://" not in url or "@" not in url:
        return url
    try:
        scheme, rest = url.split("://", 1)
        creds, hostpart = rest.rsplit("@", 1)
        if ":" in creds:
            user, _pw = creds.split(":", 1)
            return f"{scheme}://{user}:***@{hostpart}"
        return url
    except ValueError:
        return url


@wrap_handler_errors
def get_demo_world_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Agent-readable demo/runtime world model (#1629 G3).

    Read-only snapshot: serve ports, test_secret present, STABLE personas,
    persona-home seed residual, resolved DB URL (masked). Complements CLI
    serve/seed writes without violating ADR-0002.
    """
    root = Path(args.get("project_root") or project_path).resolve()
    runtime_path = root / ".dazzle" / "runtime.json"
    runtime: dict[str, Any] = {}
    if runtime_path.is_file():
        try:
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            runtime = {}

    db_url = _safe_db_url(root)
    secret = runtime.get("test_secret")
    personas_out = _persona_homes_payload(root)
    payload = {
        "project_root": str(root),
        "has_dazzle_toml": (root / "dazzle.toml").is_file(),
        "runtime_file": str(runtime_path) if runtime_path.is_file() else None,
        "ui_url": runtime.get("ui_url"),
        "api_url": runtime.get("api_url"),
        "ui_port": runtime.get("ui_port"),
        "api_port": runtime.get("api_port"),
        "test_mode_secret_present": bool(isinstance(secret, str) and secret),
        "database_url_masked": _mask_database_url(db_url) if db_url else None,
        "database_url_source": (
            "runtime.json"
            if runtime.get("database_url")
            else ("project .env / resolve" if db_url else None)
        ),
        "stable_persona_user_ids": dict(STABLE_PERSONA_USER_IDS),
        "persona_homes": personas_out,
        "persona_home_residual": sum(1 for p in personas_out if p.get("residual")),
        "seed_hint": (
            "POST /__test__/reset then POST /__test__/seed with X-Test-Secret from "
            "runtime.json; authenticate with role= after reset so principals use "
            "STABLE_PERSONA_USER_IDS (#1626/#1629)."
        ),
    }
    return json.dumps(payload, indent=2)


def _safe_db_url(root: Path) -> str:
    try:
        return resolve_db_url(project_root=root)
    except (OSError, ValueError, TypeError, RuntimeError, KeyError):
        logger.debug("demo_world db resolve failed", exc_info=True)
        return ""


def _persona_homes_payload(root: Path) -> list[dict[str, Any]]:
    try:
        homes = score_persona_homes(root)
    except (OSError, ValueError, TypeError, RuntimeError, KeyError) as exc:
        logger.debug("demo_world persona_homes failed: %s", exc, exc_info=True)
        return []
    out: list[dict[str, Any]] = []
    for h in homes:
        out.append(
            {
                "persona": h.persona,
                "default_workspace": h.default_workspace,
                "stable_user_id": h.stable_user_id or STABLE_PERSONA_USER_IDS.get(h.persona),
                "residual": h.residual,
                "reasons": h.residual_reasons,
                "regions": [
                    {
                        "region": r.region,
                        "source": r.source,
                        "bind_field": r.bind_field,
                        "seed_hits": r.seed_hits,
                        "residual": r.residual,
                        "reason": r.reason,
                    }
                    for r in h.regions
                ],
            }
        )
    return out


@wrap_handler_errors
def get_mcp_status_handler(args: dict[str, Any]) -> str:
    """Get MCP server status and optionally reload modules."""
    progress = extract_progress(args)
    progress.log_sync("Gathering MCP status...")

    reload_requested = args.get("reload", False)
    # #1629 G6 — full changelog floods agent context; compact by default
    include_changelog = bool(args.get("include_changelog", False))
    result: dict[str, Any] = {
        "mode": "dev" if is_dev_mode() else "normal",
        "project_root": str(get_project_root()),
    }

    # Determine the effective active project — roots wins over internal state
    resolved = args.get("_resolved_project_path")
    if isinstance(resolved, Path) and project_manifest(resolved).exists():
        active: dict[str, Any] = {"path": str(resolved)}
        try:
            manifest = load_manifest(project_manifest(resolved))
            active["manifest_name"] = manifest.name
            active["version"] = manifest.version
        except Exception:
            logger.debug("Failed to load project manifest", exc_info=True)
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

    # Project version — prefer pyproject.toml (editable), fall back to metadata
    try:
        from dazzle._version import get_version

        result["version"] = get_version()
    except Exception:
        result["version"] = "unknown"

    # Internal KB version info
    version_info = get_mcp_version()
    result["semantics_version"] = version_info

    # New-since-last-check: surface new capabilities from CHANGELOG.md
    try:
        current_version = result.get("version", "unknown")
        resolved = args.get("_resolved_project_path")
        project_path = (
            resolved
            if isinstance(resolved, Path)
            else (get_active_project_path() or get_project_root())
        )
        version_file = project_last_seen_version(project_path)
        last_seen: str | None = None

        if version_file.exists():
            last_seen = version_file.read_text(encoding="utf-8").strip()

        if current_version != "unknown":
            from dazzle.core.changelog import get_changelog_path, parse_changelog_since

            if last_seen and last_seen != current_version:
                new_items = parse_changelog_since(get_changelog_path(), last_seen)
            elif last_seen is None:
                # First run — show what's in the current version
                new_items = parse_changelog_since(get_changelog_path(), "")
            else:
                new_items = []

            result["last_seen_version"] = last_seen
            if include_changelog:
                result["new_since_last_check"] = new_items
            else:
                # Compact default (#1629 G6) — agents opt into full text
                result["new_since_last_check"] = {
                    "count": len(new_items) if isinstance(new_items, list) else 0,
                    "hint": (
                        "Pass include_changelog=true for full CHANGELOG entries "
                        "(default is compact to protect agent context)."
                    ),
                }

            # Persist the current version
            version_file.parent.mkdir(parents=True, exist_ok=True)
            version_file.write_text(current_version, encoding="utf-8")
    except Exception:
        logger.debug("Failed to compute new-since-last-check", exc_info=True)

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
                from dazzle.mcp.semantics_kb import get_mcp_version as new_get_version

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
        logger.debug("Browser gate not available", exc_info=True)

    # Activity log path — useful for tail -f during debugging
    try:
        from ..state import get_activity_log

        alog = get_activity_log()
        if alog is not None:
            result["activity_log_path"] = str(alog.path)
    except Exception:
        logger.debug("Activity log not available", exc_info=True)

    if is_dev_mode():
        result["available_projects"] = list(get_available_projects().keys())

    return json.dumps(result, indent=2)


@wrap_handler_errors
def get_telemetry_handler(args: dict[str, Any]) -> str:
    """Get MCP tool call telemetry data."""
    progress = extract_progress(args)
    progress.log_sync("Loading telemetry...")
    from ..state import get_knowledge_graph

    graph = get_knowledge_graph()
    if graph is None:
        return error_response("Knowledge graph not initialized")

    stats_only = args.get("stats_only", False)
    tool_name = args.get("tool_name")
    since_minutes = args.get("since_minutes")

    result: dict[str, Any] = {"stats": graph.get_tool_stats()}

    # Include knowledge effectiveness metrics (#611, #612, #613)
    result["knowledge_effectiveness"] = graph.get_knowledge_effectiveness()

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


@wrap_handler_errors
def get_activity_handler(args: dict[str, Any]) -> str:
    """Read recent MCP activity events from the SQLite activity store.

    Parameters:
        cursor_seq: int — event id to read after (0 = from start)
        count: int — max entries to return (default 20)
        format: str — "structured" (default) or "formatted" (markdown)
    """
    progress = extract_progress(args)
    progress.log_sync("Reading activity log...")
    from ..state import get_activity_store

    activity_store = get_activity_store()
    if activity_store is None:
        return error_response("Activity store not initialized")

    count = args.get("count", 20)
    fmt = args.get("format", "structured")

    since_id = args.get("cursor_seq", 0)
    events = activity_store.read_since(since_id=since_id, limit=count)
    last_id = events[-1]["id"] if events else since_id

    entries = [_db_row_to_entry(e) for e in events]

    data: dict[str, Any] = {
        "entries": entries,
        "cursor": {"seq": last_id, "epoch": 0},
        "has_more": len(events) == count,
        "stale": False,
        "active_tool": None,
        "backend": "sqlite",
    }

    if fmt == "formatted":
        from ..activity_log import ActivityLog as _AL

        formatted = _AL.format_summary(data, color=False)
        return json.dumps(
            {"formatted": formatted, "cursor": data["cursor"], "has_more": data["has_more"]},
            indent=2,
        )
    return json.dumps(data, indent=2)


@wrap_handler_errors
def get_dnr_logs_handler(args: dict[str, Any]) -> str:
    """Get Dazzle runtime logs for debugging."""
    progress = extract_progress(args)
    progress.log_sync("Reading the Dazzle runtime logs...")
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
    log_dir = project_log_dir(project_path)
    log_file = log_dir / "dazzle.log"

    result: dict[str, Any] = {
        "log_file": str(log_file),
        "project": str(project_path),
    }

    if not log_file.exists():
        result["status"] = "no_logs"
        result["message"] = (
            "No log file found. Start the the Dazzle runtime server with `dazzle serve` to generate logs."
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
