"""Dazzle Workshop — Rich Live TUI for the MCP activity log.

Presents a gamified, Dwarf-Fortress-inspired "workshop" view of MCP tool
invocations.  Reads the JSONL activity log and renders:

  - **Workbench**: active tools with progress bars and elapsed time
  - **Done**: scrolling list of completed tool calls
  - **Status bar**: live counters (working / done / errors / uptime)

Usage::

    dazzle workshop -p examples/simple_task
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Group
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

MAX_DONE = 20  # completed entries to keep visible
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


@dataclass
class WorkshopState:
    """Mutable display state built from JSONL entries."""

    active: dict[str, ActiveTool] = field(default_factory=dict)
    completed: list[CompletedTool] = field(default_factory=list)
    total_calls: int = 0
    error_count: int = 0
    start_time: float = field(default_factory=time.monotonic)
    # File-reading cursor
    _file_pos: int = 0

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
        key = f"{tool}.{operation}" if operation else tool

        if etype == TYPE_TOOL_START:
            self.total_calls += 1
            self.active[key] = ActiveTool(
                tool=tool,
                operation=operation,
                start_time=time.monotonic(),
                ts=ts,
            )

        elif etype == TYPE_TOOL_END:
            self.active.pop(key, None)
            success = entry.get("success", True)
            if not success:
                self.error_count += 1
            self.completed.append(
                CompletedTool(
                    tool=tool,
                    operation=operation,
                    ts=ts,
                    success=success,
                    duration_ms=entry.get("duration_ms"),
                    error=entry.get("error"),
                )
            )
            # Cap completed list
            if len(self.completed) > MAX_DONE:
                self.completed = self.completed[-MAX_DONE:]

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
                    )
                )
                if len(self.completed) > MAX_DONE:
                    self.completed = self.completed[-MAX_DONE:]


# ── File reading ─────────────────────────────────────────────────────────────


def read_new_entries(log_path: Path, state: WorkshopState) -> list[dict[str, Any]]:
    """Read new JSONL lines since last position, handling truncation."""
    if not log_path.exists():
        return []

    entries: list[dict[str, Any]] = []
    try:
        file_size = log_path.stat().st_size
        # Detect truncation
        if file_size < state._file_pos:
            state._file_pos = 0

        with open(log_path, encoding="utf-8") as f:
            f.seek(state._file_pos)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            state._file_pos = f.tell()
    except OSError:
        pass
    return entries


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
    """Elapsed since monotonic start."""
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
    # Right-align time
    header.append(f"  {now_str}", style="dim")

    # ── Workbench ────────────────────────────────────────────────────────
    wb_table = Table.grid(padding=(0, 1))
    wb_table.add_column(width=2)  # icon
    wb_table.add_column(min_width=22)  # tool label + progress
    wb_table.add_column(min_width=8)  # elapsed

    if state.active:
        for at in state.active.values():
            label = f"{at.tool}.{at.operation}" if at.operation else at.tool

            # Build the row content
            row_icon = Text("\u26cf", style="bold yellow")  # ⛏
            row_main = Text()
            row_main.append(f"{label}  ", style="bold cyan")

            if at.progress_current is not None and at.progress_total and at.progress_total > 0:
                ratio = min(at.progress_current / at.progress_total, 1.0)
                pct = f"{ratio * 100:.0f}%"
                counter = f"[{at.progress_current}/{at.progress_total}]"
                row_main.append("")
                # Add progress bar as separate renderable in the cell
                bar = ProgressBar(
                    total=at.progress_total,
                    completed=at.progress_current,
                    width=20,
                    style="bar.back",
                    complete_style="bar.complete",
                    finished_style="bar.finished",
                )
                row_elapsed = Text(
                    f"{pct}  {counter}  {_format_elapsed(at.start_time)}", style="dim"
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
    status.append("  \u2502  ", style="dim")
    status.append(f"{state.total_calls} calls", style="dim")
    status.append("  \u2502  ", style="dim")
    status.append(_format_uptime(state.start_time), style="dim")

    status_panel = Panel(status, border_style="dim", padding=(0, 0))

    return Group(header, workbench_panel, done_panel, status_panel)


# ── Main loop ────────────────────────────────────────────────────────────────


def watch(
    log_path: Path,
    project_name: str = "unknown",
    version: str = "",
) -> None:
    """Run the Rich Live display loop.  Blocks until Ctrl-C."""
    state = WorkshopState()

    # Ingest any existing entries so we start with history
    for entry in read_new_entries(log_path, state):
        state.ingest(entry)

    with Live(
        render_workshop(state, project_name, version),
        refresh_per_second=4,
        screen=False,
    ) as live:
        try:
            while True:
                time.sleep(POLL_INTERVAL)
                new = read_new_entries(log_path, state)
                for entry in new:
                    state.ingest(entry)
                live.update(render_workshop(state, project_name, version))
        except KeyboardInterrupt:
            pass


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


def run_workshop(project_dir: Path) -> None:
    """Entry point: resolve project info, find log, start watch."""
    import tomllib

    project_dir = project_dir.resolve()

    # Read project info from dazzle.toml
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

    log_path = _resolve_log_path(project_dir, config)

    from rich.console import Console

    console = Console()

    if not log_path.exists():
        console.print(
            f"[dim]Log not found at[/dim] {log_path}\n"
            f"[dim]Start the MCP server first, then re-run this command.[/dim]\n"
            f"[dim]Creating empty log and waiting...[/dim]"
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.touch()

    console.print(
        f"[bold yellow]\u2692[/bold yellow]  Watching [cyan]{project_name}[/cyan] "
        f"workshop \u2014 [dim]Ctrl-C to exit[/dim]\n"
    )
    watch(log_path, project_name, version)
