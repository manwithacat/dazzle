"""Flat-file signal bus for cross-loop coordination.

Used by /ux-cycle, /improve, /ux-converge and other loops to share
state without direct calls. Signals are JSON files in .dazzle/signals/.

Each emit creates a new file named `{timestamp}-{source}-{kind}.json`.
Each source has a marker file `.mark-{source}.json` recording the
timestamp of its last call to `mark_run()`. `since_last_run(source)`
returns all signals newer than that marker (excluding signals the
source emitted itself).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SIGNALS_DIR = Path(".dazzle/signals")


@dataclass
class Signal:
    """A cross-loop coordination signal."""

    source: str  # loop that emitted this signal (e.g. "ux-cycle", "improve")
    kind: str  # signal type (e.g. "ux-component-shipped", "fix-deployed")
    payload: dict[str, Any]
    timestamp: float  # Unix timestamp of emission


def _ensure_dir() -> None:
    _SIGNALS_DIR.mkdir(parents=True, exist_ok=True)


def _marker_path(source: str) -> Path:
    return _SIGNALS_DIR / f".mark-{source}.json"


def emit(source: str, kind: str, payload: dict[str, Any]) -> None:
    """Emit a signal from `source` of type `kind` with the given payload.

    Signal files are immutable and accumulate until manually cleaned up.
    """
    _ensure_dir()
    timestamp = time.time()
    filename = f"{timestamp:.6f}-{source}-{kind}.json"
    data = {
        "source": source,
        "kind": kind,
        "payload": payload,
        "timestamp": timestamp,
    }
    (_SIGNALS_DIR / filename).write_text(json.dumps(data, indent=2))


def mark_run(source: str) -> None:
    """Record that `source` has just completed a run.

    Subsequent calls to `since_last_run(source)` will only return
    signals emitted after this timestamp.
    """
    _ensure_dir()
    timestamp = time.time()
    _marker_path(source).write_text(json.dumps({"timestamp": timestamp}))


def since_last_run(source: str, kind: str | None = None) -> list[Signal]:
    """Return signals emitted since `source` last called `mark_run`.

    Excludes signals emitted by `source` itself (a source doesn't
    consume its own signals). If `kind` is given, filter by signal type.
    If `source` has never called `mark_run`, all signals not from
    `source` are returned.
    """
    if not _SIGNALS_DIR.exists():
        return []

    marker = _marker_path(source)
    last_run = 0.0
    if marker.exists():
        try:
            last_run = json.loads(marker.read_text())["timestamp"]
        except (json.JSONDecodeError, KeyError):
            last_run = 0.0

    signals: list[Signal] = []
    for f in _SIGNALS_DIR.glob("*.json"):
        if f.name.startswith(".mark-"):
            continue
        try:
            data = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        if data.get("source") == source:
            continue
        if data.get("timestamp", 0) <= last_run:
            continue
        if kind is not None and data.get("kind") != kind:
            continue
        signals.append(
            Signal(
                source=data["source"],
                kind=data["kind"],
                payload=data.get("payload", {}),
                timestamp=data["timestamp"],
            )
        )

    signals.sort(key=lambda s: s.timestamp)
    return signals
