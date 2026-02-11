"""MCP activity log — file-based progress visibility.

Provides a JSONL-based activity log that captures MCP tool invocations and
progress updates.  This is the *reliable* channel for surfacing what the
MCP server is doing, since Claude Code silently drops MCP notifications.

Consumers:
  - ``tail -f .dazzle/mcp-activity.log``  (human, separate terminal)
  - ``status activity`` MCP operation       (agent / watcher)
  - Direct file reads from background agents

The log uses monotonic sequence numbers and an epoch counter so that
cursor-based polling survives log truncation.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

logger = logging.getLogger("dazzle.mcp.activity")

# ── Defaults ────────────────────────────────────────────────────────────────

MAX_ENTRIES = 500
KEEP_AFTER_TRUNCATE = 300

# Entry types
TYPE_TOOL_START = "tool_start"
TYPE_TOOL_END = "tool_end"
TYPE_PROGRESS = "progress"
TYPE_LOG = "log"
TYPE_ERROR = "error"

# ANSI colour codes for formatted terminal output
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_WHITE = "\033[37m"
_BG_RED = "\033[41m"

# Type → colour mapping
_TYPE_STYLES: dict[str, str] = {
    TYPE_TOOL_START: _CYAN,
    TYPE_TOOL_END: _GREEN,
    TYPE_PROGRESS: _BLUE,
    TYPE_LOG: _WHITE,
    TYPE_ERROR: _RED,
}

# Type → icon mapping
_TYPE_ICONS: dict[str, str] = {
    TYPE_TOOL_START: "\u25b6",  # ▶
    TYPE_TOOL_END: "\u2714",  # ✔
    TYPE_PROGRESS: "\u2502",  # │
    TYPE_LOG: "\u2502",  # │
    TYPE_ERROR: "\u2718",  # ✘
}

# Level → style mapping for log entries
_LEVEL_STYLES: dict[str, str] = {
    "info": _DIM,
    "warning": _YELLOW,
    "error": _RED,
}


class ActivityLog:
    """Append-only JSONL activity log with cursor-based polling.

    Thread-safe.  All writes are flushed immediately so ``tail -f`` works.

    Each entry carries a monotonic ``seq`` (sequence number).  When the log
    is truncated to stay within *MAX_ENTRIES*, the ``epoch`` counter is
    bumped.  Consumers that hold a ``(epoch, seq)`` cursor can detect
    staleness and reset.
    """

    def __init__(self, log_path: Path) -> None:
        self._path = log_path
        self._lock = threading.Lock()
        self._seq = 0
        self._epoch = 0
        self._entry_count = 0
        self._fh: IO[str] | None = None  # lazy open
        self._active_tool: str | None = None
        self._active_operation: str | None = None
        self._active_start: float | None = None

        # Resume from existing log if present
        self._recover_state()

    # ── Public API ──────────────────────────────────────────────────────

    def append(self, entry: dict[str, Any]) -> int:
        """Append a JSONL entry.  Returns the assigned sequence number.

        Thread-safe.  Flushes on every write.
        """
        with self._lock:
            self._seq += 1
            entry["seq"] = self._seq
            entry["epoch"] = self._epoch
            if "ts" not in entry:
                entry["ts"] = datetime.now(UTC).isoformat(timespec="milliseconds")

            # Track in-flight tool
            etype = entry.get("type")
            if etype == TYPE_TOOL_START:
                self._active_tool = entry.get("tool")
                self._active_operation = entry.get("operation")
                self._active_start = time.monotonic()
            elif etype == TYPE_TOOL_END:
                self._active_tool = None
                self._active_operation = None
                self._active_start = None

            self._ensure_open()
            assert self._fh is not None  # guaranteed by _ensure_open
            line = json.dumps(entry, separators=(",", ":")) + "\n"
            self._fh.write(line)
            self._fh.flush()
            self._entry_count += 1

            if self._entry_count >= MAX_ENTRIES:
                self._truncate()

            return self._seq

    def read_since(
        self,
        cursor_seq: int = 0,
        cursor_epoch: int = 0,
        count: int = 50,
    ) -> dict[str, Any]:
        """Read entries after the given cursor.

        Returns::

            {
                "entries": [...],
                "cursor": {"seq": <int>, "epoch": <int>},
                "has_more": <bool>,
                "stale": <bool>,          # True if epoch changed
                "active_tool": <str|null>,
            }

        If ``stale`` is True the consumer should treat cursor_seq=0 and
        re-read (entries will already contain everything from the new epoch).
        """
        with self._lock:
            stale = cursor_epoch != self._epoch
            effective_seq = 0 if stale else cursor_seq
            entries = self._read_entries(effective_seq, count)
            last_seq = entries[-1]["seq"] if entries else effective_seq

            active_info: dict[str, Any] | None = None
            if self._active_tool:
                elapsed = (
                    (time.monotonic() - self._active_start) * 1000 if self._active_start else None
                )
                active_info = {
                    "tool": self._active_tool,
                    "operation": self._active_operation,
                    "elapsed_ms": round(elapsed) if elapsed else None,
                }

            return {
                "entries": entries,
                "cursor": {"seq": last_seq, "epoch": self._epoch},
                "has_more": len(entries) == count,
                "stale": stale,
                "active_tool": active_info,
            }

    def clear(self) -> None:
        """Truncate the log completely (e.g. on server startup)."""
        with self._lock:
            self._close()
            if self._path.exists():
                self._path.write_text("")
            self._seq = 0
            self._epoch += 1
            self._entry_count = 0

    @property
    def path(self) -> Path:
        return self._path

    @property
    def current_seq(self) -> int:
        return self._seq

    @property
    def current_epoch(self) -> int:
        return self._epoch

    @property
    def active_tool(self) -> str | None:
        return self._active_tool

    # ── Formatting ──────────────────────────────────────────────────────

    @staticmethod
    def format_entry(entry: dict[str, Any], *, color: bool = True) -> str:
        """Format a single entry for human-readable terminal display.

        When *color* is True, uses ANSI escape codes.
        """
        etype = entry.get("type", "log")
        ts_raw = entry.get("ts", "")
        tool = entry.get("tool", "")
        operation = entry.get("operation", "")
        message = entry.get("message", "")
        level = entry.get("level", "info")

        # Compact timestamp: HH:MM:SS.mmm
        try:
            dt = datetime.fromisoformat(ts_raw)
            ts = dt.strftime("%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"
        except (ValueError, AttributeError):
            ts = ts_raw[:12] if ts_raw else "??:??:??"

        icon = _TYPE_ICONS.get(etype, " ")

        if not color:
            return _format_plain(etype, ts, icon, tool, operation, message, entry)

        c = _TYPE_STYLES.get(etype, _WHITE)
        lc = _LEVEL_STYLES.get(level, _DIM)

        if etype == TYPE_TOOL_START:
            tool_label = f"{tool}.{operation}" if operation else tool
            return f"{_DIM}{ts}{_RESET}  {c}{_BOLD}{icon} {tool_label}{_RESET}"

        if etype == TYPE_TOOL_END:
            tool_label = f"{tool}.{operation}" if operation else tool
            ok = entry.get("success", True)
            dur = entry.get("duration_ms")
            dur_str = f" {_DIM}({dur:.0f}ms){_RESET}" if dur is not None else ""
            if ok:
                return f"{_DIM}{ts}{_RESET}  {_GREEN}{icon} {tool_label}{_RESET}{dur_str}"
            else:
                err = entry.get("error", "failed")
                return (
                    f"{_DIM}{ts}{_RESET}  "
                    f"{_RED}{_BOLD}\u2718 {tool_label}{_RESET} "
                    f"{_RED}{err}{_RESET}{dur_str}"
                )

        if etype == TYPE_PROGRESS:
            current = entry.get("current")
            total = entry.get("total")
            bar = ""
            if current is not None and total is not None and total > 0:
                bar = _progress_bar(current, total, color=True)
                return f"{_DIM}{ts}{_RESET}  {c}{icon}{_RESET} {bar} {_DIM}{message}{_RESET}"
            return f"{_DIM}{ts}{_RESET}  {c}{icon}{_RESET} {lc}{message}{_RESET}"

        if etype == TYPE_ERROR:
            return f"{_DIM}{ts}{_RESET}  {_RED}{_BOLD}{icon} {message}{_RESET}"

        # Generic log
        return f"{_DIM}{ts}{_RESET}  {c}{icon}{_RESET} {lc}{message}{_RESET}"

    @staticmethod
    def format_summary(data: dict[str, Any], *, color: bool = True) -> str:
        """Format a ``read_since`` result as a structured summary.

        Suitable for MCP tool responses or terminal display.
        """
        lines: list[str] = []
        entries = data.get("entries", [])
        active = data.get("active_tool")

        if active and color:
            tool = active.get("tool", "?")
            op = active.get("operation", "")
            elapsed = active.get("elapsed_ms")
            label = f"{tool}.{op}" if op else tool
            elapsed_str = f" ({elapsed / 1000:.1f}s)" if elapsed else ""
            lines.append(f"{_YELLOW}{_BOLD}\u23f3 In progress: {label}{elapsed_str}{_RESET}")
            lines.append("")
        elif active:
            tool = active.get("tool", "?")
            op = active.get("operation", "")
            elapsed = active.get("elapsed_ms")
            label = f"{tool}.{op}" if op else tool
            elapsed_str = f" ({elapsed / 1000:.1f}s)" if elapsed else ""
            lines.append(f"[IN PROGRESS] {label}{elapsed_str}")
            lines.append("")

        if not entries:
            if not active:
                lines.append(
                    f"{_DIM}No recent activity.{_RESET}" if color else "No recent activity."
                )
            return "\n".join(lines)

        for entry in entries:
            lines.append(ActivityLog.format_entry(entry, color=color))

        cursor = data.get("cursor", {})
        has_more = data.get("has_more", False)
        if has_more:
            hint = (
                f"\n{_DIM}... more entries available (cursor seq={cursor.get('seq', 0)}){_RESET}"
                if color
                else f"\n... more entries available (cursor seq={cursor.get('seq', 0)})"
            )
            lines.append(hint)

        return "\n".join(lines)

    # ── Internal ────────────────────────────────────────────────────────

    def _ensure_open(self) -> None:
        """Lazily open the log file for appending."""
        if self._fh is None or self._fh.closed:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self._path, "a", encoding="utf-8")

    def _close(self) -> None:
        if self._fh and not self._fh.closed:
            self._fh.close()
        self._fh = None

    def _truncate(self) -> None:
        """Keep last KEEP_AFTER_TRUNCATE entries, bump epoch."""
        self._close()
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
            kept = lines[-KEEP_AFTER_TRUNCATE:]
            self._path.write_text("\n".join(kept) + "\n", encoding="utf-8")
            self._entry_count = len(kept)
            self._epoch += 1
            logger.debug(
                "Activity log truncated: kept %d entries, epoch now %d",
                len(kept),
                self._epoch,
            )
        except Exception:
            logger.debug("Activity log truncation failed", exc_info=True)

    def _read_entries(self, after_seq: int, count: int) -> list[dict[str, Any]]:
        """Read up to *count* entries with seq > after_seq."""
        if not self._path.exists():
            return []
        entries: list[dict[str, Any]] = []
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("seq", 0) > after_seq:
                        entries.append(entry)
                        if len(entries) >= count:
                            break
        except OSError:
            logger.debug("Failed to read activity log", exc_info=True)
        return entries

    def _recover_state(self) -> None:
        """Recover seq/epoch/count from an existing log file."""
        if not self._path.exists():
            return
        try:
            count = 0
            max_seq = 0
            max_epoch = 0
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        s = entry.get("seq", 0)
                        e = entry.get("epoch", 0)
                        if s > max_seq:
                            max_seq = s
                        if e > max_epoch:
                            max_epoch = e
                        count += 1
                    except json.JSONDecodeError:
                        continue
            self._seq = max_seq
            self._epoch = max_epoch
            self._entry_count = count
        except OSError:
            pass

    def __del__(self) -> None:
        self._close()


# ── Helpers ─────────────────────────────────────────────────────────────────


def _progress_bar(current: int, total: int, *, width: int = 20, color: bool = True) -> str:
    """Render a compact progress bar."""
    ratio = min(current / total, 1.0) if total > 0 else 0
    filled = int(width * ratio)
    empty = width - filled

    if color:
        bar_fill = f"{_GREEN}{'━' * filled}{_RESET}"
        bar_empty = f"{_DIM}{'─' * empty}{_RESET}"
        pct = f"{_BOLD}{ratio * 100:3.0f}%{_RESET}"
        counter = f"{_DIM}[{current}/{total}]{_RESET}"
        return f"{bar_fill}{bar_empty} {pct} {counter}"
    else:
        bar_fill = "━" * filled
        bar_empty = "─" * empty
        return f"{bar_fill}{bar_empty} {ratio * 100:3.0f}% [{current}/{total}]"


def _format_plain(
    etype: str,
    ts: str,
    icon: str,
    tool: str,
    operation: str,
    message: str,
    entry: dict[str, Any],
) -> str:
    """Plain-text (no colour) formatting for a single entry."""
    if etype == TYPE_TOOL_START:
        label = f"{tool}.{operation}" if operation else tool
        return f"{ts}  {icon} {label}"

    if etype == TYPE_TOOL_END:
        label = f"{tool}.{operation}" if operation else tool
        ok = entry.get("success", True)
        dur = entry.get("duration_ms")
        dur_str = f" ({dur:.0f}ms)" if dur is not None else ""
        status = "OK" if ok else f"FAIL: {entry.get('error', '')}"
        return f"{ts}  {icon} {label} {status}{dur_str}"

    if etype == TYPE_PROGRESS:
        current = entry.get("current")
        total = entry.get("total")
        if current is not None and total is not None and total > 0:
            bar = _progress_bar(current, total, color=False)
            return f"{ts}  {icon} {bar} {message}"
        return f"{ts}  {icon} {message}"

    return f"{ts}  {icon} {message}"


def make_tool_start_entry(tool: str, operation: str | None = None) -> dict[str, Any]:
    """Create a tool_start log entry."""
    entry: dict[str, Any] = {"type": TYPE_TOOL_START, "tool": tool}
    if operation:
        entry["operation"] = operation
    return entry


def make_tool_end_entry(
    tool: str,
    operation: str | None = None,
    *,
    success: bool = True,
    duration_ms: float | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Create a tool_end log entry."""
    entry: dict[str, Any] = {
        "type": TYPE_TOOL_END,
        "tool": tool,
        "success": success,
    }
    if operation:
        entry["operation"] = operation
    if duration_ms is not None:
        entry["duration_ms"] = round(duration_ms, 1)
    if error:
        entry["error"] = error
    return entry


def make_progress_entry(
    tool: str,
    message: str,
    *,
    operation: str | None = None,
    current: int | None = None,
    total: int | None = None,
    level: str = "info",
) -> dict[str, Any]:
    """Create a progress/log entry."""
    entry: dict[str, Any] = {
        "type": TYPE_PROGRESS if current is not None else TYPE_LOG,
        "tool": tool,
        "message": message,
        "level": level,
    }
    if operation:
        entry["operation"] = operation
    if current is not None:
        entry["current"] = current
    if total is not None:
        entry["total"] = total
    return entry


def make_error_entry(
    tool: str,
    message: str,
    *,
    operation: str | None = None,
) -> dict[str, Any]:
    """Create an error log entry."""
    entry: dict[str, Any] = {
        "type": TYPE_ERROR,
        "tool": tool,
        "message": message,
        "level": "error",
    }
    if operation:
        entry["operation"] = operation
    return entry
