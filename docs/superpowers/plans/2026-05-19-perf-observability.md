# Dazzle Perf Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `dazzle perf trace` and `dazzle perf report` — a local-only OpenTelemetry-based tracing toolkit that captures a Dazzle app's runtime, persists spans to a per-run SQLite file under `.dazzle/perf/`, and emits agent-readable findings (slow endpoints, slow queries, suspected N+1s, slow Dazzle phases, exceptions).

**Architecture:** Raw OpenTelemetry SDK with a custom SQLite span exporter we own. Auto-instrumentation (`opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-psycopg`, `opentelemetry-instrumentation-asyncio`) covers the standard surface; manual `tracer.start_as_current_span()` decorates Dazzle's hot phases (predicate compile, aggregate compile, region render, fragment emit, AppSpec build). The findings extractor reads our SQLite schema directly and emits Markdown or JSON. Surfaced as `dazzle perf` Typer subcommand group and (read-only) MCP tool group `perf.*`.

**Tech Stack:** Python 3.12+ · OpenTelemetry SDK 1.27+ · psycopg 3 · FastAPI · Typer · SQLite (stdlib) · pytest + pytest-asyncio

---

## File Structure

**New files:**

| Path | Responsibility |
|---|---|
| `src/dazzle/perf/__init__.py` | Package marker + re-exports of `configure_tracer`, `dazzle_span`, `instrument_app`. |
| `src/dazzle/perf/exporter.py` | `SQLiteSpanExporter(SpanExporter)` — converts OTel spans to our 3-table schema. |
| `src/dazzle/perf/schema.sql` | DDL for the trace store (`runs`, `spans`, `events` tables + indices). Loaded once when the SQLite file is created. |
| `src/dazzle/perf/serializer.py` | `pydantic_attrs(model, prefix)` — flattens a Pydantic model into a `dict[str, scalar]` suitable for OTel span attributes. |
| `src/dazzle/perf/tracer.py` | `configure_tracer(run_id, db_path)` returns a configured `TracerProvider`. `dazzle_span(name, **attrs)` context manager / decorator that wraps `tracer.start_as_current_span` and accepts Pydantic models in `**attrs`. |
| `src/dazzle/perf/instrument.py` | `instrument_app(app)` — applies FastAPI, psycopg, and asyncio auto-instrumentations and sets a `request_id` baggage propagator. |
| `src/dazzle/perf/storage.py` | Read-side queries over the SQLite schema. Pure-function API: `list_runs`, `get_run`, `iter_spans`, `iter_events`. |
| `src/dazzle/perf/findings/__init__.py` | Re-exports the public `build_findings(run_id) -> FindingsReport` and `Finding` dataclasses. |
| `src/dazzle/perf/findings/types.py` | `Finding`, `FindingsReport`, `SlowEndpoint`, `SlowQuery`, `NPlusOne`, `SlowPhase`, `RenderFanOut`, `BootCost`, `ExceptionFinding` Pydantic models. |
| `src/dazzle/perf/findings/extractor.py` | Heuristics: each category becomes a function that takes a `Storage` handle + thresholds and returns its `Finding` list. |
| `src/dazzle/perf/findings/render.py` | `render_markdown(report)` and `render_json(report)` formatters. |
| `src/dazzle/perf/run_id.py` | `make_run_id()` — `YYYYMMDD-HHMMSS-<short-uuid>` strings, plus `latest_run_id(perf_dir)` resolver. |
| `src/dazzle/cli/perf.py` | Typer sub-app: `trace`, `report`, `list`, `show`. |
| `src/dazzle/cli/perf_impl/__init__.py` | Package marker. |
| `src/dazzle/cli/perf_impl/trace.py` | `trace_command` implementation. |
| `src/dazzle/cli/perf_impl/report.py` | `report_command` implementation. |
| `src/dazzle/cli/perf_impl/list.py` | `list_command` implementation. |
| `src/dazzle/cli/perf_impl/show.py` | `show_command` implementation. |
| `src/dazzle/mcp/server/handlers/perf.py` | MCP handler exposing `perf.list`, `perf.report`, `perf.show`. |
| `tests/unit/test_perf_serializer.py` | Pydantic-attrs flattener tests. |
| `tests/unit/test_perf_exporter.py` | SQLite span exporter round-trip tests. |
| `tests/unit/test_perf_storage.py` | Read-side query tests. |
| `tests/unit/test_perf_findings_slow_endpoints.py` | Slow-endpoint heuristic tests. |
| `tests/unit/test_perf_findings_slow_queries.py` | Slow-query heuristic tests. |
| `tests/unit/test_perf_findings_n_plus_one.py` | N+1 detection tests. |
| `tests/unit/test_perf_findings_slow_phases.py` | Slow Dazzle-phase tests. |
| `tests/unit/test_perf_findings_render_fanout.py` | Render fan-out tests. |
| `tests/unit/test_perf_findings_exceptions.py` | Exception-finding tests. |
| `tests/unit/test_perf_findings_render.py` | Markdown + JSON formatter tests. |
| `tests/unit/test_perf_run_id.py` | Run-id helper tests. |
| `tests/unit/test_perf_cli_trace.py` | CLI `trace` smoke test. |
| `tests/unit/test_perf_cli_report.py` | CLI `report` smoke test. |
| `tests/unit/test_perf_cli_list_show.py` | CLI `list` + `show` smoke tests. |
| `tests/unit/test_perf_mcp_handler.py` | MCP handler operations test. |
| `tests/unit/fixtures/perf/three_run_store.db` | Pre-seeded SQLite fixture used by reader-side tests (built by `tests/unit/conftest.py` helper, not checked in). |
| `docs/reference/perf-observability.md` | User-facing reference doc. |
| `docs/reference/perf-findings-schema.md` | JSON schema for the findings output (agent-consumption contract). |

**Modified files:**

| Path | Reason |
|---|---|
| `pyproject.toml` | Add `perf` extra carrying OTel SDK + three instrumentation packages. |
| `src/dazzle/cli/__init__.py` | Register the new `perf` Typer sub-app. |
| `src/dazzle/http/runtime/server.py:400-415` | Call `instrument_app(self._app)` when the `DAZZLE_PERF_ENABLED=1` env var is set (set by `dazzle perf trace` before launching the runtime). |
| `src/dazzle/http/runtime/predicate_compiler.py` | Wrap `compile_predicate` body with `dazzle_span("predicate.compile", expr=...)`. |
| `src/dazzle/http/runtime/aggregate_expression.py` | Wrap `compile_aggregate_expression` with `dazzle_span("aggregate.expression.compile", expr=...)`. |
| `src/dazzle/http/runtime/aggregate.py` | Wrap `build_aggregate_sql` with `dazzle_span("aggregate.build_sql", measures=..., dimension_count=...)`. |
| `src/dazzle/http/runtime/repository.py` | Wrap `Repository.aggregate` with `dazzle_span("repo.aggregate", entity=..., dim_count=...)`. |
| `src/dazzle/render/fragment/renderer/_render_dashboard.py` | Wrap region render with `dazzle_span("region.render", kind=...)` (one outermost site only — region-internal nesting is observed via auto-instrumentation). |
| `src/dazzle/render/fragment/renderer/_emit.py` | Wrap fragment emit with `dazzle_span("fragment.emit", kind=...)`. |
| `src/dazzle/core/dsl_parser.py` | Wrap top-level `parse_dsl` with `dazzle_span("dsl.parse", path=...)`. |
| `src/dazzle/mcp/server/handlers_consolidated.py` | Register the new `perf` tool group. |
| `src/dazzle/mcp/server/tools_consolidated.py` | Add the `perf` tool's JSON schema. |
| `.gitignore` | Add `.dazzle/perf/`. |
| `CHANGELOG.md` | Entry under Added. |
| `pyproject.toml` (version) | Bump to `0.71.69` at the end. |

**Schema (`schema.sql`):**

```sql
CREATE TABLE runs (
  run_id          TEXT PRIMARY KEY,
  started_at      TEXT NOT NULL,        -- ISO 8601 UTC
  ended_at        TEXT,                  -- nullable until finalised
  app_name        TEXT,
  manifest_path   TEXT,
  command_line    TEXT NOT NULL
);

CREATE TABLE spans (
  span_id         TEXT PRIMARY KEY,
  trace_id        TEXT NOT NULL,
  parent_span_id  TEXT,                  -- nullable for root spans
  run_id          TEXT NOT NULL,
  name            TEXT NOT NULL,
  kind            TEXT NOT NULL,         -- "internal" | "server" | "client" | etc.
  status          TEXT NOT NULL,         -- "ok" | "error"
  started_ns      INTEGER NOT NULL,      -- ns since unix epoch
  ended_ns        INTEGER NOT NULL,
  duration_ns     INTEGER NOT NULL,      -- ended_ns - started_ns, denormalised for query speed
  attributes_json TEXT NOT NULL,         -- JSON object of attribute key→scalar
  FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX idx_spans_run_id          ON spans(run_id);
CREATE INDEX idx_spans_parent          ON spans(run_id, parent_span_id);
CREATE INDEX idx_spans_name_duration   ON spans(run_id, name, duration_ns DESC);

CREATE TABLE events (
  event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  span_id         TEXT NOT NULL,
  run_id          TEXT NOT NULL,
  name            TEXT NOT NULL,
  timestamp_ns    INTEGER NOT NULL,
  attributes_json TEXT NOT NULL,
  FOREIGN KEY (span_id) REFERENCES spans(span_id)
);

CREATE INDEX idx_events_span ON events(span_id);
```

---

## Task 1: Add the `perf` optional-dependencies extra

**Files:**
- Modify: `pyproject.toml:92-145`

- [ ] **Step 1: Append a new `perf` extra after the `dev` block**

Insert this block in `pyproject.toml` immediately before the line that begins `# Runtime server dependencies for \`dazzle serve --local\``:

```toml
# On-demand local OpenTelemetry tracing for `dazzle perf` (#1153 follow-on).
# Local-only by design — the bundled SQLite span exporter writes traces to
# `.dazzle/perf/<run-id>.db`. No OTLP collector required; users who want
# upstream collectors can pair this extra with their own exporter config.
perf = [
    "opentelemetry-api>=1.27,<2",
    "opentelemetry-sdk>=1.27,<2",
    "opentelemetry-instrumentation-fastapi>=0.48b0",
    "opentelemetry-instrumentation-psycopg>=0.48b0",
    "opentelemetry-instrumentation-asyncio>=0.48b0",
]
```

- [ ] **Step 2: Reinstall the dev environment with the new extra**

Run: `pip install -e ".[dev,perf,llm,mcp]"`
Expected: completes cleanly; `pip list | grep opentelemetry` shows the three instrumentation packages.

- [ ] **Step 3: Sanity-check the OTel imports**

Run: `python -c "from opentelemetry.sdk.trace import TracerProvider; from opentelemetry.sdk.trace.export import SpanExporter; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add perf extra (OTel SDK + auto-instrumentations) for dazzle perf"
```

---

## Task 2: Run-id helper

**Files:**
- Create: `src/dazzle/perf/__init__.py`
- Create: `src/dazzle/perf/run_id.py`
- Test: `tests/unit/test_perf_run_id.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_perf_run_id.py`:

```python
"""Run-id helper tests (#1153 follow-on)."""

from __future__ import annotations

import re
from pathlib import Path

from dazzle.perf.run_id import latest_run_id, make_run_id


def test_make_run_id_shape() -> None:
    rid = make_run_id()
    # YYYYMMDD-HHMMSS-XXXXXXXX where the tail is 8 hex chars.
    assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{8}", rid)


def test_make_run_id_unique() -> None:
    ids = {make_run_id() for _ in range(50)}
    assert len(ids) == 50


def test_latest_run_id_returns_newest(tmp_path: Path) -> None:
    perf_dir = tmp_path / "perf"
    perf_dir.mkdir()
    (perf_dir / "20260101-000000-aaaaaaaa.db").touch()
    (perf_dir / "20260201-000000-bbbbbbbb.db").touch()
    (perf_dir / "20260115-000000-cccccccc.db").touch()
    assert latest_run_id(perf_dir) == "20260201-000000-bbbbbbbb"


def test_latest_run_id_none_when_empty(tmp_path: Path) -> None:
    perf_dir = tmp_path / "perf"
    perf_dir.mkdir()
    assert latest_run_id(perf_dir) is None


def test_latest_run_id_none_when_missing(tmp_path: Path) -> None:
    assert latest_run_id(tmp_path / "does-not-exist") is None


def test_latest_run_id_ignores_non_db_files(tmp_path: Path) -> None:
    perf_dir = tmp_path / "perf"
    perf_dir.mkdir()
    (perf_dir / "20260101-000000-aaaaaaaa.db").touch()
    (perf_dir / "README.txt").touch()
    assert latest_run_id(perf_dir) == "20260101-000000-aaaaaaaa"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_perf_run_id.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.perf'`

- [ ] **Step 3: Create the package marker**

Create `src/dazzle/perf/__init__.py`:

```python
"""On-demand local tracing for ``dazzle perf`` (#1153 follow-on).

Public surface — re-exported from submodules so callers don't need to
remember which file each helper lives in:

- :func:`configure_tracer` (in ``tracer.py``)
- :func:`dazzle_span` (in ``tracer.py``)
- :func:`instrument_app` (in ``instrument.py``)

The exporter, serializer, storage, and findings layers stay namespaced
under their submodules — those are read by the CLI / MCP handlers,
not by framework callers.
"""

from __future__ import annotations
```

- [ ] **Step 4: Implement `run_id.py`**

Create `src/dazzle/perf/run_id.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_perf_run_id.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/perf/__init__.py src/dazzle/perf/run_id.py tests/unit/test_perf_run_id.py
git commit -m "feat(perf): add run-id helper + perf package skeleton"
```

---

## Task 3: Pydantic-aware span attribute serialiser

**Files:**
- Create: `src/dazzle/perf/serializer.py`
- Test: `tests/unit/test_perf_serializer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_perf_serializer.py`:

