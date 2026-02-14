"""Dazzle Workshop — Rich Live TUI for the MCP activity store.

Presents a gamified, Dwarf-Fortress-inspired "workshop" view of MCP tool
invocations.  Reads the SQLite activity store and renders:

  - **Workbench**: active tools with progress bars and elapsed time
  - **Done**: scrolling list of completed tool calls
  - **Status bar**: live counters (working / done / errors / uptime)

Usage::

    dazzle workshop                          # watch current directory
    dazzle workshop -p examples/simple_task  # watch specific project
    dazzle workshop --info                   # print log path and exit
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from dazzle.mcp.server.activity_log import (
    TYPE_ERROR,
    TYPE_LOG,
    TYPE_PROGRESS,
    TYPE_TOOL_END,
    TYPE_TOOL_START,
)

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_TAIL = 20  # completed entries to keep visible
POLL_INTERVAL = 0.25  # seconds between log reads


# ── State ────────────────────────────────────────────────────────────────────


@dataclass
class ActiveTool:
    """An in-flight tool invocation."""

    tool: str
    operation: str | None
    start_time: float  # monotonic
    ts: str  # wall-clock from log entry
    progress_current: int | None = None
    progress_total: int | None = None
    status_message: str | None = None
    source: str = "mcp"


@dataclass
class CompletedTool:
    """A finished tool invocation."""

    tool: str
    operation: str | None
    ts: str
    success: bool
    duration_ms: float | None
    error: str | None = None
    warnings: int = 0
    source: str = "mcp"


@dataclass
class WorkshopState:
    """Mutable display state built from activity entries."""

    active: dict[str, ActiveTool] = field(default_factory=dict)
    completed: list[CompletedTool] = field(default_factory=list)
    total_calls: int = 0
    error_count: int = 0
    warning_count: int = 0
    start_time: float = field(default_factory=time.monotonic)
    max_done: int = DEFAULT_TAIL
    bell: bool = False
    # SQLite cursor
    _last_event_id: int = 0
    # Session tracking for exit summary
    _fastest: tuple[str, float] | None = None
    _slowest: tuple[str, float] | None = None

    @property
    def done_count(self) -> int:
        return len(self.completed)

    @property
    def working_count(self) -> int:
        return len(self.active)

    def ingest(self, entry: dict[str, Any]) -> None:
        """Process a single JSONL entry and update state."""
        etype = entry.get("type")
        tool = entry.get("tool", "")
        operation = entry.get("operation")
        ts = entry.get("ts", "")
        source = entry.get("source", "mcp")
        key = f"{tool}.{operation}" if operation else tool

        if etype == TYPE_TOOL_START:
            self.total_calls += 1
            self.active[key] = ActiveTool(
                tool=tool,
                operation=operation,
                start_time=time.monotonic(),
                ts=ts,
                source=source,
            )

        elif etype == TYPE_TOOL_END:
            self.active.pop(key, None)
            success = entry.get("success", True)
            dur = entry.get("duration_ms")
            warns = entry.get("warnings", 0)

            if not success:
                self.error_count += 1
                if self.bell:
                    sys.stderr.write("\a")
                    sys.stderr.flush()

            if warns:
                self.warning_count += warns

            # Track fastest/slowest for session summary
            if dur is not None:
                if self._fastest is None or dur < self._fastest[1]:
                    self._fastest = (key, dur)
                if self._slowest is None or dur > self._slowest[1]:
                    self._slowest = (key, dur)

            self.completed.append(
                CompletedTool(
                    tool=tool,
                    operation=operation,
                    ts=ts,
                    success=success,
                    duration_ms=dur,
                    error=entry.get("error"),
                    warnings=warns,
                    source=source,
                )
            )
            # Cap completed list
            if len(self.completed) > self.max_done:
                self.completed = self.completed[-self.max_done :]

        elif etype == TYPE_PROGRESS:
            if key in self.active:
                at = self.active[key]
                cur = entry.get("current")
                tot = entry.get("total")
                if cur is not None:
                    at.progress_current = cur
                if tot is not None:
                    at.progress_total = tot
                msg = entry.get("message")
                if msg:
                    at.status_message = msg

        elif etype == TYPE_LOG:
            if key in self.active:
                msg = entry.get("message")
                if msg:
                    self.active[key].status_message = msg

        elif etype == TYPE_ERROR:
            self.error_count += 1
            if self.bell:
                sys.stderr.write("\a")
                sys.stderr.flush()
            # Also remove from active if present
            if key in self.active:
                self.active.pop(key)
                self.completed.append(
                    CompletedTool(
                        tool=tool,
                        operation=operation,
                        ts=ts,
                        success=False,
                        duration_ms=None,
                        error=entry.get("message", "error"),
                        source=source,
                    )
                )
                if len(self.completed) > self.max_done:
                    self.completed = self.completed[-self.max_done :]


# ── SQLite reading ───────────────────────────────────────────────────────────


def read_new_entries_db(db_path: Path, state: WorkshopState) -> list[dict[str, Any]]:
    """Read new activity events from the SQLite database.

    Uses cursor-based polling via ``_last_event_id``.
    Returns entries as dicts compatible with ``WorkshopState.ingest()``.
    """
    if not db_path.exists():
        return []

    entries: list[dict[str, Any]] = []
    try:
        import sqlite3

        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM activity_events WHERE id > ? ORDER BY id ASC LIMIT 200",
                (state._last_event_id,),
            ).fetchall()
            for row in rows:
                entry = _db_row_to_entry(dict(row))
                entries.append(entry)
                state._last_event_id = row["id"]
        finally:
            conn.close()
    except Exception:
        pass
    return entries


def _db_row_to_entry(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a DB row dict to the entry format expected by WorkshopState.ingest()."""
    entry: dict[str, Any] = {
        "type": row["event_type"],
        "tool": row["tool"],
        "ts": row.get("ts", ""),
    }
    if row.get("operation"):
        entry["operation"] = row["operation"]
    if row.get("success") is not None:
        entry["success"] = bool(row["success"])
    if row.get("duration_ms") is not None:
        entry["duration_ms"] = row["duration_ms"]
    if row.get("error"):
        entry["error"] = row["error"]
    if row.get("warnings"):
        entry["warnings"] = row["warnings"]
    if row.get("progress_current") is not None:
        entry["current"] = row["progress_current"]
    if row.get("progress_total") is not None:
        entry["total"] = row["progress_total"]
    if row.get("message"):
        entry["message"] = row["message"]
    if row.get("level"):
        entry["level"] = row["level"]
    if row.get("source"):
        entry["source"] = row["source"]
    return entry


