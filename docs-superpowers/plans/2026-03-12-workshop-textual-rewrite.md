# Workshop Textual Rewrite Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Rich-based `dazzle workshop` TUI with a Textual app supporting keyboard-driven drill-down into MCP tool call activity, and instrument the top 15 handlers with structured progress events.

**Architecture:** Textual app with three-screen stack (Dashboard → Session → CallDetail). Polls SQLite `activity_events` table via raw connection every 250ms. Handler instrumentation uses existing `ProgressContext.advance_sync()`/`log_sync()` APIs — no schema changes needed.

**Tech Stack:** Python 3.12, Textual >= 1.0.0, SQLite (existing KG database), existing ProgressContext/ActivityStore infrastructure.

**Spec:** `docs/superpowers/specs/2026-03-12-workshop-textual-rewrite-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/dazzle/mcp/server/workshop.py` | Rewrite | Textual App class, DashboardScreen, data polling layer, widgets (ActiveToolWidget, CompletedToolRow) |
| `src/dazzle/mcp/server/workshop_screens.py` | Create | SessionScreen + CallDetailScreen |
| `src/dazzle/cli/workshop.py` | Modify | Graceful degradation if textual not installed |
| `pyproject.toml` | Modify | Add `workshop` optional dependency |
| `src/dazzle/mcp/server/handlers/pipeline.py` | Modify | Add `context_json` to pipeline results |
| `src/dazzle/mcp/server/handlers/orchestration.py` | Modify | Add `context_json` to step results |
| `src/dazzle/mcp/server/handlers/stories.py` | Modify | Add progress to coverage handlers |
| `src/dazzle/mcp/server/handlers/dsl_test.py` | Modify | Add progress to test run handlers |
| `src/dazzle/mcp/server/handlers/sentinel.py` | Modify | Add progress to scan handler |
| `src/dazzle/mcp/server/handlers/composition.py` | Modify | Add progress to audit handler |
| `src/dazzle/mcp/server/handlers/dsl.py` | Modify | Add progress to validate/fidelity handlers |
| `src/dazzle/mcp/server/handlers/discovery/missions.py` | Modify | Add progress to discovery.run |
| `src/dazzle/mcp/server/handlers/discovery/compiler.py` | Modify | Add progress to discovery.compile |
| `src/dazzle/mcp/server/handlers/discovery/emitter.py` | Modify | Add progress to discovery.emit |
| `src/dazzle/mcp/server/handlers/e2e_testing.py` | Modify | Add progress to e2e_test.run |
| `src/dazzle/mcp/server/handlers/process.py` | Modify | Add progress to coverage handler |
| `src/dazzle/mcp/server/handlers/nightly.py` | Modify | Add progress to nightly.run |
| `tests/unit/test_workshop_data.py` | Create | Data layer + ToolCall/WorkshopData tests |
| `tests/unit/test_workshop_screens.py` | Create | Screen data model + integration tests |
| `tests/unit/test_handler_instrumentation.py` | Create | Progress emission tests |

---

## Chunk 1: Foundation

### Task 1: Add Textual dependency

**Files:**
- Modify: `pyproject.toml:49-151` (optional-dependencies section)

- [ ] **Step 1: Add `workshop` optional dependency group**

In `pyproject.toml`, after the `viewport` group (around line 119), add:

```toml
# Workshop TUI (Textual-based interactive display)
workshop = [
    "textual>=1.0.0",
]
```

- [ ] **Step 2: Add `workshop` to the `dev` extras**

In the `dev` list (lines 61-79), add `"textual>=1.0.0"` so contributors get it automatically.

- [ ] **Step 3: Verify installation**