```python
"""Pydantic-attrs flattener tests."""

from __future__ import annotations

from pydantic import BaseModel

from dazzle.perf.serializer import pydantic_attrs


class Inner(BaseModel):
    name: str
    count: int


class Outer(BaseModel):
    label: str
    inner: Inner
    flags: list[str]


def test_flattens_pydantic_model_with_dotted_keys() -> None:
    m = Outer(label="x", inner=Inner(name="y", count=3), flags=["a", "b"])
    attrs = pydantic_attrs(m, prefix="op")
    assert attrs == {
        "op.label": "x",
        "op.inner.name": "y",
        "op.inner.count": 3,
        "op.flags": "[\"a\", \"b\"]",
    }


def test_handles_none_values_by_omission() -> None:
    class WithNone(BaseModel):
        a: str
        b: int | None = None

    attrs = pydantic_attrs(WithNone(a="x"), prefix="op")
    assert attrs == {"op.a": "x"}


def test_lists_of_models_render_as_json() -> None:
    m = Outer(label="x", inner=Inner(name="y", count=1), flags=[])
    attrs = pydantic_attrs(m, prefix="op")
    assert attrs["op.flags"] == "[]"


def test_non_pydantic_input_raises_typeerror() -> None:
    import pytest

    with pytest.raises(TypeError):
        pydantic_attrs({"x": 1}, prefix="op")  # type: ignore[arg-type]


def test_empty_prefix_emits_unprefixed_keys() -> None:
    m = Inner(name="y", count=3)
    attrs = pydantic_attrs(m, prefix="")
    assert attrs == {"name": "y", "count": 3}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_perf_serializer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.perf.serializer'`

- [ ] **Step 3: Implement the serialiser**

Create `src/dazzle/perf/serializer.py`:

```python
"""Flatten Pydantic models into OTel-compatible span attribute dicts.

OTel span attributes must be primitives (str / int / float / bool) or
sequences of primitives. This module recursively walks a Pydantic
model and produces a flat ``dict[str, scalar]`` keyed by dotted paths.

Lists/tuples that contain only primitives are JSON-encoded into one
string attribute (preserving structure while staying within OTel's
type rules). Lists of nested models are similarly JSON-encoded — they
shouldn't be common in span attrs, but the fallback prevents crashes.

``None`` values are omitted — OTel discourages explicit nulls and our
findings extractor treats missing keys as absent.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

_Scalar = str | int | float | bool


def pydantic_attrs(model: BaseModel, *, prefix: str) -> dict[str, _Scalar]:
    """Return a flat ``dict[str, scalar]`` for ``model``.

    Args:
        model: A Pydantic model instance.
        prefix: Dotted-path prefix prepended to every key. Pass ``""``
            to emit unprefixed keys.

    Raises:
        TypeError: when ``model`` is not a Pydantic model instance.
    """
    if not isinstance(model, BaseModel):
        raise TypeError(
            f"pydantic_attrs() requires a Pydantic model, got {type(model).__name__}"
        )
    out: dict[str, _Scalar] = {}
    _walk(model.model_dump(mode="python"), prefix, out)
    return out


def _walk(value: Any, key: str, out: dict[str, _Scalar]) -> None:
    if value is None:
        return
    if isinstance(value, bool | int | float | str):
        out[key] = value
        return
    if isinstance(value, dict):
        for k, v in value.items():
            sub_key = f"{key}.{k}" if key else str(k)
            _walk(v, sub_key, out)
        return
    if isinstance(value, list | tuple):
        # Lists are JSON-encoded into a single string attribute so the
        # full structure is preserved without splitting into N keys.
        out[key] = json.dumps(list(value), default=str)
        return
    # Fallback for unexpected types — stringify so the span attr still
    # captures something useful.
    out[key] = str(value)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_perf_serializer.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/perf/serializer.py tests/unit/test_perf_serializer.py
git commit -m "feat(perf): pydantic-aware span attribute serialiser"
```

---

## Task 4: SQLite span exporter

**Files:**
- Create: `src/dazzle/perf/schema.sql`
- Create: `src/dazzle/perf/exporter.py`
- Test: `tests/unit/test_perf_exporter.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_perf_exporter.py`:

```python
"""SQLite span exporter round-trip tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from dazzle.perf.exporter import SQLiteSpanExporter


def _make_provider(db_path: Path, run_id: str) -> TracerProvider:
    provider = TracerProvider()
    exporter = SQLiteSpanExporter(db_path=db_path, run_id=run_id)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


def test_exporter_writes_root_span(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    provider = _make_provider(db, "test-run-1")
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("root.op") as span:
        span.set_attribute("foo", "bar")

    provider.force_flush()
    rows = sqlite3.connect(db).execute(
        "SELECT name, status, attributes_json FROM spans"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "root.op"
    assert rows[0][1] == "ok"
    assert json.loads(rows[0][2]) == {"foo": "bar"}


def test_exporter_records_parent_child(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    provider = _make_provider(db, "test-run-2")
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("root"):
        with tracer.start_as_current_span("child"):
            pass
    provider.force_flush()

    rows = sqlite3.connect(db).execute(
        "SELECT name, parent_span_id IS NULL FROM spans ORDER BY started_ns"
    ).fetchall()
    assert rows[0] == ("root", 1)  # root has no parent
    assert rows[1] == ("child", 0)  # child has a parent


def test_exporter_records_error_status(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    provider = _make_provider(db, "test-run-3")
    tracer = provider.get_tracer("test")
    try:
        with tracer.start_as_current_span("boom"):
            raise RuntimeError("kaboom")
    except RuntimeError:
        pass
    provider.force_flush()

    (status,) = sqlite3.connect(db).execute(
        "SELECT status FROM spans"
    ).fetchone()
    assert status == "error"


def test_exporter_records_events(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    provider = _make_provider(db, "test-run-4")
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("op") as span:
        span.add_event("milestone", {"k": "v"})
    provider.force_flush()

    rows = sqlite3.connect(db).execute(
        "SELECT name, attributes_json FROM events"
    ).fetchall()
    assert rows == [("milestone", json.dumps({"k": "v"}))]


def test_exporter_writes_run_row_with_metadata(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    exporter = SQLiteSpanExporter(
        db_path=db,
        run_id="r1",
        app_name="examples/simple_task",
        manifest_path="/tmp/dazzle.toml",
        command_line="dazzle perf trace --url /tasks",
    )
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    provider.get_tracer("t").start_as_current_span("op").__enter__().end()
    provider.force_flush()

    row = sqlite3.connect(db).execute(
        "SELECT app_name, manifest_path, command_line FROM runs"
    ).fetchone()
    assert row == (
        "examples/simple_task",
        "/tmp/dazzle.toml",
        "dazzle perf trace --url /tasks",
    )


def test_exporter_force_flush_finalises_ended_at(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    exporter = SQLiteSpanExporter(db_path=db, run_id="r1")
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    provider.get_tracer("t").start_as_current_span("op").__enter__().end()
    exporter.shutdown()

    (ended,) = sqlite3.connect(db).execute(
        "SELECT ended_at FROM runs"
    ).fetchone()
    assert ended is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_perf_exporter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dazzle.perf.exporter'`

- [ ] **Step 3: Add the schema file**

Create `src/dazzle/perf/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS runs (
  run_id          TEXT PRIMARY KEY,
  started_at      TEXT NOT NULL,
  ended_at        TEXT,
  app_name        TEXT,
  manifest_path   TEXT,
  command_line    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS spans (
  span_id         TEXT PRIMARY KEY,
  trace_id        TEXT NOT NULL,
  parent_span_id  TEXT,
  run_id          TEXT NOT NULL,
  name            TEXT NOT NULL,
  kind            TEXT NOT NULL,
  status          TEXT NOT NULL,
  started_ns      INTEGER NOT NULL,
  ended_ns        INTEGER NOT NULL,
  duration_ns     INTEGER NOT NULL,
  attributes_json TEXT NOT NULL,
  FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_spans_run_id          ON spans(run_id);
CREATE INDEX IF NOT EXISTS idx_spans_parent          ON spans(run_id, parent_span_id);
CREATE INDEX IF NOT EXISTS idx_spans_name_duration   ON spans(run_id, name, duration_ns DESC);

CREATE TABLE IF NOT EXISTS events (
  event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  span_id         TEXT NOT NULL,
  run_id          TEXT NOT NULL,
  name            TEXT NOT NULL,
  timestamp_ns    INTEGER NOT NULL,
  attributes_json TEXT NOT NULL,
  FOREIGN KEY (span_id) REFERENCES spans(span_id)
);

CREATE INDEX IF NOT EXISTS idx_events_span ON events(span_id);
```

- [ ] **Step 4: Implement the exporter**

Create `src/dazzle/perf/exporter.py`:

```python
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
        self._conn = sqlite3.connect(self._db_path, isolation_level=None)
        self._conn.executescript(_SCHEMA_PATH.read_text())
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
        parent = span.parent
        parent_span_id = (
            f"{parent.span_id:016x}" if parent and parent.span_id else None
        )
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
        ended = _dt.datetime.now(_dt.UTC).isoformat()
        self._conn.execute(
            "UPDATE runs SET ended_at = ? WHERE run_id = ?",
            (ended, self._run_id),
        )
        self._conn.close()


def _coerce(value: Any) -> Any:
    """Coerce non-JSON-serialisable OTel attribute values to strings."""
    if isinstance(value, bool | int | float | str | list | tuple | dict) or value is None:
        return value
    return str(value)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_perf_exporter.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/perf/schema.sql src/dazzle/perf/exporter.py tests/unit/test_perf_exporter.py
git commit -m "feat(perf): SQLite span exporter with per-run schema"
```

---

## Task 5: Tracer + `dazzle_span` helper

**Files:**
- Create: `src/dazzle/perf/tracer.py`
- Test: `tests/unit/test_perf_tracer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_perf_tracer.py`:

```python
"""Tracer configuration + dazzle_span helper tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pydantic import BaseModel

from dazzle.perf.tracer import configure_tracer, dazzle_span


class _Probe(BaseModel):
    label: str
    count: int


def test_configure_tracer_returns_provider(tmp_path: Path) -> None:
    provider = configure_tracer(
        run_id="r1", db_path=tmp_path / "run.db", batch=False
    )
    assert provider is not None


def test_dazzle_span_writes_span_attrs(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    configure_tracer(run_id="r1", db_path=db, batch=False)
    with dazzle_span("phase.op", entity="Task"):
        pass

    (name, attrs_json) = sqlite3.connect(db).execute(
        "SELECT name, attributes_json FROM spans"
    ).fetchone()
    assert name == "phase.op"
    assert "entity" in attrs_json
    assert "Task" in attrs_json


def test_dazzle_span_flattens_pydantic_model(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    configure_tracer(run_id="r1", db_path=db, batch=False)
    with dazzle_span("phase.op", probe=_Probe(label="x", count=3)):
        pass

    (attrs_json,) = sqlite3.connect(db).execute(
        "SELECT attributes_json FROM spans"
    ).fetchone()
    assert "probe.label" in attrs_json
    assert "probe.count" in attrs_json


def test_dazzle_span_is_no_op_when_uninitialised() -> None:
    """Importing dazzle_span without calling configure_tracer must not
    crash; spans become no-ops via OTel's default NoOpTracer."""
    from dazzle.perf.tracer import reset_tracer

    reset_tracer()
    with dazzle_span("phase.op", x=1):
        pass  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_perf_tracer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the tracer**

Create `src/dazzle/perf/tracer.py`:

```python
"""Configure the OpenTelemetry tracer for ``dazzle perf`` runs.

Exposes two public entry points:

- :func:`configure_tracer` — call once at process start to wire up
  the SQLite exporter. Returns the configured ``TracerProvider``.
- :func:`dazzle_span` — context manager / decorator that creates a
  span on the framework tracer. Accepts a mix of scalar and Pydantic-
  model attributes; models are flattened via
  :func:`dazzle.perf.serializer.pydantic_attrs`.

When ``configure_tracer`` hasn't been called, ``dazzle_span`` resolves
the tracer from OTel's global provider (the default ``NoOpTracer``)
and silently does nothing — the framework can keep its
``dazzle_span(...)`` decorators in place without a runtime penalty
when tracing is disabled.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
)
from pydantic import BaseModel

from dazzle.perf.exporter import SQLiteSpanExporter
from dazzle.perf.serializer import pydantic_attrs

_TRACER_NAME = "dazzle"
_initialised = False


def configure_tracer(
    *,
    run_id: str,
    db_path: Path,
    batch: bool = True,
    app_name: str | None = None,
    manifest_path: str | None = None,
    command_line: str = "",
) -> TracerProvider:
    """Initialise the global tracer provider to write to ``db_path``.

    Args:
        run_id: Unique id for this trace session.
        db_path: SQLite file. Parent directories are created if missing.
        batch: When True, spans flush in batches (production default).
            Tests pass False so spans land synchronously and can be read
            back inside the test body.
        app_name / manifest_path / command_line: Metadata persisted to
            the ``runs`` row.
    """
    global _initialised
    provider = TracerProvider()
    exporter = SQLiteSpanExporter(
        db_path=db_path,
        run_id=run_id,
        app_name=app_name,
        manifest_path=manifest_path,
        command_line=command_line,
    )
    processor: Any = (
        BatchSpanProcessor(exporter) if batch else SimpleSpanProcessor(exporter)
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    _initialised = True
    return provider


def reset_tracer() -> None:
    """Drop back to OTel's default ``NoOpTracerProvider``.

    Test-only entry point — production code never calls this; the
    process exits after a single trace run.
    """
    global _initialised
    # OTel doesn't expose an unset; reassigning to a fresh ProxyTracerProvider
    # achieves the same effect because subsequent ``get_tracer`` calls
    # fall back to the no-op tracer when no exporter is attached.
    trace.set_tracer_provider(trace.ProxyTracerProvider())
    _initialised = False


@contextlib.contextmanager
def dazzle_span(name: str, **attrs: Any):
    """Open a span on the ``dazzle`` tracer.

    ``attrs`` accept any mix of scalar OTel attribute values and
    Pydantic model instances; models are flattened with
    :func:`pydantic_attrs` and prefixed with the keyword name.

    Example::

        with dazzle_span("aggregate.expression.compile", expr=ref.expression):
            ...

    When the tracer hasn't been configured, this is effectively a
    no-op — OTel's ``NoOpTracer`` returns a non-recording span.
    """
    tracer = trace.get_tracer(_TRACER_NAME)
    flat: dict[str, Any] = {}
    for key, value in attrs.items():
        if value is None:
            continue
        if isinstance(value, BaseModel):
            flat.update(pydantic_attrs(value, prefix=key))
        else:
            flat[key] = value
    with tracer.start_as_current_span(name, attributes=flat) as span:
        yield span
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_perf_tracer.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/perf/tracer.py tests/unit/test_perf_tracer.py
git commit -m "feat(perf): configure_tracer + dazzle_span helper"
```

---

## Task 6: Auto-instrumentation glue

**Files:**
- Create: `src/dazzle/perf/instrument.py`
- Test: `tests/unit/test_perf_instrument.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_perf_instrument.py`:

```python
"""Auto-instrumentation glue tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.perf.instrument import instrument_app
from dazzle.perf.tracer import configure_tracer, reset_tracer


