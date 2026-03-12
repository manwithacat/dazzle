"""Workshop drill-down screens: SessionScreen and CallDetailScreen."""

from __future__ import annotations

import time
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Collapsible, Footer, Header, Label, Static

from dazzle.mcp.server.workshop import (
    ToolCall,
    WorkshopApp,
    _format_duration,
    _format_ts,
    _relative_time,
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
            header_text = f"{tool_name} ({len(calls)} calls, {_format_duration(total_dur)} total)"
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
        body.mount(
            Label(
                f" {c.label}  \u2500  {ts}  \u2500  {dur}  \u2500  {icon}",
                classes="detail-header",
            )
        )

        # Purpose
        body.mount(Label("\n Purpose", classes="section-header"))
        body.mount(Label(f"   {c.purpose}"))

        # Progress Timeline
        if c.events:
            body.mount(Label("\n Progress Timeline", classes="section-header"))
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
