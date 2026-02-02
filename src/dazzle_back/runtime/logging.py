"""
DNR Logging Infrastructure.

Provides unified logging for both backend and frontend, with:
- LLM-friendly log format (structured, contextual, easily parseable)
- Console output for human monitoring
- File output to .dazzle/logs/ for LLM agents to monitor
- Frontend error capture endpoint

Log Format Design:
- Primary file: .dazzle/logs/dnr.log (JSONL format for LLM parsing)
- Each line is a complete JSON object with full context
- Includes timestamps, component, level, message, and structured metadata
- Designed for agents to tail/read without human preprocessing
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# =============================================================================
# Terminal Colors (respects NO_COLOR)
# =============================================================================

_NO_COLOR = os.environ.get("NO_COLOR") or not sys.stdout.isatty()


class Colors:
    """ANSI color codes for terminal output."""

    RESET = "" if _NO_COLOR else "\033[0m"
    BOLD = "" if _NO_COLOR else "\033[1m"
    DIM = "" if _NO_COLOR else "\033[2m"

    # Log levels
    DEBUG = "" if _NO_COLOR else "\033[36m"  # Cyan
    INFO = "" if _NO_COLOR else "\033[32m"  # Green
    WARNING = "" if _NO_COLOR else "\033[33m"  # Yellow
    ERROR = "" if _NO_COLOR else "\033[31m"  # Red
    CRITICAL = "" if _NO_COLOR else "\033[35m"  # Magenta

    # Components
    BACKEND = "" if _NO_COLOR else "\033[34m"  # Blue
    FRONTEND = "" if _NO_COLOR else "\033[36m"  # Cyan
    DAZZLE = "" if _NO_COLOR else "\033[35m"  # Magenta


# =============================================================================
# LLM-Friendly JSONL Formatter
# =============================================================================


class JSONLFormatter(logging.Formatter):
    """
    Formats log records as JSON Lines (JSONL) for LLM consumption.

    Each log entry is a single JSON object on one line containing:
    - timestamp: ISO 8601 format
    - level: DEBUG, INFO, WARNING, ERROR, CRITICAL
    - component: API, UI, Bar, DNR
    - message: The log message
    - context: Additional structured data (optional)
    - source: Source file/location info (if available)

    Example output:
    {"timestamp":"2024-01-15T10:30:45.123Z","level":"ERROR","component":"UI","message":"Failed to fetch /tasks","context":{"status":500,"url":"/tasks"}}
    """

    def format(self, record: logging.LogRecord) -> str:
        # Build the log entry
        entry: dict[str, Any] = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "component": getattr(record, "component", "DNR"),
            "message": record.getMessage(),
        }

        # Add context if present
        context = getattr(record, "context", None)
        if context:
            entry["context"] = context

        # Add source location for errors
        if record.levelno >= logging.WARNING:
            source_info: dict[str, Any] = {}
            if record.pathname:
                source_info["file"] = record.pathname
            if record.lineno:
                source_info["line"] = record.lineno
            if record.funcName and record.funcName != "<module>":
                source_info["function"] = record.funcName
            if source_info:
                entry["source"] = source_info

        # Add exception info if present
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(entry, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable formatter for console output."""

    LEVEL_COLORS = {
        logging.DEBUG: Colors.DEBUG,
        logging.INFO: Colors.INFO,
        logging.WARNING: Colors.WARNING,
        logging.ERROR: Colors.ERROR,
        logging.CRITICAL: Colors.CRITICAL,
    }

    def format(self, record: logging.LogRecord) -> str:
        # Get component from record or default
        component = getattr(record, "component", "DNR")
        component_color = getattr(record, "component_color", Colors.DAZZLE)

        # Format timestamp (brief for console)
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")

        # Get level color
        level_color = self.LEVEL_COLORS.get(record.levelno, "")

        # Build message
        if _NO_COLOR:
            prefix = f"[{timestamp}] [{component}]"
        else:
            prefix = (
                f"{Colors.DIM}{timestamp}{Colors.RESET} "
                f"{component_color}[{component}]{Colors.RESET}"
            )

        # Add level for non-INFO messages
        if record.levelno != logging.INFO:
            level_name = record.levelname
            if not _NO_COLOR:
                level_name = f"{level_color}{level_name}{Colors.RESET}"
            prefix = f"{prefix} {level_name}:"

        return f"{prefix} {record.getMessage()}"