@pytest.fixture
def trace_db(tmp_path: Path) -> Path:
    db = tmp_path / "run.db"
    configure_tracer(run_id="r1", db_path=db, batch=False)
    yield db
    reset_tracer()


def test_instrument_app_captures_request_span(trace_db: Path) -> None:
    app = FastAPI()

    @app.get("/hello")
    def hello() -> dict[str, str]:
        return {"ok": "yes"}

    instrument_app(app)
    client = TestClient(app)
    response = client.get("/hello")
    assert response.status_code == 200

    rows = sqlite3.connect(trace_db).execute(
        "SELECT name, status FROM spans"
    ).fetchall()
    # FastAPI instrumentation names server spans after the route template.
    assert any("GET /hello" in r[0] for r in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_perf_instrument.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the glue**

Create `src/dazzle/perf/instrument.py`:

```python
"""Apply OTel auto-instrumentations to a Dazzle runtime app.

Called once from the runtime server when ``DAZZLE_PERF_ENABLED=1`` is
set in the environment (``dazzle perf trace`` sets the var before
launching ``dazzle serve``). Importing the instrumentation packages is
deferred so the framework's normal startup path doesn't pull OTel in
when the ``perf`` extra isn't installed.
"""

from __future__ import annotations

from typing import Any


def instrument_app(app: Any) -> None:
    """Wrap ``app`` with FastAPI / psycopg / asyncio instrumentation.

    Idempotent — repeated calls are tolerated by the underlying OTel
    instrumentation packages.
    """
    from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    PsycopgInstrumentor().instrument()
    AsyncioInstrumentor().instrument()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_perf_instrument.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/perf/instrument.py tests/unit/test_perf_instrument.py
git commit -m "feat(perf): FastAPI + psycopg + asyncio auto-instrumentation"
```

---

## Task 7: Storage (read-side) helpers

**Files:**
- Create: `src/dazzle/perf/storage.py`
- Test: `tests/unit/test_perf_storage.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_perf_storage.py`:

```python
"""Storage read-side helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dazzle.perf.storage import (
    Span,
    get_run,
    iter_events,
    iter_spans,
    list_runs,
)


def _seed(db: Path, *, run_id: str) -> None:
    """Hand-craft a small trace to exercise the readers."""
    from dazzle.perf.exporter import _SCHEMA_PATH

    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, ended_at, app_name, command_line) "
        "VALUES (?, '2026-05-19T20:30:00Z', '2026-05-19T20:30:05Z', 'app', 'cmd')",
        (run_id,),
    )
    conn.execute(
        "INSERT INTO spans "
        "(span_id, trace_id, parent_span_id, run_id, name, kind, status, "
        " started_ns, ended_ns, duration_ns, attributes_json) "
        "VALUES "
        "('s1', 't1', NULL, ?, 'root', 'internal', 'ok',  0, 100, 100, '{}'),"
        "('s2', 't1', 's1',  ?, 'child','internal', 'ok', 10,  80,  70, '{\"k\": 1}')",
        (run_id, run_id),
    )
    conn.execute(
        "INSERT INTO events (span_id, run_id, name, timestamp_ns, attributes_json) "
        "VALUES ('s1', ?, 'milestone', 50, '{}')",
        (run_id,),
    )
    conn.commit()
    conn.close()


def test_list_runs_returns_runs(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(db, run_id="r1")
    runs = list(list_runs(db))
    assert len(runs) == 1
    assert runs[0].run_id == "r1"
    assert runs[0].app_name == "app"


def test_get_run_returns_single(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(db, run_id="r1")
    run = get_run(db, "r1")
    assert run is not None
    assert run.run_id == "r1"
    assert get_run(db, "nope") is None


def test_iter_spans_returns_typed_rows(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(db, run_id="r1")
    spans = list(iter_spans(db, "r1"))
    by_name = {s.name: s for s in spans}
    assert {"root", "child"} == set(by_name)
    assert by_name["child"].parent_span_id == "s1"
    assert by_name["child"].duration_ns == 70
    assert by_name["child"].attributes == {"k": 1}


def test_iter_events_returns_rows(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(db, run_id="r1")
    events = list(iter_events(db, "r1"))
    assert len(events) == 1
    assert events[0].name == "milestone"


def test_span_dataclass_is_immutable(tmp_path: Path) -> None:
    import dataclasses

    import pytest

    s = Span(
        span_id="s",
        trace_id="t",
        parent_span_id=None,
        run_id="r",
        name="n",
        kind="internal",
        status="ok",
        started_ns=0,
        ended_ns=1,
        duration_ns=1,
        attributes={},
    )
    assert dataclasses.is_dataclass(s)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.name = "x"  # type: ignore[misc]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_perf_storage.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement storage**

Create `src/dazzle/perf/storage.py`:

```python
"""Read-side queries over the perf SQLite store.

Pure functions over an immutable schema (see ``schema.sql``). The
findings extractor and CLI report formatter share these helpers — no
side-effects, no caching, one connection per call.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class Run:
    run_id: str
    started_at: str
    ended_at: str | None
    app_name: str | None
    manifest_path: str | None
    command_line: str


@dataclasses.dataclass(frozen=True)
class Span:
    span_id: str
    trace_id: str
    parent_span_id: str | None
    run_id: str
    name: str
    kind: str
    status: str
    started_ns: int
    ended_ns: int
    duration_ns: int
    attributes: dict[str, object]


@dataclasses.dataclass(frozen=True)
class Event:
    span_id: str
    run_id: str
    name: str
    timestamp_ns: int
    attributes: dict[str, object]


def list_runs(db_path: Path) -> Iterator[Run]:
    """Yield every ``runs`` row, newest first."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT run_id, started_at, ended_at, app_name, manifest_path, "
            "       command_line "
            "FROM runs ORDER BY started_at DESC"
        ).fetchall()
    for row in rows:
        yield Run(**dict(row))


def get_run(db_path: Path, run_id: str) -> Run | None:
    """Return a single ``Run`` or ``None`` when the id doesn't match."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT run_id, started_at, ended_at, app_name, manifest_path, "
            "       command_line "
            "FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    return Run(**dict(row)) if row else None


def iter_spans(db_path: Path, run_id: str) -> Iterator[Span]:
    """Yield every ``Span`` belonging to ``run_id``, oldest first."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT span_id, trace_id, parent_span_id, run_id, name, kind, "
            "       status, started_ns, ended_ns, duration_ns, attributes_json "
            "FROM spans WHERE run_id = ? ORDER BY started_ns",
            (run_id,),
        ).fetchall()
    for row in rows:
        data = dict(row)
        attrs_json = data.pop("attributes_json")
        data["attributes"] = json.loads(attrs_json) if attrs_json else {}
        yield Span(**data)


def iter_events(db_path: Path, run_id: str) -> Iterator[Event]:
    """Yield every ``Event`` belonging to ``run_id``."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT span_id, run_id, name, timestamp_ns, attributes_json "
            "FROM events WHERE run_id = ? ORDER BY timestamp_ns",
            (run_id,),
        ).fetchall()
    for row in rows:
        data = dict(row)
        attrs_json = data.pop("attributes_json")
        data["attributes"] = json.loads(attrs_json) if attrs_json else {}
        yield Event(**data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_perf_storage.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/perf/storage.py tests/unit/test_perf_storage.py
git commit -m "feat(perf): SQLite read-side helpers (Run/Span/Event)"
```

---

## Task 8: Findings types

**Files:**
- Create: `src/dazzle/perf/findings/__init__.py`
- Create: `src/dazzle/perf/findings/types.py`
- Test: `tests/unit/test_perf_findings_types.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_perf_findings_types.py`:

```python
"""Findings type tests — pin the agent-consumption schema."""

from __future__ import annotations

from dazzle.perf.findings.types import (
    BootCost,
    ExceptionFinding,
    Finding,
    FindingsReport,
    NPlusOne,
    RenderFanOut,
    SlowEndpoint,
    SlowPhase,
    SlowQuery,
)


def test_findings_report_round_trips_json() -> None:
    report = FindingsReport(
        run_id="r1",
        app_name="examples/simple_task",
        started_at="2026-05-19T20:00:00Z",
        ended_at="2026-05-19T20:00:05Z",
        slow_endpoints=[
            SlowEndpoint(route="GET /tasks", calls=12, total_ms=4200.0, p95_ms=380.0),
        ],
        slow_queries=[
            SlowQuery(statement="SELECT FROM task", calls=12, total_ms=1100.0),
        ],
        n_plus_one=[
            NPlusOne(parent_span="GET /tasks", child_statement="SELECT FROM user", repetitions=24),
        ],
        slow_phases=[
            SlowPhase(name="aggregate.build_sql", calls=8, total_ms=120.0, max_ms=30.0),
        ],
        render_fanout=[
            RenderFanOut(route="GET /tasks", region_renders=18, total_ms=600.0),
        ],
        boot_cost=BootCost(parse_dsl_ms=240.0, route_gen_ms=80.0, total_ms=400.0),
        exceptions=[
            ExceptionFinding(span_name="repo.aggregate", message="bad SQL", count=1),
        ],
    )
    payload = report.model_dump_json()
    revived = FindingsReport.model_validate_json(payload)
    assert revived == report


def test_finding_is_a_union_alias() -> None:
    f: Finding = SlowEndpoint(route="GET /", calls=1, total_ms=1.0, p95_ms=1.0)
    assert isinstance(f, SlowEndpoint)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_perf_findings_types.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the types**

Create `src/dazzle/perf/findings/__init__.py`:

```python
"""Findings package — heuristics + formatters over the perf SQLite store."""

from __future__ import annotations

from dazzle.perf.findings.extractor import build_findings
from dazzle.perf.findings.render import render_json, render_markdown
from dazzle.perf.findings.types import (
    BootCost,
    ExceptionFinding,
    Finding,
    FindingsReport,
    NPlusOne,
    RenderFanOut,
    SlowEndpoint,
    SlowPhase,
    SlowQuery,
)

__all__ = [
    "build_findings",
    "render_json",
    "render_markdown",
    "Finding",
    "FindingsReport",
    "BootCost",
    "ExceptionFinding",
    "NPlusOne",
    "RenderFanOut",
    "SlowEndpoint",
    "SlowPhase",
    "SlowQuery",
]
```

Create `src/dazzle/perf/findings/types.py`:

```python
"""Findings schema — the agent-consumption contract.

JSON serialisation of :class:`FindingsReport` is the source of truth
that downstream tools (CLI `--format json`, MCP `perf.report`) emit.
The contract is documented in
``docs/reference/perf-findings-schema.md`` — when fields change here,
update that doc in the same commit.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SlowEndpoint(BaseModel):
    route: str
    calls: int
    total_ms: float
    p95_ms: float
    model_config = ConfigDict(frozen=True)


class SlowQuery(BaseModel):
    statement: str
    calls: int
    total_ms: float
    model_config = ConfigDict(frozen=True)


class NPlusOne(BaseModel):
    parent_span: str
    child_statement: str
    repetitions: int
    model_config = ConfigDict(frozen=True)


class SlowPhase(BaseModel):
    name: str
    calls: int
    total_ms: float
    max_ms: float
    model_config = ConfigDict(frozen=True)


class RenderFanOut(BaseModel):
    route: str
    region_renders: int
    total_ms: float
    model_config = ConfigDict(frozen=True)


class BootCost(BaseModel):
    parse_dsl_ms: float
    route_gen_ms: float
    total_ms: float
    model_config = ConfigDict(frozen=True)


class ExceptionFinding(BaseModel):
    span_name: str
    message: str
    count: int
    model_config = ConfigDict(frozen=True)


Finding = (
    SlowEndpoint
    | SlowQuery
    | NPlusOne
    | SlowPhase
    | RenderFanOut
    | BootCost
    | ExceptionFinding
)