Run: `pip install -e ".[workshop]" && python -c "import textual; print(textual.__version__)"`
Expected: Version >= 1.0.0 prints successfully.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat(workshop): add textual dependency for TUI rewrite"
```

---

### Task 2: Extract data layer from workshop.py

The current `workshop.py` has ~200 lines of data layer code (SQLite polling, entry parsing, config loading) interleaved with ~450 lines of Rich rendering. Extract the data layer into the new Textual app file so it can be reused.

**Files:**
- Create: `tests/unit/test_workshop_data.py`
- Modify: `src/dazzle/mcp/server/workshop.py`

- [ ] **Step 1: Write tests for data layer functions**

Create `tests/unit/test_workshop_data.py` with tests for the data functions that will survive the rewrite:

```python
"""Tests for workshop data layer and widgets."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest


class TestDbRowToEntry:
    """Test _db_row_to_entry conversion."""

    def test_minimal_row(self):
        from dazzle.mcp.server.workshop import _db_row_to_entry

        row = {"event_type": "tool_start", "tool": "dsl", "ts": "2026-03-12T10:00:00"}
        entry = _db_row_to_entry(row)
        assert entry == {"type": "tool_start", "tool": "dsl", "ts": "2026-03-12T10:00:00"}

    def test_full_row(self):
        from dazzle.mcp.server.workshop import _db_row_to_entry

        row = {
            "event_type": "progress",
            "tool": "pipeline",
            "ts": "2026-03-12T10:00:00",
            "operation": "run",
            "success": 1,
            "duration_ms": 1234.5,
            "error": None,
            "warnings": 2,
            "progress_current": 3,
            "progress_total": 8,
            "message": "Running step 3",
            "level": "info",
            "source": "mcp",
            "context_json": '{"steps": 8}',
        }
        entry = _db_row_to_entry(row)
        assert entry["type"] == "progress"
        assert entry["current"] == 3
        assert entry["total"] == 8
        assert entry["warnings"] == 2
        assert entry["context_json"] == '{"steps": 8}'


class TestDetectDbPath:
    """Test _detect_db_path with real SQLite."""

    def test_returns_none_when_no_file(self, tmp_path):
        from dazzle.mcp.server.workshop import _detect_db_path

        # _detect_db_path uses project_kg_db() which resolves .dazzle/kg.db
        # We test via a path that doesn't exist
        assert _detect_db_path(tmp_path / "nonexistent") is None

    def test_returns_none_when_no_table(self, tmp_path):
        from dazzle.mcp.server.workshop import _detect_db_path

        # Create a .dazzle/kg.db without the activity_events table
        dazzle_dir = tmp_path / ".dazzle"
        dazzle_dir.mkdir()
        db_path = dazzle_dir / "kg.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE other_table (id INTEGER)")
        conn.close()
        assert _detect_db_path(tmp_path) is None
```

- [ ] **Step 2: Run tests to verify they pass with current code**

Run: `PYTHONPATH=src pytest tests/unit/test_workshop_data.py -v`
Expected: All tests PASS (they test existing functions).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_workshop_data.py
git commit -m "test(workshop): add data layer tests before Textual rewrite"
```

---

### Task 3: Rewrite workshop.py as Textual app with DashboardScreen

Replace the Rich renderer with a Textual app. Keep all data layer functions (`read_new_entries_db`, `_db_row_to_entry`, `_detect_db_path`, `_load_project_config`, `_resolve_log_path`, `get_log_path`). Replace `WorkshopState`, `ActiveTool`, `CompletedTool`, `watch()`, `render_workshop()`, and `run_workshop()`.

**Files:**
- Rewrite: `src/dazzle/mcp/server/workshop.py`
- Test: `tests/unit/test_workshop_data.py` (existing tests still pass)

- [ ] **Step 1: Rewrite workshop.py**

Replace the file contents. Keep the data layer section (lines 209-293 and 588-665 of the original) and rewrite everything else:

```python
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
from datetime import UTC, datetime
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


def read_new_entries_db(db_path: Path, data: WorkshopData) -> list[dict[str, Any]]:
    """Read new activity events from the SQLite database.

    Uses cursor-based polling via ``_last_event_id``.
    Returns entries as dicts compatible with ``WorkshopData.ingest()``.
    """
    if not db_path.exists():
        return []

    entries: list[dict[str, Any]] = []
    try:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM activity_events WHERE id > ? ORDER BY id ASC LIMIT 200",
                (data._last_event_id,),
            ).fetchall()
            for row in rows:
                entry = _db_row_to_entry(dict(row))
                entries.append(entry)
                data._last_event_id = row["id"]
        finally:
            conn.close()
    except Exception:
        logger.debug("Failed to poll activity events", exc_info=True)
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
    from textual.reactive import reactive
    from textual.screen import Screen
    from textual.timer import Timer
    from textual.widgets import Footer, Header, Label, Static

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False


if TEXTUAL_AVAILABLE:

    class ActiveToolWidget(Static):
        """Renders a single active (in-flight) tool call.

        Uses auto_refresh=0.25 so the spinner animates and elapsed time
        updates even when no new events arrive.
        """

        DEFAULT_CSS = "ActiveToolWidget { auto-refresh: 0.25; }"

        def __init__(self, call: ToolCall, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self._call = call

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

        selected_idx: reactive[int] = reactive(0)

        def compose(self) -> ComposeResult:
            yield Header()
            yield Container(
                Vertical(id="active-panel"),
                VerticalScroll(id="completed-panel"),
                id="dashboard-body",
            )
            yield Footer()

        def update_display(self, data: WorkshopData) -> None:
            """Refresh the dashboard from current data."""
            # Active tools
            active_panel = self.query_one("#active-panel", Vertical)
            active_panel.remove_children()
            if data.active:
                active_panel.mount(Label(" Active \u2500" * 4, classes="section-header"))
                for call in data.active.values():
                    active_panel.mount(ActiveToolWidget(call))
            else:
                active_panel.mount(Label(" No active tools", classes="dim"))

            # Completed tools
            completed_panel = self.query_one("#completed-panel", VerticalScroll)
            completed_panel.remove_children()
            recent = data.completed[-data.max_done:]
            if recent:
                completed_panel.mount(Label(" History \u2500" * 4, classes="section-header"))
                for i, call in enumerate(reversed(recent)):
                    row = CompletedToolRow(call, id=f"completed-{i}")
                    completed_panel.mount(row)
            else:
                completed_panel.mount(Label(" No completed calls yet", classes="dim"))

            # Update title with stats
            app = self.app
            if isinstance(app, WorkshopApp):
                errs = f" | {data.error_count} errors" if data.error_count else ""
                app.sub_title = (
                    f"{data.total_calls} calls{errs}"
                )

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
            recent = list(reversed(app.data.completed[-app.data.max_done:]))
            if 0 <= self.selected_idx < len(recent):
                from dazzle.mcp.server.workshop_screens import CallDetailScreen

                self.app.push_screen(CallDetailScreen(recent[self.selected_idx]))

        def action_cursor_down(self) -> None:
            app = self.app
            if isinstance(app, WorkshopApp):
                max_idx = min(len(app.data.completed), app.data.max_done) - 1
                self.selected_idx = min(self.selected_idx + 1, max(0, max_idx))

        def action_cursor_up(self) -> None:
            self.selected_idx = max(0, self.selected_idx - 1)

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

        def on_mount(self) -> None:
            """Start polling and load initial data."""
            # Ingest existing events
            for entry in read_new_entries_db(self._db_path, self.data):
                self.data.ingest(entry)
            self._update_dashboard()
            # Start poll timer
            self._poll_timer = self.set_interval(POLL_INTERVAL_S, self._poll)

        def _poll(self) -> None:
            """Poll SQLite for new events."""
            new_entries = read_new_entries_db(self._db_path, self.data)
            if new_entries:
                for entry in new_entries:
                    self.data.ingest(entry)
                self._update_dashboard()
                # Bell on errors
                if self.data.bell and any(
                    e.get("type") == TYPE_ERROR for e in new_entries
                ):
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
            project_name, version, config = _load_project_config(project_dir)
            log_path = _resolve_log_path(project_dir, config)
            print(str(log_path))
            return
        print(
            "Workshop TUI requires the 'workshop' extra:\n"
            "  pip install dazzle-dsl[workshop]"
        )
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
```

- [ ] **Step 2: Verify existing data layer tests still pass**

Run: `PYTHONPATH=src pytest tests/unit/test_workshop_data.py -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add src/dazzle/mcp/server/workshop.py
git commit -m "feat(workshop): rewrite TUI from Rich to Textual with DashboardScreen"
```

---

### Task 4: Create SessionScreen and CallDetailScreen

**Files:**
- Create: `src/dazzle/mcp/server/workshop_screens.py`
- Create: `tests/unit/test_workshop_screens.py`

- [ ] **Step 1: Create workshop_screens.py**

```python
"""Workshop drill-down screens: SessionScreen and CallDetailScreen."""

from __future__ import annotations

import time
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Collapsible, Footer, Header, Label, Static

from dazzle.mcp.server.workshop import (
    ToolCall,
    WorkshopApp,
    _format_duration,
    _format_ts,
)


class ToolCallRow(Static):
    """A single tool call row in the session view."""

    can_focus = True

    def __init__(self, call: ToolCall, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._call = call

    def render(self) -> str:
        c = self._call
        ts = _format_ts(c.start_ts)
        if c.finished:
            icon = "\u2714" if c.success else "\u2718"
        else:
            frames = "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827"
            idx = int(time.monotonic() * 8) % len(frames)
            icon = frames[idx]
        dur = _format_duration(c.elapsed_s)
        summary = f"  [{c.summary}]" if c.summary else ""
        return f" {ts}  {icon} {c.label:<28} {dur:>8}{summary}"


class SessionScreen(Screen):
    """All tool calls in the current observation window, grouped by tool."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("enter", "drill_down", "Detail"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="session-body")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_groups()

    def _refresh_groups(self) -> None:
        app = self.app
        if not isinstance(app, WorkshopApp):
            return

        body = self.query_one("#session-body", VerticalScroll)
        body.remove_children()

        groups = app.data.calls_grouped_by_tool()
        if not groups:
            body.mount(Label(" No tool calls recorded yet", classes="dim"))
            return

        for tool_name, calls in sorted(groups.items()):
            total_dur = sum(c.elapsed_s for c in calls)
            header_text = (
                f"{tool_name} ({len(calls)} calls, "
                f"{_format_duration(total_dur)} total)"
            )
            collapsible = Collapsible(title=header_text, collapsed=False)
            for call in reversed(calls):
                collapsible.compose_add_child(ToolCallRow(call))
            body.mount(collapsible)

    def action_drill_down(self) -> None:
        """Drill into the focused tool call row."""
        focused = self.focused
        if isinstance(focused, ToolCallRow):
            self.app.push_screen(CallDetailScreen(focused._call))

    def action_cursor_down(self) -> None:
        self.focus_next()

    def action_cursor_up(self) -> None:
        self.focus_previous()


