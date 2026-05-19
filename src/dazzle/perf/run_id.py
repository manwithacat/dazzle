"""Run-id generation + latest-run resolution for the perf SQLite store."""

from __future__ import annotations

import datetime as _dt
import uuid
from pathlib import Path


def make_run_id() -> str:
    """Return a timestamp + short-uuid id, e.g. ``20260519-203045-3f8a1b2c``.

    The timestamp prefix makes lexical sort == chronological sort, which
    is how :func:`latest_run_id` resolves "newest".
    """
    stamp = _dt.datetime.now(_dt.UTC).strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"{stamp}-{suffix}"


def latest_run_id(perf_dir: Path) -> str | None:
    """Return the run id of the newest ``<run_id>.db`` file in ``perf_dir``.

    Returns ``None`` when the directory doesn't exist or contains no
    matching files. Non-``.db`` entries are ignored.
    """
    if not perf_dir.is_dir():
        return None
    db_files = sorted(perf_dir.glob("*.db"))
    if not db_files:
        return None
    return db_files[-1].stem
