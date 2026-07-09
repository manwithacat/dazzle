"""Regression tests for the runtime log formatters (#1562).

ConsoleFormatter used to hand-build its line and drop `record.exc_info`, so
tracebacks never reached the console; JSONLFormatter recorded the exception
type+message but no traceback. Both now emit the full traceback.
"""

import json
import logging

from dazzle.http.runtime.logging import ConsoleFormatter, JSONLFormatter


def _record_with_exc() -> logging.LogRecord:
    try:
        raise ValueError("boom-1562")
    except ValueError:
        import sys

        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="dazzle.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="event bus failed to start",
        args=(),
        exc_info=exc_info,
    )
    return record


def test_console_appends_traceback_when_exc_info_present() -> None:
    out = ConsoleFormatter().format(_record_with_exc())
    assert "event bus failed to start" in out
    assert "Traceback (most recent call last)" in out
    assert "ValueError: boom-1562" in out


def test_console_unchanged_without_exc_info() -> None:
    record = logging.LogRecord(
        name="dazzle.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="plain message",
        args=(),
        exc_info=None,
    )
    out = ConsoleFormatter().format(record)
    assert "plain message" in out
    assert "Traceback" not in out
    assert "\n" not in out  # single-line for non-exception records


def test_console_renders_stack_info() -> None:
    record = logging.LogRecord(
        name="dazzle.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="with stack",
        args=(),
        exc_info=None,
    )
    record.stack_info = "Stack (most recent call last):\n  fake stack frame"
    out = ConsoleFormatter().format(record)
    assert "fake stack frame" in out


def test_jsonl_includes_traceback() -> None:
    out = JSONLFormatter().format(_record_with_exc())
    entry = json.loads(out)
    assert entry["exception"]["type"] == "ValueError"
    assert entry["exception"]["message"] == "boom-1562"
    assert "Traceback (most recent call last)" in entry["exception"]["traceback"]
    assert "ValueError: boom-1562" in entry["exception"]["traceback"]


def test_jsonl_no_exception_key_without_exc_info() -> None:
    record = logging.LogRecord(
        name="dazzle.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="fine",
        args=(),
        exc_info=None,
    )
    entry = json.loads(JSONLFormatter().format(record))
    assert "exception" not in entry
