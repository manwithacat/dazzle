"""Dazzle Workshop — Textual TUI for MCP activity observation.

Three-screen interactive display:
  - **Dashboard**: live active tools + recent completed history
  - **Session**: all calls grouped by tool, collapsible
  - **Call Detail**: full progress timeline for a single call

Usage::

    dazzle workshop                          # launch TUI
    dazzle workshop -p examples/simple_task  # watch specific project
    dazzle workshop --info                   # print log path and exit
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dazzle.core.paths import project_activity_log, project_kg_db
from dazzle.mcp.server.activity_log import (
    TYPE_ERROR,
    TYPE_LOG,
    TYPE_PROGRESS,
    TYPE_TOOL_END,
    TYPE_TOOL_START,
)

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_TAIL = 25  # completed entries visible on dashboard
POLL_INTERVAL_S = 0.25  # seconds between SQLite polls


# ── Data models ──────────────────────────────────────────────────────────────


@dataclass
class ToolCall:
    """A single MCP tool invocation with its full event timeline."""

    call_id: str  # "{tool}.{operation}.{start_ts}" — unique-ish key
    tool: str
    operation: str | None
    start_ts: str  # wall-clock ISO timestamp
    start_mono: float  # monotonic time for elapsed calculation
    events: list[dict[str, Any]] = field(default_factory=list)
    # Final state (set on tool_end)
    finished: bool = False
    success: bool | None = None
    duration_ms: float | None = None
    error: str | None = None
    warnings: int = 0
    context_json: str | None = None
    source: str = "mcp"
    # Live progress (updated on progress events)
    progress_current: int | None = None
    progress_total: int | None = None
    status_message: str | None = None

    @property
    def label(self) -> str:
        """Human-readable tool.operation label."""
        if self.operation:
            return f"{self.tool}.{self.operation}"
        return self.tool

    @property
    def elapsed_s(self) -> float:
        """Seconds since start (live) or final duration."""
        if self.duration_ms is not None:
            return self.duration_ms / 1000
        return time.monotonic() - self.start_mono

    @property
    def summary(self) -> str:
        """One-line summary from context_json or last event message."""
        if self.context_json:
            try:
                ctx = json.loads(self.context_json)
                if isinstance(ctx, dict):
                    # Look for common summary keys
                    for key in ("summary", "message", "status"):
                        if key in ctx:
                            return str(ctx[key])
                    # Fall back to compact repr of top-level keys
                    parts = []
                    for k, v in ctx.items():
                        if isinstance(v, (int, float, str, bool)):
                            parts.append(f"{k}={v}")
                    if parts:
                        return ", ".join(parts[:4])
            except (json.JSONDecodeError, TypeError):
                pass
        # Fall back to last event message
        if self.events:
            for evt in reversed(self.events):
                if evt.get("message"):
                    return evt["message"]
        return ""

    @property
    def purpose(self) -> str:
        """Purpose description from first log event."""
        for evt in self.events:
            if evt.get("type") in (TYPE_LOG, TYPE_PROGRESS) and evt.get("message"):
                return evt["message"]
        return self.label


@dataclass
class WorkshopData:
    """All ingested activity data, powering all three screens."""

    active: dict[str, ToolCall] = field(default_factory=dict)
    completed: list[ToolCall] = field(default_factory=list)
    all_calls: list[ToolCall] = field(default_factory=list)
    total_calls: int = 0
    error_count: int = 0
    warning_count: int = 0
    start_time: float = field(default_factory=time.monotonic)
    max_done: int = DEFAULT_TAIL
    bell: bool = False
    # SQLite cursor
    _last_event_id: int = 0

    def ingest(self, entry: dict[str, Any]) -> ToolCall | None:
        """Ingest a single activity event. Returns the affected ToolCall, if any."""
        etype = entry.get("type", "")
        tool = entry.get("tool", "unknown")
        operation = entry.get("operation")
        ts = entry.get("ts", "")
        source = entry.get("source", "mcp")

        if etype == TYPE_TOOL_START:
            call_id = f"{tool}.{operation}.{ts}"
            call = ToolCall(
                call_id=call_id,
                tool=tool,
                operation=operation,
                start_ts=ts,
                start_mono=time.monotonic(),
                source=source,
            )
            self.active[call_id] = call
            self.all_calls.append(call)
            self.total_calls += 1
            return call

        # Find the active call for this tool
        call = self._find_active(tool, operation)

        if etype == TYPE_TOOL_END:
            if call:
                call.finished = True
                call.success = entry.get("success", True)
                call.duration_ms = entry.get("duration_ms")
                call.error = entry.get("error")
                call.warnings = entry.get("warnings", 0)
                call.context_json = entry.get("context_json")
                call.events.append(entry)
                del self.active[call.call_id]
                self.completed.append(call)
                if len(self.completed) > self.max_done * 2:
                    self.completed = self.completed[-self.max_done :]
                if not call.success:
                    self.error_count += 1
                if call.warnings:
                    self.warning_count += call.warnings
            return call

        if etype == TYPE_PROGRESS:
            if call:
                call.progress_current = entry.get("current")
                call.progress_total = entry.get("total")
                call.status_message = entry.get("message")
                call.events.append(entry)
            return call

        if etype in (TYPE_LOG, TYPE_ERROR):
            if call:
                call.status_message = entry.get("message")
                call.events.append(entry)
            if etype == TYPE_ERROR:
                self.error_count += 1
            return call

        return None

    def _find_active(self, tool: str, operation: str | None) -> ToolCall | None:
        """Find the most recent active call matching tool/operation."""
        for call_id in reversed(list(self.active)):
            call = self.active[call_id]
            if call.tool == tool and (operation is None or call.operation == operation):
                return call
        return None

    def calls_grouped_by_tool(self) -> dict[str, list[ToolCall]]:
        """Group all_calls by tool name for SessionScreen."""
        groups: dict[str, list[ToolCall]] = {}
        for call in self.all_calls:
            groups.setdefault(call.tool, []).append(call)
        return groups


# ── SQLite reading ───────────────────────────────────────────────────────────


def read_new_entries_db(
    db_path: Path,
    data: WorkshopData,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Read new activity events from the SQLite database.

    Uses cursor-based polling via ``_last_event_id``.
    Returns entries as dicts compatible with ``WorkshopData.ingest()``.

    If *conn* is supplied it is reused (avoiding a new connection per poll).
    Falls back to opening a fresh connection when *conn* is ``None``.
    """
    if not db_path.exists():
        return []

    entries: list[dict[str, Any]] = []
    own_conn = conn is None
    try:
        if conn is None:
            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM activity_events WHERE id > ? ORDER BY id ASC LIMIT 200",
            (data._last_event_id,),
        ).fetchall()
        for row in rows:
            entry = _db_row_to_entry(dict(row))
            entries.append(entry)
            data._last_event_id = row["id"]
    except Exception:
        logger.debug("Failed to poll activity events", exc_info=True)
    finally:
        if own_conn and conn is not None:
            conn.close()
    return entries


