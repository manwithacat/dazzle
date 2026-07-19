"""MCP lock / multi-session diagnosis for ``dazzle mcp check`` (#1628).

Surfaces holder PID, age, live/stale classification, session dirs, and
best-effort dual-registration (Grok + Claude) so hosts don't only see
opaque handshake failures.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from dazzle.mcp.server.mcp_session import mcp_shared_mode, mcp_state_dir
from dazzle.mcp.server.process_lock import (
    EXIT_LOCK_CONTENTION,
    clear_stale_lock,
    diagnose_lock,
)
from dazzle.mcp.setup import check_mcp_server


def diagnose_project_mcp(project_root: Path) -> dict[str, Any]:
    """Return structured lock + session diagnosis for a project root."""
    root = project_root.resolve()
    dazzle = root / ".dazzle"
    legacy_lock = dazzle / "mcp.lock"
    sessions_dir = dazzle / "mcp-sessions"

    legacy = diagnose_lock(legacy_lock)
    sessions: list[dict[str, Any]] = []
    if sessions_dir.is_dir():
        for child in sorted(sessions_dir.iterdir()):
            if not child.is_dir():
                continue
            lock_diag = diagnose_lock(child / "mcp.lock")
            sessions.append(
                {
                    "id": child.name,
                    "path": str(child),
                    "kg_exists": (child / "knowledge_graph.db").exists(),
                    "lock": _diag_to_dict(lock_diag),
                }
            )

    return {
        "project_root": str(root),
        "shared_mode": mcp_shared_mode(),
        "default_state_dir": str(mcp_state_dir(root)),
        "legacy_lock": _diag_to_dict(legacy),
        "sessions": sessions,
        "multi_session_default": not mcp_shared_mode(),
    }


def clear_stale_project_locks(project_root: Path) -> list[str]:
    """Clear stale/corrupt/empty locks under the project (not live holders)."""
    root = project_root.resolve()
    messages: list[str] = []
    dazzle = root / ".dazzle"
    candidates = [dazzle / "mcp.lock"]
    sessions = dazzle / "mcp-sessions"
    if sessions.is_dir():
        candidates.extend(p / "mcp.lock" for p in sessions.iterdir() if p.is_dir())
    for path in candidates:
        if not path.exists():
            continue
        changed, msg = clear_stale_lock(path)
        prefix = "cleared" if changed else "skip"
        messages.append(f"{prefix}: {msg}")
    if not messages:
        messages.append("No lock files found to consider")
    return messages


def detect_dual_registration() -> dict[str, Any]:
    """Best-effort: dazzle MCP listed in more than one host config.

    Grok imports Claude MCP sources; registering the same ``dazzle`` server
    in both ``~/.grok/config.toml`` and Claude config can double-spawn and
    historically contended on a single lock.
    """
    home = Path.home()
    sources: list[dict[str, Any]] = []

    # Claude Code style JSON configs
    for path in (
        home / ".claude.json",
        home / ".claude" / "mcp_servers.json",
        home / ".config" / "claude-code" / "mcp_servers.json",
        home / "Library" / "Application Support" / "Claude Code" / "mcp_servers.json",
    ):
        entry = _read_dazzle_from_json(path)
        if entry is not None:
            sources.append(entry)

    # Grok config.toml
    grok = home / ".grok" / "config.toml"
    entry = _read_dazzle_from_toml(grok)
    if entry is not None:
        sources.append(entry)

    # Deduplicate by path
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for s in sources:
        key = s["config_path"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)

    dual = len(unique) >= 2
    warning = None
    if dual:
        paths = ", ".join(s["config_path"] for s in unique)
        warning = (
            f"dazzle MCP appears in multiple host configs ({paths}). "
            "Grok may import Claude sources — keep a single registration "
            "per host to avoid double-spawn."
        )
    return {
        "dual_registration": dual,
        "sources": unique,
        "warning": warning,
    }


def _diag_to_dict(diag: Any) -> dict[str, Any]:
    holder = None
    if diag.holder is not None:
        holder = {
            "pid": diag.holder.pid,
            "started_at": diag.holder.started_at,
            "working_dir": diag.holder.working_dir,
        }
    return {
        "lock_path": str(diag.lock_path),
        "exists": diag.exists,
        "classification": diag.classification,
        "pid_alive": diag.pid_alive,
        "age_seconds": diag.age_seconds,
        "holder": holder,
    }


def _read_dazzle_from_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    servers = data.get("mcpServers") or data.get("mcp_servers") or {}
    if not isinstance(servers, dict):
        return None
    # match dazzle / dazzle-* names
    for name, cfg in servers.items():
        if not isinstance(name, str):
            continue
        if name == "dazzle" or name.startswith("dazzle-"):
            return {
                "config_path": str(path),
                "name": name,
                "command": _summarize_command(cfg if isinstance(cfg, dict) else {}),
            }
    return None


def _read_dazzle_from_toml(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    # Lightweight: look for [mcp_servers.dazzle] or mcp_servers.dazzle without tomllib
    # (tomllib is 3.11+; project may still prefer no hard dep here).
    if re.search(r"(?m)^\[mcp_servers\.dazzle", text) or re.search(
        r"(?m)^\[mcpServers\.dazzle", text
    ):
        return {
            "config_path": str(path),
            "name": "dazzle",
            "command": "(see config.toml)",
        }
    # Nested table form: [mcp_servers] dazzle = { ... } is rarer; scan for dazzle key near mcp
    if "mcp_servers" in text and re.search(r"(?m)^\s*dazzle\s*=", text):
        return {
            "config_path": str(path),
            "name": "dazzle",
            "command": "(see config.toml)",
        }
    return None


def _summarize_command(cfg: dict[str, Any]) -> str:
    command = cfg.get("command", "")
    args = cfg.get("args") or []
    if isinstance(args, list):
        return f"{command} {' '.join(str(a) for a in args)}".strip()
    return str(command)


def build_check_payload(project_root: Path, *, clear_stale: bool = False) -> dict[str, Any]:
    """Assemble registration + lock + dual-reg payload for ``dazzle mcp check``."""
    root = project_root.resolve()
    status = check_mcp_server()
    lock_info = diagnose_project_mcp(root)
    dual = detect_dual_registration()
    clear_messages: list[str] = []
    if clear_stale:
        clear_messages = clear_stale_project_locks(root)
        lock_info = diagnose_project_mcp(root)
    return {
        "registration": status,
        "lock": lock_info,
        "dual_registration": dual,
        "clear_stale": clear_messages,
    }


def check_exit_code(payload: dict[str, Any]) -> int:
    """Agent-friendly exit codes for ``dazzle mcp check`` (#1628).

    * 0 — ok (registered; no blocking shared-mode lock)
    * 1 — not registered
    * 2 — shared mode with live exclusive lock holder
    """
    status = payload["registration"]
    lock_info = payload["lock"]
    legacy = lock_info["legacy_lock"]
    if lock_info["shared_mode"] and legacy["classification"] == "live":
        return EXIT_LOCK_CONTENTION
    if not status["registered"]:
        return 1
    return 0


def format_check_text(payload: dict[str, Any]) -> str:
    """Human-readable ``dazzle mcp check`` report."""
    lines: list[str] = []
    _append_registration_section(lines, payload["registration"])
    _append_lock_section(lines, payload["lock"])
    clear_messages = payload.get("clear_stale") or []
    if clear_messages:
        lines.append("")
        lines.append("--clear-stale")
        lines.extend(f"  {m}" for m in clear_messages)
    dual = payload.get("dual_registration") or {}
    if dual.get("warning"):
        lines.append("")
        lines.append(f"⚠ Dual registration: {dual['warning']}")
        for src in dual.get("sources") or []:
            lines.append(f"  • {src['config_path']} ({src.get('name')})")
    status = payload["registration"]
    if not status["registered"]:
        lines.append("")
        lines.append("💡 To register the MCP server, run: dazzle mcp-setup")
    return "\n".join(lines)


def _append_registration_section(lines: list[str], status: dict[str, Any]) -> None:
    lines.append("DAZZLE MCP Server Status")
    lines.append("=" * 50)
    lines.append(f"Status:        {status['status']}")
    lines.append(f"Registered:    {'✓ Yes' if status['registered'] else '✗ No'}")
    if status.get("config_path"):
        lines.append(f"Config:        {status['config_path']}")
    if status.get("server_command"):
        lines.append(f"Command:       {status['server_command']}")
    tools = status.get("tools") or []
    if tools:
        lines.append("")
        lines.append(f"Available Tools ({len(tools)}):")
        lines.extend(f"  • {tool}" for tool in sorted(tools))
    elif status.get("registered"):
        lines.append("")
        lines.append("Tools: Unable to enumerate (MCP SDK not available)")


def _append_lock_section(lines: list[str], lock_info: dict[str, Any]) -> None:
    lines.append("")
    lines.append("Lock / multi-session (#1628)")
    lines.append("-" * 50)
    lines.append(f"Project:       {lock_info['project_root']}")
    mode = "shared (exclusive lock)" if lock_info["shared_mode"] else "multi-session (default)"
    lines.append(f"Mode:          {mode}")
    lines.append(f"State dir:     {lock_info['default_state_dir']}")
    legacy = lock_info["legacy_lock"]
    lines.append(_format_legacy_lock_line(legacy))
    holder_note = _legacy_holder_note(legacy, shared=bool(lock_info["shared_mode"]))
    if holder_note:
        lines.append(holder_note)
    sessions = lock_info.get("sessions") or []
    if sessions:
        lines.append(f"Sessions:      {len(sessions)} under .dazzle/mcp-sessions/")
        for s in sessions[:10]:
            lock_c = s["lock"]["classification"]
            kg = "yes" if s["kg_exists"] else "no"
            lines.append(f"  • {s['id']}  lock={lock_c}  kg={kg}")
    else:
        lines.append("Sessions:      (none yet)")


def _format_legacy_lock_line(legacy: dict[str, Any]) -> str:
    parts = [f"Legacy lock:   {legacy['classification']}"]
    holder = legacy.get("holder")
    if holder:
        parts.append(f" pid={holder['pid']}")
    age = legacy.get("age_seconds")
    if age is not None:
        parts.append(f" age={int(age)}s")
    return "".join(parts)


def _legacy_holder_note(legacy: dict[str, Any], *, shared: bool) -> str | None:
    if legacy.get("classification") != "live" or not legacy.get("holder"):
        return None
    pid = legacy["holder"]["pid"]
    if shared:
        return (
            f"  LOCK_HELD_BY_PID={pid} — shared-mode holder is live; "
            f"kill {pid} or unset DAZZLE_MCP_SHARED"
        )
    return (
        f"  LOCK_HELD_BY_PID={pid} — legacy exclusive holder still "
        f"running (multi-session default is not blocked; optional: "
        f"kill {pid} or dazzle mcp check --clear-stale if stale)"
    )


def run_mcp_check(
    project_root: Path,
    *,
    clear_stale: bool = False,
    as_json: bool = False,
) -> tuple[str, int]:
    """Return (report body, exit_code) for the CLI."""
    payload = build_check_payload(project_root, clear_stale=clear_stale)
    code = check_exit_code(payload)
    if as_json:
        body = json.dumps(payload, indent=2, default=str)
    else:
        body = format_check_text(payload)
    return body, code