def _detect_db_path(project_dir: Path) -> Path | None:
    """Return the KG database path if it contains activity_events."""
    db_path = project_dir / ".dazzle" / "knowledge_graph.db"
    if not db_path.exists():
        return None
    try:
        import sqlite3

        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        try:
            conn.execute("SELECT 1 FROM activity_events LIMIT 0")
            return db_path
        except sqlite3.OperationalError:
            return None
        finally:
            conn.close()
    except Exception:
        return None


# ── Rendering ────────────────────────────────────────────────────────────────


def _format_ts(ts_raw: str) -> str:
    """Extract HH:MM:SS from an ISO timestamp."""
    try:
        dt = datetime.fromisoformat(ts_raw)
        return dt.strftime("%H:%M:%S")
    except (ValueError, AttributeError):
        return ts_raw[:8] if ts_raw else "??:??:??"


def _format_duration(ms: float | None) -> str:
    """Human-readable duration."""
    if ms is None:
        return ""
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.1f}s"


def _format_elapsed(start: float) -> str:
    """Elapsed since monotonic start — ticks live every render."""
    elapsed = time.monotonic() - start
    if elapsed < 60:
        return f"{elapsed:.1f}s"
    minutes = int(elapsed // 60)
    secs = elapsed % 60
    return f"{minutes}m{secs:.0f}s"


def _format_uptime(start: float) -> str:
    """Uptime string."""
    elapsed = time.monotonic() - start
    if elapsed < 60:
        return f"up {elapsed:.0f}s"
    minutes = int(elapsed // 60)
    secs = int(elapsed % 60)
    if minutes < 60:
        return f"up {minutes}m{secs:02d}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"up {hours}h{mins:02d}m"


def render_workshop(
    state: WorkshopState,
    project_name: str,
    version: str,
    backend: str = "",
) -> Group:
    """Build the full workshop renderable."""
    now_str = datetime.now(UTC).strftime("%H:%M:%S")

    # ── Header ───────────────────────────────────────────────────────────
    header = Text()
    header.append("  \u2692  ", style="bold yellow")
    header.append("DAZZLE WORKSHOP", style="bold white")
    header.append(f" \u00b7 {project_name}", style="dim white")
    if version:
        header.append(f" v{version}", style="dim white")
    if backend:
        header.append(f" ({backend})", style="dim")
    header.append(f"  {now_str}", style="dim")
    header.append("  \u2502  Ctrl-C to exit", style="dim")

    # ── Workbench ────────────────────────────────────────────────────────
    wb_table = Table.grid(padding=(0, 1))
    wb_table.add_column(width=2)  # icon
    wb_table.add_column(min_width=22)  # tool label + progress
    wb_table.add_column(min_width=8)  # elapsed

    if state.active:
        for at in state.active.values():
            label = f"{at.tool}.{at.operation}" if at.operation else at.tool
            if at.source == "cli":
                label = f"CLI {label}"

            row_icon = Text("\u26cf", style="bold yellow")  # ⛏
            row_main = Text()
            row_main.append(f"{label}  ", style="bold cyan")

            if at.progress_current is not None and at.progress_total and at.progress_total > 0:
                ratio = min(at.progress_current / at.progress_total, 1.0)
                pct = f"{ratio * 100:.0f}%"
                counter = f"[{at.progress_current}/{at.progress_total}]"
                row_main.append("")
                bar = ProgressBar(
                    total=at.progress_total,
                    completed=at.progress_current,
                    width=20,
                    style="bar.back",
                    complete_style="bar.complete",
                    finished_style="bar.finished",
                )
                row_elapsed = Text(
                    f"{pct}  {counter}  {_format_elapsed(at.start_time)}",
                    style="dim",
                )
                wb_table.add_row(row_icon, Group(row_main, bar), row_elapsed)
            else:
                row_elapsed = Text(_format_elapsed(at.start_time), style="dim")
                wb_table.add_row(row_icon, row_main, row_elapsed)

            # Sub-step line
            if at.status_message:
                sub = Text()
                sub.append(f"  \u2514 {at.status_message}", style="dim italic")
                wb_table.add_row(Text(""), sub, Text(""))
    else:
        idle = Text("  Idle \u2014 waiting for work...", style="dim italic")
        wb_table.add_row(Text(""), idle, Text(""))

    workbench_panel = Panel(
        wb_table,
        title="[bold]WORKBENCH[/bold]",
        title_align="left",
        border_style="blue",
        padding=(0, 1),
    )

    # ── Done ─────────────────────────────────────────────────────────────
    done_table = Table.grid(padding=(0, 1))
    done_table.add_column(width=10)  # timestamp
    done_table.add_column(width=2)  # icon
    done_table.add_column(min_width=24)  # tool label
    done_table.add_column(min_width=8)  # duration
    done_table.add_column()  # extra info

    if state.completed:
        for ct in state.completed:
            ts = Text(_format_ts(ct.ts), style="dim")
            label = f"{ct.tool}.{ct.operation}" if ct.operation else ct.tool
            if ct.source == "cli":
                label = f"CLI {label}"

            if ct.success:
                icon = Text("\u2714", style="green")  # ✔
                tool_text = Text(label)
                dur = Text(_format_duration(ct.duration_ms), style="dim")
                extra = Text()
                if ct.warnings:
                    extra.append(f"\u26a0 {ct.warnings}", style="yellow")
                done_table.add_row(ts, icon, tool_text, dur, extra)
            else:
                icon = Text("\u2718", style="bold red")  # ✘
                tool_text = Text(label, style="red")
                dur = Text(_format_duration(ct.duration_ms), style="dim")
                err = Text(ct.error or "failed", style="red dim")
                done_table.add_row(ts, icon, tool_text, dur, err)
    else:
        empty = Text("  No completed calls yet.", style="dim italic")
        done_table.add_row(Text(""), Text(""), empty, Text(""), Text(""))

    done_panel = Panel(
        done_table,
        title="[bold]DONE[/bold]",
        title_align="left",
        border_style="green" if not state.error_count else "yellow",
        padding=(0, 1),
    )

    # ── Status bar ───────────────────────────────────────────────────────
    status = Text()
    status.append("  \u26cf ", style="bold yellow")
    status.append(f"{state.working_count} working", style="cyan")
    status.append(" \u00b7 ", style="dim")
    status.append("\u2714 ", style="green")
    status.append(f"{state.done_count} done", style="green")
    if state.error_count:
        status.append(" \u00b7 ", style="dim")
        status.append("\u2718 ", style="red")
        status.append(f"{state.error_count} err", style="red")
    if state.warning_count:
        status.append(" \u00b7 ", style="dim")
        status.append(f"\u26a0 {state.warning_count}", style="yellow")
    status.append("  \u2502  ", style="dim")
    status.append(f"{state.total_calls} calls", style="dim")
    status.append("  \u2502  ", style="dim")
    status.append(_format_uptime(state.start_time), style="dim")

    status_panel = Panel(status, border_style="dim", padding=(0, 0))

    return Group(header, workbench_panel, done_panel, status_panel)


# ── Session summary ──────────────────────────────────────────────────────────


def print_session_summary(state: WorkshopState, console: Console) -> None:
    """Print a session summary on exit."""
    if state.total_calls == 0:
        return

    elapsed = time.monotonic() - state.start_time
    if elapsed < 60:
        dur_str = f"{elapsed:.0f}s"
    else:
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        dur_str = f"{mins}m {secs:02d}s"

    ok = state.total_calls - state.error_count
    console.print()
    console.print("[bold]\u2550\u2550\u2550 SESSION COMPLETE \u2550\u2550\u2550[/bold]")
    console.print(f"  Duration:  {dur_str}")
    console.print(
        f"  Tools run: {state.total_calls} "
        f"([green]{ok} \u2714[/green]"
        + (f", [red]{state.error_count} \u2718[/red]" if state.error_count else "")
        + (f", [yellow]\u26a0 {state.warning_count}[/yellow]" if state.warning_count else "")
        + ")"
    )
    if state._fastest:
        console.print(f"  Fastest:   {state._fastest[0]} ({_format_duration(state._fastest[1])})")
    if state._slowest and state._slowest != state._fastest:
        console.print(f"  Slowest:   {state._slowest[0]} ({_format_duration(state._slowest[1])})")
    console.print()


# ── Main loop ────────────────────────────────────────────────────────────────


def watch(
    db_path: Path,
    project_name: str = "unknown",
    version: str = "",
    *,
    max_done: int = DEFAULT_TAIL,
    bell: bool = False,
) -> None:
    """Run the Rich Live display loop.  Blocks until Ctrl-C.

    Reads activity events from the SQLite database at *db_path*.
    """
    state = WorkshopState(max_done=max_done, bell=bell)
    backend = "SQLite"

    # Ingest any existing entries so we start with history
    for entry in read_new_entries_db(db_path, state):
        state.ingest(entry)

    console = Console()
    with Live(
        render_workshop(state, project_name, version, backend),
        refresh_per_second=4,
        screen=False,
        console=console,
    ) as live:
        try:
            while True:
                time.sleep(POLL_INTERVAL)
                new = read_new_entries_db(db_path, state)
                for entry in new:
                    state.ingest(entry)
                live.update(render_workshop(state, project_name, version, backend))
        except KeyboardInterrupt:
            pass

    print_session_summary(state, console)


# ── Config helpers ───────────────────────────────────────────────────────────


def _resolve_log_path(project_dir: Path, config: dict[str, Any]) -> Path:
    """Determine log path from config or convention.

    Checks ``[workshop] log`` in dazzle.toml first, falls back to the
    standard ``.dazzle/mcp-activity.log`` location.
    """
    custom = config.get("workshop", {}).get("log")
    if custom:
        p = Path(custom)
        return p if p.is_absolute() else project_dir / p
    return project_dir / ".dazzle" / "mcp-activity.log"


def _load_project_config(project_dir: Path) -> tuple[str, str, dict[str, Any]]:
    """Read dazzle.toml and return (project_name, version, full_config)."""
    import tomllib

    project_name = project_dir.name
    version = ""
    config: dict[str, Any] = {}
    toml_path = project_dir / "dazzle.toml"
    if toml_path.exists():
        try:
            with open(toml_path, "rb") as f:
                config = tomllib.load(f)
            proj = config.get("project", {})
            project_name = proj.get("name", project_name)
            version = proj.get("version", "")
        except Exception:
            pass
    return project_name, version, config


# ── Entry points ─────────────────────────────────────────────────────────────


def get_log_path(project_dir: Path) -> Path:
    """Resolve the activity log path for a project.  Public API for --info."""
    project_dir = project_dir.resolve()
    _, _, config = _load_project_config(project_dir)
    return _resolve_log_path(project_dir, config)


def run_workshop(
    project_dir: Path,
    *,
    info: bool = False,
    tail: int = DEFAULT_TAIL,
    bell: bool = False,
) -> None:
    """Entry point: resolve project info, find log, start watch."""
    project_dir = project_dir.resolve()
    project_name, version, config = _load_project_config(project_dir)

    console = Console()

    # --info: just print the log path and exit
    if info:
        log_path = _resolve_log_path(project_dir, config)
        console.print(str(log_path))
        return

    # Require SQLite backend
    db_path = _detect_db_path(project_dir)
    if db_path is None:
        console.print(
            "[red bold]Error:[/red bold] No activity database found.\n"
            "Run the MCP server first so it creates the SQLite activity store.\n"
            f"Expected: {project_dir / '.dazzle' / 'knowledge_graph.db'}"
        )
        raise SystemExit(1)

    # Clear screen and jump straight into the TUI
    console.clear()
    watch(db_path, project_name, version, max_done=tail, bell=bell)
