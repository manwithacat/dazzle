"""MCP handler for e2e environment operations.

Read-only per ADR-0002: list_modes, describe_mode, status, list_baselines.
Start/stop operations live in CLI only (dazzle e2e env).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dazzle.e2e.baseline import BaselineManager
from dazzle.e2e.errors import BaselineKeyError, UnknownModeError
from dazzle.e2e.lifecycle import LockFile, _is_pid_alive, _iso_now_seconds_ago
from dazzle.e2e.modes import MODE_REGISTRY, get_mode
from dazzle.mcp.server.handlers.common import wrap_handler_errors


def _mode_to_dict(spec: Any) -> dict[str, Any]:
    d = asdict(spec)
    # Convert frozenset to sorted list for JSON serialization
    d["db_policies_allowed"] = sorted(d["db_policies_allowed"])
    return d


@wrap_handler_errors
def e2e_list_modes_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Return the full mode registry as JSON."""
    return json.dumps(
        {"modes": [_mode_to_dict(m) for m in MODE_REGISTRY]},
        indent=2,
    )


@wrap_handler_errors
def e2e_describe_mode_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Return a single mode spec by name, or an error dict if unknown."""
    name = args.get("name", "")
    try:
        spec = get_mode(name)
    except UnknownModeError as e:
        return json.dumps({"error": str(e)}, indent=2)
    return json.dumps(_mode_to_dict(spec), indent=2)


def _status_for(project_root: Path) -> dict[str, Any]:
    """Compute the status snapshot for a single example app project root."""
    lock_path = project_root / ".dazzle" / "mode_a.lock"
    runtime_path = project_root / ".dazzle" / "runtime.json"
    log_dir = project_root / ".dazzle" / "e2e-logs"

    lock = LockFile(lock_path)
    holder = lock.read_holder()

    holder_pid: int | None = None
    holder_alive: bool = False
    lock_age: float | None = None
    if holder is not None:
        raw_pid = holder.get("pid")
        if isinstance(raw_pid, int):
            holder_pid = raw_pid
            holder_alive = _is_pid_alive(raw_pid)
        started = holder.get("started_at", "")
        if started:
            lock_age = _iso_now_seconds_ago(started)

    runtime_data: dict[str, Any] | None = None
    if runtime_path.exists():
        try:
            runtime_data = json.loads(runtime_path.read_text())
        except (OSError, json.JSONDecodeError):
            pass

    last_log: Path | None = None
    last_log_tail: list[str] | None = None
    if log_dir.exists():
        logs = sorted(log_dir.glob("mode_a-*.log"), key=lambda p: p.stat().st_mtime)
        if logs:
            last_log = logs[-1]
            try:
                text = last_log.read_text(errors="replace").splitlines()
                last_log_tail = text[-20:]
            except OSError:
                last_log_tail = []

    return {
        "project_root": str(project_root),
        "lock_file": str(lock_path) if lock_path.exists() else None,
        "lock_holder_pid": holder_pid,
        "lock_holder_alive": holder_alive,
        "lock_age_seconds": round(lock_age) if lock_age is not None else None,
        "runtime_file": str(runtime_path) if runtime_path.exists() else None,
        "runtime_ports": (
            {
                "ui": runtime_data.get("ui_port"),
                "api": runtime_data.get("api_port"),
            }
            if runtime_data
            else None
        ),
        "last_log_file": str(last_log) if last_log else None,
        "last_log_tail": last_log_tail,
    }


@wrap_handler_errors
def e2e_status_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Return Mode A status for one project or scan all examples/*."""
    explicit_project = args.get("project_root")
    if explicit_project:
        root = Path(explicit_project)
        return json.dumps(_status_for(root), indent=2)

    examples_dir = project_path / "examples"
    if not examples_dir.exists():
        return json.dumps(_status_for(project_path), indent=2)

    results = []
    for child in sorted(examples_dir.iterdir()):
        if child.is_dir() and (child / "dazzle.toml").exists():
            results.append({"name": child.name, **_status_for(child)})
    return json.dumps({"examples": results}, indent=2)


@wrap_handler_errors
def e2e_list_baselines_handler(project_path: Path, args: dict[str, Any]) -> str:
    """List baseline snapshot files for a project root."""
    explicit_project = args.get("project_root")
    root = Path(explicit_project) if explicit_project else project_path

    bl_dir = root / ".dazzle" / "baselines"
    if not bl_dir.exists():
        return json.dumps({"baselines": []}, indent=2)

    url = os.environ.get("DATABASE_URL", "postgresql://localhost/unused")
    current_filename: str | None = None
    try:
        mgr = BaselineManager(root, url)
        current_filename = mgr.path_for(mgr.current_key()).name
    except (BaselineKeyError, Exception):  # noqa: BLE001 — intentional catch-all
        current_filename = None

    entries: list[dict[str, Any]] = []
    for p in sorted(bl_dir.glob("baseline-*.sql.gz")):
        # Filename format: baseline-{rev}-{hash12}.sql.gz
        stem = p.name.removesuffix(".sql.gz")
        parts = stem.split("-", 2)
        alembic_rev = parts[1] if len(parts) >= 3 else ""
        fixture_prefix = parts[2] if len(parts) >= 3 else ""

        entries.append(
            {
                "filename": p.name,
                "alembic_rev": alembic_rev,
                "fixture_hash_prefix": fixture_prefix,
                "size_bytes": p.stat().st_size,
                "mtime": datetime.fromtimestamp(p.stat().st_mtime, tz=UTC).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "is_current": p.name == current_filename,
            }
        )
    return json.dumps({"baselines": entries}, indent=2)