class CallDetailScreen(Screen):
    """Full detail view for a single tool call."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back"),
    ]

    def __init__(self, call: ToolCall, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._call = call

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="detail-body")
        yield Footer()

    def on_mount(self) -> None:
        body = self.query_one("#detail-body", VerticalScroll)
        c = self._call

        # Header
        ts = _format_ts(c.start_ts)
        dur = _format_duration(c.elapsed_s)
        icon = "\u2714" if c.success else "\u2718" if c.success is not None else "\u2026"
        body.mount(Label(
            f" {c.label}  \u2500  {ts}  \u2500  {dur}  \u2500  {icon}",
            classes="detail-header",
        ))

        # Purpose
        body.mount(Label("\n Purpose", classes="section-header"))
        body.mount(Label(f"   {c.purpose}"))

        # Progress Timeline
        if c.events:
            body.mount(Label("\n Progress Timeline", classes="section-header"))
            start_ts = c.start_mono
            start_wall = c.start_ts
            for evt in c.events:
                etype = evt.get("type", "")
                msg = evt.get("message", "")
                # Use actual event timestamps for relative time
                evt_ts = evt.get("ts", "")
                rel = _relative_time(start_wall, evt_ts)

                # Format progress info
                progress = ""
                if evt.get("current") is not None and evt.get("total"):
                    progress = f"[{evt['current']}/{evt['total']}] "

                icon = ""
                if etype == "tool_end":
                    icon = "\u2714 " if evt.get("success", True) else "\u2718 "

                body.mount(Label(f"   {rel}  {icon}{progress}{msg}"))

        # Summary
        if c.summary:
            body.mount(Label("\n Summary", classes="section-header"))
            body.mount(Label(f"   {c.summary}"))

        # Error
        if c.error:
            body.mount(Label("\n Error", classes="section-header"))
            body.mount(Label(f"   {c.error}", classes="error-text"))
```

- [ ] **Step 2: Write screen navigation tests**

Create `tests/unit/test_workshop_screens.py`:

```python
"""Tests for workshop screen data and navigation logic."""

from __future__ import annotations

import pytest

from dazzle.mcp.server.workshop import ToolCall, WorkshopData, _format_duration, _format_ts


class TestToolCall:
    def test_label_with_operation(self):
        call = ToolCall(
            call_id="dsl.validate.t1", tool="dsl", operation="validate",
            start_ts="2026-03-12T10:00:00", start_mono=0.0,
        )
        assert call.label == "dsl.validate"

    def test_label_without_operation(self):
        call = ToolCall(
            call_id="dsl.None.t1", tool="dsl", operation=None,
            start_ts="2026-03-12T10:00:00", start_mono=0.0,
        )
        assert call.label == "dsl"

    def test_purpose_from_first_log_event(self):
        call = ToolCall(
            call_id="test.t1", tool="test", operation="run",
            start_ts="t1", start_mono=0.0,
            events=[
                {"type": "log", "message": "Running quality pipeline"},
                {"type": "progress", "message": "Step 2"},
            ],
        )
        assert call.purpose == "Running quality pipeline"

    def test_purpose_fallback_to_label(self):
        call = ToolCall(
            call_id="test.t1", tool="test", operation="run",
            start_ts="t1", start_mono=0.0,
        )
        assert call.purpose == "test.run"

    def test_summary_from_context_json(self):
        call = ToolCall(
            call_id="test.t1", tool="test", operation="run",
            start_ts="t1", start_mono=0.0,
            context_json='{"summary": "8/8 steps passed"}',
        )
        assert call.summary == "8/8 steps passed"

    def test_summary_from_context_json_keys(self):
        call = ToolCall(
            call_id="test.t1", tool="test", operation="run",
            start_ts="t1", start_mono=0.0,
            context_json='{"passed": 5, "failed": 1}',
        )
        assert "passed=5" in call.summary
        assert "failed=1" in call.summary


class TestWorkshopData:
    def test_ingest_tool_start(self):
        data = WorkshopData()
        call = data.ingest({"type": "tool_start", "tool": "dsl", "operation": "validate", "ts": "t1"})
        assert call is not None
        assert len(data.active) == 1
        assert data.total_calls == 1

    def test_ingest_tool_end(self):
        data = WorkshopData()
        data.ingest({"type": "tool_start", "tool": "dsl", "operation": "validate", "ts": "t1"})
        call = data.ingest({
            "type": "tool_end", "tool": "dsl", "operation": "validate",
            "ts": "t2", "success": True, "duration_ms": 500,
        })
        assert call is not None
        assert call.finished
        assert len(data.active) == 0
        assert len(data.completed) == 1

    def test_ingest_progress_updates_call(self):
        data = WorkshopData()
        data.ingest({"type": "tool_start", "tool": "pipeline", "operation": "run", "ts": "t1"})
        call = data.ingest({
            "type": "progress", "tool": "pipeline", "operation": "run",
            "current": 3, "total": 8, "message": "Step 3",
        })
        assert call is not None
        assert call.progress_current == 3
        assert call.progress_total == 8

    def test_calls_grouped_by_tool(self):
        data = WorkshopData()
        data.ingest({"type": "tool_start", "tool": "dsl", "operation": "validate", "ts": "t1"})
        data.ingest({"type": "tool_end", "tool": "dsl", "operation": "validate", "ts": "t2", "success": True})
        data.ingest({"type": "tool_start", "tool": "story", "operation": "coverage", "ts": "t3"})
        data.ingest({"type": "tool_end", "tool": "story", "operation": "coverage", "ts": "t4", "success": True})
        data.ingest({"type": "tool_start", "tool": "dsl", "operation": "lint", "ts": "t5"})
        data.ingest({"type": "tool_end", "tool": "dsl", "operation": "lint", "ts": "t6", "success": True})

        groups = data.calls_grouped_by_tool()
        assert len(groups["dsl"]) == 2
        assert len(groups["story"]) == 1

    def test_error_count_tracked(self):
        data = WorkshopData()
        data.ingest({"type": "tool_start", "tool": "dsl", "operation": "validate", "ts": "t1"})
        data.ingest({
            "type": "tool_end", "tool": "dsl", "operation": "validate",
            "ts": "t2", "success": False, "error": "parse error",
        })
        assert data.error_count == 1


class TestFormatHelpers:
    def test_format_ts_iso(self):
        assert _format_ts("2026-03-12T10:30:45.123") == "10:30:45"

    def test_format_ts_empty(self):
        assert _format_ts("") == "??:??:??"

    def test_format_duration_subsecond(self):
        assert _format_duration(0.05) == "<0.1s"

    def test_format_duration_seconds(self):
        assert _format_duration(12.3) == "12.3s"

    def test_format_duration_minutes(self):
        assert _format_duration(125.0) == "2m5s"
```

- [ ] **Step 3: Run all workshop tests**

Run: `PYTHONPATH=src pytest tests/unit/test_workshop_data.py tests/unit/test_workshop_screens.py -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/workshop_screens.py tests/unit/test_workshop_screens.py
git commit -m "feat(workshop): add SessionScreen and CallDetailScreen with drill-down navigation"
```

---

### Task 5: Update CLI entry point

**Files:**
- Modify: `src/dazzle/cli/workshop.py`

- [ ] **Step 1: Update CLI to handle missing textual gracefully**

The `run_workshop` function already has the graceful degradation stub (from Task 3). The CLI just needs to import and call it as before. But we should verify the import path works and add `--explore` routing:

```python
"""Workshop CLI command — live TUI for MCP activity."""

import logging
from pathlib import Path

import typer


def workshop_command(
    project_dir: Path = typer.Option(  # noqa: B008
        ".",
        "--project-dir",
        "-p",
        help="Project root directory (default: current directory)",
    ),
    info: bool = typer.Option(
        False,
        "--info",
        help="Print the resolved activity log path and exit.",
    ),
    tail: int = typer.Option(
        25,
        "--tail",
        "-n",
        help="Number of completed entries on dashboard (default: 25).",
    ),
    bell: bool = typer.Option(
        False,
        "--bell",
        help="Ring terminal bell on errors.",
    ),
    explore: bool = typer.Option(
        False,
        "--explore",
        help="Open the Activity Explorer web UI instead of the TUI.",
    ),
    port: int = typer.Option(
        8877,
        "--port",
        help="Port for the Activity Explorer HTTP server (used with --explore).",
    ),
) -> None:
    """Watch MCP activity in a live workshop view."""
    # Suppress logging before importing MCP modules — the server __init__
    # calls logging.basicConfig(level=DEBUG) which floods stderr with handler
    # registration noise.
    logging.disable(logging.CRITICAL)

    if explore:
        from dazzle.mcp.server.explorer import run_explorer

        logging.disable(logging.NOTSET)
        run_explorer(Path(project_dir).resolve(), port=port)
    else:
        from dazzle.mcp.server.workshop import run_workshop

        logging.disable(logging.NOTSET)
        run_workshop(project_dir, info=info, tail=tail, bell=bell)
```

The main change is `tail` default from 20 → 25 to match the new `DEFAULT_TAIL`.

- [ ] **Step 2: Run existing tests to check nothing broke**

Run: `PYTHONPATH=src pytest tests/unit/test_workshop_data.py tests/unit/test_workshop_screens.py -v`
Expected: All PASS.

- [ ] **Step 3: Commit**

```bash
git add src/dazzle/cli/workshop.py
git commit -m "fix(workshop): update CLI default tail to 25, match Textual rewrite"
```

---

## Chunk 2: Handler Instrumentation

### Task 6: Instrument pipeline.run and orchestration layer

The pipeline already calls `progress.advance_sync()` via `run_steps_sequential()` in `orchestration.py`. We need to add `context_json` to the final result so the workshop can show a structured summary.

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/orchestration.py:116-149`
- Modify: `src/dazzle/mcp/server/handlers/pipeline.py:28-78`
- Test: `tests/unit/test_handler_instrumentation.py`

- [ ] **Step 1: Write failing test for pipeline context_json**

Create `tests/unit/test_handler_instrumentation.py`:

```python
"""Tests for handler progress instrumentation."""

from __future__ import annotations

import json

import pytest


class TestPipelineInstrumentation:
    """Verify pipeline.run emits structured context_json."""

    def test_pipeline_result_has_summary(self):
        """Pipeline JSON result should include a 'summary' key."""
        # We test the aggregate_results function directly since it produces
        # the final JSON string.
        from dazzle.mcp.server.handlers.orchestration import aggregate_results

        step_results = [
            {"step": 1, "operation": "dsl(validate)", "status": "passed", "duration_ms": 100},
            {"step": 2, "operation": "dsl(lint)", "status": "passed", "duration_ms": 200},
        ]
        errors: list[str] = []
        import time
        start = time.monotonic() - 0.5  # simulate 500ms ago

        result_json = aggregate_results(step_results, errors, start, detail="metrics")
        result = json.loads(result_json)
        assert "summary" in result
        assert result["summary"]["total_steps"] == 2
        assert result["summary"]["passed"] == 2
```

- [ ] **Step 2: Run test to verify current behavior**

Run: `PYTHONPATH=src pytest tests/unit/test_handler_instrumentation.py::TestPipelineInstrumentation -v`

Check: If the test already passes (aggregate_results already includes summary), move on. If it fails, we need to add it.

- [ ] **Step 3: Add context_json to orchestration step results**

In `src/dazzle/mcp/server/handlers/orchestration.py`, find `run_step()` (around line 42). After the step completes successfully, add context_json to the activity log `tool_end` event:

Find the `tool_end` event logging section and ensure `context_json` is included with a compact summary of the step result (status, duration, any counts).

- [ ] **Step 4: Run tests**

Run: `PYTHONPATH=src pytest tests/unit/test_handler_instrumentation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/mcp/server/handlers/orchestration.py src/dazzle/mcp/server/handlers/pipeline.py tests/unit/test_handler_instrumentation.py
git commit -m "feat(workshop): add context_json to pipeline/orchestration results"
```

---

### Task 7: Instrument story.coverage and story.rule_coverage

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/stories.py`
- Test: `tests/unit/test_handler_instrumentation.py` (extend)

- [ ] **Step 1: Read story coverage handler**

Read `src/dazzle/mcp/server/handlers/stories.py` and locate the `story_coverage_handler` and `story_rule_coverage_handler` functions. Identify where they iterate over stories/rules.

- [ ] **Step 2: Add progress calls**

For `story_coverage_handler`:
- At function start: `progress.log_sync("Evaluating story coverage")`
- In the story iteration loop: `progress.advance_sync(i, total, f"Evaluating {story.id}")`
- Before return: set `context_json` in the result with coverage percentage

For `story_rule_coverage_handler`:
- At function start: `progress.log_sync("Evaluating rule coverage")`
- In the rule iteration loop: `progress.advance_sync(i, total, f"Checking rule {rule.id}")`

Pattern for extracting progress (all handlers follow this):
```python
progress = extract_progress(args)
```

- [ ] **Step 3: Run story tests to verify nothing broke**

Run: `PYTHONPATH=src pytest tests/ -k "story" -m "not e2e" --timeout=30 -x`
Expected: All story-related tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/stories.py
git commit -m "feat(workshop): instrument story.coverage with progress events"
```

---

### Task 8: Instrument dsl_test.run_all and dsl_test.run

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/dsl_test.py`

- [ ] **Step 1: Read dsl_test handlers**

Read `src/dazzle/mcp/server/handlers/dsl_test.py` and find `run_all_dsl_tests_handler` and `run_dsl_test_handler`. Locate iteration loops.

- [ ] **Step 2: Add progress calls to run_all**

For `run_all_dsl_tests_handler`:
- `progress.log_sync("Running all DSL tests")`
- Per test file: `progress.advance_sync(i, total, f"Running {test_file}")`
- On completion: include pass/fail counts in result

For `run_dsl_test_handler` (single test):
- `progress.log_sync(f"Running test {test_id}")`
- On completion: include result in context_json

- [ ] **Step 3: Run dsl_test tests**

Run: `PYTHONPATH=src pytest tests/ -k "dsl_test" -m "not e2e" --timeout=30 -x`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/dsl_test.py
git commit -m "feat(workshop): instrument dsl_test handlers with progress events"
```

---

### Task 9: Instrument sentinel.scan

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/sentinel.py`

- [ ] **Step 1: Read sentinel handler**

Read `src/dazzle/mcp/server/handlers/sentinel.py` and locate `scan_handler`. Find where it iterates over check categories or agents.

- [ ] **Step 2: Add progress calls**

- `progress.log_sync("Starting sentinel scan")`
- Per agent/check: `progress.advance_sync(i, total, f"Running {agent_id} checks")`
- On completion: include finding counts in context_json

- [ ] **Step 3: Run sentinel tests**

Run: `PYTHONPATH=src pytest tests/ -k "sentinel" -m "not e2e" --timeout=30 -x`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/sentinel.py
git commit -m "feat(workshop): instrument sentinel.scan with progress events"
```

---

### Task 10: Instrument composition.audit

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/composition.py`

- [ ] **Step 1: Read composition handler**

Read `src/dazzle/mcp/server/handlers/composition.py` and locate `audit_handler`. Find where it iterates over surfaces.

- [ ] **Step 2: Add progress calls**

- `progress.log_sync("Auditing composition")`
- Per surface: `progress.advance_sync(i, total, f"Auditing surface {surface.id}")`

- [ ] **Step 3: Run composition tests**

Run: `PYTHONPATH=src pytest tests/ -k "composition" -m "not e2e" --timeout=30 -x`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/composition.py
git commit -m "feat(workshop): instrument composition.audit with progress events"
```

---

### Task 11: Instrument e2e_test.run

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/e2e_testing.py`

- [ ] **Step 1: Read e2e_test handler**

Read `src/dazzle/mcp/server/handlers/e2e_testing.py` and locate `run_e2e_test_handler`. Find where it iterates over test scenarios.

- [ ] **Step 2: Add progress calls**

- `progress.log_sync("Running E2E tests")`
- Per scenario: `progress.advance_sync(i, total, f"Running scenario {scenario}")`
- On completion: include pass/fail counts in `context_json`

- [ ] **Step 3: Run e2e_test tests (unit only)**

Run: `PYTHONPATH=src pytest tests/ -k "e2e_test" -m "not e2e" --timeout=30 -x`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/e2e_testing.py
git commit -m "feat(workshop): instrument e2e_test.run with progress events"
```

---

### Task 12: Instrument dsl.validate and dsl.fidelity

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/dsl.py`

- [ ] **Step 1: Read dsl handlers**

Read `src/dazzle/mcp/server/handlers/dsl.py` and locate `validate_handler` and `fidelity_handler`.

- [ ] **Step 2: Add progress calls**

For `validate_handler`:
- On completion: `progress.log_sync(f"Validated: {n_entities} entities, {n_surfaces} surfaces")`

For `fidelity_handler`:
- `progress.log_sync("Scoring surface fidelity")`
- Per surface: `progress.advance_sync(i, total, f"Scoring {surface.id}")`

- [ ] **Step 3: Run dsl tests**

Run: `PYTHONPATH=src pytest tests/ -k "test_dsl" -m "not e2e" --timeout=30 -x`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/dsl.py
git commit -m "feat(workshop): instrument dsl.validate and dsl.fidelity with progress events"
```

---

### Task 13: Instrument discovery.run, discovery.compile, discovery.emit

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/discovery/missions.py`
- Modify: `src/dazzle/mcp/server/handlers/discovery/compiler.py`
- Modify: `src/dazzle/mcp/server/handlers/discovery/emitter.py`

- [ ] **Step 1: Read discovery handlers**

Read `missions.py` (discovery.run), `compiler.py` (compile), and `emitter.py` (emit). Identify iteration points.

- [ ] **Step 2: Add progress calls**

For `discovery.run` (missions.py):
- Already has 3 log_sync calls. Add `advance_sync` with entity/surface counts where available.

For `discovery.compile` (compiler.py):
- `progress.log_sync("Compiling discovery observations")`
- Per observation group: `progress.advance_sync(i, total, f"Processing {group}")`

For `discovery.emit` (emitter.py):
- `progress.log_sync("Emitting DSL from proposals")`
- Per DSL block: `progress.advance_sync(i, total, f"Generating {block_type}")`

- [ ] **Step 3: Run discovery tests**

Run: `PYTHONPATH=src pytest tests/ -k "discovery" -m "not e2e" --timeout=30 -x`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/discovery/missions.py src/dazzle/mcp/server/handlers/discovery/compiler.py src/dazzle/mcp/server/handlers/discovery/emitter.py
git commit -m "feat(workshop): instrument discovery handlers with progress events"
```

---

### Task 14: Instrument process.coverage and nightly.run

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/process.py`
- Modify: `src/dazzle/mcp/server/handlers/nightly.py`

- [ ] **Step 1: Read handlers**

Read `process.py` for `coverage_handler` and `nightly.py` for `run_nightly_handler`. Identify iteration points.

- [ ] **Step 2: Add progress calls**

For `process.coverage`:
- `progress.log_sync("Evaluating process coverage")`
- Per process: `progress.advance_sync(i, total, f"Checking {process.id}")`

For `nightly.run`:
- `progress.log_sync("Starting nightly pipeline")`
- Per stage: `progress.advance_sync(i, total, f"Running stage {stage}")`

- [ ] **Step 3: Run tests**

Run: `PYTHONPATH=src pytest tests/ -k "process or nightly" -m "not e2e" --timeout=30 -x`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/process.py src/dazzle/mcp/server/handlers/nightly.py
git commit -m "feat(workshop): instrument process.coverage and nightly.run with progress events"
```

---

## Chunk 3: Integration & Polish

### Task 15: Integration test — synthetic events through the full stack

Verify that synthetic activity events written to SQLite show up correctly in `WorkshopData` via the polling path.

**Files:**
- Extend: `tests/unit/test_workshop_screens.py`

- [ ] **Step 1: Write integration test**

Add to `tests/unit/test_workshop_screens.py`:

```python
class TestWorkshopDataIntegration:
    """Test full polling path: SQLite → read_new_entries_db → WorkshopData.ingest."""

    def test_poll_and_ingest(self, tmp_path):
        """Write events to SQLite, poll, verify WorkshopData state."""
        import sqlite3
        from dazzle.mcp.server.workshop import WorkshopData, read_new_entries_db

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE activity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                event_type TEXT NOT NULL,
                tool TEXT NOT NULL,
                operation TEXT,
                ts TEXT,
                created_at TEXT,
                success INTEGER,
                duration_ms REAL,
                error TEXT,
                warnings INTEGER,
                progress_current INTEGER,
                progress_total INTEGER,
                message TEXT,
                level TEXT,
                context_json TEXT,
                source TEXT
            )
        """)
        # Insert a tool_start + progress + tool_end sequence
        conn.execute(
            "INSERT INTO activity_events (event_type, tool, operation, ts, source) VALUES (?, ?, ?, ?, ?)",
            ("tool_start", "pipeline", "run", "2026-03-12T10:00:00", "mcp"),
        )
        conn.execute(
            "INSERT INTO activity_events (event_type, tool, operation, ts, progress_current, progress_total, message) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("progress", "pipeline", "run", "2026-03-12T10:00:01", 3, 8, "Step 3"),
        )
        conn.execute(
            "INSERT INTO activity_events (event_type, tool, operation, ts, success, duration_ms, context_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("tool_end", "pipeline", "run", "2026-03-12T10:00:10", 1, 10000, '{"steps": 8}'),
        )
        conn.commit()
        conn.close()

        data = WorkshopData()
        entries = read_new_entries_db(db_path, data)
        assert len(entries) == 3
        for entry in entries:
            data.ingest(entry)

        assert data.total_calls == 1
        assert len(data.completed) == 1
        call = data.completed[0]
        assert call.tool == "pipeline"
        assert call.operation == "run"
        assert call.finished
        assert call.success
        assert call.duration_ms == 10000
        assert len(call.events) == 2  # progress + tool_end