# =============================================================================
# Logger Setup
# =============================================================================


_loggers: dict[str, logging.Logger] = {}
_log_dir: Path | None = None
_file_handler: RotatingFileHandler | None = None


def setup_logging(
    log_dir: Path | str = ".dazzle/logs",
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,  # 5MB
    backup_count: int = 3,
) -> Path:
    """
    Initialize the logging infrastructure.

    Creates:
    - .dazzle/logs/dnr.log: JSONL format for LLM agents
    - Console output: Human-readable format

    Args:
        log_dir: Directory for log files
        level: Minimum log level
        max_bytes: Max size per log file before rotation
        backup_count: Number of backup files to keep

    Returns:
        Path to the log directory
    """
    global _log_dir, _file_handler

    _log_dir = Path(log_dir)
    _log_dir.mkdir(parents=True, exist_ok=True)

    # Create rotating file handler with JSONL format
    log_file = _log_dir / "dazzle.log"
    _file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    _file_handler.setFormatter(JSONLFormatter())
    _file_handler.setLevel(level)

    # Configure root DNR logger
    root_logger = logging.getLogger("dazzle")
    root_logger.setLevel(level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Add console handler (human-readable)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ConsoleFormatter())
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)

    # Add file handler (JSONL for LLMs)
    root_logger.addHandler(_file_handler)

    # Write a header entry so agents know this is a JSONL log
    root_logger.info(
        "Dazzle logging initialized",
        extra={
            "component": "DNR",
            "context": {
                "log_format": "jsonl",
                "log_file": str(log_file),
                "description": "Each line is a JSON object. Use tail -f to monitor.",
            },
        },
    )

    return _log_dir


def get_logger(component: str, color: str = Colors.DAZZLE) -> logging.Logger:
    """
    Get a logger for a specific component.

    Args:
        component: Component name (e.g., "API", "UI", "Bar")
        color: ANSI color code for the component tag

    Returns:
        Configured logger instance
    """
    if component in _loggers:
        return _loggers[component]

    logger = logging.getLogger(f"dazzle.{component.lower().replace(' ', '_')}")

    # Add component info to all records via a filter
    class ComponentFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if not hasattr(record, "component"):
                record.component = component
            if not hasattr(record, "component_color"):
                record.component_color = color
            return True

    logger.addFilter(ComponentFilter())
    _loggers[component] = logger

    return logger


# =============================================================================
# Contextual Logging
# =============================================================================


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> None:
    """
    Log a message with structured context data.

    This is the preferred method for logging in DNR as it produces
    LLM-friendly output with rich context.

    Args:
        logger: Logger instance
        level: Logging level (logging.INFO, logging.ERROR, etc.)
        message: Human-readable message
        context: Structured context data (will be included in JSONL)
        **kwargs: Additional context items
    """
    extra = {"context": {**(context or {}), **kwargs}} if (context or kwargs) else {}
    logger.log(level, message, extra=extra)


# =============================================================================
# Component Loggers
# =============================================================================


def get_backend_logger() -> logging.Logger:
    """Get logger for backend/API operations."""
    return get_logger("API", Colors.BACKEND)


def get_frontend_logger() -> logging.Logger:
    """Get logger for frontend/UI operations."""
    return get_logger("UI", Colors.FRONTEND)


def get_dazzle_bar_logger() -> logging.Logger:
    """Get logger for Dazzle Bar operations."""
    return get_logger("Bar", Colors.DAZZLE)