def _db_row_to_entry(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a DB row dict to the entry format expected by WorkshopData.ingest()."""
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
    if row.get("context_json"):
        entry["context_json"] = row["context_json"]
    return entry


def _detect_db_path(project_dir: Path) -> Path | None:
    """Return the KG database path if it contains activity_events."""
    db_path = project_kg_db(project_dir)
    if not db_path.exists():
        return None
    try:
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


# ── Formatting helpers ───────────────────────────────────────────────────────


def _format_ts(ts_raw: str) -> str:
    """Extract HH:MM:SS from an ISO timestamp."""
    if not ts_raw:
        return "??:??:??"
    try:
        if "T" in ts_raw:
            return ts_raw.split("T")[1][:8]
        return ts_raw[:8]
    except Exception:
        return ts_raw[:8] if len(ts_raw) >= 8 else ts_raw


def _format_duration(seconds: float) -> str:
    """Format seconds to a compact display string."""
    if seconds < 0.1:
        return "<0.1s"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m{secs:.0f}s"


def _relative_time(start_ts: str, event_ts: str) -> str:
    """Compute relative time string between two ISO timestamps."""
    try:
        start = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
        event = datetime.fromisoformat(event_ts.replace("Z", "+00:00"))
        delta = (event - start).total_seconds()
        return f"{delta:05.1f}s"
    except (ValueError, TypeError):
        return "  ?.?s"


# ── Textual App ──────────────────────────────────────────────────────────────

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Vertical, VerticalScroll
    from textual.screen import Screen
    from textual.timer import Timer
    from textual.widgets import Footer, Header, Label, Static

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False


if TEXTUAL_AVAILABLE:

    class ActiveToolWidget(Static):
        """Renders a single active (in-flight) tool call.

        Uses auto_refresh so the spinner animates and elapsed time
        updates even when no new events arrive.
        """

        def __init__(self, call: ToolCall, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._call = call
            self.auto_refresh = 1 / 4

        def render(self) -> str:
            c = self._call
            elapsed = _format_duration(c.elapsed_s)
            progress = ""
            if c.progress_current is not None and c.progress_total:
                pct = c.progress_current / c.progress_total
                filled = int(pct * 16)
                bar = "\u2588" * filled + "\u2591" * (16 - filled)
                progress = f" {bar} {c.progress_current}/{c.progress_total}"
            else:
                # Spinner
                frames = "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827"
                idx = int(time.monotonic() * 8) % len(frames)
                progress = f" {frames[idx]}"

            status = f"  \u2514 {c.status_message}" if c.status_message else ""
            return f"\u26cf {c.label}{progress}  {elapsed}\n{status}"

    class CompletedToolRow(Static):
        """Renders a single completed tool call row."""

        can_focus = True

        def __init__(self, call: ToolCall, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._call = call

        def render(self) -> str:
            c = self._call
            ts = _format_ts(c.start_ts)
            icon = "\u2714" if c.success else "\u2718"
            dur = _format_duration(c.elapsed_s)
            summary = f"  [{c.summary}]" if c.summary else ""
            return f" {ts}  {icon} {c.label:<28} {dur:>8}{summary}"

    class DashboardScreen(Screen):
        """Live activity dashboard — default screen."""

        BINDINGS = [
            Binding("q", "quit", "Quit"),
            Binding("s", "session", "Session View"),
            Binding("j", "cursor_down", "Down", show=False),
            Binding("k", "cursor_up", "Up", show=False),
            Binding("enter", "drill_down", "Detail"),
        ]

        def compose(self) -> ComposeResult:
            yield Header()
            yield Container(
                Vertical(id="active-panel"),
                VerticalScroll(id="completed-panel"),
                id="dashboard-body",
            )
            yield Footer()

        _active_ids: set[str] = set()
        _completed_count: int = 0

        def update_display(self, data: WorkshopData) -> None:
            """Refresh the dashboard, diffing data to avoid full rebuilds."""
            self._update_active_panel(data)
            self._update_completed_panel(data)

            # Update title with stats
            app = self.app
            if isinstance(app, WorkshopApp):
                errs = f" | {data.error_count} errors" if data.error_count else ""
                app.sub_title = f"{data.total_calls} calls{errs}"

        def _update_active_panel(self, data: WorkshopData) -> None:
            """Diff active calls and only rebuild when the set changes."""
            current_ids = set(data.active.keys())
            if current_ids == self._active_ids:
                # Active widgets auto-refresh their spinners/elapsed via auto_refresh
                return

            self._active_ids = current_ids
            active_panel = self.query_one("#active-panel", Vertical)
            active_panel.remove_children()
            if data.active:
                active_panel.mount(Label(" Active \u2500" * 4, classes="section-header"))
                for call in data.active.values():
                    active_panel.mount(ActiveToolWidget(call))
            else:
                active_panel.mount(Label(" No active tools", classes="dim"))

        def _update_completed_panel(self, data: WorkshopData) -> None:
            """Append only new completed items instead of rebuilding."""
            new_count = len(data.completed)
            if new_count == self._completed_count:
                return

            completed_panel = self.query_one("#completed-panel", VerticalScroll)

            if self._completed_count == 0:
                # First population — mount header + all items
                completed_panel.remove_children()
                recent = data.completed[-data.max_done :]
                if recent:
                    completed_panel.mount(Label(" History \u2500" * 4, classes="section-header"))
                    for i, call in enumerate(reversed(recent)):
                        completed_panel.mount(CompletedToolRow(call, id=f"completed-{i}"))
                else:
                    completed_panel.mount(Label(" No completed calls yet", classes="dim"))
            else:
                # Incremental — append new items after the header
                new_items = data.completed[self._completed_count :]
                # Remove "no completed calls" placeholder if present
                placeholders = completed_panel.query(".dim")
                for p in placeholders:
                    p.remove()
                # Add header if this is the first batch after placeholder
                if self._completed_count == 0 and new_items:
                    completed_panel.mount(Label(" History \u2500" * 4, classes="section-header"))
                # Mount new rows at the top (after header)
                header = completed_panel.query(".section-header")
                after_widget = header.first() if header else None
                for call in reversed(new_items):
                    idx = new_count - 1  # unique enough id
                    new_count -= 1
                    row = CompletedToolRow(call, id=f"completed-{idx}")
                    if after_widget is not None:
                        completed_panel.mount(row, after=after_widget)
                    else:
                        completed_panel.mount(row)
                # Trim if over max
                all_rows = list(completed_panel.query("CompletedToolRow"))
                if len(all_rows) > data.max_done:
                    for row in all_rows[data.max_done :]:
                        row.remove()

            self._completed_count = len(data.completed)

        def action_session(self) -> None:
            app = self.app
            if isinstance(app, WorkshopApp):
                from dazzle.mcp.server.workshop_screens import SessionScreen

                self.app.push_screen(SessionScreen())

        def action_drill_down(self) -> None:
            """Drill into the selected completed call."""
            app = self.app
            if not isinstance(app, WorkshopApp):
                return
            # Find the focused CompletedToolRow
            focused = self.focused
            if isinstance(focused, CompletedToolRow):
                from dazzle.mcp.server.workshop_screens import CallDetailScreen

                self.app.push_screen(CallDetailScreen(focused._call))

        def action_cursor_down(self) -> None:
            self.focus_next()

        def action_cursor_up(self) -> None:
            self.focus_previous()

        def action_quit(self) -> None:
            self.app.exit()

    class WorkshopApp(App):
        """Dazzle Workshop — MCP Activity Observer."""

        TITLE = "Dazzle Workshop"
        CSS = """
        #dashboard-body {
            height: 1fr;
        }
        #active-panel {
            height: auto;
            max-height: 40%;
            padding: 0 1;
        }
        #completed-panel {
            height: 1fr;
            padding: 0 1;
        }
        .section-header {
            color: $accent;
            text-style: bold;
        }
        .dim {
            color: $text-muted;
        }
        ActiveToolWidget {
            height: auto;
            padding: 0 0 0 1;
        }
        CompletedToolRow {
            height: 1;
        }
        CompletedToolRow:focus {
            background: $accent 20%;
        }
        """

        def __init__(
            self,
            db_path: Path,
            project_name: str = "unknown",
            *,
            max_done: int = DEFAULT_TAIL,
            bell: bool = False,
        ) -> None:
            super().__init__()
            self._db_path = db_path
            self.sub_title = project_name
            self.data = WorkshopData(max_done=max_done, bell=bell)
            self._poll_timer: Timer | None = None
            self._conn: sqlite3.Connection | None = None

        def _get_conn(self) -> sqlite3.Connection:
            """Return (and cache) a persistent SQLite connection."""
            if self._conn is None:
                self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
            return self._conn

        def on_mount(self) -> None:
            """Start polling and load initial data."""
            # Ingest existing events
            for entry in read_new_entries_db(self._db_path, self.data, conn=self._get_conn()):
                self.data.ingest(entry)
            self._update_dashboard()
            # Start poll timer
            self._poll_timer = self.set_interval(POLL_INTERVAL_S, self._poll)

        def _poll(self) -> None:
            """Poll SQLite for new events."""
            try:
                conn = self._get_conn()
            except Exception:
                # Connection went stale — reset and retry next cycle
                self._conn = None
                return
            new_entries = read_new_entries_db(self._db_path, self.data, conn=conn)
            if new_entries:
                for entry in new_entries:
                    self.data.ingest(entry)
                self._update_dashboard()
                # Bell on errors
                if self.data.bell and any(e.get("type") == TYPE_ERROR for e in new_entries):
                    self.bell()

        def _update_dashboard(self) -> None:
            """Refresh the dashboard screen if it's active."""
            screen = self.screen
            if isinstance(screen, DashboardScreen):
                screen.update_display(self.data)

        def get_default_screen(self) -> DashboardScreen:
            return DashboardScreen()

    # ── Entry-point wrappers (called by CLI) ──

    def run_workshop(
        project_dir: Path,
        *,
        info: bool = False,
        tail: int = DEFAULT_TAIL,
        bell: bool = False,
    ) -> None:
        """Entry point: resolve project info, find DB, launch Textual app."""
        project_dir = project_dir.resolve()
        project_name, version, config = _load_project_config(project_dir)

        if info:
            log_path = _resolve_log_path(project_dir, config)
            print(str(log_path))
            return

        db_path = _detect_db_path(project_dir)
        if db_path is None:
            print(
                "Error: No activity database found.\n"
                "Run the MCP server first so it creates the SQLite activity store.\n"
                f"Expected: {project_kg_db(project_dir)}"
            )
            raise SystemExit(1)

        app = WorkshopApp(db_path, project_name, max_done=tail, bell=bell)
        app.run()