```

- [ ] **Step 2: Run the integration test**

Run: `PYTHONPATH=src pytest tests/unit/test_workshop_screens.py::TestWorkshopDataIntegration -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_workshop_screens.py
git commit -m "test(workshop): add integration test for SQLite → WorkshopData polling"
```

---

### Task 16: Run full test suite and fix any breakage

**Files:**
- Any files that need fixing

- [ ] **Step 1: Run all unit tests**

Run: `PYTHONPATH=src pytest tests/ -m "not e2e" --timeout=60 -x -q`
Expected: All PASS. If any fail due to the workshop rewrite (e.g., tests importing old `WorkshopState`), fix them.

- [ ] **Step 2: Run ruff and mypy**

Run: `ruff check src/dazzle/mcp/server/workshop.py src/dazzle/mcp/server/workshop_screens.py --fix && ruff format src/dazzle/mcp/server/workshop.py src/dazzle/mcp/server/workshop_screens.py`

Run: `mypy src/dazzle/mcp/server/workshop.py src/dazzle/mcp/server/workshop_screens.py`

Fix any issues.

- [ ] **Step 3: Commit any fixes**

```bash
git add -u
git commit -m "fix(workshop): resolve lint and type errors from Textual rewrite"
```

---

### Task 17: Update CHANGELOG.md

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add entries under [Unreleased]**

Under `## [Unreleased]`, add:

```markdown
### Changed
- `dazzle workshop` rewritten from Rich to Textual TUI with keyboard-driven drill-down
  - DashboardScreen: live active tools + recent completed history
  - SessionScreen: all calls grouped by tool, collapsible groups
  - CallDetailScreen: full progress timeline for a single call
  - Navigation: Enter to drill in, Esc to go back, j/k for movement
- Workshop now requires `textual>=1.0.0` via optional `workshop` extra

### Added
- Handler progress instrumentation: 15 handlers now emit structured progress events
  - pipeline.run, story.coverage, dsl_test.run_all, sentinel.scan, composition.audit,
    dsl.validate, dsl.fidelity, discovery.run/compile/emit, process.coverage, nightly.run
- `context_json` on tool completion events for structured summaries in workshop
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for workshop Textual rewrite"
```