class FindingsReport(BaseModel):
    run_id: str
    app_name: str | None
    started_at: str
    ended_at: str | None
    slow_endpoints: list[SlowEndpoint] = []
    slow_queries: list[SlowQuery] = []
    n_plus_one: list[NPlusOne] = []
    slow_phases: list[SlowPhase] = []
    render_fanout: list[RenderFanOut] = []
    boot_cost: BootCost | None = None
    exceptions: list[ExceptionFinding] = []
    model_config = ConfigDict(frozen=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_perf_findings_types.py -v`
Expected: PASS (2 tests). Note: `build_findings` / `render_*` are imported by `findings/__init__.py` but don't exist yet — the test only imports from `types.py`, so it should pass. The package import will fail until later tasks land their modules; the temporary fix below covers that.

- [ ] **Step 5: Add temporary stubs so the package imports cleanly**

Create `src/dazzle/perf/findings/extractor.py`:

```python
"""Findings extractor (skeleton — heuristics land in Task 9–14)."""

from __future__ import annotations

from pathlib import Path

from dazzle.perf.findings.types import FindingsReport


def build_findings(db_path: Path, run_id: str) -> FindingsReport:
    """Placeholder — full heuristics land in Task 9–14."""
    raise NotImplementedError
```

Create `src/dazzle/perf/findings/render.py`:

```python
"""Findings formatters (skeleton — implemented in Task 15)."""

from __future__ import annotations

from dazzle.perf.findings.types import FindingsReport


def render_markdown(report: FindingsReport) -> str:
    raise NotImplementedError


def render_json(report: FindingsReport) -> str:
    return report.model_dump_json(indent=2)
```

- [ ] **Step 6: Re-run the test to confirm imports still work**

Run: `pytest tests/unit/test_perf_findings_types.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/perf/findings/ tests/unit/test_perf_findings_types.py
git commit -m "feat(perf): findings schema (types + skeleton package)"
```

---

## Task 9: Slow-endpoint heuristic

**Files:**
- Modify: `src/dazzle/perf/findings/extractor.py`
- Test: `tests/unit/test_perf_findings_slow_endpoints.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_perf_findings_slow_endpoints.py`:

```python
"""Slow-endpoint heuristic tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dazzle.perf.findings.extractor import slow_endpoints
from dazzle.perf.exporter import _SCHEMA_PATH


def _seed_endpoint_spans(db: Path, calls: list[tuple[str, int]]) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    for i, (name, duration_ns) in enumerate(calls):
        conn.execute(
            "INSERT INTO spans "
            "(span_id, trace_id, parent_span_id, run_id, name, kind, status, "
            " started_ns, ended_ns, duration_ns, attributes_json) "
            "VALUES (?, 't', NULL, 'r1', ?, 'server', 'ok', ?, ?, ?, '{}')",
            (f"s{i}", name, i * 1000, i * 1000 + duration_ns, duration_ns),
        )
    conn.commit()
    conn.close()


def test_slow_endpoints_ranks_by_total(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed_endpoint_spans(
        db,
        [
            ("GET /tasks", 1_000_000),  # 1ms
            ("GET /tasks", 2_000_000),  # 2ms
            ("GET /users", 5_000_000),  # 5ms
        ],
    )
    results = slow_endpoints(db, "r1", top=10)
    assert results[0].route == "GET /users"
    assert results[0].total_ms == 5.0
    assert results[1].route == "GET /tasks"
    assert results[1].calls == 2
    assert results[1].total_ms == 3.0


def test_slow_endpoints_only_server_kind(tmp_path: Path) -> None:
    """``kind="internal"`` spans are not endpoints — must be filtered out."""
    db = tmp_path / "run.db"
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    conn.execute(
        "INSERT INTO spans VALUES "
        "('s1','t',NULL,'r1','internal_op','internal','ok',0,1000,1000,'{}')"
    )
    conn.commit()
    conn.close()

    assert slow_endpoints(db, "r1", top=10) == []


def test_slow_endpoints_top_n_caps_results(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed_endpoint_spans(
        db,
        [(f"GET /r{i}", 1000) for i in range(20)],
    )
    results = slow_endpoints(db, "r1", top=5)
    assert len(results) == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_perf_findings_slow_endpoints.py -v`
Expected: FAIL with `ImportError: cannot import name 'slow_endpoints'`

- [ ] **Step 3: Implement `slow_endpoints`**

Replace `src/dazzle/perf/findings/extractor.py` with:

```python
"""Findings heuristics — one function per category, plus the top-level
``build_findings`` that runs them all.

Each heuristic takes a ``db_path`` + ``run_id`` + tuning knobs and
returns its slice of the ``FindingsReport``. The functions are exposed
individually so tests can pin each heuristic in isolation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dazzle.perf.findings.types import (
    FindingsReport,
    SlowEndpoint,
)


def slow_endpoints(db_path: Path, run_id: str, *, top: int = 10) -> list[SlowEndpoint]:
    """Top-N endpoints by total wall time. Computes p95 with SQLite's
    NTILE so we don't load all spans into Python.

    Filters on ``kind = 'server'`` — only FastAPI request spans count as
    endpoints; framework-internal spans are surfaced via
    :func:`slow_phases`.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            WITH endpoint_calls AS (
                SELECT name, duration_ns
                FROM spans
                WHERE run_id = ? AND kind = 'server'
            ),
            ranked AS (
                SELECT
                    name,
                    duration_ns,
                    NTILE(20) OVER (PARTITION BY name ORDER BY duration_ns) AS bucket
                FROM endpoint_calls
            ),
            p95 AS (
                SELECT name, MAX(duration_ns) AS p95_ns
                FROM ranked
                WHERE bucket <= 19
                GROUP BY name
            )
            SELECT
                e.name AS route,
                COUNT(*) AS calls,
                SUM(e.duration_ns) / 1e6 AS total_ms,
                COALESCE(p95.p95_ns, MAX(e.duration_ns)) / 1e6 AS p95_ms
            FROM endpoint_calls e
            LEFT JOIN p95 USING (name)
            GROUP BY e.name
            ORDER BY total_ms DESC
            LIMIT ?
            """,
            (run_id, top),
        ).fetchall()
    return [
        SlowEndpoint(
            route=row["route"],
            calls=int(row["calls"]),
            total_ms=float(row["total_ms"]),
            p95_ms=float(row["p95_ms"]),
        )
        for row in rows
    ]