else:
    # Textual not installed — provide a stub that prints an error
    def run_workshop(
        project_dir: Path,
        *,
        info: bool = False,
        tail: int = DEFAULT_TAIL,
        bell: bool = False,
    ) -> None:
        """Stub when textual is not installed."""
        if info:
            project_dir = project_dir.resolve()
            _project_name, _version, config = _load_project_config(project_dir)
            log_path = _resolve_log_path(project_dir, config)
            print(str(log_path))
            return
        print("Workshop TUI requires the 'workshop' extra:\n  pip install dazzle-dsl[workshop]")
        raise SystemExit(1)


# ── Config helpers ───────────────────────────────────────────────────────────


def _resolve_log_path(project_dir: Path, config: dict[str, Any]) -> Path:
    """Determine log path from config or convention."""
    custom = config.get("workshop", {}).get("log")
    if custom:
        p = Path(custom)
        return p if p.is_absolute() else project_dir / p
    return project_activity_log(project_dir)


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
            logger.debug("Failed to read dazzle.toml", exc_info=True)
    return project_name, version, config


def get_log_path(project_dir: Path) -> Path:
    """Resolve the activity log path for a project.  Public API for --info."""
    project_dir = project_dir.resolve()
    _, _, config = _load_project_config(project_dir)
    return _resolve_log_path(project_dir, config)
