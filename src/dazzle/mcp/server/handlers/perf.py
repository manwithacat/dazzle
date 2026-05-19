"""MCP handler for the ``perf`` tool (read-only).

Operations:
  - ``list``: enumerate past runs from ``.dazzle/perf/``
  - ``report`` (``run`` optional, default latest): return the JSON
    findings payload as a string under ``findings``.
  - ``show`` (``run`` optional): return the span tree as a list of
    dicts.

CLI vs MCP boundary (ADR-0002): no process-launching operations on this
handler. ``dazzle perf trace`` stays CLI-only because it spawns
subprocesses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dazzle.perf.findings import build_findings, render_json
from dazzle.perf.run_id import latest_run_id
from dazzle.perf.storage import iter_spans, list_runs


def handle_perf(args: dict[str, Any]) -> dict[str, Any]:
    """Dispatch perf MCP operations."""
    operation = args.get("operation")
    if operation == "list":
        return _do_list()
    if operation == "report":
        return _do_report(args.get("run"))
    if operation == "show":
        return _do_show(args.get("run"))
    return {"error": f"unknown operation {operation!r}"}


def _perf_dir() -> Path:
    return Path.cwd() / ".dazzle" / "perf"


def _do_list() -> dict[str, Any]:
    perf_dir = _perf_dir()
    if not perf_dir.is_dir():
        return {"runs": []}
    runs: list[dict[str, Any]] = []
    for db_path in sorted(perf_dir.glob("*.db")):
        for run in list_runs(db_path):
            runs.append(
                {
                    "run_id": run.run_id,
                    "started_at": run.started_at,
                    "ended_at": run.ended_at,
                    "app_name": run.app_name,
                    "command_line": run.command_line,
                }
            )
    return {"runs": runs}


def _resolve_run(run: str | None) -> tuple[Path, str] | None:
    perf_dir = _perf_dir()
    run_id = run or latest_run_id(perf_dir)
    if run_id is None:
        return None
    db_path = perf_dir / f"{run_id}.db"
    if not db_path.exists():
        return None
    return db_path, run_id


def _do_report(run: str | None) -> dict[str, Any]:
    resolved = _resolve_run(run)
    if resolved is None:
        return {"error": "no matching run"}
    db_path, run_id = resolved
    report = build_findings(db_path, run_id)
    return {"findings": render_json(report)}


def _do_show(run: str | None) -> dict[str, Any]:
    resolved = _resolve_run(run)
    if resolved is None:
        return {"error": "no matching run"}
    db_path, run_id = resolved
    spans = [
        {
            "span_id": s.span_id,
            "parent_span_id": s.parent_span_id,
            "name": s.name,
            "kind": s.kind,
            "status": s.status,
            "duration_ms": s.duration_ns / 1e6,
        }
        for s in iter_spans(db_path, run_id)
    ]
    return {"spans": spans}
