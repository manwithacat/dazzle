"""SQLite span exporter for the ``dazzle perf`` toolkit.

Writes spans into a 3-table schema owned by the framework — see
``schema.sql``. Findings extraction reads the same schema directly, so
keeping the writer + reader paired in this package avoids vendor-schema
drift surprises.

This exporter is intentionally simple:

- One SQLite file per ``run_id``. Opening more than one provider with
  the same ``db_path`` is undefined.
- A single ``runs`` row per file is upserted on first export and
  finalised (``ended_at``) on shutdown.
- ``SimpleSpanProcessor`` is the recommended pairing for synchronous
  tests; the production path in ``tracer.py`` uses ``BatchSpanProcessor``.
"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from pathlib import Path
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import StatusCode

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class SQLiteSpanExporter(SpanExporter):
    """Persists OTel spans to a per-run SQLite file."""

    def __init__(
        self,
        *,
        db_path: Path,
        run_id: str,
        app_name: str | None = None,
        manifest_path: str | None = None,
        command_line: str = "",
    ) -> None:
        self._db_path = db_path
        self._run_id = run_id
        self._app_name = app_name
        self._manifest_path = manifest_path
        self._command_line = command_line
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, isolation_level=None, check_same_thread=False)
        self._conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        self._ensure_run_row()

    def _ensure_run_row(self) -> None:
        started_at = _dt.datetime.now(_dt.UTC).isoformat()
        self._conn.execute(
            "INSERT OR IGNORE INTO runs "
            "(run_id, started_at, app_name, manifest_path, command_line) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                self._run_id,
                started_at,
                self._app_name,
                self._manifest_path,
                self._command_line,
            ),
        )

    def export(self, spans: list[ReadableSpan]) -> SpanExportResult:  # type: ignore[override]
        with self._conn:
            for span in spans:
                self._write_span(span)
        return SpanExportResult.SUCCESS

    def _write_span(self, span: ReadableSpan) -> None:
        ctx = span.get_span_context()
        if ctx is None:
            return
        parent = span.parent
        parent_span_id = f"{parent.span_id:016x}" if parent and parent.span_id else None
        started_ns = span.start_time or 0
        ended_ns = span.end_time or started_ns
        status_code = span.status.status_code if span.status else StatusCode.UNSET
        status = "error" if status_code == StatusCode.ERROR else "ok"
        attributes_json = json.dumps(
            {k: _coerce(v) for k, v in (span.attributes or {}).items()},
            default=str,
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO spans "
            "(span_id, trace_id, parent_span_id, run_id, name, kind, status, "
            " started_ns, ended_ns, duration_ns, attributes_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"{ctx.span_id:016x}",
                f"{ctx.trace_id:032x}",
                parent_span_id,
                self._run_id,
                span.name,
                span.kind.name.lower(),
                status,
                started_ns,
                ended_ns,
                max(0, ended_ns - started_ns),
                attributes_json,
            ),
        )
        for event in span.events or []:
            self._conn.execute(
                "INSERT INTO events "
                "(span_id, run_id, name, timestamp_ns, attributes_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    f"{ctx.span_id:016x}",
                    self._run_id,
                    event.name,
                    event.timestamp or 0,
                    json.dumps(
                        {k: _coerce(v) for k, v in (event.attributes or {}).items()},
                        default=str,
                    ),
                ),
            )

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # noqa: ARG002
        return True

    def shutdown(self) -> None:
        if self._conn is None:
            return
        ended = _dt.datetime.now(_dt.UTC).isoformat()
        self._conn.execute(
            "UPDATE runs SET ended_at = ? WHERE run_id = ?",
            (ended, self._run_id),
        )
        self._conn.close()
        self._conn = None  # type: ignore[assignment]


def _coerce(value: Any) -> Any:
    """Coerce non-JSON-serialisable OTel attribute values to strings."""
    if isinstance(value, bool | int | float | str | list | tuple | dict) or value is None:
        return value
    return str(value)