def build_findings(db_path: Path, run_id: str) -> FindingsReport:
    """Run every heuristic and assemble the FindingsReport.

    Currently wires :func:`slow_endpoints`. Subsequent tasks add the
    other heuristics and append them here.
    """
    from dazzle.perf.storage import get_run

    run = get_run(db_path, run_id)
    if run is None:
        raise ValueError(f"run not found: {run_id}")
    return FindingsReport(
        run_id=run.run_id,
        app_name=run.app_name,
        started_at=run.started_at,
        ended_at=run.ended_at,
        slow_endpoints=slow_endpoints(db_path, run_id),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_perf_findings_slow_endpoints.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/perf/findings/extractor.py tests/unit/test_perf_findings_slow_endpoints.py
git commit -m "feat(perf): slow-endpoint heuristic"
```

---

## Task 10: Slow-query heuristic

**Files:**
- Modify: `src/dazzle/perf/findings/extractor.py`
- Test: `tests/unit/test_perf_findings_slow_queries.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_perf_findings_slow_queries.py`:

```python
"""Slow-query heuristic tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dazzle.perf.findings.extractor import (
    normalise_statement,
    slow_queries,
)
from dazzle.perf.exporter import _SCHEMA_PATH


def test_normalise_statement_strips_literals_and_collapses_whitespace() -> None:
    assert (
        normalise_statement("SELECT  * FROM task WHERE id = 'abc-123'")
        == "SELECT * FROM task WHERE id = ?"
    )
    assert (
        normalise_statement("UPDATE t SET x = 42 WHERE y = 1")
        == "UPDATE t SET x = ? WHERE y = ?"
    )
    assert (
        normalise_statement('INSERT INTO t VALUES ("a", "b")')
        == "INSERT INTO t VALUES (?, ?)"
    )


def _seed_query_spans(db: Path, queries: list[tuple[str, int]]) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    import json

    for i, (stmt, dur) in enumerate(queries):
        attrs = json.dumps({"db.statement": stmt})
        conn.execute(
            "INSERT INTO spans "
            "(span_id, trace_id, parent_span_id, run_id, name, kind, status, "
            " started_ns, ended_ns, duration_ns, attributes_json) "
            "VALUES (?, 't', NULL, 'r1', ?, 'client', 'ok', ?, ?, ?, ?)",
            (f"s{i}", "psycopg.query", i * 1000, i * 1000 + dur, dur, attrs),
        )
    conn.commit()
    conn.close()


def test_slow_queries_clusters_by_normalised_statement(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed_query_spans(
        db,
        [
            ("SELECT * FROM task WHERE id = '1'", 1_000_000),
            ("SELECT * FROM task WHERE id = '2'", 2_000_000),
            ("SELECT * FROM user WHERE id = '1'", 5_000_000),
        ],
    )
    results = slow_queries(db, "r1", top=10)
    assert results[0].statement == "SELECT * FROM user WHERE id = ?"
    assert results[1].statement == "SELECT * FROM task WHERE id = ?"
    assert results[1].calls == 2
    assert results[1].total_ms == 3.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_perf_findings_slow_queries.py -v`
Expected: FAIL with `ImportError: cannot import name 'slow_queries'`

- [ ] **Step 3: Add the helpers**

Add to `src/dazzle/perf/findings/extractor.py` (above `build_findings`):

```python
import json
import re
from collections import defaultdict

from dazzle.perf.findings.types import SlowQuery

_LITERAL_PATTERNS = [
    re.compile(r"'(?:[^']|'')*'"),         # single-quoted strings
    re.compile(r'"(?:[^"]|"")*"'),         # double-quoted strings
    re.compile(r"\b\d+(?:\.\d+)?\b"),      # numeric literals
]


def normalise_statement(stmt: str) -> str:
    """Replace string + numeric literals with ``?`` and collapse whitespace.

    Crude but effective for clustering psycopg ``db.statement`` attrs —
    the exact literal values aren't useful to a finding, but the shape
    of the query is.
    """
    out = stmt
    for pattern in _LITERAL_PATTERNS:
        out = pattern.sub("?", out)
    return re.sub(r"\s+", " ", out).strip()


def slow_queries(db_path: Path, run_id: str, *, top: int = 10) -> list[SlowQuery]:
    """Top-N SQL statements by total wall time, clustered by normalised form."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT duration_ns, attributes_json
            FROM spans
            WHERE run_id = ? AND kind = 'client'
              AND attributes_json LIKE '%"db.statement"%'
            """,
            (run_id,),
        ).fetchall()

    buckets: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        attrs = json.loads(row["attributes_json"])
        raw = attrs.get("db.statement")
        if not isinstance(raw, str):
            continue
        buckets[normalise_statement(raw)].append(int(row["duration_ns"]))

    findings = [
        SlowQuery(
            statement=stmt,
            calls=len(durations),
            total_ms=sum(durations) / 1e6,
        )
        for stmt, durations in buckets.items()
    ]
    findings.sort(key=lambda f: f.total_ms, reverse=True)
    return findings[:top]
```

Update the `build_findings` body to call it:

```python
def build_findings(db_path: Path, run_id: str) -> FindingsReport:
    from dazzle.perf.storage import get_run

    run = get_run(db_path, run_id)
    if run is None:
        raise ValueError(f"run not found: {run_id}")
    return FindingsReport(
        run_id=run.run_id,
        app_name=run.app_name,
        started_at=run.started_at,
        ended_at=run.ended_at,
        slow_endpoints=slow_endpoints(db_path, run_id),
        slow_queries=slow_queries(db_path, run_id),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_perf_findings_slow_queries.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/perf/findings/extractor.py tests/unit/test_perf_findings_slow_queries.py
git commit -m "feat(perf): slow-query heuristic with statement normalisation"
```

---

## Task 11: N+1 detector

**Files:**
- Modify: `src/dazzle/perf/findings/extractor.py`
- Test: `tests/unit/test_perf_findings_n_plus_one.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_perf_findings_n_plus_one.py`:

```python
"""N+1 detection tests — at least 3 identical normalised child queries
under one parent span flag the parent."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dazzle.perf.findings.extractor import detect_n_plus_one
from dazzle.perf.exporter import _SCHEMA_PATH


def _seed(db: Path, parent_name: str, child_statements: list[str]) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    conn.execute(
        "INSERT INTO spans VALUES "
        "('p', 't', NULL, 'r1', ?, 'server', 'ok', 0, 100, 100, '{}')",
        (parent_name,),
    )
    for i, stmt in enumerate(child_statements):
        attrs = json.dumps({"db.statement": stmt})
        conn.execute(
            "INSERT INTO spans VALUES "
            "(?, 't', 'p', 'r1', 'psycopg.query', 'client', 'ok', "
            " ?, ?, ?, ?)",
            (f"c{i}", i, i + 10, 10, attrs),
        )
    conn.commit()
    conn.close()


def test_three_identical_queries_flagged(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(
        db,
        "GET /tasks",
        [
            "SELECT FROM user WHERE id = '1'",
            "SELECT FROM user WHERE id = '2'",
            "SELECT FROM user WHERE id = '3'",
        ],
    )
    findings = detect_n_plus_one(db, "r1", threshold=3)
    assert len(findings) == 1
    assert findings[0].parent_span == "GET /tasks"
    assert findings[0].repetitions == 3


def test_below_threshold_ignored(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(
        db,
        "GET /tasks",
        [
            "SELECT FROM user WHERE id = '1'",
            "SELECT FROM user WHERE id = '2'",
        ],
    )
    assert detect_n_plus_one(db, "r1", threshold=3) == []


def test_distinct_statements_not_clustered(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(
        db,
        "GET /tasks",
        [
            "SELECT FROM user WHERE id = '1'",
            "SELECT FROM tag WHERE id = '1'",
            "SELECT FROM role WHERE id = '1'",
        ],
    )
    assert detect_n_plus_one(db, "r1", threshold=3) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_perf_findings_n_plus_one.py -v`
Expected: FAIL with `ImportError: cannot import name 'detect_n_plus_one'`

- [ ] **Step 3: Implement**

Add to `src/dazzle/perf/findings/extractor.py`:

```python
from dazzle.perf.findings.types import NPlusOne


def detect_n_plus_one(
    db_path: Path, run_id: str, *, threshold: int = 3
) -> list[NPlusOne]:
    """Flag every (parent_span, normalised_child_statement) pair whose
    repetition count meets ``threshold``."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                parent.name           AS parent_name,
                child.attributes_json AS child_attrs
            FROM spans AS child
            JOIN spans AS parent
              ON parent.span_id = child.parent_span_id
             AND parent.run_id  = child.run_id
            WHERE child.run_id = ?
              AND child.kind = 'client'
              AND child.attributes_json LIKE '%"db.statement"%'
            """,
            (run_id,),
        ).fetchall()

    buckets: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        attrs = json.loads(row["child_attrs"])
        raw = attrs.get("db.statement")
        if not isinstance(raw, str):
            continue
        buckets[(row["parent_name"], normalise_statement(raw))] += 1

    findings = [
        NPlusOne(parent_span=parent, child_statement=stmt, repetitions=count)
        for (parent, stmt), count in buckets.items()
        if count >= threshold
    ]
    findings.sort(key=lambda f: f.repetitions, reverse=True)
    return findings
```

Update `build_findings`:

```python
return FindingsReport(
    run_id=run.run_id,
    app_name=run.app_name,
    started_at=run.started_at,
    ended_at=run.ended_at,
    slow_endpoints=slow_endpoints(db_path, run_id),
    slow_queries=slow_queries(db_path, run_id),
    n_plus_one=detect_n_plus_one(db_path, run_id),
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_perf_findings_n_plus_one.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/perf/findings/extractor.py tests/unit/test_perf_findings_n_plus_one.py
git commit -m "feat(perf): N+1 detector (threshold ≥3 identical child queries)"
```

---

## Task 12: Slow Dazzle-phase heuristic

**Files:**
- Modify: `src/dazzle/perf/findings/extractor.py`
- Test: `tests/unit/test_perf_findings_slow_phases.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_perf_findings_slow_phases.py`:

```python
"""Slow Dazzle-phase tests — ranks our manually-instrumented spans."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dazzle.perf.findings.extractor import slow_phases
from dazzle.perf.exporter import _SCHEMA_PATH


_DAZZLE_PHASES = (
    "dsl.parse",
    "predicate.compile",
    "aggregate.expression.compile",
    "aggregate.build_sql",
    "repo.aggregate",
    "region.render",
    "fragment.emit",
)


def _seed_phase_spans(db: Path, rows: list[tuple[str, int]]) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    for i, (name, dur) in enumerate(rows):
        conn.execute(
            "INSERT INTO spans VALUES "
            "(?, 't', NULL, 'r1', ?, 'internal', 'ok', ?, ?, ?, '{}')",
            (f"s{i}", name, i * 1000, i * 1000 + dur, dur),
        )
    conn.commit()
    conn.close()


def test_slow_phases_aggregates_and_ranks(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed_phase_spans(
        db,
        [
            ("aggregate.build_sql", 30_000_000),  # 30 ms
            ("aggregate.build_sql", 10_000_000),  # 10 ms
            ("predicate.compile",   5_000_000),   #  5 ms
        ],
    )
    results = slow_phases(db, "r1", top=10)
    by_name = {r.name: r for r in results}
    assert by_name["aggregate.build_sql"].calls == 2
    assert by_name["aggregate.build_sql"].total_ms == 40.0
    assert by_name["aggregate.build_sql"].max_ms == 30.0
    assert by_name["predicate.compile"].calls == 1


def test_slow_phases_filters_to_known_phase_names(tmp_path: Path) -> None:
    """Non-Dazzle span names (e.g. unrelated auto-instrumentation) are
    excluded so this finding stays focused on framework hot paths."""
    db = tmp_path / "run.db"
    _seed_phase_spans(
        db,
        [
            ("aggregate.build_sql", 10_000_000),
            ("some.other.span", 50_000_000),
        ],
    )
    names = {r.name for r in slow_phases(db, "r1", top=10)}
    assert names == {"aggregate.build_sql"}


def test_known_phase_set_pinned() -> None:
    """The phase set is a public contract — pin it here so a future
    rename or addition is intentional."""
    from dazzle.perf.findings.extractor import DAZZLE_PHASE_NAMES

    assert set(DAZZLE_PHASE_NAMES) == set(_DAZZLE_PHASES)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_perf_findings_slow_phases.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement**

Add to `src/dazzle/perf/findings/extractor.py`:

```python
from dazzle.perf.findings.types import SlowPhase

DAZZLE_PHASE_NAMES: tuple[str, ...] = (
    "dsl.parse",
    "predicate.compile",
    "aggregate.expression.compile",
    "aggregate.build_sql",
    "repo.aggregate",
    "region.render",
    "fragment.emit",
)


def slow_phases(db_path: Path, run_id: str, *, top: int = 10) -> list[SlowPhase]:
    """Aggregate the manually-instrumented Dazzle spans by name and rank
    by total wall time. Span names outside :data:`DAZZLE_PHASE_NAMES`
    are excluded so this finding stays focused on framework hot paths."""
    placeholders = ", ".join("?" for _ in DAZZLE_PHASE_NAMES)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT
                name,
                COUNT(*) AS calls,
                SUM(duration_ns) / 1e6 AS total_ms,
                MAX(duration_ns) / 1e6 AS max_ms
            FROM spans
            WHERE run_id = ? AND name IN ({placeholders})
            GROUP BY name
            ORDER BY total_ms DESC
            LIMIT ?
            """,
            (run_id, *DAZZLE_PHASE_NAMES, top),
        ).fetchall()
    return [
        SlowPhase(
            name=row["name"],
            calls=int(row["calls"]),
            total_ms=float(row["total_ms"]),
            max_ms=float(row["max_ms"]),
        )
        for row in rows
    ]
```

Update `build_findings`:

```python
slow_phases=slow_phases(db_path, run_id),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_perf_findings_slow_phases.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/perf/findings/extractor.py tests/unit/test_perf_findings_slow_phases.py
git commit -m "feat(perf): slow Dazzle-phase heuristic (whitelisted span names)"
```

---

## Task 13: Render fan-out + boot cost + exceptions

**Files:**
- Modify: `src/dazzle/perf/findings/extractor.py`
- Test: `tests/unit/test_perf_findings_render_fanout.py`
- Test: `tests/unit/test_perf_findings_exceptions.py`
- Test: `tests/unit/test_perf_findings_boot_cost.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_perf_findings_render_fanout.py`:

```python
"""Render fan-out heuristic — count region.render spans under each request."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dazzle.perf.findings.extractor import render_fanout
from dazzle.perf.exporter import _SCHEMA_PATH


def _seed(db: Path, route: str, region_count: int) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    conn.execute(
        "INSERT INTO spans VALUES "
        "('p', 't', NULL, 'r1', ?, 'server', 'ok', 0, 1000, 1000, '{}')",
        (route,),
    )
    for i in range(region_count):
        conn.execute(
            "INSERT INTO spans VALUES "
            "(?, 't', 'p', 'r1', 'region.render', 'internal', 'ok', "
            " ?, ?, 50, '{}')",
            (f"r{i}", i, i + 50),
        )
    conn.commit()
    conn.close()


def test_render_fanout_counts_per_request(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(db, "GET /dashboard", region_count=18)
    results = render_fanout(db, "r1", top=10)
    assert results[0].route == "GET /dashboard"
    assert results[0].region_renders == 18
```

Create `tests/unit/test_perf_findings_exceptions.py`:

```python
"""Exception finding tests — surface spans with status=error."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dazzle.perf.findings.extractor import exceptions_from_errors
from dazzle.perf.exporter import _SCHEMA_PATH


def _seed(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    attrs = json.dumps({"error.message": "bad SQL"})
    conn.execute(
        "INSERT INTO spans VALUES "
        "('s1', 't', NULL, 'r1', 'repo.aggregate', 'internal', 'error', "
        " 0, 1, 1, ?)",
        (attrs,),
    )
    conn.execute(
        "INSERT INTO spans VALUES "
        "('s2', 't', NULL, 'r1', 'repo.aggregate', 'internal', 'error', "
        " 2, 3, 1, ?)",
        (attrs,),
    )
    conn.commit()
    conn.close()


def test_exceptions_clusters_by_span_name_and_message(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(db)
    results = exceptions_from_errors(db, "r1")
    assert len(results) == 1
    assert results[0].span_name == "repo.aggregate"
    assert results[0].message == "bad SQL"
    assert results[0].count == 2
```

Create `tests/unit/test_perf_findings_boot_cost.py`:

```python
"""Boot cost — sum of dsl.parse + route-generation spans (well-known names)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dazzle.perf.findings.extractor import boot_cost
from dazzle.perf.exporter import _SCHEMA_PATH


def test_boot_cost_sums_known_phases(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    conn.executescript(
        """
        INSERT INTO spans VALUES
          ('a', 't', NULL, 'r1', 'dsl.parse',  'internal', 'ok',  0,  240_000_000, 240_000_000, '{}'),
          ('b', 't', NULL, 'r1', 'route.gen',  'internal', 'ok',  240_000_000, 320_000_000, 80_000_000, '{}');
        """
    )
    conn.commit()
    conn.close()

    cost = boot_cost(db, "r1")
    assert cost is not None
    assert cost.parse_dsl_ms == 240.0
    assert cost.route_gen_ms == 80.0
    assert cost.total_ms == 320.0


def test_boot_cost_returns_none_when_no_boot_spans(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    conn.commit()
    conn.close()
    assert boot_cost(db, "r1") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_perf_findings_render_fanout.py tests/unit/test_perf_findings_exceptions.py tests/unit/test_perf_findings_boot_cost.py -v`
Expected: FAIL (3 files) with `ImportError`

- [ ] **Step 3: Implement**

Add to `src/dazzle/perf/findings/extractor.py`:

```python
from dazzle.perf.findings.types import (
    BootCost,
    ExceptionFinding,
    RenderFanOut,
)


def render_fanout(
    db_path: Path, run_id: str, *, top: int = 10
) -> list[RenderFanOut]:
    """For each request span, count its descendant ``region.render`` spans
    and sum their durations."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                parent.name                AS route,
                COUNT(child.span_id)       AS region_renders,
                SUM(child.duration_ns) / 1e6 AS total_ms
            FROM spans AS child
            JOIN spans AS parent
              ON parent.span_id = child.parent_span_id
             AND parent.run_id  = child.run_id
            WHERE child.run_id = ?
              AND child.name   = 'region.render'
              AND parent.kind  = 'server'
            GROUP BY parent.name
            ORDER BY region_renders DESC
            LIMIT ?
            """,
            (run_id, top),
        ).fetchall()
    return [
        RenderFanOut(
            route=row["route"],
            region_renders=int(row["region_renders"]),
            total_ms=float(row["total_ms"] or 0.0),
        )
        for row in rows
    ]


def boot_cost(db_path: Path, run_id: str) -> BootCost | None:
    """Sum the parse + route-generation cost from well-known boot span
    names. Returns ``None`` when neither span fired (the run never
    booted, or instrumentation wasn't loaded for the boot phase)."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT name, SUM(duration_ns) / 1e6 AS ms
            FROM spans
            WHERE run_id = ? AND name IN ('dsl.parse', 'route.gen')
            GROUP BY name
            """,
            (run_id,),
        ).fetchall()
    if not rows:
        return None
    by_name = {row["name"]: float(row["ms"]) for row in rows}
    parse = by_name.get("dsl.parse", 0.0)
    route = by_name.get("route.gen", 0.0)
    return BootCost(parse_dsl_ms=parse, route_gen_ms=route, total_ms=parse + route)


def exceptions_from_errors(
    db_path: Path, run_id: str
) -> list[ExceptionFinding]:
    """Cluster ``status='error'`` spans by ``(span name, error message)``."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT name, attributes_json FROM spans "
            "WHERE run_id = ? AND status = 'error'",
            (run_id,),
        ).fetchall()
    buckets: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        attrs = json.loads(row["attributes_json"])
        message = str(attrs.get("error.message", "<no message>"))
        buckets[(row["name"], message)] += 1
    return [
        ExceptionFinding(span_name=name, message=msg, count=count)
        for (name, msg), count in sorted(
            buckets.items(), key=lambda kv: kv[1], reverse=True
        )
    ]
```

Update `build_findings`:

```python
return FindingsReport(
    run_id=run.run_id,
    app_name=run.app_name,
    started_at=run.started_at,
    ended_at=run.ended_at,
    slow_endpoints=slow_endpoints(db_path, run_id),
    slow_queries=slow_queries(db_path, run_id),
    n_plus_one=detect_n_plus_one(db_path, run_id),
    slow_phases=slow_phases(db_path, run_id),
    render_fanout=render_fanout(db_path, run_id),
    boot_cost=boot_cost(db_path, run_id),
    exceptions=exceptions_from_errors(db_path, run_id),
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_perf_findings_render_fanout.py tests/unit/test_perf_findings_exceptions.py tests/unit/test_perf_findings_boot_cost.py -v`
Expected: PASS (5 tests total)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/perf/findings/extractor.py tests/unit/test_perf_findings_render_fanout.py tests/unit/test_perf_findings_exceptions.py tests/unit/test_perf_findings_boot_cost.py
git commit -m "feat(perf): render fan-out + boot cost + exceptions heuristics"
```

---

## Task 14: Markdown + JSON formatters

**Files:**
- Modify: `src/dazzle/perf/findings/render.py`
- Test: `tests/unit/test_perf_findings_render.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_perf_findings_render.py`:

```python
"""Formatter tests — Markdown shape pinned for agent paste-in."""

from __future__ import annotations

from dazzle.perf.findings.render import render_json, render_markdown
from dazzle.perf.findings.types import (
    BootCost,
    ExceptionFinding,
    FindingsReport,
    NPlusOne,
    RenderFanOut,
    SlowEndpoint,
    SlowPhase,
    SlowQuery,
)


def _full_report() -> FindingsReport:
    return FindingsReport(
        run_id="r1",
        app_name="examples/simple_task",
        started_at="2026-05-19T20:00:00Z",
        ended_at="2026-05-19T20:00:05Z",
        slow_endpoints=[
            SlowEndpoint(route="GET /tasks", calls=12, total_ms=4200.0, p95_ms=380.0),
        ],
        slow_queries=[
            SlowQuery(statement="SELECT FROM task", calls=12, total_ms=1100.0),
        ],
        n_plus_one=[
            NPlusOne(parent_span="GET /tasks", child_statement="SELECT FROM user", repetitions=24),
        ],
        slow_phases=[
            SlowPhase(name="aggregate.build_sql", calls=8, total_ms=120.0, max_ms=30.0),
        ],
        render_fanout=[
            RenderFanOut(route="GET /tasks", region_renders=18, total_ms=600.0),
        ],
        boot_cost=BootCost(parse_dsl_ms=240.0, route_gen_ms=80.0, total_ms=320.0),
        exceptions=[
            ExceptionFinding(span_name="repo.aggregate", message="bad SQL", count=1),
        ],
    )


def test_render_markdown_contains_each_section() -> None:
    out = render_markdown(_full_report())
    assert "# Perf report — r1" in out
    assert "## Slow endpoints" in out
    assert "GET /tasks" in out
    assert "## Slow queries" in out
    assert "## Suspected N+1 patterns" in out
    assert "## Dazzle hot phases" in out
    assert "## Render fan-out" in out
    assert "## Boot cost" in out
    assert "## Errors / exceptions" in out


def test_render_markdown_omits_empty_sections() -> None:
    report = FindingsReport(
        run_id="r1",
        app_name=None,
        started_at="2026-05-19T20:00:00Z",
        ended_at=None,
    )
    out = render_markdown(report)
    assert "# Perf report — r1" in out
    assert "## Slow endpoints" not in out
    assert "## Suspected N+1 patterns" not in out


def test_render_json_round_trips() -> None:
    report = _full_report()
    payload = render_json(report)
    assert '"run_id": "r1"' in payload
    revived = FindingsReport.model_validate_json(payload)
    assert revived == report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_perf_findings_render.py -v`
Expected: FAIL (NotImplementedError in `render_markdown`)

- [ ] **Step 3: Implement the formatters**

Replace `src/dazzle/perf/findings/render.py` with:

```python
"""Format a :class:`FindingsReport` for human or agent consumption.

Markdown is the default — designed to paste straight into a Claude
conversation. Empty sections are omitted so the output stays short
when nothing's wrong.

JSON output uses Pydantic's standard serialisation; the schema is
pinned in ``docs/reference/perf-findings-schema.md``.
"""

from __future__ import annotations

from dazzle.perf.findings.types import FindingsReport


def render_json(report: FindingsReport) -> str:
    return report.model_dump_json(indent=2)


def render_markdown(report: FindingsReport) -> str:
    lines: list[str] = []
    header = f"# Perf report — {report.run_id}"
    if report.app_name:
        header += f" ({report.app_name})"
    lines.append(header)
    lines.append(f"Started: {report.started_at} — Ended: {report.ended_at or '(running)'}")
    lines.append("")

    if report.slow_endpoints:
        lines.append("## Slow endpoints")
        lines.append("| Route | Calls | Total (ms) | p95 (ms) |")
        lines.append("|---|---|---|---|")
        for e in report.slow_endpoints:
            lines.append(f"| `{e.route}` | {e.calls} | {e.total_ms:.1f} | {e.p95_ms:.1f} |")
        lines.append("")

    if report.slow_queries:
        lines.append("## Slow queries")
        lines.append("| Statement | Calls | Total (ms) |")
        lines.append("|---|---|---|")
        for q in report.slow_queries:
            lines.append(f"| `{q.statement}` | {q.calls} | {q.total_ms:.1f} |")
        lines.append("")

    if report.n_plus_one:
        lines.append("## Suspected N+1 patterns")
        lines.append("| Parent span | Child query | Repetitions |")
        lines.append("|---|---|---|")
        for n in report.n_plus_one:
            lines.append(
                f"| `{n.parent_span}` | `{n.child_statement}` | {n.repetitions} |"
            )
        lines.append("")

    if report.slow_phases:
        lines.append("## Dazzle hot phases")
        lines.append("| Phase | Calls | Total (ms) | Max single (ms) |")
        lines.append("|---|---|---|---|")
        for p in report.slow_phases:
            lines.append(
                f"| `{p.name}` | {p.calls} | {p.total_ms:.1f} | {p.max_ms:.1f} |"
            )
        lines.append("")

    if report.render_fanout:
        lines.append("## Render fan-out")
        lines.append("| Route | Region renders | Total (ms) |")
        lines.append("|---|---|---|")
        for r in report.render_fanout:
            lines.append(f"| `{r.route}` | {r.region_renders} | {r.total_ms:.1f} |")
        lines.append("")

    if report.boot_cost is not None:
        bc = report.boot_cost
        lines.append("## Boot cost")
        lines.append(
            f"- `dsl.parse`: {bc.parse_dsl_ms:.1f} ms · "
            f"`route.gen`: {bc.route_gen_ms:.1f} ms · "
            f"total: {bc.total_ms:.1f} ms"
        )
        lines.append("")

    if report.exceptions:
        lines.append("## Errors / exceptions")
        lines.append("| Span | Message | Count |")
        lines.append("|---|---|---|")
        for x in report.exceptions:
            lines.append(f"| `{x.span_name}` | {x.message} | {x.count} |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_perf_findings_render.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/perf/findings/render.py tests/unit/test_perf_findings_render.py
git commit -m "feat(perf): Markdown + JSON findings formatters"
```

---

## Task 15: Hot-path span decorators in framework code

**Files:**
- Modify: `src/dazzle/http/runtime/predicate_compiler.py`
- Modify: `src/dazzle/http/runtime/aggregate_expression.py`
- Modify: `src/dazzle/http/runtime/aggregate.py`
- Modify: `src/dazzle/http/runtime/repository.py`
- Modify: `src/dazzle/render/fragment/renderer/_emit.py`
- Modify: `src/dazzle/render/fragment/renderer/_render_dashboard.py`
- Modify: `src/dazzle/core/dsl_parser.py`
- Test: `tests/unit/test_perf_hot_path_spans.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/unit/test_perf_hot_path_spans.py`:

```python
"""Pin the manual-span instrumentation against every hot path.

Each test triggers the production code path and asserts a named span
appears in the trace store. Uses ``configure_tracer(batch=False)`` so
spans are flushed synchronously inside the test body.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dazzle.perf.tracer import configure_tracer, reset_tracer


@pytest.fixture
def trace_db(tmp_path: Path) -> Path:
    db = tmp_path / "run.db"
    configure_tracer(run_id="r1", db_path=db, batch=False)
    yield db
    reset_tracer()


def _names(db: Path) -> set[str]:
    return {
        r[0]
        for r in sqlite3.connect(db).execute("SELECT name FROM spans")
    }


def test_aggregate_expression_compile_emits_span(trace_db: Path) -> None:
    from dazzle.http.runtime.aggregate_expression import (
        compile_aggregate_expression,
    )
    from dazzle.core.ir import AggregateExpr

    compile_aggregate_expression(AggregateExpr(column_name="score"))
    assert "aggregate.expression.compile" in _names(trace_db)


def test_build_aggregate_sql_emits_span(trace_db: Path) -> None:
    from dazzle.http.runtime.aggregate import build_aggregate_sql

    build_aggregate_sql(
        table_name="t",
        placeholder_style="%s",
        dimensions=[],
        measures={"primary": "count"},
        filters=None,
    )
    assert "aggregate.build_sql" in _names(trace_db)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_perf_hot_path_spans.py -v`
Expected: FAIL — the spans aren't emitted yet.

- [ ] **Step 3: Wrap `compile_aggregate_expression`**

Open `src/dazzle/http/runtime/aggregate_expression.py` and replace the body of `compile_aggregate_expression`:

```python
def compile_aggregate_expression(
    expr: AggregateExpr,
    *,
    placeholder: str = "%s",
    table_alias: str | None = None,
) -> tuple[str, list[Any]]:
    """Compile an :class:`AggregateExpr` to ``(sql, params)``.
    ... (docstring unchanged)
    """
    from dazzle.perf.tracer import dazzle_span

    with dazzle_span(
        "aggregate.expression.compile",
        placeholder=placeholder,
        table_alias=table_alias,
        expr=expr,
    ):
        params: list[Any] = []
        sql = _compile(expr, params, placeholder, table_alias)
        return f"({sql})", params
```

- [ ] **Step 4: Wrap `build_aggregate_sql`**

In `src/dazzle/http/runtime/aggregate.py`, add an import near the top:

```python
from dazzle.perf.tracer import dazzle_span
```

Wrap the body of `build_aggregate_sql` so the existing implementation runs inside a span. The minimal change: wrap the entire current body of the function in `with dazzle_span("aggregate.build_sql", table_name=table_name, dimension_count=len(dimensions), measure_count=len(measures)):`.

- [ ] **Step 5: Wrap `compile_predicate`**

In `src/dazzle/http/runtime/predicate_compiler.py`, wrap the body of `compile_predicate` with:

```python
from dazzle.perf.tracer import dazzle_span
...
def compile_predicate(...):
    """..."""
    with dazzle_span("predicate.compile"):
        # existing body
        ...
```

- [ ] **Step 6: Wrap `Repository.aggregate`**

In `src/dazzle/http/runtime/repository.py`, wrap the body of `aggregate()` (line 600+) with `dazzle_span("repo.aggregate", entity=self.table_name, dimension_count=len(dimensions), measure_count=len(measures))`.

- [ ] **Step 7: Wrap fragment emit + dashboard region render**

In `src/dazzle/render/fragment/renderer/_emit.py`, find the top-level public emit function and wrap its body with `dazzle_span("fragment.emit", fragment_kind=...)` — pull the kind off the fragment instance.

In `src/dazzle/render/fragment/renderer/_render_dashboard.py`, find the per-region render entry point and wrap with `dazzle_span("region.render", region_kind=...)`.

- [ ] **Step 8: Wrap the top-level DSL parse**

In `src/dazzle/core/dsl_parser.py`, find the public `parse_dsl` (or equivalent) entry and wrap with `dazzle_span("dsl.parse", path=str(file_path))`.

- [ ] **Step 9: Run integration tests to verify they pass**

Run: `pytest tests/unit/test_perf_hot_path_spans.py -v`
Expected: PASS (2 tests)

- [ ] **Step 10: Run the broader regression slice**

Run: `pytest tests/ -m "not e2e" -x -q --ignore=tests/parser_corpus`
Expected: PASS (~15,480 tests). Note: parser-corpus snapshot tests may need regenerating if the DSL parse path now nests a span around emission — if any fail with snapshot drift, run `--snapshot-update` and recommit.

- [ ] **Step 11: Commit**

```bash
git add src/dazzle/http/runtime/predicate_compiler.py src/dazzle/http/runtime/aggregate_expression.py src/dazzle/http/runtime/aggregate.py src/dazzle/http/runtime/repository.py src/dazzle/render/fragment/renderer/_emit.py src/dazzle/render/fragment/renderer/_render_dashboard.py src/dazzle/core/dsl_parser.py tests/unit/test_perf_hot_path_spans.py
git commit -m "feat(perf): wrap framework hot paths in dazzle_span()"
```

---

## Task 16: Wire instrumentation into the runtime server

**Files:**
- Modify: `src/dazzle/http/runtime/server.py:400-415`
- Test: `tests/unit/test_perf_server_integration.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_perf_server_integration.py`:

```python
"""Verify ``instrument_app`` is called on the FastAPI app when the
``DAZZLE_PERF_ENABLED`` env var is set, and not otherwise."""

from __future__ import annotations

import os
from unittest.mock import patch

from fastapi import FastAPI


def test_instrumentation_skipped_when_env_unset() -> None:
    from dazzle.http.runtime.server import _maybe_instrument_for_perf

    app = FastAPI()
    with patch.dict(os.environ, {}, clear=True):
        _maybe_instrument_for_perf(app)
    # Calling twice with the env off is harmless and emits nothing.


def test_instrumentation_runs_when_env_set() -> None:
    from dazzle.http.runtime.server import _maybe_instrument_for_perf

    app = FastAPI()
    called: list[FastAPI] = []

    def fake_instrument(received_app: FastAPI) -> None:
        called.append(received_app)

    with patch.dict(os.environ, {"DAZZLE_PERF_ENABLED": "1"}):
        with patch(
            "dazzle.perf.instrument.instrument_app", side_effect=fake_instrument
        ):
            _maybe_instrument_for_perf(app)
    assert called == [app]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_perf_server_integration.py -v`
Expected: FAIL with `ImportError: cannot import name '_maybe_instrument_for_perf'`

- [ ] **Step 3: Implement**

In `src/dazzle/http/runtime/server.py`, just before the line `def _create_app(self)` (around line 400), add:

```python
def _maybe_instrument_for_perf(app: Any) -> None:
    """Apply ``dazzle perf`` instrumentation when ``DAZZLE_PERF_ENABLED``
    is set. The env var is the only signal — `dazzle perf trace` sets
    it before spawning the runtime; humans starting the server directly
    don't pay the instrumentation cost.
    """
    import os

    if os.environ.get("DAZZLE_PERF_ENABLED") != "1":
        return
    from dazzle.perf.instrument import instrument_app

    instrument_app(app)
```

Then, inside `_create_app`, immediately after `self._app = _FastAPI(...)`, add:

```python
_maybe_instrument_for_perf(self._app)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_perf_server_integration.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/server.py tests/unit/test_perf_server_integration.py
git commit -m "feat(perf): server-side env-gated instrumentation"
```

---

## Task 17: CLI `dazzle perf list` and `show`

**Files:**
- Create: `src/dazzle/cli/perf.py`
- Create: `src/dazzle/cli/perf_impl/__init__.py`
- Create: `src/dazzle/cli/perf_impl/list.py`
- Create: `src/dazzle/cli/perf_impl/show.py`
- Modify: `src/dazzle/cli/__init__.py:84-100`
- Test: `tests/unit/test_perf_cli_list_show.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_perf_cli_list_show.py`:

```python
"""CLI smoke tests for `dazzle perf list` + `dazzle perf show`."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dazzle.cli import app
from dazzle.perf.exporter import _SCHEMA_PATH


@pytest.fixture
def seeded_perf_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    perf_dir = tmp_path / ".dazzle" / "perf"
    perf_dir.mkdir(parents=True)
    db = perf_dir / "20260519-120000-aaaaaaaa.db"
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, ended_at, app_name, command_line) "
        "VALUES ('20260519-120000-aaaaaaaa', '2026-05-19T12:00:00Z', "
        "        '2026-05-19T12:00:05Z', 'examples/simple_task', 'dazzle perf trace')"
    )
    conn.execute(
        "INSERT INTO spans VALUES "
        "('s1', 't', NULL, '20260519-120000-aaaaaaaa', 'GET /tasks', 'server', "
        " 'ok', 0, 1000, 1000, '{}')"
    )
    conn.commit()
    conn.close()
    return perf_dir


def test_perf_list_shows_run(seeded_perf_dir: Path) -> None:
    result = CliRunner().invoke(app, ["perf", "list"])
    assert result.exit_code == 0
    assert "20260519-120000-aaaaaaaa" in result.stdout
    assert "examples/simple_task" in result.stdout


def test_perf_show_dumps_span_tree(seeded_perf_dir: Path) -> None:
    result = CliRunner().invoke(
        app, ["perf", "show", "--run", "20260519-120000-aaaaaaaa"]
    )
    assert result.exit_code == 0
    assert "GET /tasks" in result.stdout


def test_perf_show_with_no_run_picks_latest(seeded_perf_dir: Path) -> None:
    result = CliRunner().invoke(app, ["perf", "show"])
    assert result.exit_code == 0
    assert "GET /tasks" in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_perf_cli_list_show.py -v`
Expected: FAIL — the `perf` sub-app doesn't exist yet.

- [ ] **Step 3: Implement the CLI**

Create `src/dazzle/cli/perf_impl/__init__.py`:

```python
"""dazzle perf CLI implementations."""
```

Create `src/dazzle/cli/perf_impl/list.py`:

```python
"""``dazzle perf list`` — show past runs in the current project."""

from __future__ import annotations

from pathlib import Path

import typer

from dazzle.perf.storage import list_runs


def list_command() -> None:
    """List past perf runs under ``.dazzle/perf/``."""
    perf_dir = Path.cwd() / ".dazzle" / "perf"
    if not perf_dir.exists():
        typer.echo("No perf runs yet — run `dazzle perf trace` first.")
        raise typer.Exit(0)
    found_any = False
    for db_path in sorted(perf_dir.glob("*.db")):
        for run in list_runs(db_path):
            found_any = True
            typer.echo(
                f"{run.run_id}  {run.started_at}  "
                f"{run.ended_at or '(running)'}  "
                f"{run.app_name or '-'}  "
                f"{run.command_line}"
            )
    if not found_any:
        typer.echo("No perf runs yet.")
```

Create `src/dazzle/cli/perf_impl/show.py`:

```python
"""``dazzle perf show`` — dump a span tree for one run."""

from __future__ import annotations

from pathlib import Path

import typer

from dazzle.perf.run_id import latest_run_id
from dazzle.perf.storage import iter_spans


def show_command(
    run: str | None = typer.Option(
        None, "--run", help="Run id (default: latest)"
    ),
) -> None:
    perf_dir = Path.cwd() / ".dazzle" / "perf"
    run_id = run or latest_run_id(perf_dir)
    if run_id is None:
        typer.echo("No perf runs found.")
        raise typer.Exit(1)
    db_path = perf_dir / f"{run_id}.db"
    if not db_path.exists():
        typer.echo(f"No trace file for run {run_id}")
        raise typer.Exit(1)

    children: dict[str | None, list] = {}
    for span in iter_spans(db_path, run_id):
        children.setdefault(span.parent_span_id, []).append(span)

    def emit(parent: str | None, depth: int) -> None:
        for span in children.get(parent, []):
            duration_ms = span.duration_ns / 1e6
            typer.echo(
                f"{'  ' * depth}{span.name}  "
                f"{duration_ms:.2f}ms  [{span.status}]"
            )
            emit(span.span_id, depth + 1)

    emit(None, 0)
```

Create `src/dazzle/cli/perf.py`:

```python
"""``dazzle perf`` Typer sub-app."""

from __future__ import annotations

import typer

from dazzle.cli.perf_impl.list import list_command
from dazzle.cli.perf_impl.show import show_command

perf_app = typer.Typer(help="On-demand local OpenTelemetry tracing.")
perf_app.command(name="list")(list_command)
perf_app.command(name="show")(show_command)
```

In `src/dazzle/cli/__init__.py`, locate the block where the other sub-apps are registered (search for `app.add_typer` or `app.command`) and add:

```python
from dazzle.cli.perf import perf_app
app.add_typer(perf_app, name="perf")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_perf_cli_list_show.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/perf.py src/dazzle/cli/perf_impl/ src/dazzle/cli/__init__.py tests/unit/test_perf_cli_list_show.py
git commit -m "feat(perf): dazzle perf list + show commands"
```

---

## Task 18: CLI `dazzle perf trace`

**Files:**
- Create: `src/dazzle/cli/perf_impl/trace.py`
- Modify: `src/dazzle/cli/perf.py`
- Test: `tests/unit/test_perf_cli_trace.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_perf_cli_trace.py`:

```python
"""``dazzle perf trace`` runs uvicorn in a subprocess; the unit test
exercises the pre-launch wiring (env var, db path planning) without
actually booting the server."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from dazzle.cli import app


@pytest.fixture
def cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dazzle.toml").write_text("[project]\nname='t'\n")
    return tmp_path


def test_trace_plans_run_db_and_sets_env(cwd: Path) -> None:
    captured: dict[str, object] = {}

    def fake_runner(*, run_id: str, db_path: Path, urls: tuple[str, ...], duration: int) -> None:
        captured["run_id"] = run_id
        captured["db_path"] = db_path
        captured["urls"] = urls
        captured["duration"] = duration

    with patch("dazzle.cli.perf_impl.trace._execute_trace_run", side_effect=fake_runner):
        result = CliRunner().invoke(
            app,
            ["perf", "trace", "--url", "/tasks", "--duration", "3"],
        )
    assert result.exit_code == 0
    assert captured["urls"] == ("/tasks",)
    assert captured["duration"] == 3
    assert isinstance(captured["db_path"], Path)
    assert captured["db_path"].parent.name == "perf"


def test_trace_creates_perf_dir(cwd: Path) -> None:
    with patch(
        "dazzle.cli.perf_impl.trace._execute_trace_run",
        side_effect=lambda **kwargs: None,
    ):
        CliRunner().invoke(
            app, ["perf", "trace", "--url", "/tasks", "--duration", "1"]
        )
    assert (cwd / ".dazzle" / "perf").is_dir()


def test_trace_requires_url_or_duration(cwd: Path) -> None:
    result = CliRunner().invoke(app, ["perf", "trace"])
    assert result.exit_code != 0
    assert "Provide at least one --url" in result.stdout or "Provide at least one --url" in (result.stderr or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_perf_cli_trace.py -v`
Expected: FAIL — command doesn't exist.

- [ ] **Step 3: Implement**

Create `src/dazzle/cli/perf_impl/trace.py`:

```python
"""``dazzle perf trace`` — boot a Dazzle app under tracing.

Plans a per-run SQLite path under ``.dazzle/perf/``, sets the env vars
that the runtime reads (``DAZZLE_PERF_ENABLED=1``,
``DAZZLE_PERF_DB``, ``DAZZLE_PERF_RUN_ID``), and shells out to a small
runner that:

1. Configures the global tracer in the *child* uvicorn process.
2. Boots ``dazzle serve --local`` on a free port.
3. Hits each ``--url`` (synchronously) once.
4. Sleeps for ``--duration`` seconds so additional traffic can land.
5. Shuts the server down cleanly.
"""

from __future__ import annotations

from pathlib import Path

import typer

from dazzle.perf.run_id import make_run_id


def trace_command(
    urls: list[str] = typer.Option(
        [], "--url", help="URLs to hit during the trace run (repeatable)."
    ),
    duration: int = typer.Option(
        0,
        "--duration",
        help="Seconds to keep the server alive after URL hits. "
        "0 means exit immediately after the URL hits complete.",
    ),
    report: bool = typer.Option(
        False, "--report", help="Run `dazzle perf report` against the new run when done."
    ),
) -> None:
    """Boot the app under tracing and capture a single run."""
    if not urls and duration <= 0:
        typer.echo(
            "Provide at least one --url or a non-zero --duration. "
            "Run `dazzle perf trace --help` for usage."
        )
        raise typer.Exit(1)

    perf_dir = Path.cwd() / ".dazzle" / "perf"
    perf_dir.mkdir(parents=True, exist_ok=True)
    run_id = make_run_id()
    db_path = perf_dir / f"{run_id}.db"

    _execute_trace_run(
        run_id=run_id,
        db_path=db_path,
        urls=tuple(urls),
        duration=duration,
    )

    typer.echo(f"Trace saved: {db_path}")

    if report:
        from dazzle.cli.perf_impl.report import report_command

        report_command(run=run_id, fmt="md", top=10, baseline=None)


def _execute_trace_run(
    *,
    run_id: str,
    db_path: Path,
    urls: tuple[str, ...],
    duration: int,
) -> None:
    """Spawn uvicorn under tracing, drive the URLs, return on shutdown."""
    import os
    import subprocess
    import sys
    import time
    from urllib.error import URLError
    from urllib.request import urlopen

    env = {
        **os.environ,
        "DAZZLE_PERF_ENABLED": "1",
        "DAZZLE_PERF_DB": str(db_path),
        "DAZZLE_PERF_RUN_ID": run_id,
    }

    # Boot `dazzle serve --local` in a subprocess. Local mode skips
    # Docker spin-up so the trace run starts in seconds.
    proc = subprocess.Popen(
        [sys.executable, "-m", "dazzle.cli", "serve", "--local"],
        env=env,
    )
    base = "http://127.0.0.1:3000"  # default dazzle serve port

    try:
        # Hit each URL once. Failures are non-fatal — the trace captures
        # the error span and the report surfaces it.
        for url in urls:
            target = url if url.startswith("http") else base + url
            try:
                urlopen(target, timeout=10).read()
            except URLError as exc:
                typer.echo(f"  url {target} failed: {exc}")
        if duration > 0:
            typer.echo(
                f"Server up; collecting traces for {duration}s. Hit Ctrl-C to stop early."
            )
            time.sleep(duration)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
```

In `src/dazzle/cli/perf.py`, append:

```python
from dazzle.cli.perf_impl.trace import trace_command

perf_app.command(name="trace")(trace_command)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_perf_cli_trace.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/perf_impl/trace.py src/dazzle/cli/perf.py tests/unit/test_perf_cli_trace.py
git commit -m "feat(perf): dazzle perf trace (boot + drive + capture)"
```

---

## Task 19: Tracer auto-init when the runtime sees `DAZZLE_PERF_DB`

**Files:**
- Modify: `src/dazzle/http/runtime/server.py`
- Test: extend `tests/unit/test_perf_server_integration.py`

- [ ] **Step 1: Extend the test**

Add to `tests/unit/test_perf_server_integration.py`:

```python
def test_tracer_initialised_when_perf_db_env_set(tmp_path: Path) -> None:
    import os
    from unittest.mock import patch

    from dazzle.http.runtime.server import _maybe_configure_tracer

    db = tmp_path / "run.db"
    env = {
        "DAZZLE_PERF_ENABLED": "1",
        "DAZZLE_PERF_DB": str(db),
        "DAZZLE_PERF_RUN_ID": "r1",
    }
    called: dict[str, object] = {}

    def fake_configure(**kwargs):
        called.update(kwargs)

    with patch.dict(os.environ, env), patch(
        "dazzle.perf.tracer.configure_tracer", side_effect=fake_configure
    ):
        _maybe_configure_tracer()

    assert called["run_id"] == "r1"
    assert called["db_path"] == db


def test_tracer_skipped_when_env_unset() -> None:
    import os
    from unittest.mock import patch

    from dazzle.http.runtime.server import _maybe_configure_tracer

    called = False

    def fake_configure(**kwargs):
        nonlocal called
        called = True

    with patch.dict(os.environ, {}, clear=True), patch(
        "dazzle.perf.tracer.configure_tracer", side_effect=fake_configure
    ):
        _maybe_configure_tracer()

    assert not called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_perf_server_integration.py -v`
Expected: FAIL with `ImportError: cannot import name '_maybe_configure_tracer'`

- [ ] **Step 3: Implement**

In `src/dazzle/http/runtime/server.py`, alongside `_maybe_instrument_for_perf`, add:

```python
def _maybe_configure_tracer() -> None:
    """Configure the OTel tracer when ``dazzle perf trace`` set the env.

    Runs before ``_create_app`` so the tracer is live when FastAPI's
    instrumentation attaches.
    """
    import os
    from pathlib import Path

    if os.environ.get("DAZZLE_PERF_ENABLED") != "1":
        return
    db_str = os.environ.get("DAZZLE_PERF_DB")
    run_id = os.environ.get("DAZZLE_PERF_RUN_ID")
    if not db_str or not run_id:
        return
    from dazzle.perf.tracer import configure_tracer

    configure_tracer(
        run_id=run_id,
        db_path=Path(db_str),
        batch=True,
        command_line=" ".join(__import__("sys").argv),
    )
```

Then, inside `_create_app`, **before** the `self._app = _FastAPI(...)` line, add:

```python
_maybe_configure_tracer()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_perf_server_integration.py -v`
Expected: PASS (4 tests total now)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/server.py tests/unit/test_perf_server_integration.py
git commit -m "feat(perf): server-side tracer auto-init from env vars"
```

---

## Task 20: CLI `dazzle perf report`

**Files:**
- Create: `src/dazzle/cli/perf_impl/report.py`
- Modify: `src/dazzle/cli/perf.py`
- Test: `tests/unit/test_perf_cli_report.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_perf_cli_report.py`:

```python
"""dazzle perf report — Markdown + JSON output paths."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dazzle.cli import app
from dazzle.perf.exporter import _SCHEMA_PATH


@pytest.fixture
def seeded_perf_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    perf_dir = tmp_path / ".dazzle" / "perf"
    perf_dir.mkdir(parents=True)
    db = perf_dir / "20260519-120000-aaaaaaaa.db"
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, ended_at, app_name, command_line) "
        "VALUES ('20260519-120000-aaaaaaaa','2026-05-19T12:00:00Z',"
        " '2026-05-19T12:00:05Z','examples/simple_task','dazzle perf trace')"
    )
    conn.execute(
        "INSERT INTO spans VALUES "
        "('s1','t',NULL,'20260519-120000-aaaaaaaa','GET /tasks','server','ok',"
        " 0, 5_000_000, 5_000_000, '{}')"
    )
    conn.commit()
    conn.close()
    return perf_dir


def test_report_default_is_markdown(seeded_perf_dir: Path) -> None:
    result = CliRunner().invoke(app, ["perf", "report"])
    assert result.exit_code == 0
    assert "# Perf report" in result.stdout
    assert "GET /tasks" in result.stdout


def test_report_json_format(seeded_perf_dir: Path) -> None:
    result = CliRunner().invoke(app, ["perf", "report", "--format", "json"])
    assert result.exit_code == 0
    assert '"run_id"' in result.stdout


def test_report_no_runs_returns_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["perf", "report"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_perf_cli_report.py -v`
Expected: FAIL — command doesn't exist.

- [ ] **Step 3: Implement**

Create `src/dazzle/cli/perf_impl/report.py`:

```python
"""``dazzle perf report`` — render findings from a trace SQLite file."""

from __future__ import annotations

from pathlib import Path

import typer

from dazzle.perf.findings import build_findings, render_json, render_markdown
from dazzle.perf.run_id import latest_run_id


def report_command(
    run: str | None = typer.Option(None, "--run", help="Run id (default: latest)"),
    fmt: str = typer.Option("md", "--format", help="md|json"),
    top: int = typer.Option(10, "--top", help="Per-section row cap"),  # noqa: ARG001
    baseline: str | None = typer.Option(
        None,
        "--baseline",
        help="Diff mode — compare against a prior run id (not yet implemented).",
    ),  # noqa: ARG001
) -> None:
    perf_dir = Path.cwd() / ".dazzle" / "perf"
    run_id = run or latest_run_id(perf_dir)
    if run_id is None:
        typer.echo("No perf runs found. Run `dazzle perf trace` first.")
        raise typer.Exit(1)
    db_path = perf_dir / f"{run_id}.db"
    if not db_path.exists():
        typer.echo(f"No trace file for run {run_id}")
        raise typer.Exit(1)

    report = build_findings(db_path, run_id)
    if fmt == "json":
        typer.echo(render_json(report))
    else:
        typer.echo(render_markdown(report))
```

In `src/dazzle/cli/perf.py`, append:

```python
from dazzle.cli.perf_impl.report import report_command

perf_app.command(name="report")(report_command)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_perf_cli_report.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/cli/perf_impl/report.py src/dazzle/cli/perf.py tests/unit/test_perf_cli_report.py
git commit -m "feat(perf): dazzle perf report (md + json)"
```

---

## Task 21: MCP handler

**Files:**
- Create: `src/dazzle/mcp/server/handlers/perf.py`
- Modify: `src/dazzle/mcp/server/handlers_consolidated.py`
- Modify: `src/dazzle/mcp/server/tools_consolidated.py`
- Test: `tests/unit/test_perf_mcp_handler.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_perf_mcp_handler.py`:

```python
"""MCP handler operations test."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from dazzle.mcp.server.handlers.perf import handle_perf
from dazzle.perf.exporter import _SCHEMA_PATH


@pytest.fixture
def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    perf_dir = tmp_path / ".dazzle" / "perf"
    perf_dir.mkdir(parents=True)
    db = perf_dir / "20260519-120000-aaaaaaaa.db"
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, ended_at, app_name, command_line) "
        "VALUES ('20260519-120000-aaaaaaaa','2026-05-19T12:00:00Z','2026-05-19T12:00:05Z','app','x')"
    )
    conn.execute(
        "INSERT INTO spans VALUES "
        "('s1','t',NULL,'20260519-120000-aaaaaaaa','GET /x','server','ok',0,1000,1000,'{}')"
    )
    conn.commit()
    conn.close()
    return perf_dir


def test_perf_list_returns_runs(seeded: Path) -> None:
    out = handle_perf({"operation": "list"})
    assert "runs" in out
    assert out["runs"][0]["run_id"] == "20260519-120000-aaaaaaaa"


def test_perf_report_returns_json_findings(seeded: Path) -> None:
    out = handle_perf({"operation": "report"})
    assert "findings" in out
    parsed = json.loads(out["findings"])
    assert parsed["run_id"] == "20260519-120000-aaaaaaaa"


def test_perf_show_returns_span_tree(seeded: Path) -> None:
    out = handle_perf({"operation": "show"})
    assert "spans" in out
    assert any(s["name"] == "GET /x" for s in out["spans"])


def test_perf_unknown_op_errors(seeded: Path) -> None:
    out = handle_perf({"operation": "bogus"})
    assert "error" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_perf_mcp_handler.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement**

Create `src/dazzle/mcp/server/handlers/perf.py`:

```python
"""MCP handler for the ``perf`` tool (read-only).

Operations:
  - ``list``: enumerate past runs from ``.dazzle/perf/``
  - ``report`` (``--run`` optional, default latest): return the JSON
    findings payload as a string under ``findings``.
  - ``show`` (``--run`` optional): return the span tree as a list of
    dicts.

CLI vs MCP boundary (ADR-0002): no process-launching operations on this
handler. ``dazzle perf trace`` stays CLI-only because it spawns
subprocesses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dazzle.perf.findings import build_findings, render_json
from dazzle.perf.run_id import latest_run_id
from dazzle.perf.storage import iter_spans, list_runs


def handle_perf(args: dict[str, Any]) -> dict[str, Any]:
    operation = args.get("operation")
    if operation == "list":
        return _do_list()
    if operation == "report":
        return _do_report(args.get("run"))
    if operation == "show":
        return _do_show(args.get("run"))
    return {"error": f"unknown operation {operation!r}"}


def _perf_dir() -> Path:
    return Path.cwd() / ".dazzle" / "perf"


def _do_list() -> dict[str, Any]:
    perf_dir = _perf_dir()
    if not perf_dir.is_dir():
        return {"runs": []}
    runs: list[dict[str, Any]] = []
    for db_path in sorted(perf_dir.glob("*.db")):
        for run in list_runs(db_path):
            runs.append(
                {
                    "run_id": run.run_id,
                    "started_at": run.started_at,
                    "ended_at": run.ended_at,
                    "app_name": run.app_name,
                    "command_line": run.command_line,
                }
            )
    return {"runs": runs}


def _resolve_run(run: str | None) -> tuple[Path, str] | None:
    perf_dir = _perf_dir()
    run_id = run or latest_run_id(perf_dir)
    if run_id is None:
        return None
    db_path = perf_dir / f"{run_id}.db"
    if not db_path.exists():
        return None
    return db_path, run_id


def _do_report(run: str | None) -> dict[str, Any]:
    resolved = _resolve_run(run)
    if resolved is None:
        return {"error": "no matching run"}
    db_path, run_id = resolved
    report = build_findings(db_path, run_id)
    return {"findings": render_json(report)}


def _do_show(run: str | None) -> dict[str, Any]:
    resolved = _resolve_run(run)
    if resolved is None:
        return {"error": "no matching run"}
    db_path, run_id = resolved
    spans = [
        {
            "span_id": s.span_id,
            "parent_span_id": s.parent_span_id,
            "name": s.name,
            "kind": s.kind,
            "status": s.status,
            "duration_ms": s.duration_ns / 1e6,
        }
        for s in iter_spans(db_path, run_id)
    ]
    return {"spans": spans}
```

In `src/dazzle/mcp/server/handlers_consolidated.py`, find the existing tool-name → handler dispatch (likely a dict or `match` statement). Add:

```python
from dazzle.mcp.server.handlers.perf import handle_perf
# ...
"perf": handle_perf,
```

In `src/dazzle/mcp/server/tools_consolidated.py`, add a tool schema following the existing pattern:

```python
{
    "name": "perf",
    "description": "Local OpenTelemetry trace findings for the current project (read-only).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["list", "report", "show"],
                "description": "Which read operation to perform.",
            },
            "run": {
                "type": "string",
                "description": "Run id (default: latest).",
            },
        },
        "required": ["operation"],
    },
},
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_perf_mcp_handler.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/mcp/server/handlers/perf.py src/dazzle/mcp/server/handlers_consolidated.py src/dazzle/mcp/server/tools_consolidated.py tests/unit/test_perf_mcp_handler.py
git commit -m "feat(perf): MCP perf tool (list, report, show — read-only)"
```

---

## Task 22: Reference docs

**Files:**
- Create: `docs/reference/perf-observability.md`
- Create: `docs/reference/perf-findings-schema.md`

- [ ] **Step 1: Write the user-facing reference**

Create `docs/reference/perf-observability.md`:

```markdown
# Performance observability — `dazzle perf`

Local, on-demand OpenTelemetry tracing for any Dazzle project. Captures
a single trace run to `.dazzle/perf/<run-id>.db` and emits agent-friendly
findings on slow endpoints, slow queries, suspected N+1 patterns, slow
framework phases, and exceptions.

## Install

```bash
pip install -e ".[perf]"
```

Adds the OTel SDK + the three auto-instrumentations (`fastapi`,
`psycopg`, `asyncio`). No collector required — the bundled SQLite
exporter writes a self-contained trace file per run.

## Workflow

1. **Capture a run** while hitting one or more URLs:
   ```bash
   dazzle perf trace --url /tasks --url /users --duration 10
   ```
   Boots the app under tracing, hits the URLs, then keeps the server
   alive for `--duration` seconds so any background traffic (HTMX
   prefetch, websocket pings) also lands.

2. **Read findings**:
   ```bash
   dazzle perf report                 # Markdown, paste into Claude
   dazzle perf report --format json   # for tool-use
   ```

3. **Dig deeper**:
   ```bash
   dazzle perf list                   # past runs
   dazzle perf show --run <id>        # span tree
   ```

## What gets instrumented

**Automatically:**
- FastAPI requests
- psycopg SQL queries
- asyncio task spans

**Manually (Dazzle's hot paths):**
- `dsl.parse` — top-level parse
- `predicate.compile` — scope-rule SQL compile
- `aggregate.expression.compile` — L3 inner SQL compile
- `aggregate.build_sql` — GROUP BY composer
- `repo.aggregate` — outer Repository.aggregate call
- `region.render` — per-region render
- `fragment.emit` — fragment emission

## Agent ergonomics

The Markdown report is the source of truth for agents — designed to
paste into a Claude conversation. Section structure is stable; an
agent can rely on `## Slow endpoints`, `## Suspected N+1 patterns`,
etc., as recognisable hooks.

For programmatic use, see `docs/reference/perf-findings-schema.md`.

## MCP

The `perf` MCP tool exposes read-only operations: `list`, `report`,
`show`. The `trace` subcommand stays CLI-only because it spawns a
subprocess (ADR-0002).
```

- [ ] **Step 2: Write the schema reference**

Create `docs/reference/perf-findings-schema.md`:

```markdown
# `dazzle perf report --format json` schema

The JSON payload is a serialisation of `dazzle.perf.findings.types.FindingsReport`.

```json
{
  "run_id": "string",
  "app_name": "string | null",
  "started_at": "ISO 8601 string",
  "ended_at": "ISO 8601 string | null",
  "slow_endpoints":  [ { "route": "GET /tasks", "calls": 12, "total_ms": 4200.0, "p95_ms": 380.0 } ],
  "slow_queries":    [ { "statement": "SELECT FROM task", "calls": 12, "total_ms": 1100.0 } ],
  "n_plus_one":      [ { "parent_span": "GET /tasks", "child_statement": "SELECT FROM user", "repetitions": 24 } ],
  "slow_phases":     [ { "name": "aggregate.build_sql", "calls": 8, "total_ms": 120.0, "max_ms": 30.0 } ],
  "render_fanout":   [ { "route": "GET /tasks", "region_renders": 18, "total_ms": 600.0 } ],
  "boot_cost":       { "parse_dsl_ms": 240.0, "route_gen_ms": 80.0, "total_ms": 320.0 } | null,
  "exceptions":      [ { "span_name": "repo.aggregate", "message": "bad SQL", "count": 1 } ]
}
```

## Stability

The field names and shapes here are the public contract. Renaming or
removing a field requires:

1. CHANGELOG entry under **Changed** or **Removed**.
2. Update of this doc in the same commit.
3. Discussion on whether to bump the schema-version key (none today —
   add one when the first breaking change lands).
```

- [ ] **Step 3: Commit**

```bash
git add docs/reference/perf-observability.md docs/reference/perf-findings-schema.md
git commit -m "docs(perf): user reference + findings JSON schema"
```

---

## Task 23: Gitignore + CHANGELOG + version bump

**Files:**
- Modify: `.gitignore`
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`

- [ ] **Step 1: Update `.gitignore`**

Append to `.gitignore`:

```
# Local OpenTelemetry trace runs from `dazzle perf trace` (#1153 follow-on).
.dazzle/perf/
```

- [ ] **Step 2: Bump the version**

In `pyproject.toml`, change:

```toml
version = "0.71.68"
```

to:

```toml
version = "0.71.69"
```

- [ ] **Step 3: Add CHANGELOG entry**

In `CHANGELOG.md`, insert after the `## [Unreleased]` line:

```markdown
## [0.71.69] - 2026-05-19

### Added

- **`dazzle perf` toolkit** — local, on-demand OpenTelemetry tracing.
  Captures a single run to `.dazzle/perf/<run-id>.db` via the bundled
  SQLite span exporter; emits agent-ergonomic findings on slow
  endpoints, slow queries, suspected N+1 patterns, slow framework
  phases, render fan-out, boot cost, and exceptions.

  CLI:
  - `dazzle perf trace [--url URL ...] [--duration N]` — boot under
    tracing and capture.
  - `dazzle perf report [--run ID] [--format md|json]` — emit findings.
  - `dazzle perf list` / `dazzle perf show [--run ID]` — inspect runs.

  MCP: new `perf` tool with read-only `list` / `report` / `show`
  operations. `trace` stays CLI-only (ADR-0002).

  Hot paths newly instrumented as named spans: `dsl.parse`,
  `predicate.compile`, `aggregate.expression.compile`,
  `aggregate.build_sql`, `repo.aggregate`, `region.render`,
  `fragment.emit`.

  Install: `pip install -e ".[perf]"` (new optional extra).

### Agent Guidance

- Treat `dazzle perf report` as the canonical "what's slow / what's
  buggy" probe for any Dazzle project. The Markdown output is stable;
  the JSON schema is pinned in `docs/reference/perf-findings-schema.md`.
- When a Dazzle user reports a perf complaint, the right first step
  is to ask them to run `dazzle perf trace --url <complaint-URL>`
  followed by `dazzle perf report`, then paste the Markdown back.
  Findings categories are stable: slow_endpoints, slow_queries,
  n_plus_one, slow_phases, render_fanout, boot_cost, exceptions.
- New framework hot paths must be wrapped with
  `dazzle_span("<name>", ...)` and added to `DAZZLE_PHASE_NAMES` in
  `src/dazzle/perf/findings/extractor.py` so they appear in the
  "Dazzle hot phases" section.
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore CHANGELOG.md pyproject.toml
git commit -m "chore(perf): gitignore + CHANGELOG + version bump for 0.71.69"
```

---

## Task 24: Full unit slice + quality gate

**Files:** none new.

- [ ] **Step 1: Run lint + format + types**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/ && mypy src/dazzle`
Expected: All checks pass.

- [ ] **Step 2: Run the full unit slice**

Run: `pytest tests/ -m "not e2e" -q`
Expected: All previous tests still pass; ~30 new perf tests included. Net delta ~15,510 passing.

If `tests/unit/test_api_surface_drift.py::test_surface_matches_baseline[ir_types]` fails, the new Pydantic models added in Task 8 caused expected drift. Run:

```bash
dazzle inspect api ir-types --write
git add docs/api-surface/ir-types.txt
```

and add to the previous commit with `git commit --amend --no-edit`.

- [ ] **Step 3: Manual smoke against `examples/simple_task`**

```bash
cd examples/simple_task
dazzle perf trace --url / --duration 3
dazzle perf report
```

Expected: a non-empty Markdown report with at least slow_endpoints + slow_phases rows. If the report is empty for a fresh example, that's information too — note it in the issue / follow-up rather than blocking the ship.

- [ ] **Step 4: Ship**

```bash
git push
gh run list --branch main --limit 3
```

---

## Self-Review

### Spec coverage

- ✅ Local-only OTel with custom SQLite exporter — Tasks 1, 4
- ✅ `dazzle perf trace` with `--url` (repeatable) + `--duration` — Task 18
- ✅ `dazzle perf report` with `--format md|json` — Task 20
- ✅ Split `trace` and `report` (independent) — Tasks 18, 20
- ✅ N+1 heuristic ≥ 3 — Task 11
- ✅ Manual spans on the 7 hot phases — Task 15
- ✅ Pydantic-aware span serialiser — Task 3
- ✅ Read-only MCP tool — Task 21
- ✅ Single PR — all tasks land on one feature branch; no intermediate releases.

### Placeholder scan

No "TBD", "implement later", "similar to Task N" strings remain. Every code step shows full code.

### Type consistency

- `Finding` union members match: `SlowEndpoint`, `SlowQuery`, `NPlusOne`, `SlowPhase`, `RenderFanOut`, `BootCost`, `ExceptionFinding` — declared in Task 8, referenced consistently in Tasks 9–14.
- `Span`, `Run`, `Event` dataclasses declared in Task 7, consumed in Tasks 17 (`iter_spans`), 21 (`handle_perf`).
- `dazzle_span` signature `(name, **attrs)` declared in Task 5; callers in Task 15 use it with named kwargs.
- `configure_tracer(run_id=, db_path=, batch=, app_name=, manifest_path=, command_line=)` — keyword shape declared in Task 5; called from Tasks 18, 19 with the same kwargs.
- `build_findings(db_path, run_id) -> FindingsReport` — signature declared in Task 8, called from Tasks 20 (CLI), 21 (MCP).
- The 7 phase names (`dsl.parse`, `predicate.compile`, `aggregate.expression.compile`, `aggregate.build_sql`, `repo.aggregate`, `region.render`, `fragment.emit`) appear consistently in Task 12 (`DAZZLE_PHASE_NAMES`), Task 15 (instrumentation sites), and Task 22 (docs).

No inconsistencies found.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-19-perf-observability.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