def get_dazzle_logger() -> logging.Logger:
    """Get logger for general DNR operations."""
    return get_logger("DNR", Colors.DAZZLE)


# =============================================================================
# Frontend Error Logging
# =============================================================================


def log_frontend_entry(
    level: str,
    message: str,
    source: str | None = None,
    line: int | None = None,
    column: int | None = None,
    stack: str | None = None,
    url: str | None = None,
    user_agent: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """
    Log a frontend entry (error, warning, info) from the browser.

    This creates a JSONL entry that LLM agents can parse to understand
    frontend issues.

    Args:
        level: Log level (error, warn, info, debug)
        message: Error/log message
        source: Source file URL
        line: Line number
        column: Column number
        stack: Stack trace (for errors)
        url: Page URL where error occurred
        user_agent: Browser user agent
        extra: Additional context
    """
    logger = get_frontend_logger()

    # Map frontend level to Python logging level
    level_map = {
        "error": logging.ERROR,
        "warn": logging.WARNING,
        "warning": logging.WARNING,
        "info": logging.INFO,
        "debug": logging.DEBUG,
        "log": logging.INFO,
    }
    py_level = level_map.get(level.lower(), logging.INFO)

    # Build context
    context: dict[str, Any] = {}
    if source:
        context["source_file"] = source
    if line:
        context["line"] = line
    if column:
        context["column"] = column
    if url:
        context["page_url"] = url
    if user_agent:
        context["user_agent"] = user_agent
    if stack:
        # Include stack as array for easier parsing
        context["stack_trace"] = [line.strip() for line in stack.split("\n") if line.strip()]
    if extra:
        context.update(extra)

    log_with_context(logger, py_level, message, context)


# =============================================================================
# Utility Functions
# =============================================================================


def get_log_dir() -> Path | None:
    """Get the current log directory."""
    return _log_dir


def get_log_file() -> Path | None:
    """Get the path to the main log file."""
    if _log_dir:
        return _log_dir / "dazzle.log"
    return None


def get_recent_logs(count: int = 50, level: str | None = None) -> list[dict[str, Any]]:
    """
    Get recent log entries as parsed JSON.

    Useful for LLM agents to retrieve log context.

    Args:
        count: Number of recent entries to return
        level: Optional filter by level (ERROR, WARNING, etc.)

    Returns:
        List of log entries (most recent last)
    """
    log_file = get_log_file()
    if not log_file or not log_file.exists():
        return []

    entries: list[dict[str, Any]] = []
    try:
        with open(log_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if level and entry.get("level") != level.upper():
                        continue
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue

        # Return last N entries
        return entries[-count:]
    except OSError:
        return []


def get_error_summary() -> dict[str, Any]:
    """
    Get a summary of errors for LLM diagnosis.

    Returns a structured summary that helps agents understand
    what's going wrong.

    Returns:
        Summary dict with error counts, recent errors, etc.
    """
    entries = get_recent_logs(count=200)

    errors = [e for e in entries if e.get("level") == "ERROR"]
    warnings = [e for e in entries if e.get("level") == "WARNING"]

    # Group errors by component
    by_component: dict[str, list[dict[str, Any]]] = {}
    for error in errors:
        comp = error.get("component", "unknown")
        if comp not in by_component:
            by_component[comp] = []
        by_component[comp].append(error)

    return {
        "total_entries": len(entries),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors_by_component": {k: len(v) for k, v in by_component.items()},
        "recent_errors": errors[-10:],  # Last 10 errors
        "log_file": str(get_log_file()),
    }


def clear_logs() -> int:
    """
    Clear all log files.

    Returns:
        Number of files deleted
    """
    if not _log_dir:
        return 0

    count = 0
    for log_file in _log_dir.glob("*.log*"):
        try:
            log_file.unlink()
            count += 1
        except OSError:
            pass

    return count
