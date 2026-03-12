"""Workshop drill-down screens: SessionScreen and CallDetailScreen."""

from __future__ import annotations

import json
import time
from typing import Any

try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import VerticalScroll
    from textual.screen import Screen
    from textual.widgets import Collapsible, Footer, Header, Label, Static

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False

from dazzle.mcp.server.workshop import (
    ToolCall,
    _format_duration,
    _format_ts,
    _relative_time,
)

if not TEXTUAL_AVAILABLE:
    # Module imported without textual — provide empty stubs so the import
    # succeeds but the classes are unusable (CLI guards prevent reaching here).
    class ToolCallRow:  # type: ignore[no-redef,unused-ignore]
        pass

    class SessionScreen:  # type: ignore[no-redef,unused-ignore]
        pass

    class CallDetailScreen:  # type: ignore[no-redef,unused-ignore]
        pass


if TEXTUAL_AVAILABLE:
    from dazzle.mcp.server.workshop import WorkshopApp

    class ToolCallRow(Static):  # type: ignore[no-redef]
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

    class SessionScreen(Screen):  # type: ignore[no-redef]
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
                    f"{tool_name} ({len(calls)} calls, {_format_duration(total_dur)} total)"
                )
                rows = [ToolCallRow(call) for call in reversed(calls)]  # type: ignore[call-arg]
                collapsible = Collapsible(*rows, title=header_text, collapsed=False)  # type: ignore[arg-type]
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

    class CallDetailScreen(Screen):  # type: ignore[no-redef]
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
            body.mount(
                Label(
                    f" {c.label}  \u2500  {ts}  \u2500  {dur}  \u2500  {icon}",
                    classes="detail-header",
                )
            )

            # Purpose
            body.mount(Label("\n Purpose", classes="section-header"))
            body.mount(Label(f"   {c.purpose}"))

            # DSL Context
            self._mount_dsl_context(body, c)

            # Progress Timeline
            if c.events:
                body.mount(Label("\n Progress Timeline", classes="section-header"))
                start_wall = c.start_ts
                for evt in c.events:
                    etype = evt.get("type", "")
                    msg = evt.get("message", "")
                    evt_ts = evt.get("ts", "")
                    rel = _relative_time(start_wall, evt_ts)

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

        def _mount_dsl_context(self, body: VerticalScroll, c: ToolCall) -> None:
            """Extract and display DSL context from context_json."""
            if not c.context_json:
                return
            try:
                ctx = json.loads(c.context_json)
            except (json.JSONDecodeError, TypeError):
                return
            if not isinstance(ctx, dict):
                return

            # Extract DSL-relevant keys
            context_keys = ("project", "entity", "surface", "module", "workspace", "story")
            items: list[str] = []
            for key in context_keys:
                val = ctx.get(key)
                if val:
                    items.append(f"   {key}: {val}")

            if not items:
                return

            body.mount(Label("\n DSL Context", classes="section-header"))
            for item in items:
                body.mount(Label(item))
